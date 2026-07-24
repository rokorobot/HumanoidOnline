"""`use_case` and `use_case_fit` (mirror of db/schema.sql)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import commercial_status


class UseCase(Base):
    __tablename__ = "use_case"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    typical_tasks: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    typical_requirements: Mapped[str | None] = mapped_column(Text)
    key_limitations: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    fits: Mapped[list[UseCaseFit]] = relationship(
        "UseCaseFit", back_populates="use_case"
    )


class UseCaseFit(Base):
    __tablename__ = "use_case_fit"

    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), primary_key=True
    )
    use_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("use_case.id", ondelete="CASCADE"), primary_key=True
    )
    fit_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    commercial_readiness: Mapped[str | None] = mapped_column(commercial_status)
    notes: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)

    robot: Mapped[Robot] = relationship("Robot", back_populates="use_case_fits")  # noqa: F821
    use_case: Mapped[UseCase] = relationship("UseCase", back_populates="fits", lazy="selectin")
