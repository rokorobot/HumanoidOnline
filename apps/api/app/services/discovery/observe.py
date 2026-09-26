"""Stage F1 — one observation cycle across every due, enabled source (docs/16 §17.2).

    enabled + scheduled sources -> due? -> the source's reviewed adapter
    (existing run_adapter / resume_adapter: robots, policy, bounded fetch,
    conditional GET, extraction, identity resolution) -> Stage E queue counts

This module decides only WHICH source runs and HOW it ended. Everything that
touches the network or writes a row is the existing, already-governed code:
policy and robots gates run inside every run exactly as for a manual run, and
nothing here can widen what an adapter fetches. It never records a Stage E
decision, never confirms an alias, never traces and never promotes.

Per source, in a deterministic order (by key):

- DISABLED / NOT_SCHEDULED: skipped. A source is observed only when it is enabled
  AND an attributed human set a cadence (`source cadence`).
- NO_ADAPTER / INELIGIBLE: skipped, and reported for a human.
- a RUNNING run: skipped (another process owns it); if it looks stale, reported.
- latest run HALTED_BY_POLICY (401/403/429, robots unavailable): NOT retried.
  A block is a finding (LIVE.3); a human clears it with a manual run.
- latest run FAILED/CANCELLED: resumed once (the existing governed resume). If
  that automated resume also failed, it is not retried again: reported.
- NOT_DUE: skipped until the last run's end plus the cadence.
- otherwise: one SCHEDULED adapter run.

One source failing never stops the others. The cycle result is machine-readable
(`CycleResult.as_dict`) with an exit code for the scheduler.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.acquisition import CrawlRun, ExtractionResult, FetchedPage
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.services.discovery import cache as body_cache
from app.services.discovery.acquisition import (
    STALE_RUN_AFTER,
    AcquisitionRefused,
    _utcnow,
)
from app.services.discovery.adapter_run import adapter_problems, resume_adapter, run_adapter
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.live_adapter import SourceAdapterConfig
from app.services.discovery.review import review_queue
from app.services.discovery.source_registry import next_observation_at

# Outcomes that ran something.
COMPLETED, RESUMED, HALTED, FAILED, CANCELLED = (
    "COMPLETED", "RESUMED", "HALTED", "FAILED", "CANCELLED")
# Outcomes that ran nothing.
DISABLED, NOT_SCHEDULED, NOT_DUE, NO_ADAPTER, INELIGIBLE = (
    "DISABLED", "NOT_SCHEDULED", "NOT_DUE", "NO_ADAPTER", "INELIGIBLE")
RUN_IN_PROGRESS, NEEDS_HUMAN, KILL_SWITCH, REFUSED = (
    "RUN_IN_PROGRESS", "NEEDS_HUMAN", "KILL_SWITCH", "REFUSED")
# Plan mode (no network, no writes): what a cycle would do now.
WOULD_RUN, WOULD_RESUME = "WOULD_RUN", "WOULD_RESUME"

#: A human must look at the source (the scheduler will not fix it by retrying).
ATTENTION = frozenset({HALTED, FAILED, CANCELLED, NO_ADAPTER, INELIGIBLE, NEEDS_HUMAN,
                       REFUSED})

EXIT_OK, EXIT_FAILED, EXIT_ATTENTION = 0, 1, 4

_RUN_STATUS = {"COMPLETED": COMPLETED, "HALTED_BY_POLICY": HALTED, "FAILED": FAILED,
               "CANCELLED": CANCELLED}


@dataclass
class SourceObservation:
    key: str
    status: str
    detail: str = ""
    run_id: uuid.UUID | None = None
    counts: dict = field(default_factory=dict)

    @property
    def attention(self) -> bool:
        return self.status in ATTENTION or bool(self.counts.get("review_items_this_cycle"))

    def line(self) -> str:
        return f"{self.key:<28} {self.status:<16} {self.detail}".rstrip()

    def as_dict(self) -> dict:
        return {"source": self.key, "status": self.status, "detail": self.detail,
                "run_id": str(self.run_id) if self.run_id else None,
                "attention": self.attention, "counts": self.counts}


@dataclass
class CycleResult:
    started_at: datetime
    plan_only: bool
    sources: list[SourceObservation] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if any(s.status == FAILED for s in self.sources):
            return EXIT_FAILED
        return EXIT_ATTENTION if any(s.attention for s in self.sources) else EXIT_OK

    def lines(self) -> list[str]:
        mode = "PLAN (no request, no write)" if self.plan_only else "OBSERVATION CYCLE"
        head = f"{mode} started={self.started_at.isoformat()}  sources={len(self.sources)}"
        return [head, *(s.line() for s in self.sources),
                f"attention={'yes' if any(s.attention for s in self.sources) else 'no'}  "
                f"exit={self.exit_code}  canonical_rows_written=0"]

    def as_dict(self) -> dict:
        return {"started_at": self.started_at.isoformat(), "plan_only": self.plan_only,
                "exit_code": self.exit_code, "canonical_rows_written": 0,
                "sources": [s.as_dict() for s in self.sources]}


def scheduled_operator(source: DiscoverySource) -> str:
    """crawl_run.operator for a scheduled run: who authorized the cadence."""
    return f"stage-f scheduler (cadence set by {source.observation_cadence_set_by})"


def _latest_run(session: Session, source: DiscoverySource) -> CrawlRun | None:
    return session.scalars(
        select(CrawlRun).where(CrawlRun.source_id == source.id)
        .order_by(CrawlRun.started_at.desc(), CrawlRun.created_at.desc()).limit(1)
    ).first()


def _last_activity(session: Session, run: CrawlRun) -> datetime:
    return session.scalar(select(func.max(FetchedPage.retrieved_at))
                          .where(FetchedPage.crawl_run_id == run.id)) or run.started_at


def assess(session: Session, source: DiscoverySource, config: SourceAdapterConfig | None,
           now: datetime, kill_engaged: bool) -> tuple[str, str, CrawlRun | None]:
    """(status, detail, run to resume) for one source. Reads only; pure policy.

    Status is a skip outcome, WOULD_RUN or WOULD_RESUME."""
    if not source.is_enabled:
        return DISABLED, "", None
    if source.observation_interval_hours is None:
        return NOT_SCHEDULED, "no cadence set (source cadence <key> --every ...)", None
    if config is None:
        return NO_ADAPTER, "enabled and scheduled, but no reviewed adapter module", None
    problems = adapter_problems(config, source)
    if problems:
        return INELIGIBLE, "; ".join(problems), None
    if kill_engaged:
        return KILL_SWITCH, "kill switch present; nothing requested", None
    latest = _latest_run(session, source)
    if latest is not None and latest.status == "RUNNING":
        if now - _last_activity(session, latest) >= STALE_RUN_AFTER:
            return NEEDS_HUMAN, (f"run {latest.id} is RUNNING but idle; mark it failed "
                                 "(discovery run fail) to let it resume"), None
        return RUN_IN_PROGRESS, f"run {latest.id} is in progress", None
    if latest is not None and latest.status == "HALTED_BY_POLICY":
        reason = (latest.counters or {}).get("halt_reason") or "policy halt"
        return NEEDS_HUMAN, (f"run {latest.id} halted ({reason}); not retried automatically. "
                             "A manual adapter run clears this"), None
    if latest is not None and latest.status in ("FAILED", "CANCELLED"):
        if latest.trigger == "SCHEDULED" and latest.resume_of_run_id is not None:
            return NEEDS_HUMAN, (f"automated resume {latest.id} also ended {latest.status}; "
                                 "not retried again"), None
        return WOULD_RESUME, f"resume {latest.status} run {latest.id}", latest
    due = next_observation_at(source)
    if due is not None and due > now:
        return NOT_DUE, f"next due {due.isoformat()}", None
    return WOULD_RUN, "", None


def fetch_limits_for(config: SourceAdapterConfig, parent: CrawlRun | None) -> FetchLimits:
    """The limits `adapter run` uses; a resume honours the parent's manifest."""
    parent_limits = (parent.run_manifest or {}).get("limits") if parent is not None else None
    if parent_limits:
        return FetchLimits(**parent_limits)
    return FetchLimits(page_cap=min(200, len(config.seed_urls) + config.target_cap))


