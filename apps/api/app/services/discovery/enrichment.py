"""G5-1 — the Lane B (catalogue enrichment) PLANNER. Read-only; it fetches nothing.

HumanoidOnline discovery has two complementary jobs:

    NEW_MODEL              find humanoids not yet in the catalogue (Stage E candidates)
    CATALOGUE_ENRICHMENT   revisit robots we already list and look for facts that are
                           missing, stale or newly published (G2 proposals on a robot)

This module answers, for EVERY catalogue robot, "what is missing, how urgently is it worth
looking, which first-party URLs are already known and inside an approved source boundary, and
when may it next be looked at". It is an operational queue, never a source of truth.

Reuse, not a parallel subsystem: completeness comes from the G4 machinery
(`readiness.coverage_audit` / `readiness.resolve`); URL policy is `eligibility.url_ineligibility`;
URL spelling is `urlref.normalize_url`.

Hard boundaries (pinned by tests/test_discovery_enrichment.py):

- Nothing here fetches, writes, proposes, accepts, publishes or changes maturity. A function
  in this module that takes a database session only SELECTs.
- UNKNOWN is a reason to LOOK, never a fact and never an error; it creates no proposal.
- Priority and freshness decide only scan CADENCE. They are not publication gates: a LOW
  coverage robot is publication-eligible exactly as before (`readiness.publication_check`).
- A robot whose manufacturer has no approved source is queued as NO_APPROVED_SOURCE and is
  never given a fetch. A known URL outside the approved host/path boundary is
  NEEDS_SOURCE_APPROVAL; the boundary is never widened, and a link is not an authorization.
- "Older than N days" never invalidates an accepted fact (KNOWN_BUT_OLD is a scan priority).
  REVIEW_REQUIRED needs newer observed evidence in conflict with a current fact; that needs
  fetching and is G5-2, so this planner never emits it.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.acquisition import FetchedPage
from app.models.discovery import DiscoverySource
from app.services import fact_resolution as fr
from app.services import readiness as rd
from app.services.discovery.eligibility import (
    URL_OUTSIDE_APPROVED_PATHS,
    url_ineligibility,
)
from app.services.discovery.live_adapter import SourceAdapterConfig
from app.services.discovery.urlref import UnsupportedUrl, normalize_url
from app.services.readiness import RobotRecord

# ----------------------------------------------------------------------------- vocabulary

NEW_MODEL, CATALOGUE_ENRICHMENT = "NEW_MODEL", "CATALOGUE_ENRICHMENT"

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"

#: Owner decision D2 (2026-10-04): exact minimum re-check intervals, not ranges.
BAND_INTERVAL = {HIGH: timedelta(days=7), MEDIUM: timedelta(days=21), LOW: timedelta(days=60)}
#: Owner decision D2: scan-priority thresholds only. They never touch a fact's truth.
COMMERCIAL_OLD_AFTER = timedelta(days=90)
SPEC_OLD_AFTER = timedelta(days=365)

# Freshness states of one area.
UNKNOWN_STATE, KNOWN_CURRENT, KNOWN_BUT_OLD = "UNKNOWN", "KNOWN_CURRENT", "KNOWN_BUT_OLD"
HISTORICAL, REVIEW_REQUIRED = "HISTORICAL", "REVIEW_REQUIRED"

# Approved-source status of a robot's manufacturer.
APPROVED, NO_APPROVED_SOURCE = "APPROVED", "NO_APPROVED_SOURCE"

# Why a known URL is not an eligible target.
NEEDS_SOURCE_APPROVAL, UNUSABLE_URL = "NEEDS_SOURCE_APPROVAL", "UNUSABLE_URL"

# Why a robot is not due.
DUE_NOW, NOT_DUE = "DUE_NOW", "NOT_DUE"
NO_ELIGIBLE_URL = "NO_ELIGIBLE_URL"


def lane_for_proposal(_proposal=None) -> str:
    """A G2 proposal always attaches to an EXISTING robot identity (proposals.ingest_proposals
    refuses anything else), so it is catalogue enrichment. Derived, never stored."""
    return CATALOGUE_ENRICHMENT


def lane_for_candidate(_candidate=None) -> str:
    """A Stage E discovery candidate is a possible NEW model until a human resolves it."""
    return NEW_MODEL


# ----------------------------------------------------------------------------- gap profile

#: Area -> how it is judged. Order = owner's buyer-relevance priority (WorkOrder section 4),
#: identity/revision excluded (not an enrichment gap). `high_value` marks ranks through
#: autonomy; developer interfaces and the long tail are worth seeking but never urgent alone.
@dataclass(frozen=True)
class Area:
    key: str
    kind: str          # "commercial" | "physical" | "developer" | "evidence"
    high_value: bool


AREAS: tuple[Area, ...] = (
    Area("commercial_status", "commercial", True),
    Area("availability", "commercial", True),
    Area("price", "commercial", True),
    Area("payload", "physical", True),
    Area("runtime", "physical", True),
    Area("battery", "physical", True),
    Area("height", "physical", True),
    Area("weight", "physical", True),
    Area("dof", "physical", True),
    Area("hands_manipulation", "physical", True),
    Area("autonomy", "physical", True),
    Area("sdk", "developer", False),
    Area("api", "developer", False),
    Area("ros", "developer", False),
    Area("teleoperation", "developer", False),
    Area("deployments", "evidence", False),
    Area("variants", "evidence", False),
    Area("locomotion", "physical", False),
    Area("vision", "physical", False),
    Area("language_ui", "physical", False),
    Area("official_documentation", "evidence", False),
    Area("imagery", "evidence", False),
)
_CORE = {"payload": "payload_kg", "runtime": "runtime_minutes", "battery": "battery_wh",
         "height": "height_cm", "weight": "weight_kg", "dof": "degrees_of_freedom",
         "autonomy": "autonomy", "locomotion": "mobility"}
_BOOL = {"hands_manipulation": "has_manipulation", "sdk": "has_sdk", "api": "has_api",
         "ros": "ros_support", "teleoperation": "has_teleoperation", "vision": "has_vision",
         "language_ui": "has_language_ui"}
#: Commercial maturities that mean "no longer a live product": cadence stays LOW.
HISTORICAL_STATUSES = frozenset({"DISCONTINUED"})


@dataclass(frozen=True)
class RobotInput:
    """Everything the planner needs about one robot, already loaded (pure from here on)."""

    record: RobotRecord
    #: (origin, raw URL) pairs from governed catalogue data (see KNOWN_URL_ORIGINS).
    urls: tuple[tuple[str, str], ...] = ()
    commercial_observed_at: datetime | None = None
    spec_observed_at: datetime | None = None
    has_documentation: bool = False
    announced_year: int | None = None


def _known(inp: RobotInput, area: Area, resolved: Mapping) -> bool:
    rec = inp.record
    if area.key == "commercial_status":
        return rec.commercial_status not in (None, "UNKNOWN")
    if area.key == "availability":
        return bool(rec.availability)
    if area.key == "price":
        return bool(rec.pricing)
    if area.key == "deployments":
        return bool(rec.deployments)
    if area.key == "variants":
        return bool(rec.variants)
    if area.key == "official_documentation":
        return inp.has_documentation
    if area.key == "imagery":
        return bool(rec.images)
    if area.key in _CORE:
        return rec.core.get(_CORE[area.key]) is not None
    col = _BOOL[area.key]
    fact = resolved.get(col)
    if fact is not None:
        return fact.state is not fr.State.UNKNOWN
    return rec.core.get(col) is not None


def _freshness(inp: RobotInput, area: Area, now: datetime) -> str:
    if area.kind == "commercial":
        seen, limit = inp.commercial_observed_at, COMMERCIAL_OLD_AFTER
    elif area.kind == "physical":
        seen, limit = inp.spec_observed_at, SPEC_OLD_AFTER
    else:
        return KNOWN_CURRENT   # developer/evidence presence has no age rule (D2 names two)
    if inp.record.commercial_status in HISTORICAL_STATUSES and area.kind == "commercial":
        return HISTORICAL
    # Undated knowledge cannot show it is current: it is scanned sooner, never discarded.
    return KNOWN_CURRENT if seen is not None and now - seen <= limit else KNOWN_BUT_OLD


@dataclass(frozen=True)
class GapProfile:
    slug: str
    band: str                                   # G4 coverage band: LOW | PARTIAL | GOOD
    areas: Mapping[str, str]                    # area -> UNKNOWN | KNOWN_CURRENT | ...
    unknown: tuple[str, ...]                    # in buyer-priority order
    old: tuple[str, ...]
    high_value_unknown: tuple[str, ...]
    high_value_old: tuple[str, ...]

    def reasons(self) -> list[str]:
        out = []
        if self.high_value_unknown:
            out.append("UNKNOWN high-value: " + ", ".join(self.high_value_unknown))
        rest = [a for a in self.unknown if a not in self.high_value_unknown]
        if rest:
            out.append("UNKNOWN other: " + ", ".join(rest))
        if self.old:
            out.append("KNOWN_BUT_OLD: " + ", ".join(self.old))
        return out

    def as_dict(self) -> dict:
        return {"coverage_band": self.band, "areas": dict(self.areas),
                "unknown": list(self.unknown), "known_but_old": list(self.old)}


def gap_profile(inp: RobotInput, now: datetime) -> GapProfile:
    """Machine-readable `enrichment_gap_profile`, derived from existing canonical state and
    the G4 coverage band (no second completeness system)."""
    report = rd.coverage_audit(inp.record)
    resolved = rd.resolve(inp.record)
    areas: dict[str, str] = {}
    for area in AREAS:
        areas[area.key] = (_freshness(inp, area, now) if _known(inp, area, resolved)
                           else UNKNOWN_STATE)
    hv = {a.key for a in AREAS if a.high_value}
    unknown = tuple(a.key for a in AREAS if areas[a.key] == UNKNOWN_STATE)
    old = tuple(a.key for a in AREAS if areas[a.key] == KNOWN_BUT_OLD)
    return GapProfile(inp.record.slug, report.band, areas, unknown, old,
                      tuple(a for a in unknown if a in hv), tuple(a for a in old if a in hv))


# ----------------------------------------------------------------------------- priority

def _recent(inp: RobotInput, now: datetime) -> bool:
    return inp.announced_year is not None and inp.announced_year >= now.year - 1


def priority(inp: RobotInput, gaps: GapProfile, now: datetime) -> tuple[str, list[str]]:
    """(band, reasons). Deterministic; controls CADENCE ONLY (never publication)."""
    rec = inp.record
    pending = rec.not_yet_reviewed > 0
    high: list[str] = []
    if _recent(inp, now):
        high.append("recently announced")
    if rec.is_published and gaps.band == "LOW":
        high.append("published with LOW coverage")
    if rec.commercial_status in (None, "UNKNOWN"):
        high.append("commercial status UNKNOWN")
    for a in ("availability", "commercial_status"):
        if gaps.areas.get(a) == KNOWN_BUT_OLD:
            high.append(f"{a} evidence older than 90 days")
    if pending:
        high.append("unresolved proposals pending review")
    if rec.commercial_status in HISTORICAL_STATUSES and not pending:
        return LOW, ["historical / discontinued platform"]
    if high:
        return HIGH, high
    medium: list[str] = []
    if gaps.band == "PARTIAL":
        medium.append("PARTIAL coverage")
    if "price" in gaps.unknown or any(a in gaps.unknown for a in ("sdk", "api", "ros")):
        medium.append("important commercial/developer fields UNKNOWN")
    if gaps.old:
        medium.append("evidence becoming stale")
    if medium:
        return MEDIUM, medium
    return LOW, ["stable; no recent change or high-value gap"]


def next_eligible_at(band: str, last_observation: datetime | None) -> datetime | None:
    """None = never observed (eligible immediately); else last observation + the exact
    band interval (7 / 21 / 60 days)."""
    return None if last_observation is None else last_observation + BAND_INTERVAL[band]


# ----------------------------------------------------------------------------- known URLs

#: Governed catalogue columns that name a first-party source URL (D1).
KNOWN_URL_ORIGINS = ("official_url", "specification", "pricing_offer", "availability_offer",
                     "deployment", "commercial_status", "image")


@dataclass(frozen=True)
class UrlVerdict:
    url: str            # normalized
    origins: tuple[str, ...]
    reason: str | None  # None = eligible target; else NEEDS_SOURCE_APPROVAL / UNUSABLE_URL ...
    detail: str | None = None
    source_key: str | None = None   # the approved source whose boundary admits an eligible URL

    def as_dict(self) -> dict:
        return {"url": self.url, "origins": list(self.origins), "reason": self.reason,
                "detail": self.detail, "source": self.source_key}


def collect_known_urls(inp: RobotInput) -> dict[str, tuple[str, ...]]:
    """Normalized URL -> sorted origins. Deterministic. Unusable spellings are kept under
    their raw text so they can be reported, never silently dropped."""
    raw: list[tuple[str, str]] = list(inp.urls)
    if inp.record.official_url:
        raw.append(("official_url", inp.record.official_url))
    raw.extend(("image", i.source_url) for i in inp.record.images if i.source_url)
    found: dict[str, set[str]] = {}
    for origin, url in raw:
        if not url or not url.strip():
            continue
        try:
            key = normalize_url(url)
        except UnsupportedUrl:
            key = url.strip()
        found.setdefault(key, set()).add(origin)
    return {u: tuple(sorted(o)) for u, o in sorted(found.items())}


def _as_sources(source) -> list[DiscoverySource]:
    if source is None:
        return []
    return [source] if isinstance(source, DiscoverySource) else list(source)


def classify_urls(known: Mapping[str, tuple[str, ...]], source) -> list[UrlVerdict]:
    """Eligible targets vs. excluded ones with a reason. `source` is one source, several
    (a manufacturer's website and its approved document host) or None. A URL is eligible
    when ANY approved source's host/path boundary admits it; with no approved source
    nothing is eligible. Redirect escape and robots are enforced at fetch time (G5-2): a
    verdict here is necessary, never sufficient, for a request."""
    sources = sorted(_as_sources(source), key=lambda s: s.key)
    usable = [s for s in sources if source_status(s) == APPROVED]
    out = []
    for url, origins in known.items():
        try:
            normalize_url(url)
        except UnsupportedUrl:
            out.append(UrlVerdict(url, origins, UNUSABLE_URL, "not an absolute http(s) URL"))
            continue
        if not usable:
            why = url_ineligibility(sources[0], url) if sources else None
            out.append(UrlVerdict(url, origins, NO_APPROVED_SOURCE, why))
            continue
        reasons = []
        for s in usable:
            why = url_ineligibility(s, url)
            if why is None:
                out.append(UrlVerdict(url, origins, None, source_key=s.key))
                break
            reasons.append(why)
        else:
            # a host that matches some approved source but not its paths is the closer miss
            detail = (URL_OUTSIDE_APPROVED_PATHS if URL_OUTSIDE_APPROVED_PATHS in reasons
                      else reasons[0])
            out.append(UrlVerdict(url, origins, NEEDS_SOURCE_APPROVAL, detail))
    return out


# ----------------------------------------------------------------------------- the queue

def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


#: Reviewed (code-only) mapping of an approved DOCUMENT host source to the manufacturer whose
#: documentation it carries. A document source has no radar adapter, so this is its only link to
#: a manufacturer. Adding an entry is a reviewed code change, never database data.
DOCUMENT_SOURCES: Mapping[str, str] = {"neura-documents-official": "neura-robotics"}


def sources_by_manufacturer(
    sources: Iterable[DiscoverySource],
    adapters: Mapping[str, SourceAdapterConfig],
) -> dict[str, list[DiscoverySource]]:
    """manufacturer_slug -> its registered sources, by key: the one whose reviewed adapter is
    for that manufacturer, plus any reviewed DOCUMENT_SOURCES entry. A source with neither
    names no manufacturer: not mapped."""
    out: dict[str, list[DiscoverySource]] = {}
    for s in sorted(sources, key=lambda s: s.key):
        cfg = adapters.get(s.key)
        slug = _slugify(cfg.manufacturer) if cfg is not None else DOCUMENT_SOURCES.get(s.key)
        if slug is not None:
            out.setdefault(slug, []).append(s)
    return out


def source_status(source: DiscoverySource | None) -> str:
    """APPROVED only when the source is enabled, radar-eligible and has host + prefixes."""
    if source is None:
        return NO_APPROVED_SOURCE
    if not source.is_enabled or not source.radar_eligible:
        return NO_APPROVED_SOURCE
    if not source.homepage_url or not (source.allowed_path_prefixes or ()):
        return NO_APPROVED_SOURCE
    return APPROVED


@dataclass(frozen=True)
class Target:
    """One eligible known URL with its own cadence state (G5-2 fetches `due` targets only)."""

    url: str
    source_key: str
    last_observed: datetime | None
    next_eligible: datetime | None
    due: bool

    def as_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {"url": self.url, "source": self.source_key,
                "last_observed": iso(self.last_observed),
                "next_eligible": iso(self.next_eligible), "due": self.due}


@dataclass(frozen=True)
class QueueRow:
    robot_slug: str
    manufacturer_slug: str | None
    is_published: bool
    commercial_status: str
    coverage_band: str
    gap_reasons: tuple[str, ...]
    priority: str
    priority_reasons: tuple[str, ...]
    last_observation: datetime | None
    next_eligible: datetime | None
    due: str   # DUE_NOW | NOT_DUE | NO_APPROVED_SOURCE | NO_ELIGIBLE_URL
    source_key: str | None
    source_status: str
    eligible_urls: tuple[str, ...]
    excluded_urls: tuple[UrlVerdict, ...]
    pending_proposals: int
    gaps: GapProfile = field(repr=False, default=None)  # type: ignore[assignment]
    lane: str = CATALOGUE_ENRICHMENT
    targets: tuple[Target, ...] = ()

    @property
    def fetch_planned(self) -> bool:
        """Whether a FUTURE (G5-2) fetch could be planned. G5-1 itself never fetches."""
        return self.due == DUE_NOW and bool(self.eligible_urls)

    def as_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {
            "robot_slug": self.robot_slug, "manufacturer_slug": self.manufacturer_slug,
            "is_published": self.is_published, "commercial_status": self.commercial_status,
            "coverage_band": self.coverage_band, "gap_reasons": list(self.gap_reasons),
            "priority": self.priority, "priority_reasons": list(self.priority_reasons),
            "last_observation": iso(self.last_observation),
            "next_eligible": iso(self.next_eligible), "due": self.due,
            "source": self.source_key, "source_status": self.source_status,
            "eligible_urls": list(self.eligible_urls),
            "targets": [t.as_dict() for t in self.targets],
            "excluded_urls": [v.as_dict() for v in self.excluded_urls],
            "pending_proposals": self.pending_proposals,
            "has_pending_proposals": self.pending_proposals > 0,
            "lane": self.lane, "fetch_planned": self.fetch_planned,
        }


def plan_robot(inp: RobotInput, source, last_observed, now: datetime) -> QueueRow:
    """`last_observed`: normalized URL -> last retrieval time (or one datetime for all URLs).
    Each eligible URL has its OWN next-eligible time (band interval after ITS last retrieval),
    so a newly eligible document is not held back by a recently fetched sibling page."""
    rec = inp.record
    gaps = gap_profile(inp, now)
    band, why = priority(inp, gaps, now)
    verdicts = classify_urls(collect_known_urls(inp), source)
    eligible = tuple(v.url for v in verdicts if v.reason is None)
    excluded = tuple(v for v in verdicts if v.reason is not None)
    approved = [x for x in sorted(_as_sources(source), key=lambda x: x.key)
                if source_status(x) == APPROVED]
    status = APPROVED if approved else NO_APPROVED_SOURCE

    def seen(url: str) -> datetime | None:
        return last_observed if isinstance(last_observed, datetime) else (
            (last_observed or {}).get(url))

    targets = tuple(
        Target(v.url, v.source_key, seen(v.url), nxt,
               nxt is None or nxt <= now)
        for v in verdicts if v.reason is None and status == APPROVED
        for nxt in [next_eligible_at(band, seen(v.url))])
    obs = max((t.last_observed for t in targets if t.last_observed), default=None)
    nxt_row = min((t.next_eligible for t in targets if t.next_eligible), default=None)
    if status != APPROVED:
        due = NO_APPROVED_SOURCE
    elif not eligible:
        due = NO_ELIGIBLE_URL
    else:
        due = DUE_NOW if any(t.due for t in targets) else NOT_DUE
    if due == DUE_NOW:
        nxt_row = None
    return QueueRow(
        rec.slug, rec.manufacturer_slug, rec.is_published, str(rec.commercial_status),
        gaps.band, tuple(gaps.reasons()), band, tuple(why), obs, nxt_row, due,
        next((v.source_key for v in verdicts if v.source_key),
             approved[0].key if approved else None), status,
        eligible if status == APPROVED else (), excluded, rec.not_yet_reviewed, gaps,
        targets=targets)


_BAND_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2}


def build_queue(
    inputs: Sequence[RobotInput],
    sources: Mapping[str, DiscoverySource | Sequence[DiscoverySource]],
    last_observed: Mapping[str, datetime],
    now: datetime,
) -> list[QueueRow]:
    """EVERY robot gets a row (also those with no approved source). Order: priority band,
    then due-now first, then slug: stable and reproducible. `last_observed` maps a
    NORMALIZED url to the time it was last retrieved."""
    rows = []
    for inp in inputs:
        src = sources.get(inp.record.manufacturer_slug or "")
        rows.append(plan_robot(inp, src, last_observed, now))
    rows.sort(key=lambda r: (_BAND_ORDER[r.priority], r.due != DUE_NOW, r.robot_slug))
    return rows


# ----------------------------------------------------------------------------- summary

def summarize(rows: Sequence[QueueRow]) -> dict:
    """The CATALOGUE ENRICHMENT counters. Informational: none of these gate anything."""
    bands = Counter(r.priority for r in rows)
    return {
        "catalogue_robots": len(rows),
        "robots_with_gaps": sum(1 for r in rows if r.gaps and (r.gaps.unknown or r.gaps.old)),
        "high": bands[HIGH], "medium": bands[MEDIUM], "low": bands[LOW],
        "due_now": sum(1 for r in rows if r.due == DUE_NOW),
        "not_due": sum(1 for r in rows if r.due == NOT_DUE),
        "no_approved_source": sum(1 for r in rows if r.due == NO_APPROVED_SOURCE),
        "eligible_known_urls": sum(len(r.eligible_urls) for r in rows),
        "needs_source_approval": sum(
            1 for r in rows for v in r.excluded_urls if v.reason == NEEDS_SOURCE_APPROVAL),
        "pending_proposals": sum(r.pending_proposals for r in rows),
        # Needs fetching (G5-2); present so the report shape is stable.
        "changed_no_extractor": None,
        "fetches_made": 0, "canonical_rows_written": 0,
    }


def summary_lines(summary: Mapping) -> list[str]:
    s = summary
    return [
        "CATALOGUE ENRICHMENT (Lane B planner: informational, nothing fetched)",
        f"  catalogue robots={s['catalogue_robots']}  with gaps={s['robots_with_gaps']}  "
        f"priority HIGH/MEDIUM/LOW={s['high']}/{s['medium']}/{s['low']}",
        f"  due now={s['due_now']}  not due={s['not_due']}  "
        f"no approved source={s['no_approved_source']}",
        f"  eligible known URLs={s['eligible_known_urls']}  "
        f"needs source approval={s['needs_source_approval']}  "
        f"pending proposals={s['pending_proposals']}",
        "  changed-no-extractor=n/a (needs G5-2 fetching)",
    ]


# ------------------------------------------------------------------ loading (SELECT only)

def _as_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    return None


def load_inputs(session: Session) -> list[RobotInput]:
    """Read the catalogue (G4 loader) plus URL provenance and evidence dates. SELECT only."""
    from app.services.readiness_loader import load_records

    cur = session.connection().connection.cursor()
    try:
        records = load_records(cur)
    finally:
        cur.close()
    urls: dict[str, list[tuple[str, str]]] = {}
    comm: dict[str, datetime] = {}
    spec_seen: dict[str, datetime] = {}
    docs: set[str] = set()
    years: dict[str, int | None] = {}

    for slug, year in session.execute(text("SELECT slug, announced_year FROM robot")):
        years[slug] = year
    for slug, url, observed, kind in session.execute(text(
            "SELECT r.slug, s.source_url, s.observed_at, s.source_kind "
            "FROM specification s JOIN robot r ON r.id = s.robot_id")):
        if url:
            urls.setdefault(slug, []).append(("specification", url))
            if kind == "MANUFACTURER_DOC" or urlsplit(url).path.lower().endswith(".pdf"):
                docs.add(slug)
        seen = _as_dt(observed)
        if seen is not None and (slug not in spec_seen or seen > spec_seen[slug]):
            spec_seen[slug] = seen
    evidence_sql = """
        SELECT r.slug, e.subject_type::text, e.source_url, e.observed_at
        FROM evidence_source e JOIN robot r ON
             (e.subject_type::text = 'COMMERCIAL_STATUS' AND e.subject_id = r.id)
          OR (e.subject_type::text = 'PRICING_OFFER' AND e.subject_id IN
                (SELECT id FROM pricing_offer WHERE robot_id = r.id))
          OR (e.subject_type::text = 'AVAILABILITY_OFFER' AND e.subject_id IN
                (SELECT id FROM availability_offer WHERE robot_id = r.id))
          OR (e.subject_type::text = 'DEPLOYMENT' AND e.subject_id IN
                (SELECT id FROM deployment WHERE robot_id = r.id))"""
    origin = {"COMMERCIAL_STATUS": "commercial_status", "PRICING_OFFER": "pricing_offer",
              "AVAILABILITY_OFFER": "availability_offer", "DEPLOYMENT": "deployment"}
    for slug, subject, url, observed in session.execute(text(evidence_sql)):
        if url:
            urls.setdefault(slug, []).append((origin[subject], url))
            if urlsplit(url).path.lower().endswith(".pdf"):
                docs.add(slug)
        if subject != "DEPLOYMENT":
            seen = _as_dt(observed)
            if seen is not None and (slug not in comm or seen > comm[slug]):
                comm[slug] = seen
    return [RobotInput(r, tuple(urls.get(r.slug, ())), comm.get(r.slug), spec_seen.get(r.slug),
                       r.slug in docs, years.get(r.slug)) for r in records]


def load_last_observed(session: Session) -> dict[str, datetime]:
    """Normalized URL -> newest retrieval time among observations that returned content."""
    last: dict[str, datetime] = {}
    stmt = (select(FetchedPage.url, FetchedPage.final_url, func.max(FetchedPage.retrieved_at))
            .where(FetchedPage.content_hash.is_not(None))
            .group_by(FetchedPage.url, FetchedPage.final_url))
    for url, final, when in session.execute(stmt):
        for u in {url, final}:
            if not u:
                continue
            try:
                key = normalize_url(u)
            except UnsupportedUrl:
                continue
            if when is not None and (key not in last or when > last[key]):
                last[key] = when
    return last


def plan_catalogue_with_sources(
    session: Session, adapters: Mapping[str, SourceAdapterConfig], now: datetime | None = None,
) -> tuple[list[QueueRow], dict[str, list[DiscoverySource]]]:
    """The queue plus the manufacturer -> sources map it was planned with. SELECT only."""
    when = (now or datetime.now(UTC)).astimezone(UTC)
    sources = sources_by_manufacturer(session.scalars(select(DiscoverySource)).all(), adapters)
    return build_queue(load_inputs(session), sources, load_last_observed(session), when), sources


def plan_catalogue(session: Session, adapters: Mapping[str, SourceAdapterConfig],
                   now: datetime | None = None) -> list[QueueRow]:
    """The computed enrichment queue from the live database. SELECT only."""
    return plan_catalogue_with_sources(session, adapters, now)[0]
