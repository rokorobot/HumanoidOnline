"""Shared read-schema fragments (Pydantic v2).

Numeric display fields are typed as ``float`` and cast at construction so JSON
renders plain numbers. Unknown values are ``null`` — never 0/false/"" (API
contract §conventions; AGENTS.md rule 6).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ManufacturerRef(BaseModel):
    slug: str
    name: str
    country: str | None = None


class EvidenceRead(BaseModel):
    """Provenance for a commercial fact (AGENTS.md rules 7 & 17)."""

    source_type: str
    confidence: str
    # observed_at is TIMESTAMPTZ NOT NULL — the catalogue always records when a
    # fact was observed, so it is always present (unlike published/verified).
    observed_at: datetime
    verified_at: datetime | None = None
    published_at: date | None = None
    source_url: str | None = None


class PriceDisplay(BaseModel):
    """Resolved headline price. `null` (the whole object) means no pricing rows —
    i.e. unknown price. A QUOTE_ONLY row is a *known* fact with `amount=null` and
    must not be collapsed with unknown (API contract §1).

    Everything here comes from ONE offer row. The amount, its denomination, the
    seller, the region that offer is scoped to, the basis it is quoted on and its
    order status travel together, because separating them is how a reader ends up
    reading one supplier's number under another supplier's terms. There is no
    cross-offer minimum here and no currency conversion anywhere.
    """

    type: str
    amount: float | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    currency: str | None = None
    billing_period: str | None = None
    #: Which offer this is, and on what terms — never a blend of several.
    provider: str | None = None
    region: str | None = None
    price_basis: str | None = None
    order_status_note: str | None = None
    #: The configuration this amount was quoted for, when the offer is scoped to
    #: one. NULL means the offer is variant-agnostic and speaks for the record.
    #: Present so a variant-scoped headline can never be read as the price of
    #: every configuration.
    variant: str | None = None
    #: NULL = the edition match was never assessed (and is never shown as
    #: confirmed). FALSE offers are excluded from headline selection upstream.
    edition_confirmed: bool | None = None
