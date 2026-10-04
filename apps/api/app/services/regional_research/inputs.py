"""Plain, immutable inputs for the regional availability read model (ADR-027).

No ORM, DB, clock or network dependency. A loader materializes the canonical
catalogue into these; `readmodel.py` is a pure function over them. The snapshot
date is an input, never read from a clock, so identical input gives identical
output (AGENTS.md rule 8).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class RegionNode:
    code: str
    name: str
    parent_code: str | None


@dataclass(frozen=True)
class EvidenceRow:
    source_url: str
    confidence: str          # LOW | MEDIUM | HIGH | VERIFIED
    observed_at: date
    verified_at: date | None = None


@dataclass(frozen=True)
class OfferRow:
    """An availability_offer. `region_code` None means region-unresolved."""

    provider_slug: str | None
    provider_type: str | None
    region_code: str | None
    transaction_type: str    # PURCHASE | RENTAL | LEASE | RAAS | ...
    # AVAILABLE | LIMITED | PREORDER | WAITLIST | ON_REQUEST | NOT_AVAILABLE | DISCONTINUED
    availability_status: str
    is_current: bool
    evidence: tuple[EvidenceRow, ...]


@dataclass(frozen=True)
class PriceRow:
    provider_slug: str | None
    region_code: str | None
    transaction_type: str
    # PUBLIC | FROM | RANGE | ESTIMATED | MANUFACTURER_ESTIMATE | QUOTE_ONLY
    price_type: str
    currency: str | None
    price: float | None
    price_min: float | None
    price_max: float | None
    billing_period: str
    price_basis: str | None
    is_current: bool
    evidence: tuple[EvidenceRow, ...]


@dataclass(frozen=True)
class DeploymentRow:
    """A deployment: evidence of real-world use, NOT of purchasability."""

    region_code: str | None
    customer_name: str | None
    provider_slug: str | None
    transaction_type: str | None
    unit_count: int | None
    started_on: date | None
    status: str | None
    evidence: tuple[EvidenceRow, ...]


@dataclass(frozen=True)
class RobotRow:
    slug: str
    name: str
    manufacturer_slug: str
    manufacturer_name: str
    is_published: bool
    commercial_status: str
    offers: tuple[OfferRow, ...] = ()
    prices: tuple[PriceRow, ...] = ()
    deployments: tuple[DeploymentRow, ...] = ()


@dataclass(frozen=True)
class RegionalSnapshot:
    snapshot_date: date
    regions: tuple[RegionNode, ...]
    robots: tuple[RobotRow, ...]
