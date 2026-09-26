"""Stage E — human candidate<->candidate identity decisions (docs/16 §17.1).

The primitives shared by the resolver and the review workflow. A decision is a
row in the append-only `candidate_identity_decision` table: the pair is stored in
canonical order, and the newest row (highest `decision_seq`) for a pair is the
effective decision. Nothing here merges, deletes or rewrites a candidate.
"""
from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.discovery import CandidateIdentityDecision, DiscoveryCandidate
from app.services.discovery import DiscoveryError

SAME_ENTITY = "SAME_ENTITY"
NOT_SAME_ENTITY = "NOT_SAME_ENTITY"
DECISIONS = (SAME_ENTITY, NOT_SAME_ENTITY)


def canonical_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """(smaller, larger), matching the table's ordering CHECK (UUID byte order)."""
    if a == b:
        raise DiscoveryError("a candidate cannot be paired with itself")
    return (a, b) if str(a) < str(b) else (b, a)


def effective_decisions(session: Session, candidate_id: uuid.UUID | None) -> dict[uuid.UUID, str]:
    """Counterpart id -> the effective (newest) decision involving `candidate_id`."""
    if candidate_id is None:
        return {}
    rows = session.scalars(
        select(CandidateIdentityDecision)
        .where(or_(CandidateIdentityDecision.candidate_a_id == candidate_id,
                   CandidateIdentityDecision.candidate_b_id == candidate_id))
        .order_by(CandidateIdentityDecision.decision_seq)
    ).all()
    effective: dict[uuid.UUID, str] = {}
    for row in rows:
        other = row.candidate_b_id if row.candidate_a_id == candidate_id else row.candidate_a_id
        effective[other] = row.decision
    return effective


def pair_history(session: Session, a: uuid.UUID, b: uuid.UUID) -> list[CandidateIdentityDecision]:
    first, second = canonical_pair(a, b)
    return list(session.scalars(
        select(CandidateIdentityDecision)
        .where(CandidateIdentityDecision.candidate_a_id == first,
               CandidateIdentityDecision.candidate_b_id == second)
        .order_by(CandidateIdentityDecision.decision_seq)
    ).all())


def record_identity_decision(
    session: Session, a: uuid.UUID, b: uuid.UUID, decision: str, *, decided_by: str,
    reason: str,
) -> tuple[CandidateIdentityDecision, bool]:
    """Append a decision for the pair. Returns (effective row, created?).

    If the pair's effective decision is already `decision`, nothing is written
    (repeating a command never creates duplicate history). A different decision
    appends a new row, which becomes effective; earlier rows are kept.
    """
    if decision not in DECISIONS:
        raise DiscoveryError(f"decision must be one of {DECISIONS}")
    if not (decided_by or "").strip():
        raise DiscoveryError("--by is required (an unattributed decision is not a decision)")
    if not (reason or "").strip():
        raise DiscoveryError("--reason is required")
    first, second = canonical_pair(a, b)
    for cid in (first, second):
        if session.get(DiscoveryCandidate, cid) is None:
            raise DiscoveryError(f"no discovery candidate {cid}")
    history = pair_history(session, first, second)
    if history and history[-1].decision == decision:
        return history[-1], False
    row = CandidateIdentityDecision(
        candidate_a_id=first, candidate_b_id=second, decision=decision,
        decided_by=decided_by.strip(), reason=reason.strip(),
    )
    session.add(row)
    session.flush()
    return row, True
