"""Transaction layer — `commercial_lead`, `commercial_lead_robot`,
`commercial_lead_provider` (mirror of db/schema.sql SECTION 5).

WS7 writes these tables — the platform's first commercial conversion. The DDL is
canonical (AGENTS.md rule 2); these models mirror it and never generate DDL.

Data laws honoured by the write path (see `app/services/leads`), reflected here:
  - `contact_email` is NOT NULL: WS5 anonymity ends at this capture point.
  - `message` is the buyer's free-text inquiry (added by forward migration
    `0001`); it is NOT hidden inside `outcome`/`requirements_snapshot`.
  - `lead_status` defaults to 'NEW' and is admin-only — the public path never
    transitions it, and the write schema forbids the client sending it.
  - `commercial_lead_robot.match_score` is nullable: NULL means "not produced by
    the deterministic matcher" (a direct Robot-Detail capture), never 0.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import lead_status, transaction_preference


class CommercialLead(Base):
    __tablename__ = "commercial_lead"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # A requirement may remain anonymous until lead capture; ON DELETE SET NULL
    # keeps the lead if its requirement is later removed.
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buyer_requirement.id", ondelete="SET NULL")
    )

    # captured contact (denormalised from the requirement at capture time)
    contact_name: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str] = mapped_column(Text, nullable=False)
    organization: Mapped[str | None] = mapped_column(Text)

    country_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("region.id")
    )
    use_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("use_case.id", ondelete="SET NULL")
    )
    preferred_transaction: Mapped[str] = mapped_column(
        transaction_preference, nullable=False, server_default=text("'UNKNOWN'")
    )
    # Same currency discipline as buyer_requirement: no server_default here, so a
    # Python None writes SQL NULL rather than fabricating 'USD'.
    budget_currency: Mapped[str | None] = mapped_column(CHAR(3))
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    timeline: Mapped[date | None] = mapped_column(Date)

    requirements_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    message: Mapped[str | None] = mapped_column(Text)
    lead_status: Mapped[str] = mapped_column(
        lead_status, nullable=False, server_default=text("'NEW'")
    )
    outcome: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    robots: Mapped[list[CommercialLeadRobot]] = relationship(
        "CommercialLeadRobot",
        back_populates="lead",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    providers: Mapped[list[CommercialLeadProvider]] = relationship(
        "CommercialLeadProvider",
        back_populates="lead",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<CommercialLead id={self.id!r} status={self.lead_status!r}>"


class CommercialLeadRobot(Base):
    """Robots attached to a lead — the matched shortlist that was surfaced.

    `match_score` carries the deterministic score copied from `match_result`
    (NULL for a direct Robot-Detail capture, never matched). `is_selected` marks
    the buyer's pick(s): the clicked card, or every robot for a shortlist CTA.
    """

    __tablename__ = "commercial_lead_robot"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("commercial_lead.id", ondelete="CASCADE"),
        primary_key=True,
    )
    robot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="CASCADE"), primary_key=True
    )
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    is_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    lead: Mapped[CommercialLead] = relationship("CommercialLead", back_populates="robots")


class CommercialLeadProvider(Base):
    """Lead routing / introduction log — the basis of the first revenue model.

    WS7 only *activates the mechanism*: a route is written with status='PENDING'
    and contacted_at=NULL. A PENDING route means a candidate exists; it does NOT
    mean HumanoidOnline contacted anyone (no email/webhook/CRM in v0.1).
    """

    __tablename__ = "commercial_lead_provider"
    __table_args__ = (
        UniqueConstraint("lead_id", "provider_id", "robot_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commercial_lead.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider.id", ondelete="CASCADE"), nullable=False
    )
    robot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    lead: Mapped[CommercialLead] = relationship("CommercialLead", back_populates="providers")
