"""Commercial read models: `pricing_offer`, `availability_offer`, `deployment`.

WS2 reads these to render the three independent dimensions (maturity /
obtainability / evidence) and price states. No transaction workflow is
implemented (AGENTS.md rules 9 & 21) — these are display reads only.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    availability_status,
    billing_period,
    price_type,
    transaction_type,
)


class PricingOffer(Base):
    __tablename__ = "pricing_offer"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot_variant.id", ondelete="CASCADE")
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider.id", ondelete="SET NULL")
    )
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("region.id")
    )
    transaction_type: Mapped[str] = mapped_column(transaction_type, nullable=False)
    price_type: Mapped[str] = mapped_column(price_type, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default=text("'USD'"))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    billing_period: Mapped[str] = mapped_column(
        billing_period, nullable=False, server_default=text("'ONE_TIME'")
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    robot: Mapped[Robot] = relationship("Robot", back_populates="pricing_offers")  # noqa: F821
    provider: Mapped[Provider | None] = relationship("Provider", lazy="selectin")  # noqa: F821
    region: Mapped[Region | None] = relationship("Region", lazy="selectin")  # noqa: F821


class AvailabilityOffer(Base):
    __tablename__ = "availability_offer"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot_variant.id", ondelete="CASCADE")
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider.id", ondelete="SET NULL")
    )
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("region.id")
    )
    transaction_type: Mapped[str] = mapped_column(transaction_type, nullable=False)
    availability_status: Mapped[str] = mapped_column(
        availability_status, nullable=False, server_default=text("'ON_REQUEST'")
    )
    available_from: Mapped[date | None] = mapped_column(Date)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    min_order_qty: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    robot: Mapped[Robot] = relationship(  # noqa: F821
        "Robot", back_populates="availability_offers"
    )
    provider: Mapped[Provider | None] = relationship("Provider", lazy="selectin")  # noqa: F821
    region: Mapped[Region | None] = relationship("Region", lazy="selectin")  # noqa: F821


class Deployment(Base):
    __tablename__ = "deployment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider.id", ondelete="SET NULL")
    )
    customer_name: Mapped[str | None] = mapped_column(Text)
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("region.id")
    )
    use_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("use_case.id", ondelete="SET NULL")
    )
    transaction_type: Mapped[str | None] = mapped_column(transaction_type)
    unit_count: Mapped[int | None] = mapped_column(Integer)
    contract_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    contract_currency: Mapped[str | None] = mapped_column(CHAR(3), server_default=text("'USD'"))
    started_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    robot: Mapped[Robot] = relationship("Robot", back_populates="deployments")  # noqa: F821
    provider: Mapped[Provider | None] = relationship("Provider", lazy="selectin")  # noqa: F821
    region: Mapped[Region | None] = relationship("Region", lazy="selectin")  # noqa: F821
    use_case: Mapped[UseCase | None] = relationship("UseCase", lazy="selectin")  # noqa: F821
