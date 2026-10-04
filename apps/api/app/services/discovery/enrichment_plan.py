"""G5-3 — the Lane B (CATALOGUE_ENRICHMENT) target-selection layer. Read-only, deterministic.

Question answered: *which existing catalogue robots should this governed manufacturer source
inspect next, and why?*

It builds, for every robot, an operational **enrichment target profile** (reusing the G4 coverage
band and the G5-1 gap profile; no second completeness system), derives the robot's known
first-party URLs from governed data, checks each against the approved host/path boundary, and turns
that into a bounded, ranked **fetch plan** per source plus an exact reason for every skipped target.

Hard boundaries (pinned by tests/test_g5_enrichment_plan.py):

- Nothing here fetches, proposes, creates candidates, claims or catalogue rows, changes publication
  or changes commercial status. A function taking a database session only SELECTs.
- Reason codes mean "worth checking", never "defective". UNKNOWN stays valid catalogue truth.
- Priority and freshness choose WHICH known targets a due source cycle looks at first. They are
  not a publication threshold and not a schedule: cadence stays the source's
  (`next_observation_at`).
- A URL outside the approved host/path boundary is reported `SOURCE_REVIEW_REQUIRED`; the
  boundary is never widened and a link is never an authorization. A robot whose manufacturer has
  no approved source gets no eligible target (`NO_APPROVED_TARGET`); nothing is fabricated.
- A known robot is never a discovery candidate: this layer has no write path at all.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.acquisition import FetchedPage
from app.models.discovery import DiscoverySource
from app.services.discovery import enrichment as en
from app.services.discovery.live_adapter import SourceAdapterConfig
from app.services.discovery.source_registry import next_observation_at
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

CATALOGUE_ENRICHMENT = en.CATALOGUE_ENRICHMENT

# ------------------------------------------------------------------------------ vocabulary

# Reason codes: "worth checking", never "defective".
COMMERCIAL_STATUS_UNKNOWN = "COMMERCIAL_STATUS_UNKNOWN"
COMMERCIAL_EVIDENCE_AGING = "COMMERCIAL_EVIDENCE_AGING"
PRICE_UNKNOWN = "PRICE_UNKNOWN"
AVAILABILITY_UNKNOWN = "AVAILABILITY_UNKNOWN"
BUYER_FIELDS_MISSING = "BUYER_FIELDS_MISSING"
NEW_DOCUMENT_POSSIBLE = "NEW_DOCUMENT_POSSIBLE"
PENDING_HIGH_VALUE_PROPOSAL = "PENDING_HIGH_VALUE_PROPOSAL"
SOURCE_CHANGED = "SOURCE_CHANGED"
REASON_CODES = (COMMERCIAL_STATUS_UNKNOWN, COMMERCIAL_EVIDENCE_AGING, PRICE_UNKNOWN,
                AVAILABILITY_UNKNOWN, BUYER_FIELDS_MISSING, NEW_DOCUMENT_POSSIBLE,
                PENDING_HIGH_VALUE_PROPOSAL, SOURCE_CHANGED)

# Target types.
PRODUCT_PAGE, DOCUMENT, NEWS, OTHER = "PRODUCT_PAGE", "DOCUMENT", "NEWS", "OTHER"
_TYPE_ORDER = {PRODUCT_PAGE: 0, DOCUMENT: 1, NEWS: 2, OTHER: 3}

# Decisions. PLANNED is the only one that may lead to a (future, governed) fetch.
PLANNED = "PLANNED"
NOT_DUE = "NOT_DUE"
UNCHANGED_RECENTLY = "UNCHANGED_RECENTLY"
SOURCE_REVIEW_REQUIRED = "SOURCE_REVIEW_REQUIRED"
NO_APPROVED_TARGET = "NO_APPROVED_TARGET"
NO_MEANINGFUL_GAP = "NO_MEANINGFUL_GAP"
DEFERRED_BY_BOUND = "DEFERRED_BY_BOUND"
SKIP_REASONS = (NOT_DUE, UNCHANGED_RECENTLY, SOURCE_REVIEW_REQUIRED, NO_APPROVED_TARGET,
                NO_MEANINGFUL_GAP, DEFERRED_BY_BOUND)

#: At most this many targets are planned per source cycle (a bounded fetch plan).
DEFAULT_BOUND = 8
#: A content change older than this is no longer a "recent change" signal.
CHANGE_WINDOW = timedelta(days=30)

_PRIORITY_ORDER = {en.HIGH: 0, en.MEDIUM: 1, en.LOW: 2}
_NEWS_SEGMENTS = frozenset({"news", "press", "newsroom", "blog", "media", "press-release",
                            "press-releases", "announcements"})
_BUYER_AREAS = ("payload", "runtime", "battery", "height", "weight", "dof", "hands_manipulation",
                "autonomy")


# ------------------------------------------------------------------------------ inputs


@dataclass(frozen=True)
class UrlState:
    """What the governed observations say about one normalized URL (read-only)."""

    last_observed: datetime | None = None      # newest retrieval that returned content
    last_hash: str | None = None
    previous_hash: str | None = None           # the content before the latest different one
    last_page_id: str | None = None            # the observation (fetched_page) it refers to

    @property
    def changed(self) -> bool:
        return (self.last_hash is not None and self.previous_hash is not None
                and self.last_hash != self.previous_hash)


@dataclass(frozen=True)
class PlanInput:
    """One robot as the planner sees it (already loaded; pure from here on)."""

    robot: en.RobotInput
    claim_urls: tuple[str, ...] = ()
    pending_kinds: tuple[str, ...] = ()


# ------------------------------------------------------------------------------ profile


@dataclass(frozen=True)
class Profile:
    """The deterministic enrichment target profile of one robot. Operational only: it is never
    canonical catalogue truth and nothing reads it as such."""

    robot_slug: str
    manufacturer_slug: str | None
    is_published: bool
    coverage_band: str
    commercial_status: str
    commercial_evidence_age_days: int | None
    missing_high_value: tuple[str, ...]
    official_url: str | None
    evidence_urls: tuple[str, ...]
    accepted_claim_urls: tuple[str, ...]
    pending_proposals: int
    last_observed: datetime | None
    priority: str
    reason_codes: tuple[str, ...]
    reason_text: tuple[str, ...]

    def as_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {
            "robot": self.robot_slug, "manufacturer": self.manufacturer_slug,
            "published": self.is_published, "coverage_band": self.coverage_band,
            "commercial_status": self.commercial_status,
            "commercial_evidence_age_days": self.commercial_evidence_age_days,
            "missing_high_value": list(self.missing_high_value),
            "official_url": self.official_url, "evidence_urls": list(self.evidence_urls),
            "accepted_claim_urls": list(self.accepted_claim_urls),
            "pending_proposals": self.pending_proposals, "last_observed": iso(self.last_observed),
            "priority": self.priority, "reason_codes": list(self.reason_codes),
            "reasons": list(self.reason_text), "origin": CATALOGUE_ENRICHMENT}


def _norm(url: str) -> str:
    try:
        return normalize_url(url)
    except UnsupportedUrl:
        return url.strip()


def reason_codes(inp: PlanInput, gaps: en.GapProfile, states: Mapping[str, UrlState],
                 now: datetime, *, document_source: bool) -> tuple[str, ...]:
    """Why this robot is worth looking at. Deterministic, fixed order (REASON_CODES)."""
    rec = inp.robot.record
    codes: set[str] = set()
    if rec.commercial_status in (None, "UNKNOWN"):
        codes.add(COMMERCIAL_STATUS_UNKNOWN)
    if gaps.areas.get("commercial_status") == en.KNOWN_BUT_OLD:
        codes.add(COMMERCIAL_EVIDENCE_AGING)
    if "price" in gaps.unknown:
        codes.add(PRICE_UNKNOWN)
    if "availability" in gaps.unknown:
        codes.add(AVAILABILITY_UNKNOWN)
    if any(a in gaps.unknown for a in _BUYER_AREAS):
        codes.add(BUYER_FIELDS_MISSING)
    known = en.collect_known_urls(inp.robot)
    if any(_type_of(u, o, document_source=False) == DOCUMENT and u not in states
           for u, o in known.items()):
        codes.add(NEW_DOCUMENT_POSSIBLE)            # a known document link never processed
    if "official_documentation" in gaps.unknown and document_source:
        codes.add(NEW_DOCUMENT_POSSIBLE)            # an approved document host may carry one
    if rec.not_yet_reviewed > 0:
        codes.add(PENDING_HIGH_VALUE_PROPOSAL)
    for url in known:
        st = states.get(url)
        if st is not None and st.changed and st.last_observed is not None \
                and now - st.last_observed <= CHANGE_WINDOW:
            codes.add(SOURCE_CHANGED)
    return tuple(c for c in REASON_CODES if c in codes)


def build_profile(inp: PlanInput, now: datetime, states: Mapping[str, UrlState], *,
                  document_source: bool = False) -> Profile:
    robot = inp.robot
    rec = robot.record
    gaps = en.gap_profile(robot, now)
    band, why = en.priority(robot, gaps, now)
    known = en.collect_known_urls(robot)
    codes = reason_codes(inp, gaps, states, now, document_source=document_source)
    # A changed official page or a never-processed document raises priority to HIGH (section 7).
    if band != en.HIGH and (SOURCE_CHANGED in codes or NEW_DOCUMENT_POSSIBLE in codes
                            and any(_type_of(u, o, document_source=False) == DOCUMENT
                                    and u not in states for u, o in known.items())):
        band, why = en.HIGH, [*why, "known page changed or known document not yet processed"]
    seen = [states[u].last_observed for u in known if u in states and states[u].last_observed]
    evidence_urls = tuple(sorted(u for u, o in known.items() if any(
        x in ("commercial_status", "pricing_offer", "availability_offer", "deployment")
        for x in o)))
    age = None
    if robot.commercial_observed_at is not None:
        age = max(0, (now - robot.commercial_observed_at).days)
    return Profile(
        rec.slug, rec.manufacturer_slug, rec.is_published, gaps.band, str(rec.commercial_status),
        age, gaps.high_value_unknown + tuple(a for a in gaps.high_value_old
                                             if a not in gaps.high_value_unknown),
        rec.official_url, evidence_urls, tuple(sorted(_norm(u) for u in inp.claim_urls)),
        rec.not_yet_reviewed, max(seen) if seen else None, band, codes, tuple(why))


# ------------------------------------------------------------------------------ targets


def _type_of(url: str, origins: Sequence[str], *, document_source: bool) -> str:
    parts = urlsplit(url)
    path = parts.path.lower()
    if path.endswith(".pdf") or document_source:
        return DOCUMENT
    segments = {s for s in path.split("/") if s}
    if segments & _NEWS_SEGMENTS:
        return NEWS
    if any(o in ("official_url", "specification", "pricing_offer", "availability_offer",
                 "commercial_status", "accepted_claim", "deployment") for o in origins):
        return PRODUCT_PAGE
    return OTHER


@dataclass(frozen=True)
class Target:
    source: str | None
    robot: str
    priority: str
    reason_codes: tuple[str, ...]
    url: str
    target_type: str
    eligibility: str                 # ALLOWED | the exclusion reason
    decision: str                    # PLANNED | a skip reason
    last_observed: datetime | None
    next_due: datetime | None
    detail: str | None = None
    origin: str = CATALOGUE_ENRICHMENT
    previous_observation: str | None = None   # fetched_page id of the last observation
    source_due: bool | None = None            # the governing source's cadence state

    def as_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {"source": self.source, "robot": self.robot, "origin": self.origin,
                "previous_observation": self.previous_observation,
                "source_due": self.source_due,
                "priority": self.priority, "reasons": list(self.reason_codes), "target": self.url,
                "target_type": self.target_type, "eligibility": self.eligibility,
                "decision": self.decision, "last_observed": iso(self.last_observed),
                "next_due": iso(self.next_due), "detail": self.detail}


@dataclass(frozen=True)
class SourcePlan:
    source_key: str
    source_due: bool
    source_next_due: datetime | None
    robots_considered: int
    planned: tuple[Target, ...]
    skipped: tuple[Target, ...]
    profiles: tuple[Profile, ...] = field(repr=False, default=())
    bound: int = DEFAULT_BOUND
    #: every target this source's boundary admits, whatever its decision (document discovery
    #: reads their already-retained bodies; nothing is fetched from this list)
    eligible: tuple[Target, ...] = field(repr=False, default=())
    #: robot slug -> every known URL (eligible or not): the "already known" set
    known_urls: Mapping[str, frozenset[str]] = field(repr=False, default_factory=dict)

    def as_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {
            "source": self.source_key, "source_due": self.source_due,
            "source_next_due": iso(self.source_next_due), "bound": self.bound,
            "robots_considered": self.robots_considered,
            "planned": [t.as_dict() for t in self.planned],
            "skipped": [t.as_dict() for t in self.skipped],
            "skipped_counts": dict(Counter(t.decision for t in self.skipped)),
            "profiles": [p.as_dict() for p in self.profiles],
            "writes": 0, "fetches": 0}


def _interval(band: str) -> timedelta:
    return en.BAND_INTERVAL[band]


def plan_manufacturer(inputs: Sequence[PlanInput], sources: Sequence[DiscoverySource],
                      states: Mapping[str, UrlState], now: datetime, *,
                      source_key: str, bound: int = DEFAULT_BOUND,
                      assume_due: bool = False) -> SourcePlan:
    """The bounded Lane B plan for ONE governed source: the targets, governed by that source's
    host/path boundary, of the catalogue robots belonging to its manufacturer.

    `inputs` are the manufacturer's robots; `sources` are all its registered sources (a website and
    its approved document host are separately governed; a URL belongs to whichever admits it)."""
    by_key = {s.key: s for s in sources}
    me = by_key[source_key]
    nxt = next_observation_at(me)
    # `assume_due` answers "what WOULD this source look at when it is due"; it changes only the
    # report, never any schedule or state.
    source_due = me.is_enabled and (assume_due or (nxt is not None and nxt <= now))
    document_source = any(s.key in en.DOCUMENT_SOURCES and en.source_status(s) == en.APPROVED
                          for s in sources)
    profiles = [build_profile(i, now, states, document_source=document_source) for i in inputs]
    profile_of = {p.robot_slug: p for p in profiles}

    planned: list[Target] = []
    skipped: list[Target] = []
    known_by_robot: dict[str, set[str]] = {}
    eligible: list[Target] = []
    for inp in sorted(inputs, key=lambda i: i.robot.record.slug):
        prof = profile_of[inp.robot.record.slug]
        robot = inp.robot
        known = en.collect_known_urls(
            en.RobotInput(robot.record, (*robot.urls, *(("accepted_claim", u)
                                                        for u in inp.claim_urls)),
                          robot.commercial_observed_at, robot.spec_observed_at,
                          robot.has_documentation, robot.announced_year))
        verdicts = en.classify_urls(known, list(sources))
        if not any(v.reason is None for v in verdicts) and not any(
                v.reason == en.NEEDS_SOURCE_APPROVAL for v in verdicts):
            skipped.append(Target(
                None, prof.robot_slug, prof.priority, prof.reason_codes, "-", OTHER,
                "NO_APPROVED_SOURCE", NO_APPROVED_TARGET, prof.last_observed, None,
                "no eligible first-party URL inside an approved source boundary"))
            continue
        for v in verdicts:
            st = states.get(v.url, UrlState())
            kind = _type_of(v.url, v.origins,
                            document_source=v.source_key in en.DOCUMENT_SOURCES)
            due_at = None if st.last_observed is None else st.last_observed + _interval(
                prof.priority)
            base = dict(robot=prof.robot_slug, priority=prof.priority,
                        reason_codes=prof.reason_codes, url=v.url, target_type=kind,
                        last_observed=st.last_observed, next_due=due_at,
                        previous_observation=st.last_page_id, source_due=bool(source_due))
            known_by_robot.setdefault(prof.robot_slug, set()).add(v.url)
            if v.reason is not None:
                if v.reason == en.NEEDS_SOURCE_APPROVAL:
                    skipped.append(Target(source=None, eligibility=v.reason,
                                          decision=SOURCE_REVIEW_REQUIRED, detail=v.detail,
                                          **base))
                continue
            if v.source_key != source_key:
                continue                      # governed by another source of this manufacturer
            eligible.append(Target(source=source_key, eligibility="ALLOWED",
                                   decision=PLANNED, **base))
            if not prof.reason_codes:
                skipped.append(Target(source=source_key, eligibility="ALLOWED",
                                      decision=NO_MEANINGFUL_GAP, **base))
            elif not source_due:
                skipped.append(Target(source=source_key, eligibility="ALLOWED",
                                      decision=NOT_DUE, detail=f"source next due "
                                      f"{nxt.isoformat() if nxt else 'never (no cadence)'}",
                                      **base))
            elif due_at is not None and due_at > now and SOURCE_CHANGED not in prof.reason_codes:
                skipped.append(Target(source=source_key, eligibility="ALLOWED",
                                      decision=UNCHANGED_RECENTLY,
                                      detail="observed within its cadence; content unchanged",
                                      **base))
            else:
                planned.append(Target(source=source_key, eligibility="ALLOWED",
                                      decision=PLANNED, **base))
    planned.sort(key=rank_key)
    kept, deferred = planned[:max(0, bound)], planned[max(0, bound):]
    skipped.extend(_replace_decision(t, DEFERRED_BY_BOUND,
                                     f"beyond this cycle's bound of {bound} targets")
                   for t in deferred)
    skipped.sort(key=lambda t: (t.decision, t.robot, t.url))
    return SourcePlan(source_key, bool(source_due), nxt, len(inputs), tuple(kept), tuple(skipped),
                      tuple(sorted(profiles, key=lambda p: (_PRIORITY_ORDER[p.priority],
                                                            p.robot_slug))), bound,
                      tuple(eligible), {k: frozenset(v) for k, v in known_by_robot.items()})


def plan_unsourced(inputs: Sequence[PlanInput], sourced_manufacturers: set[str],
                   states: Mapping[str, UrlState], now: datetime) -> tuple[list[Profile],
                                                                           list[Target]]:
    """Robots whose manufacturer has NO registered/approved source: still profiled (their gaps are
    real and may be high priority) but never given an eligible target. Nothing is fabricated; the
    only output is NO_APPROVED_TARGET, i.e. "onboard a governed source before this robot can be
    enriched"."""
    profiles, targets = [], []
    for inp in sorted(inputs, key=lambda i: i.robot.record.slug):
        if inp.robot.record.manufacturer_slug in sourced_manufacturers:
            continue
        prof = build_profile(inp, now, states)
        profiles.append(prof)
        targets.append(Target(None, prof.robot_slug, prof.priority, prof.reason_codes, "-", OTHER,
                              "NO_APPROVED_SOURCE", NO_APPROVED_TARGET, prof.last_observed, None,
                              "the manufacturer has no approved source; onboard one to enrich"))
    return profiles, targets


