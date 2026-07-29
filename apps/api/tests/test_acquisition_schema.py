"""DATA-D1.LIVE Slice A — schema, drift and canonical-isolation gates.

Slice A is schema only: the acquisition layer can *record* a run, and nothing in
this repository can perform one. These tests assert exactly that, plus the
structural invariants the ratified contract (docs/16) depends on:

  * the six acquisition tables exist with the ratified shape;
  * `discovery_source_class` was widened ADDITIVELY — every value DATA-D1 shipped
    survives, unrenamed and unremoved;
  * §9.1 claim-level provenance: one claim resolves to exactly one classified
    source, two sources are two rows, and promotion never rewrites a class;
  * LIVE.7: a maturity signal physically cannot write an availability value;
  * LIVE.6/D-7: excerpts are capped at 1000 UNICODE CHARACTERS, not bytes;
  * LIVE.10: `fetched_page` has no body column;
  * §5: the eligibility review is append-only;
  * no acquisition model can mutate a canonical catalogue table;
  * migration `0004` converges a `0003`-era database onto the baseline.

Every DB test runs inside a transaction that is rolled back, so nothing touches
the shared seeded database.
"""
from __future__ import annotations

import pathlib
import re
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models import acquisition as acq
from app.models.acquisition import (
    EVIDENCE_EXCERPT_MAX_CHARS,
    CandidateCommercialSignal,
    CrawlRun,
    DiscoveryEvidenceExcerpt,
    EligibilityReviewImmutableError,
    ExtractionResult,
    FetchedPage,
    SourceEligibilityReview,
)
from app.models.discovery import CandidateClaim, DiscoveryCandidate, DiscoverySource

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "db" / "schema.sql"
MIGRATION_0004 = ROOT / "db" / "migrations" / "0004_add_live_acquisition_layer.sql"

#: The six source-agnostic tables §16 ratifies for Slice A.
ACQUISITION_TABLES = {
    "source_eligibility_review",
    "crawl_run",
    "fetched_page",
    "extraction_result",
    "candidate_commercial_signal",
    "discovery_evidence_excerpt",
}

#: Canonical catalogue tables. Nothing in the acquisition layer may write these.
CANONICAL_TABLES = {
    "robot", "manufacturer", "robot_variant", "specification", "spec_definition",
    "pricing_offer", "availability_offer", "deployment", "provider", "region",
    "capability", "robot_capability", "use_case", "use_case_fit", "evidence_source",
    "robot_image", "commercial_lead", "buyer_requirement", "match_result",
}

#: Values DATA-D1 shipped in migration 0003. DATA-D1.LIVE §4 widened the enum
#: additively, so every one of these must survive verbatim.
DATA_D1_SOURCE_CLASSES = {
    "COMPETITOR_DIRECTORY", "MARKETPLACE", "EDITORIAL", "SEARCH_RESULT",
    "DISTRIBUTOR", "MANUFACTURER", "PRESS_RELEASE", "OFFICIAL_DOCUMENT",
    "OFFICIAL_VIDEO", "OTHER",
}
DATA_D1_LIVE_SOURCE_CLASSES = {
    "AGGREGATOR", "AUTHORIZED_DISTRIBUTOR", "OFFICIAL_STORE", "COMMUNITY",
}


@pytest.fixture
def dsession(database_url) -> Session:
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        conn.close()


def _source(session: Session, *, key: str, source_class: str = "MANUFACTURER") -> DiscoverySource:
    source = DiscoverySource(key=key, name=key, source_class=source_class)
    session.add(source)
    session.flush()
    return source


def _candidate(session: Session, source: DiscoverySource, ref: str) -> DiscoveryCandidate:
    candidate = DiscoveryCandidate(
        source_id=source.id, candidate_name="Zeta ZX-1", external_ref=ref
    )
    session.add(candidate)
    session.flush()
    return candidate


