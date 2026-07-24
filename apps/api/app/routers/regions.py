"""Public read API for canonical regions.

A small reference read that lets the buyer-intent Country step present the
canonical country list from live data (never hardcoded), the same way the TASK
step is seeded from `GET /api/use-cases`. The `code` returned here is exactly
what `POST /api/buyer-requirements` resolves back to a `country_region_id`.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.region import Region
from app.schemas.region import RegionListItem

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
