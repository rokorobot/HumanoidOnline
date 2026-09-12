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
    SpecCaveat,
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


def _offer_market_rank(offer: PricingOffer, market_rank: dict[str | None, int]) -> int | None:
    """This offer's place in the active market, or None if it is outside it."""
    code = offer.region.code if offer.region else None
    return market_rank.get(code)


#: Seller preference. 0 = the manufacturer selling its own robot, 1 = anyone else.
SELLER_MANUFACTURER_DIRECT = 0
SELLER_OTHER = 1


def _seller_rank(offer: PricingOffer, robot: Robot) -> int:
    """Is this offer manufacturer-direct FOR THIS ROBOT?

    Decided by two explicit governed columns — `provider.type` (the
    `provider_type` enum) and `provider.manufacturer_id` — never by reading the
    seller's name. Both halves are required: `type = 'OEM'` alone says the
    provider is somebody's factory outlet, not that it is *this* robot's, and a
    manufacturer link alone does not make a distributor direct. An OEM provider
    with no manufacturer link is therefore NOT treated as direct; it is
    unproven, and unproven must not outrank proven.

    Preference is not a claim that the OEM is cheaper. It is a claim about which
    price is the *right headline*: the manufacturer's own listing for its own
    product is the canonical commercial fact, and a reseller's markup is a fact
    about the reseller.
    """
    provider = offer.provider
    if provider is None:
        return SELLER_OTHER
    if provider.type == "OEM" and provider.manufacturer_id == robot.manufacturer_id:
        return SELLER_MANUFACTURER_DIRECT
    return SELLER_OTHER


#: Configuration relevance. 0 = variant-agnostic (`variant_id` NULL), which
#: speaks for the record itself. 1 = scoped to one configuration.
CONFIG_RECORD_LEVEL = 0
CONFIG_VARIANT_SCOPED = 1


def _config_rank(offer: PricingOffer) -> int:
    """How well does this offer represent the ROBOT-level record?

    `variant_id` NULL is variant-**agnostic** in the frozen semantics of
    `db/schema.sql` — it applies to any configuration — so it always represents
    the record better than a price attached to one configuration.

    A variant-scoped offer is nonetheless a **representative fallback**: when a
    record has no eligible variant-agnostic price, the seeded catalogue's own
    modelling shows why refusing one is wrong — `unitree-g1`'s only prices are
    scoped to its `g1` and `g1-edu` variants, and excluding them outright
    reported a robot with a published list price as having no price at all.

    This ranking is strictly about which offer represents the record on a card.
    It does NOT touch the frozen price↔availability matching rule (a
    variant-specific price still never attaches to a different variant's or a
    robot-level availability offer), and it infers nothing from `is_developer`.
    Whichever offer wins carries its variant identity into `PriceDisplay`, so a
    scoped amount is never presented as the price of every configuration.
    """
    return CONFIG_RECORD_LEVEL if offer.variant_id is None else CONFIG_VARIANT_SCOPED


#: Edition relevance, the real comparability signal (`pricing_offer.edition_confirmed`,
#: migration 0011). TRUE = this listing was checked against the manufacturer's
#: specification for this record; NULL = never assessed. FALSE is excluded earlier
#: and never reaches this ranking — absence of assessment must not read as
#: verification, so a confirmed listing is preferred over an unassessed one.
EDITION_CONFIRMED = 0
EDITION_UNASSESSED = 1


def _edition_rank(offer: PricingOffer) -> int:
    return EDITION_CONFIRMED if offer.edition_confirmed is True else EDITION_UNASSESSED


