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

from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.acquisition import CrawlRun, FetchedPage
from app.models.discovery import DiscoverySource
from app.services.discovery import DiscoveryError
from app.services.discovery import cache as body_cache
from app.services.discovery.eligibility import source_ineligibility, url_ineligibility
from app.services.discovery.fetcher import (
    RETRIEVAL_METHOD,
    USER_AGENT,
    HttpFetcher,
    KillSwitchEngaged,
)
from app.services.discovery.fingerprint import FINGERPRINT_VERSION, fingerprint, sha256_hex
from app.services.discovery.robots import RobotsRules, parse
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

#: One bounded enumeration step (docs/16 §12.1): given the seed pages this run
#: fetched and the robots rules in force, return the target URLs to fetch next.
#: Called once, after every seed; its URLs are never expanded again.
Expander = Callable[[list[tuple[FetchedPage, bytes]], RobotsRules], list[str]]

ADAPTER_KEY = "http-url-list"
ADAPTER_VERSION = "1"
#: crawl_trigger values: a named human's run, or Stage F scheduled observation.
TRIGGERS = ("MANUAL", "SCHEDULED")
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


class ResumeRefused(AcquisitionRefused):
    """A run cannot be resumed; nothing was requested and nothing was written."""


class RobotsUnavailable(Exception):
    pass


#: Refusal reason when the source already has a RUNNING run (manual or scheduled).
SOURCE_RUN_IN_PROGRESS = "SOURCE_RUN_IN_PROGRESS (another run of this source is RUNNING)"

#: Outcomes that count as "fetched successfully": resume never re-requests them.
COMPLETED_OUTCOMES = ("FETCHED", "NOT_MODIFIED")
#: A RUNNING run with no activity for this long may be marked FAILED by an operator.
STALE_RUN_AFTER = timedelta(minutes=30)


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


def _latest_fetch(session: Session, source: DiscoverySource, url: str) -> FetchedPage | None:
    return session.scalars(
        select(FetchedPage)
        .where(FetchedPage.source_id == source.id, FetchedPage.url == url,
               FetchedPage.outcome == "FETCHED")
        .order_by(FetchedPage.retrieved_at.desc())
        .limit(1)
    ).first()


def _validators(session: Session, source: DiscoverySource, url: str,
                cache_dir: Path | None = None) -> dict[str, str]:
    """Conditional-request headers from the latest successful observation.

    With `cache_dir`, they are sent only while that observation's body is still
    cached: a 304 means "what you have is current", which is useless when we no
    longer have it (a seed could not be expanded, a page not re-extracted)."""
    prior = _latest_fetch(session, source, url)
    headers: dict[str, str] = {}
    if prior is None or (cache_dir is not None
                         and not body_cache.observed_body_available(cache_dir, str(prior.id))):
        return headers
    if prior.etag:
        headers["If-None-Match"] = prior.etag
    if prior.last_modified:
        headers["If-Modified-Since"] = prior.last_modified
    return headers


