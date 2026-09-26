"""Discovery Stage B — bounded acquisition against PostgreSQL, offline.

Every run goes through httpx.MockTransport (no socket is ever opened; the
`no_external_network` guard fails the test otherwise) and a fake clock. Each
test is rollback-isolated and uses its own source, so observation history
never leaks between tests.
"""
from __future__ import annotations

import ast
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.acquisition import CrawlRun, FetchedPage, FetchedPageImmutableError
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.services.discovery import cache as body_cache
from app.services.discovery.acquisition import (
    AcquisitionRefused,
    CanonicalWriteRefused,
    build_report,
    classify,
    dry_run,
    plan,
    run_acquisition,
)
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.fingerprint import FINGERPRINT_VERSION, sha256_hex

pytestmark = pytest.mark.usefixtures("no_external_network")

HOST = "https://maker.example"
ROBOTS = f"{HOST}/robots.txt"
ALLOW_ALL = httpx.Response(200, text="User-agent: *\nAllow: /\n")
APP = Path(__file__).resolve().parents[1] / "app"


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

    def advance(self, seconds: float) -> None:
        self.t += seconds


class Site:
    def __init__(self, routes: dict | None = None) -> None:
        self.routes: dict[str, list] = {ROBOTS: [ALLOW_ALL]}
        self.routes.update({k: list(v) for k, v in (routes or {}).items()})
        self.requests: list[httpx.Request] = []

    def set(self, url: str, *responses) -> None:
        self.routes[url] = list(responses)

    def targets(self) -> list[str]:
        return [str(r.url) for r in self.requests if not str(r.url).endswith("/robots.txt")]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get(str(request.url))
        if not queue:
            return httpx.Response(404)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def cache_dir(tmp_path) -> Path:
    return tmp_path / "cache"


def make_source(session, **overrides) -> DiscoverySource:
    fields = dict(
        key=f"stage-b:{uuid.uuid4().hex[:10]}", name="Fixture maker",
        source_class="MANUFACTURER", homepage_url=f"{HOST}/",
        allowed_path_prefixes=["/products/"], is_enabled=True,
        tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime(2026, 9, 1, tzinfo=UTC),
        eligibility_reviewed_by="owner",
    )
    fields.update(overrides)
    source = DiscoverySource(**fields)
    session.add(source)
    session.flush()
    return source


def acquire(session, source, urls, site, clock, cache_dir, **limits) -> CrawlRun:
    fetcher = HttpFetcher(limits=FetchLimits(**limits), transport=httpx.MockTransport(site),
                          monotonic=clock.monotonic, sleep=clock.sleep)
    with fetcher:
        return run_acquisition(session, source=source, urls=urls, operator="Robert (test)",
                               fetcher=fetcher, cache_dir=cache_dir, now=clock.now)


def pages(session, run) -> list[FetchedPage]:
    return list(session.scalars(select(FetchedPage).where(FetchedPage.crawl_run_id == run.id)
                                .order_by(FetchedPage.retrieved_at)))


def html(text_: str, **headers) -> httpx.Response:
    return httpx.Response(200, text=f"<html><body><p>{text_}</p></body></html>",
                          headers={"content-type": "text/html; charset=utf-8", **headers})


# ------------------------------------------------------- acquisition eligibility --


@pytest.mark.parametrize("overrides", [
    {"is_enabled": False},
    {"is_enabled": False, "robots_status": "DISALLOWED"},
    {"is_enabled": False, "tos_status": "PROHIBITED"},  # owner-recorded terms decision
    {"homepage_url": None},
    {"allowed_path_prefixes": None},
])
def test_ineligible_source_reaches_no_transport(dsession, clock, cache_dir, overrides):
    source = make_source(dsession, **overrides)
    site = Site({f"{HOST}/products/h1": [html("x")]})
    with pytest.raises(AcquisitionRefused):
        acquire(dsession, source, [f"{HOST}/products/h1"], site, clock, cache_dir)
    assert site.requests == []
    assert dsession.scalar(select(func.count()).select_from(CrawlRun)
                           .where(CrawlRun.source_id == source.id)) == 0


