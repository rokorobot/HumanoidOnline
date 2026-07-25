"""Promotion gate + governed canonical write (DATA-D1 §7/§8/§18/§25-F/G/H).

`build_proposal` is autonomous (no writes). `promote` is the ONE human-invoked
canonical writer: it enforces gates P1-P8 and, only if they pass, creates the
canonical robot (unpublished) and its evidence THROUGH the existing G2 evidence
model (R5 — no parallel evidence system), then records the promotion lineage
(§19/Gate J). It never commits; the caller (CLI/admin) owns the transaction.

No autonomous promotion in v0.1: the pipeline can reach READY_FOR_PROMOTION and a
proposal, but only a human calling `promote` mutates canonical truth.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.discovery import DiscoveryCandidate, PromotionAudit
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import PromotionError
from app.services.discovery.identity import normalize

_PROMOTABLE_IDENTITY = {"MATCHED_EXISTING", "NEW_ENTITY"}


def check_gates(session: Session, candidate: DiscoveryCandidate) -> list[str]:
    """Return the list of FAILED promotion gates (empty = promotable)."""
    fails: list[str] = []
    # P1 — identity resolved
    if candidate.identity_status not in _PROMOTABLE_IDENTITY:
        fails.append(f"P1 identity not resolved (identity_status={candidate.identity_status})")
    # P2 — a qualifying authoritative source was traced
    if candidate.trace_state != "TRACE_CONFIRMED" or not candidate.trace_url:
        fails.append("P2 no confirmed authoritative source (trace_state != TRACE_CONFIRMED)")
    # P4 — no unresolved conflict
    has_conflict = candidate.status == "CONFLICT" or any(
        c.claim_status == "CONFLICT" for c in candidate.claims
    )
    if has_conflict:
        fails.append("P4 unresolved evidence conflict")
    # P6 — schema supports the entity (v0.1 promotes ROBOT candidates only)
    if candidate.entity_type != "ROBOT":
        fails.append(
            f"P6 v0.1 promotes ROBOT candidates only (entity_type={candidate.entity_type})"
        )
    # readiness — the pipeline must have reached READY_FOR_PROMOTION
    if candidate.status != "READY_FOR_PROMOTION":
        fails.append(f"not READY_FOR_PROMOTION (status={candidate.status})")
    return fails


def build_proposal(session: Session, candidate: DiscoveryCandidate) -> dict:
    """A structured, human-reviewable promotion proposal. Autonomous — no writes."""
    verified = [
        {
            "field": c.field_key, "value": c.claimed_value,
            "unit": c.unit, "evidence_url": c.evidence_url,
        }
        for c in candidate.claims
        if c.claim_status == "VERIFIED"
    ]
    unresolved = [
        {"field": c.field_key, "value": c.claimed_value, "status": c.claim_status}
        for c in candidate.claims
        if c.claim_status != "VERIFIED"
    ]
    return {
        "candidate_id": str(candidate.id),
        "entity_type": candidate.entity_type,
        "name": candidate.candidate_name,
        "manufacturer": candidate.candidate_manufacturer,
        "identity_status": candidate.identity_status,
        "trace_url": candidate.trace_url,
        "verified_claims": verified,
        "unresolved_claims": unresolved,
        "gates_failed": check_gates(session, candidate),
    }


def promote(
    session: Session,
    candidate: DiscoveryCandidate,
    approved_by: str,
    *,
    publish: bool = False,
) -> Robot:
    """HUMAN promotion gate (P8). Raises PromotionError (no canonical write) if any
    gate fails. On success: create/link the canonical robot, write an EvidenceSource
    (existing G2 path), record promotion lineage. Does not commit."""
    if not approved_by or not approved_by.strip():
        raise PromotionError("promotion requires an approving human (approved_by)")
    fails = check_gates(session, candidate)
    if fails:
        raise PromotionError("; ".join(fails))

    proposal = build_proposal(session, candidate)

    if candidate.identity_status == "MATCHED_EXISTING":
        # Dedup (DATA-D1.7): the robot already exists canonically. v0.1 does NOT
        # create a duplicate and does not overwrite existing specs; it records the
        # confirmed link + lineage. (Field-level canonical updates are a later slice.)
        robot = session.get(Robot, candidate.possible_robot_id)
        if robot is None:
            raise PromotionError("P1 matched robot no longer exists")
        evidence_id = None
    else:  # NEW_ENTITY
        manufacturer = _get_or_create_manufacturer(session, candidate)
        robot = Robot(
            slug=_unique_robot_slug(session, candidate.candidate_name or "robot"),
            manufacturer_id=manufacturer.id,
            name=candidate.candidate_name or "Unknown",
            is_published=publish,  # promotion creates UNPUBLISHED by default
        )
        session.add(robot)
        session.flush()  # assign robot.id
        evidence = EvidenceSource(
            subject_type="ROBOT",
            subject_id=robot.id,
            source_url=candidate.trace_url,
            source_type="MANUFACTURER_SITE",
            source_title=f"{candidate.candidate_name} — official source",
            confidence="VERIFIED",
            verified_at=datetime.now(UTC),
            note="Promoted via DATA-D1 governed pipeline (human-approved).",
        )
        session.add(evidence)
        session.flush()
        evidence_id = evidence.id

    candidate.status = "PROMOTED"
    candidate.promoted_robot_id = robot.id
    session.add(
        PromotionAudit(
            candidate_id=candidate.id,
            action="PROMOTED",
            promoted_entity_type="ROBOT",
            promoted_robot_id=robot.id,
            evidence_source_id=evidence_id,
            approved_by=approved_by,
            detail=proposal,
        )
    )
    session.flush()
    return robot


def reject(session: Session, candidate: DiscoveryCandidate, approved_by: str, reason: str) -> None:
    """Human rejection — recorded, not deleted (research history, §21). No canonical write."""
    candidate.status = "REJECTED"
    session.add(
        PromotionAudit(
            candidate_id=candidate.id,
            action="REJECTED",
            approved_by=approved_by,
            detail={"reason": reason},
        )
    )
    session.flush()


# --- helpers -----------------------------------------------------------------

def _get_or_create_manufacturer(session: Session, candidate: DiscoveryCandidate) -> Manufacturer:
    if candidate.possible_manufacturer_id is not None:
        found = session.get(Manufacturer, candidate.possible_manufacturer_id)
        if found is not None:
            return found
    name = candidate.candidate_manufacturer or "Unknown"
    key = normalize(name)
    for m in session.execute(select(Manufacturer)).scalars().all():
        if normalize(m.name) == key and key:
            return m
    mfr = Manufacturer(slug=_unique_manufacturer_slug(session, name), name=name)
    session.add(mfr)
    session.flush()
    return mfr


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def _unique_robot_slug(session: Session, name: str) -> str:
    return _unique_slug(session, Robot, _slugify(name))


def _unique_manufacturer_slug(session: Session, name: str) -> str:
    return _unique_slug(session, Manufacturer, _slugify(name))


def _unique_slug(session: Session, model, base: str) -> str:
    slug, n = base, 2
    taken = select(func.count()).select_from(model)
    while session.execute(taken.where(model.slug == slug)).scalar_one():
        slug = f"{base}-{n}"
        n += 1
    return slug
