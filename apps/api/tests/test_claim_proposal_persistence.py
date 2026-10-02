"""G2-1 claim-proposal persistence (migration 0018, DR-A5 B-prime), offline PostgreSQL.

Proves the persistence foundation: immutable proposals, append-only sightings and
decisions, deterministic digests and slots, edition context without extra robot
identities, checked provenance, idempotent manual ingest, and that no G2-1 operation
writes a catalogue fact, a decision, a candidate claim or `is_published`.

Everything runs in a transaction that is rolled back; each forbidden statement runs
inside a SAVEPOINT so the refusal is observed without poisoning the transaction.
"""
from __future__ import annotations

import pathlib
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_neura_mini_proposals import PAGE, replace_cell

from app.db.session import engine
from app.models import (
    CandidateClaim,
    DiscoveryClaimProposal,
    DiscoveryProposalDecision,
    DiscoveryProposalObservation,
    ProposalImmutableError,
)
from app.models.acquisition import CrawlRun, FetchedPage
from app.models.discovery import DiscoverySource
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import DiscoveryError, proposals
from app.services.discovery.fingerprint import fingerprint
from app.services.discovery.sources import neura_mini_proposals as mini

pytestmark = pytest.mark.usefixtures("no_external_network")

RESTRICT_VIOLATION = "23001"
BODY = PAGE.encode("utf-8") if isinstance(PAGE, str) else PAGE
OLD_PRICE = "19,999 € (excluding taxes and shipping)"
NEW_PRICE = "21,999 € (excluding taxes and shipping)"
PROPOSAL_COUNT = len(mini.propose_neura_mini_claims(BODY, mini.MINI_URL).proposals)


@pytest.fixture
def dsession(database_url):
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


class World:
    """A catalogue robot named '4NE1 Mini', an official source, and observed pages."""

    def __init__(self, session: Session) -> None:
        self.session = session
        tag = uuid.uuid4().hex[:8]
        self.maker = Manufacturer(slug=f"neura-{tag}", name=f"Neura{tag}")
        session.add(self.maker)
        session.flush()
        self.slug = f"4ne1-mini-{tag}"
        self.robot = Robot(slug=self.slug, manufacturer_id=self.maker.id, name=mini.ROBOT_NAME,
                           is_published=False)
        self.source = DiscoverySource(key=f"neura-{tag}", name="NEURA (test)",
                                      source_class="MANUFACTURER")
        session.add_all([self.robot, self.source])
        session.flush()
        self.run = CrawlRun(source_id=self.source.id, adapter_key="manual", adapter_version="1",
                            operator="fixture", status="COMPLETED",
                            started_at=datetime(2026, 9, 26, tzinfo=UTC),
                            finished_at=datetime(2026, 9, 26, tzinfo=UTC))
        session.add(self.run)
        session.flush()

    def page(self, body: bytes = BODY, *, url: str = mini.MINI_URL,
             source: DiscoverySource | None = None, retrieved_at: datetime | None = None,
             outcome: str = "FETCHED", http_status: int | None = 200,
             content_hash: str | None = "auto") -> FetchedPage:
        if content_hash == "auto":
            content_hash = fingerprint(body, "text/html")
        page = FetchedPage(
            crawl_run_id=self.run.id, source_id=(source or self.source).id, url=url,
            http_status=http_status, content_type="text/html", content_hash=content_hash,
            outcome=outcome,
            retrieved_at=retrieved_at or datetime(2026, 9, 26, 8, 0, tzinfo=UTC))
        self.session.add(page)
        self.session.flush()
        return page

    def ingest(self, page: FetchedPage, body: bytes = BODY, by: str = "Robert Konecny"):
        return proposals.ingest_neura_mini_proposals(
            self.session, source_key=self.source.key, robot_slug=self.slug,
            fetched_page_id=page.id, body=body, ingested_by=by)


def count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


@contextmanager
def refused(session: Session, *, op: str):
    savepoint = session.begin_nested()
    try:
        with pytest.raises(DBAPIError) as exc:
            yield
        assert getattr(exc.value.orig, "sqlstate", None) == RESTRICT_VIOLATION
        assert "append-only" in str(exc.value.orig) and f"{op} refused" in str(exc.value.orig)
    finally:
        savepoint.rollback()