@pytest.mark.parametrize("url", [
    "https://other.example/products/h1",   # outside approved host
    f"{HOST}/about/team",                  # outside allowed_path_prefixes
])
def test_url_outside_policy_reaches_no_transport_at_all(dsession, clock, cache_dir, url):
    source = make_source(dsession)
    site = Site()
    with pytest.raises(AcquisitionRefused) as exc:
        acquire(dsession, source, [f"{HOST}/products/ok", url], site, clock, cache_dir)
    assert site.requests == []  # not even robots.txt: refusal precedes any request
    assert url in str(exc.value)


@pytest.mark.parametrize("overrides", [
    {"tos_expires_at": None, "tos_reviewed_at": None},
    {"tos_expires_at": datetime(2020, 1, 1, tzinfo=UTC)},
    {"tos_page_hash": "0" * 64},
    {"tos_reviewed_at": datetime(2015, 1, 1, tzinfo=UTC)},
])
def test_tos_currency_never_blocks_acquisition(dsession, clock, cache_dir, overrides):
    """Owner decision DR-A4: missing/expired ToS expiry, an old review or a
    changed ToS page hash must not block, halt or skip acquisition."""
    source = make_source(dsession, **overrides)
    site = Site({f"{HOST}/products/h1": [html("H1")]})
    run = acquire(dsession, source, [f"{HOST}/products/h1"], site, clock, cache_dir)
    assert run.status == "COMPLETED"
    assert site.targets() == [f"{HOST}/products/h1"]
    assert not any("terms" in str(r.url) or "tos" in str(r.url) for r in site.requests)


# --------------------------------------------------------------------- robots --


def test_robots_allows_url_and_provenance_is_recorded(dsession, clock, cache_dir):
    source = make_source(dsession, last_robots_checked_at=None)  # stale/missing: re-read
    site = Site({f"{HOST}/products/h1": [html("H1")]})
    run = acquire(dsession, source, [f"{HOST}/products/h1"], site, clock, cache_dir)
    (page,) = pages(dsession, run)
    assert str(site.requests[0].url) == ROBOTS  # robots is read first, every run
    assert page.robots_decision_at_fetch == "ALLOWED"
    robots = run.run_manifest["robots"][0]
    assert robots["url"] == ROBOTS and robots["http_status"] == 200
    assert robots["sha256"] == sha256_hex(b"User-agent: *\nAllow: /\n")
    assert source.last_robots_hash == robots["sha256"]
    assert source.last_robots_checked_at == clock.base


