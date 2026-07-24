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

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.buyer_requirement import BuyerRequirement
from app.models.region import Region
from app.models.use_case import UseCase
from app.schemas.buyer_requirement import BuyerRequirementCreate, BuyerRequirementCreated

router = APIRouter(prefix="/api/buyer-requirements", tags=["buyer-intent"])


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


@router.post("", response_model=BuyerRequirementCreated, status_code=201)
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
        country_region_id = session.execute(
            select(Region.id).where(Region.code == payload.country)
        ).scalar_one_or_none()
        if country_region_id is None:
            # A stated country that does not resolve is a rejection, never a
            # silent NULL (that would erase a real demand signal).
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
        or _raw_has_signal(payload.raw_input)
    )
    if not has_signal:
        raise HTTPException(
            status_code=422, detail="at least one requirement signal is required"
        )

    requirement = BuyerRequirement(
        buyer_type=payload.buyer_type,
        contact_name=_clean(payload.contact_name),
        contact_email=_clean(payload.contact_email),
        organization=_clean(payload.organization),
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
        raw_input=payload.raw_input,
    )
    session.add(requirement)
    session.commit()

    return BuyerRequirementCreated(id=str(requirement.id))


def _clean(value: str | None) -> str | None:
    """Trim text; an empty/whitespace string becomes NULL (unknown), never ""."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None