def _default_fetcher(source: DiscoverySource, config: SourceAdapterConfig,
                     parent: CrawlRun | None, kill_switch: Callable[[], bool]) -> HttpFetcher:
    return HttpFetcher(limits=fetch_limits_for(config, parent), kill_switch=kill_switch)


def _counts(session: Session, run: CrawlRun, source: DiscoverySource) -> dict:
    acq = run.counters or {}
    ext = acq.get("extraction") or {}
    touched = set(session.scalars(
        select(ExtractionResult.candidate_id).where(
            ExtractionResult.crawl_run_id == run.id,
            ExtractionResult.candidate_id.is_not(None))))
    source_candidates = set(session.scalars(
        select(DiscoveryCandidate.id).where(DiscoveryCandidate.source_id == source.id)))
    queue = review_queue(session)
    open_items = [i for i in queue if source_candidates.intersection(i.candidate_ids)]
    cycle_items = [i for i in open_items if touched.intersection(i.candidate_ids)]
    return {
        "first_observation": acq.get("first_observation", 0),
        "changed": acq.get("changed", 0),
        "unchanged": acq.get("unchanged", 0),
        "errors": acq.get("fetch_error", 0) + ext.get("extraction_errors", 0),
        "source_removed": acq.get("source_removed", 0),
        "learned_canonical_requests": len(acq.get("learned_canonical_requests", [])),
        "new_product_urls": ext.get("new_product_urls", 0),
        "new_entity": ext.get("new_entity", 0),
        "possible_duplicate": ext.get("possible_duplicate", 0),
        "ambiguous": ext.get("ambiguous", 0),
        "review_items_this_cycle": len(cycle_items),
        "review_items_open": len(open_items),
        "review_kinds_this_cycle": sorted({i.kind for i in cycle_items}),
    }