def _run(session: Session, source: DiscoverySource) -> CrawlRun:
    run = CrawlRun(
        source_id=source.id, adapter_key="test", adapter_version="0.1",
        operator="tester",
    )
    session.add(run)
    session.flush()
    return run


# --------------------------------------------------------------------------- #
# The six tables exist, with the ratified columns
# --------------------------------------------------------------------------- #
def test_all_six_acquisition_tables_exist(database_url) -> None:
    present = set(inspect(engine).get_table_names(schema="humanoid"))
    assert ACQUISITION_TABLES <= present, ACQUISITION_TABLES - present


def test_fetched_page_has_no_body_column(database_url) -> None:
    """LIVE.10: the evidence of what a page said is durable; the page is not.

    A body column would turn the discovery layer into the site mirror DATA-D1.10
    forbids, and would put third-party page content in our database whether or
    not the terms allowed it."""
    columns = {c["name"] for c in inspect(engine).get_columns("fetched_page", schema="humanoid")}
    for forbidden in ("body", "content", "html", "raw", "body_text", "payload"):
        assert forbidden not in columns, f"fetched_page must not store bodies: {forbidden}"
    assert {"content_hash", "etag", "last_modified", "outcome"} <= columns


def test_crawl_run_records_the_named_human_and_manual_trigger(database_url) -> None:
    """LIVE.4: a run is started by a person, locally. `crawl_trigger` has exactly
    one value so adding an automated trigger is a visible schema change."""
    columns = {
        c["name"]: c for c in inspect(engine).get_columns("crawl_run", schema="humanoid")
    }
    assert columns["operator"]["nullable"] is False
    with engine.connect() as conn:
        values = conn.execute(text(
            "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid"
            " WHERE t.typname = 'crawl_trigger'"
        )).scalars().all()
    assert values == ["MANUAL"]


def test_extraction_confidence_has_no_verified_value(database_url) -> None:
    """LIVE.8 / D-6 expressed in the type system: a parser cannot express
    verification, because there is no value for it to write."""
    with engine.connect() as conn:
        values = set(conn.execute(text(
            "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid"
            " WHERE t.typname = 'extraction_confidence'"
        )).scalars().all())
    assert values == {"LOW", "MEDIUM", "HIGH"}
    assert "VERIFIED" not in values


# --------------------------------------------------------------------------- #
# §4 — the enum widening is additive
# --------------------------------------------------------------------------- #
def test_source_class_widening_preserves_every_existing_value(database_url) -> None:
    """No rename, no removal, no re-mapping. A database carrying MANUFACTURER or
    EDITORIAL rows from 0003 must be untouched by 0004."""
    with engine.connect() as conn:
        values = set(conn.execute(text(
            "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid"
            " WHERE t.typname = 'discovery_source_class'"
        )).scalars().all())
    missing = DATA_D1_SOURCE_CLASSES - values
    assert not missing, f"0004 removed or renamed shipped values: {missing}"
    assert DATA_D1_LIVE_SOURCE_CLASSES <= values


def test_migration_0004_only_adds_enum_values(database_url) -> None:
    """The migration text itself must not contain a destructive enum operation —
    ALTER TYPE ... RENAME VALUE / DROP TYPE would rewrite shipped history."""
    sql = MIGRATION_0004.read_text(encoding="utf-8")
    assert "ADD VALUE IF NOT EXISTS" in sql
    assert "RENAME VALUE" not in sql
    assert not re.search(r"DROP\s+TYPE", sql, re.I)
    assert not re.search(r"DROP\s+TABLE", sql, re.I)
    assert not re.search(r"DROP\s+COLUMN", sql, re.I)


@pytest.mark.parametrize("source_class", sorted(DATA_D1_LIVE_SOURCE_CLASSES))
def test_new_source_classes_are_usable(dsession: Session, source_class: str) -> None:
    source = _source(dsession, key=f"src-{source_class.lower()}", source_class=source_class)
    assert source.source_class == source_class
    #: Class predicts nothing about eligibility (§5) — a new class is still
    #: disabled until an affirmative review enables it.
    assert source.radar_eligible is False


