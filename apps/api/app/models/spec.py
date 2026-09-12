"""`spec_definition` and `specification` (mirror of db/schema.sql)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import capability_category, spec_value_type


class SpecDefinition(Base):
    __tablename__ = "spec_definition"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        capability_category, nullable=False, server_default=text("'OTHER'")
    )
    value_type: Mapped[str] = mapped_column(spec_value_type, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    is_filterable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    #: 'CATALOGUE_IMPORT' for definitions the catalogue importer owns; NULL for
    #: seed/hand-authored ones, which it must never rewrite.
    managed_by: Mapped[str | None] = mapped_column(Text)


class Specification(Base):
    __tablename__ = "specification"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot_variant.id", ondelete="CASCADE")
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spec_definition.id", ondelete="RESTRICT"), nullable=False
    )
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    value_bool: Mapped[bool | None] = mapped_column(Boolean)
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    #: Provenance of this value. A long-tail spec carries no evidence_source row
    #: (it is descriptive, not a commercial fact), so attribution travels with it:
    #: who stated it, where, what it describes, and when it was observed.
    managed_by: Mapped[str | None] = mapped_column(Text)
    source_label: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    #: MANUFACTURER | MANUFACTURER_DOC | COMPONENT_MANUFACTURER | RESELLER_CLAIM
    source_kind: Mapped[str | None] = mapped_column(Text)
    #: THIS_EDITION | PRODUCT_LINE | PLATFORM
    edition_scope: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    robot: Mapped[Robot] = relationship("Robot", back_populates="specifications")  # noqa: F821
    definition: Mapped[SpecDefinition] = relationship("SpecDefinition", lazy="selectin")