def test_robots_disallow_blocks_page_halts_run_and_disables_source(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site({ROBOTS: [httpx.Response(200, text="User-agent: *\nDisallow: /products/secret")],
                 f"{HOST}/products/secret": [html("S")], f"{HOST}/products/h1": [html("H1")]})
    run = acquire(dsession, source, [f"{HOST}/products/secret", f"{HOST}/products/h1"],
                  site, clock, cache_dir)
    assert site.targets() == []  # the disallowed page was never requested
    (page,) = pages(dsession, run)
    assert (page.outcome, page.robots_decision_at_fetch) == ("BLOCKED_BY_ROBOTS", "DISALLOWED")
    assert page.retrieval_method is None and page.final_url is None  # nothing retrieved
    assert run.status == "HALTED_BY_POLICY"
    assert run.counters["halt_reason"] == "robots_disallow"
    assert run.counters["not_attempted"] == 1
    assert source.is_enabled is False and source.radar_eligible is False
    assert classify(dsession, page) == "BLOCKED_BY_ROBOTS"


def test_robots_specific_to_our_bot_is_honoured(dsession, clock, cache_dir):
    source = make_source(dsession)
    robots = "User-agent: HumanoidOnlineMarketBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    site = Site({ROBOTS: [httpx.Response(200, text=robots)]})
    run = acquire(dsession, source, [f"{HOST}/products/h1"], site, clock, cache_dir)
    assert site.targets() == [] and run.status == "HALTED_BY_POLICY"


def test_radar_eligible_never_bypasses_robots(dsession, clock, cache_dir):
    source = make_source(dsession)
    assert source.radar_eligible is True
    site = Site({ROBOTS: [httpx.Response(403)]})  # 401/403 on robots = complete disallow
    run = acquire(dsession, source, [f"{HOST}/products/h1"], site, clock, cache_dir)
    assert site.targets() == [] and run.status == "HALTED_BY_POLICY"


@pytest.mark.parametrize("robots_response", [httpx.Response(503), httpx.ConnectError("down")])
def test_unavailable_robots_fetches_nothing(dsession, clock, cache_dir, robots_response):
    source = make_source(dsession)
    site = Site({ROBOTS: [robots_response]})
    run = acquire(dsession, source, [f"{HOST}/products/h1"], site, clock, cache_dir)
    assert site.targets() == []
    assert run.status == "HALTED_BY_POLICY"
    assert run.counters["halt_reason"].startswith("robots_unavailable")
    assert pages(dsession, run) == []
    assert source.is_enabled is True  # unavailable is not a disallow


def test_missing_robots_file_means_no_restriction(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site({ROBOTS: [httpx.Response(404)], f"{HOST}/products/h1": [html("H1")]})
    run = acquire(dsession, source, [f"{HOST}/products/h1"], site, clock, cache_dir)
    assert run.status == "COMPLETED" and site.targets() == [f"{HOST}/products/h1"]


def test_robots_older_than_24h_is_reread_mid_run(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/a": [html("A")], f"{HOST}/products/b": [html("B")]})
    original_get = site.__call__

    def slow(request):
        if str(request.url).endswith("/products/a"):
            clock.advance(25 * 3600)
        return original_get(request)

    fetcher = HttpFetcher(transport=httpx.MockTransport(slow), monotonic=clock.monotonic,
                          sleep=clock.sleep)
    with fetcher:
        run = run_acquisition(dsession, source=source, urls=[f"{HOST}/products/a",
                              f"{HOST}/products/b"], operator="op", fetcher=fetcher,
                              cache_dir=cache_dir, now=clock.now)
    robots_reads = [str(r.url) for r in site.requests].count(ROBOTS)
    assert robots_reads == 2 and len(run.run_manifest["robots"]) == 2


# ---------------------------------------------------------------- HTTP rules --


@pytest.mark.parametrize("status", [403, 429, 401])
def test_block_by_source_is_recorded_and_halts(dsession, clock, cache_dir, status):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/a": [httpx.Response(status)],
                 f"{HOST}/products/b": [html("B")]})
    run = acquire(dsession, source, [f"{HOST}/products/a", f"{HOST}/products/b"],
                  site, clock, cache_dir)
    assert site.targets() == [f"{HOST}/products/a"]  # one request, no retry, then stop
    (page,) = pages(dsession, run)
    assert (page.outcome, page.http_status) == ("BLOCKED_BY_SOURCE", status)
    assert run.status == "HALTED_BY_POLICY" and run.counters["not_attempted"] == 1
    assert source.is_enabled is True  # a block is a finding, not a robots disallow


def test_timeout_and_oversize_body_are_errors_not_observations_of_content(
    dsession, clock, cache_dir
):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/slow": [httpx.ReadTimeout("t")],
                 f"{HOST}/products/big": [httpx.Response(200, content=b"x" * 100)]})
    run = acquire(dsession, source, [f"{HOST}/products/slow", f"{HOST}/products/big"],
                  site, clock, cache_dir, max_body_bytes=50)  # robots.txt is 24 bytes
    slow, big = pages(dsession, run)
    assert (slow.outcome, slow.error_class) == ("ERROR", "timeout")
    assert (big.outcome, big.error_class, big.content_hash) == ("ERROR", "body_too_large", None)
    assert run.status == "COMPLETED" and run.counters["fetch_error"] == 2
    assert not cache_dir.exists() or not any(p.is_file() for p in cache_dir.glob("*"))


