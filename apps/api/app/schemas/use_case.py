"""Use-case read schemas (API contract §3)."""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.robot import RobotImagePrimary


class UseCaseListItem(BaseModel):
    slug: str
    name: str
    category: str | None = None
    robot_count: int


class SuitableRobot(BaseModel):
    slug: str
    name: str
    fit_score: float | None = None
    commercial_readiness: str | None = None
    limitations: str | None = None
    # MEDIA-01 governed thumbnail (display-eligible primary, or null -> unavailable).
    # Same image truth + gate as the catalogue card; never an alternate image path.
    primary_image: RobotImagePrimary | None = None


class UseCaseDetail(BaseModel):
    id: str
    slug: str
    name: str
    category: str | None = None
    description: str | None = None
    typical_tasks: list[str] | None = None
    typical_requirements: str | None = None
    key_limitations: str | None = None
    suitable_robots: list[SuitableRobot]
