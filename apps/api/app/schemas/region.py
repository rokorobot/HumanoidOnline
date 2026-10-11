"""Pydantic v2 read model for `region` (foundation example of ORM -> schema).

Not exposed via any endpoint in WS1 — it demonstrates the `from_attributes`
pattern that WS2 knowledge-model endpoints will follow.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RegionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    type: str
    code: str
    name: str
    iso_country: str | None
    created_at: datetime


class RegionListItem(BaseModel):
    """Compact canonical region for pickers (e.g. the buyer-intent Country step).
    `code` is the value submitted back to POST /api/buyer-requirements."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    type: str
    iso_country: str | None = None


class RegionScope(BaseModel):
    """Region codes in scope for one requested region, by the two governed questions.

    `applicable` answers `region` (eligibility): the region itself, its ancestors
    and GLOBAL. `market` answers `offered_in` (discovery): the same plus the
    region's descendants, e.g. member countries of an economic zone. Both are the
    output of the canonical resolvers in `services/regions.py`, exposed so a
    client can annotate offers without re-deriving geography. An offer with no
    region recorded applies under both questions and is not a member of either list.
    """

    code: str
    applicable: list[str]
    market: list[str]
