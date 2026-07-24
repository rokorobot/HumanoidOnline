"""`manufacturer` and `provider` (mirror of db/schema.sql)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import commercial_status, provider_type


class Manufacturer(Base):
    __tablename__ = "manufacturer"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(Text)
    country_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("region.id")
    )
    website_url: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)
    founded_year: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    target_markets: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    commercial_model: Mapped[str | None] = mapped_column(Text)
    deployment_status: Mapped[str | None] = mapped_column(commercial_status)
    support_structure: Mapped[str | None] = mapped_column(Text)
    funding_status: Mapped[str | None] = mapped_column(Text)
    is_public_company: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    ticker: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    country: Mapped[Region | None] = relationship("Region", lazy="selectin")  # noqa: F821
    robots: Mapped[list[Robot]] = relationship(  # noqa: F821
        "Robot", back_populates="manufacturer", lazy="selectin"
    )


class Provider(Base):
    __tablename__ = "provider"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    type: Mapped[str] = mapped_column(provider_type, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("manufacturer.id", ondelete="SET NULL")
    )
    country_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("region.id")
    )
    website_url: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    accepts_leads: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    lead_fee_model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
