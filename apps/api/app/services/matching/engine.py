"""The deterministic matching engine (WS6) — a PURE function.

`match(requirement, robots)` takes fully-materialized inputs and returns a
`MatchOutcome`. It performs NO I/O, reads NO clock, uses NO randomness and NO LLM
(frozen contract §7). Identical inputs always produce byte-identical output —
including when the caller passes offers/prices in a different order.

Weights (§7): use-case 25 · commercial 20 · technical 20 · geography 15 ·
budget 10 · deployment-readiness 10. A criterion the buyer did not engage is
inactive and its weight redistributes proportionally across the active ones;
commercial availability and deployment readiness are always active. A stated
criterion the robot has no data for scores a neutral-uncertain 0.5 + warning
(never 0). Hard exclusions run before scoring; UNKNOWN never excludes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.matching.inputs import (
    MatchOutcome,
    PriceInput,
    RequirementInput,
    RobotInput,
    ScoredMatch,
)

AUTONOMY_ORDER = {
    "TELEOPERATED": 0, "ASSISTED": 1, "SUPERVISED_AUTONOMY": 2,
    "TASK_AUTONOMOUS": 3, "HIGHLY_AUTONOMOUS": 4,
}
BASE_WEIGHTS = {
    "use_case_fit": 25, "commercial_availability": 20, "technical_fit": 20,
    "geographic_fit": 15, "budget_fit": 10, "deployment_readiness": 10,
}
BREAKDOWN_KEYS = tuple(BASE_WEIGHTS)
MATURITY = {
    "ANNOUNCED": 0.0, "DEVELOPMENT": 0.15, "PROTOTYPE": 0.30, "PILOT": 0.50,
    "EARLY_ACCESS": 0.65, "LIMITED_COMMERCIAL": 0.80, "COMMERCIAL": 1.0,
    "RAAS_DEPLOYMENT": 1.0,
}
# Preferred transaction -> the availability transaction_type(s) it maps to.
# None means "any transaction type" (FLEXIBLE / UNKNOWN).
PREF_TO_TXN: dict[str, set[str] | None] = {
    "RENT": {"RENTAL"}, "BUY": {"PURCHASE"}, "LEASE": {"LEASE"}, "RAAS": {"RAAS"},
    "FLEXIBLE": None, "UNKNOWN": None,
}
NON_ACCESSIBLE = {"NOT_AVAILABLE", "DISCONTINUED"}
CONSTRAINED = {"WAITLIST", "PREORDER", "LIMITED", "ON_REQUEST"}

# Dominant-constraint detail (for no_match_explanation). Factual and quantified —
# no absolute "every candidate" phrasing when the rule eliminated only a subset.
_EXCLUSION_DETAIL = {
    "payload": "the stated minimum payload exceeded the known capacity",
    "manipulation": "candidates are known not to provide the required manipulation",
    "autonomy": "the required autonomy level was above the known level",
    "discontinued": "candidates are discontinued",
}



def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _txn_allowed(pref: str) -> set[str] | None:
    return PREF_TO_TXN.get(pref, None)


def _txn_ok(txn: str, allowed: set[str] | None) -> bool:
    return allowed is None or txn in allowed


@dataclass
class _Criterion:
    subscore: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # commercial only: is there a real current, transaction-compatible, accessible
    # offer? Distinct from subscore, which is 0.5 both for "no offer" and for an
    # accessible-but-late offer (timeline soft penalty).
    accessible: bool = False


# --------------------------------------------------------------------------- #
# Hard exclusions (§7.1). exclusion_reasons returns ALL violated rules so the
# no_match_explanation can count each independently (not just the first hit).
# --------------------------------------------------------------------------- #
def exclusion_reasons(req: RequirementInput, r: RobotInput) -> list[str]:
    out: list[str] = []
    if (
        req.payload_min_kg is not None
        and r.payload_kg is not None
        and r.payload_kg < req.payload_min_kg
    ):
        out.append("payload")
    if req.manipulation_required is True and r.has_manipulation is False:
        out.append("manipulation")
    if (
        req.autonomy_required is not None
        and r.autonomy is not None
        and AUTONOMY_ORDER.get(r.autonomy, 0) < AUTONOMY_ORDER.get(req.autonomy_required, 0)
    ):
        out.append("autonomy")
    if r.commercial_status == "DISCONTINUED":
        out.append("discontinued")
    return out


def exclusion_reason(req: RequirementInput, r: RobotInput) -> str | None:
    reasons = exclusion_reasons(req, r)
    return reasons[0] if reasons else None


# --------------------------------------------------------------------------- #
# Per-criterion sub-scores in [0,1]. commercial + deployment always active;
# the others return None when the buyer stated nothing relevant (inactive).
# --------------------------------------------------------------------------- #
def _use_case(req: RequirementInput, r: RobotInput) -> _Criterion | None:
    if req.use_case is None:
        return None
    if r.use_case_fit is None:
        return _Criterion(0.5, warnings=[f"use-case fit for {req.use_case} is unverified"])
    fit = _clamp(r.use_case_fit)
    reasons = [f"use-case fit {fit:.2f} for {req.use_case}"] if fit >= 0.6 else []
    return _Criterion(fit, reasons=reasons)


def _matching_offers(req: RequirementInput, r: RobotInput):
    allowed = _txn_allowed(req.preferred_transaction)
    return [o for o in r.offers if o.is_current and _txn_ok(o.transaction_type, allowed)]


def _commercial(req: RequirementInput, r: RobotInput) -> _Criterion:
    # OBTAINABILITY dimension — availability_offer by transaction mode. Kept strictly
    # separate from MATURITY (commercial_status): accessibility is NEVER inferred
    # from status. Every branch emits a truthful reason so the always-active
    # commercial criterion explains its own score.
    offers = _matching_offers(req, r)
    accessible = [o for o in offers if o.availability_status not in NON_ACCESSIBLE]
    warnings: list[str] = []
    if accessible:
        sub = 1.0
        if not any(o.availability_status == "AVAILABLE" for o in accessible):
            warnings.append("commercial availability is constrained (waitlist/preorder/on-request)")
        if req.required_by is not None:
            known = [o.available_from for o in accessible if o.available_from is not None]
            if known and min(known) > req.required_by:
                sub = 0.5
                warnings.append("earliest known availability is after the required-by date")
        return _Criterion(
            sub, reasons=["commercially accessible for the requested transaction"],
            warnings=warnings, accessible=True,
        )
    if offers:  # matching offers exist but all are NOT_AVAILABLE / DISCONTINUED
        msg = "no accessible commercial offer for the requested transaction"
        return _Criterion(0.0, reasons=[msg], warnings=[msg])
    return _Criterion(
        0.5,
        reasons=["commercial availability unconfirmed; neutral score applied"],
        warnings=["no confirmed commercial availability"],
    )


def _geography(req: RequirementInput, r: RobotInput) -> _Criterion | None:
    if req.country is None:
        return None
    # Geography must use the SAME transaction-compatible offer universe as the
    # buyer's preference — a PURCHASE offer must not prove RENT geography.
    allowed = _txn_allowed(req.preferred_transaction)
    applicable = [
        o for o in r.offers
        if o.is_current and o.geo_applicable and _txn_ok(o.transaction_type, allowed)
    ]
    accessible = [o for o in applicable if o.availability_status not in NON_ACCESSIBLE]
    if accessible:
        return _Criterion(1.0, reasons=[f"available in {req.country}"])
    if applicable:
        return _Criterion(0.0, warnings=[f"offers for {req.country} are not accessible"])
    return _Criterion(0.5, warnings=[f"no regional availability evidence for {req.country}"])


def _technical(req: RequirementInput, r: RobotInput) -> _Criterion | None:
    parts: list[float] = []
    reasons: list[str] = []
    warnings: list[str] = []

    if req.payload_min_kg is not None:
        if req.payload_min_kg == 0:
            parts.append(1.0)
        elif r.payload_kg is None:
            parts.append(0.5)
            warnings.append("payload unverified")
        else:
            pf = _clamp(r.payload_kg / (req.payload_min_kg * 1.25))
            parts.append(pf)
            if pf >= 0.8:
                reasons.append(
                    f"payload {r.payload_kg:g} kg meets the {req.payload_min_kg:g} kg requirement"
                )

    if req.autonomy_required is not None:
        if r.autonomy is None:
            parts.append(0.5)
            warnings.append("autonomy level unverified")
        else:
            parts.append(1.0)  # below-requirement was already excluded
            reasons.append(f"autonomy {r.autonomy} meets {req.autonomy_required}")

    if req.manipulation_required is True:
        if r.has_manipulation is None:
            parts.append(0.5)
            warnings.append("manipulation capability unverified")
        else:  # True (False was excluded)
            parts.append(1.0)
            reasons.append("supports required manipulation")

    if req.operating_hours_day is not None:
        if r.runtime_minutes is None:
            parts.append(0.5)
            warnings.append("runtime unverified")
        else:
            need = req.operating_hours_day * 60
            parts.append(0.5 + 0.5 * _clamp(r.runtime_minutes / need if need else 1.0))
            if need and r.runtime_minutes < need:
                warnings.append("runtime may require a charging strategy")
            else:
                reasons.append(
                    f"runtime covers the requested {req.operating_hours_day:g} h/day duty cycle"
                )

    if not parts:
        return None
    return _Criterion(sum(parts) / len(parts), reasons=reasons, warnings=warnings)


def _price_key(p: PriceInput) -> tuple:
    """A stable, order-independent identity for a price offer."""
    return (
        p.transaction_type, p.price_type, p.currency or "", p.billing_period,
        p.price if p.price is not None else -1.0,
        p.price_min if p.price_min is not None else -1.0,
        p.price_max if p.price_max is not None else -1.0,
    )


def _budget(req: RequirementInput, r: RobotInput) -> _Criterion | None:
    if req.budget_min is None and req.budget_max is None:
        return None
    if req.budget_max is None:
        # Descriptive minimum only, no ceiling -> neutral (never penalize "cheaper").
        return _Criterion(0.5)

    cur = (req.budget_currency or "").upper()
    allowed = _txn_allowed(req.preferred_transaction)

    def comparable(p: PriceInput) -> bool:
        if not p.is_current:
            return False
        if not (p.currency and p.currency.upper() == cur):
            return False
        if not _txn_ok(p.transaction_type, allowed):
            return False
        if req.country is not None and not p.geo_applicable:
            return False
        return True

    prices = [p for p in r.prices if comparable(p)]
    if not prices:
        if any(p.is_current for p in r.prices):
            return _Criterion(0.5, warnings=["no price in the requested currency/terms"])
        return _Criterion(0.5, warnings=["no confirmed pricing"])

    max_ = req.budget_max

    def ramp(price: float) -> float:
        if price <= max_:
            return 1.0
        if price >= 1.1 * max_:
            return 0.0
        return (1.1 * max_ - price) / (0.1 * max_)

    # Evaluate every comparable price, then pick the winner ORDER-INDEPENDENTLY:
    # highest fit, then fewest warnings, then a stable price key.
    evaluated: list[tuple[float, int, tuple, list[str]]] = []
    for p in prices:
        w: list[str] = []
        if p.price_type == "QUOTE_ONLY":
            bf = 0.5
            w.append("pricing is quote-only")
        elif p.billing_period != "ONE_TIME":
            bf = 0.5
            w.append(f"price is {p.billing_period.lower()} — not comparable to a one-off budget")
        elif p.price_type == "RANGE" and p.price_min is not None and p.price_max is not None:
            if p.price_max <= max_:
                bf = 1.0
            elif p.price_min > max_:
                bf = ramp(p.price_min)
                w.append("price range starts above the stated budget")
            else:
                bf = 0.5
                w.append("price range crosses the budget ceiling")
        elif p.price_type == "FROM" and p.price is not None:
            bf = min(ramp(p.price), 0.75)
            w.append("only a starting ('from') price is published")
            if p.price > max_:
                w.append("price exceeds the stated budget")
        elif p.price_type in ("PUBLIC", "ESTIMATED") and p.price is not None:
            bf = ramp(p.price)
            if p.price > max_:
                w.append("price exceeds the stated budget")
            if p.price_type == "ESTIMATED":
                w.append("price is an estimate, not confirmed")
        else:
            bf = 0.5
            w.append("pricing is indicative")
        evaluated.append((bf, len(w), _price_key(p), w))

    evaluated.sort(key=lambda e: (-e[0], e[1], e[2]))
    best_bf, _, _, best_warnings = evaluated[0]
    reasons = ["within the stated budget"] if best_bf >= 0.99 else []
    return _Criterion(best_bf, reasons=reasons, warnings=best_warnings)


def lower_cost_refs(req: RequirementInput, r: RobotInput) -> list[tuple[float, str]]:
    """ALL 'lower-cost'-eligible price references for BEST_LOWER_COST: current,
    transaction-compatible, geography-compatible (when a country is stated),
    ONE_TIME, PUBLIC/ESTIMATED point prices. When the buyer stated a budget
    currency, only that currency is eligible. Returns every (price, currency) —
    the caller inspects the full set so a robot carrying two currencies makes the
    comparison incomparable (no FX)."""
    allowed = _txn_allowed(req.preferred_transaction)
    want_cur = req.budget_currency.upper() if req.budget_currency else None
    refs: list[tuple[float, str]] = []
    for p in r.prices:
        if not p.is_current or p.price is None:
            continue
        if p.billing_period != "ONE_TIME" or p.price_type not in ("PUBLIC", "ESTIMATED"):
            continue
        if not _txn_ok(p.transaction_type, allowed):
            continue
        if req.country is not None and not p.geo_applicable:
            continue
        currency = (p.currency or "").upper()
        if want_cur is not None and currency != want_cur:
            continue
        refs.append((float(p.price), currency))
    return refs


def _deployment(r: RobotInput) -> _Criterion:
    maturity = MATURITY.get(r.commercial_status, 0.0)
    evidence = 1.0 if r.deployment_count >= 1 else 0.5
    sub = 0.5 * maturity + 0.5 * evidence
    # MATURITY dimension only — commercial_status verbatim, NEVER translated into an
    # obtainability/purchasability claim (frozen: maturity != availability).
    reasons = [f"commercial maturity: {r.commercial_status}"]
    if r.deployment_count >= 1:
        reasons.append(f"{r.deployment_count} confirmed deployment(s)")
    return _Criterion(sub, reasons=reasons)


# --------------------------------------------------------------------------- #
# Candidate scoring (weights, redistribution, breakdown, reasons/warnings).
# --------------------------------------------------------------------------- #
@dataclass
class _Scored:
    slug: str
    score: int
    breakdown: dict[str, float]
    reasons: list[str]
    warnings: list[str]
    commercial_sub: float
    commercial_accessible: bool
    lowest_cost: float | None
    cost_currencies: frozenset[str]
    deployment_count: int
    verified_key: float  # -epoch (fresher sorts first); +inf when unknown


def _score(req: RequirementInput, r: RobotInput) -> _Scored:
    crits: dict[str, _Criterion | None] = {
        "use_case_fit": _use_case(req, r),
        "commercial_availability": _commercial(req, r),
        "technical_fit": _technical(req, r),
        "geographic_fit": _geography(req, r),
        "budget_fit": _budget(req, r),
        "deployment_readiness": _deployment(r),
    }
    active = {k: c for k, c in crits.items() if c is not None}
    active_base = sum(BASE_WEIGHTS[k] for k in active)
    factor = 100.0 / active_base if active_base else 0.0

    breakdown: dict[str, float] = {}
    contributions: list[tuple[float, str]] = []
    warnings: list[str] = []
    for key in BREAKDOWN_KEYS:
        c = crits[key]
        if c is None:
            breakdown[key] = 0.0
            continue
        eff = BASE_WEIGHTS[key] * factor
        contrib = round(c.subscore * eff, 2)
        breakdown[key] = contrib
        for rs in c.reasons:
            contributions.append((contrib, rs))
        warnings.extend(c.warnings)

    score = round(sum(breakdown.values()))

    # reasons[] = genuine facts only (active-criterion contributions + the always-
    # known commercial-status fact), highest-contributing first, de-duplicated. No
    # generic/marketing filler (§7.5).
    contributions.sort(key=lambda t: (-t[0], t[1]))
    reasons: list[str] = []
    for _, text in contributions:
        if text not in reasons:
            reasons.append(text)
    # >= 2 genuine reasons for EVERY survivor is guaranteed WITHOUT any invented
    # obtainability claim: the two always-active criteria each explain themselves —
    # deployment readiness gives a maturity fact and commercial availability gives
    # an accessibility/unknown/negative fact.
    reasons = reasons[:4]

    vt = r.freshest_verified_at
    verified_key = -vt.timestamp() if vt is not None else float("inf")
    refs = lower_cost_refs(req, r)
    return _Scored(
        slug=r.slug, score=score, breakdown=breakdown, reasons=reasons,
        warnings=warnings,
        commercial_sub=crits["commercial_availability"].subscore,
        commercial_accessible=crits["commercial_availability"].accessible,
        lowest_cost=min(p for p, _ in refs) if refs else None,
        cost_currencies=frozenset(c for _, c in refs),
        deployment_count=r.deployment_count, verified_key=verified_key,
    )


# --------------------------------------------------------------------------- #
# Category assignment among the top survivors (§6.8 result labels).
# --------------------------------------------------------------------------- #
def _assign_categories(
    ranked: list[_Scored], robots: dict[str, RobotInput], req: RequirementInput
) -> dict[str, str]:
    cats = {ranked[0].slug: "BEST_OVERALL"} if ranked else {}
    pool = ranked[1:]  # ranks 2..N
    taken: set[str] = set()

    def claim(candidates: list[_Scored], label: str) -> None:
        for s in candidates:
            if s.slug not in taken:
                cats[s.slug] = label
                taken.add(s.slug)
                return

    # BEST_COMMERCIAL: "Best Commercial (available)" — must have a real accessible
    # offer, not merely a 0.5 unknown-availability subscore.
    claim(
        sorted([s for s in pool if s.commercial_accessible],
               key=lambda s: (-s.commercial_sub, s.slug)),
        "BEST_COMMERCIAL",
    )

    # BEST_LOWER_COST: lowest KNOWN numeric eligible cost. Comparability (no FX) is
    # judged over the COMPARISON UNIVERSE — every lower-cost-eligible reference
    # across ALL of ranks 2-4 — NOT the reduced label-candidate set. A candidate
    # already claimed by a higher-precedence category still contributes its
    # currencies, so e.g. a USD BEST_COMMERCIAL winner + an EUR candidate remain
    # incomparable and no label is assigned.
    comparison = [s for s in pool if s.lowest_cost is not None]
    if not req.budget_currency:
        all_currencies: set[str] = set()
        for s in comparison:
            all_currencies |= s.cost_currencies
        if len(all_currencies) > 1:
            comparison = []
    label_candidates = [s for s in comparison if s.slug not in taken]
    claim(sorted(label_candidates, key=lambda s: (s.lowest_cost, s.slug)), "BEST_LOWER_COST")

    # BEST_DEVELOPER: a developer-oriented platform.
    def dev(s: _Scored) -> bool:
        rb = robots[s.slug]
        return bool(rb.has_sdk or rb.ros_support or rb.developer_edition)
    claim([s for s in pool if dev(s)], "BEST_DEVELOPER")

    for s in pool:
        cats.setdefault(s.slug, "ALTERNATIVE")
    return cats


# --------------------------------------------------------------------------- #
# Public entrypoint.
# --------------------------------------------------------------------------- #
def match(req: RequirementInput, robots: list[RobotInput]) -> MatchOutcome:
    excluded_counts: dict[str, int] = {}
    excluded_total = 0
    survivors: list[_Scored] = []
    by_slug: dict[str, RobotInput] = {}
    for r in robots:
        reasons = exclusion_reasons(req, r)
        if reasons:
            excluded_total += 1
            # Count EVERY violated rule so the dominant constraint is order-free.
            for code in reasons:
                excluded_counts[code] = excluded_counts.get(code, 0) + 1
            continue
        by_slug[r.slug] = r
        survivors.append(_score(req, r))

    survivors.sort(key=lambda s: (
        -s.score, -s.commercial_sub, -s.deployment_count, s.verified_key, s.slug,
    ))
    top = survivors[:4]
    cats = _assign_categories(top, by_slug, req)

    matches = tuple(
        ScoredMatch(
            slug=s.slug, score=s.score, rank=i + 1, category=cats[s.slug],
            breakdown=dict(s.breakdown), reasons=tuple(s.reasons),
            warnings=tuple(s.warnings),
        )
        for i, s in enumerate(top)
    )

    no_match_explanation = None
    if not matches:
        if excluded_counts:
            reason = max(sorted(excluded_counts), key=lambda k: excluded_counts[k])
            n, total = excluded_counts[reason], len(robots)
            no_match_explanation = (
                f"No platform matched. The dominant eliminating constraint was "
                f"{reason}: {_EXCLUSION_DETAIL[reason]} — {n} of {total} candidates."
            )
        else:
            no_match_explanation = "No published platforms are available to match yet."

    excluded_count = len(robots) - len(matches)
    return MatchOutcome(
        matches=matches,
        excluded_count=excluded_count,
        no_match_explanation=no_match_explanation,
    )
