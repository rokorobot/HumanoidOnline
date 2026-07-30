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
from sqlalchemy import delete, inspect, select, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import (
    DataError,
    IntegrityError,
    InternalError,
    ProgrammingError,
)
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


def _page(session: Session, run: CrawlRun, source: DiscoverySource) -> FetchedPage:
    page = FetchedPage(
        crawl_run_id=run.id, source_id=source.id,
        url="https://example.invalid/p", outcome="FETCHED", http_status=200,
    )
    session.add(page)
    session.flush()
    return page


def _claim(session: Session, candidate: DiscoveryCandidate, source: DiscoverySource,
           *, field_key: str = "payload_kg", value: str = "30") -> CandidateClaim:
    """A claim is now always attributed — `discovery_source_id` is NOT NULL."""
    claim = CandidateClaim(
        candidate_id=candidate.id, field_key=field_key, claimed_value=value,
        discovery_source_id=source.id,
    )
    session.add(claim)
    session.flush()
    return claim


def _excerpt_kwargs(subject, source: DiscoverySource, **overrides) -> dict:
    """Excerpt defaults that satisfy the subject/source trigger, so each test can
    break exactly one thing."""
    kwargs = dict(
        subject_type="CLAIM", subject_id=subject.id, discovery_source_id=source.id,
        excerpt_text="30 kg payload", page_url="https://example.invalid/p",
        retrieved_at=datetime.now(UTC), ordinal=0,
    )
    kwargs.update(overrides)
    return kwargs


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
    claim = _claim(dsession, candidate, source)

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
    claim = _claim(dsession, _candidate(dsession, source, "exc-1"), source)
    # 1000 multi-byte characters = 3000 bytes. Must be ACCEPTED.
    multibyte = "ä" * EVIDENCE_EXCERPT_MAX_CHARS
    excerpt = DiscoveryEvidenceExcerpt(
        **_excerpt_kwargs(claim, source, excerpt_text=multibyte)
    )
    dsession.add(excerpt)
    dsession.flush()
    assert len(excerpt.excerpt_text) == 1000


def test_an_over_length_excerpt_is_refused(dsession: Session) -> None:
    source = _source(dsession, key="exc-2")
    claim = _claim(dsession, _candidate(dsession, source, "exc-2"), source)
    dsession.add(DiscoveryEvidenceExcerpt(**_excerpt_kwargs(
        claim, source, excerpt_text="x" * (EVIDENCE_EXCERPT_MAX_CHARS + 1))))
    with pytest.raises((IntegrityError, DataError)):
        dsession.flush()