def _summary(counts: dict) -> str:
    return (f"{counts['changed']} changed / {counts['unchanged']} unchanged / "
            f"{counts['first_observation']} new / {counts['errors']} errors / "
            f"{counts['review_items_this_cycle']} review exception(s) this cycle "
            f"({counts['review_items_open']} open)")


def observe(
    session: Session,
    adapters: dict[str, SourceAdapterConfig],
    *,
    plan_only: bool = False,
    cache_dir: Path = body_cache.DEFAULT_CACHE_DIR,
    now: Callable[[], datetime] = _utcnow,
    kill_switch_for: Callable[[str], Callable[[], bool]] = lambda key: (lambda: False),
    fetcher_for: Callable[..., HttpFetcher] = _default_fetcher,
    checkpoint: Callable[[], None] | None = None,
    only: str | None = None,
) -> CycleResult:
    """One observation cycle. With `plan_only`, nothing is requested or written.

    `checkpoint` (e.g. session.commit) makes every run durable as it goes, and is
    what lets one failing source leave the others' work intact."""
    commit = checkpoint or session.flush
    result = CycleResult(started_at=now().astimezone(UTC), plan_only=plan_only)
    query = select(DiscoverySource).order_by(DiscoverySource.key)
    if only is not None:
        query = query.where(DiscoverySource.key == only)
    for source in session.scalars(query).all():
        key = source.key
        config = adapters.get(key)
        kill = kill_switch_for(key)
        status, detail, parent = assess(session, source, config, now(), kill())
        if plan_only or status not in (WOULD_RUN, WOULD_RESUME):
            result.sources.append(SourceObservation(key, status, detail))
            continue
        result.sources.append(_run_one(session, source, config, parent, cache_dir, now,
                                       kill, fetcher_for, commit))
    return result


def _run_one(session, source, config, parent, cache_dir, now, kill, fetcher_for,
             commit) -> SourceObservation:
    key, source_id = source.key, source.id
    operator = scheduled_operator(source)
    try:
        with fetcher_for(source, config, parent, kill) as fetcher:
            if parent is not None:
                run = resume_adapter(
                    session, parent_run_id=parent.id, source=source, config=config,
                    operator=operator, fetcher=fetcher, cache_dir=cache_dir, now=now,
                    checkpoint=commit, trigger="SCHEDULED")
            else:
                run = run_adapter(
                    session, source=source, config=config, operator=operator,
                    fetcher=fetcher, cache_dir=cache_dir, now=now, checkpoint=commit,
                    trigger="SCHEDULED")
    except AcquisitionRefused as exc:  # includes adapter and resume refusals
        session.rollback()
        status = NEEDS_HUMAN if parent is not None else REFUSED
        return SourceObservation(key, status, f"refused before any request: {exc}")
    except Exception as exc:  # noqa: BLE001 — one source must not stop the cycle
        # The run machinery has already durably marked its run FAILED.
        session.rollback()
        failed = session.scalars(
            select(CrawlRun.id).where(CrawlRun.source_id == source_id)
            .order_by(CrawlRun.started_at.desc()).limit(1)).first()
        return SourceObservation(key, FAILED, f"{type(exc).__name__} (run {failed})",
                                 run_id=failed)
    status = _RUN_STATUS.get(run.status, FAILED)
    if status == COMPLETED and parent is not None:
        status = RESUMED
    counts = _counts(session, run, source)
    detail = _summary(counts)
    if status in (HALTED, CANCELLED):
        detail = f"{(run.counters or {}).get('halt_reason') or run.status}; {detail}"
    return SourceObservation(key, status, detail, run_id=run.id, counts=counts)