def rank_key(t: Target) -> tuple:
    """The one ordering of planned targets: priority, then more reasons, then never-observed first and
    otherwise longest-unobserved first (so targets deferred by the bound cannot starve), then a
    stable robot / type / URL tie-break. Tolerates a malformed target (it is refused later)."""
    seen = t.last_observed.timestamp() if t.last_observed else float("-inf")
    return (_PRIORITY_ORDER.get(t.priority, 99), -len(t.reason_codes), seen, t.robot,
            _TYPE_ORDER.get(t.target_type, 99), t.url)


def _replace_decision(t: Target, decision: str, detail: str) -> Target:
    return Target(t.source, t.robot, t.priority, t.reason_codes, t.url, t.target_type,
                  t.eligibility, decision, t.last_observed, t.next_due, detail, t.origin,
                  t.previous_observation, t.source_due)


# ------------------------------------------------------------------------------ output


def plan_lines(plan: SourcePlan) -> list[str]:
    out = [f"CATALOGUE ENRICHMENT PLAN (read-only; nothing fetched) source={plan.source_key} "
           f"due={'yes' if plan.source_due else 'no'} bound={plan.bound}",
           f"  robots considered={plan.robots_considered}  planned targets={len(plan.planned)}  "
           f"skipped={len(plan.skipped)} "
           + str(dict(sorted(Counter(t.decision for t in plan.skipped).items())))]
    for t in plan.planned:
        out += [f"  source: {t.source}", f"  robot: {t.robot}", f"  origin: {t.origin}",
                f"  priority: {t.priority}", "  reasons:",
                *(f"    - {c}" for c in t.reason_codes), f"  target: {t.url}",
                f"  target_type: {t.target_type}", f"  eligibility: {t.eligibility}",
                f"  last_observed: {t.last_observed.isoformat() if t.last_observed else 'never'}",
                f"  next_due: {t.next_due.isoformat() if t.next_due else 'now'}", ""]
    for t in plan.skipped:
        out.append(f"  SKIP {t.decision:<24}{t.robot:<30}{t.url}"
                   + (f"  ({t.detail})" if t.detail else ""))
    return out


