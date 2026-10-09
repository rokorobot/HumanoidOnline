"""Robot read schemas (API contract §1)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

# AGENT-01 (docs/10): read schemas feed the machine projections (JSON-LD, sitemap).
# `updated_at` gives the sitemap a real `lastmod`. No new model — an existing
# canonical column surfaced on the governed read.
from app.schemas.common import EvidenceRead, ManufacturerRef, PriceDisplay


class RobotImagePrimary(BaseModel):
    """The single display-eligible primary image for a catalogue card (MEDIA-01).
    Same image truth as Robot Detail, through the same gate — just the compact
    fields a card needs. None -> the card shows the IMAGE_UNAVAILABLE treatment."""

    image_url: str
    source_name: str | None = None
    is_official: bool


class ProjectionEvidenceRead(BaseModel):
    """The registered (spec key, token) pair that established a projected value."""
    spec_key: str
    token: str


class SourceFactRead(BaseModel):
    """A verbatim accepted fact kept visible beside a projected value (never replaced by it)."""
    key: str
    label: str
    value: str


class ResolvedVariantValueRead(BaseModel):
    slug: str
    name: str
    #: None = unknown for this configuration (never a fabricated false).
    value: bool | None = None
    evidence: list[ProjectionEvidenceRead] = []
    source_facts: list[SourceFactRead] = []


class ResolvedFactRead(BaseModel):
    """G4 (DR-G4): one property resolved by the single shared resolver
    (`services/fact_resolution.py`). The six states are distinct and never flattened to a
    nullable boolean. `value` is set only for PRODUCT_VALUE and UNIFORM_VARIANTS.
    """
    property: str
    state: str
    value: bool | None = None
    product_value: bool | None = None
    product_source: str | None = None
    variants: list[ResolvedVariantValueRead] = []
    registry_version: str
    detail: str | None = None


class ScopeNoteRead(BaseModel):
    """Why a robot matched a positive capability filter on only SOME configurations."""
    property: str
    label: str
    configurations: list[str]


class RobotListItem(BaseModel):
    id: str
    slug: str
    name: str
    manufacturer: ManufacturerRef
    summary: str | None = None
    hero_image_url: str | None = None
    # MEDIA-01 catalogue-card image (display-eligible primary, or null -> unavailable).
    primary_image: RobotImagePrimary | None = None
    commercial_status: str
    payload_kg: float | None = None
    height_cm: float | None = None
    mobility: str | None = None
    price_display: PriceDisplay | None = None
    available_modes: list[str]
    deployment_count: int
    updated_at: datetime  # sitemap lastmod (AGENT-01)
    #: Present only when a positive capability filter matched on some configurations
    #: (ANY-VARIANT, DR-G4). Empty otherwise.
    scope_notes: list[ScopeNoteRead] = []


class StatusHistoryEntry(BaseModel):
    status: str
    effective_at: datetime
    note: str | None = None


class SpecsBlock(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    #: Horizontal extent, in the ORM's own order and naming. Two distinct
    #: measurements: span is fingertip-to-fingertip, reach is one arm from its
    #: shoulder. Neither is derived from the other, so they are reported
    #: separately and a missing one stays null rather than borrowing the other.
    arm_span_cm: float | None = None
    reach_cm: float | None = None
    payload_kg: float | None = None
    walk_speed_ms: float | None = None
    runtime_minutes: int | None = None
    battery_wh: float | None = None
    mobility: str | None = None
    degrees_of_freedom: int | None = None
    hand_type: str | None = None
    hand_dof: int | None = None
    autonomy: str | None = None
    has_manipulation: bool | None = None
    has_teleoperation: bool | None = None
    has_vision: bool | None = None
    has_language_ui: bool | None = None
    has_sdk: bool | None = None
    has_api: bool | None = None
    ros_support: bool | None = None
    developer_edition: bool | None = None
    simulation_support: bool | None = None


class ExtendedSpec(BaseModel):
    key: str
    label: str
    value: float | bool | str | None = None
    unit: str | None = None
    category: str
    #: Attribution travels WITH the value. A long-tail spec carries no
    #: evidence_source row (it is descriptive, not a commercial fact), so if the
    #: source did not come along, the value would arrive unattributable.
    source_label: str | None = None
    source_url: str | None = None
    #: MANUFACTURER | MANUFACTURER_DOC | COMPONENT_MANUFACTURER | RESELLER_CLAIM —
    #: a distributor's claim is never presented as the maker's own statement.
    source_kind: str | None = None
    #: THIS_EDITION | PRODUCT_LINE | PLATFORM. A figure stated for a family must
    #: not read as confirmation for one configuration.
    edition_scope: str | None = None
    observed_at: date | None = None
    #: Set when the value is scoped to ONE variant of this robot (e.g. Standard vs Pro);
    #: None means a product-level spec.
    variant_slug: str | None = None
    #: Display name of that variant (e.g. "Pro"); None for a product-level spec.
    variant: str | None = None


class SpecCaveat(BaseModel):
    """Why a spec is UNKNOWN, or which sources conflict. Attached to a field name
    so the UI can mark that row; it explains a NULL and never fills one."""

    field: str
    text: str


class CapabilityRead(BaseModel):
    slug: str
    name: str
    supported: bool
    detail: str | None = None


class VariantRead(BaseModel):
    slug: str
    name: str
    is_developer: bool


class UseCaseFitRead(BaseModel):
    use_case: str
    fit_score: float | None = None
    commercial_readiness: str | None = None
    limitations: str | None = None


class PricingOfferRead(BaseModel):
    transaction_type: str
    #: The configuration (variant) this offer is scoped to, or None for the whole robot.
    #: A variant-scoped amount is never reported as though it applied to every edition.
    variant: str | None = None
    variant_slug: str | None = None
    price_type: str
    price: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    currency: str
    billing_period: str
    region: str | None = None
    provider: str | None = None
    provider_name: str | None = None
    #: Public offer detail, one fact per field: what the amount includes, what
    #: shipping costs, what is in the box, what THIS seller warrants, and whether
    #: it can be ordered right now.
    price_basis: str | None = None
    shipping_terms: str | None = None
    package_contents: str | None = None
    warranty_terms: str | None = None
    order_status_note: str | None = None
    #: Tri-state. NULL = not assessed — never rendered as "confirmed". FALSE = the
    #: listing's own specification conflicts with this record, so it is shown as a
    #: qualified listing and excluded from unqualified price selection.
    edition_confirmed: bool | None = None
    edition_note: str | None = None
    #: Condition of the unit priced: NEW, USED, OPEN_BOX or REFURBISHED. A non-NEW offer is
    #: its own offer and never the new unit's price.
    condition: str = "NEW"
    evidence: EvidenceRead | None = None


class AvailabilityOfferRead(BaseModel):
    transaction_type: str
    #: The configuration (variant) this availability is scoped to, or None for the whole robot.
    variant: str | None = None
    variant_slug: str | None = None
    availability_status: str
    region: str | None = None
    provider: str | None = None
    provider_name: str | None = None
    available_from: date | None = None
    lead_time_days: int | None = None
    #: The seller's own sentence, and its delivery estimate with the geography it
    #: was stated for. A domestic estimate is never widened to a region.
    seller_wording: str | None = None
    delivery_estimate_label: str | None = None
    #: Condition of the unit this availability is for (a used unit's stock is not the new unit's).
    condition: str = "NEW"
    evidence: EvidenceRead | None = None


class DeploymentRead(BaseModel):
    customer_name: str | None = None
    region: str | None = None
    use_case: str | None = None
    transaction_type: str | None = None
    unit_count: int | None = None
    contract_value: float | None = None
    summary: str | None = None
    evidence: EvidenceRead | None = None


class RobotImageRead(BaseModel):
    """A DISPLAY-ELIGIBLE image (MEDIA-01). The read path returns ONLY eligible
    images, so the client cannot render an unverified or rights-uncleared one.
    When the list is empty the UI shows the explicit IMAGE_UNAVAILABLE state."""

    image_url: str
    image_type: str
    source_name: str | None = None
    source_url: str | None = None
    source_type: str
    is_official: bool
    is_primary: bool
    attribution: str | None = None
    #: TRUE when the asset depicts the product line/chassis rather than this exact
    #: edition. Such an image is eligible only WITH `representative_note`, and the
    #: caption must cross this boundary: an unlabelled stand-in reads as a claim
    #: about the exact edition, which is precisely what the designation prevents.
    is_representative: bool = False
    representative_note: str | None = None


class RobotDetail(BaseModel):
    id: str
    slug: str
    name: str
    #: Manufacturer's own designation for this model. A canonical `robot` column
    #: that reached neither read path until AGENT-02 required it (`docs/20` §6).
    #: Additive under §18, and served here — through the SHARED detail read — so
    #: the website and the agent surface can only ever report one value.
    model_code: str | None = None
    manufacturer: ManufacturerRef
    commercial_status: str
    summary: str | None = None
    description: str | None = None
    hero_image_url: str | None = None
    announced_year: int | None = None
    #: The manufacturer's own page for this model (identity/provenance). Carried
    #: by the catalogue all along; it had no column to land in until 0011.
    official_url: str | None = None
    status_history: list[StatusHistoryEntry]
    specs: SpecsBlock
    #: Per-field explanations of UNKNOWNs and conflicts, keyed by spec field.
    spec_caveats: list[SpecCaveat] = []
    extended_specs: list[ExtendedSpec]
    capabilities: list[CapabilityRead]
    variants: list[VariantRead]
    use_case_fits: list[UseCaseFitRead]
    pricing_offers: list[PricingOfferRead]
    availability_offers: list[AvailabilityOfferRead]
    deployments: list[DeploymentRead]
    # MEDIA-01: display-eligible verified images only, primary first. Empty -> the
    # UI renders IMAGE_UNAVAILABLE (never a generated/placeholder fill).
    images: list[RobotImageRead] = []
    #: G4 scoped resolution of the registered capability properties (additive).
    resolved_facts: list[ResolvedFactRead] = []


class CompareRow(BaseModel):
    group: str
    key: str
    label: str
    values: dict[str, float | bool | str | None]
    #: G4: the scoped resolution per robot slug for the registered properties, so a PARTIAL or
    #: VARIES state is never collapsed to a plain unknown. `values` keeps the resolved scalar
    #: only where the state is PRODUCT_VALUE / UNIFORM_VARIANTS.
    resolved: dict[str, ResolvedFactRead] | None = None


class CompareResponse(BaseModel):
    robots: list[RobotDetail]
    rows: list[CompareRow]