# ----------------------------------------------------------------- ingest ----


def test_ingest_persists_every_g1_proposal_unverified_with_provenance(dsession):
    w = World(dsession)
    page = w.page()
    report = w.ingest(page)
    assert report.status == "PROPOSED"
    assert report.proposals_created == report.observations_created == PROPOSAL_COUNT > 0
    rows = dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug)).all()
    assert len(rows) == PROPOSAL_COUNT
    for r in rows:
        assert r.claim_status == "NOT_VERIFIED"
        assert r.extractor_key == mini.EXTRACTOR_KEY
        assert r.extractor_version == mini.EXTRACTOR_VERSION
        assert r.source_id == w.source.id and r.source_url == mini.MINI_URL
        assert r.origin_fetched_page_id == page.id and r.origin_crawl_run_id == w.run.id
        assert r.origin_content_hash == page.content_hash
        assert r.evidence_excerpt.strip() and r.evidence_locator.strip()
        assert r.ingested_by == "Robert Konecny"
        assert len(r.digest) == len(r.slot_key) == 64
    assert count(dsession, DiscoveryProposalDecision) == 0


def test_reingest_of_the_same_observation_is_a_no_op(dsession):
    w = World(dsession)
    page = w.page()
    w.ingest(page)
    before = (count(dsession, DiscoveryClaimProposal),
              count(dsession, DiscoveryProposalObservation))
    again = w.ingest(page)
    assert (again.proposals_created, again.observations_created) == (0, 0)
    assert again.unchanged == PROPOSAL_COUNT
    after = (count(dsession, DiscoveryClaimProposal),
             count(dsession, DiscoveryProposalObservation))
    assert after == before


def test_unchanged_page_seen_again_adds_sightings_only(dsession):
    w = World(dsession)
    w.ingest(w.page())
    proposals_before = count(dsession, DiscoveryClaimProposal)
    second = w.page()
    report = w.ingest(second)
    assert report.proposals_created == 0 and report.observations_created == PROPOSAL_COUNT
    assert count(dsession, DiscoveryClaimProposal) == proposals_before
    sightings = dsession.scalars(
        select(DiscoveryProposalObservation).where(
            DiscoveryProposalObservation.fetched_page_id == second.id)).all()
    assert len(sightings) == PROPOSAL_COUNT


def test_same_slot_with_a_changed_value_is_a_new_proposal_and_supersedes(dsession):
    w = World(dsession)
    w.ingest(w.page())
    changed = replace_cell(PAGE, OLD_PRICE, NEW_PRICE)
    body = changed.encode("utf-8") if isinstance(changed, str) else changed
    report = w.ingest(w.page(body), body)
    assert report.proposals_created == 1
    states = proposals.proposal_states(dsession, w.slug)
    old = [s for s in states if s["value"].startswith("19,999")]
    new = [s for s in states if s["value"].startswith("21,999")]
    assert len(old) == len(new) == 1
    assert old[0]["state"] == proposals.SUPERSEDED and new[0]["state"] == proposals.CURRENT
    assert old[0]["kind"] == new[0]["kind"] == "PRICE_ESTIMATE"
    assert old[0]["edition"] == new[0]["edition"] == "Standard"
    rows = {r.digest: r for r in dsession.scalars(select(DiscoveryClaimProposal))
            if r.robot_slug == w.slug}
    assert rows[old[0]["digest"]].slot_key == rows[new[0]["digest"]].slot_key
    assert sum(s["state"] == proposals.SUPERSEDED for s in states) == 1


def test_standard_and_pro_are_edition_context_not_robot_identities(dsession):
    w = World(dsession)
    robots_before = count(dsession, Robot)
    w.ingest(w.page())
    assert count(dsession, Robot) == robots_before
    rows = dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug)).all()
    assert {r.robot_slug for r in rows} == {w.slug}
    assert {r.edition for r in rows} == {"Standard", "Pro", None}
    price = {r.edition: r for r in rows if r.kind == "PRICE_ESTIMATE"}
    assert price["Standard"].slot_key != price["Pro"].slot_key
    assert price["Standard"].digest != price["Pro"].digest


