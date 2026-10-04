"""The Stage F least-privilege role (db/roles/discovery_observer.sql), offline.

Creates a throwaway LOGIN role with exactly that file's grants, runs one real
observation cycle AS that role against a synthetic site, then proves the role
cannot write the canonical catalogue, read leads, run DDL, or delete history.
Setup and cleanup use the owner connection; the cycle uses only the role.
"""
from __future__ import annotations

import pathlib
import uuid

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from test_discovery_stage_f_observe import Harness

from app.config import get_settings
from app.db.session import engine as owner_engine
from app.models.acquisition import (
    CandidateCommercialSignal,
    CrawlRun,
    DiscoveryEvidenceExcerpt,
    ExtractionResult,
    FetchedPage,
)
from app.models.discovery import (
    CandidateClaim,
    CandidateImageRef,
    DiscoveryCandidate,
    DiscoverySource,
)
from app.services.discovery.observe import observe

pytestmark = pytest.mark.usefixtures("no_external_network")

GRANTS = pathlib.Path(__file__).resolve().parents[3] / "db" / "roles" / "discovery_observer.sql"


@pytest.fixture
def observer_role(database_url):
    name = f"discovery_observer_t{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    with owner_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f"CREATE ROLE {name} LOGIN PASSWORD '{password}'"))
        conn.exec_driver_sql(GRANTS.read_text(encoding="utf-8").replace(
            "discovery_observer", name))
    url = make_url(get_settings().resolved_database_url).set(username=name, password=password)
    role_engine = create_engine(url, connect_args={"options": "-csearch_path=humanoid,public"})
    try:
        yield role_engine
    finally:
        role_engine.dispose()
        with owner_engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f"DROP OWNED BY {name}"))
            conn.execute(text(f"DROP ROLE {name}"))


def _cleanup(source_id) -> None:
    with Session(owner_engine) as s:
        runs = select(CrawlRun.id).where(CrawlRun.source_id == source_id)
        cands = select(DiscoveryCandidate.id).where(DiscoveryCandidate.source_id == source_id)
        s.execute(delete(DiscoveryEvidenceExcerpt).where(
            DiscoveryEvidenceExcerpt.discovery_source_id == source_id))
        s.execute(delete(CandidateCommercialSignal).where(
            CandidateCommercialSignal.discovery_source_id == source_id))
        s.execute(delete(CandidateImageRef).where(CandidateImageRef.candidate_id.in_(cands)))
        s.execute(delete(CandidateClaim).where(CandidateClaim.candidate_id.in_(cands)))
        s.execute(delete(ExtractionResult).where(ExtractionResult.crawl_run_id.in_(runs)))
        s.execute(delete(DiscoveryCandidate).where(DiscoveryCandidate.source_id == source_id))
        s.execute(delete(FetchedPage).where(FetchedPage.source_id == source_id))
        s.execute(delete(CrawlRun).where(CrawlRun.source_id == source_id))
        s.execute(delete(DiscoverySource).where(DiscoverySource.id == source_id))
        s.commit()


def test_one_cycle_runs_as_the_observer_role_and_nothing_else_is_writable(
        observer_role, tmp_path):
    with Session(owner_engine, expire_on_commit=False) as owner:
        h = Harness(owner, tmp_path)
        site = h.source("role")
        owner.commit()
        source_id = owner.scalars(select(DiscoverySource.id).where(
            DiscoverySource.key == site.key)).one()
    try:
        with Session(observer_role, expire_on_commit=False) as session:
            h.session = session
            result = observe(session, h.adapters, cache_dir=h.cache_dir, now=h.now,
                             fetcher_for=h._fetcher, only=site.key, checkpoint=session.commit)
            [obs] = result.sources
            assert obs.status == "COMPLETED", obs.detail
            assert obs.counts["new_entity"] == 2
        with observer_role.connect() as conn:
            for sql in (
                "INSERT INTO robot (slug, manufacturer_id, name) SELECT 'x', id, 'x' "
                "FROM manufacturer LIMIT 1",
                "UPDATE manufacturer SET name = name",
                "INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type) "
                "VALUES ('ROBOT', gen_random_uuid(), 'https://x', 'OTHER')",
                "SELECT count(*) FROM commercial_lead",
                "DELETE FROM fetched_page",
                "UPDATE discovery_source SET tos_status = 'ALLOWED'",
                "UPDATE discovery_source SET observation_interval_hours = 6",
                "INSERT INTO candidate_identity_decision (candidate_a_id, candidate_b_id, "
                "decision, decided_by, reason) VALUES (gen_random_uuid(), gen_random_uuid(), "
                "'SAME_ENTITY', 'x', 'x')",
                "INSERT INTO promotion_audit (action, approved_by) VALUES ('PROMOTED', 'x')",
                "CREATE TABLE humanoid.observer_ddl (id int)",
            ):
                with pytest.raises(ProgrammingError, match="permission denied"):
                    conn.execute(text(sql))
                conn.rollback()
    finally:
        _cleanup(source_id)


# ---------------------------------------------------------------------------------------------
# G5-1: the Lane B enrichment planner under the SAME least-privilege role.
# ---------------------------------------------------------------------------------------------

#: The relations the planner's query path reads beyond the Stage F baseline (derived from
#: services/readiness_loader.load_records and services/discovery/enrichment.load_inputs), and
#: granted SELECT-only by db/roles/discovery_observer.sql. Nothing here is granted "just in case".
PLANNER_READ_ONLY = (
    "robot_variant", "specification", "spec_definition", "evidence_source", "pricing_offer",
    "availability_offer", "deployment", "accepted_claim", "claim_retraction",
    "discovery_proposal_decision",
)


