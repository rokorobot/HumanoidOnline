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


def _descendants_of(session: Session, region_id: uuid.UUID) -> set[uuid.UUID]:
    """`region_id` plus every region beneath it, walking `parent_id` downward."""
    ids: set[uuid.UUID] = {region_id}
    frontier = [region_id]
    while frontier:
        children = session.execute(
            select(Region.id).where(Region.parent_id.in_(frontier))
        ).scalars().all()
        new = [c for c in children if c not in ids]
        ids.update(new)
        frontier = new
    return ids


def discovery_region_ids(session: Session, *, code: str) -> set[uuid.UUID]:
    """Regions whose offers make a robot DISCOVERABLE in a market (`docs/20` §12.1).

    Deliberately a different question from `applicable_region_ids`, and kept in a
    different function so the two can never be confused at a call site:

        applicability / eligibility  = the region + its ANCESTORS + GLOBAL
        discovery / market browsing  = the region + ancestors + DESCENDANTS + GLOBAL

    The descendants are the whole point. A buyer browsing the EU market should
    find a robot a German supplier lists, because that listing is real and
    inspectable — but including it says only that such an offer exists. It is not
    evidence of delivery to any particular country, and this function is never
    used for eligibility, matching or lead routing, which keep the ancestor rule.

    Each offer still reports its own region verbatim; nothing here relabels a DE
    offer as EU. An unknown code returns the empty set, so a typo matches nothing
    rather than widening to everything.
    """
    resolved = session.execute(
        select(Region.id).where(Region.code == code)
    ).scalar_one_or_none()
    if resolved is None:
        return set()
    ids = _ancestors_of(session, resolved) | _descendants_of(session, resolved)
    global_id = session.execute(
        select(Region.id).where(Region.code == GLOBAL_CODE)
    ).scalar_one_or_none()
    if global_id is not None:
        ids.add(global_id)
    return ids


#: Precedence of an offer's own scope inside an active market, used to choose a
#: headline offer. Exact first, then a wider region containing it, then a narrower
#: region inside the market, then worldwide, then region-agnostic.
MARKET_RANK_EXACT = 0
MARKET_RANK_ANCESTOR = 1
MARKET_RANK_DESCENDANT = 2
MARKET_RANK_GLOBAL = 3
MARKET_RANK_AGNOSTIC = 4


def discovery_market_rank(session: Session, *, code: str) -> dict[str | None, int]:
    """Region code -> precedence within the market `code`, for headline selection.

    The keys are exactly the regions this market can show (plus `None` for
    region-agnostic offers), so a caller can both *filter* an offer out of the
    market and *rank* the ones inside it without a second interpretation of
    geography. An empty mapping means the code resolved to nothing.
    """
    resolved = session.execute(
        select(Region.id).where(Region.code == code)
    ).scalar_one_or_none()
    if resolved is None:
        return {}
    ancestors = _ancestors_of(session, resolved)
    descendants = _descendants_of(session, resolved)
    ranks: dict[str | None, int] = {None: MARKET_RANK_AGNOSTIC}
    rows = session.execute(
        select(Region.id, Region.code).where(
            Region.id.in_(ancestors | descendants)
        )
    ).all()
    for region_id, region_code in rows:
        if region_id == resolved:
            ranks[region_code] = MARKET_RANK_EXACT
        elif region_id in ancestors:
            ranks[region_code] = MARKET_RANK_ANCESTOR
        else:
            ranks[region_code] = MARKET_RANK_DESCENDANT
    ranks.setdefault(GLOBAL_CODE, MARKET_RANK_GLOBAL)
    return ranks


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