def test_slot_and_digest_are_deterministic(dsession):
    w = World(dsession)
    w.ingest(w.page())
    expected = {p.digest for p in mini.propose_neura_mini_claims(BODY, mini.MINI_URL).proposals}
    stored = {r.digest for r in dsession.scalars(select(DiscoveryClaimProposal)).all()
              if r.robot_slug == w.slug}
    assert stored == expected and len(stored) == PROPOSAL_COUNT
    assert proposals.slot_key("s", "r", "K", "Pro", "loc") == proposals.slot_key(
        "s", "r", "K", "Pro", "loc")
    assert proposals.slot_key("s", "r", "K", "Pro", "loc") != proposals.slot_key(
        "s", "r", "K", "Standard", "loc")


def test_identical_content_is_never_attached_to_a_second_robot(dsession):
    a, b = World(dsession), World(dsession)
    a.ingest(a.page())
    with pytest.raises(DiscoveryError, match="another robot"):
        b.ingest(b.page())


def test_provenance_resolves_to_the_correct_observation_and_source(dsession):
    w = World(dsession)
    page = w.page()
    w.ingest(page)
    row = dsession.execute(text("""
        SELECT s.key, fp.content_hash, fp.url, o.content_hash AS o_hash, cr.id AS run_id
        FROM discovery_proposal_observation o
        JOIN discovery_claim_proposal p ON p.id = o.proposal_id
        JOIN fetched_page fp ON fp.id = o.fetched_page_id
        JOIN crawl_run cr ON cr.id = o.crawl_run_id
        JOIN discovery_source s ON s.id = p.source_id
        WHERE p.robot_slug = :slug LIMIT 1"""), {"slug": w.slug}).one()
    assert row.key == w.source.key and row.url == mini.MINI_URL
    assert row.content_hash == row.o_hash == page.content_hash and row.run_id == w.run.id


def test_ingest_refuses_unproven_provenance_and_wrong_identity(dsession):
    w = World(dsession)
    page = w.page()
    with pytest.raises(DiscoveryError, match="content_hash"):
        w.ingest(page, BODY + b"<!-- tampered text -->x")
    other = DiscoverySource(key=f"o-{uuid.uuid4().hex[:6]}", name="o",
                            source_class="MANUFACTURER")
    dsession.add(other)
    dsession.flush()
    with pytest.raises(DiscoveryError, match="named source"):
        proposals.ingest_neura_mini_proposals(
            dsession, source_key=other.key, robot_slug=w.slug, fetched_page_id=page.id,
            body=BODY, ingested_by="x")
    with pytest.raises(DiscoveryError, match="reads"):
        w.ingest(w.page(url="https://neura-robotics.com/product/4ne1-reservation"))
    with pytest.raises(DiscoveryError, match="catalogue"):
        proposals.ingest_neura_mini_proposals(
            dsession, source_key=w.source.key, robot_slug="no-such-robot",
            fetched_page_id=page.id, body=BODY, ingested_by="x")
    with pytest.raises(DiscoveryError, match="--by"):
        w.ingest(page, by="  ")
    assert count(dsession, DiscoveryClaimProposal) == 0


def test_ingest_writes_no_catalogue_fact_decision_or_candidate_claim(dsession):
    w = World(dsession)
    tables = ("robot", "manufacturer", "evidence_source", "specification", "pricing_offer",
              "availability_offer", "robot_variant", "robot_capability", "robot_image",
              "candidate_claim", "discovery_candidate", "promotion_audit",
              "candidate_identity_decision", "discovery_proposal_decision")

    def snapshot():
        return {t: dsession.scalar(text(f"SELECT count(*) FROM {t}")) for t in tables}

    robot_row = dsession.execute(
        text("SELECT to_jsonb(r) FROM robot r WHERE id = :i"), {"i": w.robot.id}).scalar()
    before = snapshot()
    page = w.page()
    w.ingest(page)
    w.ingest(page)
    w.ingest(w.page())
    assert snapshot() == before
    assert dsession.execute(text("SELECT to_jsonb(r) FROM robot r WHERE id = :i"),
                            {"i": w.robot.id}).scalar() == robot_row
    assert dsession.scalar(select(Robot.is_published).where(Robot.id == w.robot.id)) is False
    assert dsession.scalar(select(func.count()).select_from(EvidenceSource).where(
        EvidenceSource.subject_id == w.robot.id)) == 0
    assert count(dsession, CandidateClaim) == before["candidate_claim"]


