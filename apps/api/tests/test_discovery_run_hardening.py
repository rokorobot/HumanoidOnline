"""Discovery run hardening — durable FAILED and governed resume (docs/16 §7, Gate H).

Offline, against PostgreSQL. The session joins the test transaction in
`create_savepoint` mode, so `session.commit()` (the CLI's checkpoint) is a real,
durable commit for the test's purposes and `session.rollback()` discards only
what was not yet committed — exactly what a crash does to a real run. The whole
test is still rolled back at the end.

Proves:
- an unexpected exception moves a durable run RUNNING -> FAILED (KeyboardInterrupt
  -> CANCELLED) and re-raises; observations committed before it survive, the
  uncommitted remainder does not;
- a process that died without recording an end can be marked FAILED only by a
  governed, attributed, stale-only operator act;
- resume creates a NEW linked run, honours the parent's manifest and limits,
  requests only what the chain has not fetched successfully, and never
  duplicates or rewrites a committed observation;
- an adapter run whose extraction failed is resumable without any request, and
  the resume extracts the parent's pages exactly once.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_discovery_acquisition import HOST, Clock, Site, html, make_source
from test_discovery_adapter_run import (
    ALPHA,
    BETA,
    OMEGA_NEWS,
    FixtureSite,
    _candidate,
    world,  # noqa: F401 - pytest fixture
)

from app.cli import discovery as cli
from app.db.session import engine
from app.models.acquisition import CrawlRun, ExtractionResult, FetchedPage
from app.models.discovery import DiscoveryCandidate
from app.services.discovery import adapter_run as adapter_module
from app.services.discovery import cache as body_cache
from app.services.discovery.acquisition import (
    DiscoveryError,
    ResumeRefused,
    build_report,
    mark_stale_run_failed,
    resume_acquisition,
    run_acquisition,
)
from app.services.discovery.adapter_run import resume_adapter, run_adapter
from app.services.discovery.fetcher import FetchLimits, HttpFetcher

pytestmark = pytest.mark.usefixtures("no_external_network")

URLS = [f"{HOST}/products/{c}" for c in "abcd"]


@pytest.fixture
def dsession(database_url):
    """Commits are durable savepoints; rollback returns to the last commit."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def clock() -> Clock:
    return Clock()


class Exploding:
    """Wraps a site; raises `exc` instead of answering `fail_on` (once)."""

    def __init__(self, site, fail_on: str, exc: BaseException) -> None:
        self.site, self.fail_on, self.exc = site, fail_on, exc
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if url == self.fail_on and self.exc is not None:
            exc, self.exc = self.exc, None
            raise exc
        return self.site(request)

    def targets(self) -> list[str]:
        return [u for u in self.requests if not u.endswith("/robots.txt")]


def _site() -> Site:
    return Site({u: [html(f"page {u[-1]}")] for u in URLS})


def _fetcher(handler, clock, **limits) -> HttpFetcher:
    return HttpFetcher(limits=FetchLimits(**limits), transport=httpx.MockTransport(handler),
                       monotonic=clock.monotonic, sleep=clock.sleep)


def _acquire(session, source, handler, clock, cache_dir, urls=URLS) -> CrawlRun:
    with _fetcher(handler, clock) as fetcher:
        return run_acquisition(session, source=source, urls=urls, operator="Robert (test)",
                               fetcher=fetcher, cache_dir=cache_dir, now=clock.now,
                               checkpoint=session.commit)


def _resume(session, source, parent, handler, clock, cache_dir, **limits) -> CrawlRun:
    with _fetcher(handler, clock, **limits) as fetcher:
        return resume_acquisition(session, parent_run_id=parent.id, source=source,
                                  operator="Robert (test)", fetcher=fetcher,
                                  cache_dir=cache_dir, now=clock.now, checkpoint=session.commit)


