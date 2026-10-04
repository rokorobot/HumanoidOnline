"""G5-2 — Lane B (catalogue enrichment) controlled fetching, document discovery and reporting.

Runs after Lane A (the radar `observe` cycle) in the same scheduled invocation. It connects the
G5-1 planner's DUE targets to the EXISTING governed fetch / ingest path; it adds no network code
of its own:

    planner queue -> due eligible URLs -> run_acquisition (robots, redirect boundary, bounded GET,
    size limits, conditional GET, immutable observations, content hashes) -> registered extractor
    -> G2 proposals (digest / slot dedup) -> human review          (and stops)

What it never does (pinned by tests/test_discovery_enrichment_fetch.py): accept a proposal, write
a decision, claim, audit or catalogue row, change publication or maturity, convert UNKNOWN or a
missing statement into anything, fetch outside an approved source's host/path boundary, crawl
recursively, or fetch a document that no reviewed extractor reads.

Scope decisions, each deliberate:

- Only sources WITHOUT a radar cadence are fetched by Lane B (today: document hosts such as
  `neura-documents-official`). A cadence source's own pages are Lane A's: a Lane B run there
  would move its `last_crawled_at` and become its "latest run", disturbing Lane A's cadence and
  halt/resume rules. Its due targets are reported as `deferred_radar_source`, not fetched.
- Per-source target cap and the fetcher's own limits bound every run; the band intervals
  (7/21/60 days) decide which URL is due, never publication.
- Document DISCOVERY is one level and read-only: links in already-retained product-page bodies.
  A link is not an authorization: it becomes a target only when an approved source admits the
  URL AND a registered extractor reads exactly that document.
- NOT_RESTATED is a report only: a previously proposed slot the newest content no longer states.
  It creates no proposal, preserves every accepted claim and never turns anything UNKNOWN.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.acquisition import CrawlRun, FetchedPage
from app.models.claim_proposal import DiscoveryClaimProposal, DiscoveryProposalObservation
from app.models.discovery import DiscoverySource
from app.services.discovery import cache as body_cache
from app.services.discovery import g2_ingest
from app.services.discovery.acquisition import (
    CHANGED,
    FIRST_OBSERVATION,
    SOURCE_RUN_IN_PROGRESS,
    STALE_RUN_AFTER,
    UNCHANGED,
    AcquisitionRefused,
    _utcnow,
    classify,
    run_acquisition,
)
from app.services.discovery.eligibility import source_ineligibility
from app.services.discovery.enrichment import (
    APPROVED,
    BAND_INTERVAL,
    QueueRow,
    classify_urls,
    source_status,
)
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.proposal_review import latest_content_page_for
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

LANE_B_ADAPTER = ("g5-lane-b", "1")
MAX_TARGETS_PER_SOURCE = 20
DOCUMENT_SUFFIXES = (".pdf",)

#: Proposal kinds that state a commercial fact (price, fee, availability, terms).
_COMMERCIAL_MARKERS = ("PRICE", "FEE", "AVAILAB", "RESERVATION", "LAUNCH")

# Per-source outcomes.
FETCHED, WOULD_FETCH = "FETCHED", "WOULD_FETCH"
DEFERRED_RADAR, REFUSED, FAILED = "DEFERRED_RADAR_SOURCE", "REFUSED", "FAILED"
RUN_IN_PROGRESS, NEEDS_HUMAN, KILL_SWITCH = "RUN_IN_PROGRESS", "NEEDS_HUMAN", "KILL_SWITCH"
HALTED = "HALTED"


def is_commercial_kind(kind: str) -> bool:
    return any(m in kind.upper() for m in _COMMERCIAL_MARKERS)


@dataclass
class SourceRun:
    key: str
    status: str
    urls: list[str]
    detail: str = ""
    run_id: uuid.UUID | None = None
    counts: dict = field(default_factory=dict)
    g2: dict | None = None

    def as_dict(self) -> dict:
        return {"source": self.key, "status": self.status, "urls": self.urls,
                "detail": self.detail, "run_id": str(self.run_id) if self.run_id else None,
                "counts": self.counts, "g2": self.g2}


@dataclass
class Discovered:
    robot_slug: str
    url: str
    found_on: str
    status: str            # TARGET | ELIGIBLE_NO_EXTRACTOR | NEEDS_SOURCE_APPROVAL | ...
    source_key: str | None = None

    def as_dict(self) -> dict:
        return {"robot": self.robot_slug, "url": self.url, "found_on": self.found_on,
                "status": self.status, "source": self.source_key}


@dataclass
class LaneBResult:
    plan_only: bool
    runs: list[SourceRun] = field(default_factory=list)
    discovered: list[Discovered] = field(default_factory=list)
    changed_no_extractor: list[str] = field(default_factory=list)
    first_no_extractor: list[str] = field(default_factory=list)
    not_restated: list[dict] = field(default_factory=list)
    deferred_radar: list[str] = field(default_factory=list)
    deferred_cap: list[str] = field(default_factory=list)
    robots_with_due: int = 0
    robots_checked: int = 0
    robots_deferred_cadence: int = 0
    pages: dict = field(default_factory=lambda: {
        "changed": 0, "first_observation": 0, "unchanged": 0, "errors": 0})
    proposals_created: int = 0
    commercial_proposals: int = 0
    error: str | None = None

    @property
    def robots_no_change(self) -> int:
        return max(self.robots_checked - self.pages["changed"] - self.pages["first_observation"], 0)

    @property
    def failed(self) -> bool:
        return self.error is not None or any(r.status == FAILED for r in self.runs)

    @property
    def attention(self) -> bool:
        """A human must look: a run needing one, a G2 attention (new proposals / failures)."""
        return self.failed or any(
            r.status in (NEEDS_HUMAN, HALTED, REFUSED)
            or (r.g2 or {}).get("attention") for r in self.runs)

    def as_dict(self) -> dict:
        return {
            "plan_only": self.plan_only, "runs": [r.as_dict() for r in self.runs],
            "documents_discovered": [d.as_dict() for d in self.discovered],
            "changed_no_extractor": self.changed_no_extractor,
            "first_observation_no_extractor": self.first_no_extractor,
            "not_restated": self.not_restated,
            "deferred_radar_source": self.deferred_radar, "deferred_cap": self.deferred_cap,
            "robots_with_due_targets": self.robots_with_due,
            "robots_checked": self.robots_checked,
            "robots_deferred_by_cadence": self.robots_deferred_cadence,
            "robots_with_no_changes": self.robots_no_change, "pages": self.pages,
            "new_facts_proposed": self.proposals_created,
            "commercial_changes_proposed": self.commercial_proposals,
            "attention": self.attention, "error": self.error,
            "writes_decisions": False, "writes_claims": False, "writes_catalogue": False,
        }

    def lines(self) -> list[str]:
        mode = "would fetch" if self.plan_only else "fetched"
        out = [f"  lane B ({'PLAN: no request, no write' if self.plan_only else 'governed fetch'})"]
        if self.error:
            out.append(f"  LANE B ERROR: {self.error}")
        for r in self.runs:
            out.append(f"  - {r.key:<28} {r.status:<22} {len(r.urls)} URL(s) {r.detail}".rstrip())
        out.extend([
            f"  robots checked={self.robots_checked}  with no changes={self.robots_no_change}  "
            f"deferred by cadence={self.robots_deferred_cadence}",
            f"  pages {mode}: changed={self.pages['changed']}  "
            f"first observation={self.pages['first_observation']}  "
            f"unchanged={self.pages['unchanged']}  errors={self.pages['errors']}",
            f"  new facts proposed={self.proposals_created}  "
            f"commercial changes proposed={self.commercial_proposals}",
            f"  datasheets/docs discovered={len(self.discovered)}  "
            f"changed-no-extractor={len(self.changed_no_extractor)}  "
            f"not-restated={len(self.not_restated)}",
        ])
        if self.deferred_radar:
            out.append(f"  deferred (radar-cadence source; Lane A owns it)="
                        f"{len(self.deferred_radar)}")
        return out


# ------------------------------------------------------------------ document links

class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def document_links(body: bytes, base_url: str) -> list[str]:
    """Normalized absolute document (PDF) URLs linked from an HTML body. Pure; one level."""
    parser = _Links()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    out: set[str] = set()
    for href in parser.hrefs:
        url, _ = urldefrag(urljoin(base_url, href.strip()))
        if not urlsplit(url).path.lower().endswith(DOCUMENT_SUFFIXES):
            continue
        try:
            out.add(normalize_url(url))
        except UnsupportedUrl:
            continue
    return sorted(out)


def _is_html(page: FetchedPage) -> bool:
    return "html" in (page.content_type or "").lower()


def _registered_source(registry: Mapping[str, g2_ingest.G2Ingest], url: str) -> str | None:
    """The source key whose registered extractor reads exactly this document."""
    for key, cfg in sorted(registry.items()):
        if url in cfg.page_urls:
            return key
    return None


# ------------------------------------------------------------------ NOT_RESTATED (report only)

def not_restated(session: Session, source: DiscoverySource, cfg: g2_ingest.G2Ingest) -> list[dict]:
    """Slots proposed from an earlier version of a registered page that its NEWEST content (once
    ingested) no longer states. Read-only: no proposal, decision or deletion follows from it."""
    out: list[dict] = []
    for url in cfg.page_urls:
        page = latest_content_page_for(session, source.id, url)
        if page is None:
            continue
        sighted = set(session.scalars(
            select(DiscoveryClaimProposal.slot_key)
            .join(DiscoveryProposalObservation,
                  DiscoveryProposalObservation.proposal_id == DiscoveryClaimProposal.id)
            .where(DiscoveryProposalObservation.fetched_page_id == page.id)))
        if not sighted:
            continue        # the newest content is not ingested yet: nothing to compare
        seen = session.execute(
            select(DiscoveryClaimProposal.slot_key, DiscoveryClaimProposal.kind,
                   DiscoveryClaimProposal.evidence_locator, DiscoveryClaimProposal.edition)
            .where(DiscoveryClaimProposal.source_id == source.id,
                   DiscoveryClaimProposal.robot_slug == cfg.robot_slug,
                   # a multi-page source (XPENG) proposes from several pages: only slots
                   # proposed from THIS page can be "not restated" by it
                   DiscoveryClaimProposal.source_url == url)).all()
        gone = {}
        for slot, kind, locator, edition in seen:
            if slot not in sighted:
                gone[slot] = {"source": source.key, "url": url, "kind": kind,
                              "locator": locator, "edition": edition}
        out.extend(gone[k] for k in sorted(gone))
    return out


# ------------------------------------------------------------------ the run

def _default_fetcher(source: DiscoverySource, urls: Sequence[str],
                     kill: Callable[[], bool]) -> HttpFetcher:
    return HttpFetcher(limits=FetchLimits(page_cap=max(1, min(len(urls), MAX_TARGETS_PER_SOURCE))),
                       kill_switch=kill)


def _operator(source: DiscoverySource) -> str:
    return f"g5 lane-b scheduler (source approved by {source.eligibility_reviewed_by})"


def _latest_run(session: Session, source: DiscoverySource) -> CrawlRun | None:
    return session.scalars(
        select(CrawlRun).where(CrawlRun.source_id == source.id)
        .order_by(CrawlRun.started_at.desc(), CrawlRun.created_at.desc()).limit(1)).first()


def _discover_documents(session: Session, rows: Sequence[QueueRow],
                        manufacturer_sources: Mapping[str, Sequence[DiscoverySource]],
                        by_key: Mapping[str, DiscoverySource], registry, cache_dir: Path,
                        now: datetime, result: LaneBResult) -> dict[str, dict[str, set[str]]]:
    """Document links in already-retained pages of each robot's own approved URLs. Returns the
    new fetch targets: source key -> {url -> robot slugs}. One level; nothing is fetched here."""
    new: dict[str, dict[str, set[str]]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        known = set(row.eligible_urls) | {v.url for v in row.excluded_urls}
        for t in row.targets:
            src = by_key.get(t.source_key)
            if src is None:
                continue
            page = latest_content_page_for(session, src.id, t.url)
            if page is None or not _is_html(page):
                continue
            body = body_cache.read_observed_body(cache_dir, str(page.id))
            if body is None:
                continue
            for link in document_links(body, page.final_url or page.url):
                if link in known or (row.robot_slug, link) in seen:
                    continue
                seen.add((row.robot_slug, link))
                verdict = classify_urls({link: ("discovered",)},
                                        manufacturer_sources.get(row.manufacturer_slug or ""))[0]
                if verdict.reason is not None:
                    result.discovered.append(Discovered(row.robot_slug, link, t.url,
                                                        verdict.reason))
                    continue
                reader = _registered_source(registry, link)
                if reader is None or reader != verdict.source_key:
                    result.discovered.append(Discovered(
                        row.robot_slug, link, t.url, "ELIGIBLE_NO_EXTRACTOR", verdict.source_key))
                    continue
                prior = latest_content_page_for(session, by_key[reader].id, link)
                if prior is not None:
                    # Already observed: no longer a discovery. It follows the band cadence
                    # like any known URL (never re-fetched every cycle).
                    if prior.retrieved_at + BAND_INTERVAL[row.priority] <= now:
                        new.setdefault(reader, {}).setdefault(link, set()).add(row.robot_slug)
                    continue
                result.discovered.append(Discovered(row.robot_slug, link, t.url, "TARGET",
                                                    verdict.source_key))
                new.setdefault(reader, {}).setdefault(link, set()).add(row.robot_slug)
    return new


def run_lane_b(
    session: Session,
    rows: Sequence[QueueRow],
    manufacturer_sources: Mapping[str, Sequence[DiscoverySource]],
    *,
    plan_only: bool = False,
    cache_dir: Path = body_cache.DEFAULT_CACHE_DIR,
    now: Callable[[], datetime] = _utcnow,
    kill_switch_for: Callable[[str], Callable[[], bool]] = lambda key: (lambda: False),
    fetcher_for: Callable[..., HttpFetcher] = _default_fetcher,
    checkpoint: Callable[[], None] | None = None,
    registry: Mapping[str, g2_ingest.G2Ingest] | None = None,
) -> LaneBResult:
    """One Lane B pass. With `plan_only`: no request, no write (cached bodies are only read)."""
    reg = g2_ingest.G2_INGESTS if registry is None else registry
    commit = checkpoint or session.flush
    result = LaneBResult(plan_only=plan_only)
    by_key = {s.key: s for srcs in manufacturer_sources.values() for s in srcs}

    due: dict[str, dict[str, set[str]]] = {}
    due_slugs: set[str] = set()
    for row in rows:
        if not row.targets:
            continue
        if any(t.due for t in row.targets):
            due_slugs.add(row.robot_slug)
        else:
            result.robots_deferred_cadence += 1
        for t in row.targets:
            if t.due:
                due.setdefault(t.source_key, {}).setdefault(t.url, set()).add(row.robot_slug)
    for key, urls in _discover_documents(session, rows, manufacturer_sources, by_key, reg,
                                         cache_dir, now(), result).items():
        for url, slugs in urls.items():
            due.setdefault(key, {}).setdefault(url, set()).update(slugs)
            due_slugs.update(slugs)
    result.robots_with_due = len(due_slugs)

    checked: set[str] = set()
    for key in sorted(due):
        source = by_key[key]
        urls = sorted(due[key])
        if source.observation_interval_hours is not None:
            result.deferred_radar.extend(urls)
            result.runs.append(SourceRun(key, DEFERRED_RADAR, urls,
                                         "radar-cadence source: Lane A observes its pages"))
            continue
        if len(urls) > MAX_TARGETS_PER_SOURCE:
            result.deferred_cap.extend(urls[MAX_TARGETS_PER_SOURCE:])
            urls = urls[:MAX_TARGETS_PER_SOURCE]
        run = _run_source(session, source, urls, reg, plan_only, cache_dir, now,
                          kill_switch_for(key), fetcher_for, commit, result)
        result.runs.append(run)
        if run.status in (FETCHED, WOULD_FETCH):
            for u in urls:
                checked.update(due[key][u])
    result.robots_checked = len(checked)

    for key, cfg in sorted(reg.items()):
        if key in by_key:
            result.not_restated.extend(not_restated(session, by_key[key], cfg))
    return result


def _run_source(session, source, urls, registry, plan_only, cache_dir, now, kill, fetcher_for,
                commit, result: LaneBResult) -> SourceRun:
    if plan_only:
        return SourceRun(source.key, WOULD_FETCH, urls)
    reason = source_ineligibility(source) or (
        None if source_status(source) == APPROVED else "source is not approved")
    if reason:
        return SourceRun(source.key, REFUSED, urls, f"refused before any request: {reason}")
    if kill():
        return SourceRun(source.key, KILL_SWITCH, urls, "kill switch present; nothing requested")
    latest = _latest_run(session, source)
    if latest is not None and latest.status == "RUNNING":
        last = session.scalar(select(func.max(FetchedPage.retrieved_at))
                              .where(FetchedPage.crawl_run_id == latest.id)) or latest.started_at
        stale = now() - last >= STALE_RUN_AFTER
        return SourceRun(source.key, NEEDS_HUMAN if stale else RUN_IN_PROGRESS, urls,
                         f"run {latest.id} is {'idle' if stale else 'in progress'}")
    if latest is not None and latest.status == "HALTED_BY_POLICY":
        return SourceRun(source.key, NEEDS_HUMAN, urls,
                         f"run {latest.id} halted ({(latest.counters or {}).get('halt_reason')}); "
                         "not retried automatically (a block is a finding)")
    operator = _operator(source)
    try:
        with fetcher_for(source, urls, kill) as fetcher:
            run = run_acquisition(
                session, source=source, urls=urls, operator=operator, fetcher=fetcher,
                cache_dir=cache_dir, now=now, checkpoint=commit, adapter=LANE_B_ADAPTER,
                manifest_extra={"lane": "CATALOGUE_ENRICHMENT"}, trigger="SCHEDULED")
    except AcquisitionRefused as exc:
        session.rollback()
        if any(r == SOURCE_RUN_IN_PROGRESS for _, r in exc.problems):
            return SourceRun(source.key, RUN_IN_PROGRESS, urls, "another run started first")
        return SourceRun(source.key, REFUSED, urls, f"refused before any request: {exc}")
    except Exception as exc:  # noqa: BLE001 - one source must not stop the cycle
        session.rollback()
        return SourceRun(source.key, FAILED, urls, type(exc).__name__)

    status = FETCHED if run.status == "COMPLETED" else HALTED
    detail = "" if status == FETCHED else str((run.counters or {}).get("halt_reason") or run.status)
    out = SourceRun(source.key, status, urls, detail, run_id=run.id)
    extractor_urls = set(registry[source.key].page_urls) if source.key in registry else set()
    for page in session.scalars(select(FetchedPage).where(FetchedPage.crawl_run_id == run.id)):
        state = classify(session, page)
        if state == CHANGED:
            result.pages["changed"] += 1
        elif state == FIRST_OBSERVATION:
            result.pages["first_observation"] += 1
        elif state == UNCHANGED:
            result.pages["unchanged"] += 1
        else:
            result.pages["errors"] += 1
        if state in (CHANGED, FIRST_OBSERVATION) and page.url not in extractor_urls:
            (result.changed_no_extractor if state == CHANGED else result.first_no_extractor
             ).append(page.url)
    out.counts = {k: (run.counters or {}).get(k, 0) for k in
                  ("fetched", "not_modified", "first_observation", "changed", "unchanged",
                   "fetch_error", "blocked_by_robots", "blocked_by_source")}
    g2 = g2_ingest.ingest_for_source(session, source, cache_dir=cache_dir, operator=operator,
                                     checkpoint=commit, registry=registry)
    if g2 is not None:
        out.g2 = g2.as_dict()
        result.proposals_created += g2.proposals_created
        result.commercial_proposals += session.scalar(
            select(func.count()).select_from(DiscoveryClaimProposal).where(
                DiscoveryClaimProposal.origin_crawl_run_id == run.id,
                func.upper(DiscoveryClaimProposal.kind).op("~")(
                    "(" + "|".join(_COMMERCIAL_MARKERS) + ")"))) or 0
    return out
