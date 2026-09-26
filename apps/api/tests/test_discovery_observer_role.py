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
