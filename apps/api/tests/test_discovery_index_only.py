"""INDEX-ONLY adapter runs — offline, against PostgreSQL, NEURA fixtures.

An index-only run fetches the reviewed seeds only (same gates, robots.txt and
3 s interval as a full run), enumerates one level, and reports what WOULD be
targeted. It never requests a target, never creates a candidate, claim or
signal, and never writes a catalogue row.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import discovery as cli
from app.db.session import engine
from app.models.acquisition import CandidateCommercialSignal, CrawlRun, ExtractionResult
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery.acquisition import build_report
from app.services.discovery.adapter_run import AdapterRefused, index_adapter
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.sources.neura_robotics import CONFIG as NEURA

pytestmark = pytest.mark.usefixtures("no_external_network")

FIXTURES = Path(__file__).parent / "fixtures" / "neura_structure"
HOST = "https://neura-robotics.com"
SEEDS = {
    f"{HOST}/robots.txt": ("robots.txt", "text/plain"),
    f"{HOST}/product-sitemap.xml": ("product-sitemap.xml", "application/xml"),
    f"{HOST}/news": ("news.html", "text/html; charset=UTF-8"),
    f"{HOST}/product/4ne1-reservation": ("reservation-4ne1.html", "text/html; charset=UTF-8"),
}
MINI = f"{HOST}/product/4ne1-mini-reservation"


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
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def now(self) -> datetime:
        return datetime(2026, 9, 26, 12, tzinfo=UTC) + timedelta(seconds=self.t)


def _world(dsession):
    tag = uuid.uuid4().hex[:6]
    mfr = dsession.scalars(
        select(Manufacturer).where(Manufacturer.name == "Neura Robotics")).first()
    if mfr is None:
        mfr = Manufacturer(slug=f"neura-robotics-{tag}", name="Neura Robotics")
        dsession.add(mfr)
        dsession.flush()
    dsession.add(Robot(slug=f"neura-4ne-1-{tag}", manufacturer_id=mfr.id, name="4NE-1",
                       is_published=True))
    source = DiscoverySource(
        key=f"neura-index-{tag}", name="NEURA (index test)", source_class="MANUFACTURER",
        homepage_url=f"{HOST}/", allowed_path_prefixes=list(NEURA.allowed_path_prefixes),
        is_enabled=True, tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime(2026, 9, 26, tzinfo=UTC),
        eligibility_reviewed_by="fixture-reviewer",
    )
    dsession.add(source)
    dsession.flush()
    return source, replace(NEURA, source_key=source.key)


def _run(dsession, source, config, tmp_path, requests):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requests.append(url)
        if url not in SEEDS:
            return httpx.Response(404)
        name, ctype = SEEDS[url]
        return httpx.Response(200, headers={"content-type": ctype},
                              content=(FIXTURES / name).read_bytes())

    clock = Clock()
    fetcher = HttpFetcher(limits=FetchLimits(page_cap=60), transport=httpx.MockTransport(handler),
                          monotonic=clock.monotonic, sleep=clock.sleep)
    with fetcher:
        run = index_adapter(dsession, source=source, config=config, operator="index-test",
                            fetcher=fetcher, cache_dir=tmp_path / "cache", now=clock.now)
    return run, clock


def test_index_only_fetches_seeds_only_and_reports_what_would_be_targeted(dsession, tmp_path):
    source, config = _world(dsession)
    counts = lambda: tuple(  # noqa: E731
        dsession.scalar(select(func.count()).select_from(m)) for m in (Robot, Manufacturer))
    before = counts()
    requests: list[str] = []
    run, clock = _run(dsession, source, config, tmp_path, requests)

    # Only robots.txt and the three reviewed seeds were requested, 3 s apart.
    assert requests == [f"{HOST}/robots.txt", *NEURA.seed_urls]
    assert clock.sleeps and all(s == 3.0 for s in clock.sleeps)
    assert run.status == "COMPLETED" and run.run_manifest["mode"] == "INDEX_ONLY"
    assert run.run_manifest["expanded_urls"] == []
    assert run.run_manifest["effective_min_interval_seconds"] == 3.0

    report = run.run_manifest["index_report"]
    assert [s["outcome"] for s in report["seeds"]] == ["FETCHED"] * 3
    qualifying = {q["url"]: q for q in report["qualifying"]}
    assert MINI in qualifying and qualifying[MINI]["cap"] == "SELECTED"
    assert qualifying[MINI]["unseen"] is True
    assert MINI in report["link_only"] and MINI in report["absent_from_sitemap_but_linked"]
    assert f"{HOST}/product/mipa-reservation" in report["sitemap_and_links"]
    assert f"{HOST}/products/4ne1" in report["link_only"]
    assert f"{HOST}/product/4ne1-reservation" in report["seeds_linked"]
    assert {e["reason"] for e in report["excluded"]} >= {"OUTSIDE_PATHS"}
    assert f"{HOST}/shop" in {e["url"] for e in report["excluded"]}
    assert len(report["targets_not_fetched"]) <= NEURA.target_cap

    [seed_product] = report["seed_products"]
    assert (seed_product["status"], seed_product["name"]) == ("EXTRACTED", "4NE1")
    # The existing resolver, read-only: no alias, so no silent match to '4NE-1'.
    assert seed_product["predicted"]["identity_status"] == "NEW_ENTITY"

    # Nothing extracted or written beyond the run and its seed observations.
    for model in (DiscoveryCandidate, ExtractionResult):
        column = model.source_id if model is DiscoveryCandidate else ExtractionResult.crawl_run_id
        target = source.id if model is DiscoveryCandidate else run.id
        assert dsession.scalar(select(func.count()).select_from(model).where(
            column == target)) == 0
    assert dsession.scalar(select(func.count()).select_from(CandidateCommercialSignal).where(
        CandidateCommercialSignal.discovery_source_id == source.id)) == 0
    assert counts() == before
    assert run.counters["canonical_rows_written"] == 0

    text = build_report(dsession, run.id)
    for heading in ("INDEX-ONLY", "SEEDS", "QUALIFYING URLS", "LINK-ONLY",
                    "ABSENT FROM SITEMAP BUT LINKED", "EXCLUDED", "SEED PRODUCT PAGES"):
        assert heading in text
    assert "resolver=NEW_ENTITY" in text


def test_second_index_run_prefers_unseen_and_still_fetches_no_target(dsession, tmp_path):
    source, config = _world(dsession)
    requests: list[str] = []
    _run(dsession, source, replace(config, target_cap=2), tmp_path / "a", requests)
    requests.clear()
    run, _ = _run(dsession, source, replace(config, target_cap=2), tmp_path / "b", requests)
    assert requests == [f"{HOST}/robots.txt", *NEURA.seed_urls]
    report = run.run_manifest["index_report"]
    assert sum(q["cap"] == "SELECTED" for q in report["qualifying"]) == 2
    assert all(q["unseen"] for q in report["qualifying"])        # no target was ever fetched
    assert run.run_manifest["enumeration"]["deferred"]           # recorded, not dropped


def test_index_only_obeys_every_gate(dsession, tmp_path):
    source, config = _world(dsession)
    source.is_enabled = False
    requests: list[str] = []
    with pytest.raises(AdapterRefused):
        _run(dsession, source, config, tmp_path, requests)
    assert requests == []
    assert dsession.scalar(select(func.count()).select_from(CrawlRun).where(
        CrawlRun.source_id == source.id)) == 0


def test_cli_rejects_index_only_with_resume():
    with pytest.raises(SystemExit):
        cli.main(["adapter", "run", "neura-robotics-official", "--operator", "x",
                  "--index-only", "--resume", "00000000-0000-0000-0000-000000000000"])
