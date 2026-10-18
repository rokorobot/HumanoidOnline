"""Unitree Robotics adapter (www.unitree.com H2 / R1 / G1), offline.

Fixtures are the 2026-10-18 structural-review bodies, trimmed (tests/fixtures/unitree/README.md).
The live tests serve them through httpx.MockTransport for `www.unitree.com`; the
`no_external_network` guard fails the test on any real socket.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.acquisition import CrawlRun, FetchedPage
from app.models.discovery import CandidateClaim, DiscoveryCandidate, DiscoverySource
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import source_registry as registry
from app.services.discovery.adapter_run import plan_adapter, run_adapter
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.promotion import _APPROVED_FIELDS
from app.services.discovery.robots import parse
from app.services.discovery.sources import ADAPTERS
from app.services.discovery.sources import unitree_robotics as u

pytestmark = pytest.mark.usefixtures("no_external_network")

FIX = Path(__file__).parent / "fixtures" / "unitree"
PAGES = {"/H2/": "h2.html", "/R1/": "r1.html", "/g1/": "g1.html"}
URL = {"h2": "https://www.unitree.com/H2/", "r1": "https://www.unitree.com/R1/",
       "g1": "https://www.unitree.com/g1/"}


def body(name: str) -> bytes:
    return (FIX / f"{name}.html").read_bytes()


def extract(name: str, raw: bytes | None = None, url: str | None = None):
    return u.extract_unitree_product(u.CONFIG, raw if raw is not None else body(name),
                                     url or URL[name])


def claims(result) -> dict[str, str]:
    return {c.field_key: c.claimed_value for c in result.claims}


# --------------------------------------------------------------------- pure extraction --


@pytest.mark.parametrize("page, name, editions", [
    ("h2", "H2", "H2; H2 EDU"), ("r1", "R1", "R1 AIR; R1; R1 EDU"), ("g1", "G1", "G1; G1 EDU")])
def test_each_reviewed_page_yields_its_model_identity_and_editions(page, name, editions):
    result = extract(page)
    assert (result.status, result.name, result.name_method) == ("EXTRACTED", name, "SELECTOR")
    assert claims(result)["unitree.editions"] == editions
    assert result.rejected == ()
    assert "not resolved to catalogue robots" in " ".join(result.notes)


def test_extraction_is_deterministic():
    for page in URL:
        assert extract(page) == extract(page)


def test_prices_are_verbatim_per_edition_with_the_stated_terms():
    h2, r1, g1 = claims(extract("h2")), claims(extract("r1")), claims(extract("g1"))
    assert h2["unitree.price_terms"] == "Price（Tax and Shipping cost excluded）"
    assert (h2["unitree.price[H2]"], h2["unitree.price[H2 EDU]"]) == ("$29,900", "Contact Sales")
    assert (r1["unitree.price[R1 AIR]"], r1["unitree.price[R1]"], r1["unitree.price[R1 EDU]"]) \
        == ("$4,900", "$5,900", "Contact Sales")
    assert g1["unitree.price_terms"] == "Price(Tax and Shipping cost excluded)"
    assert (g1["unitree.price[G1]"], g1["unitree.price[G1 EDU]"]) == ("US $13.5K", "Contact sales")
    assert r1["unitree.price_from"] == "Price from $4,900"
    assert g1["unitree.price_from"] == "Price from $13.5K"
    assert "unitree.price_from" not in h2                    # the H2 page states no "from" price


def test_price_signals_only_for_the_page_model_and_fail_closed_on_money():
    def sig(page):
        return sorted((s.price_type, s.price_amount, s.price_currency, s.evidence.locator)
                      for s in extract(page).signals)
    # A bare "$" states no currency, so the amount and currency stay UNKNOWN; the excerpt keeps it.
    assert sig("h2") == [("PUBLIC", None, None, "price-table/row[H2]")]
    assert sig("r1") == [("FROM", None, None, "hero/price-from"),
                         ("PUBLIC", None, None, "price-table/row[R1]")]
    # "US $" states the currency; the "K" suffix is never expanded into an amount.
    assert sig("g1") == [("FROM", None, None, "hero/price-from"),
                         ("PUBLIC", None, "USD", "price-table/row[G1]")]
    for page in URL:
        for s in extract(page).signals:
            assert s.axis == "PRICE" and s.region_code is None   # no region, VAT or EU inferred
            assert "EDU" not in s.evidence.locator               # an EDU row never prices a model
            if s.price_type == "PUBLIC":
                assert "Tax and Shipping cost excluded" in s.evidence.excerpt


def test_an_exact_stated_usd_amount_is_the_only_amount_ever_parsed():
    raw = body("h2").replace(b"$29,900", b"US $29,900")
    [signal] = extract("h2", raw).signals
    assert (signal.price_amount, signal.price_currency) == (Decimal("29900"), "USD")


def test_contact_sales_on_the_model_row_is_quote_only():
    raw = body("h2").replace(b"$29,900", b"Contact Sales")
    [signal] = extract("h2", raw).signals
    assert (signal.price_type, signal.price_amount) == ("QUOTE_ONLY", None)


def test_specifications_are_verbatim_text_per_edition_and_never_promotable():
    r1 = claims(extract("r1"))
    key = "unitree.spec[{}]/Mechanical Dimensions/Degree of Freedom(Total Joints)"
    assert [r1[key.format(e)] for e in ("R1 AIR", "R1", "R1 EDU")] == ["20", "26", "26-40"]
    assert r1["unitree.spec[R1 AIR]/Mechanical Dimensions/Weight (With Battery)"] == "About 27kg"
    for page in URL:
        result = extract(page)
        assert all(c.unit is None for c in result.claims)
        assert not {c.field_key for c in result.claims} & set(_APPROVED_FIELDS)
        assert all(c.field_key.startswith("unitree.") for c in result.claims)
        assert all(len(c.evidence.excerpt) <= 1000 and c.evidence.locator for c in result.claims)


# ------------------------------------------------------------ failure modes (fail closed) --


def test_a_title_that_does_not_name_the_slug_model_is_ambiguous():
    raw = body("h2").replace(b"<title>Unitree H2 Destiny", b"<title>Unitree H1 Destiny")
    result = extract("h2", raw)
    assert result.status == "AMBIGUOUS" and result.name is None and result.claims == ()


def test_the_g1_seo_title_is_tokenized_on_underscores():
    assert "G1_Humanoid" in body("g1").decode("utf-8")
    assert extract("g1").name == "G1"


def test_a_page_without_an_edition_list_names_nothing():
    raw = re.sub(rb'<ul class="versions".*?</ul>', b"", body("h2"), flags=re.S)
    result = extract("h2", raw)
    assert result.status == "NOTHING_FOUND" and result.signals == () and result.claims == ()


def test_edition_list_and_grid_model_row_must_agree():
    raw = body("h2").replace(b'<div class="params">', (
        b'<div class="params"><div class="part"><div class="category">X</div><ul class="value">'
        b'<li><div class="valPart"><p>Model</p></div><div class="valPart"><p>H2</p></div>'
        b'<div class="valPart"><p>H2 PRO</p></div></li></ul></div>'), 1)
    assert extract("h2", raw).status == "AMBIGUOUS"


def test_missing_price_table_keeps_identity_and_specs_but_states_no_model_price():
    raw = re.sub(rb"<li><div class=\"valPart\"><div><p>Price\(Tax.*?</li>", b"", body("g1"),
                 count=1, flags=re.S)
    result = extract("g1", raw)
    assert result.status == "EXTRACTED" and result.name == "G1"
    assert "unitree.price[G1]" not in claims(result)
    assert [s.price_type for s in result.signals] == ["FROM"]     # only the hero line remains
    assert any(k.startswith("unitree.spec[G1]") for k in claims(result))


def test_a_misaligned_grid_row_is_rejected_whole_never_partially_attributed():
    # Drop one whole value cell from the Weight row.
    cell = rb'(<p>Weight \(With Battery\)</p></div></div>)<div class="valPart">.*?</div></div>'
    raw = re.sub(cell, rb"\1", body("h2"), count=1, flags=re.S)
    result = extract("h2", raw)
    assert any("Weight (With Battery)" in r and "rejected" in r for r in result.rejected)
    assert not any("Weight (With Battery)" in k for k in claims(result))
    assert result.status == "EXTRACTED"                      # the rest of the page still reads


@pytest.mark.parametrize("url", ["https://www.unitree.com/H2plus/", "https://www.unitree.com/",
                                 "https://unistore.unitree.com/H2/", "https://www.unitree.com/cn/h1"])
def test_only_the_three_reviewed_pages_are_read(url):
    assert extract("h2", url=url).status == "NOTHING_FOUND"


# ---------------------------------------------------------------- config and eligibility --


def test_the_adapter_is_a_fixed_reviewed_set_of_three_pages_on_one_host():
    assert ADAPTERS["unitree-robotics-official"] is u.CONFIG
    assert u.CONFIG.host == "www.unitree.com" and u.CONFIG.manufacturer == "Unitree Robotics"
    assert u.CONFIG.seed_urls == ("https://www.unitree.com/H2", "https://www.unitree.com/R1",
                                  "https://www.unitree.com/g1")
    assert u.CONFIG.target_cap == 1 and u.CONFIG.blocked_reason is None
    assert u.CONFIG.announcement_path_pattern is None and u.CONFIG.heading_identity is False
    for path, kind in (("/H2", "PRODUCT"), ("/g1", "PRODUCT"), ("/H2plus", None),
                       ("/cn/g1", None), ("/sitemap.xml", None)):
        assert u.CONFIG.kind_of(f"https://www.unitree.com{path}") == kind
    assert u.STRUCTURAL_FINDINGS["robots_status"] == "ALLOWED"
    assert "UNITREE_STRUCTURAL_REVIEW_2026-10-18" in u.CONFIG.structural_review


def test_robots_with_a_utf8_bom_is_parsed_and_its_rules_apply():
    served = (FIX / "robots.txt").read_text(encoding="utf-8")
    assert served.startswith("﻿")
    assert parse(served).allows("https://www.unitree.com/H2")
    # The fail-open defect this fixes: a BOM used to hide the group, dropping its Disallow.
    assert not parse("﻿User-agent:*\nDisallow: /H2\n").allows("https://www.unitree.com/H2")


@pytest.fixture
def dsession(database_url):
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


def _source(session, *, authorize=True, enable=True, paths=("/H2", "/R1", "/g1")):
    key = "unitree-robotics-official"
    assert session.scalar(select(DiscoverySource).where(DiscoverySource.key == key)) is None
    registry.register_source(session, key=key, name="Unitree Robotics",
                             source_class="MANUFACTURER", homepage_url="https://www.unitree.com/",
                             registered_by="test")
    registry.review_source(session, key, reviewed_by="test", tos_decision="UNKNOWN",
                           robots_decision="ALLOWED", path_prefixes=list(paths))
    if authorize:
        registry.authorize_owner(session, key, by="test", reason="A4 fixture",
                                 path_prefixes=list(paths))
    if enable:
        registry.enable_source(session, key, by="test")
    return registry.get_source(session, key)


def test_the_adapter_is_runnable_only_after_review_owner_authorization_and_enable(dsession):
    source = _source(dsession, authorize=False, enable=False)
    assert "SOURCE_DISABLED" in plan_adapter(u.CONFIG, source)
    registry.authorize_owner(dsession, source.key, by="test", reason="A4 fixture",
                             path_prefixes=["/H2", "/R1", "/g1"])
    registry.enable_source(dsession, source.key, by="test")
    assert plan_adapter(u.CONFIG, source) == []
    assert source.tos_status == "UNKNOWN" and source.access_basis == "OWNER_AUTHORIZED"


def test_a_narrower_owner_scope_refuses_the_adapter_before_any_request(dsession):
    source = _source(dsession, paths=("/H2",))
    problems = plan_adapter(u.CONFIG, source)
    assert "PATH_PREFIX_NOT_APPROVED (/R1)" in problems
    assert "PATH_PREFIX_NOT_APPROVED (/g1)" in problems


# ------------------------------------------------------------------- live run (offline) --


class Site:
    """www.unitree.com as reviewed: robots with a BOM, slash-less 302s, ETags and 304s."""

    def __init__(self) -> None:
        self.robots = (FIX / "robots.txt").read_bytes()
        self.status: dict[str, int] = {}
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.unitree.com"
        path = request.url.path
        self.requests.append(path)
        if path == "/robots.txt":
            return httpx.Response(200, content=self.robots, headers={"content-type": "text/plain"})
        if path in self.status:
            return httpx.Response(self.status[path])
        if path + "/" in PAGES:
            return httpx.Response(302, headers={"location": path + "/"})
        if path not in PAGES:
            return httpx.Response(404)
        raw = (FIX / PAGES[path]).read_bytes()
        etag = '"' + hashlib.sha256(raw).hexdigest()[:12] + '"'
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers={"etag": etag})
        return httpx.Response(200, content=raw, headers={"content-type": "text/html",
                                                         "etag": etag})


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> datetime:
        return datetime(2026, 10, 19, 6, tzinfo=UTC) + timedelta(seconds=self.t)

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _run(session, source, site, clock, tmp_path):
    fetcher = HttpFetcher(limits=FetchLimits(page_cap=20), transport=httpx.MockTransport(site),
                          monotonic=clock.monotonic, sleep=clock.sleep)
    with fetcher:
        return run_adapter(session, source=source, config=u.CONFIG, operator="test",
                           fetcher=fetcher, cache_dir=tmp_path / "cache", now=clock.now)


def _canonical(session) -> tuple:
    return tuple(session.scalar(select(func.count()).select_from(m))
                 for m in (Robot, Manufacturer, EvidenceSource))


def _candidates(session, source) -> dict[str, DiscoveryCandidate]:
    return {c.candidate_name: c for c in session.scalars(
        select(DiscoveryCandidate).where(DiscoveryCandidate.source_id == source.id))}


def _claim_count(session, source) -> int:
    return session.scalar(select(func.count()).select_from(CandidateClaim).join(
        DiscoveryCandidate).where(DiscoveryCandidate.source_id == source.id))


def test_a_run_reads_the_three_pages_through_the_redirect_and_writes_nothing_canonical(
        dsession, tmp_path):
    source, site, clock = _source(dsession), Site(), Clock()
    before = _canonical(dsession)
    run = _run(dsession, source, site, clock, tmp_path)
    assert run.status == "COMPLETED", run.run_manifest
    assert site.requests[0] == "/robots.txt"
    assert {"/H2", "/H2/", "/R1", "/R1/", "/g1", "/g1/"} <= set(site.requests)
    assert not any(p.startswith(("/cn", "/booking", "/download")) for p in site.requests)
    found = _candidates(dsession, source)
    assert set(found) == {"H2", "R1", "G1"}
    assert all(c.candidate_manufacturer == "Unitree Robotics" for c in found.values())
    assert _claim_count(dsession, source) == 70 + 99 + 69
    assert _canonical(dsession) == before                       # observation is not publication
    assert clock.t >= 3                                          # paced, never a burst


def test_an_unchanged_second_run_is_conditional_and_duplicates_nothing(dsession, tmp_path):
    source, site, clock = _source(dsession), Site(), Clock()
    _run(dsession, source, site, clock, tmp_path)
    claims_once = _claim_count(dsession, source)
    candidates_once = set(_candidates(dsession, source))
    clock.t += 48 * 3600
    second = _run(dsession, source, site, clock, tmp_path)
    assert second.status == "COMPLETED"
    assert _claim_count(dsession, source) == claims_once
    assert set(_candidates(dsession, source)) == candidates_once
    statuses = {p.http_status for p in dsession.scalars(
        select(FetchedPage).where(FetchedPage.crawl_run_id == second.id))}
    assert 304 in statuses


def test_a_block_halts_the_run_and_is_not_retried(dsession, tmp_path):
    source, site, clock = _source(dsession), Site(), Clock()
    site.status["/R1"] = 403
    run = _run(dsession, source, site, clock, tmp_path)
    assert run.status == "HALTED_BY_POLICY"
    assert site.requests.count("/R1") == 1                      # no retry, no other identity


def test_a_robots_disallow_behind_the_bom_is_honoured(dsession, tmp_path):
    source, site, clock = _source(dsession), Site(), Clock()
    site.robots = "﻿User-agent:*\nDisallow: /g1\n".encode()
    _run(dsession, source, site, clock, tmp_path)
    assert "/g1" not in site.requests and "/g1/" not in site.requests
    assert "G1" not in _candidates(dsession, source)


def test_the_run_record_names_the_adapter_and_its_review(dsession, tmp_path):
    source = _source(dsession)
    run = _run(dsession, source, Site(), Clock(), tmp_path)
    assert (run.adapter_key, run.adapter_version) == ("unitree-robotics-official", "0.1.0")
    assert "UNITREE_STRUCTURAL_REVIEW" in run.run_manifest["adapter_structural_review"]
    assert isinstance(dsession.get(CrawlRun, run.id), CrawlRun)
