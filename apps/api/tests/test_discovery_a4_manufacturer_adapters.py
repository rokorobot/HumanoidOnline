"""A4 manufacturer adapters: Booster, AgiBot, Agility Robotics, Figure AI (identity-first), offline.

Fixtures are 2026-10-18 structural-review bodies, trimmed (tests/fixtures/<maker>/README.md). The
live tests serve them through httpx.MockTransport; the `no_external_network` guard fails the test on
any real socket.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import CandidateClaim, DiscoveryCandidate, DiscoverySource
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import source_registry as registry
from app.services.discovery.adapter_run import plan_adapter, run_adapter
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.live_adapter import extract_product
from app.services.discovery.sources import ADAPTERS
from app.services.discovery.urlref import normalize_url

pytestmark = pytest.mark.usefixtures("no_external_network")

FIX = Path(__file__).parent / "fixtures"
#: source key -> {seed URL: (fixture, expected candidate name)}, robots fixture or None (404).
SOURCES = {
    "booster-robotics-official": ({
        "https://www.booster.tech/booster-t2?target=en": ("booster/t2.html", "Booster T2"),
        "https://www.booster.tech/booster-k1?target=en": ("booster/k1.html", "Booster K1"),
    }, "booster/robots.txt", "https://www.booster.tech/"),
    "agibot-official": ({
        "https://www.agibot.com/products/A2": ("agibot/a2.html", "A2"),
        "https://www.agibot.com/products/X2": ("agibot/x2.html", "X2"),
    }, None, "https://www.agibot.com/"),
    "agility-robotics-official": ({
        "https://www.agilityrobotics.com/solutions/digit-5": ("agility/digit-5.html", "Digit 5"),
    }, "agility/robots.txt", "https://www.agilityrobotics.com/"),
    "figure-ai-official": ({
        "https://www.figure.ai/figure": ("figure/figure.html", "Figure 03"),
    }, "figure/robots.txt", "https://www.figure.ai/"),
}
PAGES = [(key, url, fx, name) for key, (pages, _, _) in SOURCES.items()
         for url, (fx, name) in pages.items()]
#: v0.2.0: verbatim specification claims per reviewed page (2026-10-18 fixtures).
CLAIMS = {"booster/t2.html": 64, "booster/k1.html": 81, "agibot/a2.html": 0,
          "agibot/x2.html": 70, "agility/digit-5.html": 4, "figure/figure.html": 6}


def raw(fixture: str) -> bytes:
    return (FIX / fixture).read_bytes()


# --------------------------------------------------------------------- pure extraction --


@pytest.mark.parametrize("key, url, fixture, name", PAGES)
def test_each_reviewed_page_names_its_model_and_states_nothing_commercial(key, url, fixture, name):
    from app.services.discovery.promotion import _APPROVED_FIELDS
    result = extract_product(ADAPTERS[key], raw(fixture), url)
    assert (result.status, result.name) == ("EXTRACTED", name)
    assert result.signals == ()                             # no price, availability or maturity
    assert len(result.claims) == CLAIMS[fixture] and result.rejected == ()
    prefix = key.split("-")[0] + ".spec["
    assert all(c.field_key.startswith(prefix) and c.unit is None for c in result.claims)
    assert not {c.field_key for c in result.claims} & set(_APPROVED_FIELDS)   # never promotable
    assert all(len(c.evidence.excerpt) <= 1000 and c.evidence.locator for c in result.claims)
    assert extract_product(ADAPTERS[key], raw(fixture), url) == result   # deterministic


def _claims(key, fixture, url, body=None):
    result = extract_product(ADAPTERS[key], body if body is not None else raw(fixture), url)
    return {c.field_key: c.claimed_value for c in result.claims}, result


def test_specification_values_are_verbatim_and_edition_keyed():
    t2, _ = _claims("booster-robotics-official", "booster/t2.html",
                    "https://www.booster.tech/booster-t2?target=en")
    assert t2["booster.spec[T2 Education]/Actuators/Max Peak Torque"] == "140 N·m"
    k1, _ = _claims("booster-robotics-official", "booster/k1.html",
                    "https://www.booster.tech/booster-k1?target=en")
    assert [k1[f"booster.spec[K1 {e}]/Computing & Sensors/GPU"]
            for e in ("Geek Edition", "Education", "Professional")] == [
        "48 TOPS (dense) AI computing power", "117 TOPS AI computing power",
        "200 TOPS AI computing power"]
    x2, _ = _claims("agibot-official", "agibot/x2.html", "https://www.agibot.com/products/X2")
    assert (x2["agibot.spec[X2]/Weight"], x2["agibot.spec[X2 Ultra]/Weight"]) == (
        "Approx.35kg", "Approx.39kg")
    assert x2["agibot.spec[X2]/Arm Reach"] == "558mm excluding end effector"   # words kept apart
    assert x2["agibot.spec[X2 Ultra]/Perception System/3D LiDAR"] == "Equipped"
    digit, _ = _claims("agility-robotics-official", "agility/digit-5.html",
                       "https://www.agilityrobotics.com/solutions/digit-5")
    assert digit == {"agility.spec[Digit 5]/Payload*": "23kg/50lbs",
                     "agility.spec[Digit 5]/Reach*": "2.2m/7.2ft",
                     "agility.spec[Digit 5]/Run to charge ratio*": "10:1",
                     "agility.spec[Digit 5]/Work/Shift*": "20HRS/24HRS"}
    fig, _ = _claims("figure-ai-official", "figure/figure.html", "https://www.figure.ai/figure")
    assert fig["figure.spec[Figure 03]/Height"] == "5'8\"" and \
        fig["figure.spec[Figure 03]/Weight"] == "61KG"


def test_booster_an_unreviewed_edition_label_is_never_attributed():
    body = raw("booster/t2.html").replace(b">Professional<", b">Ultra<")
    claims, result = _claims("booster-robotics-official", "booster/t2.html",
                             "https://www.booster.tech/booster-t2?target=en", body)
    assert result.status == "EXTRACTED"
    assert not any("Ultra" in k or "T2 Professional" in k for k in claims)
    # The lines under the unknown label are attributed to NO edition (not to the previous one):
    # Education keeps exactly its own reviewed lines.
    assert len(claims) == CLAIMS["booster/t2.html"] // 2


def test_booster_a_repeated_block_with_a_different_value_is_dropped():
    body = raw("booster/t2.html").replace(b"Max Peak Torque: 140 N", b"Max Peak Torque: 150 N", 1)
    claims, result = _claims("booster-robotics-official", "booster/t2.html",
                             "https://www.booster.tech/booster-t2?target=en", body)
    assert "booster.spec[T2 Education]/Actuators/Max Peak Torque" not in claims
    assert any("different values" in r for r in result.rejected)


def test_agibot_a_merged_cell_rejects_its_row_whole():
    body = raw("agibot/x2.html").replace(
        b'<td valign="top" width="598">25</td>',
        b'<td valign="top" colspan="2" width="598">25</td>', 1)
    claims, result = _claims("agibot-official", "agibot/x2.html",
                             "https://www.agibot.com/products/X2", body)
    assert not any("Total Degrees of Freedom" in k for k in claims)
    assert any("merged cell" in r for r in result.rejected)


@pytest.mark.parametrize("key", sorted(SOURCES))
def test_each_adapter_is_a_fixed_reviewed_seed_set_on_one_host(key):
    config, (pages, _, home) = ADAPTERS[key], SOURCES[key]
    assert config.source_key == key and config.version == "0.2.0"
    assert set(config.seed_urls) == set(pages) and config.target_cap == 1
    assert config.structural_review and config.blocked_reason is None
    assert f"https://{config.host}/" == home
    for seed in config.seed_urls:
        assert normalize_url(seed) == seed and config.kind_of(seed) == "PRODUCT"


@pytest.mark.parametrize("key, url", [
    ("agibot-official", "https://www.agibot.com/products/G2"),          # wheeled: not in scope
    ("agibot-official", "https://store.agibot.com/products/A2"),
    ("agility-robotics-official", "https://www.agilityrobotics.com/solutions/digit/spec-sheet"),
    ("figure-ai-official", "https://www.figure.ai/news/ramping-figure-03-production"),
    ("booster-robotics-official", "https://www.booster.tech/store?key=t2&target=en"),
])
def test_unreviewed_pages_and_other_hosts_are_not_products(key, url):
    assert ADAPTERS[key].kind_of(url) is None or urlsplit(url).hostname != ADAPTERS[key].host


def test_agibot_navigation_menus_never_name_the_product():
    # The site menu lists "AGIBOT X1", "AGIBOT A3"... on every page; only the page's own
    # heading counts. Removing that heading leaves no identity at all.
    body = raw("agibot/a2.html").replace(b'<h2 class="wow fadeInUp">AGIBOT A2</h2>', b"")
    result = extract_product(ADAPTERS["agibot-official"], body, "https://www.agibot.com/products/A2")
    assert result.status == "NOTHING_FOUND" and result.name is None


def test_agibot_a_heading_for_another_model_is_ambiguous():
    body = raw("agibot/a2.html").replace(b"AGIBOT A2</h2>", b"AGIBOT A3</h2>", 1)
    result = extract_product(ADAPTERS["agibot-official"], body, "https://www.agibot.com/products/A2")
    assert result.status == "AMBIGUOUS"


def test_agibot_canonical_to_the_homepage_is_ignored():
    assert b'rel="canonical" href="https://www.agibot.com/"' in raw("agibot/a2.html")
    result = extract_product(ADAPTERS["agibot-official"], raw("agibot/a2.html"),
                             "https://www.agibot.com/products/A2")
    assert result.status == "EXTRACTED"


def test_agility_title_slug_and_h1_must_agree():
    url = "https://www.agilityrobotics.com/solutions/digit-5"
    body = raw("agility/digit-5.html").replace(b"<title>Digit 5 | Agility",
                                               b"<title>Digit 6 | Agility")
    assert extract_product(ADAPTERS["agility-robotics-official"], body, url).status == "AMBIGUOUS"


def test_figure_title_and_h1_must_agree():
    body = raw("figure/figure.html").replace(b'__heading">FIGURE 03</h1>',
                                             b'__heading">FIGURE 04</h1>', 1)
    result = extract_product(ADAPTERS["figure-ai-official"], body, "https://www.figure.ai/figure")
    assert result.status == "AMBIGUOUS"


def test_figure_robots_disallow_is_outside_the_adapter_scope():
    from app.services.discovery.robots import parse
    rules = parse(raw("figure/robots.txt").decode("utf-8"))
    assert not rules.allows("https://www.figure.ai/info")
    assert rules.allows("https://www.figure.ai/figure")


# ------------------------------------------------------------------- eligibility + live --


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


def _source(session, key, *, authorize=True, enable=True):
    config, (_, _, home) = ADAPTERS[key], SOURCES[key]
    assert session.scalar(select(DiscoverySource).where(DiscoverySource.key == key)) is None
    registry.register_source(session, key=key, name=key, source_class="MANUFACTURER",
                             homepage_url=home, registered_by="test")
    paths = list(config.allowed_path_prefixes)
    registry.review_source(session, key, reviewed_by="test", tos_decision="UNKNOWN",
                           robots_decision="ALLOWED", path_prefixes=paths)
    if authorize:
        registry.authorize_owner(session, key, by="test", reason="A4 fixture", path_prefixes=paths)
    if enable:
        registry.enable_source(session, key, by="test")
    return registry.get_source(session, key)


class Site:
    def __init__(self, key: str) -> None:
        pages, robots, _ = SOURCES[key]
        self.host = ADAPTERS[key].host
        self.robots = raw(robots) if robots else None
        self.pages = {urlsplit(u).path: fx for u, (fx, _) in pages.items()}
        self.status: dict[str, int] = {}
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == self.host
        path = request.url.path
        self.requests.append(path)
        if path == "/robots.txt":
            return httpx.Response(200, content=self.robots) if self.robots is not None \
                else httpx.Response(404)
        if path in self.status:
            return httpx.Response(self.status[path])
        if path not in self.pages:
            return httpx.Response(404)
        body = raw(self.pages[path])
        etag = '"' + hashlib.sha256(body).hexdigest()[:12] + '"'
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers={"etag": etag})
        return httpx.Response(200, content=body, headers={"content-type": "text/html",
                                                          "etag": etag})


class Clock:
    t = 0.0

    def now(self):
        return datetime(2026, 10, 19, 6, tzinfo=UTC) + timedelta(seconds=self.t)

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def _run(session, source, key, site, clock, tmp_path):
    fetcher = HttpFetcher(limits=FetchLimits(page_cap=20), transport=httpx.MockTransport(site),
                          monotonic=clock.monotonic, sleep=clock.sleep)
    with fetcher:
        return run_adapter(session, source=source, config=ADAPTERS[key], operator="test",
                           fetcher=fetcher, cache_dir=tmp_path / "cache", now=clock.now)


def _canonical(session):
    return tuple(session.scalar(select(func.count()).select_from(m))
                 for m in (Robot, Manufacturer, EvidenceSource))


@pytest.mark.parametrize("key", sorted(SOURCES))
def test_runnable_only_when_reviewed_owner_authorized_and_enabled(dsession, key):
    source = _source(dsession, key, authorize=False, enable=False)
    assert "SOURCE_DISABLED" in plan_adapter(ADAPTERS[key], source)
    registry.authorize_owner(dsession, key, by="test", reason="A4 fixture",
                             path_prefixes=list(ADAPTERS[key].allowed_path_prefixes))
    registry.enable_source(dsession, key, by="test")
    assert plan_adapter(ADAPTERS[key], source) == []
    assert source.tos_status == "UNKNOWN"


@pytest.mark.parametrize("key", sorted(SOURCES))
def test_a_run_names_every_seed_model_and_writes_nothing_canonical(dsession, tmp_path, key):
    source, site, clock = _source(dsession, key), Site(key), Clock()
    before = _canonical(dsession)
    run = _run(dsession, source, key, site, clock, tmp_path)
    assert run.status == "COMPLETED", run.run_manifest
    assert site.requests[0] == "/robots.txt"
    names = set(dsession.scalars(select(DiscoveryCandidate.candidate_name).where(
        DiscoveryCandidate.source_id == source.id)))
    assert names == {name for _, (_, name) in SOURCES[key][0].items()}
    assert dsession.scalar(select(func.count()).select_from(CandidateClaim).join(
        DiscoveryCandidate).where(DiscoveryCandidate.source_id == source.id)) == sum(
        CLAIMS[fx] for fx, _ in SOURCES[key][0].values())
    assert _canonical(dsession) == before
    second = _run(dsession, source, key, site, clock, tmp_path)        # unchanged pages
    assert second.status == "COMPLETED"
    assert len(set(dsession.scalars(select(DiscoveryCandidate.id).where(
        DiscoveryCandidate.source_id == source.id)))) == len(names)


def test_a_block_halts_and_is_not_retried(dsession, tmp_path):
    key = "figure-ai-official"
    source, site = _source(dsession, key), Site(key)
    site.status["/figure"] = 403
    run = _run(dsession, source, key, site, Clock(), tmp_path)
    assert run.status == "HALTED_BY_POLICY" and site.requests.count("/figure") == 1