def _role_name(engine) -> str:
    return engine.url.username


def test_enrichment_planner_runs_as_the_observer_role(observer_role):
    from app.cli.discovery import _enrichment_summary
    from app.services.discovery import enrichment
    from app.services.discovery.sources import ADAPTERS

    with Session(owner_engine) as owner:
        expected = owner.scalar(text("SELECT count(*) FROM robot"))
    assert expected > 0
    with Session(observer_role) as session:
        rows = enrichment.plan_catalogue(session, ADAPTERS)
        assert len(rows) == expected                       # every robot is in the queue
        summary = _enrichment_summary(session)
        assert summary is not None and summary["catalogue_robots"] == expected
        assert summary["fetches_made"] == 0 and summary["canonical_rows_written"] == 0
        session.rollback()


def test_planner_relations_are_select_only_and_nothing_mutates(observer_role):
    role = _role_name(observer_role)
    with owner_engine.connect() as conn:
        grants = conn.execute(text(
            "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = :r AND table_schema = 'humanoid'"), {"r": role}).all()
        schema_privs = conn.execute(text(
            "SELECT has_schema_privilege(:r, 'humanoid', 'CREATE')"), {"r": role}).scalar()
    by_table: dict[str, set[str]] = {}
    for table, priv in grants:
        by_table.setdefault(table, set()).add(priv)
    for table in PLANNER_READ_ONLY:
        assert by_table.get(table) == {"SELECT"}, (table, by_table.get(table))
    for table in ("robot", "manufacturer", "robot_image"):   # baseline reads stay read-only
        assert by_table[table] == {"SELECT"}
    forbidden = {"DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
    assert not [t for t, p in by_table.items() if p & forbidden]
    assert schema_privs is False
    with observer_role.connect() as conn:
        for sql in (
            "UPDATE specification SET value_text = value_text",
            "DELETE FROM pricing_offer",
            "UPDATE availability_offer SET is_current = is_current",
            "INSERT INTO deployment (robot_id) SELECT id FROM robot LIMIT 1",
            "UPDATE robot SET is_published = is_published",
            "UPDATE robot_variant SET name = name",
            "DELETE FROM accepted_claim",
            "DELETE FROM claim_retraction",
            "INSERT INTO discovery_proposal_decision (proposal_id, decision, decided_by, "
            "rationale) VALUES (gen_random_uuid(), 'ACCEPT', 'x', 'x')",
            "UPDATE spec_definition SET label = label",
            "TRUNCATE evidence_source",
        ):
            with pytest.raises(ProgrammingError, match="permission denied"):
                conn.execute(text(sql))
            conn.rollback()


def test_planner_never_changes_the_cycle_exit_status(observer_role, monkeypatch):
    from app.cli import discovery as cli
    from app.services.discovery import enrichment
    from app.services.discovery.observe import CycleResult

    def boom(*a, **k):
        raise RuntimeError("planner unavailable")

    monkeypatch.setattr(enrichment, "plan_catalogue", boom)
    with Session(observer_role) as session:
        assert cli._enrichment_summary(session) is None     # swallowed, session still usable
        assert session.scalar(text("SELECT 1")) == 1
    from datetime import UTC, datetime
    bare = CycleResult(started_at=datetime.now(UTC), plan_only=False)
    with_planner = CycleResult(started_at=bare.started_at, plan_only=False,
                               enrichment={"catalogue_robots": 1})
    assert bare.exit_code == with_planner.exit_code == 0


def test_observe_cli_prints_the_enrichment_section(capsys, tmp_path):
    """The wiring: `discovery observe --plan` reports the planner (not 'unavailable')."""
    from app.cli.discovery import main

    code = main(["observe", "--plan", "--cache-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "NEW MODEL RADAR" in out and "CATALOGUE ENRICHMENT" in out
    assert "catalogue robots=" in out and "unavailable" not in out


# ---------------------------------------------------------------------------------------------
# G5-4: the planner -> executor path under the SAME role; no privilege was added for it.
# ---------------------------------------------------------------------------------------------


def test_the_g5_plan_and_lane_b_plan_run_as_the_observer_with_select_only_accepted_claims(
        observer_role, tmp_path):
    from app.services.discovery import enrichment_fetch, enrichment_plan
    from app.services.discovery.sources import ADAPTERS

    with Session(observer_role) as session:
        plans, sources = enrichment_plan.plan_sources(session, ADAPTERS)
        res = enrichment_fetch.run_lane_b(session, plans, sources, plan_only=True,
                                          cache_dir=tmp_path / "cache")
        assert res.plan_only and res.failed is False
        session.rollback()
    with observer_role.connect() as conn:
        for sql in ("INSERT INTO accepted_claim (claim_digest) VALUES ('x')",
                    "UPDATE accepted_claim SET created_by = created_by",
                    "DELETE FROM accepted_claim",
                    "INSERT INTO claim_retraction (claim_id) VALUES (gen_random_uuid())"):
            with pytest.raises(ProgrammingError, match="permission denied"):
                conn.execute(text(sql))
            conn.rollback()
    grants = GRANTS.read_text(encoding="utf-8")
    assert "GRANT SELECT ON\n    robot_variant" in grants and "accepted_claim" in grants
    for forbidden in ("INSERT ON accepted_claim", "UPDATE ON accepted_claim",
                      "GRANT ALL", "discovery_reviewer"):
        assert forbidden not in grants
