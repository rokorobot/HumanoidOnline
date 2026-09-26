"""Slice B — one adapter run end to end, offline, against PostgreSQL.

seed -> bounded enumeration -> acquisition -> deterministic extraction ->
evidence -> candidate / claims / signals -> existing resolve_identity -> human
review. The site is the SYNTHETIC fixture in tests/fixtures/discovery_adapter,
served through httpx.MockTransport (the `no_external_network` guard fails the
test on any socket). Each test is rollback-isolated with its own source and a
unique fictional manufacturer, so it never collides with other candidates.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
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
    PromotionAudit,
)
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery.acquisition import build_report
from app.services.discovery.adapter_run import AdapterRefused, plan_adapter, run_adapter
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.live_adapter import SourceAdapterConfig
from app.services.discovery.sources.neura_robotics import CONFIG as NEURA

pytestmark = pytest.mark.usefixtures("no_external_network")

FIXTURES = Path(__file__).parent / "fixtures" / "discovery_adapter"
HOST = "https://maker.example"
ALPHA = f"{HOST}/products/ex-alpha-7"
BETA = f"{HOST}/products/ex-beta-2"
GAMMA = f"{HOST}/products/ex-gamma"
SERIES = f"{HOST}/products/ex-series"
DUO = f"{HOST}/products/ex-duo"
OMEGA_NEWS = f"{HOST}/news/2026/ex-omega-unveiled"
UPDATE_NEWS = f"{HOST}/news/2026/company-update"
CANONICAL_TABLES = (Robot, Manufacturer, PromotionAudit)


# ------------------------------------------------------------------ fixtures --


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


class Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.base = datetime(2026, 9, 26, 12, tzinfo=UTC)
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def now(self) -> datetime:
        return self.base + timedelta(seconds=self.t)


class FixtureSite:
    """Serves one fixture version; records every request."""

    def __init__(self, maker: str, version: str = "v1") -> None:
        self.maker = maker
        self.requests: list[str] = []
        self.load(version)

    def load(self, version: str) -> None:
        directory = FIXTURES / version
        self.routes = json.loads((directory / "site.json").read_text(encoding="utf-8"))
        self.directory = directory

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        entry = self.routes.get(url)
        if entry is None:
            return httpx.Response(404)
        if isinstance(entry, dict):
            return httpx.Response(entry["status"])
        path = (self.directory / entry).resolve()
        body = path.read_text(encoding="utf-8").replace("__MAKER__", self.maker)
        ctype = {".html": "text/html; charset=utf-8", ".xml": "application/xml",
                 ".txt": "text/plain"}[path.suffix]
        return httpx.Response(200, headers={"content-type": ctype}, text=body)

    def targets(self) -> list[str]:
        return [u for u in self.requests if not u.endswith("/robots.txt")]


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def world(dsession):
    """A registered, approved source; a unique fictional maker with two
    canonical robots (EX-Gamma, EX-Delta); and a matching adapter config."""
    tag = uuid.uuid4().hex[:8]
    maker = f"Example{tag} Robotics"
    mfr = Manufacturer(slug=f"example-{tag}", name=maker)
    dsession.add(mfr)
    dsession.flush()
    gamma = Robot(slug=f"ex-gamma-{tag}", manufacturer_id=mfr.id, name="EX-Gamma",
                  is_published=True)
    delta = Robot(slug=f"ex-delta-{tag}", manufacturer_id=mfr.id, name="EX-Delta",
                  is_published=True)
    source = DiscoverySource(
        key=f"example-{tag}", name=f"{maker} official site", source_class="MANUFACTURER",
        homepage_url=f"{HOST}/", allowed_path_prefixes=["/products", "/news", "/sitemap.xml"],
        is_enabled=True, tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime(2026, 9, 1, tzinfo=UTC),
        eligibility_reviewed_by="fixture-reviewer",
    )
    dsession.add_all([gamma, delta, source])
    dsession.flush()
    config = SourceAdapterConfig(
        key="example-fixture", version="1.0.0", source_key=source.key,
        source_class="MANUFACTURER", host="maker.example", manufacturer=maker,
        allowed_path_prefixes=("/products", "/news", "/sitemap.xml"),
        seed_urls=(f"{HOST}/products", f"{HOST}/sitemap.xml"),
        product_path_pattern=re.compile(r"/products/[a-z0-9-]+"),
        announcement_path_pattern=re.compile(r"/news/\d{4}/[a-z0-9-]+"),
        property_map={"payload": ("payload_kg", "kg"), "height": ("height_m", "m")},
        quote_phrases=("price on request",),
        structural_review="fixture: synthetic pages",
    )
    return {"maker": maker, "mfr": mfr, "gamma": gamma, "source": source, "config": config}


def _run(dsession, world, clock, tmp_path, site, config=None):
    fetcher = HttpFetcher(limits=FetchLimits(page_cap=60), transport=httpx.MockTransport(site),
                          monotonic=clock.monotonic, sleep=clock.sleep)
    with fetcher:
        return run_adapter(dsession, source=world["source"], config=config or world["config"],
                           operator="fixture-operator", fetcher=fetcher,
                           cache_dir=tmp_path / "cache", now=clock.now)


def _candidate(dsession, source, url) -> DiscoveryCandidate | None:
    return dsession.scalars(select(DiscoveryCandidate).where(
        DiscoveryCandidate.source_id == source.id, DiscoveryCandidate.external_ref == url)).first()


def _canonical_counts(dsession) -> dict:
    return {m.__tablename__: dsession.scalar(select(func.count()).select_from(m))
            for m in CANONICAL_TABLES}


def _signals(dsession, candidate) -> list[CandidateCommercialSignal]:
    return dsession.scalars(select(CandidateCommercialSignal).where(
        CandidateCommercialSignal.candidate_id == candidate.id)).all()


# ------------------------------------------------------------------- tests --


def test_first_run_detects_every_first_observation_outcome(dsession, world, clock, tmp_path):
    source = world["source"]
    # A manual-bootstrap-style candidate for EX-Beta 2 already exists elsewhere.
    other = DiscoverySource(key=f"bootstrap-{uuid.uuid4().hex[:8]}", name="Bootstrap",
                            source_class="OTHER")
    dsession.add(other)
    dsession.flush()
    dsession.add(DiscoveryCandidate(source_id=other.id, entity_type="ROBOT",
                                    external_ref="bootstrap/ex-beta-2", candidate_name="EX-Beta 2",
                                    candidate_manufacturer=world["maker"]))
    dsession.flush()
    before = _canonical_counts(dsession)
    site = FixtureSite(world["maker"])

    run = _run(dsession, world, clock, tmp_path, site)

    assert run.status == "COMPLETED"
    # One level only: seeds, then the seven targets; excluded links never requested.
    assert site.targets() == [
        f"{HOST}/products", f"{HOST}/sitemap.xml",
        UPDATE_NEWS, OMEGA_NEWS, ALPHA, BETA, DUO, GAMMA, SERIES,
    ]
    assert not any("ex-private" in u or "other.example" in u or "sitemap-products" in u
                   for u in site.requests)
    assert source.is_enabled  # a robots-disallowed LINK is excluded, not a source halt
    # robots Crawl-delay: 3 overrides the 2 s floor between every request.
    assert clock.sleeps and all(s == 3.0 for s in clock.sleeps)
    assert run.run_manifest["effective_min_interval_seconds"] == 3.0

    alpha = _candidate(dsession, source, ALPHA)
    beta = _candidate(dsession, source, BETA)
    gamma = _candidate(dsession, source, GAMMA)
    series = _candidate(dsession, source, SERIES)
    omega = _candidate(dsession, source, OMEGA_NEWS)
    assert (alpha.identity_status, alpha.candidate_manufacturer) == ("NEW_ENTITY", world["maker"])
    assert beta.identity_status == "POSSIBLE_DUPLICATE"        # vs the bootstrap candidate
    assert (gamma.identity_status, gamma.possible_robot_id) == ("MATCHED_EXISTING",
                                                                world["gamma"].id)
    assert series.identity_status == "AMBIGUOUS"               # no model identity, 2 siblings
    assert (omega.candidate_name, omega.identity_status) == ("EX-Omega", "NEW_ENTITY")
    assert _candidate(dsession, source, DUO) is None           # multi-product page: no guess
    assert _candidate(dsession, source, UPDATE_NEWS) is None   # announcement without identity
    for cand in (alpha, beta, gamma, series, omega):
        assert cand.status in ("SOURCE_TRACE", "POSSIBLE_DUPLICATE", "IDENTITY_REVIEW")
        assert cand.promoted_robot_id is None and cand.trace_state == "NOT_TRACED"

    # Commercial facts: evidence-bound, NOT_VERIFIED, axes separate, UNKNOWN kept.
    assert {(s.axis, s.price_type, s.availability_value, str(s.price_amount), s.price_currency)
            for s in _signals(dsession, alpha)} == {
        ("PRICE", "PUBLIC", None, "49000.00", "USD"),
        ("OBTAINABILITY", None, "AVAILABLE", "None", None)}
    assert {(s.axis, s.price_type, s.availability_value) for s in _signals(dsession, beta)} == {
        ("PRICE", "QUOTE_ONLY", None), ("OBTAINABILITY", None, "ON_REQUEST")}
    assert _signals(dsession, gamma) == [] and _signals(dsession, series) == []
    assert not any(s.availability_value == "NOT_AVAILABLE"
                   for s in dsession.scalars(select(CandidateCommercialSignal).where(
                       CandidateCommercialSignal.discovery_source_id == source.id)))
    assert {(c.field_key, c.claimed_value, c.unit, c.claim_status) for c in alpha.claims} == {
        ("payload_kg", "20", "kg", "NOT_VERIFIED"), ("height_m", "1.70", "m", "NOT_VERIFIED")}
    image = dsession.scalars(select(CandidateImageRef).where(
        CandidateImageRef.candidate_id == alpha.id)).one()
    assert (image.retrieval_source_class, image.media_status) == ("MANUFACTURER", "CANDIDATE")

    # Gate J: every claim and signal has an excerpt with URL, time, hash, locator.
    claims = dsession.scalars(select(CandidateClaim).where(
        CandidateClaim.discovery_source_id == source.id)).all()
    signals = dsession.scalars(select(CandidateCommercialSignal).where(
        CandidateCommercialSignal.discovery_source_id == source.id)).all()
    assert claims and signals
    for subject_type, rows in (("CLAIM", claims), ("COMMERCIAL_SIGNAL", signals)):
        for row in rows:
            assert row.extraction_confidence and row.crawl_run_id == run.id
            excerpt = dsession.scalars(select(DiscoveryEvidenceExcerpt).where(
                DiscoveryEvidenceExcerpt.subject_type == subject_type,
                DiscoveryEvidenceExcerpt.subject_id == row.id)).one()
            assert excerpt.page_url and excerpt.retrieved_at and excerpt.page_hash
            assert excerpt.locator and len(excerpt.excerpt_text) <= 1000

    # The announcement without identity is evidence waiting for a human.
    update_page = dsession.scalars(select(FetchedPage).where(
        FetchedPage.crawl_run_id == run.id, FetchedPage.url == UPDATE_NEWS)).one()
    result = dsession.scalars(select(ExtractionResult).where(
        ExtractionResult.fetched_page_id == update_page.id)).one()
    notes = json.loads(result.notes)
    assert (result.status, result.candidate_id) == ("AMBIGUOUS", None)
    assert notes["classification"] == "NEW_ANNOUNCEMENT_URL"
    assert notes["headline"] == "A new humanoid is coming" and "Stay tuned" in notes["excerpt"]
    assert notes["page_hash"] == update_page.content_hash

    extraction = run.counters["extraction"]
    assert extraction["new_product_urls"] == 4
    assert extraction["known_robot_new_url"] == 1
    assert extraction["new_announcement_urls"] == 2
    assert extraction["announcement_candidates"] == 1
    assert extraction["newly_orderable"] == 1                  # EX-Alpha 7 InStock
    assert extraction["canonical_rows_written"] == 0
    assert _canonical_counts(dsession) == before               # enforced, not hoped

    report = build_report(dsession, run.id)
    assert "EXCLUDED ROBOTS_DISALLOW" in report and "Canonical rows written" in report
    assert "known robot at a new URL" in report


def test_second_run_detects_changes_removals_and_skips_unchanged(dsession, world, clock,
                                                                  tmp_path):
    source = world["source"]
    site = FixtureSite(world["maker"])
    _run(dsession, world, clock, tmp_path, site)
    clock.t += 7 * 24 * 3600
    site.load("v2")
    before = _canonical_counts(dsession)

    run = _run(dsession, world, clock, tmp_path, site)

    extraction = run.counters["extraction"]
    alpha = _candidate(dsession, source, ALPHA)
    beta = _candidate(dsession, source, BETA)
    gamma = _candidate(dsession, source, GAMMA)
    # Changed price: a NEW signal row, the old one preserved (never overwritten).
    assert sorted(str(s.price_amount) for s in _signals(dsession, alpha)
                  if s.axis == "PRICE") == ["49000.00", "52000.00"]
    assert extraction["price_changes"] == 1
    # Changed specification: both values preserved for a human.
    assert sorted(c.claimed_value for c in alpha.claims if c.field_key == "payload_kg") == \
        ["20", "25"]
    assert extraction["changed_specifications"] == 1 and extraction["claims_unchanged"] == 1
    # Newly orderable (preorder).
    assert {s.availability_value for s in _signals(dsession, beta)
            if s.axis == "OBTAINABILITY"} == {"ON_REQUEST", "PREORDER"}
    assert extraction["newly_orderable"] == 1
    # Removed page.
    assert gamma.status == "RECHECK_REQUIRED" and extraction["removed_pages"] == 1
    # Unchanged pages are not re-extracted (Gate F).
    assert extraction["unchanged_not_reextracted"] == 4        # duo, series, both news
    assert extraction["changed_pages"] == 2
    assert extraction["new_product_urls"] == 0 and extraction["new_announcement_urls"] == 0
    assert _canonical_counts(dsession) == before
    assert dsession.scalar(select(func.count()).select_from(DiscoveryCandidate).where(
        DiscoveryCandidate.source_id == source.id)) == 5       # re-crawl reaches the same rows


def test_cap_defers_and_records_rather_than_drops(dsession, world, clock, tmp_path):
    config = replace(world["config"], target_cap=2)
    site = FixtureSite(world["maker"])
    run = _run(dsession, world, clock, tmp_path, site, config)
    enumeration = run.run_manifest["enumeration"]
    assert enumeration["selected"] == [UPDATE_NEWS, OMEGA_NEWS]
    assert enumeration["deferred"] == [ALPHA, BETA, DUO, GAMMA, SERIES]
    assert site.targets()[2:] == [UPDATE_NEWS, OMEGA_NEWS]
    assert "DEFERRED (not fetched this run)  " + ALPHA in build_report(dsession, run.id)

    clock.t += 3600
    site.requests.clear()
    second = _run(dsession, world, clock, tmp_path, site, config)
    assert second.run_manifest["enumeration"]["selected"] == [ALPHA, BETA]  # unseen first


def test_refused_adapter_issues_no_request(dsession, world, clock, tmp_path):
    source = world["source"]
    cases = {
        "ADAPTER_NOT_STRUCTURALLY_REVIEWED": replace(world["config"], structural_review=None),
        "SOURCE_KEY_MISMATCH": replace(world["config"], source_key="someone-else"),
        "SOURCE_CLASS_MISMATCH": replace(world["config"], source_class="AGGREGATOR"),
        "HOST_NOT_APPROVED": replace(world["config"], host="other.example"),
        "PATH_PREFIX_NOT_APPROVED": replace(world["config"],
                                            allowed_path_prefixes=("/products", "/shop")),
    }
    for reason, config in cases.items():
        site = FixtureSite(world["maker"])
        with pytest.raises(AdapterRefused) as refused:
            _run(dsession, world, clock, tmp_path, site, config)
        assert any(r.startswith(reason) for _, r in refused.value.problems), reason
        assert site.requests == []
    source.is_enabled = False
    site = FixtureSite(world["maker"])
    with pytest.raises(AdapterRefused):
        _run(dsession, world, clock, tmp_path, site)
    assert site.requests == []
    assert dsession.scalar(select(func.count()).select_from(CrawlRun).where(
        CrawlRun.source_id == source.id)) == 0


def test_neura_adapter_is_refused_until_reviewed(dsession):
    assert set(plan_adapter(NEURA, None)) >= {
        "ADAPTER_NOT_STRUCTURALLY_REVIEWED", "ADAPTER_HAS_NO_SEEDS",
        "ADAPTER_HAS_NO_PATH_PREFIXES", "SOURCE_NOT_REGISTERED"}


def test_replay_of_the_fixture_run_is_identical(dsession, world, clock, tmp_path):
    """§15 / Gate I: replaying the recorded site from the same starting state
    gives byte-identical extraction output."""
    def snapshot(run) -> list:
        rows = dsession.execute(
            select(ExtractionResult.status, FetchedPage.url, ExtractionResult.notes)
            .join(FetchedPage, FetchedPage.id == ExtractionResult.fetched_page_id)
            .where(ExtractionResult.crawl_run_id == run.id).order_by(FetchedPage.url)).all()
        claims = dsession.execute(
            select(DiscoveryCandidate.external_ref, CandidateClaim.field_key,
                   CandidateClaim.claimed_value, CandidateClaim.unit)
            .join(DiscoveryCandidate, DiscoveryCandidate.id == CandidateClaim.candidate_id)
            .where(CandidateClaim.crawl_run_id == run.id)
            .order_by(DiscoveryCandidate.external_ref, CandidateClaim.field_key)).all()
        return [tuple(r) for r in rows], [tuple(c) for c in claims]

    outputs = []
    for attempt in range(2):
        savepoint = dsession.begin_nested()
        clock.t = 0.0
        run = _run(dsession, world, clock, tmp_path / str(attempt), FixtureSite(world["maker"]))
        outputs.append(snapshot(run))
        savepoint.rollback()
    assert outputs[0][0] and outputs[0][1]
    assert outputs[0] == outputs[1]
