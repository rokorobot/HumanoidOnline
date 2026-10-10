"""Public read API for canonical regions.

A small reference read that lets the buyer-intent Country step present the
canonical country list from live data (never hardcoded), the same way the TASK
step is seeded from `GET /api/use-cases`. The `code` returned here is exactly
what `POST /api/buyer-requirements` resolves back to a `country_region_id`.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.region import Region
from app.schemas.region import RegionListItem, RegionScope
from app.services.regions import applicable_region_ids, discovery_region_ids

router = APIRouter(prefix="/api/regions", tags=["regions"])


@router.get("", response_model=list[RegionListItem])
def list_regions(
    session: Annotated[Session, Depends(get_session)],
    type: Annotated[str | None, Query(description="Filter by region_type, e.g. COUNTRY")] = None,
) -> list[RegionListItem]:
    stmt = select(Region)
    if type is not None:
        stmt = stmt.where(Region.type == type)
    stmt = stmt.order_by(Region.name)
    rows = session.execute(stmt).scalars().all()
    return [RegionListItem.model_validate(r) for r in rows]


@router.get("/{code}/scope", response_model=RegionScope)
def region_scope(
    code: str,
    session: Annotated[Session, Depends(get_session)],
) -> RegionScope:
    """Which region codes an offer may carry to be in scope for `code`.

    A read-only projection of the two canonical resolvers, so the compare view
    can say whether a recorded offer applies to a buyer's region or belongs to a
    market without a second interpretation of the hierarchy. It reports scope
    only: it asserts nothing about delivery, and it never relabels an offer.
    An unknown code is 404, never an empty (or widened) scope.
    """
    applicable = applicable_region_ids(session, code=code)
    if not applicable:
        raise HTTPException(status_code=404, detail="unknown region code")
    market = discovery_region_ids(session, code=code)

    def codes(ids: set) -> list[str]:
        return sorted(
            session.execute(select(Region.code).where(Region.id.in_(ids))).scalars().all()
        )

    return RegionScope(code=code, applicable=codes(applicable), market=codes(market))
