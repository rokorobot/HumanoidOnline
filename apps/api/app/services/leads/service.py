"""Commercial-lead capture orchestration (WS7 §6–§12).

`capture_lead` is the single entry point. It enforces the WS7 integrity rules:

  - Requirement-linked capture locks the `buyer_requirement` FOR UPDATE (the same
    serialization point WS6 uses for first-match persistence), reads the PERSISTED
    `match_result` (never reruns matching, never mutates historical scoring
    inputs), validates the submitted robot slugs against that persisted shortlist,
    and creates-or-extends exactly one lead per requirement atomically.
  - A different contact email on an already-bound requirement is a 409 — identity
    is never silently overwritten.
  - A direct Robot-Detail capture (no requirement_id) creates a fresh, minimal
    requirement + lead in one transaction; the selected robot gets match_score
    NULL (it was never produced by the deterministic matcher).
  - The requirements snapshot is frozen server-side; contact identity is NOT
    duplicated inside it (those are first-class lead columns).
  - Provider routing writes PENDING candidates only — no auto-contact.

The service raises HTTPException directly (the semantics are inherently HTTP:
404 / 409 / 422); the router stays a thin edge.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.buyer_requirement import BuyerRequirement
from app.models.commercial_lead import CommercialLead, CommercialLeadRobot
from app.models.match_result import MatchResult
from app.models.region import Region
from app.models.robot import Robot
from app.models.use_case import UseCase
from app.schemas.commercial_lead import CommercialLeadCreate
from app.services.leads.routing import route_providers

SNAPSHOT_VERSION = 1
DIRECT_CAPTURE_WIZARD_VERSION = 1


def _num(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def _iso(v: date | None) -> str | None:
    return v.isoformat() if v is not None else None


def _parse_requirement_id(req_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(req_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="requirement not found") from exc


def _resolve_country(session: Session, code: str | None) -> uuid.UUID | None:
    """Canonical COUNTRY only (a country code, never an economic zone / GLOBAL).
    A stated-but-unresolvable country is a rejection, never a silent NULL."""
    if code is None:
        return None
    region_id = session.execute(
        select(Region.id).where(Region.code == code, Region.type == "COUNTRY")
    ).scalar_one_or_none()
    if region_id is None:
        raise HTTPException(status_code=422, detail=f"unknown country: {code!r}")
    return region_id


def _resolve_published_robots(session: Session, slugs: list[str]) -> dict[str, uuid.UUID]:
    """Resolve slugs to published-robot ids; any unknown/unpublished slug -> 422."""
    if not slugs:
        return {}
    rows = session.execute(
        select(Robot.slug, Robot.id).where(
            Robot.slug.in_(slugs), Robot.is_published.is_(True)
        )
    ).all()
    found = {slug: rid for slug, rid in rows}
    missing = [s for s in slugs if s not in found]
    if missing:
        raise HTTPException(
            status_code=422, detail=f"unknown or unpublished robot(s): {missing}"
        )
    return found


def _snapshot_from_requirement(session: Session, req: BuyerRequirement) -> dict:
    """Frozen decision context. Versioned. Contact identity is intentionally NOT
    duplicated here — it lives in the lead's first-class columns (WS7 §10)."""
    use_case = None
    if req.use_case_id is not None:
        use_case = session.execute(
            select(UseCase.slug).where(UseCase.id == req.use_case_id)
        ).scalar_one_or_none()
    country = None
    if req.country_region_id is not None:
        country = session.execute(
            select(Region.code).where(Region.id == req.country_region_id)
        ).scalar_one_or_none()
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "buyer_type": req.buyer_type,
        "use_case": use_case,
        "industry": req.industry,
        "task_description": req.task_description,
        "environment": req.environment,
        "country": country,
        "payload_min_kg": _num(req.payload_min_kg),
        "operating_hours_day": _num(req.operating_hours_day),
        "manipulation_required": req.manipulation_required,
        "autonomy_required": req.autonomy_required,
        "budget_currency": req.budget_currency,
        "budget_min": _num(req.budget_min),
        "budget_max": _num(req.budget_max),
        "required_by": _iso(req.required_by),
        "preferred_transaction": req.preferred_transaction,
        "raw_input": req.raw_input or {},
    }


def capture_lead(
    session: Session, payload: CommercialLeadCreate
) -> tuple[CommercialLead, bool]:
    """Capture (or extend) a commercial lead. Returns (lead, created) where
    `created` drives the 201 vs 200 status. All state mutations commit atomically."""
    country_id = _resolve_country(session, payload.country)

    if payload.requirement_id is not None:
        return _capture_requirement_linked(session, payload, country_id)
    return _capture_direct(session, payload, country_id)


# --- requirement-linked capture (from /matches/[id]) -------------------------

