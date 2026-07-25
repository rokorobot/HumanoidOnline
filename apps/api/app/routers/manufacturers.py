"""Public read API for manufacturers (API contract §2)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_session
from app.models.commercial import Deployment
from app.models.manufacturer import Manufacturer, Provider
from app.models.robot import Robot
from app.schemas.common import Page
from app.schemas.manufacturer import (
    ManufacturerDeployment,
    ManufacturerDetail,
    ManufacturerListItem,
    ManufacturerRobot,
    ProviderRead,
)
from app.services.reads import derive_portfolio_status

router = APIRouter(prefix="/api/manufacturers", tags=["manufacturers"])


@router.get("", response_model=Page[ManufacturerListItem])
def list_manufacturers(
    session: Annotated[Session, Depends(get_session)],
    limit: int = 24,
    offset: int = 0,
) -> Page[ManufacturerListItem]:
    limit = max(1, min(limit, 100))
    total = session.execute(select(func.count(Manufacturer.id))).scalar_one()

    published_robot_count = (
        select(func.count(Robot.id))
        .where(Robot.manufacturer_id == Manufacturer.id, Robot.is_published.is_(True))
        .scalar_subquery()
    )
    rows = session.execute(
        select(Manufacturer, published_robot_count.label("robot_count"))
        .order_by(Manufacturer.name)
        .limit(limit)
        .offset(offset)
    ).all()

    # Published robots' commercial_status per manufacturer, for portfolio_status.
    mfr_ids = [m.id for m, _ in rows]
    statuses: dict[object, list[str]] = {}
    if mfr_ids:
        for mid, status in session.execute(
            select(Robot.manufacturer_id, Robot.commercial_status).where(
                Robot.manufacturer_id.in_(mfr_ids), Robot.is_published.is_(True)
            )
        ).all():
            statuses.setdefault(mid, []).append(status)

    items = [
        ManufacturerListItem(
            slug=m.slug,
            name=m.name,
            country=m.country.code if m.country else None,
            robot_count=int(count),
            deployment_status=m.deployment_status,
            portfolio_status=derive_portfolio_status(statuses.get(m.id, [])),
            updated_at=m.updated_at,
        )
        for m, count in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{slug}", response_model=ManufacturerDetail)
def get_manufacturer(
    slug: str, session: Annotated[Session, Depends(get_session)]
) -> ManufacturerDetail:
    m = session.execute(
        select(Manufacturer)
        .where(Manufacturer.slug == slug)
        .options(selectinload(Manufacturer.robots))
    ).scalars().first()
    if m is None:
        raise HTTPException(status_code=404, detail="manufacturer not found")

    providers = session.execute(
        select(Provider).where(Provider.manufacturer_id == m.id).order_by(Provider.name)
    ).scalars().all()

    robot_ids = [r.id for r in m.robots]
    deployments: list[ManufacturerDeployment] = []
    if robot_ids:
        dep_rows = session.execute(
            select(Deployment)
            .where(Deployment.robot_id.in_(robot_ids))
            .options(selectinload(Deployment.robot), selectinload(Deployment.region))
        ).scalars().all()
        deployments = [
            ManufacturerDeployment(
                robot_slug=d.robot.slug,
                customer_name=d.customer_name,
                region=d.region.code if d.region else None,
                summary=d.summary,
            )
            for d in dep_rows
        ]

    return ManufacturerDetail(
        id=str(m.id),
        slug=m.slug,
        name=m.name,
        legal_name=m.legal_name,
        country=m.country.code if m.country else None,
        website_url=m.website_url,
        founded_year=m.founded_year,
        description=m.description,
        commercial_model=m.commercial_model,
        deployment_status=m.deployment_status,
        is_public_company=m.is_public_company,
        ticker=m.ticker,
        robots=[
            ManufacturerRobot(slug=r.slug, name=r.name, commercial_status=r.commercial_status)
            for r in sorted(m.robots, key=lambda r: r.name)
            if r.is_published
        ],
        providers=[ProviderRead(slug=p.slug, name=p.name, type=p.type) for p in providers],
        deployments=deployments,
    )