def test_parser_output_stays_proposal_only(dsession):
    w = World(dsession)
    w.ingest(w.page())
    statuses = set(dsession.scalars(select(DiscoveryClaimProposal.claim_status).where(
        DiscoveryClaimProposal.robot_slug == w.slug)))
    assert statuses == {"NOT_VERIFIED"}
    with pytest.raises(DBAPIError):
        with dsession.begin_nested():
            dsession.execute(text(
                "UPDATE discovery_claim_proposal SET claim_status = 'VERIFIED' WHERE false"))
            dsession.execute(text(
                "INSERT INTO discovery_claim_proposal (digest, slot_key, source_id, source_url,"
                " robot_slug, kind, target, representability, value, evidence_excerpt,"
                " evidence_locator, extraction_method, extraction_confidence, claim_status,"
                " extractor_key, extractor_version, origin_fetched_page_id, origin_crawl_run_id,"
                " origin_content_hash, origin_retrieved_at, ingested_by) "
                "SELECT repeat('c', 64), repeat('d', 64), source_id, source_url, robot_slug, kind,"
                " target, representability, value, evidence_excerpt, evidence_locator,"
                " extraction_method, extraction_confidence, 'VERIFIED', extractor_key,"
                " extractor_version, origin_fetched_page_id, origin_crawl_run_id,"
                " origin_content_hash, origin_retrieved_at, ingested_by "
                "FROM discovery_claim_proposal LIMIT 1"))


# ------------------------------------------------------------- immutability --


def _decide(session: Session, proposal: DiscoveryClaimProposal, decision: str = "DEFER",
            **kw) -> DiscoveryProposalDecision:
    row = DiscoveryProposalDecision(
        proposal_id=proposal.id, decision=decision, decided_by=kw.get("by", "Robert Konecny"),
        rationale=kw.get("why", "needs the owner's price-type decision"),
        resolved_choices=kw.get("choices", {"price_type": "UNRESOLVED"}))
    session.add(row)
    session.flush()
    return row


@pytest.mark.parametrize("table,assignment", [
    ("discovery_claim_proposal", "value = value"),
    ("discovery_claim_proposal", "gap = 'rewritten'"),
    ("discovery_proposal_observation", "observed_by = 'someone'"),
    ("discovery_proposal_decision", "rationale = 'rewritten'"),
])
def test_raw_update_is_refused_by_the_database(dsession, table, assignment):
    w = World(dsession)
    w.ingest(w.page())
    _decide(dsession, dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug)).first())
    with refused(dsession, op="UPDATE"):
        dsession.execute(text(f"UPDATE {table} SET {assignment}"))
    with refused(dsession, op="UPDATE"):
        dsession.execute(text(f"UPDATE {table} SET {assignment} WHERE false"))


@pytest.mark.parametrize("table", [
    "discovery_claim_proposal", "discovery_proposal_observation", "discovery_proposal_decision"])
def test_raw_delete_is_refused_by_the_database(dsession, table):
    w = World(dsession)
    w.ingest(w.page())
    _decide(dsession, dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug)).first())
    n = count(dsession, DiscoveryClaimProposal)
    with refused(dsession, op="DELETE"):
        dsession.execute(text(f"DELETE FROM {table}"))
    with refused(dsession, op="DELETE"):
        dsession.execute(text(f"DELETE FROM {table} WHERE false"))
    assert count(dsession, DiscoveryClaimProposal) == n


def test_orm_listeners_refuse_changes_as_a_backstop(dsession):
    w = World(dsession)
    w.ingest(w.page())
    row = dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug)).first()
    decision = _decide(dsession, row)
    with dsession.begin_nested():
        row.value = "tampered"
        with pytest.raises(ProposalImmutableError):
            dsession.flush()
        dsession.expire(row)
    with dsession.begin_nested():
        dsession.delete(decision)
        with pytest.raises(ProposalImmutableError):
            dsession.flush()
        dsession.expire(decision)