def learned_canonical(session: Session, source: DiscoverySource, url: str) -> str | None:
    """The URL that actually served `url` last time, when it differs only in
    representation (normalizes to the same URL, e.g. a trailing-slash redirect).

    Requesting it directly saves the redirect hop and lets the conditional
    headers reach the resource that set them. A redirect to a different resource
    is never learned. The caller must still pass it through the source policy
    and robots.txt; if either refuses, the planned URL is requested as usual."""
    prior = _latest_fetch(session, source, url)
    if prior is None or not prior.final_url or prior.final_url == url:
        return None
    try:
        same = normalize_url(prior.final_url) == normalize_url(url)
    except UnsupportedUrl:
        return None
    return prior.final_url if same else None


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
    resume_of: CrawlRun | None = None,
    trigger: str = "MANUAL",
) -> CrawlRun:
    """One run over an explicit URL list (MANUAL, or SCHEDULED by Stage F).
    Refuses before any request if the source or any URL fails policy.
    `checkpoint` (e.g. session.commit) is called after every durable step; the
    caller owns the transaction.

    With `expand`, `urls` are the run's seeds: after the last seed, `expand` is
    called once with the fetched seed bodies and returns target URLs, which are
    re-checked against the source policy and the page cap and then fetched. The
    targets are never expanded (one level, no recursion).

    Durability: with a committing `checkpoint`, every observation is committed as
    it is recorded. An unexpected exception rolls back only the uncommitted
    remainder, then durably marks the run FAILED (KeyboardInterrupt: CANCELLED)
    before re-raising, so no run is left RUNNING by an error this process saw.
    A resume (`resume_of`) may legitimately have nothing left to fetch."""
    if not operator or not operator.strip():
        raise AcquisitionRefused([("-", "OPERATOR_REQUIRED")])
    if trigger not in TRIGGERS:
        raise AcquisitionRefused([("-", f"UNKNOWN_TRIGGER ({trigger})")])
    if urls or resume_of is None:
        _refuse_unless_planned(source, urls, fetcher.limits.page_cap)
    else:
        reason = source_ineligibility(source)
        if reason:
            raise AcquisitionRefused([("-", reason)])

    release = _guard_writes(session)
    try:
        return _run(session, source, urls, operator.strip(), fetcher, cache_dir, now,
                    checkpoint, expand, adapter, manifest_extra or {}, resume_of, trigger)
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
         expand, adapter, manifest_extra, resume_of, trigger="MANUAL") -> CrawlRun:
    counters = {
        "requested": len(urls), "attempted": 0, "fetched": 0, "not_modified": 0,
        FIRST_OBSERVATION.lower(): 0, UNCHANGED.lower(): 0, CHANGED.lower(): 0,
        SOURCE_REMOVED.lower(): 0, FETCH_ERROR.lower(): 0,
        "blocked_by_robots": 0, "blocked_by_source": 0, "redirects_refused": [],
        "not_attempted": 0, "halt_reason": None, "canonical_rows_written": 0,
        "learned_canonical_requests": [],
    }
    run = CrawlRun(
        source_id=source.id, adapter_key=adapter[0], adapter_version=adapter[1],
        trigger=trigger, operator=operator, status="RUNNING", started_at=now(),
        resume_of_run_id=resume_of.id if resume_of is not None else None,
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
    # One RUNNING run per source, enforced by the database
    # (uq_crawl_run_one_running_per_source): a concurrent manual or scheduled
    # run of the same source is refused here, before any request.
    try:
        with session.begin_nested():
            session.add(run)
            session.flush()
    except IntegrityError as exc:
        if "uq_crawl_run_one_running_per_source" not in str(exc.orig):
            raise
        raise AcquisitionRefused([("-", SOURCE_RUN_IN_PROGRESS)]) from None
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
                checkpoint()  # the expanded target list is durable before any target
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
    except KeyboardInterrupt:
        _end_durably(session, run.id, "CANCELLED", "interrupted", now, checkpoint)
        raise
    except Exception as exc:
        _end_durably(session, run.id, "FAILED", f"unexpected_error: {type(exc).__name__}",
                     now, checkpoint)
        raise
    counters["not_attempted"] = counters["requested"] - counters["attempted"]
    run.status = status
    run.finished_at = now()
    run.counters = counters
    flag_modified(run, "counters")  # mutated in place: force the JSONB write
    source.last_crawled_at = run.finished_at
    session.flush()
    checkpoint()
    return run


def observed_counters(session: Session, run: CrawlRun) -> dict:
    """The §18 counters rebuilt from the run's COMMITTED observations — used when
    the in-memory counters of an interrupted run cannot be trusted."""
    manifest = run.run_manifest or {}
    version = manifest.get("fingerprint_version", FINGERPRINT_VERSION)
    requested = len(manifest.get("requested_urls", [])) + len(manifest.get("expanded_urls", []))
    counters = {
        "requested": requested, "attempted": 0, "fetched": 0, "not_modified": 0,
        FIRST_OBSERVATION.lower(): 0, UNCHANGED.lower(): 0, CHANGED.lower(): 0,
        SOURCE_REMOVED.lower(): 0, FETCH_ERROR.lower(): 0,
        "blocked_by_robots": 0, "blocked_by_source": 0, "redirects_refused": [],
        "not_attempted": 0, "halt_reason": None, "canonical_rows_written": 0,
    }
    for page in session.scalars(select(FetchedPage).where(FetchedPage.crawl_run_id == run.id)):
        counters["attempted"] += 1
        key = {"FETCHED": "fetched", "NOT_MODIFIED": "not_modified",
               "BLOCKED_BY_ROBOTS": "blocked_by_robots",
               "BLOCKED_BY_SOURCE": "blocked_by_source"}.get(page.outcome)
        if key:
            counters[key] += 1
        state = classify(session, page, version)
        if state.lower() in counters and state not in ("BLOCKED_BY_ROBOTS", "BLOCKED_BY_SOURCE"):
            counters[state.lower()] += 1
    counters["not_attempted"] = max(requested - counters["attempted"], 0)
    return counters


def _end_durably(session, run_id, status, reason, now, checkpoint) -> None:
    """Discard the uncommitted remainder, then record how the run ended.

    Only a run that was durably written can be marked; if nothing was ever
    committed (a non-committing caller) the rollback leaves nothing behind."""
    session.rollback()
    run = session.get(CrawlRun, run_id)
    if run is None or run.status != "RUNNING":
        return
    counters = observed_counters(session, run)
    counters["halt_reason"] = reason
    run.status = status
    run.finished_at = now()
    run.counters = counters
    session.flush()
    checkpoint()


def mark_stale_run_failed(
    session: Session, run_id, *, by: str, reason: str,
    now: Callable[[], datetime] = _utcnow, stale_after: timedelta = STALE_RUN_AFTER,
) -> CrawlRun:
    """Governed recovery for a run whose process died without recording an end
    (killed, power loss): an attributed operator act, refused while the run shows
    recent activity, so a live run in another process is not cut off."""
    if not (by or "").strip() or not (reason or "").strip():
        raise DiscoveryError("--by and --reason are required")
    run = session.get(CrawlRun, run_id)
    if run is None:
        raise DiscoveryError(f"no crawl_run {run_id}")
    if run.status != "RUNNING":
        raise DiscoveryError(f"run {run_id} is {run.status}, not RUNNING")
    last = session.scalar(select(func.max(FetchedPage.retrieved_at))
                          .where(FetchedPage.crawl_run_id == run.id)) or run.started_at
    if now() - last < stale_after:
        raise DiscoveryError(
            f"run {run_id} was active at {last.isoformat()}; it is not stale yet "
            f"(needs {int(stale_after.total_seconds() // 60)} idle minutes)")
    counters = observed_counters(session, run)
    counters["halt_reason"] = f"marked_failed_by_operator: {reason.strip()}"
    run.status = "FAILED"
    run.finished_at = now()
    run.counters = counters
    run.run_manifest = {**(run.run_manifest or {}), "marked_failed_by": by.strip()}
    session.flush()
    return run


# ------------------------------------------------------------------ resume --


def _planned_urls(run: CrawlRun) -> list[str]:
    """Every URL the run intended to fetch, in order: seeds/explicit URLs, then
    expanded targets. A resumed run inherits its parent's plan."""
    manifest = run.run_manifest or {}
    if "planned_urls" in manifest:
        return list(manifest["planned_urls"])
    planned = list(manifest.get("requested_urls", []))
    planned += [u for u in manifest.get("expanded_urls", []) if u not in planned]
    return planned


def run_chain(session: Session, run: CrawlRun) -> list[CrawlRun]:
    """`run` and every run it resumes, newest first."""
    chain = [run]
    while chain[-1].resume_of_run_id is not None:
        parent = session.get(CrawlRun, chain[-1].resume_of_run_id)
        if parent is None or parent in chain:
            break
        chain.append(parent)
    return chain


def resume_plan(session: Session, parent: CrawlRun | None, source: DiscoverySource | None,
                adapter: tuple[str, str], limits: dict) -> tuple[list[str], list[str]]:
    """(remaining URLs, already-completed URLs) for resuming `parent`, or
    ResumeRefused. Pure reads; nothing is requested or written."""
    problems: list[str] = []
    if parent is None:
        raise ResumeRefused([("-", "NO_SUCH_RUN")])
    if parent.status == "RUNNING":
        problems.append("RUN_STILL_RUNNING (mark it FAILED first: discovery run fail)")
    elif parent.status == "COMPLETED":
        problems.append("RUN_COMPLETED (nothing to resume)")
    elif parent.status == "HALTED_BY_POLICY":
        problems.append("RUN_HALTED_BY_POLICY (a policy outcome is not retried)")
    child = session.scalars(select(CrawlRun.id).where(CrawlRun.resume_of_run_id == parent.id)
                            ).first()
    if child is not None:
        problems.append(f"ALREADY_RESUMED (by run {child}; resume that run instead)")
    if source is None or source.id != parent.source_id:
        problems.append("SOURCE_MISMATCH")
    if (parent.adapter_key, parent.adapter_version) != tuple(adapter):
        problems.append(f"ADAPTER_MISMATCH ({parent.adapter_key}@{parent.adapter_version})")
    manifest = parent.run_manifest or {}
    if manifest.get("fingerprint_version") != FINGERPRINT_VERSION:
        problems.append("FINGERPRINT_VERSION_CHANGED")
    if manifest.get("limits") != limits:
        problems.append("LIMITS_CHANGED (a resume honours the parent's manifest)")
    if problems:
        raise ResumeRefused([("-", p) for p in problems])
    chain_ids = [r.id for r in run_chain(session, parent)]
    done = set(session.scalars(
        select(FetchedPage.url).where(FetchedPage.crawl_run_id.in_(chain_ids),
                                      FetchedPage.outcome.in_(COMPLETED_OUTCOMES))
    ))
    planned = _planned_urls(parent)
    return [u for u in planned if u not in done], [u for u in planned if u in done]


def resume_acquisition(
    session: Session, *, parent_run_id, source: DiscoverySource | None, operator: str,
    fetcher: HttpFetcher, cache_dir: Path = body_cache.DEFAULT_CACHE_DIR,
    now: Callable[[], datetime] = _utcnow, checkpoint: Callable[[], None] = lambda: None,
) -> CrawlRun:
    """Resume a FAILED or CANCELLED plain run (docs/16 §7): a NEW run linked by
    `resume_of_run_id`, same manifest, fetching only the planned URLs the chain
    has not already fetched successfully. Committed observations are never
    re-requested, rewritten or duplicated."""
    parent = session.get(CrawlRun, parent_run_id)
    remaining, skipped = resume_plan(session, parent, source, (ADAPTER_KEY, ADAPTER_VERSION),
                                     fetcher.limits.as_manifest())
    return run_acquisition(
        session, source=source, urls=remaining, operator=operator, fetcher=fetcher,
        cache_dir=cache_dir, now=now, checkpoint=checkpoint, resume_of=parent,
        manifest_extra={"planned_urls": _planned_urls(parent),
                        "resume_skipped_completed": skipped},
    )


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

    # Stage F: request the URL that served this page last time when it differs
    # only in representation (no redirect hop; validators reach the right resource).
    # It must pass the source policy and robots like any hop; otherwise `url`.
    request_url = url
    learned = learned_canonical(session, source, url)
    if learned is not None and hop_refusal(learned) is None:
        request_url = learned
        counters["learned_canonical_requests"].append({"url": url, "requested": learned})
    result = fetcher.get_following(request_url, _validators(session, source, url, cache_dir),
                                   hop_refusal)
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
        f"adapter={run.adapter_key}@{run.adapter_version}   trigger={run.trigger}   "
        f"operator={run.operator}",
        f"started={run.started_at.isoformat()}  finished="
        f"{run.finished_at.isoformat() if run.finished_at else '-'}  status={run.status}"
        f"  resumed_from={run.resume_of_run_id or '-'}",
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
        f"Learned canonical URLs requested     "
        f"{len(counters.get('learned_canonical_requests', []))}",
        f"Not attempted                        {counters.get('not_attempted', 0)}",
        f"Halt reason                          {counters.get('halt_reason') or '-'}",
        f"Canonical rows written               {counters.get('canonical_rows_written', 0)}",
    ]
    return "\n".join(lines + _adapter_report(manifest, counters))


