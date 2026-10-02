"""G2-1 claim-proposal persistence — DR-A5 B-prime (migration 0018).

Mirror of the three tables in db/schema.sql (the DDL is canonical, AGENTS.md rule 2):

* `DiscoveryClaimProposal` — an immutable extraction proposal. Not a claim, never
  verified, never read by the public API, the catalogue or promotion.
* `DiscoveryProposalObservation` — an append-only sighting of a proposal on an
  observed page. An unchanged re-observation adds one of these and nothing else.
* `DiscoveryProposalDecision` — an append-only human ACCEPT / REJECT / DEFER with
  attribution, a rationale and the human's resolved choices. The newest
  `decision_seq` is effective. G2-1 turns no decision into an accepted claim.

All three are refused UPDATE/DELETE by database triggers; the ORM listeners below
are a backstop. A robot is referenced by `robot_slug` text, never a foreign key.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import extraction_confidence, extraction_method, proposal_decision_kind

_UUID_PK = dict(primary_key=True, server_default=text("gen_random_uuid()"))


class DiscoveryClaimProposal(Base):
    __tablename__ = "discovery_claim_proposal"
    __table_args__ = (
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name="ck_claim_proposal_digest"),
        CheckConstraint("slot_key ~ '^[0-9a-f]{64}$'", name="ck_claim_proposal_slot"),
        CheckConstraint("representability IN ('CLEAN', 'PARTIAL', 'UNREPRESENTABLE')",
                        name="ck_claim_proposal_representability"),
        CheckConstraint("claim_status = 'NOT_VERIFIED'", name="ck_claim_proposal_not_verified"),
        CheckConstraint("jsonb_typeof(review_questions) = 'array'",
                        name="ck_claim_proposal_review_questions"),
        CheckConstraint("jsonb_typeof(structured) = 'object'", name="ck_claim_proposal_structured"),
        CheckConstraint("btrim(evidence_excerpt) <> ''", name="ck_claim_proposal_excerpt"),
        CheckConstraint("btrim(evidence_locator) <> ''", name="ck_claim_proposal_locator"),
        CheckConstraint("btrim(robot_slug) <> ''", name="ck_claim_proposal_robot_slug"),
        CheckConstraint("btrim(ingested_by) <> ''", name="ck_claim_proposal_attributed"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    proposal_seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True, nullable=False)
    digest: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    slot_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_source.id", ondelete="RESTRICT"),
        nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    robot_slug: Mapped[str] = mapped_column(Text, nullable=False)
    edition: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    representability: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    structured: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    evidence_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_locator: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(extraction_method, nullable=False)
    extraction_confidence: Mapped[str] = mapped_column(extraction_confidence, nullable=False)
    claim_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'NOT_VERIFIED'"))
    gap: Mapped[str | None] = mapped_column(Text)
    review_questions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    extractor_key: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    origin_fetched_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fetched_page.id", ondelete="RESTRICT"), nullable=False)
    origin_crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id", ondelete="RESTRICT"), nullable=False)
    origin_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    origin_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False)


class DiscoveryProposalObservation(Base):
    __tablename__ = "discovery_proposal_observation"
    __table_args__ = (
        UniqueConstraint("proposal_id", "fetched_page_id", name="uq_proposal_observation"),
        CheckConstraint("btrim(observed_by) <> ''", name="ck_proposal_observation_attributed"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    observation_seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True, nullable=False)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_claim_proposal.id", ondelete="RESTRICT"),
        nullable=False)
    fetched_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fetched_page.id", ondelete="RESTRICT"), nullable=False)
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id", ondelete="RESTRICT"), nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False)


class DiscoveryProposalDecision(Base):
    __tablename__ = "discovery_proposal_decision"
    __table_args__ = (
        CheckConstraint("btrim(decided_by) <> ''", name="ck_proposal_decision_attributed"),
        CheckConstraint("btrim(rationale) <> ''", name="ck_proposal_decision_reasoned"),
        CheckConstraint("jsonb_typeof(resolved_choices) = 'object'",
                        name="ck_proposal_decision_choices"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    decision_seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True, nullable=False)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_claim_proposal.id", ondelete="RESTRICT"),
        nullable=False)
    decision: Mapped[str] = mapped_column(proposal_decision_kind, nullable=False)
    decided_by: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_choices: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False)


class ProposalImmutableError(RuntimeError):
    """Raised when an immutable / append-only proposal-layer row is changed or removed."""


def _refuse(kind: str):
    def listener(_mapper, _connection, target) -> None:
        raise ProposalImmutableError(
            f"{target.__tablename__} is append-only: refusing {kind} of row {target.id!r}. "
            "Record a new row instead.")
    return listener


# ORM backstop; the database triggers (trg_*_no_update / trg_*_no_delete) are the real gate.
for _model in (DiscoveryClaimProposal, DiscoveryProposalObservation, DiscoveryProposalDecision):
    event.listen(_model, "before_update", _refuse("UPDATE"), propagate=True)
    event.listen(_model, "before_delete", _refuse("DELETE"), propagate=True)
