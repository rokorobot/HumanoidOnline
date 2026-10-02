"""Least-privilege boundaries for the G2-1 proposal tables (DR-A5 section 16).

Throwaway NOLOGIN roles are created INSIDE the test transaction (so nothing persists),
given exactly the grants in db/roles/discovery_observer.sql and
db/roles/discovery_reviewer.sql, and each statement runs `SET LOCAL ROLE`-ed inside a
SAVEPOINT. Proves: observation can insert proposals and sightings but cannot create or
even read human decisions; review can insert decisions but cannot alter proposals or
sightings; neither writes the catalogue.
"""
from __future__ import annotations

import pathlib
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from test_claim_proposal_persistence import BODY, World

from app.db.session import engine

pytestmark = pytest.mark.usefixtures("no_external_network")

ROLES = pathlib.Path(__file__).resolve().parents[3] / "db" / "roles"
PROPOSAL_INSERT = (
    "INSERT INTO discovery_claim_proposal (digest, slot_key, source_id, source_url, robot_slug,"
    " kind, target, representability, value, evidence_excerpt, evidence_locator,"
    " extraction_method, extraction_confidence, extractor_key, extractor_version,"
    " origin_fetched_page_id, origin_crawl_run_id, origin_content_hash, origin_retrieved_at,"
    " ingested_by) SELECT lpad(to_hex((random() * 1e12)::bigint), 64, '0'), slot_key, source_id,"
    " source_url, robot_slug, kind, target, representability, value, evidence_excerpt,"
    " evidence_locator, extraction_method, extraction_confidence, extractor_key,"
    " extractor_version, origin_fetched_page_id, origin_crawl_run_id, origin_content_hash,"
    " origin_retrieved_at, ingested_by FROM discovery_claim_proposal LIMIT 1")
OBSERVATION_INSERT = (
    "INSERT INTO discovery_proposal_observation (proposal_id, fetched_page_id, crawl_run_id,"
    " content_hash, retrieved_at, observed_by) SELECT p.id, fp.id, fp.crawl_run_id,"
    " fp.content_hash, fp.retrieved_at, 'role-test' FROM discovery_claim_proposal p"
    " JOIN fetched_page fp ON fp.id <> p.origin_fetched_page_id AND fp.source_id = p.source_id"
    " LIMIT 1")
DECISION_INSERT = (
    "INSERT INTO discovery_proposal_decision (proposal_id, decision, decided_by, rationale)"
    " SELECT id, 'DEFER', 'Robert Konecny', 'role test' FROM discovery_claim_proposal LIMIT 1")


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


def _role(session: Session, grants_file: str, template_name: str) -> str:
    name = f"{template_name}_t{uuid.uuid4().hex[:8]}"
    session.execute(text(f"CREATE ROLE {name} NOLOGIN"))
    sql = (ROLES / grants_file).read_text(encoding="utf-8").replace(template_name, name)
    session.connection().exec_driver_sql(sql.replace("%", "%%"))
    return name


def _as(session: Session, role: str, sql: str) -> None:
    """Run one statement as `role` (it must succeed); the role is reset afterwards."""
    session.execute(text(f"SET LOCAL ROLE {role}"))
    session.execute(text(sql))
    session.execute(text("RESET ROLE"))


def _denied(session: Session, role: str, sql: str) -> None:
    """The statement must be refused; the savepoint rollback also undoes SET LOCAL ROLE."""
    savepoint = session.begin_nested()
    try:
        session.execute(text(f"SET LOCAL ROLE {role}"))
        with pytest.raises(ProgrammingError, match="permission denied"):
            session.execute(text(sql))
    finally:
        savepoint.rollback()


def _world(session: Session) -> World:
    w = World(session)
    w.ingest(w.page())
    w.page()          # a second observed page, for the sighting insert
    return w


CATALOGUE_AND_OTHER = (
    "INSERT INTO robot (slug, manufacturer_id, name) SELECT 'x', id, 'x' FROM manufacturer LIMIT 1",
    "UPDATE manufacturer SET name = name",
    "UPDATE robot SET is_published = true",
    "INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type) "
    "VALUES ('ROBOT', gen_random_uuid(), 'https://x', 'OTHER')",
    "INSERT INTO promotion_audit (action, approved_by) VALUES ('PROMOTED', 'x')",
    "CREATE TABLE humanoid.role_ddl (id int)",
)