# ------------------------------------------------------------------------------ loading


def load_url_states(session: Session) -> dict[str, UrlState]:
    """Normalized URL -> last two distinct content hashes and last retrieval. SELECT only."""
    rows = session.execute(
        select(FetchedPage.url, FetchedPage.final_url, FetchedPage.content_hash,
               FetchedPage.retrieved_at, FetchedPage.id)
        .where(FetchedPage.content_hash.is_not(None))
        .order_by(FetchedPage.retrieved_at)).all()
    hashes: dict[str, list[tuple[datetime, str, str]]] = {}
    for url, final, content_hash, when, page_id in rows:
        for u in {url, final}:
            if not u:
                continue
            try:
                key = normalize_url(u)
            except UnsupportedUrl:
                continue
            hashes.setdefault(key, []).append((when, content_hash, str(page_id)))
    states: dict[str, UrlState] = {}
    for key, seq in hashes.items():
        seq.sort(key=lambda x: x[0])
        last_when, last_hash, last_id = seq[-1]
        previous = next((h for _, h, _ in reversed(seq[:-1]) if h != last_hash), None)
        states[key] = UrlState(last_when if last_when.tzinfo else last_when.replace(tzinfo=UTC),
                               last_hash, previous, last_id)
    return states


def load_plan_inputs(session: Session) -> list[PlanInput]:
    """The G5-1 robot inputs plus accepted-claim source URLs and pending proposal kinds."""
    inputs = en.load_inputs(session)
    claim_urls: dict[str, list[str]] = {}
    for slug, url in session.execute(text(
            "SELECT DISTINCT robot_slug, source_url FROM accepted_claim")):
        if url:
            claim_urls.setdefault(slug, []).append(url)
    return [PlanInput(i, tuple(claim_urls.get(i.record.slug, ()))) for i in inputs]


