"""Public read API for use cases (API contract §3)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_session
from app.models.robot import Robot
from app.models.use_case import UseCase, UseCaseFit
from app.schemas.common import Page
from app.schemas.use_case import SuitableRobot, UseCaseDetail, UseCaseListItem

router = APIRouter(prefix="/api/use-cases", tags=["use-cases"])


@router.get("", response_model=Page[UseCaseListItem])
def list_use_cases(
    session: Annotated[Session, Depends(get_session)],
    limit: int = 24,
    offset: int = 0,
) -> Page[UseCaseListItem]:
    limit = max(1, min(limit, 100))
    total = session.execute(select(func.count(UseCase.id))).scalar_one()

    robot_count = (
        select(func.count(func.distinct(UseCaseFit.robot_id)))
        .join(Robot, Robot.id == UseCaseFit.robot_id)
        .where(UseCaseFit.use_case_id == UseCase.id, Robot.is_published.is_(True))
        .scalar_subquery()
    )
    rows = session.execute(
        select(UseCase, robot_count.label("robot_count"))
        .order_by(UseCase.name)
        .limit(limit)
        .offset(offset)
    ).all()

    items = [
        UseCaseListItem(
            slug=u.slug, name=u.name, category=u.category, robot_count=int(count)
        )
        for u, count in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{slug}", response_model=UseCaseDetail)
def get_use_case(
    slug: str, session: Annotated[Session, Depends(get_session)]
) -> UseCaseDetail:
    u = session.execute(
        select(UseCase)
        .where(UseCase.slug == slug)
        .options(selectinload(UseCase.fits).selectinload(UseCaseFit.robot))
    ).scalars().first()
    if u is None:
        raise HTTPException(status_code=404, detail="use case not found")

    suitable = sorted(
        (
            SuitableRobot(
                slug=f.robot.slug,
                name=f.robot.name,
                fit_score=float(f.fit_score) if f.fit_score is not None else None,
                commercial_readiness=f.commercial_readiness,
                limitations=f.limitations,
            )
            for f in u.fits
            if f.robot.is_published
        ),
        key=lambda x: (x.fit_score if x.fit_score is not None else -1.0),
        reverse=True,
    )

    return UseCaseDetail(
        id=str(u.id),
        slug=u.slug,
        name=u.name,
        category=u.category,
        description=u.description,
        typical_tasks=u.typical_tasks,
        typical_requirements=u.typical_requirements,
        key_limitations=u.key_limitations,
        suitable_robots=suitable,
    )
