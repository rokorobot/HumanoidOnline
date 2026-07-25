"""Public read API for robots (API contract §1)."""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_session
from app.models.commercial import AvailabilityOffer
from app.models.enums import AUTONOMY_ORDER
from app.models.manufacturer import Manufacturer
from app.models.region import Region
from app.models.robot import Robot
from app.models.use_case import UseCase, UseCaseFit
from app.schemas.common import Page
from app.schemas.robot import CompareResponse, CompareRow, RobotDetail, RobotListItem
from app.services import reads

router = APIRouter(prefix="/api/robots", tags=["robots"])

_SORTS = {
    "name": Robot.name,
    "price": Robot.lowest_purchase_price,
    "payload": Robot.payload_kg,
    "newest": Robot.created_at,
}


def _apply_filters(stmt, *, q, manufacturer, commercial_status, transaction_type,
                   availability_status, region, use_case, payload_min, height_min,
                   height_max, price_max, mobility, autonomy_min, has_sdk, ros_support,
                   developer_edition, has_manipulation):
    stmt = stmt.where(Robot.is_published.is_(True))
    if q:
        stmt = stmt.where(Robot.search_vector.op("@@")(func.plainto_tsquery("english", q)))
    if manufacturer:
        stmt = stmt.where(
            Robot.manufacturer_id.in_(
                select(Manufacturer.id).where(Manufacturer.slug == manufacturer)
            )
        )
    if commercial_status:
        stmt = stmt.where(Robot.commercial_status.in_(commercial_status))
    if use_case:
        stmt = stmt.where(
            Robot.id.in_(
                select(UseCaseFit.robot_id)
                .join(UseCase, UseCase.id == UseCaseFit.use_case_id)
                .where(UseCase.slug == use_case)
            )
        )
    if payload_min is not None:
        stmt = stmt.where(Robot.payload_kg >= payload_min)
    if height_min is not None:
        stmt = stmt.where(Robot.height_cm >= height_min)
    if height_max is not None:
        stmt = stmt.where(Robot.height_cm <= height_max)
    if price_max is not None:
        stmt = stmt.where(Robot.lowest_purchase_price <= price_max)
    if mobility:
        stmt = stmt.where(Robot.mobility == mobility)
    if autonomy_min:
        if autonomy_min in AUTONOMY_ORDER:
            allowed = AUTONOMY_ORDER[AUTONOMY_ORDER.index(autonomy_min):]
            stmt = stmt.where(Robot.autonomy.in_(allowed))
    for flag, value in (
        (Robot.has_sdk, has_sdk),
        (Robot.ros_support, ros_support),
        (Robot.developer_edition, developer_edition),
        (Robot.has_manipulation, has_manipulation),
    ):
        if value is not None:
            stmt = stmt.where(flag.is_(value))

    # Availability-derived filters, all gated by is_current + canonical predicate.
    if transaction_type or availability_status or region:
        avail = (
            select(AvailabilityOffer.robot_id)
            .where(AvailabilityOffer.is_current.is_(True))
            .where(func.commercially_accessible(AvailabilityOffer.availability_status))
        )
        if transaction_type:
            avail = avail.where(AvailabilityOffer.transaction_type.in_(transaction_type))
        if availability_status:
            avail = avail.where(AvailabilityOffer.availability_status.in_(availability_status))
        if region:
            avail = avail.where(
                AvailabilityOffer.region_id.in_(
                    select(Region.id).where(Region.code == region)
                )
            )
        stmt = stmt.where(Robot.id.in_(avail))
    return stmt


@router.get("", response_model=Page[RobotListItem])
def list_robots(
    session: Annotated[Session, Depends(get_session)],
    q: str | None = None,
    manufacturer: str | None = None,
    commercial_status: Annotated[list[str] | None, Query()] = None,
    transaction_type: Annotated[list[str] | None, Query()] = None,
    availability_status: Annotated[list[str] | None, Query()] = None,
    region: str | None = None,
    use_case: str | None = None,
    payload_min: float | None = None,
    height_min: float | None = None,
    height_max: float | None = None,
    price_max: float | None = None,
    mobility: str | None = None,
    autonomy_min: str | None = None,
    has_sdk: bool | None = None,
    ros_support: bool | None = None,
    developer_edition: bool | None = None,
    has_manipulation: bool | None = None,
    sort: str = "name",
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page[RobotListItem]:
    filters = dict(
        q=q, manufacturer=manufacturer, commercial_status=commercial_status,
        transaction_type=transaction_type, availability_status=availability_status,
        region=region, use_case=use_case, payload_min=payload_min, height_min=height_min,
        height_max=height_max, price_max=price_max, mobility=mobility,
        autonomy_min=autonomy_min, has_sdk=has_sdk, ros_support=ros_support,
        developer_edition=developer_edition, has_manipulation=has_manipulation,
    )

    total = session.execute(
        _apply_filters(select(func.count(Robot.id)), **filters)
    ).scalar_one()

    desc = sort.startswith("-")
    key = sort[1:] if desc else sort
    col = _SORTS.get(key, Robot.name)
    order = col.desc().nullslast() if desc else col.asc().nullslast()

    stmt = _apply_filters(
        select(Robot).options(selectinload(Robot.pricing_offers)), **filters
    ).order_by(order, Robot.slug).limit(limit).offset(offset)
    robots = list(session.execute(stmt).scalars())

    snapshot = reads.snapshot_for(session, [r.id for r in robots])
    items = [reads.serialize_list_item(r, snapshot) for r in robots]
    return Page(items=items, total=total, limit=limit, offset=offset)


def _load_detail(session: Session, slug: str) -> Robot | None:
    stmt = (
        select(Robot)
        .where(Robot.slug == slug, Robot.is_published.is_(True))
        .options(
            selectinload(Robot.variants),
            selectinload(Robot.status_history),
            selectinload(Robot.specifications),
            selectinload(Robot.robot_capabilities),
            selectinload(Robot.use_case_fits),
            selectinload(Robot.pricing_offers),
            selectinload(Robot.availability_offers),
            selectinload(Robot.deployments),
            selectinload(Robot.images),
        )
    )
    return session.execute(stmt).scalars().first()


@router.get("/compare", response_model=CompareResponse)
def compare_robots(
    session: Annotated[Session, Depends(get_session)],
    ids: str = Query(..., description="2–4 comma-separated robot slugs"),
) -> CompareResponse:
    slugs = [s.strip() for s in ids.split(",") if s.strip()]
    unique = list(dict.fromkeys(slugs))
    robots = [r for r in (_load_detail(session, s) for s in unique) if r is not None]
    if not 2 <= len(robots) <= 4:
        raise HTTPException(status_code=422, detail="compare requires 2–4 valid robot slugs")

    details = [reads.serialize_detail(session, r) for r in robots]
    rows: list[CompareRow] = []
    for group, attr, label in reads.COMPARE_FIELDS:
        values: dict[str, float | bool | str | None] = {}
        for r in robots:
            raw = getattr(r, attr)
            values[r.slug] = float(raw) if isinstance(raw, Decimal) else raw
        rows.append(CompareRow(group=group, key=attr, label=label, values=values))
    return CompareResponse(robots=details, rows=rows)


@router.get("/{slug}", response_model=RobotDetail)
def get_robot(
    slug: str, session: Annotated[Session, Depends(get_session)]
) -> RobotDetail:
    robot = _load_detail(session, slug)
    if robot is None:
        raise HTTPException(status_code=404, detail="robot not found")
    return reads.serialize_detail(session, robot)
