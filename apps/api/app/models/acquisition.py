"""Live-acquisition layer — DATA-D1.LIVE (docs/16, RATIFIED v0.1, main @ 6875a34).

Mirror of db/schema.sql SECTION 10 / db/migrations/0004. The DDL is canonical
(AGENTS.md rule 2); these models mirror it and never generate DDL.

**Slice A is SCHEMA ONLY.** These models exist so an acquisition run can be
*recorded*. There is no adapter, no HTTP client, no robots fetcher, no crawler
and no scheduler in this slice, and nothing here can perform a fetch.

Structural isolation (DATA-D1 §5 / DATA-D1.10 / Gate K) is preserved exactly as
the 0003 layer preserves it: every foreign key points INTO the discovery layer or
FROM discovery TO canonical, and no canonical table references back. None of
these models declares a relationship that could write `robot`, `manufacturer` or
any other canonical table — asserted by tests/test_acquisition_schema.py.

Claim-level provenance (§9.1): `candidate_claim.discovery_source_id` and
`CandidateCommercialSignal.discovery_source_id` are the anchors. One claim
resolves to exactly one classified source, so two sources asserting the same
value are two rows and never one blended row.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    availability_status,
    billing_period,
    buyer_type,
    candidate_entity_type,
    claim_status,
    commercial_status,
    crawl_run_status,
    crawl_trigger,
    eligibility_decision,
    evidence_subject_type,
    extraction_confidence,
    extraction_method,
    extraction_status,
    fetch_outcome,
    price_type,
    robots_status,
    signal_axis,
    transaction_type,
)

#: LIVE.6 / owner decision D-7 — per excerpt, in Unicode CHARACTERS.
EVIDENCE_EXCERPT_MAX_CHARS = 1000


class SourceEligibilityReview(Base):
    """DATA-D1.LIVE §5 — APPEND-ONLY eligibility history.

    `discovery_source` carries the *effective* decision; this carries its
    *history*, so a decision can be audited and re-reviewed rather than silently
    overwritten. It is append-only because this row is the artefact that
    authorizes contacting a third party: if it could be edited, an authorization
    could be backdated.

    Both axes are recorded separately, each with its own URL, hash and excerpt,
    because they genuinely disagree in practice — the first real assessment
    (2026-07-29) found official manufacturer sites whose robots.txt was
    permissive while their terms prohibited automated access outright.
    """

    __tablename__ = "source_eligibility_review"
    __table_args__ = (
        CheckConstraint(
            "(robots_excerpt IS NULL OR char_length(robots_excerpt) <= 1000)"
            " AND (tos_excerpt IS NULL OR char_length(tos_excerpt) <= 1000)",
            name="ck_source_eligibility_review_excerpt_len",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_source.id", ondelete="RESTRICT"),
        nullable=False,
    )
    robots_url: Mapped[str | None] = mapped_column(Text)
    robots_decision: Mapped[str] = mapped_column(
        robots_status, nullable=False, server_default=text("'UNKNOWN'")
    )
    robots_page_hash: Mapped[str | None] = mapped_column(Text)
    robots_excerpt: Mapped[str | None] = mapped_column(Text)
    tos_url: Mapped[str | None] = mapped_column(Text)
    tos_decision: Mapped[str] = mapped_column(
        eligibility_decision, nullable=False, server_default=text("'UNKNOWN'")
    )
    tos_page_hash: Mapped[str | None] = mapped_column(Text)
    tos_excerpt: Mapped[str | None] = mapped_column(Text)
    path_prefixes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    #: An unattributed review is not a review (DATA-D1.9).
    reviewed_by: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The assessment's recommendation, kept distinct from the owner's decision:
    #: assessing is evidence, enabling the source is a human act (§5 step 5).
    recommendation: Mapped[str] = mapped_column(
        eligibility_decision, nullable=False, server_default=text("'UNKNOWN'")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<SourceEligibilityReview source={self.source_id} "
            f"tos={self.tos_decision} robots={self.robots_decision}>"
        )


class CrawlRun(Base):
    """DATA-D1.LIVE §7 — one acquisition run.

    `trigger` is `MANUAL`-only in v0.1 (LIVE.4): a named human starts a run on a
    local machine. No scheduler, cron entry, queue or worker may start one, and
    the enum having a single value means adding an automated trigger is a visible
    schema change rather than a configuration flag.

    `HALTED_BY_POLICY` is a first-class outcome, not an error to retry: robots
    changed, the terms review expired mid-run, or the source began denying
    access.
    """

    __tablename__ = "crawl_run"
    __table_args__ = (
        CheckConstraint(
            "(status = 'RUNNING' AND finished_at IS NULL)"
            " OR (status <> 'RUNNING' AND finished_at IS NOT NULL)",
            name="ck_crawl_run_finished",
        ),
        CheckConstraint(
            "resume_of_run_id IS DISTINCT FROM id",
            name="ck_crawl_run_not_self_resume",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_source.id", ondelete="RESTRICT"),
        nullable=False,
    )
    adapter_key: Mapped[str] = mapped_column(Text, nullable=False)
    #: Bump => re-extraction of an unchanged page is meaningful (§8).
    adapter_version: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(
        crawl_trigger, nullable=False, server_default=text("'MANUAL'")
    )
    #: The named human who started it (LIVE.4).
    operator: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        crawl_run_status, nullable=False, server_default=text("'RUNNING'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume_of_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id", ondelete="SET NULL")
    )
    #: Planned URL set, limits, rate policy, UA string, robots hash, fixture mode.
    run_manifest: Mapped[dict | None] = mapped_column(JSONB)
    #: The §18 report figures, including `canonical_rows_written` — which must
    #: always be 0, printed on every run rather than assumed.
    counters: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<CrawlRun {self.adapter_key}@{self.adapter_version} status={self.status}>"


class FetchedPage(Base):
    """DATA-D1.LIVE §8 — per-URL outcome.

    **There is deliberately no body column** (LIVE.10 / owner decision D-3):
    bodies live in the content-addressed cache under `var/discovery/cache/`,
    outside the database and outside the build context. What is durable here is
    the hash, the validators and the outcome — the evidence of what a page said
    survives, the page itself does not.

    This table is also what makes a run resumable (§7): a resumed run skips URLs
    its parent already fetched successfully, rather than re-fetching "to be
    safe".
    """

    __tablename__ = "fetched_page"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_source.id", ondelete="RESTRICT"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(Text)
    content_length: Mapped[int | None] = mapped_column(Integer)
    #: SHA-256 of the normalized body: dedup + change detection without storage.
    content_hash: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(fetch_outcome, nullable=False)
    #: What robots said AT the moment of the request — never a stored decision.
    robots_decision_at_fetch: Mapped[str | None] = mapped_column(robots_status)
    error_class: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<FetchedPage {self.url!r} outcome={self.outcome}>"


class ExtractionResult(Base):
    """DATA-D1.LIVE §9 — what one extractor pass over one page produced.

    `AMBIGUOUS` is a real outcome routed to a human, never a guess (DATA-D1.6).
    """

    __tablename__ = "extraction_result"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id", ondelete="CASCADE"), nullable=False
    )
    fetched_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fetched_page.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_candidate.id", ondelete="SET NULL")
    )
    extractor_key: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(
        candidate_entity_type, nullable=False, server_default=text("'ROBOT'")
    )
    status: Mapped[str] = mapped_column(extraction_status, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class CandidateCommercialSignal(Base):
    """DATA-D1.LIVE §9 / LIVE.7 — one commercial signal on one axis.

    A commercial signal is not a scalar field/value pair, which is why it is not
    forced into `candidate_claim`. The three axes — maturity, obtainability and
    price semantics — are recorded separately and never merged into a single
    status label: a robot may legitimately be `AVAILABLE` for `PURCHASE` in one
    region and `ON_REQUEST` elsewhere, and no single label can express that.

    The database enforces the separation rather than trusting convention: the
    `ck_commercial_signal_axis_value` CHECK means a `MATURITY` signal physically
    cannot write an availability value. `UNKNOWN` is the absence of a signal and
    never becomes `NOT_AVAILABLE`; `QUOTE_ONLY` is a PRICE fact and never
    becomes `UNKNOWN`.

    `discovery_source_id` is NOT NULL here (§9.1): this is a new table, so there
    is no pre-existing unattributed row to accommodate, and an unattributed
    commercial signal is exactly the thing that must never exist.
    """

    __tablename__ = "candidate_commercial_signal"
    __table_args__ = (
        CheckConstraint(
            "(axis = 'MATURITY'      AND availability_value IS NULL AND price_type IS NULL)"
            " OR (axis = 'OBTAINABILITY' AND maturity_value IS NULL AND price_type IS NULL)"
            " OR (axis = 'PRICE'         AND maturity_value IS NULL"
            " AND availability_value IS NULL)",
            name="ck_commercial_signal_axis_value",
        ),
        CheckConstraint(
            "price_amount IS NULL"
            " OR (price_currency IS NOT NULL AND price_type IS NOT NULL)",
            name="ck_commercial_signal_price",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: §9.1 provenance anchor. One signal, one classified source.
    discovery_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_source.id", ondelete="RESTRICT"),
        nullable=False,
    )
    crawl_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id", ondelete="SET NULL")
    )
    fetched_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fetched_page.id", ondelete="SET NULL")
    )
    axis: Mapped[str] = mapped_column(signal_axis, nullable=False)
    maturity_value: Mapped[str | None] = mapped_column(commercial_status)
    availability_value: Mapped[str | None] = mapped_column(availability_status)
    transaction_type: Mapped[str | None] = mapped_column(transaction_type)
    region_code: Mapped[str | None] = mapped_column(Text)
    buyer_type: Mapped[str | None] = mapped_column(buyer_type)
    price_type: Mapped[str | None] = mapped_column(price_type)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_currency: Mapped[str | None] = mapped_column(Text)
    billing_period: Mapped[str | None] = mapped_column(billing_period)
    extractor_key: Mapped[str | None] = mapped_column(Text)
    extractor_version: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str | None] = mapped_column(extraction_method)
    extraction_confidence: Mapped[str | None] = mapped_column(extraction_confidence)
    #: Only a human moves this off NOT_VERIFIED (LIVE.8 / DATA-D1.2).
    claim_status: Mapped[str] = mapped_column(
        claim_status, nullable=False, server_default=text("'NOT_VERIFIED'")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class DiscoveryEvidenceExcerpt(Base):
    """DATA-D1.LIVE §9 / LIVE.6 (owner decision D-7) — an exact supporting passage.

    Excerpts are rows rather than a column because one passage often cannot
    justify a claim: a price and the region it applies to may sit in different
    parts of a page. So a claim or signal may carry **several**, ordered by
    `ordinal`.

    The 1000-character limit is in Unicode **characters** (`char_length`, not
    `octet_length`), and it is a retention limit rather than a licence to
    reassemble a page out of fragments — DATA-D1.10 and LIVE.10 still bind.
    """

    __tablename__ = "discovery_evidence_excerpt"
    __table_args__ = (
        CheckConstraint(
            f"char_length(excerpt_text) <= {EVIDENCE_EXCERPT_MAX_CHARS}",
            name="ck_evidence_excerpt_len",
        ),
        CheckConstraint("btrim(excerpt_text) <> ''", name="ck_evidence_excerpt_not_blank"),
        UniqueConstraint("subject_type", "subject_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    subject_type: Mapped[str] = mapped_column(evidence_subject_type, nullable=False)
    #: Soft reference to a claim / signal / image-ref row. Deliberately not three
    #: nullable FKs: one write path serves all three, and the (type, id) pair
    #: keeps the target unambiguous.
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    crawl_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_run.id", ondelete="SET NULL")
    )
    fetched_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fetched_page.id", ondelete="SET NULL")
    )
    excerpt_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    page_hash: Mapped[str | None] = mapped_column(Text)
    locator: Mapped[str | None] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


# --------------------------------------------------------- append-only (§5) --
# Same pattern, and the same honest scope, as `promotion_audit` (WS8.1 / R6): the
# listeners are registered at model-import time so every ORM session is covered —
# the API, the admin and any future CLI alike. This stops `session.delete(...)`,
# attribute mutation and SQLAdmin's edit/delete paths. It does NOT stop raw SQL
# or a bulk Core UPDATE/DELETE against the table; a database-level guarantee
# would need a trigger, which is new DDL and out of Slice A's authorized scope.
#
# Why it matters here specifically: an eligibility review is what authorizes
# contacting a third party. An editable authorization can be backdated, and the
# whole DATA-D1.9 gate would become forgeable.


class EligibilityReviewImmutableError(RuntimeError):
    """Raised when an append-only eligibility-review row is modified or removed."""


@event.listens_for(SourceEligibilityReview, "before_update", propagate=True)
def _eligibility_review_block_update(
    _mapper, _connection, target: SourceEligibilityReview
) -> None:
    raise EligibilityReviewImmutableError(
        "source_eligibility_review is append-only: refusing UPDATE of row "
        f"{target.id!r}. Record a NEW review instead — an eligibility decision "
        "is evidence, and evidence is not edited."
    )


@event.listens_for(SourceEligibilityReview, "before_delete", propagate=True)
def _eligibility_review_block_delete(
    _mapper, _connection, target: SourceEligibilityReview
) -> None:
    raise EligibilityReviewImmutableError(
        "source_eligibility_review is append-only: refusing DELETE of row "
        f"{target.id!r}"
    )
