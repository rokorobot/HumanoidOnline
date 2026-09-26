"""Gate Q — raw-body cache retention (docs/16 LIVE.10 / §19 Gate Q).

LIVE.10 (owner decision D-3) settles the periods: successful raw page bodies
90 days, failed/blocked responses 30 days, and crawl manifests, hashes,
excerpts and provenance records indefinitely. So this prunes only BODIES:

- observation sidecars (`observations/<fetched_page_id>.json`) are provenance
  records and are never removed;
- failed/blocked responses are never cached in the first place (only a 2xx body
  is stored), so the 30-day rule has nothing to act on today.

A body is KEPT when any of these holds, whatever its age:

  RECENT     an observation referencing it was retrieved within the window;
  BASELINE   it is the latest successful observation of its URL: a later 304 is
             answered from it (seed expansion, re-extraction), and a conditional
             request is only sent while it exists;
  OPEN_RUN   it belongs to a RUNNING / FAILED / CANCELLED run (a resume may
             still extract it).

A body no sidecar references is an orphan (an observation that was rolled
back); it is pruned only once its file is older than the window.

Safety: deterministic (sorted, clock injected); dry run unless `apply=True`;
only regular, non-symlink files named by a 64-hex digest directly under the
cache root are ever candidates; the root itself may not be a symlink; nothing
outside it can be named, so nothing outside it can be removed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.acquisition import CrawlRun, FetchedPage
from app.services.discovery import DiscoveryError

#: LIVE.10: successful raw page bodies are retained for 90 days.
BODY_RETENTION = timedelta(days=90)
_DIGEST = re.compile(r"[0-9a-f]{64}")
_OPEN_RUN_STATUSES = ("RUNNING", "FAILED", "CANCELLED")


@dataclass
class PruneReport:
    root: str
    cutoff: datetime
    applied: bool
    kept: dict[str, int] = field(default_factory=dict)       # reason -> bodies
    prune: list[tuple[str, int, str]] = field(default_factory=list)  # digest, bytes, why
    skipped: list[tuple[str, str]] = field(default_factory=list)     # name, why

    def lines(self) -> list[str]:
        mode = "APPLIED" if self.applied else "DRY RUN (nothing removed)"
        total = sum(size for _, size, _ in self.prune)
        return [
            f"CACHE RETENTION {mode}  root={self.root}",
            f"  window: bodies retained {BODY_RETENTION.days} days (docs/16 LIVE.10); "
            f"cutoff {self.cutoff.isoformat()}; sidecars/provenance kept indefinitely",
            *(f"  KEPT {reason:<10} {count}" for reason, count in sorted(self.kept.items())),
            f"  {'REMOVED' if self.applied else 'WOULD REMOVE'} {len(self.prune)} body file(s), "
            f"{total} bytes",
            *(f"    {digest}  {size:>10}  {why}" for digest, size, why in self.prune),
            *(f"  SKIPPED {name}  ({why})" for name, why in self.skipped),
        ]


def _sidecars(root: Path) -> dict[str, str]:
    """fetched_page_id -> raw body digest, from the observation sidecars."""
    out: dict[str, str] = {}
    folder = root / "observations"
    if not folder.is_dir() or folder.is_symlink():
        return out
    for path in sorted(folder.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            digest = json.loads(path.read_text(encoding="utf-8"))["raw_sha256"]
        except (OSError, KeyError, ValueError, TypeError):
            continue
        if isinstance(digest, str) and _DIGEST.fullmatch(digest):
            out[path.stem] = digest
    return out


def _protected_page_ids(session: Session, cutoff: datetime) -> dict[str, set[str]]:
    """reason -> fetched_page ids whose bodies must be kept (plus KNOWN: every
    successful observation in the database)."""
    pages = session.execute(
        select(FetchedPage.id, FetchedPage.source_id, FetchedPage.url, FetchedPage.retrieved_at,
               CrawlRun.status)
        .join(CrawlRun, CrawlRun.id == FetchedPage.crawl_run_id)
        .where(FetchedPage.outcome == "FETCHED")
        .order_by(FetchedPage.retrieved_at, FetchedPage.id)
    ).all()
    latest: dict[tuple, str] = {}
    protected: dict[str, set[str]] = {"RECENT": set(), "BASELINE": set(), "OPEN_RUN": set(),
                                      "KNOWN": set()}
    for page_id, source_id, url, retrieved_at, run_status in pages:
        protected["KNOWN"].add(str(page_id))
        latest[(source_id, url)] = str(page_id)  # ordered by time: the last one wins
        if retrieved_at >= cutoff:
            protected["RECENT"].add(str(page_id))
        if run_status in _OPEN_RUN_STATUSES:
            protected["OPEN_RUN"].add(str(page_id))
    protected["BASELINE"] = set(latest.values())
    return protected


def prune_cache(session: Session, root: Path, *, now: datetime | None = None,
                apply: bool = False) -> PruneReport:
    """Report (and with `apply`, remove) cache bodies past LIVE.10 retention."""
    if root.is_symlink():
        raise DiscoveryError(f"cache root {root} is a symlink; refusing to prune")
    if not root.is_dir():
        raise DiscoveryError(f"cache root {root} does not exist")
    base = root.resolve()
    when = (now or datetime.now(UTC)).astimezone(UTC)
    cutoff = when - BODY_RETENTION
    report = PruneReport(root=str(base), cutoff=cutoff, applied=apply)

    by_page = _sidecars(base)
    referenced: dict[str, set[str]] = {}
    for page_id, digest in by_page.items():
        referenced.setdefault(digest, set()).add(page_id)
    protected = _protected_page_ids(session, cutoff)

    for path in sorted(base.iterdir(), key=lambda p: p.name):
        name = path.name
        if not _DIGEST.fullmatch(name):
            continue  # sidecar folder, kill switches, temp files: never touched
        if path.is_symlink() or not path.is_file() or path.resolve().parent != base:
            report.skipped.append((name, "not a regular file directly under the root"))
            continue
        # Sidecars of observations the database does not hold (rolled back) do
        # not count: such a body is an orphan and ages by its file time.
        pages = referenced.get(name, set()) & protected["KNOWN"]
        reason = next((r for r in ("OPEN_RUN", "BASELINE", "RECENT")
                       if pages & protected[r]), None)
        if reason is None and not pages:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if mtime >= cutoff:
                reason = "RECENT"
        if reason is not None:
            report.kept[reason] = report.kept.get(reason, 0) + 1
            continue
        why = "orphan (no sidecar) older than window" if not pages else (
            f"all {len(pages)} referencing observation(s) older than window and superseded")
        report.prune.append((name, path.stat().st_size, why))

    if apply:
        for digest, _size, _why in report.prune:
            target = base / digest
            if target.is_symlink() or target.resolve().parent != base:
                continue  # re-checked at deletion time
            target.unlink(missing_ok=True)
    return report
