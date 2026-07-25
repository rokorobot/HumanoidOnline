"""Candidate state machine, tracing + verification (DATA-D1 §6/§9/§25-D/E).

Runs a candidate autonomously through IDENTITY_REVIEW -> SOURCE_TRACE ->
VERIFICATION -> READY_FOR_PROMOTION (or a blocking side state). It NEVER reaches
PROMOTED — that is the human gate in `promotion.promote` (§8/§18/Gate H). Reads
canonical only; writes only the discovery layer.

Trace vs lead (H2): a discovered `official_url` is a LEAD, not proof. `advance`
never confirms a trace from a lead. A trace becomes TRACE_CONFIRMED only via an
EXPLICIT `record_trace(...)` that records the authoritative source, its type, and
who verified it — the offline stand-in for real OEM tracing (which, when built,
sits behind the crawler-etiquette layer + the DATA-D1.9 review).

State machine is terminal-safe (H5): PROMOTED / REJECTED do not re-advance.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.discovery import DiscoveryCandidate
from app.services.discovery import DiscoveryError
from app.services.discovery.identity import resolve_identity

_PROMOTABLE_IDENTITY = {"MATCHED_EXISTING", "NEW_ENTITY"}
_TERMINAL = {"PROMOTED", "REJECTED"}


def advance(session: Session, candidate: DiscoveryCandidate) -> DiscoveryCandidate:
    """Advance a candidate as far as the evidence allows, deterministically.

    Refuses terminal candidates (H5): a PROMOTED/REJECTED candidate is not
    re-advanced (that would need a separately governed reopen).
    """
    if candidate.status in _TERMINAL:
        raise DiscoveryError(
            f"candidate is terminal ({candidate.status}); cannot re-advance"
        )

    # 1) IDENTITY_REVIEW
    candidate.status = "IDENTITY_REVIEW"
    identity = resolve_identity(session, candidate)
    if identity == "POSSIBLE_DUPLICATE":
        candidate.status = "POSSIBLE_DUPLICATE"
        return candidate
    if identity not in _PROMOTABLE_IDENTITY:
        candidate.status = "IDENTITY_REVIEW"  # AMBIGUOUS / UNRESOLVED: block (D1.6)
        return candidate

    # 2) SOURCE_TRACE — only an EXPLICIT confirmed trace advances (H2).
    candidate.status = "SOURCE_TRACE"
    if candidate.trace_state == "TRACE_FAILED":
        candidate.status = "INSUFFICIENT_EVIDENCE"
        return candidate
    if candidate.trace_state != "TRACE_CONFIRMED" or not candidate.trace_verified_by:
        return candidate  # awaiting record_trace(); a lead is not proof

    # 3) VERIFICATION
    candidate.status = "VERIFICATION"
    if _mark_conflicts(candidate):
        candidate.status = "CONFLICT"
        return candidate
    _finalize_claim_statuses(candidate)

    # 4) READY_FOR_PROMOTION (proposal may be built; promotion is human-gated)
    candidate.status = "READY_FOR_PROMOTION"
    return candidate


def record_trace(
    session: Session,
    candidate: DiscoveryCandidate,
    *,
    trace_url: str,
    trace_source_type: str,
    verified_by: str,
    confirmed_fields: frozenset[str] = frozenset(),
    state: str = "TRACE_CONFIRMED",
) -> None:
    """Explicitly record the outcome of tracing a candidate to an authoritative
    source (H2). This is the governed stand-in for real OEM tracing; a bare
    `official_url` lead never reaches this on its own. `confirmed_fields` marks
    which claims that source actually supports (they become VERIFIED)."""
    if candidate.status in _TERMINAL:
        raise DiscoveryError(f"candidate is terminal ({candidate.status}); cannot trace")
    if not verified_by or not verified_by.strip():
        raise DiscoveryError("record_trace requires an attributed verifier")
    if state == "TRACE_CONFIRMED" and not trace_url:
        raise DiscoveryError("a confirmed trace requires an authoritative trace_url")

    candidate.trace_state = state
    candidate.trace_url = trace_url or None
    candidate.trace_source_type = trace_source_type if state == "TRACE_CONFIRMED" else None
    candidate.trace_verified_by = verified_by
    candidate.trace_verified_at = datetime.now(UTC)

    if state == "TRACE_CONFIRMED":
        for claim in candidate.claims:
            if claim.claimed_value is not None and claim.field_key in confirmed_fields:
                claim.claim_status = "VERIFIED"
                claim.evidence_url = claim.evidence_url or trace_url


def flag_recheck(session: Session, candidate: DiscoveryCandidate, reason: str) -> None:
    """Autonomously mark a candidate for re-verification (§12). RECHECK_REQUIRED is
    workflow metadata, not a canonical fact change — no human gate, no canonical
    mutation. Terminal candidates are not re-opened here (H5): re-checking a
    promoted robot is a NEW discovery event, not a status flip on the old one."""
    if candidate.status in _TERMINAL:
        raise DiscoveryError(
            f"candidate is terminal ({candidate.status}); recheck is a new discovery event"
        )
    candidate.status = "RECHECK_REQUIRED"
    candidate.candidate_data = {**(candidate.candidate_data or {}), "recheck_reason": reason}


def _mark_conflicts(candidate: DiscoveryCandidate) -> bool:
    """A field with two or more DIFFERENT non-null claimed values is a conflict —
    preserved, never averaged (DATA-D1.8). Marks the offending claims CONFLICT,
    overriding any tentative VERIFIED."""
    by_field: dict[str, set[str]] = {}
    for claim in candidate.claims:
        if claim.claimed_value is not None:
            by_field.setdefault(claim.field_key, set()).add(claim.claimed_value)
    conflicted = {f for f, vals in by_field.items() if len(vals) > 1}
    if not conflicted:
        return False
    for claim in candidate.claims:
        if claim.field_key in conflicted:
            claim.claim_status = "CONFLICT"
    return True


def _finalize_claim_statuses(candidate: DiscoveryCandidate) -> None:
    """A missing value stays UNKNOWN (never 0/false, DATA-D1.5). VERIFIED (set by a
    confirmed trace) stays; everything else remains NOT_VERIFIED — entity existence
    is what the confirmed trace establishes; specs stay UNKNOWN unless individually
    confirmed (verified existence != complete specs, §11)."""
    for claim in candidate.claims:
        if claim.claimed_value is None:
            claim.claim_status = "UNKNOWN"
