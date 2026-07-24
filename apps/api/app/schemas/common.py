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
    must not be collapsed with unknown (API contract §1)."""

    type: str
    amount: float | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    currency: str | None = None
    billing_period: str | None = None
