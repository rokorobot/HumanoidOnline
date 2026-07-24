"""Fully-materialized inputs/outputs for the pure matching engine (WS6).

These are plain dataclasses with NO ORM, DB, time or network dependency. The
repository layer (app/services/matching/repository.py) loads PostgreSQL into
these; `engine.py` is a pure function over them. Keeping the engine's inputs
concrete + immutable is what makes matching deterministic and unit-testable
without a database (frozen contract §7.5).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class OfferInput:
    """A current availability_offer, with geo-applicability pre-resolved by the
    loader (exact country / ancestor economic zone / GLOBAL / region-agnostic)."""

    transaction_type: str
    availability_status: str
    is_current: bool
    region_code: str | None
    geo_applicable: bool
    available_from: date | None = None


@dataclass(frozen=True)
class PriceInput:
    transaction_type: str
    price_type: str          # PUBLIC | FROM | ESTIMATED | QUOTE_ONLY | RANGE
    currency: str | None
    price: float | None
    price_min: float | None
    price_max: float | None
    billing_period: str      # ONE_TIME | HOURLY | ... | ANNUAL
    is_current: bool
    geo_applicable: bool


@dataclass(frozen=True)
class RobotInput:
    slug: str
    name: str
    manufacturer_name: str
    manufacturer_country: str | None
    commercial_status: str
    payload_kg: float | None
    has_manipulation: bool | None
    autonomy: str | None
    runtime_minutes: int | None
    has_sdk: bool | None
    ros_support: bool | None
    developer_edition: bool | None
    # fit_score for the requirement's use case (None = no fit row / unverified)
    use_case_fit: float | None
    offers: tuple[OfferInput, ...]
    prices: tuple[PriceInput, ...]
    deployment_count: int
    # freshest relevant commercial evidence verified_at, for tie-breaking
    freshest_verified_at: datetime | None = None


@dataclass(frozen=True)
class RequirementInput:
    use_case: str | None
    country: str | None
    payload_min_kg: float | None
    operating_hours_day: float | None
    manipulation_required: bool | None
    autonomy_required: str | None
    budget_currency: str | None
    budget_min: float | None
    budget_max: float | None
    required_by: date | None
    preferred_transaction: str   # UNKNOWN | RENT | BUY | LEASE | RAAS | FLEXIBLE


@dataclass(frozen=True)
class ScoredMatch:
    slug: str
    score: int
    rank: int
    category: str
    breakdown: dict[str, float]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class MatchOutcome:
    matches: tuple[ScoredMatch, ...]
    excluded_count: int
    no_match_explanation: str | None
