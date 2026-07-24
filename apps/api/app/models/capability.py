"""`capability` and `robot_capability` (mirror of db/schema.sql)."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import capability_category


class Capability(Base):
    __tablename__ = "capability"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(capability_category, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class RobotCapability(Base):
    __tablename__ = "robot_capability"

    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), primary_key=True
    )
    capability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capability.id", ondelete="CASCADE"), primary_key=True
    )
    supported: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    detail: Mapped[str | None] = mapped_column(Text)

    robot: Mapped[Robot] = relationship("Robot", back_populates="robot_capabilities")  # noqa: F821
    capability: Mapped[Capability] = relationship("Capability", lazy="selectin")
