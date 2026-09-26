"""NEURA source module after the 2026-09-26 structural review — offline.

The fixtures under tests/fixtures/neura_structure record STRUCTURE only
(robots rules, sitemap <loc> entries, link shapes); they carry no commercial
fact. The module is configured from that evidence but stays BLOCKED, because
the generic extractor is unsafe for this site (see the review document).
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.acquisition import CrawlRun, FetchedPage
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery.adapter_run import AdapterRefused, adapter_problems, run_adapter
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.live_adapter import (
    PRODUCT,
    enumerate_targets,
    extract_product,
    seed_links,
)
from app.services.discovery.robots import parse
from app.services.discovery.sources.neura_robotics import BLOCK_CODE, STRUCTURAL_FINDINGS
from app.services.discovery.sources.neura_robotics import CONFIG as NEURA
from app.services.discovery.urlref import normalize_url

FIXTURES = Path(__file__).parent / "fixtures" / "neura_structure"
HOST = "https://neura-robotics.com"
REVIEW = Path(__file__).resolve().parents[3] / "docs" / "discovery" / \
    "NEURA_STRUCTURAL_REVIEW_2026-09-26.md"


def _robots():
    return parse((FIXTURES / "robots.txt").read_text(encoding="utf-8"))


def _seeds():
    return [(f"{HOST}/product-sitemap.xml", (FIXTURES / "product-sitemap.xml").read_bytes()),
            (f"{HOST}/news/", (FIXTURES / "news.html").read_bytes())]


# ------------------------------------------------------------- configuration --


def test_config_is_the_reviewed_structure():
    assert (NEURA.host, NEURA.manufacturer, NEURA.source_class) == (
        "neura-robotics.com", "Neura Robotics", "MANUFACTURER")
    assert NEURA.allowed_path_prefixes == ("/products/", "/product/", "/product-sitemap.xml",
                                           "/news/")
    assert NEURA.seed_urls == (f"{HOST}/product-sitemap.xml", f"{HOST}/news")
    assert all(normalize_url(s) == s for s in NEURA.seed_urls)
    assert NEURA.target_cap == 50
    assert NEURA.announcement_path_pattern is None
    assert NEURA.property_map == {} and NEURA.quote_phrases == ()
    assert NEURA.structural_review and REVIEW.name in NEURA.structural_review
    assert REVIEW.is_file()
    assert NEURA.blocked_reason.startswith(f"{BLOCK_CODE}: ")
    assert NEURA.heading_identity is False
    for phrase in ("server-rendered", "robots-compatible", "no usable Product JSON-LD",
                   "<h1> is not a safe identity", "refundable reservation fee",
                   "estimated robot price"):
        assert phrase in NEURA.blocked_reason


def test_findings_record_only_what_the_seven_responses_established():
    assert [status for _, status in STRUCTURAL_FINDINGS["requests"]] == [
        200, 200, 200, 301, 200, 200, 200]
    assert STRUCTURAL_FINDINGS["robots_status"] == "ALLOWED"
    assert STRUCTURAL_FINDINGS["crawl_delay_seconds"] == 3
    assert set(STRUCTURAL_FINDINGS["url_families"]) == {
        "/products/<slug>/", "/product/<slug>-reservation/"}
    assert "4NE-1" in STRUCTURAL_FINDINGS["identity_issues"][0]
    language = STRUCTURAL_FINDINGS["commercial_language"]
    assert "NOT a price" in language["reservation_fee"]
    assert "NOT an actual purchase price" in language["estimated_price"]


def test_shop_is_not_a_viable_seed():
    shop = f"{HOST}/shop/"
    assert STRUCTURAL_FINDINGS["rejected_seeds"][shop].startswith("301")
    assert normalize_url(shop) not in NEURA.seed_urls
    assert not any(normalize_url(shop).endswith(p.rstrip("/")) for p in NEURA.allowed_path_prefixes)
    assert dict(enumerate_targets(NEURA, _seeds(), _robots(), {}).excluded)[
        f"{HOST}/shop"] == "OUTSIDE_PATHS"


@pytest.mark.parametrize("url", [
    f"{HOST}/products/4ne1", f"{HOST}/products/mipa", f"{HOST}/products/maira",
    f"{HOST}/product/4ne1-reservation", f"{HOST}/product/4ne1-mini-reservation",
    f"{HOST}/product/quadruped-reservation",
])
def test_product_pattern_accepts_observed_shapes(url):
    assert NEURA.kind_of(normalize_url(url + "/")) == PRODUCT


@pytest.mark.parametrize("url", [
    f"{HOST}/shop", f"{HOST}/de/produkt/4ne1-reservierung", f"{HOST}/product/4ne1",
    f"{HOST}/products/4ne1/specs", f"{HOST}/products", f"{HOST}/applications/gluing",
    f"{HOST}/neura-acquires-adlatus-robotics", f"{HOST}/2026/06/10", f"{HOST}/news",
    f"{HOST}/wp-json/wp/v2/product/35501",
])
def test_product_pattern_rejects_everything_else(url):
    assert NEURA.kind_of(url) is None


# --------------------------------------------------------------- enumeration --


def test_enumeration_is_bounded_to_host_prefixes_and_pattern():
    result = enumerate_targets(NEURA, _seeds(), _robots(), {})
    assert result.selected == [
        f"{HOST}/product/4ne1-reservation",
        f"{HOST}/product/mipa-reservation",
        f"{HOST}/product/quadruped-reservation",
        f"{HOST}/products/4ne1",
        f"{HOST}/products/lara",
        f"{HOST}/products/maira",
        f"{HOST}/products/mav",
        f"{HOST}/products/mipa",
    ]
    assert result.deferred == []                      # 8 targets, far under the cap of 50
    reasons = dict(result.excluded)
    assert reasons[f"{HOST}/shop"] == "OUTSIDE_PATHS"
    assert reasons[f"{HOST}/de/produkt/4ne1-reservierung"] == "OUTSIDE_PATHS"
    assert reasons[f"{HOST}/neura-acquires-adlatus-robotics"] == "OUTSIDE_PATHS"
    assert reasons[f"{HOST}/wp-json/wp/v2/pages/2670"] == "OUTSIDE_PATHS"
    assert all(urlsplit_host(u) == "neura-robotics.com" for u in result.selected)


def urlsplit_host(url: str) -> str:
    from urllib.parse import urlsplit
    return urlsplit(url).hostname or ""


def test_robots_as_observed_allows_targets_with_a_three_second_delay():
    rules = _robots()
    assert rules.crawl_delay == 3.0                   # "Crawl-delay:3", no space
    assert rules.allows(f"{HOST}/products/4ne1")
    with HttpFetcher(limits=FetchLimits()) as fetcher:
        assert fetcher.honour_crawl_delay("neura-robotics.com", rules.crawl_delay) == 3.0


def test_a_robots_disallow_excludes_targets():
    rules = parse("User-agent: HumanoidOnlineMarketBot\nDisallow: /product/\n")
    result = enumerate_targets(NEURA, _seeds(), rules, {})
    assert not any("/product/" in u for u in result.selected)
    assert dict(result.excluded)[f"{HOST}/product/4ne1-reservation"] == "ROBOTS_DISALLOW"


def test_capped_enumeration_defers_the_rest():
    result = enumerate_targets(replace(NEURA, target_cap=3), _seeds(), _robots(), {})
    assert len(result.selected) == 3 and len(result.deferred) == 5


# ---------------------------------------------------------------- extraction --


TAGLINE_PAGE = (
    b'<html><head><title>Humanoid Robot X for Work | Maker</title>'
    b'<script type="application/ld+json">{"@context":"https://schema.org","@graph":['
    b'{"@type":"WebPage","name":"Robot page"},{"@type":"BreadcrumbList"},'
    b'{"@type":"Organization","name":"Maker"}]}</script></head>'
    b"<body><h1>A Marketing Tagline</h1><p>synthetic text</p></body></html>"
)
# Synthetic figures with the observed SHAPE of the reservation wording only.
RESERVATION_PAGE = (
    b"<html><head><title>Reserve X: A Robot | Maker</title></head><body>"
    b"<h2>Reservation</h2><p>Estimated price/unit (1-19 units) 1,111 EUR "
    b"(excluding taxes and shipping)</p><p>Reservation fee 11EUR per unit</p>"
    b"<p>The reservation fee is fully refundable.</p></body></html>"
)


def test_a_marketing_h1_cannot_become_a_robot_identity():
    result = extract_product(NEURA, TAGLINE_PAGE)
    assert result.status == "NOTHING_FOUND" and result.name is None
    assert extract_product(NEURA, TAGLINE_PAGE) == result             # deterministic
    # The hazard it guards against: the generic heading fallback WOULD use it.
    generic = extract_product(replace(NEURA, heading_identity=True), TAGLINE_PAGE)
    assert generic.name == "A Marketing Tagline"


def test_no_product_jsonld_creates_no_candidate_identity():
    for body in (TAGLINE_PAGE, RESERVATION_PAGE, b"<html><body></body></html>"):
        result = extract_product(NEURA, body)
        assert result.status == "NOTHING_FOUND"
        assert result.name is None and result.claims == () and result.signals == ()


def test_reservation_fee_and_estimate_never_become_a_price():
    result = extract_product(NEURA, RESERVATION_PAGE)
    assert not any(s.axis == "PRICE" for s in result.signals)
    # Even with heading identity and generic quote phrases, free text is never a price.
    loose = replace(NEURA, heading_identity=True, quote_phrases=("price on request",))
    assert not any(s.axis == "PRICE" for s in extract_product(loose, RESERVATION_PAGE).signals)


def test_sitemap_omission_does_not_hide_a_linked_reservation_page():
    mini = f"{HOST}/product/4ne1-mini-reservation"
    sitemap_urls = {normalize_url(u)
                    for u in seed_links((FIXTURES / "product-sitemap.xml").read_bytes())}
    assert mini not in sitemap_urls                                   # omitted from the sitemap
    assert normalize_url(STRUCTURAL_FINDINGS["sitemap_omissions"][0]) == mini
    assert NEURA.kind_of(mini) == PRODUCT                             # but it qualifies
    linked = enumerate_targets(
        NEURA, [(f"{HOST}/product/4ne1-reservation/",
                 (FIXTURES / "reservation-page-links.html").read_bytes())], _robots(), {})
    assert mini in linked.selected                                    # reached by one-level links
    # Known gap, recorded rather than assumed away: the current seeds do not reach it.
    assert mini not in enumerate_targets(NEURA, _seeds(), _robots(), {}).selected


# ---------------------------------------------------------- refusal (offline) --


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


@pytest.mark.usefixtures("no_external_network")
def test_blocked_module_is_refused_even_for_an_approved_source(dsession):
    source = DiscoverySource(
        key=f"neura-test-{uuid.uuid4().hex[:8]}",
        name="NEURA Robotics (test)", source_class="MANUFACTURER",
        homepage_url=f"{HOST}/", allowed_path_prefixes=list(NEURA.allowed_path_prefixes),
        is_enabled=True, tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime(2026, 9, 26, tzinfo=UTC),
        eligibility_reviewed_by="fixture-reviewer",
    )
    dsession.add(source)
    dsession.flush()
    config = replace(NEURA, source_key=source.key)
    assert adapter_problems(config, source) == [
        f"ADAPTER_BLOCKED ({NEURA.blocked_reason})"]

    def canonical_counts():
        return (dsession.scalar(select(func.count()).select_from(Robot)),
                dsession.scalar(select(func.count()).select_from(Manufacturer)))

    before = canonical_counts()
    requests: list[str] = []
    transport = httpx.MockTransport(lambda r: requests.append(str(r.url)) or httpx.Response(500))
    with HttpFetcher(transport=transport) as fetcher, pytest.raises(AdapterRefused):
        run_adapter(dsession, source=source, config=config, operator="test", fetcher=fetcher)
    assert requests == []
    assert canonical_counts() == before
    for model in (CrawlRun, FetchedPage, DiscoveryCandidate):
        assert dsession.scalar(select(func.count()).select_from(model).where(
            model.source_id == source.id)) == 0
