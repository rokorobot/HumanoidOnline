"""Public read API for product lines (API contract §3b; DR-L1)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.product_line import ProductLine
from app.models.robot import Robot
from app.schemas.common import ManufacturerRef
from app.schemas.product_line import ProductLineDetail, ProductLineListItem
from app.services import reads

router = APIRouter(prefix="/api/product-lines", tags=["product-lines"])


def _manufacturer_ref(line: ProductLine) -> ManufacturerRef:
    m = line.manufacturer
    return ManufacturerRef(slug=m.slug, name=m.name, country=reads._country_code(m))


def _published_member_slugs(session: Session, line_ids: list) -> dict:
    """line id -> published member robot slugs, in name order."""
    rows = session.execute(
        select(Robot.product_line_id, Robot.slug)
        .where(Robot.product_line_id.in_(line_ids), Robot.is_published.is_(True))
        .order_by(Robot.name, Robot.slug)
    ).all()
    members: dict = {}
    for line_id, slug in rows:
        members.setdefault(line_id, []).append(slug)
    return members


@router.get("", response_model=list[ProductLineListItem])
def list_product_lines(
    session: Annotated[Session, Depends(get_session)],
) -> list[ProductLineListItem]:
    lines = session.execute(
        select(ProductLine).where(ProductLine.is_published.is_(True)).order_by(ProductLine.name)
    ).scalars().all()
    members = _published_member_slugs(session, [ln.id for ln in lines])
    return [
        ProductLineListItem(
            slug=ln.slug,
            name=ln.name,
            manufacturer=_manufacturer_ref(ln),
            source_url=ln.source_url,
            observed_at=ln.observed_at,
            robot_slugs=members.get(ln.id, []),
        )
        for ln in lines
    ]


@router.get("/{slug}", response_model=ProductLineDetail)
def get_product_line(
    slug: str, session: Annotated[Session, Depends(get_session)]
) -> ProductLineDetail:
    line = session.execute(
        select(ProductLine).where(ProductLine.slug == slug, ProductLine.is_published.is_(True))
    ).scalars().first()
    if line is None:
        raise HTTPException(status_code=404, detail="product line not found")
    slugs = _published_member_slugs(session, [line.id]).get(line.id, [])
    # The shared governed detail read and serialization: no fact is re-derived here.
    by_slug = {r.slug: r for r in reads.load_details(session, slugs)}
    return ProductLineDetail(
        slug=line.slug,
        name=line.name,
        manufacturer=_manufacturer_ref(line),
        source_url=line.source_url,
        observed_at=line.observed_at,
        robots=[reads.serialize_detail(session, by_slug[s]) for s in slugs if s in by_slug],
    )
