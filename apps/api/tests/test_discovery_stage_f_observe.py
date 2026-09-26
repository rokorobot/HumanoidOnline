"""Stage F1 — scheduled observation cycles, offline against PostgreSQL.

Every site here is SYNTHETIC and served through httpx.MockTransport (the
`no_external_network` guard fails the test on any socket). The session joins the
test transaction in `create_savepoint` mode, so `session.commit()` (the cycle's
checkpoint) is durable for the test and `session.rollback()` discards only the
uncommitted remainder, as a crash would. Everything is rolled back at the end.

The product pages use the real NEURA redirect shape: the linked URL has no
trailing slash and answers 301 to the trailing-slash URL that serves the page.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cli import discovery as cli
from app.db import session as db_session
from app.db.session import engine
from app.models.acquisition import CrawlRun, ExtractionResult
from app.models.discovery import CandidateClaim, DiscoveryCandidate, DiscoverySource
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import DiscoveryError, review
from app.services.discovery import source_registry as registry
from app.services.discovery.acquisition import learned_canonical
from app.services.discovery.fetcher import HttpFetcher
from app.services.discovery.live_adapter import SourceAdapterConfig
from app.services.discovery.observe import (
    EXIT_ATTENTION,
    EXIT_FAILED,
    fetch_limits_for,
    observe,
)

pytestmark = pytest.mark.usefixtures("no_external_network")

ALLOW_ALL = "User-agent: *\nAllow: /\n"


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


def listing(*paths: str) -> str:
    items = "".join(f'<li><a href="{p}">{p}</a></li>' for p in paths)
    return f"<html><body><h1>Products</h1><ul>{items}</ul></body></html>"


def product(name: str, extra: str = "") -> str:
    return f"<html><head><title>{name}</title></head><body><h1>{name}</h1>{extra}</body></html>"


class Site:
    """One synthetic manufacturer site with ETags, 304s and NEURA-shaped redirects."""

    def __init__(self, host: str) -> None:
        self.host = host
        self.robots = ALLOW_ALL
        self.pages = {"/products": listing("/products/a", "/products/b"),
                      "/products/a/": product("X-A"), "/products/b": product("X-B")}
        self.redirects = {"/products/a": "/products/a/"}  # the real NEURA shape
        self.status: dict[str, int] = {}
        self.boom: set[str] = set()
        self.requests: list[tuple[str, str | None]] = []  # (path, If-None-Match)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, inm = request.url.path, request.headers.get("if-none-match")
        self.requests.append((path, inm))
        if path == "/robots.txt":
            return httpx.Response(200, text=self.robots, headers={"content-type": "text/plain"})
        if path in self.boom:
            raise RuntimeError("site exploded")
        if path in self.status:
            return httpx.Response(self.status[path])
        if path in self.redirects:
            return httpx.Response(301, headers={"location": self.redirects[path]})
        body = self.pages.get(path)
        if body is None:
            return httpx.Response(404)
        etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:12] + '"'
        if inm == etag:
            return httpx.Response(304, headers={"etag": etag})
        return httpx.Response(200, text=body,
                              headers={"content-type": "text/html; charset=utf-8", "etag": etag})

    def paths(self, start: int = 0) -> list[str]:
        return [p for p, _ in self.requests[start:] if p != "/robots.txt"]


class Harness:
    """Sources + adapters + sites + a clock; runs cycles through `observe`."""

    def __init__(self, session: Session, tmp_path) -> None:
        self.session = session
        self.cache_dir = tmp_path / "cache"
        self.sites: dict[str, Site] = {}
        self.adapters: dict[str, SourceAdapterConfig] = {}
        self.keys: list[str] = []
        self.t = 0.0
        self.base = datetime(2026, 9, 27, 6, tzinfo=UTC)
        self.killed: set[str] = set()

    # clock -------------------------------------------------------------------
    def now(self) -> datetime:
        return self.base + timedelta(seconds=self.t)

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds

    def advance(self, hours: float) -> None:
        self.t += hours * 3600

    # world -------------------------------------------------------------------
    def source(self, label: str, *, cadence: int | None = 24, enabled: bool = True,
               adapter: bool = True, last_crawled: datetime | None = None) -> Site:
        tag = uuid.uuid4().hex[:8]
        host = f"m{tag}.example"
        source = DiscoverySource(
            key=f"stagef-{label}-{tag}", name=f"Maker {label}", source_class="MANUFACTURER",
            homepage_url=f"https://{host}/", allowed_path_prefixes=["/products"],
            is_enabled=enabled, tos_status="ALLOWED", robots_status="ALLOWED",
            eligibility_reviewed_at=datetime(2026, 9, 1, tzinfo=UTC),
            eligibility_reviewed_by="owner", last_crawled_at=last_crawled,
            observation_interval_hours=cadence,
            observation_cadence_set_by="robert" if cadence else None,
            observation_cadence_set_at=datetime(2026, 9, 26, tzinfo=UTC) if cadence else None,
        )
        self.session.add(source)
        self.session.flush()
        if adapter:
            self.adapters[source.key] = SourceAdapterConfig(
                key=f"fixture-{tag}", version="1", source_key=source.key,
                source_class="MANUFACTURER", host=host, manufacturer=f"Maker{tag} Robotics",
                allowed_path_prefixes=("/products",), seed_urls=(f"https://{host}/products",),
                product_path_pattern=re.compile(r"/products/[a-z0-9-]+"),
                structural_review="fixture: synthetic pages",
            )
        site = Site(host)
        site.key = source.key
        self.sites[host] = site
        self.keys.append(source.key)
        return site

    def _route(self, request: httpx.Request) -> httpx.Response:
        return self.sites[request.url.host](request)

    def _fetcher(self, source, config, parent, kill) -> HttpFetcher:
        return HttpFetcher(limits=fetch_limits_for(config, parent),
                           transport=httpx.MockTransport(self._route),
                           monotonic=self.monotonic, sleep=self.sleep, kill_switch=kill)

    def cycle(self, *, plan_only: bool = False):
        self.session.commit()
        result = observe(
            self.session, self.adapters, plan_only=plan_only, cache_dir=self.cache_dir,
            now=self.now, fetcher_for=self._fetcher,
            kill_switch_for=lambda key: (lambda: key in self.killed),
            checkpoint=None if plan_only else self.session.commit)
        ours = [s for s in result.sources if s.key in self.keys]
        return result, {s.key: s for s in ours}, [s.key for s in ours]

    def candidates(self, site: Site) -> list[DiscoveryCandidate]:
        return list(self.session.scalars(
            select(DiscoveryCandidate).join(DiscoverySource)
            .where(DiscoverySource.key == site.key).order_by(DiscoveryCandidate.external_ref)))


@pytest.fixture
def h(dsession, tmp_path) -> Harness:
    return Harness(dsession, tmp_path)


def canonical(session) -> tuple:
    return tuple(session.scalar(select(func.count()).select_from(m))
                 for m in (Robot, Manufacturer, EvidenceSource))


def count(session, model, **where) -> int:
    q = select(func.count()).select_from(model)
    for k, v in where.items():
        q = q.where(getattr(model, k) == v)
    return session.scalar(q)


# ------------------------------------------------------------- orchestration --


def test_cycle_runs_due_sources_and_skips_the_rest_with_reasons_in_key_order(h):
    due = h.source("a")
    disabled = h.source("b", enabled=False)
    unscheduled = h.source("c", cadence=None)
    not_due = h.source("d", last_crawled=h.now() - timedelta(hours=1))
    no_adapter = h.source("e", adapter=False)
    before = canonical(h.session)
    result, by_key, order = h.cycle()
    assert order == sorted(order)
    status = {k: s.status for k, s in by_key.items()}
    assert status == {due.key: "COMPLETED", disabled.key: "DISABLED",
                      unscheduled.key: "NOT_SCHEDULED", not_due.key: "NOT_DUE",
                      no_adapter.key: "NO_ADAPTER"}
    for site in (disabled, unscheduled, not_due, no_adapter):
        assert site.requests == []                       # never contacted
    assert due.requests[0][0] == "/robots.txt"          # robots gate on every run
    run = h.session.get(CrawlRun, by_key[due.key].run_id)
    assert run.trigger == "SCHEDULED" and run.operator.endswith("(cadence set by robert)")
    counts = by_key[due.key].counts
    assert (counts["first_observation"], counts["new_entity"]) == (3, 2)
    assert counts["review_items_this_cycle"] == 2        # two new candidates await a trace
    assert result.exit_code == EXIT_ATTENTION
    assert canonical(h.session) == before                # zero canonical writes
    assert "NO_ADAPTER" in "\n".join(result.lines())


def test_plan_mode_requests_nothing_and_writes_nothing(h):
    site = h.source("a")
    runs = count(h.session, CrawlRun)
    result, by_key, _ = h.cycle(plan_only=True)
    assert by_key[site.key].status == "WOULD_RUN" and result.plan_only
    assert site.requests == [] and count(h.session, CrawlRun) == runs


def test_kill_switch_skips_the_source(h):
    site = h.source("a")
    h.killed.add(site.key)
    _, by_key, _ = h.cycle()
    assert by_key[site.key].status == "KILL_SWITCH" and site.requests == []


def test_one_failing_source_does_not_stop_the_others(h):
    broken = h.source("a")
    healthy = h.source("b")
    broken.boom.add("/products/b")
    result, by_key, _ = h.cycle()
    assert by_key[broken.key].status == "FAILED"
    assert h.session.get(CrawlRun, by_key[broken.key].run_id).status == "FAILED"
    assert by_key[healthy.key].status == "COMPLETED"
    assert len(h.candidates(healthy)) == 2
    assert result.exit_code == EXIT_FAILED


def test_failed_run_is_resumed_once_and_repeated_failure_is_surfaced(h):
    site = h.source("a")
    site.boom.add("/products/b")
    _, first, _ = h.cycle()
    failed = h.session.get(CrawlRun, first[site.key].run_id)
    assert failed.status == "FAILED"
    # Next cycle: one automated resume, which fails again (the site is still broken).
    _, second, _ = h.cycle()
    resumed = h.session.get(CrawlRun, second[site.key].run_id)
    assert second[site.key].status == "FAILED"
    assert resumed.resume_of_run_id == failed.id and resumed.trigger == "SCHEDULED"
    # Third cycle: no further retry, no request at all; a human is asked instead.
    seen = len(site.requests)
    _, third, _ = h.cycle()
    assert third[site.key].status == "NEEDS_HUMAN" and "not retried again" in third[site.key].detail
    assert len(site.requests) == seen


def test_a_resume_that_succeeds_completes_the_failed_work(h):
    site = h.source("a")
    site.boom.add("/products/b")
    _, first, _ = h.cycle()
    site.boom.clear()
    _, second, _ = h.cycle()
    assert second[site.key].status == "RESUMED"
    assert h.session.get(CrawlRun, second[site.key].run_id).resume_of_run_id == \
        first[site.key].run_id
    assert "/products/b" in site.paths() and len(h.candidates(site)) == 2


@pytest.mark.parametrize(("setup", "halt"), [
    (lambda s: s.status.__setitem__("/products/b", 429), "blocked_by_source_http_429"),
    (lambda s: s.status.__setitem__("/products/b", 403), "blocked_by_source_http_403"),
])
def test_a_source_block_is_a_halt_that_is_not_retried(h, setup, halt):
    site = h.source("a")
    setup(site)
    _, first, _ = h.cycle()
    assert first[site.key].status == "HALTED" and halt in first[site.key].detail
    h.advance(48)                                         # due again by cadence
    seen = len(site.requests)
    _, second, _ = h.cycle()
    assert second[site.key].status == "NEEDS_HUMAN" and "not retried" in second[site.key].detail
    assert len(site.requests) == seen


def test_robots_disallowed_links_are_never_requested(h):
    site = h.source("a")
    site.robots = "User-agent: *\nDisallow: /products/b\n"
    _, first, _ = h.cycle()
    assert first[site.key].status == "COMPLETED" and "/products/b" not in site.paths()


def test_robots_disallow_halts_and_disables_the_source(h):
    site = h.source("a")
    site.robots = "User-agent: *\nDisallow: /products\n"      # the seed itself
    _, first, _ = h.cycle()
    assert first[site.key].status == "HALTED" and "robots_disallow" in first[site.key].detail
    h.advance(48)
    seen = len(site.requests)
    _, second, _ = h.cycle()
    assert second[site.key].status == "DISABLED" and len(site.requests) == seen


# ------------------------------------------------------- new / changed only --


def test_unchanged_cycle_is_conditional_and_creates_no_duplicate_work(h):
    site = h.source("a")
    h.cycle()
    candidates = count(h.session, DiscoveryCandidate)
    results, claims = count(h.session, ExtractionResult), count(h.session, CandidateClaim)
    before = canonical(h.session)
    h.advance(25)
    start = len(site.requests)
    _, by_key, _ = h.cycle()
    obs = by_key[site.key]
    assert obs.status == "COMPLETED"
    assert (obs.counts["unchanged"], obs.counts["changed"], obs.counts["first_observation"]) \
        == (3, 0, 0)
    # Every page request is conditional and answered 304; a/ is asked for directly.
    page_requests = [(p, inm) for p, inm in site.requests[start:] if p != "/robots.txt"]
    assert [p for p, _ in page_requests] == ["/products", "/products/a/", "/products/b"]
    assert all(inm for _, inm in page_requests)
    assert (count(h.session, DiscoveryCandidate), count(h.session, ExtractionResult),
            count(h.session, CandidateClaim)) == (candidates, results, claims)
    assert canonical(h.session) == before
    assert obs.counts["review_items_this_cycle"] == 0    # nothing new to look at


def test_new_and_changed_urls_are_processed(h):
    site = h.source("a")
    h.cycle()
    site.pages["/products"] = listing("/products/a", "/products/b", "/products/c")
    site.pages["/products/b"] = product("X-B", "<p>Now with a bigger battery.</p>")
    site.pages["/products/c"] = product("X-C")
    h.advance(25)
    _, by_key, _ = h.cycle()
    counts = by_key[site.key].counts
    # seed listing and b changed; c is new; a is unchanged (304).
    assert (counts["changed"], counts["first_observation"], counts["unchanged"]) == (2, 1, 1)
    assert counts["new_product_urls"] == 1
    assert [c.candidate_name for c in h.candidates(site)] == ["X-A", "X-B", "X-C"]
    run_id = by_key[site.key].run_id
    extracted = set(h.session.scalars(
        select(DiscoveryCandidate.candidate_name).join(
            ExtractionResult, ExtractionResult.candidate_id == DiscoveryCandidate.id)
        .where(ExtractionResult.crawl_run_id == run_id)))
    assert extracted == {"X-B", "X-C"}                   # a was not re-extracted


# ---------------------------------------------------------------- redirects --


def test_known_canonical_redirect_is_not_repeated_on_later_cycles(h):
    site = h.source("a")
    h.cycle()
    assert site.paths()[:3] == ["/products", "/products/a", "/products/a/"]  # 301, then page
    h.advance(25)
    start = len(site.requests)
    _, by_key, _ = h.cycle()
    later = site.requests[start:]
    assert ("/products/a", None) not in later and not any(p == "/products/a" for p, _ in later)
    assert any(p == "/products/a/" and inm for p, inm in later)   # conditional, right URL
    assert by_key[site.key].counts["learned_canonical_requests"] == 1
    run = h.session.get(CrawlRun, by_key[site.key].run_id)
    assert run.counters["learned_canonical_requests"] == [
        {"url": f"https://{site.host}/products/a", "requested": f"https://{site.host}/products/a/"}]
    [cand_a] = [c for c in h.candidates(site) if c.candidate_name == "X-A"]
    assert cand_a.external_ref == f"https://{site.host}/products/a"  # identity unchanged


def test_learned_canonical_is_refused_by_robots_and_redirects_are_still_recorded(h):
    site = h.source("a")
    h.cycle()
    site.robots = "User-agent: *\nDisallow: /products/a/\n"
    h.advance(25)
    start = len(site.requests)
    _, by_key, _ = h.cycle()
    later = site.paths(start)
    assert "/products/a/" not in later                   # robots applies to the learned URL
    assert "/products/a" in later                        # fell back to the planned URL
    assert by_key[site.key].status == "HALTED"           # whose redirect robots then refused


def test_only_same_resource_redirects_are_learned(h, dsession):
    site = h.source("a")
    site.pages["/products"] = listing("/products/a", "/products/b", "/products/old")
    site.redirects["/products/old"] = "/products/new"
    site.pages["/products/new"] = product("X-N")
    h.cycle()
    source = dsession.scalars(select(DiscoverySource).where(
        DiscoverySource.key == site.key)).one()
    base = f"https://{site.host}"
    assert learned_canonical(dsession, source, f"{base}/products/a") == f"{base}/products/a/"
    assert learned_canonical(dsession, source, f"{base}/products/old") is None
    assert learned_canonical(dsession, source, f"{base}/products/b") is None
    h.advance(25)
    start = len(site.requests)
    h.cycle()
    assert site.paths(start).count("/products/old") == 1  # still asked for, then followed


def test_off_policy_redirect_is_refused_and_never_learned(h, dsession):
    site = h.source("a")
    site.redirects["/products/b"] = "https://elsewhere.example/products/b"
    h.cycle()
    source = dsession.scalars(select(DiscoverySource).where(
        DiscoverySource.key == site.key)).one()
    assert learned_canonical(dsession, source, f"https://{site.host}/products/b") is None
    assert "elsewhere.example" not in h.sites                # never contacted


def test_validators_are_not_sent_when_the_cached_body_is_gone(h):
    site = h.source("a")
    h.cycle()
    for body in h.cache_dir.iterdir():
        if body.is_file():
            body.unlink()                                  # cache lost (e.g. a new runner)
    h.advance(25)
    start = len(site.requests)
    _, by_key, _ = h.cycle()
    assert all(inm is None for p, inm in site.requests[start:] if p != "/robots.txt")
    assert by_key[site.key].status == "COMPLETED"
    assert by_key[site.key].counts["errors"] == 0        # full bodies, still extracted


# ------------------------------------------------------------------ Stage E --


def test_resolved_duplicate_does_not_reappear_on_later_cycles(h):
    site = h.source("a")
    site.pages["/products"] = listing("/products/a", "/products/b", "/products/a-reservation")
    site.pages["/products/a-reservation"] = product("X-A")
    _, first, _ = h.cycle()
    assert "DUPLICATE_PAIR" in first[site.key].counts["review_kinds_this_cycle"]
    a, reservation = [c for c in h.candidates(site) if c.candidate_name == "X-A"]
    review.decide_pair(h.session, a.id, reservation.id, review.SAME_ENTITY, decided_by="robert",
                       reason="reservation page of the same robot")
    # Both pages change, so both are re-extracted and re-resolved on the next cycle.
    site.pages["/products/a/"] = product("X-A", "<p>v2</p>")
    site.pages["/products/a-reservation"] = product("X-A", "<p>v2</p>")
    h.advance(25)
    _, second, _ = h.cycle()
    kinds = second[site.key].counts["review_kinds_this_cycle"]
    assert "DUPLICATE_PAIR" not in kinds
    assert {c.identity_status for c in h.candidates(site)} == {"NEW_ENTITY"}
    assert all(c.promoted_robot_id is None for c in h.candidates(site))  # never promoted


# ------------------------------------------------------------------ cadence --


@pytest.mark.parametrize(("value", "hours"), [("6h", 6), ("24h", 24), ("1d", 24), ("7d", 168),
                                              ("12", 12), ("90d", 2160)])
def test_interval_parsing(value, hours):
    assert registry.parse_interval(value) == hours


@pytest.mark.parametrize("value", ["5h", "0d", "91d", "30m", "1w", "", "daily"])
def test_interval_parsing_refuses_minutes_and_out_of_range(value):
    with pytest.raises(DiscoveryError):
        registry.parse_interval(value)


def test_cadence_is_attributed_and_due_is_last_end_plus_interval(dsession):
    source = DiscoverySource(key=f"cad-{uuid.uuid4().hex[:8]}", name="Cadence",
                             source_class="MANUFACTURER")
    dsession.add(source)
    dsession.flush()
    assert registry.next_observation_at(source) is None
    with pytest.raises(DiscoveryError, match="--by"):
        registry.set_cadence(dsession, source.key, every="24h", by=" ")
    registry.set_cadence(dsession, source.key, every="2d", by="robert")
    assert (source.observation_interval_hours, source.observation_cadence_set_by) == (48, "robert")
    assert source.is_enabled is False                    # cadence never enables
    assert registry.next_observation_at(source) <= datetime.now(UTC)   # never observed: due
    source.last_crawled_at = datetime(2026, 9, 27, 6, tzinfo=UTC)
    assert registry.next_observation_at(source) == datetime(2026, 9, 29, 6, tzinfo=UTC)
    registry.set_cadence(dsession, source.key, every=None, by="robert")
    assert source.observation_interval_hours is None and "cadence OFF" in source.notes


def test_database_refuses_an_unattributed_or_minute_cadence(dsession):
    source = DiscoverySource(key=f"cad-{uuid.uuid4().hex[:8]}", name="Cadence",
                             source_class="MANUFACTURER")
    dsession.add(source)
    dsession.flush()
    for sql in ("UPDATE discovery_source SET observation_interval_hours = 24 WHERE id = :id",
                "UPDATE discovery_source SET observation_interval_hours = 1,"
                " observation_cadence_set_by = 'r', observation_cadence_set_at = now()"
                " WHERE id = :id"):
        savepoint = dsession.begin_nested()
        with pytest.raises(IntegrityError, match="ck_discovery_source_cadence"):
            dsession.execute(text(sql), {"id": source.id})
        savepoint.rollback()


@contextmanager
def _shared(session):
    yield session


def test_cli_cadence_and_observe_plan(dsession, h, monkeypatch, capsys, tmp_path):
    site = h.source("a", cadence=None)
    dsession.commit = dsession.flush
    monkeypatch.setattr(db_session, "SessionLocal", lambda: _shared(dsession))
    assert cli.main(["source", "cadence", site.key, "--every", "1d", "--by", "robert"]) == 0
    assert "observation_cadence=every 24h" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["source", "cadence", site.key, "--by", "robert"])  # --every or --off
    report = tmp_path / "cycle.json"
    code = cli.main(["observe", "--plan", "--only", site.key, "--report-json", str(report)])
    out = capsys.readouterr().out
    assert code == 4 and "PLAN (no request, no write)" in out  # enabled, no adapter module
    assert '"plan_only": true' in report.read_text(encoding="utf-8")
    assert site.requests == []