def plan_unsourced_from_db(session: Session, adapters: Mapping[str, SourceAdapterConfig],
                           now: datetime | None = None) -> tuple[list[Profile], list[Target]]:
    when = (now or datetime.now(UTC)).astimezone(UTC)
    by_mfr = en.sources_by_manufacturer(session.scalars(select(DiscoverySource)).all(), adapters)
    approved = {m for m, ss in by_mfr.items() if any(en.source_status(s) == en.APPROVED
                                                     for s in ss)}
    return plan_unsourced(load_plan_inputs(session), approved, load_url_states(session), when)


def plan_source(session: Session, adapters: Mapping[str, SourceAdapterConfig], source_key: str,
                now: datetime | None = None, bound: int = DEFAULT_BOUND,
                assume_due: bool = False) -> SourcePlan:
    """The Lane B plan for one registered source from the live database. SELECT only."""
    when = (now or datetime.now(UTC)).astimezone(UTC)
    all_sources = session.scalars(select(DiscoverySource)).all()
    by_mfr = en.sources_by_manufacturer(all_sources, adapters)
    mfr = next((m for m, ss in by_mfr.items() if any(s.key == source_key for s in ss)), None)
    if mfr is None:
        raise ValueError(f"source {source_key!r} is not mapped to a manufacturer")
    inputs = [i for i in load_plan_inputs(session) if i.robot.record.manufacturer_slug == mfr]
    return plan_manufacturer(inputs, by_mfr[mfr], load_url_states(session), when,
                             source_key=source_key, bound=bound, assume_due=assume_due)


