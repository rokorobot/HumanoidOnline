"""AGENT-02 public projections — the boundary where internal identity stops.

The governed read layer (`services/reads.py`) serializes for the website and the
public HTTP API, and its `RobotListItem` carries `id` — the row's PostgreSQL
UUID. That is legitimate there and stays. It is **not** legitimate on an agent
surface: `docs/20` §8 makes the slug the canonical external identifier and states
that internal database UUIDs are never the public contract, §20 forbids database
selectors outright, and §21.10 requires that no raw database identifier appear in
any request or response.

So this module is a projection, not a second serializer. It consumes the governed
`RobotListItem` and reshapes *identity* only — dropping the internal id, deriving
`canonical_url` from the slug. It never recomputes a robot fact: `price_display`,
`primary_image`, `available_modes` and the UNKNOWN-bearing spec fields are passed
through exactly as the governed read produced them, so pricing semantics
(`docs/20` §10), MEDIA-01 image eligibility and `null`-means-UNKNOWN (§9.1) can
only ever have one implementation.

`PriceDisplay` and `RobotImagePrimary` are reused deliberately: they are value
objects carrying no identifiers, and re-declaring them here would fork the
pricing and image display rules — the opposite of the point.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, datetime

from pydantic import BaseModel

from app.models.evidence import EvidenceSource
from app.models.robot import Robot
from app.schemas.common import PriceDisplay
from app.schemas.robot import (
    CapabilityRead,
    ExtendedSpec,
    RobotDetail,
    RobotImagePrimary,
    RobotImageRead,
    RobotListItem,
    SpecsBlock,
    StatusHistoryEntry,
    UseCaseFitRead,
    VariantRead,
)
from app.services import reads

#: The wire identifier of the ratified contract (`docs/20` §18). One constant for
#: the whole tool surface: two tools reporting different versions of the same
#: contract would be a lie about which semantics answered the call.
CONTRACT_VERSION = "agent-tools/0.1"

#: The citable address of a robot (`docs/20` §8). Relative because this is the
#: transport-independent semantic layer: the absolute origin belongs to whichever
#: binding serves it, and this service has no governed origin helper to borrow.
CANONICAL_ROBOT_PATH = "/robots/{slug}"


def canonical_robot_url(slug: str) -> str:
    """`/robots/{slug}` — derived from the canonical slug and nothing else.

    Never from a database id, never from a caller-supplied value, and with no
    alternate aliases: §8 has exactly one citable address per robot.
    """
    return CANONICAL_ROBOT_PATH.format(slug=slug)


class AgentManufacturerRef(BaseModel):
    """A manufacturer as an agent may see it: slug + name, no row id."""

    slug: str
    name: str


class AgentRobotListItem(BaseModel):
    """The `docs/20` §5 list projection, exactly.

    Mandatory: `slug`, `name`, `commercial_status`, `canonical_url`,
    `manufacturer`, `deployment_count`, `updated_at`. UNKNOWN-capable (present as
    `null`, key never omitted): `payload_kg`, `height_cm`, `mobility`.
    Conditional: `price_display`, `available_modes`, `primary_image`.

    Fields the HTTP schema also carries — `id`, `summary`, `hero_image_url` — are
    deliberately absent. `id` is forbidden (§8/§20); the other two are simply not
    in the ratified projection, and adding output fields is an additive decision
    for the contract to take, not for this layer to assume.
    """

    slug: str
    name: str
    commercial_status: str
    canonical_url: str
    manufacturer: AgentManufacturerRef
    payload_kg: float | None = None
    height_cm: float | None = None
    mobility: str | None = None
    price_display: PriceDisplay | None = None
    available_modes: list[str]
    deployment_count: int
    primary_image: RobotImagePrimary | None = None
    updated_at: datetime


def project_list_item(item: RobotListItem) -> AgentRobotListItem:
    """Project one governed list read onto the agent surface.

    Identity is reshaped; facts are forwarded untouched.
    """
    return AgentRobotListItem(
        slug=item.slug,
        name=item.name,
        commercial_status=item.commercial_status,
        canonical_url=canonical_robot_url(item.slug),
        manufacturer=AgentManufacturerRef(
            slug=item.manufacturer.slug, name=item.manufacturer.name
        ),
        payload_kg=item.payload_kg,
        height_cm=item.height_cm,
        mobility=item.mobility,
        price_display=item.price_display,
        available_modes=item.available_modes,
        deployment_count=item.deployment_count,
        primary_image=item.primary_image,
        updated_at=item.updated_at,
    )


# ---------------------------------------------------------------------------
# AGENT-02.2c — full detail (`docs/20` §6)
# ---------------------------------------------------------------------------


class AgentEvidence(BaseModel):
    """Provenance as an agent sees it (`docs/20` §9.5).

    The governed metadata of §7, plus the two things an agent needs and the HTTP
    reader does not: `evidence_ref`, the opaque address of the *selected row*
    (§7.1), and `subject_type`, what the evidence is about.

    Absent by contract: `evidence_source.id` and `subject_id` (§8, §20). The ref
    already addresses the row — exposing the raw identifier beside it would hand
    back the very selector the ref exists to replace.

    One shape everywhere. Pricing offers, availability offers, deployments and
    `commercial_status_evidence` all carry this object, so an agent learns to
    read provenance once.
    """

    source_type: str
    confidence: str
    observed_at: datetime
    verified_at: datetime | None = None
    published_at: date | None = None
    source_url: str | None = None
    subject_type: str
    evidence_ref: str


class AgentPricingOffer(BaseModel):
    """`PricingOfferRead` with agent provenance. Pricing semantics (§10) belong to
    the governed read — nothing here recomputes an amount, a type or a currency."""

    transaction_type: str
    price_type: str
    price: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    currency: str
    billing_period: str
    region: str | None = None
    provider: str | None = None
    evidence: AgentEvidence | None = None


class AgentAvailabilityOffer(BaseModel):
    """`AvailabilityOfferRead` with agent provenance (§11)."""

    transaction_type: str
    availability_status: str
    region: str | None = None
    provider: str | None = None
    available_from: date | None = None
    lead_time_days: int | None = None
    evidence: AgentEvidence | None = None


class AgentDeployment(BaseModel):
    """`DeploymentRead` with agent provenance."""

    customer_name: str | None = None
    region: str | None = None
    use_case: str | None = None
    transaction_type: str | None = None
    unit_count: int | None = None
    contract_value: float | None = None
    summary: str | None = None
    evidence: AgentEvidence | None = None


class AgentRobotDetail(BaseModel):
    """The `docs/20` §6 detail projection.

    Identity is reshaped — no `id`, manufacturer by slug/name, `canonical_url`
    derived from the slug — and evidence is replaced by the agent object of §9.5.
    Everything else is the governed detail verbatim.

    `SpecsBlock`, `ExtendedSpec`, `CapabilityRead`, `VariantRead`,
    `UseCaseFitRead`, `RobotImageRead` and `StatusHistoryEntry` are reused rather
    than redeclared: they carry no identifier and no evidence, so a parallel
    definition would fork MEDIA-01 eligibility and the UNKNOWN-is-null rule (§9.1)
    for no gain. Only the three offer/deployment schemas needed an agent
    counterpart, and only because their `evidence` field changes type.

    `commercial_status` stays a plain enum value with its provenance in the
    sibling `commercial_status_evidence` (§6). Turning the status itself into an
    object would change how every consumer reads a mandatory field.
    """

    slug: str
    name: str
    model_code: str | None = None
    manufacturer: AgentManufacturerRef
    canonical_url: str
    commercial_status: str
    commercial_status_evidence: AgentEvidence | None = None
    summary: str | None = None
    description: str | None = None
    hero_image_url: str | None = None
    announced_year: int | None = None
    status_history: list[StatusHistoryEntry]
    specs: SpecsBlock
    extended_specs: list[ExtendedSpec]
    capabilities: list[CapabilityRead]
    variants: list[VariantRead]
    use_case_fits: list[UseCaseFitRead]
    pricing_offers: list[AgentPricingOffer]
    availability_offers: list[AgentAvailabilityOffer]
    deployments: list[AgentDeployment]
    images: list[RobotImageRead] = []


def _agent_evidence(
    row: EvidenceSource | None, issue_ref: Callable[[EvidenceSource], str]
) -> AgentEvidence | None:
    """One selected evidence row as the agent object, or `null`.

    `None` in, `None` out — a fact with no selected evidence carries
    `evidence: null` and no ref. A reference is **never** synthesized to make an
    unevidenced fact look sourced (§9.5): `commercial_status = UNKNOWN` requires
    no evidence at all (`docs/05` G2.1), and filling the field for symmetry would
    invent provenance the catalogue does not have.
    """
    if row is None:
        return None
    return AgentEvidence(
        source_type=row.source_type,
        confidence=row.confidence,
        observed_at=row.observed_at,
        verified_at=row.verified_at,
        published_at=row.published_at,
        source_url=row.source_url,
        subject_type=row.subject_type,
        evidence_ref=issue_ref(row),
    )


def _aligned(public: list, rows: list, what: str) -> list:
    """Pair each exposed public fact with the ORM row it was built from.

    Both lists come from the *same* `reads` selector (`current_pricing_offers`
    and its siblings), so they correspond element-wise by construction. The
    length check is not paranoia about today's code but a tripwire for
    tomorrow's: if the governed serializer ever changes which offers it exposes,
    misaligned lists would silently attach one offer's provenance to another's
    price, and a confidently mis-sourced number is worse than a missing one.
    """
    if len(public) != len(rows):  # pragma: no cover — structural guard
        raise RuntimeError(f"{what}: governed detail and ORM rows are misaligned")
    return list(zip(public, rows, strict=True))


def project_detail(
    detail: RobotDetail,
    robot: Robot,
    evidence_rows: dict[tuple[str, uuid.UUID], EvidenceSource],
    issue_ref: Callable[[EvidenceSource], str],
) -> AgentRobotDetail:
    """Project one governed detail read onto the agent surface (`docs/20` §6).

    Facts come from `detail` — the same object the website renders — and are
    forwarded untouched. `robot` and `evidence_rows` answer only *which* evidence
    row belongs to *which* fact, by internal subject identity rather than by
    matching public values: two offers may legitimately share a price, provider,
    region and timestamp, so value equality is not an identity.

    Those internal UUIDs stop here. Nothing below returns a key or value derived
    from a row id except the opaque `evidence_ref` itself (§8, §20, §21.10).
    """

    def ev(subject_type: str, subject_id: uuid.UUID) -> AgentEvidence | None:
        return _agent_evidence(evidence_rows.get((subject_type, subject_id)), issue_ref)

    pricing = [
        AgentPricingOffer(
            **offer.model_dump(exclude={"evidence"}),
            evidence=ev("PRICING_OFFER", row.id),
        )
        for offer, row in _aligned(
            detail.pricing_offers, reads.current_pricing_offers(robot), "pricing_offers"
        )
    ]
    availability = [
        AgentAvailabilityOffer(
            **offer.model_dump(exclude={"evidence"}),
            evidence=ev("AVAILABILITY_OFFER", row.id),
        )
        for offer, row in _aligned(
            detail.availability_offers,
            reads.current_availability_offers(robot),
            "availability_offers",
        )
    ]
    deployments = [
        AgentDeployment(
            **dep.model_dump(exclude={"evidence"}),
            evidence=ev("DEPLOYMENT", row.id),
        )
        for dep, row in _aligned(
            detail.deployments, reads.recorded_deployments(robot), "deployments"
        )
    ]

    return AgentRobotDetail(
        slug=detail.slug,
        name=detail.name,
        model_code=detail.model_code,
        manufacturer=AgentManufacturerRef(
            slug=detail.manufacturer.slug, name=detail.manufacturer.name
        ),
        canonical_url=canonical_robot_url(detail.slug),
        commercial_status=detail.commercial_status,
        commercial_status_evidence=ev("COMMERCIAL_STATUS", robot.id),
        summary=detail.summary,
        description=detail.description,
        hero_image_url=detail.hero_image_url,
        announced_year=detail.announced_year,
        status_history=detail.status_history,
        specs=detail.specs,
        extended_specs=detail.extended_specs,
        capabilities=detail.capabilities,
        variants=detail.variants,
        use_case_fits=detail.use_case_fits,
        pricing_offers=pricing,
        availability_offers=availability,
        deployments=deployments,
        images=detail.images,
    )
