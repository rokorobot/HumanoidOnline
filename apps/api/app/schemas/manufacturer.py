"""Manufacturer read schemas (API contract §2)."""
from __future__ import annotations

from pydantic import BaseModel


class ManufacturerListItem(BaseModel):
    slug: str
    name: str
    country: str | None = None
    robot_count: int
    deployment_status: str | None = None


class ManufacturerRobot(BaseModel):
    slug: str
    name: str
    commercial_status: str


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