def _pages(session, run) -> list[FetchedPage]:
    return list(session.scalars(select(FetchedPage).where(FetchedPage.crawl_run_id == run.id)
                                .order_by(FetchedPage.retrieved_at)))


def _run_ids(session, source) -> list:
    return list(session.scalars(select(CrawlRun.id).where(CrawlRun.source_id == source.id)))


# ------------------------------------------------------------ durable FAILED --


def test_unexpected_exception_marks_the_run_failed_and_keeps_committed_observations(
        dsession, clock, tmp_path):
    source = make_source(dsession)
    dsession.commit()
    handler = Exploding(_site(), URLS[2], RuntimeError("parser exploded"))

    with pytest.raises(RuntimeError, match="parser exploded"):
        _acquire(dsession, source, handler, clock, tmp_path / "cache")

    [run_id] = _run_ids(dsession, source)
    run = dsession.get(CrawlRun, run_id)
    assert run.status == "FAILED" and run.finished_at is not None
    assert run.counters["halt_reason"] == "unexpected_error: RuntimeError"
    assert [p.url for p in _pages(dsession, run)] == URLS[:2]      # committed ones survive
    assert run.counters["attempted"] == 2 and run.counters["fetched"] == 2
    assert run.counters["not_attempted"] == 2
    assert "status=FAILED" in build_report(dsession, run.id)


def test_failure_after_flush_discards_the_uncommitted_observation(dsession, clock, tmp_path,
                                                                  monkeypatch):
    source = make_source(dsession)
    dsession.commit()
    real = body_cache.record_observation
    calls = {"n": 0}

    def flaky(root, page_id, meta):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real(root, page_id, meta)

    monkeypatch.setattr(body_cache, "record_observation", flaky)
    with pytest.raises(OSError):
        _acquire(dsession, source, _site(), clock, tmp_path / "cache")
    run = dsession.get(CrawlRun, _run_ids(dsession, source)[0])
    assert run.status == "FAILED"
    assert run.counters["halt_reason"] == "unexpected_error: OSError"
    assert [p.url for p in _pages(dsession, run)] == URLS[:1]      # 2nd was never committed


def test_keyboard_interrupt_cancels_durably(dsession, clock, tmp_path):
    source = make_source(dsession)
    dsession.commit()
    with pytest.raises(KeyboardInterrupt):
        _acquire(dsession, source, Exploding(_site(), URLS[1], KeyboardInterrupt()), clock,
                 tmp_path / "cache")
    run = dsession.get(CrawlRun, _run_ids(dsession, source)[0])
    assert (run.status, run.counters["halt_reason"]) == ("CANCELLED", "interrupted")
    assert [p.url for p in _pages(dsession, run)] == URLS[:1]


def test_a_dead_process_is_marked_failed_only_by_a_governed_stale_act(dsession, clock, tmp_path):
    source = make_source(dsession)
    dsession.commit()
    # SystemExit is not caught: it stands in for a process that died (kill -9).
    with pytest.raises(SystemExit):
        _acquire(dsession, source, Exploding(_site(), URLS[2], SystemExit(1)), clock,
                 tmp_path / "cache")
    run = dsession.get(CrawlRun, _run_ids(dsession, source)[0])
    assert run.status == "RUNNING"                                 # nothing recorded an end

    with pytest.raises(ResumeRefused, match="RUN_STILL_RUNNING"):
        _resume(dsession, source, run, _site(), clock, tmp_path / "cache")
    with pytest.raises(DiscoveryError, match="not stale yet"):
        mark_stale_run_failed(dsession, run.id, by="robert", reason="process killed",
                              now=clock.now)
    with pytest.raises(DiscoveryError, match="required"):
        mark_stale_run_failed(dsession, run.id, by=" ", reason="x", now=clock.now)

    clock.t += 31 * 60
    marked = mark_stale_run_failed(dsession, run.id, by="robert", reason="process killed",
                                   now=clock.now)
    assert marked.status == "FAILED"
    assert marked.counters["halt_reason"] == "marked_failed_by_operator: process killed"
    assert marked.counters["attempted"] == 2 and marked.run_manifest["marked_failed_by"] == "robert"
    with pytest.raises(DiscoveryError, match="not RUNNING"):
        mark_stale_run_failed(dsession, run.id, by="robert", reason="again", now=clock.now)


