"""Slice B adapter primitives — pure and offline (docs/16 §12 / §12.1 / §15).

robots Crawl-delay, the fetcher's per-host interval, bounded one-level
enumeration and deterministic extraction. No database, no network.
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.live_adapter import (
    ANNOUNCEMENT,
    PRODUCT,
    SourceAdapterConfig,
    enumerate_targets,
    extract_announcement,
    extract_product,
    extraction_digest,
    seed_links,
)
from app.services.discovery.robots import RobotsRules, parse
from app.services.discovery.sources import ADAPTERS, adapter_for
from app.services.discovery.sources.neura_robotics import CONFIG as NEURA

FIXTURES = Path(__file__).parent / "fixtures" / "discovery_adapter"
MAKER = "Example Robotics"

CONFIG = SourceAdapterConfig(
    key="example-robotics-fixture", version="1.0.0", source_key="example-robotics-fixture",
    source_class="MANUFACTURER", host="maker.example", manufacturer=MAKER,
    allowed_path_prefixes=("/products", "/news", "/sitemap.xml"),
    seed_urls=("https://maker.example/products", "https://maker.example/sitemap.xml"),
    product_path_pattern=re.compile(r"/products/[a-z0-9-]+"),
    announcement_path_pattern=re.compile(r"/news/\d{4}/[a-z0-9-]+"),
    property_map={"payload": ("payload_kg", "kg"), "height": ("height_m", "m")},
    quote_phrases=("price on request",),
    structural_review="fixture: synthetic pages",
)


def page(version: str, name: str, maker: str = MAKER) -> bytes:
    return (FIXTURES / version / name).read_text(encoding="utf-8").replace(
        "__MAKER__", maker).encode("utf-8")


def robots() -> RobotsRules:
    return parse((FIXTURES / "v1" / "robots.txt").read_text(encoding="utf-8"))


# ------------------------------------------------------------ crawl-delay --


def test_crawl_delay_is_read_from_the_applicable_group() -> None:
    rules = robots()
    assert rules.crawl_delay == 3.0
    assert not rules.allows("https://maker.example/products/ex-private")
    assert parse("User-agent: GPTBot\nCrawl-delay: 60\n").crawl_delay is None
    assert parse("User-agent: *\nCrawl-delay: soon\n").crawl_delay is None
    assert parse("User-agent: *\nCrawl-delay: -4\n").crawl_delay is None
    assert parse("User-agent: HumanoidOnlineMarketBot\nCrawl-delay: 7\n"
                 "User-agent: *\nCrawl-delay: 1\n").crawl_delay == 7.0


def test_crawl_delay_only_ever_slows_the_fetcher() -> None:
    with HttpFetcher(limits=FetchLimits()) as fetcher:
        assert fetcher.interval_for("maker.example") == 2.0
        assert fetcher.honour_crawl_delay("maker.example", 1.0) == 2.0   # floor wins
        assert fetcher.honour_crawl_delay("MAKER.example", 3.0) == 3.0   # longer delay wins
        assert fetcher.honour_crawl_delay("maker.example", 2.5) == 3.0   # never lowered
        assert fetcher.honour_crawl_delay("maker.example", None) == 3.0
        assert fetcher.interval_for("other.example") == 2.0              # per host


# ------------------------------------------------------------ enumeration --


def _seeds():
    return [("https://maker.example/products", page("v1", "listing.html")),
            ("https://maker.example/sitemap.xml", page("v1", "sitemap.xml"))]


def test_enumeration_is_one_bounded_level_from_the_seeds() -> None:
    result = enumerate_targets(CONFIG, _seeds(), robots(), {})
    assert result.selected == [
        "https://maker.example/news/2026/company-update",
        "https://maker.example/news/2026/ex-omega-unveiled",
        "https://maker.example/products/ex-alpha-7",
        "https://maker.example/products/ex-beta-2",
        "https://maker.example/products/ex-duo",
        "https://maker.example/products/ex-gamma",
        "https://maker.example/products/ex-series",
    ]
    assert result.deferred == []
    assert dict(result.excluded) == {
        "https://maker.example/about": "OUTSIDE_PATHS",
        "https://maker.example/products/category/humanoids": "NO_PATTERN",
        "https://maker.example/products/ex-private": "ROBOTS_DISALLOW",
        "https://maker.example/sitemap-products.xml": "OUTSIDE_PATHS",  # never followed
        "https://other.example/products/ex-alpha-7": "OFF_HOST",
    }


def test_enumeration_caps_unseen_first_and_defers_the_rest() -> None:
    capped = replace(CONFIG, target_cap=3)
    seen = {
        "https://maker.example/news/2026/company-update": datetime(2026, 9, 1, tzinfo=UTC),
        "https://maker.example/products/ex-alpha-7": datetime(2026, 8, 1, tzinfo=UTC),
    }
    result = enumerate_targets(capped, _seeds(), robots(), seen)
    assert result.selected == [
        "https://maker.example/news/2026/ex-omega-unveiled",
        "https://maker.example/products/ex-beta-2",
        "https://maker.example/products/ex-duo",
    ]
    assert result.deferred == [
        "https://maker.example/products/ex-gamma",
        "https://maker.example/products/ex-series",
        "https://maker.example/products/ex-alpha-7",           # seen longest ago
        "https://maker.example/news/2026/company-update",      # seen most recently
    ]


def test_sitemap_is_just_another_bounded_seed() -> None:
    assert seed_links(page("v1", "sitemap.xml")) == [
        "https://maker.example/products/ex-alpha-7/",
        "https://maker.example/news/2026/ex-omega-unveiled",
        "https://maker.example/news/2026/company-update?utm_campaign=rss",
        "https://maker.example/sitemap-products.xml",
    ]


def test_kind_of_uses_the_adapter_patterns() -> None:
    assert CONFIG.kind_of("https://maker.example/products/ex-1") == PRODUCT
    assert CONFIG.kind_of("https://maker.example/news/2026/launch") == ANNOUNCEMENT
    assert CONFIG.kind_of("https://maker.example/products/a/b") is None


# ------------------------------------------------------------- extraction --


def test_jsonld_product_extraction_is_evidence_bound() -> None:
    result = extract_product(CONFIG, page("v1", "ex-alpha-7.html"))
    assert (result.status, result.name, result.name_method) == ("EXTRACTED", "EX-Alpha 7", "JSONLD")
    assert [(c.field_key, c.claimed_value, c.unit) for c in result.claims] == [
        ("payload_kg", "20", "kg"), ("height_m", "1.70", "m")]
    assert any("unsupported property 'Battery chemistry'" in r for r in result.rejected)
    price, availability = result.signals
    assert (price.axis, price.price_type, price.price_amount, price.price_currency) == (
        "PRICE", "PUBLIC", Decimal("49000"), "USD")
    assert (availability.axis, availability.availability_value) == ("OBTAINABILITY", "AVAILABLE")
    assert [i.image_url for i in result.images] == [
        "https://maker.example/media/ex-alpha-7-front.jpg"]
    for item in (*result.claims, *result.signals):
        assert item.evidence.excerpt and len(item.evidence.excerpt) <= 1000
        assert item.evidence.locator.startswith("jsonld[0]")


def test_quote_phrase_is_quote_only_and_on_request_never_a_price() -> None:
    result = extract_product(CONFIG, page("v1", "ex-beta-2.html"))
    assert [(s.axis, s.price_type, s.availability_value, s.price_amount)
            for s in result.signals] == [
        ("PRICE", "QUOTE_ONLY", None, None), ("OBTAINABILITY", None, "ON_REQUEST", None)]
    assert "Price on request" in result.signals[0].evidence.excerpt
    assert result.signals[0].evidence.locator.startswith("offset:")


def test_unknown_stays_unknown() -> None:
    gamma = extract_product(CONFIG, page("v1", "ex-gamma.html"))
    assert (gamma.status, gamma.name, gamma.name_method) == ("EXTRACTED", "EX-Gamma", "SELECTOR")
    assert gamma.claims == () and gamma.signals == ()      # "Out of stock" text is not a signal
    series = extract_product(CONFIG, page("v1", "ex-series.html"))
    assert series.signals == ()                             # OutOfStock != NOT_AVAILABLE
    assert any("OutOfStock" in r for r in series.rejected)


def test_multi_product_page_and_foreign_brand_are_ambiguous() -> None:
    assert extract_product(CONFIG, page("v1", "ex-duo.html")).status == "AMBIGUOUS"
    foreign = extract_product(CONFIG, page("v1", "ex-alpha-7.html", maker="Other Corp"))
    assert foreign.status == "AMBIGUOUS" and foreign.name is None


def test_announcements_need_explicit_identity() -> None:
    omega = extract_announcement(CONFIG, page("v1", "news-omega.html"))
    assert omega.headline == "Example Robotics unveils EX-Omega"
    assert omega.product_name == "EX-Omega"
    assert omega.evidence.locator == "jsonld[0]/description"
    update = extract_announcement(CONFIG, page("v1", "news-update.html"))
    assert update.headline == "A new humanoid is coming"
    assert update.product_name is None                      # waits for a human
    assert "Stay tuned" in update.evidence.excerpt
    other = extract_announcement(replace(CONFIG, manufacturer="Other Corp"),
                                 page("v1", "news-omega.html"))
    assert other.product_name is None


@pytest.mark.parametrize("name", ["ex-alpha-7.html", "ex-beta-2.html", "ex-gamma.html",
                                  "ex-duo.html", "ex-series.html"])
def test_fixture_replay_is_byte_identical(name: str) -> None:
    body = page("v1", name)
    assert extraction_digest(extract_product(CONFIG, body)) == \
        extraction_digest(extract_product(CONFIG, bytes(body)))


def test_excerpt_over_limit_is_rejected_not_truncated() -> None:
    long_value = "x" * 1200
    body = (
        '<script type="application/ld+json">{"@type":"Product","name":"EX-1",'
        f'"additionalProperty":[{{"name":"Payload","value":"{long_value}","unitText":"kg"}}]}}'
        "</script>"
    ).encode()
    result = extract_product(CONFIG, body)
    assert result.claims == ()
    assert any("over 1000" in r for r in result.rejected)


# --------------------------------------------------------- source modules --


def test_neura_module_is_registered_but_not_runnable() -> None:
    assert adapter_for("neura-robotics-official") is NEURA
    assert set(ADAPTERS) == {"neura-robotics-official"}
    assert NEURA.manufacturer == "Neura Robotics"          # canonical catalogue name
    assert NEURA.host == "neura-robotics.com"
    assert NEURA.structural_review is None and NEURA.seed_urls == ()
    assert NEURA.target_cap == 50
    assert NEURA.kind_of("https://neura-robotics.com/anything") is None
