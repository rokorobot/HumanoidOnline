"""Gate Q — raw-body cache retention (docs/16 LIVE.10), offline.

The cache is produced by real (synthetic, offline) observation cycles, then
pruned with an injected clock far in the future. Proves: dry run removes
nothing; only superseded bodies past 90 days and old orphans go; the latest
body of every URL and bodies of open runs stay; sidecars (provenance) stay;
nothing that is not a digest-named regular file directly under the root is
ever touched, including a symlink pointing outside it.
"""
from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_discovery_stage_f_observe import Harness, dsession, product  # noqa: F401

from app.models.acquisition import CrawlRun
from app.services.discovery import DiscoveryError
from app.services.discovery.cache_retention import BODY_RETENTION, prune_cache

pytestmark = pytest.mark.usefixtures("no_external_network")


@pytest.fixture
def h(dsession, tmp_path) -> Harness:  # noqa: F811
    return Harness(dsession, tmp_path)


def _two_cycles(h: Harness):
    site = h.source("a")
    _, first, _ = h.cycle()
    site.pages["/products/b"] = product("X-B", "<p>changed</p>")
    h.advance(25)
    h.cycle()
    return site, first[site.key].run_id


def _bodies(root) -> set[str]:
    return {p.name for p in root.iterdir() if p.is_file() and re.fullmatch(r"[0-9a-f]{64}", p.name)}


def _future(h: Harness) -> datetime:
    return max(datetime.now(UTC), h.now()) + timedelta(days=200)


def _age(path, now: datetime, days: int) -> None:
    stamp = (now - timedelta(days=days)).timestamp()
    os.utime(path, (stamp, stamp))


def test_retention_period_is_the_settled_live10_value():
    assert BODY_RETENTION == timedelta(days=90)


def test_dry_run_then_apply_removes_only_superseded_expired_bodies_and_old_orphans(h, tmp_path):
    _two_cycles(h)
    root = h.cache_dir
    now = _future(h)
    bodies = _bodies(root)
    assert len(bodies) == 4                      # listing, a, b (v1), b (v2)
    sidecars = sorted(p.name for p in (root / "observations").iterdir())
    old_orphan, new_orphan = root / ("0" * 64), root / ("1" * 64)
    old_orphan.write_bytes(b"orphan")
    new_orphan.write_bytes(b"orphan")
    _age(old_orphan, now, 120)
    _age(new_orphan, now, 1)
    bystanders = {"README.txt": b"keep", "KILL": b"", ("f" * 63) + "g": b"not a digest"}
    for name, data in bystanders.items():
        (root / name).write_bytes(data)
    (root / ("2" * 64 + "-dir")).mkdir()
    (root / ("3" * 64)).mkdir()                  # digest-named directory: skipped

    report = prune_cache(h.session, root, now=now)
    assert not report.applied
    assert [why for _, _, why in report.prune].count(
        "orphan (no sidecar) older than window") == 1
    assert len(report.prune) == 2                # b v1 + the old orphan
    assert report.kept == {"BASELINE": 3, "RECENT": 1}
    assert _bodies(root) == bodies | {old_orphan.name, new_orphan.name}   # dry run: untouched
    assert "DRY RUN" in "\n".join(report.lines())

    applied = prune_cache(h.session, root, now=now, apply=True)
    assert [d for d, _, _ in applied.prune] == [d for d, _, _ in report.prune]  # deterministic
    remaining = _bodies(root)
    assert old_orphan.name not in remaining and new_orphan.name in remaining
    assert len(remaining & bodies) == 3          # the latest body of every URL
    assert sorted(p.name for p in (root / "observations").iterdir()) == sidecars
    for name, data in bystanders.items():
        assert (root / name).read_bytes() == data
    assert (root / ("3" * 64)).is_dir() and (root / ("2" * 64 + "-dir")).is_dir()


def test_nothing_is_pruned_inside_the_window(h):
    _two_cycles(h)
    report = prune_cache(h.session, h.cache_dir, now=h.now() + timedelta(days=30))
    assert report.prune == []


def test_bodies_of_an_open_run_are_kept(h):
    _, first_run = _two_cycles(h)
    run = h.session.get(CrawlRun, first_run)
    run.status = "FAILED"                        # a resume could still extract it
    h.session.flush()
    report = prune_cache(h.session, h.cache_dir, now=_future(h))
    assert report.prune == [] and report.kept.get("OPEN_RUN") == 3


def test_symlink_pointing_outside_is_never_followed_or_removed(h, tmp_path):
    _two_cycles(h)
    victim = tmp_path / "outside.txt"
    victim.write_bytes(b"precious")
    link = h.cache_dir / ("4" * 64)
    try:
        link.symlink_to(victim)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this machine")
    now = _future(h)
    report = prune_cache(h.session, h.cache_dir, now=now, apply=True)
    assert (link.name, "not a regular file directly under the root") in report.skipped
    assert victim.read_bytes() == b"precious" and link.is_symlink()


def test_root_must_exist_and_must_not_be_a_symlink(h, tmp_path):
    with pytest.raises(DiscoveryError, match="does not exist"):
        prune_cache(h.session, tmp_path / "missing")
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this machine")
    with pytest.raises(DiscoveryError, match="symlink"):
        prune_cache(h.session, alias)


def test_pruned_history_does_not_break_the_next_cycle(h):
    site, _ = _two_cycles(h)
    prune_cache(h.session, h.cache_dir, now=_future(h), apply=True)
    h.advance(25)
    _, by_key, _ = h.cycle()
    assert by_key[site.key].status == "COMPLETED" and by_key[site.key].counts["errors"] == 0
    assert h.session.scalars(select(CrawlRun.status).where(
        CrawlRun.id == by_key[site.key].run_id)).one() == "COMPLETED"
