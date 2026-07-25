"""Discovery layer — DATA-D1 (docs/11_DATA_D1_CONTRACT.md, RATIFIED v0.1).

Mirror of db/schema.sql SECTION 10 / db/migrations/0003. These are the
NONCANONICAL research tables: competitors are radar only, and nothing here is a
canonical fact until it passes the promotion gate (§7). The DDL is canonical
(AGENTS.md rule 2); these models mirror it and never generate DDL.

Structural isolation (§5 / DATA-D1.10 / Gate K): the `possible_*` / `promoted_*`
columns reference canonical rows FROM a candidate; no canonical table references
back. The public API never exposes these tables (§22 / Gate I).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    candidate_entity_type,
    candidate_identity_status,
    candidate_status,
    claim_status,
    discovery_source_class,
    trace_state,
)


class DiscoverySource(Base):
    """A radar source. DATA-D1.9: crawler-eligible only once ToS/robots reviewed
    (the DB CHECK forbids is_enabled unless tos_reviewed AND robots_allowed)."""

    __tablename__ = "discovery_source"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_class: Mapped[str] = mapped_column(discovery_source_class, nullable=False)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    tos_reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    robots_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    @property
    def radar_eligible(self) -> bool:
        """DATA-D1.9 in one place: a source may be crawled only when reviewed,
        access-permitted, and explicitly enabled."""
        return self.is_enabled and self.tos_reviewed and self.robots_allowed


class DiscoveryCandidate(Base):
    __tablename__ = "discovery_candidate"
    __table_args__ = (UniqueConstraint("source_id", "external_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(
        candidate_entity_type, nullable=False, server_default=text("'ROBOT'")
    )
    candidate_name: Mapped[str | None] = mapped_column(Text)
    candidate_manufacturer: Mapped[str | None] = mapped_column(Text)
    discovery_url: Mapped[str | None] = mapped_column(Text)
    external_ref: Mapped[str | None] = mapped_column(Text)
    # Minimal (DATA-D1.10): identity leads + claimed values under investigation.
    candidate_data: Mapped[dict | None] = mapped_column(JSONB)
    identity_status: Mapped[str] = mapped_column(
        candidate_identity_status, nullable=False, server_default=text("'UNRESOLVED'")
    )
    status: Mapped[str] = mapped_column(
        candidate_status, nullable=False, server_default=text("'DISCOVERED'")
    )
    trace_state: Mapped[str] = mapped_column(
        trace_state, nullable=False, server_default=text("'NOT_TRACED'")
    )
    trace_url: Mapped[str | None] = mapped_column(Text)
    # Candidate -> canonical only. No canonical row points back here (Gate K).
    possible_robot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="SET NULL")
    )
    possible_manufacturer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("manufacturer.id", ondelete="SET NULL")
    )
    promoted_robot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="SET NULL")
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    claims: Mapped[list[CandidateClaim]] = relationship(
        "CandidateClaim",
        back_populates="candidate",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    images: Mapped[list[CandidateImageRef]] = relationship(
        "CandidateImageRef",
        back_populates="candidate",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<DiscoveryCandidate {self.candidate_name!r} status={self.status!r}>"


class CandidateClaim(Base):
    """One claimed field value. NULL claimed_value = UNKNOWN (never 0/false).
    Multiple rows per (candidate, field_key) preserve source conflicts (DATA-D1.8)."""

    __tablename__ = "candidate_claim"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_key: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    claim_status: Mapped[str] = mapped_column(
        claim_status, nullable=False, server_default=text("'NOT_VERIFIED'")
    )
    discovery_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_source.id", ondelete="SET NULL")
    )
    evidence_url: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    candidate: Mapped[DiscoveryCandidate] = relationship(
        "DiscoveryCandidate", back_populates="claims"
    )


class CandidateImageRef(Base):
    """Reference-only candidate imagery (DATA-D1 R3): URL + metadata, NO binary."""

    __tablename__ = "candidate_image_ref"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    discovery_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_source.id", ondelete="SET NULL")
    )
    credited_to: Mapped[str | None] = mapped_column(Text)
    media_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'CANDIDATE'")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    candidate: Mapped[DiscoveryCandidate] = relationship(
        "DiscoveryCandidate", back_populates="images"
    )


class PromotionAudit(Base):
    """Append-only human-approval + promotion lineage (§19 / Gate J)."""

    __tablename__ = "promotion_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    promoted_entity_type: Mapped[str | None] = mapped_column(candidate_entity_type)
    promoted_robot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("robot.id", ondelete="SET NULL")
    )
    evidence_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
