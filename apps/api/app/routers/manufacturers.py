"""Public read API for manufacturers (API contract §2)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_session
from app.models.commercial import Deployment
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer, Provider
from app.models.robot import Robot
from app.schemas.common import Page
from app.schemas.manufacturer import (
    ManufacturerDeployment,
    ManufacturerDetail,
    ManufacturerListItem,
    ManufacturerRobot,
    ManufacturerSource,
    ProviderRead,
)
from app.services.reads import _primary_image, derive_portfolio_status

router = APIRouter(prefix="/api/manufacturers", tags=["manufacturers"])

#: docs/26 §3.1 fixed provenance statement prefix.
_AGENT_RETRIEVAL_PREFIX = "RETRIEVAL: AGENT_ASSISTED_RESEARCH"


def _retrieval(note: str | None) -> str | None:
    if note and note.startswith(_AGENT_RETRIEVAL_PREFIX):
        return "AGENT_ASSISTED_RESEARCH"
    return None


@router.get("", response_model=Page[ManufacturerListItem])
def list_manufacturers(
    session: Annotated[Session, Depends(get_session)],
    limit: int = 24,
    offset: int = 0,
) -> Page[ManufacturerListItem]:
    limit = max(1, min(limit, 100))
    total = session.execute(select(func.count(Manufacturer.id))).scalar_one()

    # Aggregate counts only — no unpublished robot identity or content is
    # selected here, so an unpublished record can raise a number without ever
    # reaching a public surface.
    tracked_robot_count = (
        select(func.count(Robot.id))
        .where(Robot.manufacturer_id == Manufacturer.id)
        .scalar_subquery()
    )
    published_robot_count = (
        select(func.count(Robot.id))
        .where(Robot.manufacturer_id == Manufacturer.id, Robot.is_published.is_(True))
        .scalar_subquery()
    )
    rows = session.execute(
        select(
            Manufacturer,
            tracked_robot_count.label("tracked_robot_count"),
            published_robot_count.label("published_robot_count"),
        )
        .order_by(Manufacturer.name)
        .limit(limit)
        .offset(offset)
    ).all()

    # Published robots' commercial_status per manufacturer, for portfolio_status.
    mfr_ids = [m.id for m, _, _ in rows]
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
            tracked_robot_count=int(tracked),
            published_robot_count=int(published),
            deployment_status=m.deployment_status,
            portfolio_status=derive_portfolio_status(statuses.get(m.id, [])),
            updated_at=m.updated_at,
        )
        for m, tracked, published in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{slug}", response_model=ManufacturerDetail)
def get_manufacturer(
    slug: str, session: Annotated[Session, Depends(get_session)]
) -> ManufacturerDetail:
    m = session.execute(
        select(Manufacturer)
        .where(Manufacturer.slug == slug)
        .options(selectinload(Manufacturer.robots).selectinload(Robot.images))
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

    # Company-level provenance. Deterministic order: newest observation first,
    # then URL, then the internal id (never exposed) as the final tie-break.
    evidence_rows = session.execute(
        select(EvidenceSource)
        .where(
            EvidenceSource.subject_type == "MANUFACTURER",
            EvidenceSource.subject_id == m.id,
        )
        .order_by(
            EvidenceSource.observed_at.desc(),
            EvidenceSource.source_url,
            EvidenceSource.id,
        )
    ).scalars().all()

    published = [r for r in m.robots if r.is_published]

    return ManufacturerDetail(
        id=str(m.id),
        slug=m.slug,
        name=m.name,
        legal_name=m.legal_name,
        country=m.country.code if m.country else None,
        headquarters_city=m.headquarters_city,
        incorporation=m.incorporation,
        operating_locations=list(m.operating_locations or []),
        website_url=m.website_url,
        founded_year=m.founded_year,
        description=m.description,
        target_markets=list(m.target_markets or []),
        commercial_model=m.commercial_model,
        deployment_status=m.deployment_status,
        deployment_note=m.deployment_note,
        is_public_company=m.is_public_company,
        ticker=m.ticker,
        parent_company=m.parent_company,
        parent_listing=m.parent_listing,
        parent_relationship=m.parent_relationship,
        # Same two facts as the list endpoint: every record vs published ones.
        tracked_robot_count=len(m.robots),
        published_robot_count=len(published),
        robots=[
            ManufacturerRobot(
                slug=r.slug,
                name=r.name,
                commercial_status=r.commercial_status,
                # Reuse the exact catalogue-card MEDIA-01 selection (display-
                # eligible gate); no unverified image can reach this surface.
                primary_image=_primary_image(r),
            )
            for r in sorted(published, key=lambda r: r.name)
        ],
        providers=[ProviderRead(slug=p.slug, name=p.name, type=p.type) for p in providers],
        deployments=deployments,
        sources=[
            ManufacturerSource(
                claim_fields=list(e.claim_fields or []),
                source_type=e.source_type,
                source_title=e.source_title,
                source_url=e.source_url,
                published_at=e.published_at,
                observed_at=e.observed_at,
                verified_at=e.verified_at,
                confidence=e.confidence,
                retrieval=_retrieval(e.note),
            )
            for e in evidence_rows
        ],
    )