def test_legitimate_insert_paths_work(dsession):
    w = World(dsession)
    w.ingest(w.page())
    row = dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug)).first()
    first = _decide(dsession, row, "DEFER")
    second = _decide(dsession, row, "REJECT", why="not a catalogue fact", choices={})
    assert second.decision_seq > first.decision_seq
    state = [s for s in proposals.proposal_states(dsession, w.slug) if s["id"] == str(row.id)]
    assert state[0]["decision"] == "REJECT"          # newest decision is effective
    assert count(dsession, DiscoveryProposalDecision) == 2   # history kept, nothing accepted
    assert dsession.scalar(text("SELECT count(*) FROM promotion_audit")) is not None


def test_a_decision_requires_attribution_rationale_and_object_choices(dsession):
    w = World(dsession)
    w.ingest(w.page())
    row = dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug)).first()
    for kw in ({"by": "  "}, {"why": ""}, {"choices": ["not", "an", "object"]}):
        with pytest.raises(DBAPIError):
            with dsession.begin_nested():
                _decide(dsession, row, **kw)


def test_a_decision_on_a_superseded_proposal_stays_as_history(dsession):
    w = World(dsession)
    w.ingest(w.page())
    old = dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug,
        DiscoveryClaimProposal.kind == "PRICE_ESTIMATE",
        DiscoveryClaimProposal.edition == "Standard")).one()
    _decide(dsession, old, "REJECT", why="estimate, not a price", choices={})
    changed = replace_cell(PAGE, OLD_PRICE, NEW_PRICE)
    body = changed.encode("utf-8") if isinstance(changed, str) else changed
    w.ingest(w.page(body), body)
    by_digest = {s["digest"]: s for s in proposals.proposal_states(dsession, w.slug)}
    assert by_digest[old.digest]["state"] == proposals.SUPERSEDED
    assert by_digest[old.digest]["decision"] == "REJECT"
    new = next(s for s in by_digest.values() if s["value"].startswith("21,999"))
    assert new["state"] == proposals.CURRENT and new["decision"] is None


def test_proposals_hold_no_foreign_key_to_a_canonical_table(dsession):
    rows = dsession.execute(text("""
        SELECT conrelid::regclass::text AS t, confrelid::regclass::text AS ref
        FROM pg_constraint
        WHERE contype = 'f' AND conrelid IN (
            'humanoid.discovery_claim_proposal'::regclass,
            'humanoid.discovery_proposal_observation'::regclass,
            'humanoid.discovery_proposal_decision'::regclass)""")).all()
    assert rows
    for _t, ref in rows:
        assert ref.split(".")[-1] in {
            "discovery_source", "crawl_run", "fetched_page", "discovery_claim_proposal"}, ref


# ----------------------------------------------- registry and unwired scope ---


def test_field_policy_registry_is_the_three_column_skeleton_with_no_new_mapping():
    from app.services.discovery import field_policy
    from app.services.discovery.promotion import _APPROVED_FIELDS

    assert set(field_policy.REGISTRY) == set(_APPROVED_FIELDS) == {
        "height_cm", "weight_kg", "payload_kg"}
    result = mini.propose_neura_mini_claims(BODY, mini.MINI_URL)
    assert all(field_policy.policy_for(p.target) is None for p in result.proposals)


def test_proposal_ingest_is_not_wired_into_observation_or_the_neura_adapter():
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    for rel in ("services/discovery/observe.py", "services/discovery/adapter_run.py",
                "services/discovery/live_adapter.py",
                "services/discovery/sources/neura_robotics.py",
                "services/discovery/promotion.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "discovery.proposals" not in src and "neura_mini_proposals" not in src, rel


def test_cli_requires_attribution_and_a_valid_observation_id():
    from app.cli.discovery import main

    for argv in (
        ["proposals", "ingest", "s", "--robot-slug", "r", "--fetched-page", str(uuid.uuid4()),
         "--body-file", "x.html"],
        ["proposals", "ingest", "s", "--robot-slug", "r", "--fetched-page", "not-a-uuid",
         "--body-file", "x.html", "--by", "Robert Konecny"],
    ):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2
