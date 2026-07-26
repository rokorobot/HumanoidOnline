"""Promotion gate + governed canonical write (DATA-D1 §7/§8/§18/§25-F/G/H).

`build_proposal` is autonomous (no writes). `promote` is the ONE human-invoked
canonical writer: it enforces the promotion gates IMPLEMENTED HERE and, only if
they pass, creates/links the
canonical robot, writes VERIFIED claims into a small approved set of typed fields,
records provenance THROUGH the existing G2 evidence model (R5 — no parallel evidence
system), and records the promotion lineage (§19/Gate J). It never commits; the
caller (CLI/admin) owns the transaction.

Truthful scope (H4): only claims a confirmed trace VERIFIED are written to canonical
fields, and only into the approved set below; UNKNOWN/NOT_VERIFIED/CONFLICT claims
are never written (Gate F), and an existing non-null canonical value is never
overwritten (that path is a conflict for a later slice). Promotion is idempotent
(H5): an already-promoted candidate is refused.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.discovery import DiscoveryCandidate, PromotionAudit
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import PromotionError
from app.services.discovery.identity import normalize

_PROMOTABLE_IDENTITY = {"MATCHED_EXISTING", "NEW_ENTITY"}

# The narrow, typed set of canonical fields a VERIFIED claim may write in v0.1.
# (field_key) -> (robot attribute, expected unit or None, minimum-allowed value).
_APPROVED_FIELDS: dict[str, tuple[str, str | None, Decimal]] = {
    "height_cm": ("height_cm", "cm", Decimal("0.1")),
    "weight_kg": ("weight_kg", "kg", Decimal("0.1")),
    "payload_kg": ("payload_kg", "kg", Decimal("0")),
}


def check_gates(session: Session, candidate: DiscoveryCandidate) -> list[str]:
    """Return the list of FAILED promotion gates (empty = promotable).

    WS8.3 / R12 (gap Q8a) — this docstring states only what is actually
    enforced. Three call sites previously advertised "P1-P8" while the code
    implemented a subset; documentation that overstates a governance gate is
    worse than none, because a reviewer trusts it.

    Enforced here: **P1** identity resolved · **P2** confirmed authoritative
    trace · **P4** no conflict on the candidate or its claims · **P6** entity
    type is ROBOT (v0.1) · readiness (`status == READY_FOR_PROMOTION`).
    Enforced separately in `promote()`: **P8** human approval (`approved_by`),
    plus idempotency.

    **P3, P5 and P7 are NOT implemented.** They are DATA-D1 scope, dispositioned
    ACCEPT-DEFER in the WS8 contract (§8.3 Q8b) and deliberately out of WS8's
    hardening scope — WS8 does not add missing promotion gates, it stops the
    documentation from claiming they exist.
    """
    fails: list[str] = []
    # P1 — identity resolved
    if candidate.identity_status not in _PROMOTABLE_IDENTITY:
        fails.append(f"P1 identity not resolved (identity_status={candidate.identity_status})")
    # P2 — an explicitly CONFIRMED authoritative trace (not a bare lead, H2)
    if (
        candidate.trace_state != "TRACE_CONFIRMED"
        or not candidate.trace_url
        or not candidate.trace_verified_by
    ):
        fails.append("P2 no confirmed authoritative trace (needs record_trace)")
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
            "promotable": c.field_key in _APPROVED_FIELDS,
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
        "trace_source_type": candidate.trace_source_type,
        "trace_verified_by": candidate.trace_verified_by,
        "verified_claims": verified,
        "unresolved_claims": unresolved,
        "gates_failed": check_gates(session, candidate),
    }


def promote(session: Session, candidate: DiscoveryCandidate, approved_by: str) -> Robot:
    """HUMAN promotion gate (P8). Raises PromotionError (no canonical write) if any
    gate fails. Idempotent: an already-promoted candidate is refused. The promoted
    robot is always created UNPUBLISHED — publishing is the separate canonical
    catalogue workflow, never a side effect of discovery. Does not commit."""
    if not approved_by or not approved_by.strip():
        raise PromotionError("promotion requires an approving human (approved_by)")
    if candidate.status == "PROMOTED" or candidate.promoted_robot_id is not None:
        raise PromotionError("candidate already promoted (idempotency guard)")
    fails = check_gates(session, candidate)
    if fails:
        raise PromotionError("; ".join(fails))

    proposal = build_proposal(session, candidate)

    if candidate.identity_status == "MATCHED_EXISTING":
        robot = session.get(Robot, candidate.possible_robot_id)
        if robot is None:
            raise PromotionError("P1 matched robot no longer exists")
        # Dedup (DATA-D1.7): no duplicate robot. Fill only NULL approved fields from
        # VERIFIED claims (never overwrite an existing canonical value).
        promoted_fields = _write_verified_fields(robot, candidate)
    else:  # NEW_ENTITY
        manufacturer = _get_or_create_manufacturer(session, candidate)
        robot = Robot(
            slug=_unique_robot_slug(session, candidate.candidate_name or "robot"),
            manufacturer_id=manufacturer.id,
            name=candidate.candidate_name or "Unknown",
            is_published=False,  # always unpublished — publishing is a separate workflow
        )
        session.add(robot)
        session.flush()  # assign robot.id
        promoted_fields = _write_verified_fields(robot, candidate)

    # Provenance ALWAYS recorded, for NEW_ENTITY *and* MATCHED_EXISTING, through the
    # existing G2 evidence model (R5 / Gate J). source_type/verified time come from
    # the confirmed trace — never hardcoded (H2).
    evidence = EvidenceSource(
        subject_type="ROBOT",
        subject_id=robot.id,
        source_url=candidate.trace_url,
        source_type=candidate.trace_source_type or "OTHER",
        source_title=f"{candidate.candidate_name} — confirmed authoritative source",
        confidence="VERIFIED",
        verified_at=candidate.trace_verified_at or datetime.now(UTC),
        note=(
            "DATA-D1 governed promotion (human-approved). Trace confirmed by "
            f"{candidate.trace_verified_by}."
        ),
    )
    session.add(evidence)
    session.flush()

    candidate.status = "PROMOTED"
    candidate.promoted_robot_id = robot.id
    session.add(
        PromotionAudit(
            candidate_id=candidate.id,
            action="PROMOTED",
            promoted_entity_type="ROBOT",
            promoted_robot_id=robot.id,
            evidence_source_id=evidence.id,
            approved_by=approved_by,
            detail={**proposal, "promoted_fields": promoted_fields},
        )
    )
    session.flush()
    return robot


def reject(session: Session, candidate: DiscoveryCandidate, approved_by: str, reason: str) -> None:
    """Human rejection — recorded, not deleted (research history, §21). Independently
    requires an attributed human + a reason (H5); no canonical write."""
    if not approved_by or not approved_by.strip():
        raise PromotionError("rejection requires an approving human (approved_by)")
    if not reason or not reason.strip():
        raise PromotionError("rejection requires a reason")
    if candidate.status in {"PROMOTED", "REJECTED"}:
        raise PromotionError(f"candidate is terminal ({candidate.status})")
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

def _write_verified_fields(robot: Robot, candidate: DiscoveryCandidate) -> list[dict]:
    """Write VERIFIED claims into the approved typed field set, with normalization
    + validation. Never overwrites a non-null canonical value; skips anything that
    fails normalization. Returns the list of fields actually written (for audit)."""
    written: list[dict] = []
    for claim in candidate.claims:
        if claim.claim_status != "VERIFIED" or claim.field_key not in _APPROVED_FIELDS:
            continue
        attr, expected_unit, minimum = _APPROVED_FIELDS[claim.field_key]
        if getattr(robot, attr) is not None:
            continue  # never overwrite existing canonical (conflict-safe)
        if expected_unit and claim.unit and claim.unit.lower() != expected_unit:
            continue  # unit mismatch -> do not coerce
        try:
            value = Decimal(str(claim.claimed_value))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if value < minimum:
            continue  # fails the canonical CHECK domain
        setattr(robot, attr, value)
        written.append({"field": attr, "value": str(value), "evidence_url": claim.evidence_url})
    return written


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
