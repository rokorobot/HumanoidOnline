"""`robot`, `robot_variant`, `robot_status_history` (mirror of db/schema.sql)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import autonomy_level, commercial_status, mobility_type


class Robot(Base):
    __tablename__ = "robot"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("manufacturer.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    model_code: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    hero_image_url: Mapped[str | None] = mapped_column(Text)
    announced_year: Mapped[int | None] = mapped_column(Integer)

    commercial_status: Mapped[str] = mapped_column(
        commercial_status, nullable=False, server_default=text("'ANNOUNCED'")
    )

    # First-class physical specs.
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    #: Horizontal extent. Distinct measurements: span is fingertip-to-fingertip,
    #: reach is one arm from its shoulder. Neither is derived from the other.
    arm_span_cm: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    reach_cm: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    payload_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    walk_speed_ms: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    battery_wh: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    mobility: Mapped[str | None] = mapped_column(mobility_type)
    degrees_of_freedom: Mapped[int | None] = mapped_column(Integer)
    hand_type: Mapped[str | None] = mapped_column(Text)
    hand_dof: Mapped[int | None] = mapped_column(Integer)

    # Intelligence / capability flags.
    autonomy: Mapped[str | None] = mapped_column(autonomy_level)
    has_manipulation: Mapped[bool | None] = mapped_column(Boolean)
    has_teleoperation: Mapped[bool | None] = mapped_column(Boolean)
    has_vision: Mapped[bool | None] = mapped_column(Boolean)
    has_language_ui: Mapped[bool | None] = mapped_column(Boolean)

    # Developer flags.
    has_sdk: Mapped[bool | None] = mapped_column(Boolean)
    has_api: Mapped[bool | None] = mapped_column(Boolean)
    ros_support: Mapped[bool | None] = mapped_column(Boolean)
    developer_edition: Mapped[bool | None] = mapped_column(Boolean)
    simulation_support: Mapped[bool | None] = mapped_column(Boolean)

    # Denormalised cache (authoritative money is pricing_offer).
    lowest_purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    lowest_price_currency: Mapped[str | None] = mapped_column(CHAR(3))

    # Maintained by trigger; deferred so reads don't pull it unless needed.
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, deferred=True)
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    manufacturer: Mapped[Manufacturer] = relationship(  # noqa: F821
        "Manufacturer", back_populates="robots", lazy="selectin"
    )
    variants: Mapped[list[RobotVariant]] = relationship(
        "RobotVariant", back_populates="robot", cascade="all, delete-orphan"
    )
    status_history: Mapped[list[RobotStatusHistory]] = relationship(
        "RobotStatusHistory",
        back_populates="robot",
        cascade="all, delete-orphan",
        order_by="RobotStatusHistory.effective_at",
    )
    specifications: Mapped[list[Specification]] = relationship(  # noqa: F821
        "Specification", back_populates="robot", cascade="all, delete-orphan"
    )
    robot_capabilities: Mapped[list[RobotCapability]] = relationship(  # noqa: F821
        "RobotCapability", back_populates="robot", cascade="all, delete-orphan"
    )
    use_case_fits: Mapped[list[UseCaseFit]] = relationship(  # noqa: F821
        "UseCaseFit", back_populates="robot", cascade="all, delete-orphan"
    )
    pricing_offers: Mapped[list[PricingOffer]] = relationship(  # noqa: F821
        "PricingOffer", back_populates="robot", cascade="all, delete-orphan"
    )
    availability_offers: Mapped[list[AvailabilityOffer]] = relationship(  # noqa: F821
        "AvailabilityOffer", back_populates="robot", cascade="all, delete-orphan"
    )
    deployments: Mapped[list[Deployment]] = relationship(  # noqa: F821
        "Deployment", back_populates="robot", cascade="all, delete-orphan"
    )
    images: Mapped[list[RobotImage]] = relationship(  # noqa: F821
        "RobotImage", back_populates="robot", cascade="all, delete-orphan", lazy="selectin"
    )


class RobotVariant(Base):
    __tablename__ = "robot_variant"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_developer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    spec_overrides: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    robot: Mapped[Robot] = relationship("Robot", back_populates="variants")


class RobotStatusHistory(Base):
    __tablename__ = "robot_status_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(commercial_status, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    robot: Mapped[Robot] = relationship("Robot", back_populates="status_history")