def test_observer_inserts_proposals_and_sightings_but_never_decisions(dsession):
    w = _world(dsession)
    role = _role(dsession, "discovery_observer.sql", "discovery_observer")
    _as(dsession, role, PROPOSAL_INSERT)
    _as(dsession, role, OBSERVATION_INSERT)
    _as(dsession, role, "SELECT count(*) FROM discovery_claim_proposal")
    _denied(dsession, role, DECISION_INSERT)
    _denied(dsession, role, "SELECT count(*) FROM discovery_proposal_decision")
    for sql in ("UPDATE discovery_claim_proposal SET gap = 'x'",
                "DELETE FROM discovery_claim_proposal",
                "UPDATE discovery_proposal_observation SET observed_by = 'x'",
                "DELETE FROM discovery_proposal_observation",
                *CATALOGUE_AND_OTHER):
        _denied(dsession, role, sql)
    assert w.robot.is_published is False


def test_reviewer_inserts_decisions_but_cannot_alter_proposals_or_run_observation(dsession):
    _world(dsession)
    role = _role(dsession, "discovery_reviewer.sql", "discovery_reviewer")
    _as(dsession, role, "SELECT count(*) FROM discovery_claim_proposal")
    _as(dsession, role, "SELECT count(*) FROM discovery_proposal_observation")
    _as(dsession, role, DECISION_INSERT)
    _as(dsession, role, "SELECT count(*) FROM discovery_proposal_decision")
    for sql in (PROPOSAL_INSERT, OBSERVATION_INSERT,
                "UPDATE discovery_claim_proposal SET gap = 'x'",
                "DELETE FROM discovery_claim_proposal",
                "UPDATE discovery_proposal_decision SET rationale = 'x'",
                "DELETE FROM discovery_proposal_decision",
                "INSERT INTO crawl_run (source_id, adapter_key, adapter_version, operator) "
                "SELECT id, 'a', '1', 'x' FROM discovery_source LIMIT 1",
                "INSERT INTO candidate_claim (candidate_id, field_key, claimed_value) "
                "VALUES (gen_random_uuid(), 'height_cm', '1')",
                *CATALOGUE_AND_OTHER):
        _denied(dsession, role, sql)


def test_the_review_service_runs_end_to_end_as_the_reviewer_role(dsession):
    """G2-2: list, derive state (supersession/staleness) and decide, all as the reviewer."""
    from app.services.discovery import proposal_review as pr

    w = _world(dsession)
    role = _role(dsession, "discovery_reviewer.sql", "discovery_reviewer")
    dsession.execute(text(f"SET LOCAL ROLE {role}"))
    states = pr.list_proposals(dsession, robot_slug=w.slug)
    assert states and all(st.state == pr.CURRENT for st in states)
    target = next(st.proposal for st in states if st.proposal.kind == "DESIGN_CAVEAT")
    row, created = pr.decide(dsession, str(target.id), pr.DEFER, decided_by="Robert Konecny",
                             rationale="reviewer-role proof")
    again, created2 = pr.decide(dsession, str(target.id), pr.DEFER, decided_by="Robert Konecny",
                                rationale="reviewer-role proof")
    assert created and not created2 and again.id == row.id
    pr.render_show(dsession, target)
    dsession.execute(text("RESET ROLE"))
    for sql in ("UPDATE robot SET is_published = true", "UPDATE robot SET name = name",
                "DELETE FROM robot"):
        _denied(dsession, role, sql)


def test_a_role_with_no_g2_grants_has_no_access_to_the_new_tables(dsession):
    """Default deny: the production observer today holds no privilege on these tables."""
    _world(dsession)
    role = _role(dsession, "discovery_reviewer.sql", "discovery_reviewer")
    bare = f"bare_{uuid.uuid4().hex[:8]}"
    dsession.execute(text(f"CREATE ROLE {bare} NOLOGIN"))
    dsession.execute(text(f"GRANT USAGE ON SCHEMA humanoid TO {bare}"))
    for table in ("discovery_claim_proposal", "discovery_proposal_observation",
                  "discovery_proposal_decision"):
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert dsession.scalar(text(
                f"SELECT has_table_privilege('{bare}', 'humanoid.{table}', '{priv}')")) is False
    assert role and BODY
