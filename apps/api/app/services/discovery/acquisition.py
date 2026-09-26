"""Discovery Stage B — bounded source acquisition and change detection.

Answers exactly one question: "what did this approved source return, and has
its observable content changed?" It never decides that something is a new
robot, never extracts facts, and never writes a canonical table. A changed page
is evidence only (DATA-D1 boundary: source -> raw retrieval/evidence -> later
candidate -> validation -> human approval -> canonical).

Sequence per run:

    registered source -> acquisition eligibility (source + every URL, before
    any request) -> robots.txt (run start, re-read if older than 24 h, checked
    per URL and per redirect hop) -> bounded HTTP GET -> raw-body cache ->
    immutable fetched_page observation -> versioned fingerprint comparison ->
    run report

Writes only `crawl_run`, `fetched_page` and bookkeeping fields on
`discovery_source` (robots hash/check time, last crawl, disable on robots
disallow); a flush guard refuses anything else, which is what makes
`canonical_rows_written = 0` enforced rather than hoped.

Terms of Service currency is not consulted (owner decision DR-A4); the owner's
recorded `tos_status` is enforced through `radar_eligible`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import event, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.acquisition import CrawlRun, FetchedPage
from app.models.discovery import DiscoverySource
from app.services.discovery import DiscoveryError
from app.services.discovery import cache as body_cache
from app.services.discovery.eligibility import url_ineligibility
from app.services.discovery.fetcher import (
    RETRIEVAL_METHOD,
    USER_AGENT,
    HttpFetcher,
    KillSwitchEngaged,
)
from app.services.discovery.fingerprint import FINGERPRINT_VERSION, fingerprint, sha256_hex
from app.services.discovery.robots import RobotsRules, parse

#: One bounded enumeration step (docs/16 §12.1): given the seed pages this run
#: fetched and the robots rules in force, return the target URLs to fetch next.
#: Called once, after every seed; its URLs are never expanded again.
Expander = Callable[[list[tuple[FetchedPage, bytes]], RobotsRules], list[str]]

ADAPTER_KEY = "http-url-list"
ADAPTER_VERSION = "1"
#: docs/16 LIVE.2 — a robots evaluation older than this is re-read before use.
ROBOTS_MAX_AGE = timedelta(hours=24)

# Change classification of one observation. Reuses the freshness_result words
# (UNCHANGED / CHANGED / FETCH_ERROR / SOURCE_REMOVED) and the fetch_outcome
# words for policy blocks; FIRST_OBSERVATION is the one state neither has.
FIRST_OBSERVATION = "FIRST_OBSERVATION"
UNCHANGED = "UNCHANGED"
CHANGED = "CHANGED"
SOURCE_REMOVED = "SOURCE_REMOVED"
FETCH_ERROR = "FETCH_ERROR"

_ALLOWED_WRITES = (CrawlRun, FetchedPage, DiscoverySource)


class AcquisitionRefused(DiscoveryError):
    """Nothing was requested: the source or a URL failed acquisition policy."""

    def __init__(self, problems: list[tuple[str, str]]):
        self.problems = problems
        super().__init__("; ".join(f"{url}: {reason}" for url, reason in problems))


class CanonicalWriteRefused(DiscoveryError):
    """Acquisition attempted to write outside crawl_run/fetched_page/discovery_source."""


class RobotsUnavailable(Exception):
    pass


@dataclass
class RobotsSnapshot:
    url: str
    http_status: int | None
    sha256: str | None
    checked_at: datetime
    rules: RobotsRules

    def as_manifest(self) -> dict:
        return {"url": self.url, "http_status": self.http_status, "sha256": self.sha256,
                "checked_at": self.checked_at.isoformat(),
                "crawl_delay": self.rules.crawl_delay}


@dataclass
class RunResult:
    run: CrawlRun | None
    decisions: list[tuple[str, str]] = field(default_factory=list)  # dry-run only


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- planning --


def plan(source: DiscoverySource | None, urls: list[str], page_cap: int) -> list[tuple[str, str]]:
    """Policy verdict per URL — pure, no network, no database writes.

    Returns (url, "OK" | reason). robots.txt is not evaluated here: it is read
    at crawl (or dry-run) time, never answered from a stored decision.
    """
    if not urls:
        return [("-", "NO_URLS")]
    verdicts: list[tuple[str, str]] = []
    seen: set[str] = set()
    for url in urls:
        reason = url_ineligibility(source, url)
        if reason is None and url in seen:
            reason = "DUPLICATE_URL"
        seen.add(url)
        verdicts.append((url, reason or "OK"))
    if len(urls) > page_cap:
        verdicts.append(("-", f"PAGE_CAP_EXCEEDED ({len(urls)} > {page_cap})"))
    return verdicts


def _refuse_unless_planned(source, urls, page_cap) -> None:
    problems = [(u, r) for u, r in plan(source, urls, page_cap) if r != "OK"]
    if problems:
        raise AcquisitionRefused(problems)


# ------------------------------------------------------------------ robots --


def _robots_url(source: DiscoverySource) -> str:
    parts = urlsplit(source.homepage_url.strip())
    return f"{parts.scheme.lower()}://{parts.hostname.lower()}/robots.txt"


def read_robots(fetcher: HttpFetcher, source: DiscoverySource, now: datetime) -> RobotsSnapshot:
    """Fetch and parse robots.txt (RFC 9309 status semantics, see robots.py).

    Redirects are followed only within the same host; anything else, a 5xx or
    a transport failure means robots is unavailable, and no page is fetched.
    """
    url = _robots_url(source)
    host = urlsplit(url).hostname

    def same_host(target: str) -> str | None:
        return None if (urlsplit(target).hostname or "").lower() == host else "ROBOTS_OFF_HOST"

    result = fetcher.get_following(url, None, same_host)
    response = result.response
    if result.refused or result.too_many_redirects or response.status is None:
        raise RobotsUnavailable(result.refused[1] if result.refused else
                                "too_many_redirects" if result.too_many_redirects
                                else response.error_class or "unreachable")
    status = response.status
    if 200 <= status < 300 and response.body is not None:
        return RobotsSnapshot(result.final_url, status, sha256_hex(response.body), now,
                              parse(response.body.decode("utf-8", errors="replace")))
    if 200 <= status < 300:  # 2xx but body over cap: cannot evaluate
        raise RobotsUnavailable(response.error_class or "unreadable")
    if status in (401, 403):
        return RobotsSnapshot(result.final_url, status, None, now, RobotsRules(disallow_all=True))
    if 400 <= status < 500:
        return RobotsSnapshot(result.final_url, status, None, now, RobotsRules())
    raise RobotsUnavailable(f"http_{status}")


# ----------------------------------------------------------- classification --


def _latest_earlier_fetch(session: Session, page: FetchedPage, version: str) -> FetchedPage | None:
    return session.scalars(
        select(FetchedPage)
        .join(CrawlRun, CrawlRun.id == FetchedPage.crawl_run_id)
        .where(
            FetchedPage.source_id == page.source_id,
            FetchedPage.url == page.url,
            FetchedPage.outcome == "FETCHED",
            FetchedPage.content_hash.is_not(None),
            FetchedPage.retrieved_at < page.retrieved_at,
            FetchedPage.id != page.id,
            CrawlRun.run_manifest["fingerprint_version"].astext == version,
        )
        .order_by(FetchedPage.retrieved_at.desc())
        .limit(1)
    ).first()


def classify(session: Session, page: FetchedPage, version: str = FINGERPRINT_VERSION) -> str:
    """Deterministic change state of one observation, derived from history.

    Only observations fingerprinted with the same FINGERPRINT_VERSION are
    compared, so a normalization change never reads as a page change.
    """
    if page.outcome == "FETCHED":
        prior = _latest_earlier_fetch(session, page, version)
        if prior is None:
            return FIRST_OBSERVATION
        return UNCHANGED if prior.content_hash == page.content_hash else CHANGED
    if page.outcome == "NOT_MODIFIED":
        return UNCHANGED
    if page.outcome == "ERROR" and page.http_status in (404, 410):
        return SOURCE_REMOVED
    if page.outcome == "ERROR":
        return FETCH_ERROR
    return page.outcome  # BLOCKED_BY_ROBOTS / BLOCKED_BY_SOURCE


def _validators(session: Session, source: DiscoverySource, url: str) -> dict[str, str]:
    prior = session.scalars(
        select(FetchedPage)
        .where(FetchedPage.source_id == source.id, FetchedPage.url == url,
               FetchedPage.outcome == "FETCHED")
        .order_by(FetchedPage.retrieved_at.desc())
        .limit(1)
    ).first()
    headers: dict[str, str] = {}
    if prior is not None and prior.etag:
        headers["If-None-Match"] = prior.etag
    if prior is not None and prior.last_modified:
        headers["If-Modified-Since"] = prior.last_modified
    return headers


# -------------------------------------------------------------------- run --


def _guard_writes(session: Session):
    def before_flush(sess, _ctx, _instances):
        for obj in (*sess.new, *sess.dirty, *sess.deleted):
            if not isinstance(obj, _ALLOWED_WRITES):
                raise CanonicalWriteRefused(
                    f"acquisition may not write {type(obj).__name__} (LIVE.5)"
                )
    event.listen(session, "before_flush", before_flush)
    return lambda: event.remove(session, "before_flush", before_flush)


def dry_run(
    source: DiscoverySource, urls: list[str], fetcher: HttpFetcher, *,
    now: Callable[[], datetime] = _utcnow,
) -> RunResult:
    """Policy + robots.txt only: one robots request, no target page, no DB write."""
    _refuse_unless_planned(source, urls, fetcher.limits.page_cap)
    try:
        robots = read_robots(fetcher, source, now())
    except RobotsUnavailable as exc:
        return RunResult(None, [(u, f"WOULD_NOT_FETCH: robots unavailable ({exc})") for u in urls])
    return RunResult(None, [
        (u, "WOULD_FETCH" if robots.rules.allows(u) else "WOULD_NOT_FETCH: robots disallow")
        for u in urls
    ])


def run_acquisition(
    session: Session,
    *,
    source: DiscoverySource,
    urls: list[str],
    operator: str,
    fetcher: HttpFetcher,
    cache_dir: Path = body_cache.DEFAULT_CACHE_DIR,
    now: Callable[[], datetime] = _utcnow,
    checkpoint: Callable[[], None] = lambda: None,
    expand: Expander | None = None,
    adapter: tuple[str, str] = (ADAPTER_KEY, ADAPTER_VERSION),
    manifest_extra: dict | None = None,
) -> CrawlRun:
    """One MANUAL run over an explicit URL list. Refuses before any request if
    the source or any URL fails policy. `checkpoint` (e.g. session.commit) is
    called after every durable step; the caller owns the transaction.

    With `expand`, `urls` are the run's seeds: after the last seed, `expand` is
    called once with the fetched seed bodies and returns target URLs, which are
    re-checked against the source policy and the page cap and then fetched. The
    targets are never expanded (one level, no recursion)."""
    if not operator or not operator.strip():
        raise AcquisitionRefused([("-", "OPERATOR_REQUIRED")])
    _refuse_unless_planned(source, urls, fetcher.limits.page_cap)

    release = _guard_writes(session)
    try:
        return _run(session, source, urls, operator.strip(), fetcher, cache_dir, now,
                    checkpoint, expand, adapter, manifest_extra or {})
    finally:
        release()


def _prior_body(session: Session, source: DiscoverySource, url: str,
                cache_dir: Path) -> bytes | None:
    """The cached body of the latest FETCHED observation of `url` (for a 304 seed)."""
    prior = session.scalars(
        select(FetchedPage)
        .where(FetchedPage.source_id == source.id, FetchedPage.url == url,
               FetchedPage.outcome == "FETCHED")
        .order_by(FetchedPage.retrieved_at.desc())
        .limit(1)
    ).first()
    return body_cache.read_observed_body(cache_dir, str(prior.id)) if prior else None


def _run(session, source, urls, operator, fetcher, cache_dir, now, checkpoint,
         expand, adapter, manifest_extra) -> CrawlRun:
    counters = {
        "requested": len(urls), "attempted": 0, "fetched": 0, "not_modified": 0,
        FIRST_OBSERVATION.lower(): 0, UNCHANGED.lower(): 0, CHANGED.lower(): 0,
        SOURCE_REMOVED.lower(): 0, FETCH_ERROR.lower(): 0,
        "blocked_by_robots": 0, "blocked_by_source": 0, "redirects_refused": [],
        "not_attempted": 0, "halt_reason": None, "canonical_rows_written": 0,
    }
    run = CrawlRun(
        source_id=source.id, adapter_key=adapter[0], adapter_version=adapter[1],
        trigger="MANUAL", operator=operator, status="RUNNING", started_at=now(),
        run_manifest={
            "source_key": source.key,
            "requested_urls": list(urls),
            "retrieval_method": RETRIEVAL_METHOD,
            "user_agent": USER_AGENT,
            "limits": fetcher.limits.as_manifest(),
            "fingerprint_version": FINGERPRINT_VERSION,
            "cache_dir": str(cache_dir),
            "dry_run": False,
            "robots": [],
            **manifest_extra,
        },
        counters=counters,
    )
    session.add(run)
    session.flush()
    checkpoint()

    status = "COMPLETED"
    robots: RobotsSnapshot | None = None
    remaining = list(urls)
    seeds: list[tuple[FetchedPage, bytes]] = []
    expanded = expand is None
    host = (urlsplit(source.homepage_url or "").hostname or "").lower()
    try:
        while remaining or not expanded:
            if not remaining:
                expanded = True
                targets = _expansion(source, expand(seeds, robots.rules) if robots else [],
                                     urls, fetcher.limits.page_cap, run)
                counters["requested"] += len(targets)
                remaining = list(targets)
                continue
            url = remaining[0]
            if robots is None or now() - robots.checked_at > ROBOTS_MAX_AGE:
                try:
                    robots = read_robots(fetcher, source, now())
                except RobotsUnavailable as exc:
                    counters["halt_reason"] = f"robots_unavailable: {exc}"
                    status = "HALTED_BY_POLICY"
                    break
                run.run_manifest = {**run.run_manifest,
                                    "robots": [*run.run_manifest["robots"], robots.as_manifest()]}
                source.last_robots_hash = robots.sha256
                source.last_robots_checked_at = robots.checked_at
                interval = fetcher.honour_crawl_delay(host, robots.rules.crawl_delay)
                run.run_manifest = {**run.run_manifest,
                                    "effective_min_interval_seconds": interval}

            remaining.pop(0)
            counters["attempted"] += 1
            page, halt, raw_sha256 = _acquire_one(session, run, source, url, robots,
                                                  fetcher, cache_dir, now, counters)
            session.flush()
            state = classify(session, page)
            if state in (FIRST_OBSERVATION, UNCHANGED, CHANGED, SOURCE_REMOVED, FETCH_ERROR):
                counters[state.lower()] += 1
            if page.outcome == "FETCHED":
                body_cache.record_observation(cache_dir, str(page.id), {
                    **page_cache_meta(page), "raw_sha256": raw_sha256, "change": state,
                    "fingerprint_version": FINGERPRINT_VERSION,
                })
            if not expanded:
                body = (body_cache.read_body(cache_dir, raw_sha256) if raw_sha256
                        else _prior_body(session, source, url, cache_dir)
                        if page.outcome == "NOT_MODIFIED" else None)
                if body is not None:
                    seeds.append((page, body))
            checkpoint()
            if halt:
                counters["halt_reason"] = halt
                status = "HALTED_BY_POLICY"
                if page.outcome == "BLOCKED_BY_ROBOTS":
                    # docs/16 Gate B: a robots disallow disables the source
                    # pending re-review. Robots, not ToS (DR-A4).
                    source.is_enabled = False
                break
    except KillSwitchEngaged:
        status = "CANCELLED"
        counters["halt_reason"] = "kill_switch"
    counters["not_attempted"] = counters["requested"] - counters["attempted"]
    run.status = status
    run.finished_at = now()
    run.counters = counters
    flag_modified(run, "counters")  # mutated in place: force the JSONB write
    source.last_crawled_at = run.finished_at
    session.flush()
    checkpoint()
    return run


def _expansion(source, targets, seeds, page_cap, run) -> list[str]:
    """Re-check expanded targets against the source policy and the run's page
    cap. Nothing is dropped silently: refused and over-cap URLs are recorded."""
    accepted: list[str] = []
    refused: list[dict] = []
    over_cap: list[str] = []
    room = page_cap - len(seeds)
    for url in targets:
        reason = url_ineligibility(source, url)
        if reason is None and (url in seeds or url in accepted):
            reason = "DUPLICATE_URL"
        if reason:
            refused.append({"url": url, "reason": reason})
        elif len(accepted) >= room:
            over_cap.append(url)
        else:
            accepted.append(url)
    run.run_manifest = {**run.run_manifest, "expanded_urls": list(accepted),
                        "expansion_refused": refused, "expansion_over_page_cap": over_cap}
    return accepted


def page_cache_meta(page: FetchedPage) -> dict:
    return {
        "fetched_page_id": str(page.id), "crawl_run_id": str(page.crawl_run_id),
        "url": page.url, "final_url": page.final_url,
        "retrieved_at": page.retrieved_at.isoformat(), "content_hash": page.content_hash,
    }


def _acquire_one(session, run, source, url, robots, fetcher, cache_dir, now, counters):
    """Fetch one URL and record exactly one immutable observation.

    Returns (page, halt_reason | None, raw_sha256 | None).
    """
    page = FetchedPage(crawl_run_id=run.id, source_id=source.id, url=url)

    if not robots.rules.allows(url):
        page.outcome, page.robots_decision_at_fetch = "BLOCKED_BY_ROBOTS", "DISALLOWED"
        page.retrieved_at = now()
        counters["blocked_by_robots"] += 1
        session.add(page)
        return page, "robots_disallow", None

    def hop_refusal(target: str) -> str | None:
        reason = url_ineligibility(source, target)
        if reason:
            return reason
        return None if robots.rules.allows(target) else "ROBOTS_DISALLOW"

    result = fetcher.get_following(url, _validators(session, source, url), hop_refusal)
    response = result.response
    page.retrieved_at = now()
    page.retrieval_method = RETRIEVAL_METHOD
    page.final_url = result.final_url
    page.robots_decision_at_fetch = "ALLOWED"
    page.http_status = response.status
    page.content_type = response.headers.get("content-type")
    page.etag = response.headers.get("etag")
    page.last_modified = response.headers.get("last-modified")
    session.add(page)
    halt = raw_sha256 = None

    if result.refused:
        target, reason = result.refused
        counters["redirects_refused"].append({"url": url, "location": target, "reason": reason})
        if reason == "ROBOTS_DISALLOW":
            page.outcome, page.error_class = "BLOCKED_BY_ROBOTS", "redirect_robots_disallow"
            page.robots_decision_at_fetch = "DISALLOWED"
            counters["blocked_by_robots"] += 1
            return page, "robots_disallow", None
        page.outcome, page.error_class = "ERROR", f"redirect_outside_policy:{reason}"
        return page, None, None
    if result.too_many_redirects:
        page.outcome, page.error_class = "ERROR", "too_many_redirects"
        return page, None, None
    if response.error_class in ("transport", "timeout"):
        page.outcome, page.error_class = "ERROR", response.error_class
        return page, None, None

    status = response.status
    if status == 304:
        page.outcome = "NOT_MODIFIED"
        counters["not_modified"] += 1
    elif status in (401, 403, 429):
        # docs/16 §13 / LIVE.3: a block is a finding — record it and stop.
        page.outcome, page.error_class = "BLOCKED_BY_SOURCE", f"http_{status}"
        counters["blocked_by_source"] += 1
        halt = f"blocked_by_source_http_{status}"
    elif 200 <= status < 300 and response.error_class == "body_too_large":
        page.outcome, page.error_class = "ERROR", "body_too_large"
    elif 200 <= status < 300:
        body = response.body or b""
        page.outcome = "FETCHED"
        page.content_length = len(body)
        page.content_hash = fingerprint(body, page.content_type)
        raw_sha256 = body_cache.store_body(cache_dir, body)
        counters["fetched"] += 1
    elif status in (404, 410):
        page.outcome, page.error_class = "ERROR", "gone"
    else:
        page.outcome, page.error_class = "ERROR", "status"
    return page, halt, raw_sha256


# ------------------------------------------------------------------ report --


def build_report(session: Session, run_id) -> str:
    """The run report, reproducible from the database at any time (docs/16 §18)."""
    run = session.get(CrawlRun, run_id)
    if run is None:
        raise DiscoveryError(f"no crawl_run {run_id}")
    manifest, counters = run.run_manifest or {}, run.counters or {}
    version = manifest.get("fingerprint_version", FINGERPRINT_VERSION)
    pages = session.scalars(
        select(FetchedPage).where(FetchedPage.crawl_run_id == run.id)
        .order_by(FetchedPage.retrieved_at, FetchedPage.url)
    ).all()
    lines = [
        f"RUN {run.id}   source={manifest.get('source_key')}   "
        f"adapter={run.adapter_key}@{run.adapter_version}   operator={run.operator}",
        f"started={run.started_at.isoformat()}  finished="
        f"{run.finished_at.isoformat() if run.finished_at else '-'}  status={run.status}",
        f"user-agent={manifest.get('user_agent')}   method={manifest.get('retrieval_method')}",
        f"limits={manifest.get('limits')}   fingerprint={version}",
        f"robots={manifest.get('robots')}",
        "",
    ]
    for page in pages:
        lines.append(
            f"  {classify(session, page, version):<18} {page.outcome:<18} "
            f"{page.http_status if page.http_status is not None else '-':<4} {page.url}"
            + (f"  -> {page.final_url}" if page.final_url and page.final_url != page.url else "")
            + (f"  [{page.error_class}]" if page.error_class else "")
        )
    lines += [
        "",
        f"URLs requested                       {counters.get('requested', 0)}",
        f"URLs attempted                       {counters.get('attempted', 0)}",
        f"First observations                   {counters.get('first_observation', 0)}",
        f"Unchanged (incl. 304)                {counters.get('unchanged', 0)}",
        f"Changed                              {counters.get('changed', 0)}",
        f"Source removed (404/410)             {counters.get('source_removed', 0)}",
        f"Fetch errors                         {counters.get('fetch_error', 0)}",
        f"Blocked by robots / by source        {counters.get('blocked_by_robots', 0)}"
        f" / {counters.get('blocked_by_source', 0)}",
        f"Redirects refused                    {len(counters.get('redirects_refused', []))}",
        f"Not attempted                        {counters.get('not_attempted', 0)}",
        f"Halt reason                          {counters.get('halt_reason') or '-'}",
        f"Canonical rows written               {counters.get('canonical_rows_written', 0)}",
    ]
    return "\n".join(lines + _adapter_report(manifest, counters))


def _adapter_report(manifest: dict, counters: dict) -> list[str]:
    """The Slice B additions to the §18 report: enumeration and extraction."""
    extraction = counters.get("extraction")
    enumeration = manifest.get("enumeration")
    if extraction is None and enumeration is None:
        return []
    lines = ["", "ENUMERATION (one level from reviewed seeds)"]
    enumeration = enumeration or {}
    lines.append(f"  targets selected {len(enumeration.get('selected', []))}   "
                 f"cap={manifest.get('target_cap')}   "
                 f"deferred {len(enumeration.get('deferred', []))}   "
                 f"excluded {len(enumeration.get('excluded', []))}")
    lines += [f"  DEFERRED (not fetched this run)  {u}" for u in enumeration.get("deferred", [])]
    lines += [f"  EXCLUDED {e['reason']:<16} {e['url']}" for e in enumeration.get("excluded", [])]
    if extraction is None:
        return lines
    lines += ["", "EXTRACTION"]
    lines += [f"  {p['change']:<18} {p['kind'] or '-':<12} {p['url']}  -> {p['result']}"
              for p in counters.get("extraction_pages", [])]
    changes = extraction.get("commercial_status_changes", {})
    rows = [
        ("New product URLs", "new_product_urls"),
        ("Existing robots matched", "matched_existing"),
        ("  of which known robot at a new URL", "known_robot_new_url"),
        ("New robot candidates (NEW_ENTITY)", "new_entity"),
        ("Possible duplicates", "possible_duplicate"),
        ("Ambiguous identity", "ambiguous"),
        ("Terminal candidates observed", "terminal_candidate_observed"),
        ("Identity string changed", "identity_changed"),
        ("Changed pages (re-extracted)", "changed_pages"),
        ("Unchanged, not re-extracted", "unchanged_not_reextracted"),
        ("Removed pages", "removed_pages"),
        ("Changed specifications", "changed_specifications"),
        ("Price or quote signals", "price_or_quote_signals"),
        ("Price changes", "price_changes"),
        ("Newly orderable / preorder", "newly_orderable"),
        ("Real image references found", "image_refs"),
        ("Claims written (all NOT_VERIFIED)", "claims_written"),
        ("Signals written (all NOT_VERIFIED)", "signals_written"),
        ("Rejected or unsupported values", "rejected_or_unsupported"),
        ("New announcement URLs", "new_announcement_urls"),
        ("Changed announcements", "announcements_changed"),
        ("Candidates from announcements", "announcement_candidates"),
        ("Extraction errors", "extraction_errors"),
    ]
    lines += [f"{label:<37}{extraction.get(key, 0)}" for label, key in rows]
    lines.append(f"{'Commercial-status changes':<37}maturity {changes.get('MATURITY', 0)} / "
                 f"obtainability {changes.get('OBTAINABILITY', 0)} / "
                 f"price {changes.get('PRICE', 0)}")
    lines.append(f"{'Canonical rows written':<37}{extraction.get('canonical_rows_written', 0)}")
    return lines