def test_page_cap_refuses_before_any_request(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site()
    urls = [f"{HOST}/products/{i}" for i in range(3)]
    with pytest.raises(AcquisitionRefused, match="PAGE_CAP_EXCEEDED"):
        acquire(dsession, source, urls, site, clock, cache_dir, page_cap=2)
    assert site.requests == []


def test_per_host_rate_limit_applies_across_robots_and_pages(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/a": [html("A")], f"{HOST}/products/b": [html("B")]})
    acquire(dsession, source, [f"{HOST}/products/a", f"{HOST}/products/b"], site, clock,
            cache_dir)
    assert clock.sleeps == [2.0, 2.0]  # robots -> a -> b, >= 2 s apart


def test_conditional_request_uses_prior_validators_and_304_is_unchanged(
    dsession, clock, cache_dir
):
    source = make_source(dsession)
    url = f"{HOST}/products/h1"
    modified = {"last-modified": "Tue, 01 Sep 2026 00:00:00 GMT"}
    site = Site({url: [html("H1", etag='"v1"', **modified),
                       httpx.Response(304, headers={"etag": '"v1"'})]})
    first = acquire(dsession, source, [url], site, clock, cache_dir)
    second = acquire(dsession, source, [url], site, clock, cache_dir)
    conditional = [r for r in site.requests if str(r.url) == url][1]
    assert conditional.headers["if-none-match"] == '"v1"'
    assert conditional.headers["if-modified-since"] == "Tue, 01 Sep 2026 00:00:00 GMT"
    (page,) = pages(dsession, second)
    assert page.outcome == "NOT_MODIFIED" and page.content_hash is None
    assert classify(dsession, page) == "UNCHANGED"
    assert second.counters["unchanged"] == 1 and second.counters["not_modified"] == 1
    assert pages(dsession, first)[0].outcome == "FETCHED"


# ------------------------------------------------------------------ redirects --


def test_redirect_inside_policy_is_followed_and_final_url_recorded(dsession, clock, cache_dir):
    source = make_source(dsession)
    moved = httpx.Response(301, headers={"location": "/products/new"})
    site = Site({f"{HOST}/products/old": [moved],
                 f"{HOST}/products/new": [html("New")]})
    run = acquire(dsession, source, [f"{HOST}/products/old"], site, clock, cache_dir)
    (page,) = pages(dsession, run)
    assert page.url == f"{HOST}/products/old"            # requested URL preserved
    assert page.final_url == f"{HOST}/products/new"
    assert (page.outcome, page.retrieval_method) == ("FETCHED", "HTTP_GET")


@pytest.mark.parametrize(("location", "reason"), [
    ("https://evil.example/products/x", "URL_OUTSIDE_APPROVED_HOST"),
    ("https://shop.maker.example/products/x", "URL_OUTSIDE_APPROVED_HOST"),
    ("/about/x", "URL_OUTSIDE_APPROVED_PATHS"),
])
def test_redirect_outside_policy_is_refused_and_not_fetched(
    dsession, clock, cache_dir, location, reason
):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/a": [httpx.Response(302, headers={"location": location})]})
    run = acquire(dsession, source, [f"{HOST}/products/a"], site, clock, cache_dir)
    assert site.targets() == [f"{HOST}/products/a"]
    (page,) = pages(dsession, run)
    assert page.outcome == "ERROR" and page.error_class == f"redirect_outside_policy:{reason}"
    assert page.final_url == f"{HOST}/products/a"
    assert run.counters["redirects_refused"][0]["reason"] == reason


def test_redirect_cannot_escape_robots(dsession, clock, cache_dir):
    source = make_source(dsession, allowed_path_prefixes=["/products/"])
    site = Site({ROBOTS: [httpx.Response(200, text="User-agent: *\nDisallow: /products/private")],
                 f"{HOST}/products/a": [
                     httpx.Response(302, headers={"location": "/products/private"})],
                 f"{HOST}/products/private": [html("secret")]})
    run = acquire(dsession, source, [f"{HOST}/products/a"], site, clock, cache_dir)
    assert f"{HOST}/products/private" not in site.targets()
    (page,) = pages(dsession, run)
    assert (page.outcome, page.robots_decision_at_fetch) == ("BLOCKED_BY_ROBOTS", "DISALLOWED")
    assert run.status == "HALTED_BY_POLICY" and source.is_enabled is False


def test_redirect_chain_is_bounded(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/a": [httpx.Response(302, headers={"location": "/products/a"})]})
    run = acquire(dsession, source, [f"{HOST}/products/a"], site, clock, cache_dir,
                  max_redirects=2)
    (page,) = pages(dsession, run)
    assert page.error_class == "too_many_redirects" and len(site.targets()) == 3


# ----------------------------------------------------------- change detection --


def test_first_unchanged_changed_and_history_is_preserved(dsession, clock, cache_dir):
    source = make_source(dsession)
    url = f"{HOST}/products/h1"
    site = Site({url: [html("Coming soon"), html("Coming  soon"), html("Pre-order open")]})
    runs = [acquire(dsession, source, [url], site, clock, cache_dir) for _ in range(3)]
    observed = [pages(dsession, r)[0] for r in runs]
    assert [classify(dsession, p) for p in observed] == ["FIRST_OBSERVATION", "UNCHANGED",
                                                        "CHANGED"]
    assert [r.counters["first_observation"] + r.counters["unchanged"] * 10
            + r.counters["changed"] * 100 for r in runs] == [1, 10, 100]
    # one new row per retrieval; earlier rows untouched
    assert len({p.id for p in observed}) == 3
    assert observed[0].content_hash == observed[1].content_hash != observed[2].content_hash


@pytest.mark.parametrize("status", [404, 410])
def test_gone_is_source_removed(dsession, clock, cache_dir, status):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/h1": [httpx.Response(status)]})
    run = acquire(dsession, source, [f"{HOST}/products/h1"], site, clock, cache_dir)
    (page,) = pages(dsession, run)
    assert (page.outcome, page.http_status, page.error_class) == ("ERROR", status, "gone")
    assert classify(dsession, page) == "SOURCE_REMOVED"
    assert run.counters["source_removed"] == 1


def test_other_status_is_fetch_error(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/h1": [httpx.Response(500)]})
    run = acquire(dsession, source, [f"{HOST}/products/h1"], site, clock, cache_dir)
    (page,) = pages(dsession, run)
    assert classify(dsession, page) == "FETCH_ERROR"
    assert len(site.targets()) == 3  # bounded retries for 5xx


def test_only_same_fingerprint_version_is_compared(dsession, clock, cache_dir):
    source = make_source(dsession)
    url = f"{HOST}/products/h1"
    site = Site({url: [html("Same")]})
    first = acquire(dsession, source, [url], site, clock, cache_dir)
    first.run_manifest = {**first.run_manifest, "fingerprint_version": "legacy/0"}
    dsession.flush()
    second = acquire(dsession, source, [url], site, clock, cache_dir)
    assert classify(dsession, pages(dsession, second)[0]) == "FIRST_OBSERVATION"
    assert second.run_manifest["fingerprint_version"] == FINGERPRINT_VERSION


# ------------------------------------------------------------------ persistence --


def test_observations_are_immutable(dsession, clock, cache_dir):
    source = make_source(dsession)
    run = acquire(dsession, source, [f"{HOST}/products/h1"],
                  Site({f"{HOST}/products/h1": [html("H1")]}), clock, cache_dir)
    (page,) = pages(dsession, run)
    page.content_hash = "f" * 64
    with pytest.raises(FetchedPageImmutableError):
        dsession.flush()
    dsession.rollback()


def test_observation_delete_is_refused(dsession, clock, cache_dir):
    source = make_source(dsession)
    run = acquire(dsession, source, [f"{HOST}/products/h1"],
                  Site({f"{HOST}/products/h1": [html("H1")]}), clock, cache_dir)
    dsession.delete(pages(dsession, run)[0])
    with pytest.raises(FetchedPageImmutableError):
        dsession.flush()
    dsession.rollback()


def test_raw_body_is_cached_by_sha256_and_never_stored_in_db(dsession, clock, cache_dir):
    source = make_source(dsession)
    response = html("H1 humanoid")
    body = response.content
    run = acquire(dsession, source, [f"{HOST}/products/h1"],
                  Site({f"{HOST}/products/h1": [response]}), clock, cache_dir)
    (page,) = pages(dsession, run)
    raw = sha256_hex(body)
    assert body_cache.read_body(cache_dir, raw) == body
    sidecar = (cache_dir / "observations" / f"{page.id}.json").read_text(encoding="utf-8")
    assert raw in sidecar and page.content_hash in sidecar
    assert page.content_length == len(body)
    columns = {c.name for c in FetchedPage.__table__.columns}
    assert not {"body", "content", "raw_body", "html"} & columns
    # the observation and its body are linked, but the body lives only on disk
    assert raw != page.content_hash  # content_hash is the normalized fingerprint


def test_page_provenance_fields(dsession, clock, cache_dir):
    source = make_source(dsession)
    run = acquire(dsession, source, [f"{HOST}/products/h1"],
                  Site({f"{HOST}/products/h1": [html("H1", etag='"e"')]}), clock, cache_dir)
    (page,) = pages(dsession, run)
    assert page.url == page.final_url == f"{HOST}/products/h1"
    assert page.retrieval_method == "HTTP_GET"
    assert page.retrieved_at == clock.base + timedelta(seconds=2)
    assert page.http_status == 200 and page.content_type.startswith("text/html")
    assert page.etag == '"e"' and page.robots_decision_at_fetch == "ALLOWED"
    manifest = run.run_manifest
    assert manifest["requested_urls"] == [f"{HOST}/products/h1"]
    assert manifest["source_key"] == source.key and manifest["retrieval_method"] == "HTTP_GET"
    assert manifest["user_agent"].startswith("HumanoidOnlineMarketBot/0.1")
    assert manifest["limits"]["page_cap"] == 200
    assert run.operator == "Robert (test)" and run.trigger == "MANUAL"
    assert run.counters["canonical_rows_written"] == 0


# ---------------------------------------------------------- canonical isolation --

CANONICAL_TABLES = ("robot", "manufacturer", "evidence_source", "pricing_offer",
                    "availability_offer", "specification", "robot_image",
                    "discovery_candidate", "candidate_claim")


def test_no_canonical_rows_are_written(dsession, clock, cache_dir):
    def counts():
        return {t: dsession.execute(text(f"SELECT count(*) FROM {t}")).scalar()
                for t in CANONICAL_TABLES}

    before = counts()
    source = make_source(dsession)
    site = Site({f"{HOST}/products/a": [html("Launch: new humanoid H9")],
                 f"{HOST}/products/b": [httpx.Response(404)]})
    run = acquire(dsession, source, [f"{HOST}/products/a", f"{HOST}/products/b"],
                  site, clock, cache_dir)
    assert counts() == before
    assert run.counters["canonical_rows_written"] == 0
    assert "Canonical rows written               0" in build_report(dsession, run.id)


def test_flush_guard_refuses_any_other_table(dsession, clock, cache_dir):
    source = make_source(dsession)
    dsession.add(DiscoveryCandidate(source_id=source.id, external_ref="sneaky"))
    with pytest.raises(CanonicalWriteRefused):
        acquire(dsession, source, [f"{HOST}/products/a"], Site(), clock, cache_dir)
    dsession.rollback()


def test_acquisition_code_imports_no_canonical_models_or_promotion():
    allowed = {"app.models.acquisition", "app.models.discovery"}
    files = [APP / "services" / "discovery" / f for f in
             ("acquisition.py", "fetcher.py", "robots.py", "cache.py", "fingerprint.py",
              "eligibility.py")] + [APP / "cli" / "discovery.py"]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("app.models"):
                    assert node.module in allowed, (path.name, node.module)
                assert "promotion" not in node.module, (path.name, node.module)
                assert "pipeline" not in node.module, (path.name, node.module)


# ------------------------------------------------------------ plan and dry run --


def test_plan_is_pure_and_reports_every_problem(dsession):
    source = make_source(dsession)
    verdicts = dict(plan(source, [f"{HOST}/products/a", f"{HOST}/about",
                                  f"{HOST}/products/a"], page_cap=200))
    assert verdicts[f"{HOST}/about"] == "URL_OUTSIDE_APPROVED_PATHS"
    assert plan(source, [], 200) == [("-", "NO_URLS")]
    assert dict(plan(source, [f"{HOST}/products/a"] * 2, 200)) == {
        f"{HOST}/products/a": "DUPLICATE_URL"}


def test_dry_run_reads_only_robots_and_writes_nothing(dsession, clock):
    source = make_source(dsession)
    site = Site({ROBOTS: [httpx.Response(200, text="User-agent: *\nDisallow: /products/b")]})
    before = dsession.scalar(select(func.count()).select_from(CrawlRun))
    fetcher = HttpFetcher(transport=httpx.MockTransport(site), monotonic=clock.monotonic,
                          sleep=clock.sleep)
    with fetcher:
        result = dry_run(source, [f"{HOST}/products/a", f"{HOST}/products/b"], fetcher,
                         now=clock.now)
    assert [str(r.url) for r in site.requests] == [ROBOTS]
    assert dict(result.decisions) == {f"{HOST}/products/a": "WOULD_FETCH",
                                      f"{HOST}/products/b": "WOULD_NOT_FETCH: robots disallow"}
    assert result.run is None
    assert dsession.scalar(select(func.count()).select_from(CrawlRun)) == before
    assert not dsession.new and not dsession.dirty


def test_dry_run_refuses_ineligible_source_without_any_request(dsession, clock):
    source = make_source(dsession, is_enabled=False)
    site = Site()
    with pytest.raises(AcquisitionRefused):
        dry_run(source, [f"{HOST}/products/a"],
                HttpFetcher(transport=httpx.MockTransport(site)), now=clock.now)
    assert site.requests == []


def test_operator_is_required(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site()
    fetcher = HttpFetcher(transport=httpx.MockTransport(site))
    with pytest.raises(AcquisitionRefused, match="OPERATOR_REQUIRED"):
        run_acquisition(dsession, source=source, urls=[f"{HOST}/products/a"], operator=" ",
                        fetcher=fetcher, cache_dir=cache_dir)
    assert site.requests == []


def test_kill_switch_cancels_between_requests(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/a": [html("A")], f"{HOST}/products/b": [html("B")]})
    fetched: list[str] = []

    def kill() -> bool:
        return len(site.targets()) >= 1  # engage after the first page

    fetcher = HttpFetcher(transport=httpx.MockTransport(site), monotonic=clock.monotonic,
                          sleep=clock.sleep, kill_switch=kill)
    with fetcher:
        run = run_acquisition(dsession, source=source,
                              urls=[f"{HOST}/products/a", f"{HOST}/products/b"],
                              operator="op", fetcher=fetcher, cache_dir=cache_dir, now=clock.now)
    fetched = site.targets()
    assert fetched == [f"{HOST}/products/a"]
    assert run.status == "CANCELLED" and run.finished_at is not None
    assert run.counters["halt_reason"] == "kill_switch"


def test_report_is_reproducible_from_the_database(dsession, clock, cache_dir):
    source = make_source(dsession)
    site = Site({f"{HOST}/products/a": [html("A")], f"{HOST}/products/b": [httpx.Response(410)]})
    run = acquire(dsession, source, [f"{HOST}/products/a", f"{HOST}/products/b"],
                  site, clock, cache_dir)
    report = build_report(dsession, run.id)
    assert f"RUN {run.id}" in report and "status=COMPLETED" in report
    assert "FIRST_OBSERVATION" in report and "SOURCE_REMOVED" in report
    assert report == build_report(dsession, run.id)
