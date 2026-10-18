"""docs/28 (A4) — the version-controlled source registry and its idempotent sync.

The manifest carries IDENTITY only. Sync registers a missing source DISABLED with
ToS and robots UNKNOWN, reports drift without overwriting, and never reviews,
authorizes, enables, schedules or fetches. Offline; DB tests roll back.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import discovery as cli
from app.db import session as db_session
from app.db.session import engine
from app.models.discovery import DiscoverySource, DiscoverySourceOwnerAuthorizationEvent
from app.services.discovery import DiscoveryError
from app.services.discovery.source_manifest import (
    DRIFT,
    REGISTERED,
    UNCHANGED,
    UNMANAGED,
    WOULD_REGISTER,
    load_manifest,
    sync_sources,
)
from app.services.discovery.sources import ADAPTERS

pytestmark = pytest.mark.usefixtures("no_external_network")

#: The owner's 2026-10-18 A4 monitoring programme.
A4_SOURCES = {"unitree-robotics-official", "booster-robotics-official", "agibot-official",
              "agility-robotics-official", "figure-ai-official", "alza-cz"}
#: Registered and running before A4, on SOURCE_PERMISSION (owner ToS ALLOWED).
EXISTING = {"neura-robotics-official", "neura-documents-official", "xpeng-official"}


# ---------------------------------------------------------------- manifest (pure) --


def test_manifest_lists_exactly_the_nine_registered_sources():
    entries = load_manifest()
    assert {e["key"] for e in entries} == A4_SOURCES | EXISTING
    assert [e["key"] for e in entries] == sorted(e["key"] for e in entries)


def test_manifest_hosts_are_single_origins_and_claim_no_store_host():
    entries = {e["key"]: e for e in load_manifest()}
    assert entries["unitree-robotics-official"]["homepage_url"] == "https://www.unitree.com/"
    assert entries["alza-cz"]["homepage_url"] == "https://www.alza.cz/"
    assert not any("shop." in e["homepage_url"] or "store." in e["homepage_url"]
                   for e in entries.values())
    assert entries["alza-cz"]["source_class"] == "DISTRIBUTOR"   # a retailer, not a maker


def test_manifest_adapters_match_code_and_only_reviewed_a4_adapters_exist():
    """Adapter readiness is code, not data. When an A4 adapter lands (after its
    structural review), this test is updated in that same reviewed PR: Unitree (2026-10-18,
    UNITREE_STRUCTURAL_REVIEW_2026-10-18) is the first."""
    entries = {e["key"]: e for e in load_manifest()}
    for key, config in ADAPTERS.items():
        assert key in entries
        assert entries[key]["homepage_url"] == f"https://{config.host}/"
        assert entries[key]["source_class"] == config.source_class
    assert A4_SOURCES & set(ADAPTERS) == {"unitree-robotics-official"}


@pytest.mark.parametrize("bad", [
    {"homepage_url": "http://x.example/"}, {"homepage_url": "https://x.example/shop"},
    {"homepage_url": "https://X.example/"}, {"source_class": "SHOP"}, {"name": " "},
])
def test_manifest_validation_fails_closed(tmp_path, bad):
    entry = {"key": "k", "name": "N", "source_class": "MANUFACTURER",
             "homepage_url": "https://x.example/", **bad}
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"sources": [entry]}), encoding="utf-8")
    with pytest.raises(DiscoveryError):
        load_manifest(path)


def test_manifest_refuses_duplicate_keys(tmp_path):
    entry = {"key": "k", "name": "N", "source_class": "MANUFACTURER",
             "homepage_url": "https://x.example/"}
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"sources": [entry, entry]}), encoding="utf-8")
    with pytest.raises(DiscoveryError, match="duplicate"):
        load_manifest(path)


# ----------------------------------------------------------------- sync (database) --


@pytest.fixture
def shared_session(database_url, monkeypatch):
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False)
    session.commit = session.flush       # CLI commits must not escape the rollback
    session.rollback = lambda: None      # ... nor may a plan's rollback end the test

    @contextmanager
    def local():
        yield session

    monkeypatch.setattr(db_session, "SessionLocal", local)
    try:
        present = set(session.scalars(select(DiscoverySource.key).where(
            DiscoverySource.key.in_(A4_SOURCES | EXISTING))))
        assert not present, f"unexpected rows in the test database: {present}"
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


def _ours(result):
    return {line.key: line for line in result.lines if line.key in A4_SOURCES | EXISTING}


def _production_like(session):
    """The three running sources as production holds them (abridged)."""
    when = datetime(2026, 9, 26, tzinfo=UTC)
    for key, name, cls, home, paths, hours in (
            ("neura-robotics-official", "NEURA Robotics", "MANUFACTURER",
             "https://neura-robotics.com/", ["/products/"], 48),
            ("neura-documents-official", "NEURA Robotics documents (px.media)",
             "OFFICIAL_DOCUMENT", "https://neurarobotics.px.media/", ["/plk/"], 168),
            ("xpeng-official", "XPENG", "MANUFACTURER", "https://www.xpeng.com/",
             ["/technology/ai_robot_iron"], 120)):
        session.add(DiscoverySource(
            key=key, name=name, source_class=cls, homepage_url=home, is_enabled=True,
            tos_status="ALLOWED", robots_status="ALLOWED", eligibility_reviewed_at=when,
            eligibility_reviewed_by="owner", allowed_path_prefixes=paths,
            observation_interval_hours=hours, observation_cadence_set_by="Robert",
            observation_cadence_set_at=when))
    session.flush()


_COLS = ("key", "name", "source_class", "homepage_url", "is_enabled", "tos_status",
         "robots_status", "access_basis", "owner_authorized_by", "allowed_path_prefixes",
         "observation_interval_hours", "eligibility_reviewed_by", "notes")


def _state(session) -> dict:
    rows = session.scalars(select(DiscoverySource).where(
        DiscoverySource.key.in_(A4_SOURCES | EXISTING)))
    return {r.key: {c: getattr(r, c) for c in _COLS} for r in rows}


def test_plan_writes_nothing_and_apply_registers_only_the_missing_disabled(shared_session):
    _production_like(shared_session)
    before = _state(shared_session)
    plan = _ours(sync_sources(shared_session, apply=False))
    assert {k for k, line in plan.items() if line.status == WOULD_REGISTER} == A4_SOURCES
    assert {k for k, line in plan.items() if line.status == UNCHANGED} == EXISTING
    assert _state(shared_session) == before                      # plan wrote nothing

    applied = _ours(sync_sources(shared_session, apply=True, by="robert"))
    assert {k for k, line in applied.items() if line.status == REGISTERED} == A4_SOURCES
    after = _state(shared_session)
    assert {k: after[k] for k in EXISTING} == before              # running sources untouched
    for key in A4_SOURCES:
        row = after[key]
        assert (row["is_enabled"], row["tos_status"], row["robots_status"],
                row["access_basis"], row["owner_authorized_by"], row["allowed_path_prefixes"],
                row["observation_interval_hours"], row["eligibility_reviewed_by"]) == (
            False, "UNKNOWN", "UNKNOWN", "SOURCE_PERMISSION", None, None, None, None)
    assert shared_session.scalar(select(func.count()).select_from(
        DiscoverySourceOwnerAuthorizationEvent)) == 0                # nothing authorized


def test_reapplying_the_sync_changes_nothing(shared_session):
    _production_like(shared_session)
    sync_sources(shared_session, apply=True, by="robert")
    once = _state(shared_session)
    second = _ours(sync_sources(shared_session, apply=True, by="robert"))
    assert {line.status for line in second.values()} == {UNCHANGED}
    assert _state(shared_session) == once                         # notes included


def test_drift_is_reported_never_overwritten(shared_session):
    _production_like(shared_session)
    xpeng = shared_session.scalar(select(DiscoverySource).where(
        DiscoverySource.key == "xpeng-official"))
    xpeng.homepage_url = "https://shop.xpeng.com/"
    shared_session.flush()
    result = sync_sources(shared_session, apply=True, by="robert")
    line = _ours(result)["xpeng-official"]
    assert line.status == DRIFT and "not overwritten" in line.detail
    assert xpeng.homepage_url == "https://shop.xpeng.com/" and xpeng.is_enabled is True
    assert result.needs_attention


def test_a_database_only_source_is_reported_unmanaged_and_kept(shared_session):
    shared_session.add(DiscoverySource(key="zz-unlisted-source", name="Unlisted",
                                       source_class="OTHER"))
    shared_session.flush()
    lines = {x.key: x for x in sync_sources(shared_session, apply=False).lines}
    assert lines["zz-unlisted-source"].status == UNMANAGED
    assert shared_session.scalar(select(DiscoverySource).where(
        DiscoverySource.key == "zz-unlisted-source")) is not None


def test_apply_requires_attribution(shared_session):
    with pytest.raises(DiscoveryError, match="--by"):
        sync_sources(shared_session, apply=True, by=" ")


def test_cli_sync_reports_adapter_readiness(shared_session, capsys):
    _production_like(shared_session)
    code = cli.main(["source", "sync"])
    out = capsys.readouterr().out
    assert "PLAN (no write)" in out
    line = next(x for x in out.splitlines() if "booster-robotics-official" in x)
    assert "WOULD_REGISTER" in line and "adapter=NONE" in line
    line = next(x for x in out.splitlines() if "unitree-robotics-official" in x)
    assert "WOULD_REGISTER" in line and "adapter=unitree-robotics-official@0.1.0" in line
    line = next(x for x in out.splitlines() if "neura-documents-official" in x)
    assert "adapter=LANE_B_DOCUMENT" in line
    line = next(x for x in out.splitlines() if " xpeng-official" in x)
    assert "adapter=xpeng-official@0.1.0" in line
    assert code in (0, 4)       # 4 only when the shared test database holds other sources
    assert cli.main(["source", "sync", "--apply"]) == 1          # refused: no --by
