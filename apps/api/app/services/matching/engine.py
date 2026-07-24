"""The deterministic matching engine (WS6) — a PURE function.

`match(requirement, robots)` takes fully-materialized inputs and returns a
`MatchOutcome`. It performs NO I/O, reads NO clock, uses NO randomness and NO LLM
(frozen contract §7). Identical inputs always produce byte-identical output.

Weights (§7): use-case 25 · commercial 20 · technical 20 · geography 15 ·
budget 10 · deployment-readiness 10. A criterion the buyer did not engage is
inactive and its weight redistributes proportionally across the active ones;
commercial availability and deployment readiness are always active. A stated
criterion the robot has no data for scores a neutral-uncertain 0.5 + warning
(never 0). Hard exclusions run before scoring; UNKNOWN never excludes.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.matching.inputs import (
    MatchOutcome,
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

# Exclusion reason code -> human explanation (for no_match_explanation).
_EXCLUSION_TEXT = {
    "payload": "the stated minimum payload exceeded every candidate's known capacity",
    "manipulation": "manipulation was required but candidates are known not to manipulate",
    "autonomy": "the required autonomy level was above every candidate's known level",
    "discontinued": "the matching platforms are discontinued",
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass
class _Criterion:
    subscore: float
    reasons: list[str]
    warnings: list[str]


# --------------------------------------------------------------------------- #
# Hard exclusions (§7.1) — a KNOWN value violating a STATED requirement.
# --------------------------------------------------------------------------- #
def exclusion_reason(req: RequirementInput, r: RobotInput) -> str | None:
    if (
        req.payload_min_kg is not None
        and r.payload_kg is not None
        and r.payload_kg < req.payload_min_kg
    ):
        return "payload"
    if req.manipulation_required is True and r.has_manipulation is False:
        return "manipulation"
    if (
        req.autonomy_required is not None
        and r.autonomy is not None
        and AUTONOMY_ORDER.get(r.autonomy, 0) < AUTONOMY_ORDER.get(req.autonomy_required, 0)
    ):
        return "autonomy"
    if r.commercial_status == "DISCONTINUED":
        return "discontinued"
    return None


# --------------------------------------------------------------------------- #
# Per-criterion sub-scores in [0,1]. commercial + deployment always active;
# the others return None when the buyer stated nothing relevant (inactive).
# --------------------------------------------------------------------------- #
def _use_case(req: RequirementInput, r: RobotInput) -> _Criterion | None:
    if req.use_case is None:
        return None
    if r.use_case_fit is None:
        return _Criterion(0.5, [], [f"use-case fit for {req.use_case} is unverified"])
    fit = _clamp(r.use_case_fit)
    reasons = [f"use-case fit {fit:.2f} for {req.use_case}"] if fit >= 0.6 else []
    return _Criterion(fit, reasons, [])


def _matching_offers(req: RequirementInput, r: RobotInput):
    allowed = PREF_TO_TXN.get(req.preferred_transaction, None)
    return [
        o for o in r.offers
        if o.is_current and (allowed is None or o.transaction_type in allowed)
    ]


def _commercial(req: RequirementInput, r: RobotInput) -> _Criterion:
    offers = _matching_offers(req, r)
    accessible = [o for o in offers if o.availability_status not in NON_ACCESSIBLE]
    reasons: list[str] = []
    warnings: list[str] = []
    if accessible:
        sub = 1.0
        reasons.append("commercially accessible for the requested transaction")
        if not any(o.availability_status == "AVAILABLE" for o in accessible):
            warnings.append("commercial availability is constrained (waitlist/preorder/on-request)")
        # required-by soft penalty (never a hard exclude)
        if req.required_by is not None:
            known = [o.available_from for o in accessible if o.available_from is not None]
            if known and min(known) > req.required_by:
                sub = 0.5
                warnings.append("earliest known availability is after the required-by date")
        return _Criterion(sub, reasons if sub == 1.0 else [], warnings)
    if offers:  # matching offers exist but all are NOT_AVAILABLE / DISCONTINUED
        return _Criterion(0.0, [], ["no accessible commercial offer for the requested transaction"])
    return _Criterion(0.5, [], ["no confirmed commercial availability"])


def _geography(req: RequirementInput, r: RobotInput) -> _Criterion | None:
    if req.country is None:
        return None
    applicable = [o for o in r.offers if o.is_current and o.geo_applicable]
    accessible = [o for o in applicable if o.availability_status not in NON_ACCESSIBLE]
    if accessible:
        return _Criterion(1.0, [f"available in {req.country}"], [])
    if applicable:
        return _Criterion(0.0, [], [f"offers for {req.country} are not accessible"])
    return _Criterion(0.5, [], [f"no regional availability evidence for {req.country}"])


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

    if not parts:
        return None
    return _Criterion(sum(parts) / len(parts), reasons, warnings)


def _budget(req: RequirementInput, r: RobotInput) -> _Criterion | None:
    if req.budget_min is None and req.budget_max is None:
        return None
    # Descriptive minimum only, no ceiling -> neutral (never penalize "too cheap").
    if req.budget_max is None:
        return _Criterion(0.5, [], [])

    cur = (req.budget_currency or "").upper()
    allowed = PREF_TO_TXN.get(req.preferred_transaction, None)

    def comparable(p) -> bool:
        # No FX in WS6: only compare a price stated in the buyer's currency,
        # matching the transaction preference, and geographically applicable
        # when a country was stated.
        if not p.is_current:
            return False
        if not (p.currency and p.currency.upper() == cur):
            return False
        if allowed is not None and p.transaction_type not in allowed:
            return False
        if req.country is not None and not p.geo_applicable:
            return False
        return True

    prices = [p for p in r.prices if comparable(p)]
    if not prices:
        # Distinguish *why* there is no comparable price (all neutral-uncertain).
        if any(p.is_current for p in r.prices):
            return _Criterion(0.5, [], ["no price in the requested currency/terms"])
        return _Criterion(0.5, [], ["no confirmed pricing"])

    best = 0.0
    best_warnings: list[str] = []
    max_ = req.budget_max

    def ramp(price: float) -> float:
        if price <= max_:
            return 1.0
        if price >= 1.1 * max_:
            return 0.0
        return (1.1 * max_ - price) / (0.1 * max_)

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
            else:
                bf = 0.5
                w.append("price range crosses the budget ceiling")
        elif p.price_type == "FROM" and p.price is not None:
            bf = min(ramp(p.price), 0.75)
            w.append("only a starting ('from') price is published")
        elif p.price_type in ("PUBLIC", "ESTIMATED") and p.price is not None:
            bf = ramp(p.price)
            if p.price_type == "ESTIMATED":
                w.append("price is an estimate, not confirmed")
        else:
            bf = 0.5
            w.append("pricing is indicative")
        if bf > best:
            best, best_warnings = bf, w
    reasons = ["within the stated budget"] if best >= 0.99 else []
    return _Criterion(best, reasons, best_warnings)


def _deployment(r: RobotInput) -> _Criterion:
    maturity = MATURITY.get(r.commercial_status, 0.0)
    evidence = 1.0 if r.deployment_count >= 1 else 0.5
    sub = 0.5 * maturity + 0.5 * evidence
    reasons: list[str] = []
    if r.deployment_count >= 1:
        reasons.append(f"{r.deployment_count} confirmed deployment(s)")
    if maturity >= 1.0:
        reasons.append(f"commercial maturity: {r.commercial_status}")
    return _Criterion(sub, reasons, [])


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
    reasons: list[str] = []
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

    # reasons[] = top concrete contributing facts, guaranteed >= 2 (§7.5).
    contributions.sort(key=lambda t: (-t[0], t[1]))
    for _, text in contributions:
        if text not in reasons:
            reasons.append(text)
    if len(reasons) < 2:
        pub = f"tracked platform by {r.manufacturer_name}"
        if pub not in reasons:
            reasons.append(pub)
    if len(reasons) < 2:
        reasons.append(f"commercial status: {r.commercial_status}")
    reasons = reasons[:4]

    vt = r.freshest_verified_at
    verified_key = -vt.timestamp() if vt is not None else float("inf")
    return _Scored(
        slug=r.slug, score=score, breakdown=breakdown, reasons=reasons,
        warnings=warnings, commercial_sub=crits["commercial_availability"].subscore,
        deployment_count=r.deployment_count, verified_key=verified_key,
    )


# --------------------------------------------------------------------------- #
# Category assignment among the top survivors (§6.8 result labels).
# --------------------------------------------------------------------------- #
def _assign_categories(ranked: list[_Scored], robots: dict[str, RobotInput]) -> dict[str, str]:
    cats = {ranked[0].slug: "BEST_OVERALL"} if ranked else {}
    pool = ranked[1:]  # ranks 2..N
    taken: set[str] = set()

    def claim(candidates: list[_Scored], label: str) -> None:
        for s in candidates:
            if s.slug not in taken:
                cats[s.slug] = label
                taken.add(s.slug)
                return

    # BEST_COMMERCIAL: strongest commercial availability (must be positive).
    claim(sorted([s for s in pool if s.commercial_sub > 0.0],
                 key=lambda s: (-s.commercial_sub, s.slug)), "BEST_COMMERCIAL")
    # BEST_LOWER_COST: strongest budget fit (must be positive).
    claim(sorted([s for s in pool if s.breakdown["budget_fit"] > 0.0],
                 key=lambda s: (-s.breakdown["budget_fit"], s.slug)), "BEST_LOWER_COST")
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
    excluded: dict[str, int] = {}
    survivors: list[_Scored] = []
    by_slug: dict[str, RobotInput] = {}
    for r in robots:
        reason = exclusion_reason(req, r)
        if reason is not None:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        by_slug[r.slug] = r
        survivors.append(_score(req, r))

    survivors.sort(key=lambda s: (
        -s.score, -s.commercial_sub, -s.deployment_count, s.verified_key, s.slug,
    ))
    top = survivors[:4]
    cats = _assign_categories(top, by_slug)

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
        if excluded:
            reason = max(sorted(excluded), key=lambda k: excluded[k])
            n = excluded[reason]
            total = len(robots)
            no_match_explanation = (
                f"No platform matched: {_EXCLUSION_TEXT[reason]} "
                f"({n} of {total} candidates excluded)."
            )
        else:
            no_match_explanation = "No published platforms are available to match yet."

    excluded_count = len(robots) - len(matches)
    return MatchOutcome(
        matches=matches,
        excluded_count=excluded_count,
        no_match_explanation=no_match_explanation,
    )
