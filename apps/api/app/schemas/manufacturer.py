"""Manufacturer read schemas (API contract §2)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.robot import RobotImagePrimary


class ManufacturerListItem(BaseModel):
    slug: str
    name: str
    country: str | None = None
    robot_count: int
    deployment_status: str | None = None
    # Derived from published robots' commercial_status (see reads.derive_portfolio_status).
    # Distinct from the coarse `deployment_status` company column.
    portfolio_status: str | None = None
    updated_at: datetime  # sitemap lastmod (AGENT-01)


class ManufacturerRobot(BaseModel):
    slug: str
    name: str
    commercial_status: str
    # MEDIA-01 governed thumbnail (display-eligible primary, or null -> unavailable).
    # Same image truth + gate as the catalogue card; never an alternate image path.
    primary_image: RobotImagePrimary | None = None


class ProviderRead(BaseModel):
    slug: str
    name: str
    type: str


class ManufacturerDeployment(BaseModel):
    robot_slug: str
    customer_name: str | None = None
    region: str | None = None
    summary: str | None = None


class ManufacturerDetail(BaseModel):
    id: str
    slug: str
    name: str
    legal_name: str | None = None
    country: str | None = None
    website_url: str | None = None
    founded_year: int | None = None
    description: str | None = None
    commercial_model: str | None = None
    deployment_status: str | None = None
    is_public_company: bool
    ticker: str | None = None
    robots: list[ManufacturerRobot]
    providers: list[ProviderRead]
    deployments: list[ManufacturerDeployment]
