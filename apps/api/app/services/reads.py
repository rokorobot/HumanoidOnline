"""Serialization + read helpers for the knowledge layer.

Preserves the frozen semantics: unknown price (no rows) -> price_display is null;
QUOTE_ONLY is a known fact with amount null; available_modes/deployment_count
come from the canonical `robot_commercial_snapshot` view.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.models.commercial import AvailabilityOffer, Deployment, PricingOffer
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
    RobotImagePrimary,
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


def load_evidence_rows(
    session: Session, subject_ids: set[uuid.UUID]
) -> dict[tuple[str, uuid.UUID], EvidenceSource]:
    """Best evidence per (subject_type, subject_id): verified first, then newest,
    then a deterministic internal tie-break (`docs/20` §13.1).

    **This function owns the one canonical selection rule.** It is stated here
    and nowhere else: the agent surface must cite the same row the website
    displays, so a second implementation would eventually mean two catalogues
    disagreeing about their own provenance.

    The third sort key is not decoration. Verified-ness and `observed_at` can tie
    exactly — the seeded catalogue imports every row with one timestamp — and a
    stable sort then falls back to the order an unordered query happened to
    return, which PostgreSQL does not guarantee. Since an `evidence_ref`
    addresses the *selected row*, an unbroken tie would let a published citation
    point somewhere else after a replan. The row id orders ties and nothing else;
    it is never exposed (§8, §20).

    Returns the ORM rows, because AGENT-02 needs the selected row's identity to
    issue an `evidence_ref` for it (§7.1). Callers that only need the public
    metadata use `load_evidence`, which is this function plus one projection.
    """
    if not subject_ids:
        return {}
    rows = list(
        session.execute(
            select(EvidenceSource).where(EvidenceSource.subject_id.in_(subject_ids))
        ).scalars()
    )
    rows.sort(
        key=lambda e: (1 if e.verified_at else 0, e.observed_at, str(e.id)), reverse=True
    )
    best: dict[tuple[str, uuid.UUID], EvidenceSource] = {}
    for e in rows:
        best.setdefault((e.subject_type, e.subject_id), e)
    return best


def evidence_read(row: EvidenceSource) -> EvidenceRead:
    """The public HTTP provenance metadata of one evidence row.

    Exactly the fields `docs/20` §7 lists. Notably absent: `id` and `subject_id`
    (§8, §20 — never public on any surface), and `subject_type`/`evidence_ref`,
    which belong to the *agent* evidence object (§9.5) and are added by the agent
    projection rather than pushed into the shared HTTP schema.
    """
    return EvidenceRead(
        source_type=row.source_type,
        confidence=row.confidence,
        observed_at=row.observed_at,
        verified_at=row.verified_at,
        published_at=row.published_at,
        source_url=row.source_url,
    )


def load_evidence(
    session: Session, subject_ids: set[uuid.UUID]
) -> dict[tuple[str, uuid.UUID], EvidenceRead]:
    """`load_evidence_rows` projected onto the public metadata.

    The long-standing interface, unchanged for its callers. Selection is not
    reimplemented here — this is one call plus one projection, so HTTP and AGENT
    can never diverge on *which* row is the best evidence for a fact.
    """
    return {
        key: evidence_read(row)
        for key, row in load_evidence_rows(session, subject_ids).items()
    }


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


def _eligible_images(robot: Robot):
    """Display-eligible images (MEDIA-01 gate), primary first then official. The
    single ordering shared by the catalogue card and the detail gallery."""
    return sorted(
        (i for i in robot.images if i.is_display_eligible()),
        key=lambda i: (not i.is_primary, not i.is_official),
    )


def _governed_hero_image_url(robot: Robot) -> str | None:
    """WS8.3 / R11 — close the `hero_image_url` bypass (gap Q6).

    `robot.hero_image_url` is a free-text column that predates MEDIA-01 and was
    serialized RAW on both read paths, so any URL written there reached the API
    without passing the eligibility gate at all — MEDIA-01 enforced on one field
    and bypassable via another. It renders in no component today, which made it
    a latent hole rather than a live one, but "currently unused" is not a
    security property.

    The column stays (it is in the frozen API contract) and keeps its nullable
    shape, but it may only carry a URL that a display-eligible image *also*
    carries. Anything else serializes as null: MEDIA-01 is the single authority
    on which imagery may cross the boundary.
    """
    hero = (robot.hero_image_url or "").strip()
    if not hero:
        return None
    return hero if any(i.image_url == hero for i in _eligible_images(robot)) else None


def _primary_image(robot: Robot) -> RobotImagePrimary | None:
    """The catalogue-card primary image (MEDIA-01.8). Among display-eligible images,
    prefer an explicit primary, then a FRONT view (comparable lineup), then official."""
    eligible = _eligible_images(robot)
    if not eligible:
        return None
    img = min(
        eligible,
        key=lambda i: (not i.is_primary, i.image_type != "FRONT", not i.is_official),
    )
    return RobotImagePrimary(
        image_url=img.image_url, source_name=img.source_name, is_official=img.is_official
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
        hero_image_url=_governed_hero_image_url(robot),
        primary_image=_primary_image(robot),
        commercial_status=robot.commercial_status,
        payload_kg=_f(robot.payload_kg),
        height_cm=_f(robot.height_cm),
        mobility=robot.mobility,
        price_display=price_display_for(robot),
        available_modes=modes,
        deployment_count=dep_count,
        updated_at=robot.updated_at,
    )


def _specs_block(robot: Robot) -> SpecsBlock:
    return SpecsBlock(
        height_cm=_f(robot.height_cm),
        weight_kg=_f(robot.weight_kg),
        arm_span_cm=_f(robot.arm_span_cm),
        reach_cm=_f(robot.reach_cm),
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


def load_detail(session: Session, slug: str) -> Robot | None:
    """The one governed detail load: a *published* robot by canonical slug.

    Moved here from the HTTP router (`docs/20` §6) so the detail route, `compare`
    and AGENT-02's `get_robot` share one implementation. Critically, the
    publication predicate lives *inside* this function rather than at each call
    site: a caller cannot forget it, and there is no parameter with which to ask
    for an unpublished robot (AGENT-01.7, §14).

    Slug matching is exact and case-sensitive, and there are no aliases (§6), so
    an unknown slug, an unpublished one and a case variant are all simply
    ``None`` — indistinguishable, which is the point.
    """
    stmt = (
        select(Robot)
        .where(Robot.slug == slug, Robot.is_published.is_(True))
        .options(
            selectinload(Robot.variants),
            selectinload(Robot.status_history),
            selectinload(Robot.specifications),
            selectinload(Robot.robot_capabilities),
            selectinload(Robot.use_case_fits),
            selectinload(Robot.pricing_offers),
            selectinload(Robot.availability_offers),
            selectinload(Robot.deployments),
            selectinload(Robot.images),
        )
    )
    return session.execute(stmt).scalars().first()


# ---------------------------------------------------------------------------
# Which commercial facts a detail response actually exposes.
#
# Stated once, because two consumers must agree on it *exactly*. `serialize_detail`
# uses these to build the public lists; AGENT-02 uses them to walk the matching
# ORM rows and attach each fact's evidence. Attaching provenance by zipping two
# lists is only sound while both are built from one definition of "exposed, in
# this order" — so that definition is a function, not a repeated comprehension.
# ---------------------------------------------------------------------------


def current_pricing_offers(robot: Robot) -> list[PricingOffer]:
    """Pricing offers a detail response exposes: current ones, in relation order."""
    return [p for p in robot.pricing_offers if p.is_current]


def current_availability_offers(robot: Robot) -> list[AvailabilityOffer]:
    """Availability offers a detail response exposes: current ones, in order."""
    return [a for a in robot.availability_offers if a.is_current]


def recorded_deployments(robot: Robot) -> list[Deployment]:
    """Deployments a detail response exposes. No currency filter exists here —
    a deployment is a historical fact, not a standing offer."""
    return list(robot.deployments)


def detail_subject_ids(robot: Robot) -> set[uuid.UUID]:
    """Every subject whose evidence a detail response may cite.

    Deliberately wider than the exposed facts: it spans *all* loaded offers, not
    just current ones, so the evidence query is a single round trip over the
    whole detail. Evidence for a non-exposed offer is simply never looked up
    again — nothing attaches provenance to a fact the response does not carry.
    """
    return (
        {robot.id}
        | {p.id for p in robot.pricing_offers}
        | {a.id for a in robot.availability_offers}
        | {d.id for d in robot.deployments}
    )


def serialize_detail(
    session: Session,
    robot: Robot,
    *,
    evidence_rows: dict[tuple[str, uuid.UUID], EvidenceSource] | None = None,
) -> RobotDetail:
    """The governed detail projection.

    `evidence_rows` lets a caller that has *already* run the canonical selection
    hand those rows in, so `get_robot` selects once and serializes once instead
    of running best-evidence twice over the same subjects. Omitted (the HTTP
    path), behaviour is exactly as before: this function selects for itself.
    Either way the rows come from `load_evidence_rows`, so there is one rule.
    """
    if evidence_rows is None:
        evidence_rows = load_evidence_rows(session, detail_subject_ids(robot))
    ev = {key: evidence_read(row) for key, row in evidence_rows.items()}

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
        for p in current_pricing_offers(robot)
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
        for a in current_availability_offers(robot)
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
        for d in recorded_deployments(robot)
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
        for img in _eligible_images(robot)
    ]

    return RobotDetail(
        id=str(robot.id),
        slug=robot.slug,
        name=robot.name,
        model_code=robot.model_code,
        manufacturer=ManufacturerRef(
            slug=robot.manufacturer.slug,
            name=robot.manufacturer.name,
            country=_country_code(robot.manufacturer),
        ),
        commercial_status=robot.commercial_status,
        summary=robot.summary,
        description=robot.description,
        hero_image_url=_governed_hero_image_url(robot),
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