# --------------------------------------------------------------------------- #
# §9.1 — claim-level provenance
# --------------------------------------------------------------------------- #
def test_a_claim_resolves_to_exactly_one_classified_source(dsession: Session) -> None:
    source = _source(dsession, key="prov-one", source_class="AGGREGATOR")
    candidate = _candidate(dsession, source, "prov-1")
    claim = CandidateClaim(
        candidate_id=candidate.id, field_key="payload_kg", claimed_value="30",
        discovery_source_id=source.id,
    )
    dsession.add(claim)
    dsession.flush()

    resolved = dsession.execute(
        select(DiscoverySource.source_class)
        .join(CandidateClaim, CandidateClaim.discovery_source_id == DiscoverySource.id)
        .where(CandidateClaim.id == claim.id)
    ).scalar_one()
    assert resolved == "AGGREGATOR"


def test_two_sources_asserting_the_same_value_are_two_rows(dsession: Session) -> None:
    """The owner's 30/35/30 kg case. Corroboration must be COUNTABLE without
    being merged: a blended row would erase which source said what, and an
    aggregator's agreement would silently inherit a manufacturer's authority."""
    manufacturer = _source(dsession, key="prov-mfr", source_class="MANUFACTURER")
    aggregator = _source(dsession, key="prov-agg", source_class="AGGREGATOR")
    candidate = _candidate(dsession, manufacturer, "prov-2")

    for source in (manufacturer, aggregator):
        dsession.add(CandidateClaim(
            candidate_id=candidate.id, field_key="payload_kg", claimed_value="30",
            discovery_source_id=source.id,
        ))
    dsession.flush()

    rows = dsession.execute(
        select(CandidateClaim).where(
            CandidateClaim.candidate_id == candidate.id,
            CandidateClaim.field_key == "payload_kg",
        )
    ).scalars().all()
    assert len(rows) == 2, "same value from two sources must stay two attributed rows"
    assert {r.discovery_source_id for r in rows} == {manufacturer.id, aggregator.id}
    # Both still unverified: agreement raises priority, never confidence.
    assert {r.claim_status for r in rows} == {"NOT_VERIFIED"}


def test_a_conflicting_value_is_preserved_alongside_not_overwritten(dsession: Session) -> None:
    """35 kg from an aggregator does not replace 30 kg from the manufacturer, and
    does not get averaged into it (DATA-D1.8)."""
    manufacturer = _source(dsession, key="conf-mfr", source_class="MANUFACTURER")
    aggregator = _source(dsession, key="conf-agg", source_class="AGGREGATOR")
    candidate = _candidate(dsession, manufacturer, "conf-1")
    dsession.add_all([
        CandidateClaim(candidate_id=candidate.id, field_key="payload_kg",
                       claimed_value="30", discovery_source_id=manufacturer.id),
        CandidateClaim(candidate_id=candidate.id, field_key="payload_kg",
                       claimed_value="35", discovery_source_id=aggregator.id),
    ])
    dsession.flush()

    values = dsession.execute(
        select(CandidateClaim.claimed_value)
        .where(CandidateClaim.candidate_id == candidate.id)
    ).scalars().all()
    assert sorted(values) == ["30", "35"]


