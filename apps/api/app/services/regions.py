"""Canonical region applicability — one resolver, not three.

Geography in this catalogue is hierarchical (`region.parent_id`) and an offer
attaches to exactly one scope. The question "does this offer apply to a buyer
in X?" therefore has one governed answer:

    the region itself + its ancestor regions + GLOBAL

plus region-agnostic (`NULL`) offers, which apply everywhere. `db/schema.sql`
states the same rule for price↔availability attachment ("exact region > parent >
GLOBAL/NULL") and `docs/03` restates it as frozen dictionary semantics.

Two copies of this walk already existed — `matching/repository.py` (keyed by
country code) and `leads/routing.py` (keyed by region id, whose docstring says it
"Mirrors the matching repository's country->applicable-regions walk"). This
module is the canonical implementation new consumers must use, so a third
interpretation is never written. Migrating those two existing consumers is
deliberately left as follow-up: they are covered by their own ratified tests, and
`test_region_applicability.py` pins this resolver's parity with both.

**GLOBAL is applicability, not identity.** A GLOBAL offer may satisfy a narrower
query, but callers must keep reporting its own region verbatim. Nothing here
rewrites an offer's region, and nothing here invents a region for an offer that
has none.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.region import Region

GLOBAL_CODE = "GLOBAL"


def _ancestors_of(session: Session, region_id: uuid.UUID) -> set[uuid.UUID]:
    """`region_id` plus every ancestor, walking `parent_id` to the root."""
    ids: set[uuid.UUID] = {region_id}
    parent = session.execute(
        select(Region.parent_id).where(Region.id == region_id)
    ).scalar_one_or_none()
    while parent is not None and parent not in ids:
        ids.add(parent)
        parent = session.execute(
            select(Region.parent_id).where(Region.id == parent)
        ).scalar_one_or_none()
    return ids


def applicable_region_ids(
    session: Session,
    *,
    code: str | None = None,
    region_id: uuid.UUID | None = None,
    require_type: str | None = None,
) -> set[uuid.UUID]:
    """Regions whose offers apply to a buyer located in the given region.

    Address the region either by `code` (any `region_type` — `search_robots`
    accepts `EU` and `DE` alike) or by `region_id`. `require_type` restricts the
    code lookup when a caller genuinely needs one (matching resolves a buyer's
    stated `COUNTRY`); it is None by default so an economic zone is a valid
    query scope.

    Returns an empty set when the code is unknown, so an unrecognised region
    matches nothing rather than silently widening to GLOBAL. GLOBAL itself is
    always included when the region resolves, because a worldwide offer applies
    to every narrower geography.
    """
    if (code is None) == (region_id is None):
        raise ValueError("exactly one of `code` or `region_id` is required")

    ids: set[uuid.UUID] = set()
    if region_id is not None:
        ids |= _ancestors_of(session, region_id)
    else:
        stmt = select(Region.id).where(Region.code == code)
        if require_type is not None:
            stmt = stmt.where(Region.type == require_type)
        resolved = session.execute(stmt).scalar_one_or_none()
        if resolved is None:
            # Unknown region: match nothing. Returning {GLOBAL} here would turn a
            # typo into a worldwide query.
            return set()
        ids |= _ancestors_of(session, resolved)

    global_id = session.execute(
        select(Region.id).where(Region.code == GLOBAL_CODE)
    ).scalar_one_or_none()
    if global_id is not None:
        ids.add(global_id)
    return ids
