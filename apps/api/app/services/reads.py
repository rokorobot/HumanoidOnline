"""Serialization + read helpers for the knowledge layer.

Preserves the frozen semantics: unknown price (no rows) -> price_display is null;
QUOTE_ONLY is a known fact with amount null; available_modes/deployment_count
come from the canonical `robot_commercial_snapshot` view.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceSource
from app.models.robot import Robot
from app.models.spec import Specification
from app.schemas.common import EvidenceRead, ManufacturerRef, PriceDisplay
from app.schemas.robot import (
    AvailabilityOfferRead,
    CapabilityRead,
    DeploymentRead,
    ExtendedSpec,
    PricingOfferRead,
    RobotDetail,
    RobotImageRead,
    RobotListItem,
    SpecsBlock,
    StatusHistoryEntry,
    UseCaseFitRead,
    VariantRead,
)

# Maturity ranking for a manufacturer's PORTFOLIO status (display-only, derived
# from an existing canonical fact — the published robots' commercial_status).
# DISCONTINUED is deliberately OUTSIDE this ranking: it is only surfaced when
# every published robot is discontinued. No new predicate is introduced.
_PORTFOLIO_ORDER = [
    "ANNOUNCED", "DEVELOPMENT", "PROTOTYPE", "PILOT", "EARLY_ACCESS",
    "LIMITED_COMMERCIAL", "COMMERCIAL", "RAAS_DEPLOYMENT",
]


def derive_portfolio_status(statuses: list[str]) -> str | None:
    """Most commercially-mature ACTIVE status among a manufacturer's published
    robots. Returns ``DISCONTINUED`` only when every robot is discontinued, and
    ``None`` when there are no published robots.
    """
    if not statuses:
        return None
    active = [s for s in statuses if s != "DISCONTINUED"]
    if not active:
        return "DISCONTINUED"
    return max(
        active,
        key=lambda s: _PORTFOLIO_ORDER.index(s) if s in _PORTFOLIO_ORDER else -1,
    )


# Headline-price preference: prefer a purchase-like mode, then the most concrete
# price_type, then most recently updated.
_TXN_PREF = {"PURCHASE": 0, "DEVELOPER": 1}
_PRICE_TYPE_RANK = {"PUBLIC": 0, "FROM": 1, "ESTIMATED": 2, "RANGE": 3, "QUOTE_ONLY": 4}


def _f(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _country_code(manufacturer) -> str | None:
    country = getattr(manufacturer, "country", None)
    return country.code if country is not None else None


def _spec_value(spec: Specification) -> float | bool | str | None:
    if spec.value_number is not None:
        return float(spec.value_number)
    if spec.value_bool is not None:
        return spec.value_bool
    return spec.value_text


def load_evidence(
    session: Session, subject_ids: set[uuid.UUID]
) -> dict[tuple[str, uuid.UUID], EvidenceRead]:
    """Best evidence per (subject_type, subject_id): verified first, then newest."""
    if not subject_ids:
        return {}
    rows = list(
        session.execute(
            select(EvidenceSource).where(EvidenceSource.subject_id.in_(subject_ids))
        ).scalars()
    )
    rows.sort(key=lambda e: (1 if e.verified_at else 0, e.observed_at), reverse=True)
    best: dict[tuple[str, uuid.UUID], EvidenceRead] = {}
    for e in rows:
        key = (e.subject_type, e.subject_id)
        if key not in best:
            best[key] = EvidenceRead(
                source_type=e.source_type,
                confidence=e.confidence,
                observed_at=e.observed_at,
                verified_at=e.verified_at,
                published_at=e.published_at,
                source_url=e.source_url,
            )
    return best


def snapshot_for(
    session: Session, robot_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, list[str]]]:
    """(deployment_count, available_modes) per robot from the canonical view."""
    if not robot_ids:
        return {}
    rows = session.execute(
        text(
            "SELECT id, deployment_count, available_modes "
            "FROM humanoid.robot_commercial_snapshot WHERE id = ANY(:ids)"
        ),
        {"ids": list(robot_ids)},
    ).all()
    return {r.id: (int(r.deployment_count or 0), list(r.available_modes or [])) for r in rows}


def price_display_for(robot: Robot) -> PriceDisplay | None:
    offers = [p for p in robot.pricing_offers if p.is_current]
    if not offers:
        return None  # unknown price — no rows
    offers.sort(
        key=lambda p: (
            _TXN_PREF.get(p.transaction_type, 9),
            _PRICE_TYPE_RANK.get(p.price_type, 9),
            -p.updated_at.timestamp(),
        )
    )
    p = offers[0]
    return PriceDisplay(
        type=p.price_type,
        amount=_f(p.price),
        amount_min=_f(p.price_min),
        amount_max=_f(p.price_max),
        currency=p.currency,
        billing_period=p.billing_period,
    )


def serialize_list_item(
    robot: Robot, snapshot: dict[uuid.UUID, tuple[int, list[str]]]
) -> RobotListItem:
    dep_count, modes = snapshot.get(robot.id, (0, []))
    return RobotListItem(
        id=str(robot.id),
        slug=robot.slug,
        name=robot.name,
        manufacturer=ManufacturerRef(
            slug=robot.manufacturer.slug, name=robot.manufacturer.name
        ),
        summary=robot.summary,
        hero_image_url=robot.hero_image_url,
        commercial_status=robot.commercial_status,
        payload_kg=_f(robot.payload_kg),
        height_cm=_f(robot.height_cm),
        mobility=robot.mobility,
        price_display=price_display_for(robot),
        available_modes=modes,
        deployment_count=dep_count,
    )


def _specs_block(robot: Robot) -> SpecsBlock:
    return SpecsBlock(
        height_cm=_f(robot.height_cm),
        weight_kg=_f(robot.weight_kg),
        payload_kg=_f(robot.payload_kg),
        walk_speed_ms=_f(robot.walk_speed_ms),
        runtime_minutes=robot.runtime_minutes,
        battery_wh=_f(robot.battery_wh),
        mobility=robot.mobility,
        degrees_of_freedom=robot.degrees_of_freedom,
        hand_type=robot.hand_type,
        hand_dof=robot.hand_dof,
        autonomy=robot.autonomy,
        has_manipulation=robot.has_manipulation,
        has_teleoperation=robot.has_teleoperation,
        has_vision=robot.has_vision,
        has_language_ui=robot.has_language_ui,
        has_sdk=robot.has_sdk,
        has_api=robot.has_api,
        ros_support=robot.ros_support,
        developer_edition=robot.developer_edition,
        simulation_support=robot.simulation_support,
    )


def serialize_detail(session: Session, robot: Robot) -> RobotDetail:
    subject_ids: set[uuid.UUID] = {robot.id}
    subject_ids |= {p.id for p in robot.pricing_offers}
    subject_ids |= {a.id for a in robot.availability_offers}
    subject_ids |= {d.id for d in robot.deployments}
    ev = load_evidence(session, subject_ids)

    extended = [
        ExtendedSpec(
            key=s.definition.key,
            label=s.definition.label,
            value=_spec_value(s),
            unit=s.unit or s.definition.unit,
            category=s.definition.category,
        )
        for s in robot.specifications
    ]
    capabilities = [
        CapabilityRead(
            slug=rc.capability.slug,
            name=rc.capability.name,
            supported=rc.supported,
            detail=rc.detail,
        )
        for rc in robot.robot_capabilities
    ]
    variants = [
        VariantRead(slug=v.slug, name=v.name, is_developer=v.is_developer)
        for v in robot.variants
    ]
    fits = sorted(
        (
            UseCaseFitRead(
                use_case=f.use_case.slug,
                fit_score=_f(f.fit_score),
                commercial_readiness=f.commercial_readiness,
                limitations=f.limitations,
            )
            for f in robot.use_case_fits
        ),
        key=lambda x: (x.fit_score if x.fit_score is not None else -1.0),
        reverse=True,
    )
    pricing = [
        PricingOfferRead(
            transaction_type=p.transaction_type,
            price_type=p.price_type,
            price=_f(p.price),
            price_min=_f(p.price_min),
            price_max=_f(p.price_max),
            currency=p.currency,
            billing_period=p.billing_period,
            region=p.region.code if p.region else None,
            provider=p.provider.slug if p.provider else None,
            evidence=ev.get(("PRICING_OFFER", p.id)),
        )
        for p in robot.pricing_offers
        if p.is_current
    ]
    availability = [
        AvailabilityOfferRead(
            transaction_type=a.transaction_type,
            availability_status=a.availability_status,
            region=a.region.code if a.region else None,
            provider=a.provider.slug if a.provider else None,
            available_from=a.available_from,
            lead_time_days=a.lead_time_days,
            evidence=ev.get(("AVAILABILITY_OFFER", a.id)),
        )
        for a in robot.availability_offers
        if a.is_current
    ]
    deployments = [
        DeploymentRead(
            customer_name=d.customer_name,
            region=d.region.code if d.region else None,
            use_case=d.use_case.slug if d.use_case else None,
            transaction_type=d.transaction_type,
            unit_count=d.unit_count,
            contract_value=_f(d.contract_value),
            summary=d.summary,
            evidence=ev.get(("DEPLOYMENT", d.id)),
        )
        for d in robot.deployments
    ]
    status_history = [
        StatusHistoryEntry(status=h.status, effective_at=h.effective_at, note=h.note)
        for h in robot.status_history
    ]
    # MEDIA-01: only DISPLAY-ELIGIBLE images cross the API boundary (identity
    # VERIFIED + rights PERMITTED/ATTRIBUTION_REQUIRED). A non-null image_url is
    # never sufficient. Primary first, then official, for a stable gallery order.
    images = [
        RobotImageRead(
            image_url=img.image_url,
            image_type=img.image_type,
            source_name=img.source_name,
            source_url=img.source_url,
            source_type=img.source_type,
            is_official=img.is_official,
            is_primary=img.is_primary,
            attribution=img.attribution,
        )
        for img in sorted(
            (i for i in robot.images if i.is_display_eligible()),
            key=lambda i: (not i.is_primary, not i.is_official),
        )
    ]

    return RobotDetail(
        id=str(robot.id),
        slug=robot.slug,
        name=robot.name,
        manufacturer=ManufacturerRef(
            slug=robot.manufacturer.slug,
            name=robot.manufacturer.name,
            country=_country_code(robot.manufacturer),
        ),
        commercial_status=robot.commercial_status,
        summary=robot.summary,
        description=robot.description,
        hero_image_url=robot.hero_image_url,
        announced_year=robot.announced_year,
        status_history=status_history,
        specs=_specs_block(robot),
        extended_specs=extended,
        capabilities=capabilities,
        variants=variants,
        use_case_fits=fits,
        pricing_offers=pricing,
        availability_offers=availability,
        deployments=deployments,
        images=images,
    )


# Comparison groups: (group, first-class robot attribute, label)
COMPARE_FIELDS: list[tuple[str, str, str]] = [
    ("commercial", "commercial_status", "Commercial status"),
    ("physical", "height_cm", "Height (cm)"),
    ("physical", "weight_kg", "Weight (kg)"),
    ("physical", "payload_kg", "Payload (kg)"),
    ("physical", "walk_speed_ms", "Walk speed (m/s)"),
    ("physical", "runtime_minutes", "Runtime (min)"),
    ("physical", "mobility", "Mobility"),
    ("manipulation", "hand_type", "Hand type"),
    ("manipulation", "hand_dof", "Hand DOF"),
    ("manipulation", "has_manipulation", "Manipulation"),
    ("intelligence", "autonomy", "Autonomy"),
    ("intelligence", "has_vision", "Vision"),
    ("intelligence", "has_language_ui", "Language UI"),
    ("developer", "has_sdk", "SDK"),
    ("developer", "ros_support", "ROS support"),
    ("developer", "developer_edition", "Developer edition"),
]