# ------------------------------------------------------------------ resume --


def test_resume_fetches_only_what_was_not_fetched_and_duplicates_nothing(
        dsession, clock, tmp_path):
    source = make_source(dsession)
    dsession.commit()
    cache_dir = tmp_path / "cache"
    with pytest.raises(RuntimeError):
        _acquire(dsession, source, Exploding(_site(), URLS[2], RuntimeError("boom")), clock,
                 cache_dir)
    parent = dsession.get(CrawlRun, _run_ids(dsession, source)[0])
    before = {(p.id, p.url, p.content_hash, p.outcome) for p in _pages(dsession, parent)}

    site = Exploding(_site(), "-", None)
    resumed = _resume(dsession, source, parent, site, clock, cache_dir)

    assert resumed.status == "COMPLETED" and resumed.resume_of_run_id == parent.id
    assert site.targets() == URLS[2:]                              # never re-requested a, b
    assert resumed.run_manifest["requested_urls"] == URLS[2:]
    assert resumed.run_manifest["resume_skipped_completed"] == URLS[:2]
    assert resumed.run_manifest["planned_urls"] == URLS
    assert {(p.id, p.url, p.content_hash, p.outcome)
            for p in _pages(dsession, parent)} == before           # parent untouched
    assert dsession.get(CrawlRun, parent.id).status == "FAILED"
    fetched = list(dsession.scalars(select(FetchedPage.url).where(
        FetchedPage.source_id == source.id, FetchedPage.outcome == "FETCHED")))
    assert sorted(fetched) == URLS                                 # one observation per URL
    assert f"resumed_from={parent.id}" in build_report(dsession, resumed.id)


def test_resume_of_a_resume_walks_the_chain(dsession, clock, tmp_path):
    source = make_source(dsession)
    dsession.commit()
    cache_dir = tmp_path / "cache"
    with pytest.raises(RuntimeError):
        _acquire(dsession, source, Exploding(_site(), URLS[1], RuntimeError()), clock, cache_dir)
    first = dsession.get(CrawlRun, _run_ids(dsession, source)[0])
    with pytest.raises(RuntimeError):
        _resume(dsession, source, first, Exploding(_site(), URLS[3], RuntimeError()), clock,
                cache_dir)
    second = dsession.scalars(select(CrawlRun).where(CrawlRun.resume_of_run_id == first.id)).one()
    assert second.status == "FAILED"

    with pytest.raises(ResumeRefused, match="ALREADY_RESUMED"):
        _resume(dsession, source, first, _site(), clock, cache_dir)
    site = Exploding(_site(), "-", None)
    third = _resume(dsession, source, second, site, clock, cache_dir)
    assert site.targets() == URLS[3:]
    assert third.status == "COMPLETED"
    assert sorted(dsession.scalars(select(FetchedPage.url).where(
        FetchedPage.source_id == source.id, FetchedPage.outcome == "FETCHED"))) == URLS