def test_a_commercial_signal_cannot_be_unattributed(dsession: Session) -> None:
    """§9.1: there is no 'unknown source' fallback. `discovery_source_id` is
    NOT NULL on this new table, so an unattributed commercial signal — the most
    dangerous kind — cannot be written at all."""
    source = _source(dsession, key="sig-src")
    candidate = _candidate(dsession, source, "sig-1")
    dsession.add(CandidateCommercialSignal(
        candidate_id=candidate.id, axis="MATURITY", maturity_value="COMMERCIAL",
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


# --------------------------------------------------------------------------- #
# LIVE.7 — the three axes cannot merge
# --------------------------------------------------------------------------- #
def test_a_maturity_signal_cannot_write_availability(dsession: Session) -> None:
    """The law as a constraint rather than a convention: `ANNOUNCED` can never
    become `NOT_AVAILABLE`, because the row is rejected by the database."""
    source = _source(dsession, key="axis-1")
    candidate = _candidate(dsession, source, "axis-1")
    dsession.add(CandidateCommercialSignal(
        candidate_id=candidate.id, discovery_source_id=source.id,
        axis="MATURITY", maturity_value="ANNOUNCED",
        availability_value="NOT_AVAILABLE",
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_an_obtainability_signal_cannot_write_maturity_or_price(dsession: Session) -> None:
    source = _source(dsession, key="axis-2")
    candidate = _candidate(dsession, source, "axis-2")
    dsession.add(CandidateCommercialSignal(
        candidate_id=candidate.id, discovery_source_id=source.id,
        axis="OBTAINABILITY", availability_value="AVAILABLE",
        maturity_value="COMMERCIAL",
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


@pytest.mark.parametrize(
    ("axis", "kwargs"),
    [
        ("MATURITY", {"maturity_value": "COMMERCIAL"}),
        ("OBTAINABILITY", {"availability_value": "ON_REQUEST",
                           "transaction_type": "PURCHASE", "region_code": "US"}),
        ("PRICE", {"price_type": "QUOTE_ONLY"}),
    ],
)
def test_each_axis_accepts_only_its_own_value(dsession: Session, axis, kwargs) -> None:
    source = _source(dsession, key=f"axis-ok-{axis.lower()}")
    candidate = _candidate(dsession, source, f"axis-ok-{axis}")
    signal = CandidateCommercialSignal(
        candidate_id=candidate.id, discovery_source_id=source.id, axis=axis, **kwargs
    )
    dsession.add(signal)
    dsession.flush()
    assert signal.claim_status == "NOT_VERIFIED"


def test_quote_only_needs_no_price_amount(dsession: Session) -> None:
    """QUOTE_ONLY is a real price fact with no number — it must never be coerced
    into UNKNOWN, and must not require an amount."""
    source = _source(dsession, key="price-quote")
    candidate = _candidate(dsession, source, "price-quote")
    signal = CandidateCommercialSignal(
        candidate_id=candidate.id, discovery_source_id=source.id,
        axis="PRICE", price_type="QUOTE_ONLY",
    )
    dsession.add(signal)
    dsession.flush()
    assert signal.price_amount is None


def test_a_price_amount_requires_currency_and_semantics(dsession: Session) -> None:
    """A bare number is not a price: $13,500 means nothing without a currency and
    without saying whether it is public, estimated or a starting figure."""
    source = _source(dsession, key="price-bare")
    candidate = _candidate(dsession, source, "price-bare")
    dsession.add(CandidateCommercialSignal(
        candidate_id=candidate.id, discovery_source_id=source.id,
        axis="PRICE", price_amount=13500,
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


# --------------------------------------------------------------------------- #
# LIVE.6 / D-7 — evidence excerpts
# --------------------------------------------------------------------------- #
def test_excerpt_limit_is_one_thousand_unicode_characters(dsession: Session) -> None:
    """`char_length`, not `octet_length`. A multi-byte excerpt gets the full
    thousand characters the ratified limit promises, rather than a silently
    smaller allowance."""
    source = _source(dsession, key="exc-1")
    run = _run(dsession, source)
    # 1000 multi-byte characters = 3000 bytes. Must be ACCEPTED.
    multibyte = "ä" * EVIDENCE_EXCERPT_MAX_CHARS
    excerpt = DiscoveryEvidenceExcerpt(
        subject_type="CLAIM", subject_id=uuid.uuid4(), crawl_run_id=run.id,
        excerpt_text=multibyte, page_url="https://example.invalid/p",
        retrieved_at=datetime.now(UTC), ordinal=0,
    )
    dsession.add(excerpt)
    dsession.flush()
    assert len(excerpt.excerpt_text) == 1000


def test_an_over_length_excerpt_is_refused(dsession: Session) -> None:
    source = _source(dsession, key="exc-2")
    run = _run(dsession, source)
    dsession.add(DiscoveryEvidenceExcerpt(
        subject_type="CLAIM", subject_id=uuid.uuid4(), crawl_run_id=run.id,
        excerpt_text="x" * (EVIDENCE_EXCERPT_MAX_CHARS + 1),
        page_url="https://example.invalid/p", retrieved_at=datetime.now(UTC),
    ))
    with pytest.raises((IntegrityError, DataError)):
        dsession.flush()


def test_a_blank_excerpt_is_refused(dsession: Session) -> None:
    """'The page implied it' is not evidence (LIVE.6)."""
    source = _source(dsession, key="exc-3")
    run = _run(dsession, source)
    dsession.add(DiscoveryEvidenceExcerpt(
        subject_type="CLAIM", subject_id=uuid.uuid4(), crawl_run_id=run.id,
        excerpt_text="   ", page_url="https://example.invalid/p",
        retrieved_at=datetime.now(UTC),
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_one_claim_may_carry_several_ordered_excerpts(dsession: Session) -> None:
    """A price and the region it applies to may sit in different parts of a page,
    so one passage often cannot justify a claim (D-7)."""
    source = _source(dsession, key="exc-4")
    run = _run(dsession, source)
    subject = uuid.uuid4()
    for ordinal, body in enumerate(["$13,500", "Ships to US only"]):
        dsession.add(DiscoveryEvidenceExcerpt(
            subject_type="COMMERCIAL_SIGNAL", subject_id=subject, crawl_run_id=run.id,
            excerpt_text=body, page_url="https://example.invalid/p",
            retrieved_at=datetime.now(UTC), ordinal=ordinal,
        ))
    dsession.flush()
    rows = dsession.execute(
        select(DiscoveryEvidenceExcerpt)
        .where(DiscoveryEvidenceExcerpt.subject_id == subject)
        .order_by(DiscoveryEvidenceExcerpt.ordinal)
    ).scalars().all()
    assert [r.excerpt_text for r in rows] == ["$13,500", "Ships to US only"]


def test_excerpt_ordinals_are_unique_per_subject(dsession: Session) -> None:
    source = _source(dsession, key="exc-5")
    run = _run(dsession, source)
    subject = uuid.uuid4()
    for _ in range(2):
        dsession.add(DiscoveryEvidenceExcerpt(
            subject_type="CLAIM", subject_id=subject, crawl_run_id=run.id,
            excerpt_text="same ordinal", page_url="https://example.invalid/p",
            retrieved_at=datetime.now(UTC), ordinal=0,
        ))
    with pytest.raises(IntegrityError):
        dsession.flush()


# --------------------------------------------------------------------------- #
# §5 — the eligibility review is append-only
# --------------------------------------------------------------------------- #
def test_an_eligibility_review_cannot_be_updated(dsession: Session) -> None:
    """An eligibility decision authorizes contacting a third party. If it could be
    edited, an authorization could be backdated and DATA-D1.9 would be forgeable."""
    source = _source(dsession, key="elig-1")
    review = SourceEligibilityReview(
        source_id=source.id, reviewed_by="reviewer", tos_decision="PROHIBITED",
        robots_decision="ALLOWED", recommendation="PROHIBITED",
    )
    dsession.add(review)
    dsession.flush()

    review.tos_decision = "ALLOWED"
    with pytest.raises(EligibilityReviewImmutableError):
        dsession.flush()


def test_an_eligibility_review_cannot_be_deleted(dsession: Session) -> None:
    source = _source(dsession, key="elig-2")
    review = SourceEligibilityReview(source_id=source.id, reviewed_by="reviewer")
    dsession.add(review)
    dsession.flush()
    dsession.delete(review)
    with pytest.raises(EligibilityReviewImmutableError):
        dsession.flush()


def test_appending_a_new_review_is_the_supported_correction(dsession: Session) -> None:
    """Re-review is how a decision changes: the history is preserved, so 'this was
    prohibited in July and permitted in September' remains auditable."""
    source = _source(dsession, key="elig-3")
    dsession.add(SourceEligibilityReview(
        source_id=source.id, reviewed_by="reviewer", tos_decision="PROHIBITED"))
    dsession.flush()
    dsession.add(SourceEligibilityReview(
        source_id=source.id, reviewed_by="reviewer", tos_decision="ALLOWED"))
    dsession.flush()

    decisions = dsession.execute(
        select(SourceEligibilityReview.tos_decision)
        .where(SourceEligibilityReview.source_id == source.id)
    ).scalars().all()
    assert sorted(decisions) == ["ALLOWED", "PROHIBITED"]


def test_an_unattributed_review_is_refused(dsession: Session) -> None:
    """DATA-D1.9: reviewing is not being allowed, and an unattributed review is
    not a review."""
    source = _source(dsession, key="elig-4")
    dsession.add(SourceEligibilityReview(source_id=source.id))
    with pytest.raises(IntegrityError):
        dsession.flush()


# --------------------------------------------------------------------------- #
# crawl_run integrity
# --------------------------------------------------------------------------- #
def test_a_finished_run_must_say_when_it_finished(dsession: Session) -> None:
    source = _source(dsession, key="run-1")
    dsession.add(CrawlRun(
        source_id=source.id, adapter_key="a", adapter_version="1",
        operator="op", status="COMPLETED",
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_a_running_run_must_not_claim_a_finish_time(dsession: Session) -> None:
    source = _source(dsession, key="run-2")
    dsession.add(CrawlRun(
        source_id=source.id, adapter_key="a", adapter_version="1", operator="op",
        status="RUNNING", finished_at=datetime.now(UTC),
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_halted_by_policy_is_a_first_class_outcome(dsession: Session) -> None:
    """Robots changed, or the terms review expired mid-run. That is a policy
    outcome to record, not an error to retry."""
    source = _source(dsession, key="run-3")
    run = CrawlRun(
        source_id=source.id, adapter_key="a", adapter_version="1", operator="op",
        status="HALTED_BY_POLICY", finished_at=datetime.now(UTC),
    )
    dsession.add(run)
    dsession.flush()
    assert run.status == "HALTED_BY_POLICY"


def test_a_run_cannot_resume_itself(dsession: Session) -> None:
    source = _source(dsession, key="run-4")
    run = _run(dsession, source)
    run.resume_of_run_id = run.id
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_a_resumed_run_links_to_its_parent(dsession: Session) -> None:
    source = _source(dsession, key="run-5")
    parent = _run(dsession, source)
    child = CrawlRun(
        source_id=source.id, adapter_key="a", adapter_version="1", operator="op",
        resume_of_run_id=parent.id,
    )
    dsession.add(child)
    dsession.flush()
    assert child.resume_of_run_id == parent.id


# --------------------------------------------------------------------------- #
# Canonical isolation — the invariant the whole contract protects
# --------------------------------------------------------------------------- #
def test_no_canonical_table_references_the_acquisition_layer(database_url) -> None:
    """Gate K, extended to the new tables. Canonical truth must not depend on
    research rows: a canonical FK into the discovery layer would make deleting a
    candidate a canonical-integrity problem."""
    inspector = inspect(engine)
    offenders: list[str] = []
    for table in sorted(CANONICAL_TABLES):
        for fk in inspector.get_foreign_keys(table, schema="humanoid"):
            if fk["referred_table"] in ACQUISITION_TABLES:
                offenders.append(f"{table}.{fk['constrained_columns']} -> {fk['referred_table']}")
    assert offenders == [], offenders


def test_acquisition_models_declare_no_canonical_foreign_key(database_url) -> None:
    """Structural, not behavioural: none of the six tables can even NAME a
    canonical row, so there is no column through which one could be mutated."""
    inspector = inspect(engine)
    offenders: list[str] = []
    for table in sorted(ACQUISITION_TABLES):
        for fk in inspector.get_foreign_keys(table, schema="humanoid"):
            if fk["referred_table"] in CANONICAL_TABLES:
                offenders.append(f"{table} -> {fk['referred_table']}")
    assert offenders == [], (
        f"acquisition tables must not reference canonical rows: {offenders}"
    )


def test_no_acquisition_model_maps_a_canonical_table(database_url) -> None:
    """A model mapped onto `robot` or `manufacturer` inside the acquisition module
    would be a write path into the catalogue regardless of intent."""
    mapped = {
        obj.__tablename__
        for obj in vars(acq).values()
        if isinstance(obj, type) and hasattr(obj, "__tablename__")
    }
    assert mapped & CANONICAL_TABLES == set(), mapped & CANONICAL_TABLES
    assert mapped <= ACQUISITION_TABLES, mapped - ACQUISITION_TABLES


def test_recording_a_full_acquisition_run_writes_no_canonical_row(dsession: Session) -> None:
    """The §18 report line `Canonical rows written = 0`, asserted rather than
    hoped: exercise every acquisition table and count the catalogue before and
    after."""
    counts_before = {
        table: dsession.execute(
            text(f"SELECT count(*) FROM humanoid.{table}")  # noqa: S608 - fixed allowlist
        ).scalar_one()
        for table in sorted(CANONICAL_TABLES)
    }

    source = _source(dsession, key="full-run", source_class="AGGREGATOR")
    dsession.add(SourceEligibilityReview(
        source_id=source.id, reviewed_by="reviewer", tos_decision="ALLOWED",
        robots_decision="ALLOWED", recommendation="ALLOWED",
    ))
    run = _run(dsession, source)
    page = FetchedPage(
        crawl_run_id=run.id, source_id=source.id,
        url="https://example.invalid/robots/zeta", outcome="FETCHED",
        http_status=200, content_hash="a" * 64,
    )
    dsession.add(page)
    dsession.flush()
    candidate = _candidate(dsession, source, "full-run-1")
    dsession.add(ExtractionResult(
        crawl_run_id=run.id, fetched_page_id=page.id, candidate_id=candidate.id,
        extractor_key="test", extractor_version="0.1", status="EXTRACTED",
    ))
    claim = CandidateClaim(
        candidate_id=candidate.id, field_key="height_cm", claimed_value="170",
        discovery_source_id=source.id, crawl_run_id=run.id, fetched_page_id=page.id,
        extraction_method="SELECTOR", extraction_confidence="HIGH",
    )
    dsession.add(claim)
    signal = CandidateCommercialSignal(
        candidate_id=candidate.id, discovery_source_id=source.id,
        axis="PRICE", price_type="PUBLIC", price_amount=13500, price_currency="USD",
        crawl_run_id=run.id, fetched_page_id=page.id,
    )
    dsession.add(signal)
    dsession.flush()
    dsession.add(DiscoveryEvidenceExcerpt(
        subject_type="COMMERCIAL_SIGNAL", subject_id=signal.id, crawl_run_id=run.id,
        fetched_page_id=page.id, excerpt_text="$13,500 USD",
        page_url=page.url, retrieved_at=datetime.now(UTC), locator=".price",
    ))
    dsession.flush()

    counts_after = {
        table: dsession.execute(
            text(f"SELECT count(*) FROM humanoid.{table}")  # noqa: S608 - fixed allowlist
        ).scalar_one()
        for table in sorted(CANONICAL_TABLES)
    }
    assert counts_after == counts_before, "acquisition wrote a canonical row"
    # And the claim it did write is unverified, attributed, and aggregator-class.
    assert claim.claim_status == "NOT_VERIFIED"
    assert signal.claim_status == "NOT_VERIFIED"


# --------------------------------------------------------------------------- #
# Schema <-> model drift
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("table", sorted(ACQUISITION_TABLES))
def test_model_columns_match_the_database(database_url, table: str) -> None:
    """`db/schema.sql` is canonical (AGENTS.md rule 2); the models mirror it. A
    column present in one and not the other is drift, and drift is how a model
    starts quietly lying about what is stored."""
    from app.db.base import Base

    model = next(
        m.class_ for m in Base.registry.mappers if m.class_.__tablename__ == table
    )
    db_columns = {c["name"] for c in inspect(engine).get_columns(table, schema="humanoid")}
    model_columns = {c.name for c in model.__table__.columns}
    assert model_columns == db_columns, (
        f"{table}: only in model {model_columns - db_columns}, "
        f"only in database {db_columns - model_columns}"
    )


@pytest.mark.parametrize(
    "table", ["discovery_source", "candidate_claim", "candidate_image_ref"]
)
def test_extended_discovery_models_match_the_database(database_url, table: str) -> None:
    """The 0003 tables gained additive columns; the mirror must be exact there too."""
    from app.db.base import Base

    model = next(
        m.class_ for m in Base.registry.mappers if m.class_.__tablename__ == table
    )
    db_columns = {c["name"] for c in inspect(engine).get_columns(table, schema="humanoid")}
    model_columns = {c.name for c in model.__table__.columns}
    assert model_columns == db_columns, (
        f"{table}: only in model {model_columns - db_columns}, "
        f"only in database {db_columns - model_columns}"
    )


def test_schema_sql_and_migration_0004_declare_the_same_tables() -> None:
    """Migration drift is the failure the migrations README warns about: the
    baseline and the forward migration must converge on the same shape."""
    schema = SCHEMA_SQL.read_text(encoding="utf-8")
    migration = MIGRATION_0004.read_text(encoding="utf-8")
    for table in sorted(ACQUISITION_TABLES):
        assert re.search(rf"CREATE TABLE {table}\b", schema), f"{table} missing from schema.sql"
        assert re.search(
            rf"CREATE TABLE IF NOT EXISTS {table}\b", migration
        ), f"{table} missing from migration 0004"


# --------------------------------------------------------------------------- #
# Slice A carries no acquisition MACHINERY — only the schema
# --------------------------------------------------------------------------- #
def test_slice_a_adds_no_http_client_or_crawler(database_url) -> None:
    """The authorized exclusions, asserted against the source tree rather than
    trusted: Slice A is schema only."""
    forbidden = re.compile(
        r"\b(?:import\s+(?:requests|httpx|aiohttp|urllib3|selenium|playwright)"
        r"|from\s+(?:requests|httpx|aiohttp|selenium|playwright)\s+import"
        r"|urllib\.request|robotparser|RobotFileParser)\b"
    )
    offenders: list[str] = []
    for path in (ROOT / "apps" / "api" / "app").rglob("*.py"):
        if forbidden.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"Slice A must add no fetching machinery: {offenders}"


def test_acquisition_module_imports_no_network_or_scheduler(database_url) -> None:
    source = (ROOT / "apps" / "api" / "app" / "models" / "acquisition.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("requests", "httpx", "urllib", "socket", "asyncio",
                      "schedule", "celery", "apscheduler", "subprocess"):
        assert f"import {forbidden}" not in source, forbidden


def test_commercial_routing_fields_are_not_implemented(database_url) -> None:
    """§16.1 fields are canonical and explicitly NOT in Slice A — they need their
    own ratification with the commercial workstream. Shipping them early would
    quietly create a merchant-of-record surface."""
    inspector = inspect(engine)
    all_columns: set[str] = set()
    for table in inspector.get_table_names(schema="humanoid"):
        all_columns |= {c["name"] for c in inspector.get_columns(table, schema="humanoid")}
    for field in (
        "official_purchase_url", "official_quote_url", "lead_route_type",
        "lead_recipient", "manufacturer_partner_status", "referral_tracking_code",
        "commission_model", "merchant_of_record", "transaction_completed_off_platform",
    ):
        assert field not in all_columns, f"§16.1 field {field} is out of Slice A scope"
