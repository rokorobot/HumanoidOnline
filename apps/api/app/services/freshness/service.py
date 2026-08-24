"""Freshness service foundation — docs/22 Phases 5, 6, 9.

FOUNDATION SLICE: no HTTP client. `run_due_checks()` accepts a pluggable
`FreshnessChecker` — this slice ships none; a real, HTTP-backed one is a
later, separately-gated slice. Every function here is fully exercisable with
a fake/stub checker, which is exactly the point (docs/22 Phase 5: "This
allows complete testing without contacting third-party sites").

The governed change path — the ONLY place this module ever touches
`discovery_candidate` — is `create_or_reuse_recheck()`, called from exactly
two result branches (CHANGED, SOURCE_REMOVED; docs/22 Phase 6's deterministic
change-identity table defines a change_key for both). UNCHANGED and
FETCH_ERROR never call it, by construction (docs/22 Phase 5/6). Manual
CHANGE_FOUND and automated CHANGED both resolve through `record_observation`
-> `create_or_reuse_recheck` — literally the same function call, never a
parallel path (docs/22 Phase 9 / WorkOrder Phase 8).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.models.freshness import FreshnessObservation, FreshnessTarget
from app.models.robot import Robot
from app.services.discovery.pipeline import flag_recheck
from app.services.freshness import FreshnessError
from app.services.freshness.eligibility import compute_execution_mode, mode_reason

#: pipeline.flag_recheck() already refuses these (H5); checked here too so
#: create_or_reuse_recheck never even attempts the call on a terminal row —
#: the ratified invariant is "no new work AND no exception," not "no new
#: work via a caught exception."
_TERMINAL_CANDIDATE_STATUSES = {"PROMOTED", "REJECTED"}

_MANUAL_OUTCOME_TO_RESULT = {
    "CHECKED_UNCHANGED": "UNCHANGED",
    "CHANGE_FOUND": "CHANGED",
    "SOURCE_UNAVAILABLE": "FETCH_ERROR",
}


@dataclass
class CheckOutcome:
    """What a `FreshnessChecker` (or a manual report) produces for one
    target. No page body, ever (docs/22 Phase 2/4 minimal retention)."""

    result: str  # UNCHANGED | CHANGED | FETCH_ERROR | SOURCE_REMOVED
    etag: str | None = None
    last_modified: str | None = None
    content_fingerprint: str | None = None
    detected_change_type: str | None = None
    http_status: int | None = None
    error_detail: str | None = None


class FreshnessChecker(Protocol):
    """The seam this slice deliberately leaves unimplemented (no HTTP
    client). A real implementation performs the docs/22 Phase 7 bounded,
    conditional GET of `target.url` and returns a `CheckOutcome`."""

    def check(self, target: FreshnessTarget) -> CheckOutcome: ...


def _now() -> datetime:
    return datetime.now(UTC)


def is_due(target: FreshnessTarget, now: datetime) -> bool:
    """docs/22 Phase 6: due iff never checked, or the interval has elapsed."""
    if target.last_checked_at is None:
        return True
    return target.last_checked_at <= now - timedelta(days=target.interval_days)


def due_targets(session: Session, *, now: datetime | None = None) -> list[FreshnessTarget]:
    """Active targets whose interval has elapsed. Table size stays small by
    construction (docs/22 Phase 7: `max_targets_per_run` bounds a run; the
    live target count is bounded by however many are deliberately
    registered), so filtering the per-target interval in Python after one
    `active = true` query is simpler and just as correct as expressing
    per-row interval arithmetic in SQL."""
    now = now or _now()
    active = session.execute(
        select(FreshnessTarget).where(FreshnessTarget.active.is_(True))
    ).scalars().all()
    return [t for t in active if is_due(t, now)]


def due_manual_targets(
    session: Session, *, now: datetime | None = None
) -> list[tuple[FreshnessTarget, str, str]]:
    """Due targets whose current mode is NOT `AUTO_CHECK` — i.e. everything
    the weekly manual queue (docs/22 Phase 9 / WorkOrder Phase 8) must
    surface: robot + exact URL + why AUTO_CHECK is unavailable. Returns
    `(target, mode, reason)` triples."""
    now = now or _now()
    out: list[tuple[FreshnessTarget, str, str]] = []
    for target in due_targets(session, now=now):
        source = session.get(DiscoverySource, target.discovery_source_id)
        mode = compute_execution_mode(target, source, now)
        if mode == "AUTO_CHECK":
            continue
        out.append((target, mode, mode_reason(target, source, mode)))
    return out


def _change_key(*, result: str, content_fingerprint: str | None) -> str:
    """docs/22 Phase 6 — deterministic change identity. No random UUID, no
    timestamp, anywhere: either the content fingerprint itself, or one of two
    fixed literal strings."""
    if result == "SOURCE_REMOVED":
        return "SOURCE_REMOVED"
    if content_fingerprint:
        return content_fingerprint
    return "MANUAL_CHANGE"  # a CHANGED/CHANGE_FOUND report with no fingerprint supplied


def create_or_reuse_recheck(
    session: Session, target: FreshnessTarget, change_key: str, reason: str
) -> DiscoveryCandidate:
    """docs/22 Phase 6, corrected per the owner's ratified implementation
    invariant: NO generation suffix, ever. A retry/repeat observation of the
    SAME content (same `change_key`) always resolves to the SAME external_ref
    — if that candidate is terminal (PROMOTED/REJECTED), it is referenced for
    lineage only and NEVER touched again, regardless of whether it became
    terminal before or after this particular observation ran. A genuinely
    new, later distinct change (a different `change_key`) is never blocked by
    this — it lands on a different `external_ref` and creates a fresh
    candidate normally, independent of any other candidate's state.
    """
    ref = f"freshness/{target.id}/{change_key}"
    existing = session.execute(
        select(DiscoveryCandidate).where(
            DiscoveryCandidate.source_id == target.discovery_source_id,
            DiscoveryCandidate.external_ref == ref,
        )
    ).scalar_one_or_none()

    if existing is None:
        # candidate_name/candidate_manufacturer are populated from the robot
        # this recheck IS — not a shadow-data violation (DATA-D1.10 restricts
        # the free-form candidate_data JSONB, not these ordinary typed
        # columns) — so that identity.resolve_identity(), if a later human
        # calls pipeline.advance() through the standard governed CLI, derives
        # the SAME MATCHED_EXISTING verdict independently rather than relying
        # on a value set once here and never re-derived.
        robot = session.get(Robot, target.robot_id)
        candidate = DiscoveryCandidate(
            source_id=target.discovery_source_id,
            entity_type="ROBOT",
            external_ref=ref,
            candidate_name=robot.name if robot else None,
            candidate_manufacturer=robot.manufacturer.name if robot else None,
            identity_status="MATCHED_EXISTING",  # this recheck IS this exact robot, not a lead
            possible_robot_id=target.robot_id,
        )
        session.add(candidate)
        session.flush()
        flag_recheck(session, candidate, reason)
        return candidate

    if existing.status in _TERMINAL_CANDIDATE_STATUSES:
        # Ratified invariant: never resurrect, never open a new generation
        # solely because the matched candidate is terminal. Lineage still
        # points here (the caller sets discovery_candidate_id = existing.id)
        # so an auditor can see "this observation matches already-resolved
        # work" — but flag_recheck() is never called and nothing reopens.
        return existing

    flag_recheck(session, existing, reason)  # idempotent in effect
    return existing


def record_observation(
    session: Session,
    target: FreshnessTarget,
    *,
    trigger: str,
    mode: str,
    outcome: CheckOutcome,
) -> FreshnessObservation:
    """docs/22 Phase 5 — the one place every result branch converges. Always
    creates exactly one `FreshnessObservation` (the honest, append-only log);
    only CHANGED and SOURCE_REMOVED ever call `create_or_reuse_recheck`
    (docs/22 Phase 6's change-identity table defines a change_key for both;
    UNCHANGED and FETCH_ERROR never do, by construction).
    """
    if trigger not in ("MANUAL", "SCHEDULED_FRESHNESS"):
        raise FreshnessError(f"unknown trigger {trigger!r}")
    if outcome.result not in ("UNCHANGED", "CHANGED", "FETCH_ERROR", "SOURCE_REMOVED"):
        raise FreshnessError(f"unknown result {outcome.result!r}")

    obs = FreshnessObservation(
        freshness_target_id=target.id,
        trigger=trigger,
        execution_mode_at_check=mode,
        result=outcome.result,
        etag=outcome.etag,
        last_modified=outcome.last_modified,
        content_fingerprint=outcome.content_fingerprint,
        detected_change_type=outcome.detected_change_type,
        http_status=outcome.http_status,
        error_detail=(outcome.error_detail[:1000] if outcome.error_detail else None),
    )
    session.add(obs)
    session.flush()  # assign obs.id before it's referenced in a flag_recheck() reason

    now = _now()
    target.last_checked_at = now
    target.last_result = outcome.result

    if outcome.result == "UNCHANGED":
        # Bookkeeping only — never touches discovery_candidate (docs/22 Phase 5).
        if outcome.etag is not None:
            target.etag = outcome.etag
        if outcome.last_modified is not None:
            target.last_modified = outcome.last_modified
        if outcome.content_fingerprint is not None:
            target.content_fingerprint = outcome.content_fingerprint

    elif outcome.result == "CHANGED":
        if outcome.etag is not None:
            target.etag = outcome.etag
        if outcome.last_modified is not None:
            target.last_modified = outcome.last_modified
        target.content_fingerprint = outcome.content_fingerprint
        target.last_change_detected_at = now
        change_key = _change_key(result="CHANGED", content_fingerprint=outcome.content_fingerprint)
        reason = f"freshness observation {obs.id}: change detected at {target.url}"
        if obs.error_detail:  # an operator's --note, for a manual CHANGE_FOUND
            reason = f"{reason} — {obs.error_detail}"
        candidate = create_or_reuse_recheck(session, target, change_key, reason=reason)
        obs.discovery_candidate_id = candidate.id

    elif outcome.result == "FETCH_ERROR":
        # UNKNOWN semantics (docs/11 §5): an error is UNKNOWN-about-this-check,
        # never a negative fact. Validators are deliberately NOT updated —
        # carried forward so the next attempt can still use conditional-request
        # semantics — and no candidate is ever created from this branch.
        pass

    elif outcome.result == "SOURCE_REMOVED":
        # Workflow signal, following docs/22's exact change-identity semantics
        # (Phase 6 defines a dedicated "SOURCE_REMOVED" change_key precisely so
        # repeated weekly observations of a still-missing page converge onto
        # one governed work item instead of creating a fresh one every run).
        # Never auto-unpublishes, never mutates target.manual_override/active
        # (docs/22 Phase 5: those are durable config a human sets explicitly).
        change_key = _change_key(result="SOURCE_REMOVED", content_fingerprint=None)
        candidate = create_or_reuse_recheck(
            session, target, change_key,
            reason=f"freshness observation {obs.id}: source removed at {target.url}",
        )
        obs.discovery_candidate_id = candidate.id

    session.flush()
    return obs


def run_due_checks(
    session: Session,
    *,
    trigger: str,
    checker: FreshnessChecker,
    limit: int | None = None,
) -> list[FreshnessObservation]:
    """The shared entry point both a manual local run and a future scheduled
    run call (docs/22 Phase 8/9: "same application/service path"). Only
    `AUTO_CHECK` targets are ever checked — eligibility is evaluated here,
    freshly, immediately before any call to `checker.check()`, never trusted
    from a stored value (docs/22 Phase 3: "the eligibility check ... is the
    live condition under which the fetch code is invoked at all").

    One failing target does not abort the run (docs/22 Phase 7, test M/T):
    only `checker.check()` — the one call that can fail unpredictably — is
    wrapped, and any exception there becomes a FETCH_ERROR observation for
    that target rather than propagating. Every other target in the batch is
    processed normally.
    """
    if trigger not in ("MANUAL", "SCHEDULED_FRESHNESS"):
        raise FreshnessError(f"unknown trigger {trigger!r}")

    now = _now()
    targets = due_targets(session, now=now)
    if limit is not None:
        targets = targets[:limit]

    observations: list[FreshnessObservation] = []
    for target in targets:
        source = session.get(DiscoverySource, target.discovery_source_id)
        mode = compute_execution_mode(target, source, now)
        if mode != "AUTO_CHECK":
            continue  # not run; surfaced separately via due_manual_targets()

        try:
            outcome = checker.check(target)
        except Exception as exc:  # noqa: BLE001 - a checker failure is data, not our bug
            outcome = CheckOutcome(result="FETCH_ERROR", error_detail=str(exc)[:1000])

        observations.append(
            record_observation(session, target, trigger=trigger, mode=mode, outcome=outcome)
        )

    return observations


def record_manual_check(
    session: Session,
    target: FreshnessTarget,
    *,
    outcome: str,
    operator: str,
    note: str | None = None,
    content_fingerprint: str | None = None,
) -> FreshnessObservation:
    """docs/22 Phase 9 / WorkOrder Phase 8 — the human review path.
    `CHANGE_FOUND` resolves through the IDENTICAL `record_observation` ->
    `create_or_reuse_recheck` path automated `CHANGED` does; there is no
    parallel truth pipeline (mirrors `bootstrap.py`'s `--operator`
    discipline: an unattributed write is refused).
    """
    if not operator or not operator.strip():
        raise FreshnessError(
            "record_manual_check requires an attributed operator — an "
            "unattributed observation is not auditable (DATA-D1.9 discipline)"
        )
    if outcome not in _MANUAL_OUTCOME_TO_RESULT:
        raise FreshnessError(f"unknown manual outcome {outcome!r}")

    now = _now()
    source = session.get(DiscoverySource, target.discovery_source_id)
    mode = compute_execution_mode(target, source, now)

    check_outcome = CheckOutcome(
        result=_MANUAL_OUTCOME_TO_RESULT[outcome],
        content_fingerprint=content_fingerprint,
        # An operator's --note is carried in error_detail regardless of
        # outcome (FreshnessObservation has no separate free-text column —
        # docs/22 Phase 2). For CHANGE_FOUND, record_observation folds it
        # into the flag_recheck() reason too, so the discovery-layer review
        # sees it without a second lookup.
        error_detail=note,
    )
    return record_observation(session, target, trigger="MANUAL", mode=mode, outcome=check_outcome)