def _capture_requirement_linked(
    session: Session, payload: CommercialLeadCreate, country_id: uuid.UUID | None
) -> tuple[CommercialLead, bool]:
    rid = _parse_requirement_id(payload.requirement_id)

    # Lock the requirement FOR UPDATE to serialize concurrent first submissions
    # (same discipline as WS6 first-match persistence): a second submission waits,
    # then sees the existing lead and extends it rather than creating a duplicate.
    req = session.execute(
        select(BuyerRequirement).where(BuyerRequirement.id == rid).with_for_update()
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="requirement not found")

    # Persisted shortlist (never rerun matching): slug -> (robot_id, score).
    match_rows = session.execute(
        select(MatchResult.robot_id, MatchResult.score, Robot.slug)
        .join(Robot, Robot.id == MatchResult.robot_id)
        .where(MatchResult.requirement_id == rid)
        .order_by(MatchResult.rank)
    ).all()
    persisted: dict[str, tuple[uuid.UUID, Decimal]] = {
        slug: (robot_id, score) for robot_id, score, slug in match_rows
    }

    submitted = list(payload.robot_slugs)
    submitted_set = set(submitted)
    if not persisted:
        # Zero-match (or a requirement never matched): the ONLY valid selection is
        # empty. A robot attached here would be unbacked by any surfaced match.
        if submitted_set:
            raise HTTPException(
                status_code=422,
                detail="robot_slugs must be empty for a requirement with no matches",
            )
    else:
        unknown = submitted_set - set(persisted)
        if unknown:
            # Spoof protection: the browser may not attach a robot outside the
            # requirement's persisted shortlist.
            raise HTTPException(
                status_code=422,
                detail=f"robot_slugs not in the persisted match shortlist: {sorted(unknown)}",
            )

    resolved_pref = payload.preferred_transaction or req.preferred_transaction
    lead_country_id = country_id if country_id is not None else req.country_region_id

    existing = session.execute(
        select(CommercialLead).where(CommercialLead.requirement_id == rid)
    ).scalars().first()

    # Selected robot ids for this submission (⊆ persisted, validated above).
    submitted_robot_ids = {persisted[s][0] for s in submitted_set}

    if existing is not None:
        # One public commercial conversion object per requirement: extend, never
        # duplicate. Identity is never overwritten.
        if existing.contact_email.strip().lower() != payload.contact_email.lower():
            raise HTTPException(
                status_code=409,
                detail="requirement is already bound to a different contact email",
            )
        _extend_requirement_linked(existing, submitted_robot_ids, payload)
        route_providers(session, existing)
        session.commit()
        return existing, False

    # First capture for this requirement.
    lead = CommercialLead(
        requirement_id=rid,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        organization=payload.organization,
        country_region_id=lead_country_id,
        use_case_id=req.use_case_id,
        preferred_transaction=resolved_pref,
        budget_currency=req.budget_currency,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
        timeline=req.required_by,
        requirements_snapshot=_snapshot_from_requirement(session, req),
        message=payload.message,
    )
    # Persist the FULL surfaced shortlist as decision context; is_selected marks
    # the buyer's pick(s) (the clicked card, or every robot for a shortlist CTA).
    for slug, (robot_id, score) in persisted.items():
        lead.robots.append(
            CommercialLeadRobot(
                robot_id=robot_id,
                match_score=score,
                is_selected=slug in submitted_set,
            )
        )
    session.add(lead)

    # First requirement-linked capture may populate the requirement's contact
    # identity (WS7 §8). This does NOT alter the scoring inputs, so the persisted
    # match_result still describes the requirement that generated it.
    if req.contact_email is None:
        req.contact_email = payload.contact_email
    if req.contact_name is None:
        req.contact_name = payload.contact_name
    if req.organization is None:
        req.organization = payload.organization

    session.flush()  # assign lead.id before routing appends child rows
    route_providers(session, lead)
    session.commit()
    return lead, True


def _extend_requirement_linked(
    lead: CommercialLead,
    submitted_robot_ids: set[uuid.UUID],
    payload: CommercialLeadCreate,
) -> None:
    """Extend an existing requirement-linked lead: union in newly-selected robots
    (rows for the full shortlist already exist from first capture) and fill a
    message if none was captured yet. Additive only — a robot is never
    un-selected, and existing identity/message are never clobbered."""
    for row in lead.robots:
        if row.robot_id in submitted_robot_ids:
            row.is_selected = True
    if payload.message is not None and lead.message is None:
        lead.message = payload.message


# --- direct Robot-Detail capture (no requirement) ----------------------------

def _capture_direct(
    session: Session, payload: CommercialLeadCreate, country_id: uuid.UUID | None
) -> tuple[CommercialLead, bool]:
    if not payload.robot_slugs:
        raise HTTPException(
            status_code=422,
            detail="a direct capture (no requirement_id) must name at least one robot",
        )
    robot_ids = _resolve_published_robots(session, payload.robot_slugs)

    resolved_pref = payload.preferred_transaction or "UNKNOWN"

    # A legitimate but MINIMAL requirement. Unknown stays unknown — we do NOT
    # fabricate task_description / use_case / budget / payload. The origin is
    # retained in a versioned raw_input.
    primary_slug = payload.robot_slugs[0]
    req = BuyerRequirement(
        buyer_type="UNKNOWN",
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        organization=payload.organization,
        country_region_id=country_id,
        preferred_transaction=resolved_pref,
        raw_input={
            "wizard_version": DIRECT_CAPTURE_WIZARD_VERSION,
            "source": "robot_detail_direct_capture",
            "answers": {
                "robot_interest": {"state": "ANSWERED", "value": primary_slug},
            },
        },
    )
    session.add(req)
    session.flush()  # assign req.id

    lead = CommercialLead(
        requirement_id=req.id,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        organization=payload.organization,
        country_region_id=country_id,
        use_case_id=None,
        preferred_transaction=resolved_pref,
        requirements_snapshot=_snapshot_from_requirement(session, req),
        message=payload.message,
    )
    # The selected robot(s) were not produced by the deterministic matcher, so
    # match_score is NULL (never 0); the buyer explicitly asked about them.
    for slug in payload.robot_slugs:
        lead.robots.append(
            CommercialLeadRobot(
                robot_id=robot_ids[slug], match_score=None, is_selected=True
            )
        )
    session.add(lead)
    session.flush()
    route_providers(session, lead)
    session.commit()
    return lead, True