def price_display_for(
    robot: Robot, *, market_rank: dict[str | None, int] | None = None
) -> PriceDisplay | None:
    """The headline price: ONE offer row, reported with its own terms.

    Everything the card shows — amount, currency, seller, region, price basis and
    order status — comes from the single offer selected here, so a number is
    never displayed under another seller's terms.

    The order of preference, highest first:

    1. **Eligibility.** Removed outright: retired offers (`is_current` false)
       and edition-excluded ones (`edition_confirmed` FALSE).
    2. **Transaction mode, then price concreteness** — a purchase before a
       developer price, a published figure before an estimate.
    3. **Market applicability**, when `offered_in` is active: offers outside the
       market are dropped rather than ranked (an offer in an unrelated market is
       not a worse answer, it is not an answer), and the rest are ordered exact
       region, wider region, member region, worldwide, region-agnostic.
    4. **Configuration relevance** (`_config_rank`) — a variant-agnostic offer,
       which speaks for the record, before one scoped to a single
       configuration. The scoped offer is a *representative fallback*: it wins
       only when no eligible variant-agnostic price exists, and it carries its
       variant identity into the result so it is never read as the price of
       every configuration.
    5. **Edition relevance to THIS record** (`_edition_rank`) — a listing
       confirmed against the manufacturer's specification before one never
       assessed. Comparability is settled BEFORE seller preference, so an offer
       can never win on who sells it while describing something else.
    6. **Manufacturer-direct before reseller** (`_seller_rank`) — the business
       preference, decided from governed columns, not seller names, and only
       among candidates already established as comparable.
    7. **Amount, inside one comparable group only.** `price` decides solely
       between offers sharing a currency AND a price basis. Across groups there
       is no comparison at all: `services/pricing.py` states the rule this
       obeys — with no FX and no tax normalisation, a differently-denominated
       price is *incomparable*, which is a different fact from *expensive*.
    8. **Documented arbitrary tie-break** — provider slug, region code,
       currency, basis, alphabetically. This exists only so repeated imports
       cannot reorder equals. It expresses NO preference: it does not mean USD
       beats EUR or that a pre-tax basis is better, and it must never be read as
       one.

    **Stability.** Every key is a durable attribute. `updated_at` is rewritten
    and offer UUIDs are regenerated by every import, so neither may participate:
    either would change the headline for no reason at all.
    """
    offers = [
        p for p in robot.pricing_offers
        if p.is_current and p.edition_confirmed is not False
    ]
    if market_rank is not None:
        offers = [p for p in offers if _offer_market_rank(p, market_rank) is not None]
    if not offers:
        return None  # unknown price — no rows (or none inside this market)

    def preference(p: PricingOffer) -> tuple:
        """Everything decided on merit, before any amount is looked at."""
        return (
            _TXN_PREF.get(p.transaction_type, 9),
            _PRICE_TYPE_RANK.get(p.price_type, 9),
            _offer_market_rank(p, market_rank) if market_rank is not None else 0,
            _config_rank(p),
            _edition_rank(p),
            _seller_rank(p, robot),
        )

    def arbitrary(p: PricingOffer) -> tuple:
        """Deterministic, meaningless, and last. Never a preference."""
        return (
            p.provider.slug if p.provider else "~",
            p.region.code if p.region else "~",
            p.currency,
            p.price_basis or "",
        )

    best = min(preference(p) for p in offers)
    finalists = [p for p in offers if preference(p) == best]

    # The amount may break the remaining tie only when every finalist is quoted
    # in the same money on the same basis. Otherwise the amounts are genuinely
    # incomparable and are not consulted at all — ranking currencies to force an
    # answer would invent a preference this system does not have.
    groups = {(p.currency, p.price_basis or "") for p in finalists}
    if len(groups) == 1:
        p = min(
            finalists,
            key=lambda p: (
                float(p.price) if p.price is not None else float("inf"),
                arbitrary(p),
            ),
        )
    else:
        p = min(finalists, key=arbitrary)
    return PriceDisplay(
        type=p.price_type,
        amount=_f(p.price),
        amount_min=_f(p.price_min),
        amount_max=_f(p.price_max),
        currency=p.currency,
        billing_period=p.billing_period,
        provider=p.provider.slug if p.provider else None,
        region=p.region.code if p.region else None,
        price_basis=p.price_basis,
        order_status_note=p.order_status_note,
        edition_confirmed=p.edition_confirmed,
        # Provenance of the configuration, not a preference signal: present only
        # when the winning offer is scoped to one variant.
        variant=p.variant.name if p.variant is not None else None,
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
    robot: Robot,
    snapshot: dict[uuid.UUID, tuple[int, list[str]]],
    *,
    market_rank: dict[str | None, int] | None = None,
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
        price_display=price_display_for(robot, market_rank=market_rank),
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


# The one governed detail eager-load graph, factored out so load_detail and
# load_details (single vs batched) can never drift into two independently
# maintained option lists — the whole point of "one governed read" (`docs/20`
# §6) is broken if a batching call site has to remember to copy this by hand.
_DETAIL_LOAD_OPTIONS = (
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
        .options(*_DETAIL_LOAD_OPTIONS)
    )
    return session.execute(stmt).scalars().first()


def load_details(session: Session, slugs: list[str]) -> list[Robot]:
    """Batched sibling of `load_detail`: the identical governed eager-load
    graph (`_DETAIL_LOAD_OPTIONS`), for however many slugs the caller passes,
    as ONE query graph instead of one per slug — SQLAlchemy's `selectin`
    strategy already batches a relationship's children across however many
    parent rows a single `select` returns, so this is the same governed
    projection `load_detail` gives one robot, just invoked for a set instead
    of a loop (compare's multi-robot read is the motivating caller).

    A slug that doesn't resolve to a published robot is simply absent from the
    result, same as `load_detail` returning ``None`` for it. Row order is
    whatever the database returns, NOT necessarily `slugs` order — a caller
    that needs requested-order (compare does) reorders the result itself.
    """
    if not slugs:
        return []
    stmt = (
        select(Robot)
        .where(Robot.slug.in_(slugs), Robot.is_published.is_(True))
        .options(*_DETAIL_LOAD_OPTIONS)
    )
    return list(session.execute(stmt).scalars().all())


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
            # Attribution travels with the value: a long-tail spec has no
            # evidence_source row, so dropping these would leave a figure nobody
            # can trace and no way to tell a reseller's claim from the maker's.
            source_label=s.source_label,
            source_url=s.source_url,
            source_kind=s.source_kind,
            edition_scope=s.edition_scope,
            observed_at=s.observed_at,
        )
        for s in sorted(
            robot.specifications,
            key=lambda s: (s.definition.sort_order, s.definition.key),
        )
    ]
    caveats = [
        SpecCaveat(field=c["field"], text=c["text"])
        for c in (robot.spec_caveats or [])
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
            price_basis=p.price_basis,
            shipping_terms=p.shipping_terms,
            package_contents=p.package_contents,
            warranty_terms=p.warranty_terms,
            order_status_note=p.order_status_note,
            edition_confirmed=p.edition_confirmed,
            edition_note=p.edition_note,
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
            seller_wording=a.seller_wording,
            delivery_estimate_label=a.delivery_estimate_label,
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
        official_url=robot.official_url,
        status_history=status_history,
        specs=_specs_block(robot),
        spec_caveats=caveats,
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
