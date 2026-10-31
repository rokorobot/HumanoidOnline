"""Product-line read schemas (DR-L1). A line carries identity and provenance only."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.common import ManufacturerRef
from app.schemas.robot import RobotDetail


class ProductLineBase(BaseModel):
    slug: str
    name: str
    manufacturer: ManufacturerRef
    #: The manufacturer page that presents the editions together, and when it was read.
    source_url: str
    observed_at: date


class ProductLineListItem(ProductLineBase):
    #: Published member robots only.
    robot_slugs: list[str]


class ProductLineDetail(ProductLineBase):
    #: Full robot detail per published member, exactly as GET /api/robots/{slug}.
    robots: list[RobotDetail]