def _index_lines(report: dict) -> list[str]:
    """INDEX-ONLY report: seeds, what would be targeted, and why the rest is not."""
    lines = ["", "INDEX-ONLY (no target page requested; nothing extracted or written)", "SEEDS"]
    lines += [f"  {s['outcome']:<18} {s['http_status'] or '-':<4} {s['url']}"
              + (f"  -> {s['final_url']}" if s.get("final_url") not in (None, s["url"]) else "")
              for s in report.get("seeds", [])]
    lines.append("QUALIFYING URLS (cap / unseen / found in)")
    lines += [f"  {q['cap']:<9} {'unseen' if q['unseen'] else 'seen':<7} {q['url']}"
              f"  [{', '.join(q['found_in'])}]" for q in report.get("qualifying", [])]
    for key, title in (("sitemap_only", "SITEMAP-ONLY"), ("link_only", "LINK-ONLY"),
                       ("sitemap_and_links", "SITEMAP AND LINKS"),
                       ("absent_from_sitemap_but_linked", "ABSENT FROM SITEMAP BUT LINKED"),
                       ("seeds_linked", "SEEDS ALSO LINKED (extracted from the seed fetch)")):
        lines.append(f"{title} ({len(report.get(key, []))})")
        lines += [f"  {u}" for u in report.get(key, [])]
    lines.append(f"NORMALIZATION DUPLICATES ({len(report.get('normalization_duplicates', []))})")
    lines += [f"  {d['url']}  <= {d['raw']}" for d in report.get("normalization_duplicates", [])]
    lines.append(f"EXCLUDED ({len(report.get('excluded', []))})")
    lines += [f"  {e['reason']:<16} {e['url']}" for e in report.get("excluded", [])]
    lines.append("SEED PRODUCT PAGES (identity computed in memory; resolver prediction read-only)")
    for row in report.get("seed_products", []):
        predicted = row.get("predicted") or {}
        lines.append(f"  {row['status']:<14} name={row['name']!r}  "
                     f"resolver={predicted.get('identity_status', '-')}  {row['url']}")
    lines.append(f"TARGETS NOT FETCHED ({len(report.get('targets_not_fetched', []))})")
    return lines


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
    if manifest.get("index_report") is not None:
        return lines + _index_lines(manifest["index_report"])
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
