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

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint, event, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    candidate_entity_type,
    candidate_identity_status,
    candidate_status,
    claim_status,
    discovery_source_class,
    extraction_confidence,
    extraction_method,
    robots_status,
    source_type,
    tos_status,
    trace_state,
)


class DiscoverySource(Base):
    """A radar source. DATA-D1.9: crawler-eligible only when the ToS AFFIRMATIVELY
    permits automation, the robots policy is not a disallow, and the review is
    attributed + timestamped. The DB CHECK enforces the same on is_enabled."""

    __tablename__ = "discovery_source"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_class: Mapped[str] = mapped_column(discovery_source_class, nullable=False)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    tos_status: Mapped[str] = mapped_column(
        tos_status, nullable=False, server_default=text("'UNKNOWN'")
    )
    robots_status: Mapped[str] = mapped_column(
        robots_status, nullable=False, server_default=text("'UNKNOWN'")
    )
    eligibility_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eligibility_reviewed_by: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # DATA-D1.LIVE §5 / LIVE.2 / owner decision D-2 (migration 0004). The two
    # axes expire differently on purpose: a terms page is a legal document that
    # changes rarely and deliberately (90 days, void on a material hash change),
    # while a robots policy is an operational signal that can change any day and
    # is therefore re-read every run, never answered from a stored decision.
    allowed_path_prefixes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    tos_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tos_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tos_page_hash: Mapped[str | None] = mapped_column(Text)
    last_robots_hash: Mapped[str | None] = mapped_column(Text)
    last_robots_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    @property
    def radar_eligible(self) -> bool:
        """DATA-D1.9 in one place: a source may be crawled only when the ToS
        affirmatively permits automation, robots is not a disallow, an attributed
        review exists, and it is explicitly enabled. Reviewing != being allowed."""
        return (
            self.is_enabled
            and self.tos_status == "ALLOWED"
            and self.robots_status in ("ALLOWED", "NOT_APPLICABLE")
            and self.eligibility_reviewed_at is not None
            and bool(self.eligibility_reviewed_by)
        )


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
    external_ref: Mapped[str] = mapped_column(Text, nullable=False)
    # Minimal (DATA-D1.10): allowlisted leads only — never a copied competitor record.
    candidate_data: Mapped[dict | None] = mapped_column(JSONB)
    identity_status: Mapped[str] = mapped_column(
        candidate_identity_status, nullable=False, server_default=text("'UNRESOLVED'")
    )
    status: Mapped[str] = mapped_column(
        candidate_status, nullable=False, server_default=text("'DISCOVERED'")
    )
    # Trace = EXPLICIT confirmation of an authoritative source (H2). A bare
    # official-URL lead never sets these; only record_trace() does.
    trace_state: Mapped[str] = mapped_column(
        trace_state, nullable=False, server_default=text("'NOT_TRACED'")
    )
    trace_url: Mapped[str | None] = mapped_column(Text)
    trace_source_type: Mapped[str | None] = mapped_column(source_type)
    trace_verified_by: Mapped[str | None] = mapped_column(Text)
    trace_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    #: DATA-D1.LIVE §9.1 — THE claim-level provenance anchor. Every claim resolves
    #: to exactly one classified source (`DiscoverySource.source_class`), so two
    #: sources asserting the same value are two rows, never one blended row, and
    #: corroboration can be counted without being merged.
    #:
    #: NOT NULL + RESTRICT (migration 0004). Nullable + SET NULL failed Gate X
    #: twice: an unattributed claim could be inserted, and deleting a source would
    #: silently strip provenance from claims already made.
    discovery_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_source.id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_url: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    # DATA-D1.LIVE §9 (migration 0004) — extraction provenance. The exact
    # supporting passages live in `discovery_evidence_excerpt`, not here: one
    # claim may need several, and a column could hold only one.
    extractor_key: Mapped[str | None] = mapped_column(Text)
    extractor_version: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str | None] = mapped_column(extraction_method)
    #: LIVE.8: parser confidence, never verification. Has no VERIFIED value.
    extraction_confidence: Mapped[str | None] = mapped_column(extraction_confidence)
    crawl_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id", ondelete="SET NULL")
    )
    fetched_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fetched_page.id", ondelete="SET NULL")
    )
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
    # DATA-D1.LIVE §10 (migration 0004) — RETRIEVAL provenance, which is not the
    # same as claimed authorship. An image credited to a manufacturer but seen on
    # an aggregator is `retrieval_source_class = AGGREGATOR` (the Figure 02
    # precedent). Note what is deliberately ABSENT: no is_official, no
    # rights_status, no usage_basis. Those are MEDIA-01 verdicts made by a human,
    # and an extractor that could set them would bypass MEDIA-01 entirely.
    page_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declared_credit: Mapped[str | None] = mapped_column(Text)
    #: Who the page CLAIMS made it — a claim, never an attribution we assert.
    attribution_claimed: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str | None] = mapped_column(Text)
    retrieval_source_class: Mapped[str | None] = mapped_column(discovery_source_class)
    crawl_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id", ondelete="SET NULL")
    )
    fetched_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fetched_page.id", ondelete="SET NULL")
    )
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


# --------------------------------------------------------------- WS8.1 / R6 --
# Gap B5: `promotion_audit` is declared append-only in three places (this
# docstring, db/schema.sql:1187-1189, and the DATA-D1 contract) but nothing
# enforced it — SQLAdmin exposed full CRUD. WS8 gate R6 requires the promise to
# be **enforced by the application**, not merely documented.
#
# The listeners are registered at model-import time so every ORM session is
# covered: the API, the admin, and the governed promotion CLI alike.
#
# Honest scope: this is ORM-level enforcement. It stops `session.delete(...)`,
# attribute mutation and SQLAdmin's edit/delete paths. It does **not** stop raw
# SQL or a bulk Core `UPDATE`/`DELETE` issued against the table directly. A
# database-level guarantee would need a trigger, i.e. new DDL — out of scope for
# WS8.1, and any such enforcement must satisfy L7's database-enforcement clause.


class PromotionAuditImmutableError(RuntimeError):
    """Raised when an append-only promotion-audit row is modified or removed."""


@event.listens_for(PromotionAudit, "before_update", propagate=True)
def _promotion_audit_block_update(_mapper, _connection, target: PromotionAudit) -> None:
    raise PromotionAuditImmutableError(
        f"promotion_audit is append-only: refusing UPDATE of row {target.id!r}"
    )


@event.listens_for(PromotionAudit, "before_delete", propagate=True)
def _promotion_audit_block_delete(_mapper, _connection, target: PromotionAudit) -> None:
    raise PromotionAuditImmutableError(
        f"promotion_audit is append-only: refusing DELETE of row {target.id!r}"
    )