# ------------------------------------------------------------------------------ all sources


def plan_all_from_inputs(inputs: Sequence[PlanInput],
                         sources_by_mfr: Mapping[str, Sequence[DiscoverySource]],
                         states: Mapping[str, UrlState], now: datetime, *,
                         bound: int = DEFAULT_BOUND) -> dict[str, SourcePlan]:
    """The plan of EVERY registered source, each over its own manufacturer's robots. This is the
    single selection policy Lane B executes: G4 gaps + freshness + source eligibility + cadence +
    priority + bound."""
    out: dict[str, SourcePlan] = {}
    for mfr, srcs in sorted(sources_by_mfr.items()):
        robots = [i for i in inputs if i.robot.record.manufacturer_slug == mfr]
        for s in sorted(srcs, key=lambda s: s.key):
            out[s.key] = plan_manufacturer(robots, list(srcs), states, now, source_key=s.key,
                                           bound=bound)
    return out


def plan_sources(session: Session, adapters: Mapping[str, SourceAdapterConfig],
                 now: datetime | None = None, bound: int = DEFAULT_BOUND
                 ) -> tuple[dict[str, SourcePlan], dict[str, list[DiscoverySource]]]:
    """(plans by source key, sources by manufacturer) from the live database. SELECT only."""
    when = (now or datetime.now(UTC)).astimezone(UTC)
    by_mfr = en.sources_by_manufacturer(session.scalars(select(DiscoverySource)).all(), adapters)
    plans = plan_all_from_inputs(load_plan_inputs(session), by_mfr, load_url_states(session),
                                 when, bound=bound)
    return plans, by_mfr


