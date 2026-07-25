"""Robot read schemas (API contract §1)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import EvidenceRead, ManufacturerRef, PriceDisplay


class RobotImagePrimary(BaseModel):
    """The single display-eligible primary image for a catalogue card (MEDIA-01).
    Same image truth as Robot Detail, through the same gate — just the compact
    fields a card needs. None -> the card shows the IMAGE_UNAVAILABLE treatment."""

    image_url: str
    source_name: str | None = None
    is_official: bool


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


class StatusHistoryEntry(BaseModel):
    status: str
    effective_at: datetime
    note: str | None = None


class SpecsBlock(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
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
    price_type: str
    price: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    currency: str
    billing_period: str
    region: str | None = None
    provider: str | None = None
    evidence: EvidenceRead | None = None


class AvailabilityOfferRead(BaseModel):
    transaction_type: str
    availability_status: str
    region: str | None = None
    provider: str | None = None
    available_from: date | None = None
    lead_time_days: int | None = None
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
    """A DISPLAY-ELIGIBLE verified image (MEDIA-01). The read path returns ONLY
    eligible images (identity VERIFIED + rights PERMITTED/ATTRIBUTION_REQUIRED),
    so the client cannot render an unverified or rights-uncleared image. When the
    list is empty the UI shows the explicit IMAGE_UNAVAILABLE state."""

    image_url: str
    image_type: str
    source_name: str | None = None
    source_url: str | None = None
    source_type: str
    is_official: bool
    is_primary: bool
    attribution: str | None = None


class RobotDetail(BaseModel):
    id: str
    slug: str
    name: str
    manufacturer: ManufacturerRef
    commercial_status: str
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
    pricing_offers: list[PricingOfferRead]
    availability_offers: list[AvailabilityOfferRead]
    deployments: list[DeploymentRead]
    # MEDIA-01: display-eligible verified images only, primary first. Empty -> the
    # UI renders IMAGE_UNAVAILABLE (never a generated/placeholder fill).
    images: list[RobotImageRead] = []


class CompareRow(BaseModel):
    group: str
    key: str
    label: str
    values: dict[str, float | bool | str | None]


class CompareResponse(BaseModel):
    robots: list[RobotDetail]
    rows: list[CompareRow]
