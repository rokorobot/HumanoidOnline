"""Pure regional availability read model (ADR-027 §4–§9, §12).

`build_regional_availability` turns a materialized catalogue snapshot into the
numbers, tables and answer text a Regional Research Resource shows. It performs
no I/O, reads no clock and uses no randomness: identical input gives identical
output.

Rules pinned here (all from ADR-027):

* Population is **published robots only**. Unpublished robots are dropped on
  entry and never appear in any output.
* A region is a *membership set*: the requested region plus every descendant in
  the region tree. `GLOBAL` is never a member, so a GLOBAL offer is never
  regional availability (it is reported as `GLOBAL_ONLY`).
* An offer **qualifies** only if it is region-specific, current, evidence-linked,
  fresh (latest evidence date within `freshness_days` of the snapshot date) and
  its status is obtainable. A price row alone never qualifies.
* A missing offer is never `NOT_AVAILABLE`: robots without a qualifying offer are
  grouped by *why* (no evidence on file), and the answer text says "no confirmed
  offer on file", never "not available".
* UNKNOWN stays UNKNOWN: a missing/NULL price is `NOT_PUBLISHED`; `QUOTE_ONLY`
  is `PRICE_ON_REQUEST`; manufacturer/HumanoidOnline estimates are `ESTIMATE`
  and are never counted as a published price. Nothing defaults to 0.
* Confidence is never upgraded: an offer reports the weakest confidence among its
  in-window evidence, and `human_verified` is true only when every in-window row
  carries `verified_at`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .inputs import (
    EvidenceRow,
    OfferRow,
    PriceRow,
    RegionalSnapshot,
    RegionNode,
    RobotRow,
)

GLOBAL_CODE = "GLOBAL"
DEFAULT_FRESHNESS_DAYS = 90
DEFAULT_MIN_ROBOTS = 5
DEFAULT_MIN_MANUFACTURERS = 3

OBTAINABLE = frozenset({"AVAILABLE", "LIMITED", "PREORDER", "WAITLIST", "ON_REQUEST"})
NOT_OBTAINABLE = frozenset({"NOT_AVAILABLE", "DISCONTINUED"})
PUBLISHED_PRICE_TYPES = frozenset({"PUBLIC", "FROM", "RANGE"})
ESTIMATE_PRICE_TYPES = frozenset({"ESTIMATED", "MANUFACTURER_ESTIMATE"})
_CONFIDENCE_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "VERIFIED": 3}

# Mutually exclusive classification of every published robot, highest first.
QUALIFYING = "QUALIFYING"
CONFIRMED_NOT_OBTAINABLE = "CONFIRMED_NOT_OBTAINABLE"
STALE_OR_NON_CURRENT = "STALE_OR_NON_CURRENT"
OFFER_WITHOUT_EVIDENCE = "OFFER_WITHOUT_EVIDENCE"
UNRESOLVED_REGION = "UNRESOLVED_REGION"
PRICE_ONLY = "PRICE_ONLY"
GLOBAL_ONLY = "GLOBAL_ONLY"
OTHER_REGION_ONLY = "OTHER_REGION_ONLY"
NO_OFFERS = "NO_OFFERS"
GROUP_ORDER = (
    QUALIFYING, CONFIRMED_NOT_OBTAINABLE, STALE_OR_NON_CURRENT,
    OFFER_WITHOUT_EVIDENCE, UNRESOLVED_REGION, PRICE_ONLY, GLOBAL_ONLY,
    OTHER_REGION_ONLY, NO_OFFERS,
)

# Best-status ordering for the purchase sentence of the answer block.
_PURCHASE_STATUS_ORDER = ("AVAILABLE", "LIMITED", "PREORDER", "WAITLIST", "ON_REQUEST")


@dataclass(frozen=True)
class PriceState:
    kind: str                       # PUBLISHED | PRICE_ON_REQUEST | ESTIMATE | NOT_PUBLISHED
    price_type: str | None = None
    amount: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    currency: str | None = None
    billing_period: str | None = None
    price_basis: str | None = None


@dataclass(frozen=True)
class QualifyingOffer:
    robot_slug: str
    robot_name: str
    manufacturer_slug: str
    manufacturer_name: str
    provider_slug: str | None
    provider_type: str | None
    region_code: str
    transaction_type: str
    availability_status: str
    evidence_date: date
    confidence: str                 # weakest in-window confidence; never upgraded
    human_verified: bool            # every in-window evidence row has verified_at
    source_urls: tuple[str, ...]
    prices: tuple[PriceState, ...]


@dataclass(frozen=True)
class RegionalDeployment:
    """Evidenced use in the region. Separate from purchasability: a deployment
    never makes a robot a qualifying offer, and carries no freshness window
    (it records something that happened)."""

    robot_slug: str
    robot_name: str
    manufacturer_slug: str
    manufacturer_name: str
    region_code: str
    customer_name: str | None       # None = undisclosed
    provider_slug: str | None
    transaction_type: str | None
    unit_count: int | None
    started_on: date | None
    status: str | None
    evidence_date: date
    confidence: str                 # weakest confidence; never upgraded
    human_verified: bool
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class RobotRef:
    slug: str
    name: str
    manufacturer_slug: str


@dataclass(frozen=True)
class GroupSummary:
    reason: str
    robots: tuple[RobotRef, ...]

    @property
    def count(self) -> int:
        return len(self.robots)


@dataclass(frozen=True)
class GateResult:
    passes: bool
    qualifying_robots: int
    qualifying_manufacturers: int
    min_robots: int
    min_manufacturers: int
    failures: tuple[str, ...]


@dataclass(frozen=True)
class KeyFigures:
    population: int
    qualifying_robots: int
    qualifying_manufacturers: int
    no_confirmed_offer: int
    purchase_robots: int
    purchase_by_best_status: tuple[tuple[str, int], ...]      # AVAILABLE→ON_REQUEST, zeros kept
    robots_by_other_transaction: tuple[tuple[str, int], ...]  # non-PURCHASE types, sorted
    purchase_robots_with_published_price: int
    purchase_robots_price_on_request: int
    purchase_robots_price_not_published: int


@dataclass(frozen=True)
class RegionalAvailability:
    region_code: str
    region_name: str
    snapshot_date: date
    freshness_days: int
    member_region_codes: tuple[str, ...]
    key_figures: KeyFigures
    qualifying_offers: tuple[QualifyingOffer, ...]
    deployments: tuple[RegionalDeployment, ...]
    groups: tuple[GroupSummary, ...]
    reconciles: bool
    gate: GateResult
    direct_answer: str


# --------------------------------------------------------------------------- #
# Region membership
# --------------------------------------------------------------------------- #
def region_members(regions: tuple[RegionNode, ...], region_code: str) -> frozenset[str]:
    """`region_code` plus every descendant. Cycle-safe; GLOBAL is never added
    unless it is itself the requested region."""
    by_code = {r.code: r for r in regions}
    if region_code not in by_code:
        raise ValueError(f"unknown region {region_code!r}")
    children: dict[str, list[str]] = {}
    for r in regions:
        if r.parent_code is not None:
            children.setdefault(r.parent_code, []).append(r.code)
    members = {region_code}
    frontier = [region_code]
    while frontier:
        nxt: list[str] = []
        for code in frontier:
            for child in children.get(code, ()):
                if child not in members:
                    members.add(child)
                    nxt.append(child)
        frontier = nxt
    return frozenset(members)


# --------------------------------------------------------------------------- #
# Evidence freshness
# --------------------------------------------------------------------------- #
def _evidence_date(ev: EvidenceRow) -> date:
    return ev.verified_at or ev.observed_at


def _in_window(ev: EvidenceRow, snapshot: date, freshness_days: int) -> bool:
    age = (snapshot - _evidence_date(ev)).days
    return 0 <= age <= freshness_days


def _fresh_evidence(
    evidence: tuple[EvidenceRow, ...], snapshot: date, freshness_days: int
) -> tuple[EvidenceRow, ...]:
    return tuple(e for e in evidence if _in_window(e, snapshot, freshness_days))


# --------------------------------------------------------------------------- #
# Prices
# --------------------------------------------------------------------------- #
def _price_state(p: PriceRow) -> PriceState:
    common = dict(
        price_type=p.price_type, currency=p.currency,
        billing_period=p.billing_period, price_basis=p.price_basis,
    )
    if p.price_type == "QUOTE_ONLY":
        return PriceState(kind="PRICE_ON_REQUEST", **common)
    if p.price_type in ESTIMATE_PRICE_TYPES:
        return PriceState(kind="ESTIMATE", amount=p.price, price_min=p.price_min,
                          price_max=p.price_max, **common)
    if p.price_type in PUBLISHED_PRICE_TYPES and (
        p.price is not None or (p.price_min is not None and p.price_max is not None)
    ):
        return PriceState(kind="PUBLISHED", amount=p.price, price_min=p.price_min,
                          price_max=p.price_max, **common)
    return PriceState(kind="NOT_PUBLISHED", **common)


def _price_sort_key(s: PriceState) -> tuple:
    value = s.amount if s.amount is not None else (s.price_min or 0.0)
    return (s.kind, s.currency or "", s.billing_period or "", value, s.price_basis or "")


def _prices_for_offer(
    robot: RobotRow, offer: OfferRow, snapshot: date, freshness_days: int
) -> tuple[PriceState, ...]:
    """Prices for the same robot × provider × transaction × region as the offer.
    Only current, evidence-linked, fresh price rows count; otherwise the price is
    NOT_PUBLISHED (UNKNOWN), never an invented value."""
    states = [
        _price_state(p)
        for p in robot.prices
        if p.is_current
        and p.provider_slug == offer.provider_slug
        and p.transaction_type == offer.transaction_type
        and p.region_code == offer.region_code
        and _fresh_evidence(p.evidence, snapshot, freshness_days)
    ]
    if not states:
        return (PriceState(kind="NOT_PUBLISHED"),)
    return tuple(sorted(set(states), key=_price_sort_key))


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def _classify(
    robot: RobotRow, members: frozenset[str], snapshot: date, freshness_days: int
) -> tuple[str, tuple[QualifyingOffer, ...]]:
    qualifying: list[QualifyingOffer] = []
    confirmed_not_obtainable = stale = no_evidence = False

    for o in (o for o in robot.offers if o.region_code in members):
        if not o.is_current:
            stale = True
            continue
        if not o.evidence:
            no_evidence = True
            continue
        fresh = _fresh_evidence(o.evidence, snapshot, freshness_days)
        if not fresh:
            stale = True
            continue
        if o.availability_status in NOT_OBTAINABLE:
            confirmed_not_obtainable = True
            continue
        if o.availability_status not in OBTAINABLE:
            continue
        qualifying.append(
            QualifyingOffer(
                robot_slug=robot.slug,
                robot_name=robot.name,
                manufacturer_slug=robot.manufacturer_slug,
                manufacturer_name=robot.manufacturer_name,
                provider_slug=o.provider_slug,
                provider_type=o.provider_type,
                region_code=o.region_code or "",
                transaction_type=o.transaction_type,
                availability_status=o.availability_status,
                evidence_date=max(_evidence_date(e) for e in fresh),
                confidence=min((e.confidence for e in fresh),
                               key=lambda c: _CONFIDENCE_RANK.get(c, -1)),
                human_verified=all(e.verified_at is not None for e in fresh),
                source_urls=tuple(sorted({e.source_url for e in fresh})),
                prices=_prices_for_offer(robot, o, snapshot, freshness_days),
            )
        )
    if qualifying:
        return QUALIFYING, tuple(qualifying)
    if confirmed_not_obtainable:
        return CONFIRMED_NOT_OBTAINABLE, ()
    if stale:
        return STALE_OR_NON_CURRENT, ()
    if no_evidence:
        return OFFER_WITHOUT_EVIDENCE, ()

    rows = list(robot.offers) + list(robot.prices)
    if any(r.region_code is None for r in rows):
        return UNRESOLVED_REGION, ()
    if any(p.region_code in members for p in robot.prices):
        return PRICE_ONLY, ()
    if any(r.region_code == GLOBAL_CODE for r in rows):
        return GLOBAL_ONLY, ()
    if rows:
        return OTHER_REGION_ONLY, ()
    return NO_OFFERS, ()


# --------------------------------------------------------------------------- #
# Deployments
# --------------------------------------------------------------------------- #
def _regional_deployments(
    robot: RobotRow, members: frozenset[str]
) -> tuple[RegionalDeployment, ...]:
    out = []
    for d in robot.deployments:
        if d.region_code not in members or not d.evidence:
            continue  # unresolved/other region, or no evidence: not a regional fact
        out.append(
            RegionalDeployment(
                robot_slug=robot.slug,
                robot_name=robot.name,
                manufacturer_slug=robot.manufacturer_slug,
                manufacturer_name=robot.manufacturer_name,
                region_code=d.region_code or "",
                customer_name=d.customer_name,
                provider_slug=d.provider_slug,
                transaction_type=d.transaction_type,
                unit_count=d.unit_count,
                started_on=d.started_on,
                status=d.status,
                evidence_date=max(_evidence_date(e) for e in d.evidence),
                confidence=min((e.confidence for e in d.evidence),
                               key=lambda c: _CONFIDENCE_RANK.get(c, -1)),
                human_verified=all(e.verified_at is not None for e in d.evidence),
                source_urls=tuple(sorted({e.source_url for e in d.evidence})),
            )
        )
    return tuple(out)


# --------------------------------------------------------------------------- #
# Direct answer
# --------------------------------------------------------------------------- #
def _fmt_money(amount: float) -> str:
    return f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _join(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _purchase_price_range(offers: tuple[QualifyingOffer, ...]) -> str | None:
    """`low–high CUR` over published purchase prices, only when they share one
    currency, one billing period and one stated price basis. Otherwise None, so
    the sentence omits it rather than approximating (ADR-027 §9)."""
    published = [
        p
        for o in offers
        if o.transaction_type == "PURCHASE"
        for p in o.prices
        if p.kind == "PUBLISHED"
    ]
    if not published:
        return None
    currencies = {p.currency for p in published}
    if len(currencies) != 1 or None in currencies:
        return None
    if len({p.billing_period for p in published}) != 1:
        return None
    bases = {p.price_basis for p in published}
    if len(bases) != 1 or None in bases:
        return None
    values: list[float] = []
    for p in published:
        if p.amount is not None:
            values.append(p.amount)
        else:
            values.extend(v for v in (p.price_min, p.price_max) if v is not None)
    lo, hi = min(values), max(values)
    cur = published[0].currency
    if lo == hi:
        return f"{_fmt_money(lo)} {cur}"
    return f"{_fmt_money(lo)}–{_fmt_money(hi)} {cur}"


def _direct_answer(
    region_name: str, snapshot: date, kf: KeyFigures, offers: tuple[QualifyingOffer, ...]
) -> str:
    n = kf.qualifying_robots
    parts: list[str] = []
    if n == 0:
        parts.append(
            f"As of {snapshot.isoformat()}, HumanoidOnline has no confirmed offer on file "
            f"for a published humanoid robot in {region_name}."
        )
    else:
        parts.append(
            f"As of {snapshot.isoformat()}, HumanoidOnline lists {n} published humanoid "
            f"{_plural(n, 'robot', 'robots')} with a confirmed offer in {region_name}."
        )
    if kf.purchase_robots:
        counts = dict(kf.purchase_by_best_status)
        waitlist_or_preorder = counts.get("WAITLIST", 0) + counts.get("PREORDER", 0)
        bits = [
            f"{c} {label}"
            for c, label in (
                (counts.get("AVAILABLE", 0), "available"),
                (counts.get("LIMITED", 0), "limited"),
                (waitlist_or_preorder, "waitlist or preorder"),
                (counts.get("ON_REQUEST", 0), "on request"),
            )
            if c
        ]
        parts.append(f"{kf.purchase_robots} can be purchased: {_join(bits)}.")
        priced = kf.purchase_robots_with_published_price
        if priced:
            rng = _purchase_price_range(offers)
            tail = f" ({rng})" if rng else ""
            parts.append(
                f"{priced} of the {kf.purchase_robots} purchasable "
                f"{_plural(kf.purchase_robots, 'robot has', 'robots have')} a published "
                f"purchase price{tail}."
            )
    label = {"RENTAL": "rental", "LEASE": "lease", "RAAS": "RaaS"}
    for t, c in kf.robots_by_other_transaction:
        if c:
            parts.append(
                f"Additionally, {c} of these robots "
                f"{_plural(c, 'has', 'have')} a confirmed {label.get(t, t.lower())} offer."
            )
    if kf.no_confirmed_offer:
        parts.append(
            f"{kf.no_confirmed_offer} other published "
            f"{_plural(kf.no_confirmed_offer, 'robot has', 'robots have')} no confirmed "
            f"{region_name} offer on file."
        )
    parts.append("Evidence sources, confidence and observation dates are listed below.")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build_regional_availability(
    snapshot: RegionalSnapshot,
    region_code: str,
    *,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    min_robots: int = DEFAULT_MIN_ROBOTS,
    min_manufacturers: int = DEFAULT_MIN_MANUFACTURERS,
) -> RegionalAvailability:
    members = region_members(snapshot.regions, region_code)
    region_name = next(r.name for r in snapshot.regions if r.code == region_code)

    published = sorted((r for r in snapshot.robots if r.is_published), key=lambda r: r.slug)
    deployments = tuple(
        sorted(
            (d for r in published for d in _regional_deployments(r, members)),
            key=lambda d: (d.robot_slug, d.region_code, d.customer_name or "",
                           d.started_on or date.min),
        )
    )
    grouped: dict[str, list[RobotRow]] = {g: [] for g in GROUP_ORDER}
    offers_by_robot: dict[str, tuple[QualifyingOffer, ...]] = {}
    for robot in published:
        reason, q = _classify(robot, members, snapshot.snapshot_date, freshness_days)
        grouped[reason].append(robot)
        if q:
            offers_by_robot[robot.slug] = q

    qualifying_offers = tuple(
        sorted(
            (o for q in offers_by_robot.values() for o in q),
            key=lambda o: (o.robot_slug, o.provider_slug or "", o.region_code,
                           o.transaction_type),
        )
    )
    groups = tuple(
        GroupSummary(
            reason=g,
            robots=tuple(RobotRef(r.slug, r.name, r.manufacturer_slug) for r in grouped[g]),
        )
        for g in GROUP_ORDER
    )
    population = len(published)
    reconciles = sum(g.count for g in groups) == population

    qual_robots = grouped[QUALIFYING]
    manufacturers = {r.manufacturer_slug for r in qual_robots}

    purchase_robots = [
        slug for slug, q in offers_by_robot.items()
        if any(o.transaction_type == "PURCHASE" for o in q)
    ]
    best_status = {s: 0 for s in _PURCHASE_STATUS_ORDER}
    with_price = on_request = not_published = 0
    for slug in purchase_robots:
        purchase = [o for o in offers_by_robot[slug] if o.transaction_type == "PURCHASE"]
        statuses = {o.availability_status for o in purchase}
        best_status[next(s for s in _PURCHASE_STATUS_ORDER if s in statuses)] += 1
        kinds = {p.kind for o in purchase for p in o.prices}
        if "PUBLISHED" in kinds:
            with_price += 1
        elif "PRICE_ON_REQUEST" in kinds:
            on_request += 1
        else:
            not_published += 1
    other_types: dict[str, set[str]] = {}
    for slug, q in offers_by_robot.items():
        for o in q:
            if o.transaction_type != "PURCHASE":
                other_types.setdefault(o.transaction_type, set()).add(slug)

    kf = KeyFigures(
        population=population,
        qualifying_robots=len(qual_robots),
        qualifying_manufacturers=len(manufacturers),
        no_confirmed_offer=population - len(qual_robots),
        purchase_robots=len(purchase_robots),
        purchase_by_best_status=tuple((s, best_status[s]) for s in _PURCHASE_STATUS_ORDER),
        robots_by_other_transaction=tuple(
            (t, len(s)) for t, s in sorted(other_types.items())
        ),
        purchase_robots_with_published_price=with_price,
        purchase_robots_price_on_request=on_request,
        purchase_robots_price_not_published=not_published,
    )

    failures = []
    if len(qual_robots) < min_robots:
        failures.append(f"qualifying robots {len(qual_robots)} < {min_robots}")
    if len(manufacturers) < min_manufacturers:
        failures.append(f"qualifying manufacturers {len(manufacturers)} < {min_manufacturers}")
    gate = GateResult(
        passes=not failures,
        qualifying_robots=len(qual_robots),
        qualifying_manufacturers=len(manufacturers),
        min_robots=min_robots,
        min_manufacturers=min_manufacturers,
        failures=tuple(failures),
    )

    return RegionalAvailability(
        region_code=region_code,
        region_name=region_name,
        snapshot_date=snapshot.snapshot_date,
        freshness_days=freshness_days,
        member_region_codes=tuple(sorted(members)),
        key_figures=kf,
        qualifying_offers=qualifying_offers,
        deployments=deployments,
        groups=groups,
        reconciles=reconciles,
        gate=gate,
        direct_answer=_direct_answer(region_name, snapshot.snapshot_date, kf, qualifying_offers),
    )
