"""Buyer-intent write API (API contract §4) — WS5.

`POST /api/buyer-requirements` persists exactly one `buyer_requirement` and
returns its id. This is the platform's first write path, so it holds the line on
the data laws:

  - Canonical resolution only: a use-case slug / country code resolves to an
    existing row's id, or the request is rejected 422. Buyer input NEVER creates
    a taxonomy row, and a stated-but-unresolvable country is never silently
    dropped to NULL.
  - UNKNOWN != SKIPPED: the nullable structured columns cannot tell them apart,
    so the full versioned `raw_input` is stored verbatim to preserve the
    distinction. An explicitly-UNKNOWN answer is itself a demand signal.
  - Known FALSE persists (manipulation_required); no budget => NULL currency
    (the DB DEFAULT 'USD' is overridden with an explicit NULL).
  - No matching and no lead: this endpoint creates zero `match_result` and zero
    `commercial_lead` rows. Matching runs later (WS6, on the first /matches fetch).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.buyer_requirement import BuyerRequirement
from app.models.match_result import MatchResult
from app.models.region import Region
from app.models.robot import Robot
from app.models.use_case import UseCase
from app.schemas.buyer_requirement import BuyerRequirementCreate, BuyerRequirementCreated
from app.schemas.match import MatchItem, MatchResponse, MatchRobotRef, RequirementRead
from app.security.rate_limit import rate_limited
from app.services.matching import match
from app.services.matching.repository import (
    load_candidates,
    robot_ids_by_slug,
    to_requirement_input,
)

router = APIRouter(prefix="/api/buyer-requirements", tags=["buyer-intent"])


def _parse_id(req_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(req_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="requirement not found") from exc


def _raw_has_signal(raw_input: dict | None) -> bool:
    """True if any wizard answer is explicitly ANSWERED or UNKNOWN — both are
    demand signals. SKIPPED (or an absent answer) is not. This is what lets an
    explicit 'Unknown' transaction preference (ANSWERED with value UNKNOWN, which
    projects to preferred_transaction='UNKNOWN') still count as intent, distinct
    from skipping the step."""
    if not isinstance(raw_input, dict):
        return False
    answers = raw_input.get("answers")
    if not isinstance(answers, dict):
        return False
    return any(
        isinstance(a, dict) and a.get("state") in ("ANSWERED", "UNKNOWN")
        for a in answers.values()
    )


@router.post(
    "",
    response_model=BuyerRequirementCreated,
    status_code=201,
    # WS8.1 / R3 — endpoint-aware abuse control on the anonymous buyer-intent
    # write path. No authentication is introduced (WS8-L10): WS5 anonymity is
    # preserved, and abuse is bounded by IP-tiered limits only.
    dependencies=[Depends(rate_limited("buyer_requirements"))],
)
def create_buyer_requirement(
    payload: BuyerRequirementCreate,
    session: Annotated[Session, Depends(get_session)],
) -> BuyerRequirementCreated:
    # --- canonical resolution (never create taxonomy rows from buyer input) ---
    use_case_id = None
    if payload.use_case is not None:
        use_case_id = session.execute(
            select(UseCase.id).where(UseCase.slug == payload.use_case)
        ).scalar_one_or_none()
        if use_case_id is None:
            raise HTTPException(status_code=422, detail=f"unknown use_case: {payload.use_case!r}")

    country_region_id = None
    if payload.country is not None:
        # Canonical COUNTRY only: the Country step is a country, so a non-country
        # region code (EU, GLOBAL, an economic zone) must NOT resolve. A stated
        # country that does not resolve is a rejection, never a silent NULL.
        country_region_id = session.execute(
            select(Region.id).where(
                Region.code == payload.country, Region.type == "COUNTRY"
            )
        ).scalar_one_or_none()
        if country_region_id is None:
            raise HTTPException(status_code=422, detail=f"unknown country: {payload.country!r}")

    # --- budget: no 0/USD defaulting on a no-budget requirement ---
    if payload.budget is not None:
        budget_currency = payload.budget.currency
        budget_min = payload.budget.min
        budget_max = payload.budget.max
    else:
        budget_currency = None  # explicit NULL overrides the DDL DEFAULT 'USD'
        budget_min = None
        budget_max = None

    # Versioned wizard payload (schema-validated: wizard_version + answer states).
    raw_dict = payload.raw_input.model_dump()

    # --- at least one requirement signal (an explicit UNKNOWN counts) ---
    has_signal = any(
        v is not None
        for v in (
            use_case_id,
            _clean(payload.industry),
            _clean(payload.task_description),
            _clean(payload.environment),
            payload.payload_min_kg,
            payload.operating_hours_day,
            payload.manipulation_required,  # False is a signal (is not None)
            payload.autonomy_required,
            country_region_id,
            budget_min,
            budget_max,
            payload.required_by,
        )
    )
    has_signal = (
        has_signal
        or payload.preferred_transaction != "UNKNOWN"
        or _raw_has_signal(raw_dict)
    )
    if not has_signal:
        raise HTTPException(
            status_code=422, detail="at least one requirement signal is required"
        )

    # WS5 is anonymous: contact identity (name/email/organization) is NOT captured
    # here — those columns stay NULL and are owned by WS7 (commercial lead).
    requirement = BuyerRequirement(
        buyer_type=payload.buyer_type,
        country_region_id=country_region_id,
        use_case_id=use_case_id,
        industry=_clean(payload.industry),
        task_description=_clean(payload.task_description),
        environment=_clean(payload.environment),
        payload_min_kg=payload.payload_min_kg,
        operating_hours_day=payload.operating_hours_day,
        manipulation_required=payload.manipulation_required,
        autonomy_required=payload.autonomy_required,
        budget_currency=budget_currency,
        budget_min=budget_min,
        budget_max=budget_max,
        required_by=payload.required_by,
        preferred_transaction=payload.preferred_transaction,
        raw_input=raw_dict,
    )
    session.add(requirement)
    session.commit()

    return BuyerRequirementCreated(id=str(requirement.id))


@router.get("/{req_id}", response_model=RequirementRead)
def get_buyer_requirement(
    req_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> RequirementRead:
    """Anonymous requirement read — powers Adjust Requirements (prefill a NEW
    wizard from a stored requirement; it never mutates the historical one)."""
    rid = _parse_id(req_id)
    req = session.get(BuyerRequirement, rid)
    if req is None:
        raise HTTPException(status_code=404, detail="requirement not found")
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
    return RequirementRead(
        id=str(req.id),
        use_case=use_case,
        country=country,
        industry=req.industry,
        task_description=req.task_description,
        environment=req.environment,
        payload_min_kg=float(req.payload_min_kg) if req.payload_min_kg is not None else None,
        operating_hours_day=(
            float(req.operating_hours_day) if req.operating_hours_day is not None else None
        ),
        manipulation_required=req.manipulation_required,
        autonomy_required=req.autonomy_required,
        budget_currency=req.budget_currency,
        budget_min=float(req.budget_min) if req.budget_min is not None else None,
        budget_max=float(req.budget_max) if req.budget_max is not None else None,
        required_by=req.required_by,
        preferred_transaction=req.preferred_transaction,
        raw_input=req.raw_input,
    )


def _items_from_results(session: Session, rid: uuid.UUID) -> list[MatchItem]:
    rows = session.execute(
        select(MatchResult, Robot)
        .join(Robot, Robot.id == MatchResult.robot_id)
        .where(MatchResult.requirement_id == rid)
        .order_by(MatchResult.rank)
    ).all()
    return [
        MatchItem(
            robot=MatchRobotRef(slug=rob.slug, name=rob.name, manufacturer=rob.manufacturer.name),
            score=int(mr.score),
            rank=mr.rank,
            category=mr.category,
            score_breakdown=mr.score_breakdown,
            reasons=list(mr.reasons or []),
            warnings=list(mr.warnings or []),
        )
        for mr, rob in rows
    ]


@router.get("/{req_id}/matches", response_model=MatchResponse)
def get_matches(
    req_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> MatchResponse:
    """Deterministic matching, computed on the FIRST request and persisted; later
    requests return the stored result unchanged (idempotent). The requirement row
    is locked FOR UPDATE so a concurrent first request waits and then reads the
    persisted rows rather than rescoring. A zero-survivor outcome persists nothing
    (no sentinel row, no schema change) and is recomputed deterministically."""
    rid = _parse_id(req_id)
    # Lock the requirement to serialize concurrent first-fetches.
    req = session.execute(
        select(BuyerRequirement).where(BuyerRequirement.id == rid).with_for_update()
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="requirement not found")

    published_total = session.execute(
        select(func.count(Robot.id)).where(Robot.is_published.is_(True))
    ).scalar_one()

    existing = _items_from_results(session, rid)
    if existing:
        session.commit()  # release the lock; nothing to write
        return MatchResponse(
            requirement_id=req_id,
            matches=existing,
            excluded_count=published_total - len(existing),
            no_match_explanation=None,
        )

    # First run (or a prior zero-survivor outcome): score and persist.
    req_input = to_requirement_input(session, req)
    candidates = load_candidates(session, req_input)
    outcome = match(req_input, candidates)
    cand_by_slug = {c.slug: c for c in candidates}
    slug_to_id = robot_ids_by_slug(session, [m.slug for m in outcome.matches])

    for m in outcome.matches:
        session.add(
            MatchResult(
                requirement_id=rid,
                robot_id=slug_to_id[m.slug],
                score=m.score,
                rank=m.rank,
                category=m.category,
                score_breakdown=m.breakdown,
                reasons=list(m.reasons),
                warnings=list(m.warnings),
            )
        )
    session.commit()

    items = [
        MatchItem(
            robot=MatchRobotRef(
                slug=m.slug,
                name=cand_by_slug[m.slug].name,
                manufacturer=cand_by_slug[m.slug].manufacturer_name,
            ),
            score=m.score,
            rank=m.rank,
            category=m.category,
            score_breakdown=m.breakdown,
            reasons=list(m.reasons),
            warnings=list(m.warnings),
        )
        for m in outcome.matches
    ]
    return MatchResponse(
        requirement_id=req_id,
        matches=items,
        excluded_count=outcome.excluded_count,
        no_match_explanation=outcome.no_match_explanation,
    )


def _clean(value: str | None) -> str | None:
    """Trim text; an empty/whitespace string becomes NULL (unknown), never ""."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None