@pytest.mark.parametrize("case", ["completed", "halted", "source", "limits", "adapter"])
def test_resume_refusals_issue_no_request(dsession, clock, tmp_path, case):
    source = make_source(dsession)
    dsession.commit()
    cache_dir = tmp_path / "cache"
    if case == "halted":
        site = _site()
        site.set(URLS[1], httpx.Response(429))
        parent = _acquire(dsession, source, site, clock, cache_dir)
        assert parent.status == "HALTED_BY_POLICY"
    else:
        with pytest.raises(RuntimeError):
            _acquire(dsession, source, Exploding(_site(), URLS[1], RuntimeError()), clock,
                     cache_dir)
        parent = dsession.get(CrawlRun, _run_ids(dsession, source)[0])
    target_source, limits, expected = source, {}, ""
    if case == "completed":
        parent.status = "COMPLETED"
        expected = "RUN_COMPLETED"
    elif case == "halted":
        expected = "RUN_HALTED_BY_POLICY"
    elif case == "source":
        target_source, expected = make_source(dsession), "SOURCE_MISMATCH"
    elif case == "limits":
        limits, expected = {"page_cap": 10}, "LIMITS_CHANGED"
    elif case == "adapter":
        parent.adapter_key, expected = "some-adapter", "ADAPTER_MISMATCH"
    site = Exploding(_site(), "-", None)
    with pytest.raises(ResumeRefused, match=expected):
        _resume(dsession, target_source, parent, site, clock, cache_dir, **limits)
    assert site.requests == []


# --------------------------------------------------------------- adapters --


def _adapter_fetcher(site, clock):
    return HttpFetcher(limits=FetchLimits(page_cap=60), transport=httpx.MockTransport(site),
                       monotonic=clock.monotonic, sleep=clock.sleep)


def test_extraction_failure_is_durable_and_resume_extracts_once(
        dsession, world, clock, tmp_path, monkeypatch):  # noqa: F811
    source, config = world["source"], world["config"]
    dsession.commit()
    cache_dir = tmp_path / "cache"
    real = adapter_module.extract_product

    def broken(cfg, body):
        if b"EX-Beta 2" in body and b"<h1>EX-Beta 2" in body:
            raise ValueError("extractor bug")
        return real(cfg, body)

    monkeypatch.setattr(adapter_module, "extract_product", broken)
    site = FixtureSite(world["maker"])
    with pytest.raises(ValueError), _adapter_fetcher(site, clock) as fetcher:
        run_adapter(dsession, source=source, config=config, operator="Robert (test)",
                    fetcher=fetcher, cache_dir=cache_dir, now=clock.now,
                    checkpoint=dsession.commit)
    parent = dsession.get(CrawlRun, _run_ids(dsession, source)[0])
    assert parent.status == "FAILED"
    assert parent.counters["halt_reason"] == "extraction_failed: ValueError"
    assert len(_pages(dsession, parent)) == 9                      # observations kept
    assert dsession.scalar(select(func.count()).select_from(ExtractionResult).where(
        ExtractionResult.crawl_run_id == parent.id)) == 0          # partial extraction gone
    assert _candidate(dsession, source, ALPHA) is None

    monkeypatch.setattr(adapter_module, "extract_product", real)
    site.requests.clear()
    with _adapter_fetcher(site, clock) as fetcher:
        resumed = resume_adapter(dsession, parent_run_id=parent.id, source=source,
                                 config=config, operator="Robert (test)", fetcher=fetcher,
                                 cache_dir=cache_dir, now=clock.now, checkpoint=dsession.commit)
    assert site.requests == []                                     # nothing left to fetch
    assert resumed.status == "COMPLETED" and resumed.resume_of_run_id == parent.id
    assert resumed.counters["extraction"]["target_pages"] == 7
    assert dsession.scalar(select(func.count()).select_from(DiscoveryCandidate).where(
        DiscoveryCandidate.source_id == source.id)) == 5
    results = list(dsession.scalars(select(ExtractionResult).join(
        FetchedPage, FetchedPage.id == ExtractionResult.fetched_page_id).where(
        FetchedPage.source_id == source.id)))
    assert len(results) == 7 and {r.crawl_run_id for r in results} == {parent.id}  # lineage

    # Resuming a completed resume is refused; nothing is extracted twice.
    with pytest.raises(ResumeRefused, match="RUN_COMPLETED"), \
            _adapter_fetcher(site, clock) as fetcher:
        resume_adapter(dsession, parent_run_id=resumed.id, source=source, config=config,
                       operator="Robert (test)", fetcher=fetcher, cache_dir=cache_dir,
                       now=clock.now, checkpoint=dsession.commit)


