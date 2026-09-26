"""NEURA identity-only deterministic extractor — offline (no NEURA request).

Fixtures are the reduced 2026-09-26 captures in tests/fixtures/neura_structure:
identity markers verbatim, body text and amounts synthetic. The extractor names a
model only when the URL slug and another deterministic locator agree; it never
reads <h1> or Elementor ids, and it emits no claim, signal or image.
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

from app.db.session import engine
from app.models.acquisition import CandidateCommercialSignal, ExtractionResult, FetchedPage
from app.models.discovery import CandidateClaim, DiscoveryCandidate, DiscoverySource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery.adapter_run import adapter_problems, run_adapter
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.live_adapter import (
    enumerate_targets,
    extract_product,
    extraction_digest,
)
from app.services.discovery.robots import parse
from app.services.discovery.sources.neura_robotics import BLOCK_CODE
from app.services.discovery.sources.neura_robotics import CONFIG as NEURA

FIXTURES = Path(__file__).parent / "fixtures" / "neura_structure"
HOST = "https://neura-robotics.com"
RESERVATION_URL = f"{HOST}/product/4ne1-reservation"
ROBOT_URL = f"{HOST}/products/4ne1"
MINI_URL = f"{HOST}/product/4ne1-mini-reservation"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


RESERVATION = fixture("reservation-4ne1.html")
ROBOT = fixture("robot-4ne1.html")


def edit(body: bytes, old: str, new: str) -> bytes:
    assert old.encode() in body, old
    return body.replace(old.encode(), new.encode())


# ------------------------------------------------------------------ identity --


def test_reservation_page_yields_the_deterministic_model_identity():
    result = extract_product(NEURA, RESERVATION, RESERVATION_URL)
    assert (result.status, result.name, result.name_method) == ("EXTRACTED", "4NE1", "SELECTOR")
    assert "agreeing locators: ['url_slug', 'breadcrumb', 'title']" in result.notes
    assert result.claims == () and result.signals == () and result.images == ()


def test_robot_page_identity_comes_from_breadcrumb_and_slug_never_h1():
    result = extract_product(NEURA, ROBOT, ROBOT_URL)
    assert (result.status, result.name) == ("EXTRACTED", "4NE1")
    assert "agreeing locators: ['url_slug', 'breadcrumb']" in result.notes
    assert "Tagline" not in extraction_digest(result)


def test_marketing_h1_can_never_become_an_identity():
    # Remove every real locator: only the tagline <h1> remains.
    no_crumb = edit(ROBOT, '"name":"4NE1"}', '"name":"Something Else"}')
    tagline_only = edit(no_crumb, '"name":"Products"', '"name":"Company"')
    result = extract_product(NEURA, tagline_only, ROBOT_URL)
    assert result.status == "NOTHING_FOUND" and result.name is None
    # Even a tagline that happens to slugify to the URL slug is never read.
    teasing = edit(tagline_only, "A Marketing Tagline For A Teammate", "4NE1")
    assert extract_product(NEURA, teasing, ROBOT_URL).name is None


@pytest.mark.parametrize(("body", "url", "why"), [
    (edit(RESERVATION, '"name":"4NE1 Reservation"', '"name":"4NE1 Mini Reservation"'),
     RESERVATION_URL, "breadcrumb vs title"),
    (edit(RESERVATION, '<title>Reserve 4NE1:', '<title>Reserve MiPA:'),
     RESERVATION_URL, "<title> vs og:title"),
    (edit(edit(RESERVATION, '<link rel="canonical" href="https://neura-robotics.com/product/'
                            '4ne1-reservation/" />', ''),
          '<meta property="og:url"', '<meta property="og:ignored"'),
     f"{HOST}/product/mipa-reservation", "names vs URL slug"),
    (RESERVATION, f"{HOST}/product/mipa-reservation", "canonical points elsewhere"),
    (edit(ROBOT, '"name":"4NE1"}', '"name":"MiPA"}'), ROBOT_URL, "breadcrumb vs slug"),
])
def test_disagreeing_locators_are_ambiguous(body, url, why):
    result = extract_product(NEURA, body, url)
    assert result.status == "AMBIGUOUS", why
    assert result.name is None


@pytest.mark.parametrize(("body", "url"), [
    (edit(RESERVATION, "single-product", "single-page"), RESERVATION_URL),  # no Woo marker
    (b"<html><head><title>x</title></head><body class='single-product'></body></html>",
     RESERVATION_URL),
    (b"<html><body><h1>4NE1</h1></body></html>", ROBOT_URL),
    (RESERVATION, f"{HOST}/news"),                                         # outside families
    (RESERVATION, None),                                                   # no URL
])
def test_insufficient_identity_evidence_is_nothing_found(body, url):
    result = extract_product(NEURA, body, url)
    assert result.status == "NOTHING_FOUND" and result.name is None


def test_reservation_fee_and_estimated_price_never_become_a_price():
    result = extract_product(NEURA, RESERVATION, RESERVATION_URL)
    assert result.signals == ()
    assert not any(s.axis == "PRICE" for s in result.signals)
    assert any("not extracted" in n for n in result.notes)


def test_replay_is_deterministic():
    for body, url in ((RESERVATION, RESERVATION_URL), (ROBOT, ROBOT_URL)):
        assert extraction_digest(extract_product(NEURA, body, url)) == \
            extraction_digest(extract_product(NEURA, bytes(body), url))


# ----------------------------------------------------------------- discovery --


def _robots():
    return parse((FIXTURES / "robots.txt").read_text(encoding="utf-8"))


def test_mini_is_discovered_from_one_level_links_despite_the_sitemap():
    seeds = [(f"{HOST}/product-sitemap.xml", fixture("product-sitemap.xml")),
             (f"{HOST}/news/", fixture("news.html")),
             (RESERVATION_URL + "/", RESERVATION)]
    result = enumerate_targets(NEURA, seeds, _robots(), {})
    assert MINI_URL in result.selected
    assert RESERVATION_URL not in result.selected       # a seed: extracted, never refetched
    assert all(u.startswith(HOST + "/product") for u in result.selected)
    assert len(result.selected) <= NEURA.target_cap and result.deferred == []


def test_source_stays_blocked_from_live_execution():
    problems = adapter_problems(NEURA, None)
    assert any(p.startswith(f"ADAPTER_BLOCKED ({BLOCK_CODE}:") for p in problems)
    assert NEURA.product_extractor is not None and NEURA.heading_identity is False


# ------------------------------------------------ end to end (offline, PG) --


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


ROUTES = {
    f"{HOST}/robots.txt": ("robots.txt", "text/plain"),
    f"{HOST}/product-sitemap.xml": ("product-sitemap.xml", "application/xml"),
    f"{HOST}/news": ("news.html", "text/html; charset=UTF-8"),
    RESERVATION_URL: ("reservation-4ne1.html", "text/html; charset=UTF-8"),
    ROBOT_URL: ("robot-4ne1.html", "text/html; charset=UTF-8"),
}


@pytest.mark.usefixtures("no_external_network")
def test_offline_run_extracts_identity_only_and_leaves_review_to_humans(dsession, tmp_path):
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
        key=f"neura-offline-{tag}", name="NEURA (offline test)", source_class="MANUFACTURER",
        homepage_url=f"{HOST}/", allowed_path_prefixes=list(NEURA.allowed_path_prefixes),
        is_enabled=True, tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime(2026, 9, 26, tzinfo=UTC),
        eligibility_reviewed_by="fixture-reviewer",
    )
    dsession.add(source)
    dsession.flush()
    before = (dsession.scalar(select(func.count()).select_from(Robot)),
              dsession.scalar(select(func.count()).select_from(Manufacturer)))
    # Approval is simulated for this offline test ONLY; the shipped CONFIG stays blocked.
    config = replace(NEURA, source_key=source.key, blocked_reason=None)
    assert adapter_problems(config, source) == []

    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requests.append(url)
        if url not in ROUTES:
            return httpx.Response(404)
        name, ctype = ROUTES[url]
        return httpx.Response(200, headers={"content-type": ctype}, content=fixture(name))

    clock = Clock()
    fetcher = HttpFetcher(limits=FetchLimits(page_cap=60), transport=httpx.MockTransport(handler),
                          monotonic=clock.monotonic, sleep=clock.sleep)
    with fetcher:
        run = run_adapter(dsession, source=source, config=config, operator="offline-test",
                          fetcher=fetcher, now=clock.now, cache_dir=tmp_path / "cache")

    assert run.status == "COMPLETED"
    assert requests.count(RESERVATION_URL) == 1            # the seed is never refetched
    assert MINI_URL in requests                            # discovered despite the sitemap
    assert clock.sleeps and all(s == 3.0 for s in clock.sleeps)

    cands = {c.external_ref: c for c in dsession.scalars(select(DiscoveryCandidate).where(
        DiscoveryCandidate.source_id == source.id))}
    assert set(cands) == {RESERVATION_URL, ROBOT_URL}
    assert {c.candidate_name for c in cands.values()} == {"4NE1"}
    assert {c.candidate_manufacturer for c in cands.values()} == {"Neura Robotics"}
    # No alias: '4NE1' never silently matches the catalogue's '4NE-1'.
    assert {c.identity_status for c in cands.values()} == {"NEW_ENTITY", "POSSIBLE_DUPLICATE"}
    assert all(c.promoted_robot_id is None for c in cands.values())
    for model in (CandidateClaim, CandidateCommercialSignal):
        column = model.candidate_id
        assert dsession.scalar(select(func.count()).select_from(model).where(
            column.in_([c.id for c in cands.values()]))) == 0
    seed_page = dsession.scalars(select(FetchedPage).where(
        FetchedPage.crawl_run_id == run.id, FetchedPage.url == RESERVATION_URL)).one()
    assert dsession.scalars(select(ExtractionResult).where(
        ExtractionResult.fetched_page_id == seed_page.id)).one().status == "EXTRACTED"
    assert (dsession.scalar(select(func.count()).select_from(Robot)),
            dsession.scalar(select(func.count()).select_from(Manufacturer))) == before
    assert run.counters["extraction"]["canonical_rows_written"] == 0
