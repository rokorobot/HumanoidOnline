"""Candidate state machine + verification (DATA-D1 §6/§9/§25-D/E).

Runs a candidate autonomously through IDENTITY_REVIEW -> SOURCE_TRACE ->
VERIFICATION -> READY_FOR_PROMOTION (or a blocking side state). It NEVER reaches
PROMOTED — that transition is the human gate in `promotion.promote` (§8/§18/Gate H).
Reads canonical only; writes only the discovery layer.

v0.1 tracing is deterministic and offline: a source may expose an `official_url`
LEAD in candidate_data; treating that lead as a confirmed authoritative source is a
stand-in for real OEM tracing (which, when built, sits behind the crawler-etiquette
layer and the DATA-D1.9 review). No `official_url` -> TRACE_FAILED (a legitimate
research outcome, §9 — never fabricated).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.discovery import DiscoveryCandidate
from app.services.discovery.identity import resolve_identity

_PROMOTABLE_IDENTITY = {"MATCHED_EXISTING", "NEW_ENTITY"}


def advance(session: Session, candidate: DiscoveryCandidate) -> DiscoveryCandidate:
    """Advance a candidate as far as the evidence allows, deterministically."""
    # 1) IDENTITY_REVIEW
    candidate.status = "IDENTITY_REVIEW"
    identity = resolve_identity(session, candidate)
    if identity == "POSSIBLE_DUPLICATE":
        candidate.status = "POSSIBLE_DUPLICATE"
        return candidate
    if identity not in _PROMOTABLE_IDENTITY:
        # AMBIGUOUS / UNRESOLVED: identity must resolve before facts attach (D1.6).
        candidate.status = "IDENTITY_REVIEW"
        return candidate

    # 2) SOURCE_TRACE
    candidate.status = "SOURCE_TRACE"
    _trace(candidate)
    if candidate.trace_state == "TRACE_FAILED":
        candidate.status = "INSUFFICIENT_EVIDENCE"
        return candidate

    # 3) VERIFICATION
    candidate.status = "VERIFICATION"
    if _has_conflict(candidate):
        candidate.status = "CONFLICT"
        return candidate
    _verify_claims(candidate)

    # 4) READY_FOR_PROMOTION (a proposal may now be built; promotion is human-gated)
    candidate.status = "READY_FOR_PROMOTION"
    return candidate


def flag_recheck(session: Session, candidate: DiscoveryCandidate, reason: str) -> None:
    """Autonomously mark a candidate/record for re-verification (§12).

    RECHECK_REQUIRED is workflow metadata, NOT a canonical fact change, so it needs
    no human gate — and it never mutates a canonical value (a stale source initiates
    verification, it does not erase the existing canonical truth).
    """
    candidate.status = "RECHECK_REQUIRED"
    # Reason retained as workflow metadata on the candidate (not a canonical fact).
    candidate.candidate_data = {**(candidate.candidate_data or {}), "recheck_reason": reason}


def _trace(candidate: DiscoveryCandidate) -> None:
    official = (candidate.candidate_data or {}).get("official_url")
    if official:
        candidate.trace_state = "TRACE_CONFIRMED"
        candidate.trace_url = official
    else:
        candidate.trace_state = "TRACE_FAILED"
        candidate.trace_url = None


def _has_conflict(candidate: DiscoveryCandidate) -> bool:
    """A field with two or more DIFFERENT non-null claimed values is a conflict —
    preserved, never averaged (DATA-D1.8). Marks the offending claims CONFLICT."""
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


def _verify_claims(candidate: DiscoveryCandidate) -> None:
    """Per-claim verification. A claim is VERIFIED only if it carries its own
    authoritative evidence_url; a missing value stays UNKNOWN (never 0/false,
    DATA-D1.5); anything else remains NOT_VERIFIED. Entity EXISTENCE is what the
    confirmed trace establishes; specs stay UNKNOWN unless individually evidenced
    (verified existence != complete specs, §11)."""
    for claim in candidate.claims:
        if claim.claimed_value is None:
            claim.claim_status = "UNKNOWN"
        elif claim.evidence_url:
            claim.claim_status = "VERIFIED"
        else:
            claim.claim_status = "NOT_VERIFIED"