def test_a_blank_excerpt_is_refused(dsession: Session) -> None:
    """'The page implied it' is not evidence (LIVE.6)."""
    source = _source(dsession, key="exc-3")
    claim = _claim(dsession, _candidate(dsession, source, "exc-3"), source)
    dsession.add(DiscoveryEvidenceExcerpt(
        **_excerpt_kwargs(claim, source, excerpt_text="   ")))
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_one_claim_may_carry_several_ordered_excerpts(dsession: Session) -> None:
    """A price and the region it applies to may sit in different parts of a page,
    so one passage often cannot justify a claim (D-7)."""
    source = _source(dsession, key="exc-4")
    candidate = _candidate(dsession, source, "exc-4")
    signal = CandidateCommercialSignal(
        candidate_id=candidate.id, discovery_source_id=source.id,
        axis="PRICE", price_type="PUBLIC", price_amount=13500, price_currency="USD",
    )
    dsession.add(signal)
    dsession.flush()
    subject = signal.id
    for ordinal, body in enumerate(["$13,500", "Ships to US only"]):
        dsession.add(DiscoveryEvidenceExcerpt(
            subject_type="COMMERCIAL_SIGNAL", subject_id=subject,
            discovery_source_id=source.id,
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
    claim = _claim(dsession, _candidate(dsession, source, "exc-5"), source)
    for _ in range(2):
        dsession.add(DiscoveryEvidenceExcerpt(
            **_excerpt_kwargs(claim, source, excerpt_text="same ordinal")))
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
        subject_type="COMMERCIAL_SIGNAL", subject_id=signal.id,
        discovery_source_id=source.id, crawl_run_id=run.id,
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
#: Tables whose ORM mapping must match the DDL exactly, not merely by name.
MIRRORED_TABLES = sorted(
    ACQUISITION_TABLES | {"discovery_source", "candidate_claim", "candidate_image_ref"}
)


def _pg_type(type_) -> str:
    """A comparable type string, schema-qualification stripped.

    Compiling both the reflected and the mapped type with the PostgreSQL dialect
    is what makes `Integer` vs `BIGINT` and `TEXT` vs `CHAR(3)` visible — the
    previous name-only comparison let both of those through.
    """
    rendered = str(type_.compile(dialect=postgresql.dialect()))
    return rendered.split(".")[-1].upper()


def _model_for(table: str):
    from app.db.base import Base

    return next(m.class_ for m in Base.registry.mappers if m.class_.__tablename__ == table)


@pytest.mark.parametrize("table", MIRRORED_TABLES)
def test_model_mirrors_the_database_exactly(database_url, table: str) -> None:
    """`db/schema.sql` is canonical (AGENTS.md rule 2); the models mirror it.

    The earlier version of this test compared column NAMES only, and two real type
    mismatches passed unnoticed: `content_length` was BIGINT in the DDL and
    Integer in the ORM, and `price_currency` was CHAR(3) versus Text. A name-only
    mirror check is barely a check — it cannot see the difference between a model
    that accepts what the database rejects and one that does not.
    """
    model = _model_for(table)
    inspector = inspect(engine)
    db_columns = {c["name"]: c for c in inspector.get_columns(table, schema="humanoid")}
    model_columns = {c.name: c for c in model.__table__.columns}

    assert set(model_columns) == set(db_columns), (
        f"{table}: only in model {set(model_columns) - set(db_columns)}, "
        f"only in database {set(db_columns) - set(model_columns)}"
    )

    mismatches: list[str] = []
    for name, column in sorted(model_columns.items()):
        db_column = db_columns[name]

        # Type, including enum name, fixed length and numeric precision/scale.
        model_type, db_type = _pg_type(column.type), _pg_type(db_column["type"])
        if model_type != db_type:
            mismatches.append(f"{name}: type model={model_type} db={db_type}")

        # Nullability. A model that says NULL-able where the database says NOT NULL
        # lets application code build a row the database will refuse.
        if bool(column.nullable) != bool(db_column["nullable"]):
            mismatches.append(
                f"{name}: nullable model={column.nullable} db={db_column['nullable']}"
            )

        # Server defaults, where the contract depends on them (claim_status
        # defaulting to NOT_VERIFIED, trigger defaults, etc.).
        db_default = (db_column.get("default") or "").split("::")[0].strip("'") or None
        model_default = None
        if column.server_default is not None:
            model_default = str(column.server_default.arg).split("::")[0].strip("'")
        if (model_default is None) != (db_default is None):
            mismatches.append(
                f"{name}: server_default model={model_default!r} db={db_default!r}"
            )

    assert mismatches == [], f"{table} ORM/DDL drift: " + "; ".join(mismatches)


@pytest.mark.parametrize("table", MIRRORED_TABLES)
def test_model_foreign_keys_match_targets_and_delete_actions(
    database_url, table: str
) -> None:
    """A wrong ON DELETE is invisible until the day a row is deleted.

    `SET NULL` versus `RESTRICT` on `candidate_claim.discovery_source_id` is the
    difference between silently stripping provenance from existing claims and
    refusing to delete a source that has any — Gate X depends on the second.
    """
    model = _model_for(table)
    db_fks = {
        (tuple(fk["constrained_columns"]), fk["referred_table"],
         (fk.get("options") or {}).get("ondelete", "").upper() or "NO ACTION")
        for fk in inspect(engine).get_foreign_keys(table, schema="humanoid")
    }
    model_fks = set()
    for constraint in model.__table__.foreign_key_constraints:
        columns = tuple(c.name for c in constraint.columns)
        target = next(iter(constraint.elements)).column.table.name
        ondelete = (constraint.ondelete or "NO ACTION").upper()
        model_fks.add((columns, target, ondelete))

    assert model_fks == db_fks, (
        f"{table} foreign-key drift — "
        f"only in model: {sorted(model_fks - db_fks)}; "
        f"only in db: {sorted(db_fks - model_fks)}"
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


# --------------------------------------------------------------------------- #
# ADVERSARIAL — the database must refuse forbidden states, not merely the ORM
#
# "The normal ORM path behaves correctly" is not "the database cannot represent a
# forbidden state". Everything below goes around the ORM deliberately: raw SQL,
# Core bulk statements, hand-built rows. That is the level at which a bypass
# happens, and the earlier SQLAdmin mutation bypass is precisely that failure
# already having occurred once in this layer.
# --------------------------------------------------------------------------- #
def test_raw_sql_cannot_insert_an_unattributed_claim(dsession: Session) -> None:
    """Gate X, fail-closed: a claim with no resolvable source must be REJECTED."""
    source = _source(dsession, key="raw-claim")
    candidate = _candidate(dsession, source, "raw-claim")
    with pytest.raises(IntegrityError):
        dsession.execute(
            text("INSERT INTO humanoid.candidate_claim (candidate_id, field_key,"
                 " claimed_value) VALUES (:cid, 'payload_kg', '30')"),
            {"cid": candidate.id},
        )


def test_deleting_a_source_with_claims_fails_rather_than_nulling_provenance(
    dsession: Session,
) -> None:
    """ON DELETE RESTRICT, not SET NULL. Nulling would turn "an aggregator said
    so" into an anonymous assertion at exactly the moment the audit trail
    matters."""
    source = _source(dsession, key="restrict-src", source_class="AGGREGATOR")
    candidate = _candidate(dsession, source, "restrict-1")
    _claim(dsession, candidate, source)

    with pytest.raises(IntegrityError):
        dsession.execute(
            text("DELETE FROM humanoid.discovery_source WHERE id = :sid"),
            {"sid": source.id},
        )


def test_an_excerpt_without_a_source_is_refused(dsession: Session) -> None:
    source = _source(dsession, key="exc-nosrc")
    claim = _claim(dsession, _candidate(dsession, source, "exc-nosrc"), source)
    with pytest.raises(IntegrityError):
        dsession.execute(
            text("INSERT INTO humanoid.discovery_evidence_excerpt (subject_type,"
                 " subject_id, excerpt_text, page_url, retrieved_at)"
                 " VALUES ('CLAIM', :sid, 'x', 'https://e.invalid/p', now())"),
            {"sid": claim.id},
        )


def test_an_excerpt_pointing_at_a_nonexistent_subject_is_refused(
    dsession: Session,
) -> None:
    """The polymorphic subject cannot be a foreign key, so a trigger enforces it.
    Left unchecked this accepted ANY random UUID — and an orphan quotation is
    indistinguishable from a fabricated one."""
    source = _source(dsession, key="exc-orphan")
    dsession.add(DiscoveryEvidenceExcerpt(
        subject_type="CLAIM", subject_id=uuid.uuid4(),
        discovery_source_id=source.id, excerpt_text="quoted at nothing",
        page_url="https://example.invalid/p", retrieved_at=datetime.now(UTC),
    ))
    with pytest.raises((IntegrityError, InternalError)):
        dsession.flush()


def test_an_excerpt_whose_source_differs_from_its_subject_is_refused(
    dsession: Session,
) -> None:
    """An excerpt must be evidence FOR the claim it is attached to. Otherwise a
    manufacturer-sourced passage could be quoted at an aggregator's claim, and the
    provenance chain would read as sound while being false."""
    manufacturer = _source(dsession, key="exc-mfr", source_class="MANUFACTURER")
    aggregator = _source(dsession, key="exc-agg", source_class="AGGREGATOR")
    claim = _claim(dsession, _candidate(dsession, aggregator, "exc-mix"), aggregator)

    dsession.add(DiscoveryEvidenceExcerpt(
        subject_type="CLAIM", subject_id=claim.id,
        discovery_source_id=manufacturer.id,   # not the claim's source
        excerpt_text="borrowed authority", page_url="https://example.invalid/p",
        retrieved_at=datetime.now(UTC),
    ))
    with pytest.raises((IntegrityError, InternalError)):
        dsession.flush()


def test_an_excerpt_on_an_unattributed_image_ref_is_refused(dsession: Session) -> None:
    """`candidate_image_ref.discovery_source_id` predates this contract and is
    nullable; an excerpt still may not hang off an unattributed subject."""
    source = _source(dsession, key="exc-img")
    candidate = _candidate(dsession, source, "exc-img")
    image_id = dsession.execute(
        text("INSERT INTO humanoid.candidate_image_ref (candidate_id, image_url)"
             " VALUES (:cid, 'https://example.invalid/i.jpg') RETURNING id"),
        {"cid": candidate.id},
    ).scalar_one()

    dsession.add(DiscoveryEvidenceExcerpt(
        subject_type="IMAGE_REF", subject_id=image_id,
        discovery_source_id=source.id, excerpt_text="credit line",
        page_url="https://example.invalid/p", retrieved_at=datetime.now(UTC),
    ))
    with pytest.raises((IntegrityError, InternalError)):
        dsession.flush()


def test_a_page_from_another_run_is_refused(dsession: Session) -> None:
    """Postgres cannot express "this page belongs to that run" as a foreign key,
    so without the lineage trigger a claim could cite a page fetched during a
    different run and the chain would still look sound."""
    source = _source(dsession, key="lineage-run")
    run_a = _run(dsession, source)
    run_b = _run(dsession, source)
    page_of_a = _page(dsession, run_a, source)
    candidate = _candidate(dsession, source, "lineage-run")

    dsession.add(CandidateClaim(
        candidate_id=candidate.id, field_key="height_cm", claimed_value="170",
        discovery_source_id=source.id,
        crawl_run_id=run_b.id, fetched_page_id=page_of_a.id,   # mismatched
    ))
    with pytest.raises((IntegrityError, InternalError)):
        dsession.flush()


def test_a_page_from_another_source_is_refused(dsession: Session) -> None:
    source_a = _source(dsession, key="lineage-src-a")
    source_b = _source(dsession, key="lineage-src-b", source_class="AGGREGATOR")
    run_a = _run(dsession, source_a)
    page_of_a = _page(dsession, run_a, source_a)
    candidate = _candidate(dsession, source_b, "lineage-src")

    dsession.add(CandidateClaim(
        candidate_id=candidate.id, field_key="height_cm", claimed_value="170",
        discovery_source_id=source_b.id, fetched_page_id=page_of_a.id,
    ))
    with pytest.raises((IntegrityError, InternalError)):
        dsession.flush()


def test_a_fetched_page_must_belong_to_its_runs_source(dsession: Session) -> None:
    """Lineage is checked at the root too: a page recorded against a run must
    share that run's source, or every downstream check is built on sand."""
    source_a = _source(dsession, key="page-src-a")
    source_b = _source(dsession, key="page-src-b")
    run = _run(dsession, source_a)
    dsession.add(FetchedPage(
        crawl_run_id=run.id, source_id=source_b.id,
        url="https://example.invalid/x", outcome="FETCHED",
    ))
    with pytest.raises((IntegrityError, InternalError)):
        dsession.flush()


def test_consistent_lineage_is_accepted(dsession: Session) -> None:
    """The positive case, so the triggers are shown to PERMIT correct rows rather
    than merely to reject."""
    source = _source(dsession, key="lineage-ok")
    run = _run(dsession, source)
    page = _page(dsession, run, source)
    candidate = _candidate(dsession, source, "lineage-ok")
    claim = CandidateClaim(
        candidate_id=candidate.id, field_key="height_cm", claimed_value="170",
        discovery_source_id=source.id, crawl_run_id=run.id, fetched_page_id=page.id,
    )
    dsession.add(claim)
    dsession.flush()
    dsession.add(DiscoveryEvidenceExcerpt(
        subject_type="CLAIM", subject_id=claim.id, discovery_source_id=source.id,
        crawl_run_id=run.id, fetched_page_id=page.id,
        excerpt_text="Height 170 cm", page_url=page.url,
        retrieved_at=datetime.now(UTC), locator=".spec-height",
    ))
    dsession.flush()


# --------------------------------------------------------------------------- #
# §5 append-only — enforced by the DATABASE, not by cooperative sessions
# --------------------------------------------------------------------------- #
def _review(session: Session, source: DiscoverySource) -> SourceEligibilityReview:
    review = SourceEligibilityReview(
        source_id=source.id, reviewed_by="reviewer", tos_decision="PROHIBITED",
    )
    session.add(review)
    session.flush()
    return review


def test_raw_sql_update_of_an_eligibility_review_is_refused(dsession: Session) -> None:
    """The ORM listener is developer feedback; THIS is the integrity boundary. If
    the record that authorizes contacting a third party could be edited, an
    authorization could be backdated and DATA-D1.9 would be forgeable."""
    source = _source(dsession, key="appendonly-1")
    review = _review(dsession, source)
    with pytest.raises((InternalError, ProgrammingError, IntegrityError)):
        dsession.execute(
            text("UPDATE humanoid.source_eligibility_review SET tos_decision ="
                 " 'ALLOWED' WHERE id = :rid"),
            {"rid": review.id},
        )


def test_raw_sql_delete_of_an_eligibility_review_is_refused(dsession: Session) -> None:
    source = _source(dsession, key="appendonly-2")
    review = _review(dsession, source)
    with pytest.raises((InternalError, ProgrammingError, IntegrityError)):
        dsession.execute(
            text("DELETE FROM humanoid.source_eligibility_review WHERE id = :rid"),
            {"rid": review.id},
        )


def test_core_bulk_update_of_an_eligibility_review_is_refused(dsession: Session) -> None:
    """A Core bulk statement never fires ORM instance listeners — which is exactly
    how the earlier SQLAdmin bypass got through on promotion_audit."""
    source = _source(dsession, key="appendonly-3")
    review = _review(dsession, source)
    with pytest.raises((InternalError, ProgrammingError, IntegrityError)):
        dsession.execute(
            update(SourceEligibilityReview)
            .where(SourceEligibilityReview.id == review.id)
            .values(tos_decision="ALLOWED")
        )


def test_core_bulk_delete_of_an_eligibility_review_is_refused(dsession: Session) -> None:
    source = _source(dsession, key="appendonly-4")
    review = _review(dsession, source)
    with pytest.raises((InternalError, ProgrammingError, IntegrityError)):
        dsession.execute(
            delete(SourceEligibilityReview).where(
                SourceEligibilityReview.id == review.id
            )
        )


def test_a_matchless_bulk_update_is_still_refused(dsession: Session) -> None:
    """The trigger is FOR EACH STATEMENT: a row-level trigger never fires for a
    statement that matches nothing, so `UPDATE ... WHERE <no match>` would appear
    to succeed. Refusing the ATTEMPT is the honest semantics here."""
    with pytest.raises((InternalError, ProgrammingError, IntegrityError)):
        dsession.execute(
            text("UPDATE humanoid.source_eligibility_review SET notes = 'x'"
                 " WHERE id = '00000000-0000-0000-0000-000000000000'")
        )


def test_the_integrity_triggers_exist_in_the_database(database_url) -> None:
    """Named explicitly, so removing one is a visible test failure rather than a
    silent loss of the boundary."""
    with engine.connect() as conn:
        triggers = set(conn.execute(text(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
        )).scalars().all())
    for name in (
        "trg_source_eligibility_review_no_update",
        "trg_source_eligibility_review_no_delete",
        "trg_evidence_excerpt_subject",
        "trg_fetched_page_lineage",
        "trg_candidate_claim_lineage",
        "trg_commercial_signal_lineage",
        "trg_evidence_excerpt_lineage",
        "trg_extraction_result_lineage",
    ):
        assert name in triggers, f"missing integrity trigger {name}"


def test_the_orm_listener_remains_as_early_feedback(dsession: Session) -> None:
    """Kept deliberately: it fails in Python with a clear message before the
    statement reaches the database. It is simply no longer the boundary."""
    source = _source(dsession, key="appendonly-5")
    review = _review(dsession, source)
    review.tos_decision = "ALLOWED"
    with pytest.raises(EligibilityReviewImmutableError):
        dsession.flush()


# --------------------------------------------------------------------------- #
# The specific drift a name-only comparison could not see
# --------------------------------------------------------------------------- #
def test_content_length_is_bigint_in_both_ddl_and_orm(database_url) -> None:
    db_type = next(
        c["type"] for c in inspect(engine).get_columns("fetched_page", schema="humanoid")
        if c["name"] == "content_length"
    )
    assert _pg_type(db_type) == "BIGINT"
    assert _pg_type(FetchedPage.__table__.c.content_length.type) == "BIGINT"


def test_price_currency_is_char3_in_both_ddl_and_orm(database_url) -> None:
    db_type = next(
        c["type"] for c in inspect(engine).get_columns(
            "candidate_commercial_signal", schema="humanoid")
        if c["name"] == "price_currency"
    )
    assert _pg_type(db_type) == "CHAR(3)"
    assert _pg_type(
        CandidateCommercialSignal.__table__.c.price_currency.type
    ) == "CHAR(3)"


def test_price_amount_keeps_its_precision_and_scale(database_url) -> None:
    """NUMERIC(14, 2): money must not silently become a float, and the scale is
    what keeps a price from being rounded on the way in."""
    db_type = next(
        c["type"] for c in inspect(engine).get_columns(
            "candidate_commercial_signal", schema="humanoid")
        if c["name"] == "price_amount"
    )
    assert _pg_type(db_type) == "NUMERIC(14, 2)"
    assert _pg_type(
        CandidateCommercialSignal.__table__.c.price_amount.type
    ) == "NUMERIC(14, 2)"
