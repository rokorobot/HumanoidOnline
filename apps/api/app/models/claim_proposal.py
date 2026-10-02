"""G2-1 / G2-3 claim-proposal persistence — DR-A5 B-prime (migration 0018).

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


class AcceptedClaim(Base):
    """G2-3 (migration 0019): an immutable accepted claim. Exists only from an effective
    ACCEPT on a CURRENT, non-stale proposal for a registered field policy; one per
    (decision, target). Not a catalogue fact until materialized through db/catalogue/."""

    __tablename__ = "accepted_claim"
    __table_args__ = (
        CheckConstraint("claim_digest ~ '^[0-9a-f]{64}$'", name="ck_accepted_claim_digest"),
        CheckConstraint(
            "target_kind IN ('robot_variant', 'specification', 'NO_CATALOGUE_HOME')",
            name="ck_accepted_claim_target_kind"),
        CheckConstraint("value_type IN ('TEXT')", name="ck_accepted_claim_value_type"),
        CheckConstraint(
            "edition_scope IS NULL OR edition_scope IN ('THIS_EDITION', 'PRODUCT_LINE', "
            "'PLATFORM')", name="ck_accepted_claim_scope"),
        CheckConstraint("target_kind <> 'robot_variant' OR variant_slug IS NOT NULL",
                        name="ck_accepted_claim_variant"),
        CheckConstraint("jsonb_typeof(resolved_choices) = 'object'",
                        name="ck_accepted_claim_choices"),
        CheckConstraint("btrim(created_by) <> ''", name="ck_accepted_claim_attributed"),
        CheckConstraint("btrim(robot_slug) <> ''", name="ck_accepted_claim_robot"),
        CheckConstraint("btrim(accepted_value) <> ''", name="ck_accepted_claim_value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    claim_seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True, nullable=False)
    claim_digest: Mapped[str] = mapped_column(Text, nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_proposal_decision.id", ondelete="RESTRICT"), nullable=False)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_claim_proposal.id", ondelete="RESTRICT"),
        nullable=False)
    proposal_digest: Mapped[str] = mapped_column(Text, nullable=False)
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_proposal_observation.id", ondelete="RESTRICT"), nullable=False)
    observation_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_source.id", ondelete="RESTRICT"),
        nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    robot_slug: Mapped[str] = mapped_column(Text, nullable=False)
    variant_slug: Mapped[str | None] = mapped_column(Text)
    edition_label: Mapped[str | None] = mapped_column(Text)
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_key: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_value: Mapped[str] = mapped_column(Text, nullable=False)
    edition_scope: Mapped[str | None] = mapped_column(Text)
    verbatim_value: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_locator: Mapped[str] = mapped_column(Text, nullable=False)
    policy_key: Mapped[str] = mapped_column(Text, nullable=False)
    registry_version: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_choices: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False)


class ClaimRetraction(Base):
    """G2-3: append-only withdrawal of an accepted claim, optionally naming its correction."""

    __tablename__ = "claim_retraction"
    __table_args__ = (
        CheckConstraint("btrim(retracted_by) <> ''", name="ck_claim_retraction_attributed"),
        CheckConstraint("btrim(reason) <> ''", name="ck_claim_retraction_reasoned"),
        CheckConstraint("replacement_claim_id IS DISTINCT FROM claim_id",
                        name="ck_claim_retraction_not_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    retraction_seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True, nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accepted_claim.id", ondelete="RESTRICT"),
        nullable=False, unique=True)
    replacement_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accepted_claim.id", ondelete="RESTRICT"))
    retracted_by: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False)


class CatalogueWriteAudit(Base):
    """G2-3: append-only record that a catalogue row exists because of an accepted claim.
    It records; the importer (M2) is the only writer of the catalogue."""

    __tablename__ = "catalogue_write_audit"
    __table_args__ = (
        CheckConstraint("method IN ('IMPORTER_M2')", name="ck_catalogue_write_audit_method"),
        CheckConstraint("target_table IN ('robot_variant', 'specification')",
                        name="ck_catalogue_write_audit_table"),
        CheckConstraint("after_hash ~ '^[0-9a-f]{64}$'", name="ck_catalogue_write_audit_after"),
        CheckConstraint("btrim(change_ref) <> ''", name="ck_catalogue_write_audit_change"),
        CheckConstraint("btrim(applied_by) <> ''", name="ck_catalogue_write_audit_attributed"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    audit_seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True, nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accepted_claim.id", ondelete="RESTRICT"),
        nullable=False)
    robot_slug: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    change_ref: Mapped[str] = mapped_column(Text, nullable=False)
    importer_run_ref: Mapped[str | None] = mapped_column(Text)
    target_table: Mapped[str] = mapped_column(Text, nullable=False)
    target_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    before_hash: Mapped[str | None] = mapped_column(Text)
    after_hash: Mapped[str] = mapped_column(Text, nullable=False)
    applied_by: Mapped[str] = mapped_column(Text, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
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
for _model in (DiscoveryClaimProposal, DiscoveryProposalObservation,
               DiscoveryProposalDecision, AcceptedClaim, ClaimRetraction,
               CatalogueWriteAudit):
    event.listen(_model, "before_update", _refuse("UPDATE"), propagate=True)
    event.listen(_model, "before_delete", _refuse("DELETE"), propagate=True)
