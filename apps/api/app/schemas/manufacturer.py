"""Manufacturer read schemas (API contract §2)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.robot import RobotImagePrimary


class ManufacturerListItem(BaseModel):
    slug: str
    name: str
    # Headquarters country code (migration 0013); null when unresolved.
    country: str | None = None
    # Two different facts, never collapsed into one "robot count". `tracked`
    # is every catalogue record for this manufacturer, published or not;
    # `published` is the subset with a public profile. A single count forced
    # the card to render "0 ROBOTS" for a manufacturer whose robots we hold
    # records for but have not published — a false claim about the maker
    # rather than a statement about our own publication state.
    tracked_robot_count: int
    published_robot_count: int
    deployment_status: str | None = None
    # Derived from PUBLISHED robots' commercial_status only (see
    # reads.derive_portfolio_status) — it describes published catalogue records,
    # never unpublished ones or the company. Distinct from `deployment_status`.
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


class ManufacturerSource(BaseModel):
    """One company-level evidence row and the profile fields it supports.

    The row's free-text `note` is not published: it carries internal provenance
    wording. `retrieval` exposes the one fact from it a reader needs — that the
    source was read by agent-assisted research (docs/26) — and `verified_at`
    stays null until a human verifies it.
    """

    claim_fields: list[str]
    source_type: str
    source_title: str | None = None
    source_url: str | None = None
    published_at: date | None = None
    observed_at: datetime
    verified_at: datetime | None = None
    confidence: str
    retrieval: str | None = None


class ManufacturerDetail(BaseModel):
    id: str
    slug: str
    name: str
    legal_name: str | None = None
    # Headquarters, kept apart from incorporation and other operating locations.
    country: str | None = None
    headquarters_city: str | None = None
    incorporation: str | None = None
    operating_locations: list[str] = []
    website_url: str | None = None
    founded_year: int | None = None
    description: str | None = None
    target_markets: list[str] = []
    commercial_model: str | None = None
    # Humanoid deployment status and what it rests on.
    deployment_status: str | None = None
    deployment_note: str | None = None
    # Null = listing status unknown. Describes this entity only.
    is_public_company: bool | None = None
    ticker: str | None = None
    parent_company: str | None = None
    parent_listing: str | None = None
    parent_relationship: str | None = None
    tracked_robot_count: int
    published_robot_count: int
    robots: list[ManufacturerRobot]
    providers: list[ProviderRead]
    deployments: list[ManufacturerDeployment]
    sources: list[ManufacturerSource]
