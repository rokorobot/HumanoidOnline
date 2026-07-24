"""Impure loader/persistence for matching (WS6).

Materializes the requirement + the published-candidate snapshot from PostgreSQL
into the pure engine's dataclasses, and persists the result. All DB access lives
here so `engine.py` stays a pure, deterministic function.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.buyer_requirement import BuyerRequirement
from app.models.evidence import EvidenceSource
from app.models.region import Region
from app.models.robot import Robot
from app.models.use_case import UseCase
from app.services.matching.inputs import (
    OfferInput,
    PriceInput,
    RequirementInput,
    RobotInput,
)


def _f(v) -> float | None:
    return float(v) if v is not None else None


def to_requirement_input(session: Session, req: BuyerRequirement) -> RequirementInput:
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
    return RequirementInput(
        use_case=use_case,
        country=country,
        payload_min_kg=_f(req.payload_min_kg),
        operating_hours_day=_f(req.operating_hours_day),
        manipulation_required=req.manipulation_required,
        autonomy_required=req.autonomy_required,
        budget_currency=req.budget_currency,
        budget_min=_f(req.budget_min),
        budget_max=_f(req.budget_max),
        required_by=req.required_by,
        preferred_transaction=req.preferred_transaction,
    )


def _applicable_region_ids(session: Session, country_code: str) -> set[uuid.UUID]:
    """The country itself + its ancestor regions (economic zone, ...) + GLOBAL —
    the regions whose offers apply to a buyer in `country_code`."""
    row = session.execute(
        select(Region.id, Region.parent_id).where(
            Region.code == country_code, Region.type == "COUNTRY"
        )
    ).first()
    ids: set[uuid.UUID] = set()
    if row is not None:
        ids.add(row[0])
        parent = row[1]
        while parent is not None:
            ids.add(parent)
            parent = session.execute(
                select(Region.parent_id).where(Region.id == parent)
            ).scalar_one_or_none()
    global_id = session.execute(
        select(Region.id).where(Region.code == "GLOBAL")
    ).scalar_one_or_none()
    if global_id is not None:
        ids.add(global_id)
    return ids


def load_candidates(session: Session, req: RequirementInput) -> list[RobotInput]:
    country_known = req.country is not None
    applicable = _applicable_region_ids(session, req.country) if country_known else set()

    def geo_ok(region_id) -> bool:
        # Region-agnostic (NULL) applies everywhere; when no country is stated
        # geography is inactive, so applicability is not a constraint.
        return (not country_known) or region_id is None or region_id in applicable

    target_uc_id = None
    if req.use_case is not None:
        target_uc_id = session.execute(
            select(UseCase.id).where(UseCase.slug == req.use_case)
        ).scalar_one_or_none()

    # Freshest verified evidence per subject (robot / offer / deployment id).
    evidence = dict(
        session.execute(
            select(EvidenceSource.subject_id, func.max(EvidenceSource.verified_at))
            .where(EvidenceSource.verified_at.is_not(None))
            .group_by(EvidenceSource.subject_id)
        ).all()
    )

    robots = session.execute(
        select(Robot)
        .where(Robot.is_published.is_(True))
        .options(
            selectinload(Robot.pricing_offers),
            selectinload(Robot.availability_offers),
            selectinload(Robot.deployments),
            selectinload(Robot.use_case_fits),
        )
    ).scalars().all()

    out: list[RobotInput] = []
    for r in robots:
        uc_fit = None
        if target_uc_id is not None:
            for f in r.use_case_fits:
                if f.use_case_id == target_uc_id:
                    uc_fit = _f(f.fit_score)
                    break

        offers = tuple(
            OfferInput(
                transaction_type=o.transaction_type,
                availability_status=o.availability_status,
                is_current=o.is_current,
                region_code=None,
                geo_applicable=geo_ok(o.region_id),
                available_from=o.available_from,
            )
            for o in r.availability_offers
        )
        prices = tuple(
            PriceInput(
                transaction_type=p.transaction_type,
                price_type=p.price_type,
                currency=p.currency,
                price=_f(p.price),
                price_min=_f(p.price_min),
                price_max=_f(p.price_max),
                billing_period=p.billing_period,
                is_current=p.is_current,
                geo_applicable=geo_ok(p.region_id),
            )
            for p in r.pricing_offers
        )

        subject_ids = (
            [r.id]
            + [p.id for p in r.pricing_offers]
            + [a.id for a in r.availability_offers]
            + [d.id for d in r.deployments]
        )
        stamps = [evidence[s] for s in subject_ids if s in evidence]
        freshest = max(stamps) if stamps else None

        out.append(
            RobotInput(
                slug=r.slug,
                name=r.name,
                manufacturer_name=r.manufacturer.name,
                manufacturer_country=None,
                commercial_status=r.commercial_status,
                payload_kg=_f(r.payload_kg),
                has_manipulation=r.has_manipulation,
                autonomy=r.autonomy,
                runtime_minutes=r.runtime_minutes,
                has_sdk=r.has_sdk,
                ros_support=r.ros_support,
                developer_edition=r.developer_edition,
                use_case_fit=uc_fit,
                offers=offers,
                prices=prices,
                deployment_count=len(r.deployments),
                freshest_verified_at=freshest,
            )
        )
    return out


def robot_ids_by_slug(session: Session, slugs: list[str]) -> dict[str, uuid.UUID]:
    if not slugs:
        return {}
    rows = session.execute(
        select(Robot.slug, Robot.id).where(Robot.slug.in_(slugs))
    ).all()
    return {slug: rid for slug, rid in rows}