def test_adapter_acquisition_failure_resumes_without_re_enumerating(
        dsession, world, clock, tmp_path):  # noqa: F811
    source, config = world["source"], world["config"]
    dsession.commit()
    cache_dir = tmp_path / "cache"
    handler = Exploding(FixtureSite(world["maker"]), BETA, RuntimeError("network stack bug"))
    with pytest.raises(RuntimeError), _adapter_fetcher(handler, clock) as fetcher:
        run_adapter(dsession, source=source, config=config, operator="Robert (test)",
                    fetcher=fetcher, cache_dir=cache_dir, now=clock.now,
                    checkpoint=dsession.commit)
    parent = dsession.get(CrawlRun, _run_ids(dsession, source)[0])
    assert parent.status == "FAILED"
    fetched_before = [p.url for p in _pages(dsession, parent)]
    assert OMEGA_NEWS in fetched_before and ALPHA in fetched_before and BETA not in fetched_before

    site = Exploding(FixtureSite(world["maker"]), "-", None)
    with _adapter_fetcher(site, clock) as fetcher:
        resumed = resume_adapter(dsession, parent_run_id=parent.id, source=source,
                                 config=config, operator="Robert (test)", fetcher=fetcher,
                                 cache_dir=cache_dir, now=clock.now, checkpoint=dsession.commit)
    # No seed re-fetch, no re-enumeration: only the parent's unfetched targets.
    assert site.targets() == [u for u in parent.run_manifest["expanded_urls"]
                              if u not in fetched_before]
    assert resumed.status == "COMPLETED"
    assert dsession.scalar(select(func.count()).select_from(DiscoveryCandidate).where(
        DiscoveryCandidate.source_id == source.id)) == 5           # same as a clean run
    urls = list(dsession.scalars(select(FetchedPage.url).where(
        FetchedPage.source_id == source.id, FetchedPage.outcome == "FETCHED")))
    assert len(urls) == len(set(urls)) == 9                        # no duplicate observation
    per_page = dsession.execute(
        select(ExtractionResult.fetched_page_id, func.count()).join(
            FetchedPage, FetchedPage.id == ExtractionResult.fetched_page_id)
        .where(FetchedPage.source_id == source.id)
        .group_by(ExtractionResult.fetched_page_id)).all()
    assert per_page and all(n == 1 for _, n in per_page)           # extracted exactly once


def test_resume_needs_a_reviewed_adapter(dsession, world, clock, tmp_path):  # noqa: F811
    config = replace(world["config"], structural_review=None)
    with pytest.raises(adapter_module.AdapterRefused), \
            _adapter_fetcher(FixtureSite(world["maker"]), clock) as fetcher:
        resume_adapter(dsession, parent_run_id=world["source"].id, source=world["source"],
                       config=config, operator="x", fetcher=fetcher, cache_dir=tmp_path)


# --------------------------------------------------------------------- CLI --


@pytest.mark.parametrize("argv", [
    ["crawl", "k", "--operator", "r", "--resume", "00000000-0000-0000-0000-000000000000",
     "--url", "https://maker.example/products/a"],
    ["crawl", "k", "--operator", "r", "--resume", "00000000-0000-0000-0000-000000000000",
     "--dry-run"],
    ["crawl", "k", "--operator", "r", "--resume", "not-a-uuid"],
    ["run", "fail", "not-a-uuid", "--by", "r", "--reason", "x"],
    ["run", "fail", "00000000-0000-0000-0000-000000000000", "--by", "r"],
])
def test_cli_resume_and_fail_argument_rules(argv):
    with pytest.raises(SystemExit):
        cli.main(argv)


def test_stale_window_default_is_thirty_minutes():
    from app.services.discovery.acquisition import STALE_RUN_AFTER
    assert STALE_RUN_AFTER == timedelta(minutes=30)