# ------------------------------------------------------------------------------ the contract


def contract_problems(t: Target) -> list[str]:
    """Why a target is NOT a well-formed executable Lane B target. The planner produces only
    well-formed ones; the executor refuses anything else (a fabricated or hand-edited target)."""
    problems = []
    if t.origin != CATALOGUE_ENRICHMENT:
        problems.append(f"origin {t.origin!r} is not {CATALOGUE_ENRICHMENT}")
    if t.decision != PLANNED:
        problems.append(f"decision {t.decision!r} is not {PLANNED}")
    if t.eligibility != "ALLOWED":
        problems.append(f"eligibility {t.eligibility!r} is not ALLOWED")
    if not t.source:
        problems.append("no governing source")
    if not t.robot:
        problems.append("no canonical robot slug")
    if t.priority not in _PRIORITY_ORDER:
        problems.append(f"unknown priority {t.priority!r}")
    if t.target_type not in _TYPE_ORDER:
        problems.append(f"unknown target type {t.target_type!r}")
    if not t.reason_codes:
        problems.append("no reason code: nothing says why this target is worth checking")
    try:
        if normalize_url(t.url) != t.url:
            problems.append("URL is not in normalized form")
    except UnsupportedUrl:
        problems.append("URL is not an absolute http(s) URL")
    return problems


def discovered_target(plan: SourcePlan, source_key: str, robot: str, url: str,
                      found_on: str) -> Target | None:
    """A document link found in an already-retained approved page, as a planner-contract target.
    None if the robot has no profile in this plan. It still has to pass the executor's
    execution-time source-policy check like every other target."""
    prof = next((p for p in plan.profiles if p.robot_slug == robot), None)
    if prof is None:
        return None
    codes = prof.reason_codes if NEW_DOCUMENT_POSSIBLE in prof.reason_codes else tuple(
        c for c in REASON_CODES if c in {*prof.reason_codes, NEW_DOCUMENT_POSSIBLE})
    return Target(source_key, robot, prof.priority, codes, url, DOCUMENT, "ALLOWED", PLANNED,
                  None, None, f"discovered on {found_on}", source_due=plan.source_due)
