"""Pure matching-engine tests (WS6) — NO database.

The engine is a pure function, so these run without DATABASE_URL. They lock the
frozen matching contract (01_PRODUCT_CONTRACT §7) and acceptance criteria E1-E8:
hard exclusions, UNKNOWN never excludes and scores 0.5, weight redistribution,
clamped ramps, deterministic ties, and byte-identical repeatability.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from app.services.matching import (
    OfferInput,
    PriceInput,
    RequirementInput,
    RobotInput,
    match,
)
from app.services.matching.engine import exclusion_reason


def robot(slug: str = "r", **kw) -> RobotInput:
    d = dict(
        name=slug.upper(), manufacturer_name="Maker", manufacturer_country="US",
        commercial_status="COMMERCIAL", payload_kg=None, has_manipulation=None,
        autonomy=None, runtime_minutes=None, has_sdk=None, ros_support=None,
        developer_edition=None, use_case_fit=None, offers=(), prices=(),
        deployment_count=0, freshest_verified_at=None,
    )
    d.update(kw)
    return RobotInput(slug=slug, **d)


def req(**kw) -> RequirementInput:
    d = dict(
        use_case=None, country=None, payload_min_kg=None, operating_hours_day=None,
        manipulation_required=None, autonomy_required=None, budget_currency=None,
        budget_min=None, budget_max=None, required_by=None,
        preferred_transaction="UNKNOWN",
    )
    d.update(kw)
    return RequirementInput(**d)


def offer(txn="PURCHASE", status="AVAILABLE", geo=True, cur=True, avail=None) -> OfferInput:
    return OfferInput(
        transaction_type=txn, availability_status=status, is_current=cur,
        region_code=None, geo_applicable=geo, available_from=avail,
    )


def price(txn="PURCHASE", ptype="PUBLIC", cur="USD", amount=None, pmin=None, pmax=None,
          period="ONE_TIME", geo=True) -> PriceInput:
    return PriceInput(
        transaction_type=txn, price_type=ptype, currency=cur, price=amount,
        price_min=pmin, price_max=pmax, billing_period=period, is_current=True,
        geo_applicable=geo,
    )


def slugs(outcome):
    return [m.slug for m in outcome.matches]


# ---- E1 / E8 + hard exclusions ------------------------------------------

def test_e1_payload_below_requirement_excluded() -> None:
    r = robot("small", payload_kg=3.0)
    out = match(req(payload_min_kg=12), [r])
    assert slugs(out) == []
    assert out.no_match_explanation and "payload" in out.no_match_explanation.lower()


def test_e8_discontinued_excluded() -> None:
    disc = robot("old", commercial_status="DISCONTINUED", payload_kg=50)
    assert slugs(match(req(payload_min_kg=1), [disc])) == []


def test_manipulation_required_known_false_excluded() -> None:
    ex = exclusion_reason
    assert ex(req(manipulation_required=True), robot(has_manipulation=False)) == "manipulation"
    # unknown does NOT exclude
    assert ex(req(manipulation_required=True), robot(has_manipulation=None)) is None
    # false requirement is not a constraint
    assert ex(req(manipulation_required=False), robot(has_manipulation=False)) is None


def test_autonomy_below_excluded_unknown_passes() -> None:
    ex = exclusion_reason
    assert ex(req(autonomy_required="TASK_AUTONOMOUS"), robot(autonomy="ASSISTED")) == "autonomy"
    assert ex(req(autonomy_required="TASK_AUTONOMOUS"), robot(autonomy=None)) is None
    assert ex(req(autonomy_required="ASSISTED"), robot(autonomy="HIGHLY_AUTONOMOUS")) is None


# ---- E2 / UNKNOWN never excludes and scores 0.5 -------------------------

def test_e2_unknown_payload_not_excluded_scores_neutral_with_warning() -> None:
    r = robot("u", payload_kg=None)
    out = match(req(payload_min_kg=12), [r])
    assert slugs(out) == ["u"]
    m = out.matches[0]
    assert "payload unverified" in m.warnings


def test_unknown_scores_half_on_every_axis() -> None:
    # use_case fit missing, autonomy/manip/runtime unknown, quote-only price, no geo.
    r = robot("u", commercial_status="COMMERCIAL")
    out = match(
        req(use_case="warehouse-logistics", country="DE", autonomy_required="ASSISTED",
            manipulation_required=True, operating_hours_day=16, budget_currency="USD",
            budget_max=100000),
        [r],
    )
    w = out.matches[0].warnings
    assert "use-case fit for warehouse-logistics is unverified" in w
    assert "autonomy level unverified" in w
    assert "manipulation capability unverified" in w
    assert "runtime unverified" in w
    assert any("no confirmed commercial availability" in x for x in w)
    assert any("DE" in x for x in w)  # geography evidence missing


# ---- E3 byte-identical -----------------------------------------------------

def test_e3_repeatable_byte_identical() -> None:
    rs = [robot("a", payload_kg=20, use_case_fit=0.9, offers=(offer(),)),
          robot("b", payload_kg=10, use_case_fit=0.4)]
    r1 = req(use_case="warehouse-logistics", payload_min_kg=8)
    assert match(r1, rs) == match(r1, list(rs))


# ---- E6 score == Σ breakdown, >= 2 reasons -----------------------------

def test_e6_score_equals_breakdown_sum_and_two_reasons() -> None:
    r = robot("a", payload_kg=20, use_case_fit=0.9, deployment_count=2,
              offers=(offer(),))
    out = match(req(use_case="warehouse-logistics", payload_min_kg=12), [r])
    m = out.matches[0]
    assert m.score == round(sum(m.breakdown.values()))
    assert set(m.breakdown) == {
        "use_case_fit", "commercial_availability", "technical_fit",
        "geographic_fit", "budget_fit", "deployment_readiness",
    }
    assert len(m.reasons) >= 2


# ---- E7 deterministic empty explanation --------------------------------

def test_e7_all_excluded_gives_dominant_explanation() -> None:
    rs = [robot("a", payload_kg=1), robot("b", payload_kg=2),
          robot("c", commercial_status="DISCONTINUED")]
    out = match(req(payload_min_kg=50), rs)
    assert out.matches == ()
    # payload eliminated 2, discontinued 1 -> payload is dominant.
    assert "payload" in out.no_match_explanation.lower()
    assert out.excluded_count == 3


# ---- weight redistribution ---------------------------------------------

def test_weight_redistribution_only_active_criteria_sum_to_100() -> None:
    # Only commercial + deployment active (nothing stated). Perfect on both.
    r = robot("a", commercial_status="COMMERCIAL", deployment_count=1, offers=(offer(),))
    out = match(req(), [r])
    m = out.matches[0]
    # inactive criteria contribute 0.
    for k in ("use_case_fit", "technical_fit", "geographic_fit", "budget_fit"):
        assert m.breakdown[k] == 0.0
    # commercial 1.0 and deployment (0.5*1 + 0.5*1)=1.0, weights 20/10 -> 66.67/33.33
    assert m.breakdown["commercial_availability"] == 66.67
    assert m.breakdown["deployment_readiness"] == 33.33
    assert m.score == 100


# ---- payload ramp ------------------------------------------------------

def test_payload_ramp_meets_min_scores_0_8_headroom_scores_1() -> None:
    # only payload active -> technical == payload_fit; check the raw subscore via breakdown.
    at_min = match(req(payload_min_kg=12), [robot("a", payload_kg=12, offers=(offer(),))])
    head = match(req(payload_min_kg=12), [robot("a", payload_kg=15, offers=(offer(),))])
    # active = commercial(20)+deployment(10)+technical(20) => factor 2 => tech eff 40
    assert at_min.matches[0].breakdown["technical_fit"] == round(0.8 * 40, 2)
    assert head.matches[0].breakdown["technical_fit"] == round(1.0 * 40, 2)


def test_zero_payload_requirement_scores_full() -> None:
    out = match(req(payload_min_kg=0), [robot("a", payload_kg=None, offers=(offer(),))])
    assert out.matches[0].breakdown["technical_fit"] == round(1.0 * 40, 2)


# ---- budget ramp (linear, not a cliff) ---------------------------------

def _budget_fit(amount: float) -> float:
    r = robot("a", prices=(price(amount=amount),), offers=(offer(),))
    out = match(req(budget_currency="USD", budget_max=100000, preferred_transaction="BUY"), [r])
    return out.matches[0].breakdown["budget_fit"]


def test_budget_linear_ramp_to_110pct() -> None:
    # active = commercial(20)+deployment(10)+budget(10) => factor 2.5 => budget eff 25
    assert _budget_fit(100000) == round(1.0 * 25, 2)
    assert _budget_fit(105000) == round(0.5 * 25, 2)
    assert _budget_fit(110000) == 0.0
    assert _budget_fit(200000) == 0.0


def test_quote_only_against_budget_is_neutral() -> None:
    r = robot("a", prices=(price(ptype="QUOTE_ONLY", amount=None),), offers=(offer(),))
    out = match(req(budget_currency="USD", budget_max=100000, preferred_transaction="BUY"), [r])
    m = out.matches[0]
    assert m.breakdown["budget_fit"] == round(0.5 * 25, 2)
    assert "pricing is quote-only" in m.warnings


# ---- deterministic tie chain -------------------------------------------

def test_tie_chain_commercial_then_deployment_then_verified_then_slug() -> None:
    fresh = datetime(2026, 6, 1, tzinfo=UTC)
    old = datetime(2020, 1, 1, tzinfo=UTC)
    # All four score identically on use-case only (0.9), differ only on tie keys.
    base = dict(use_case_fit=0.9)
    a = robot("a", **base, offers=(offer(status="ON_REQUEST"),))   # commercial 1.0
    b = robot("b", **base, deployment_count=5)                     # commercial 0.5, dep 5
    c = robot("c", **base, freshest_verified_at=fresh)
    d = robot("d", **base, freshest_verified_at=old)
    out = match(req(use_case="warehouse-logistics"), [d, c, b, a])
    # a wins on commercial subscore; then b (more deployments); then c (fresher) ; then d
    assert slugs(out) == ["a", "b", "c", "d"]


def test_pure_slug_tiebreak_when_all_else_equal() -> None:
    rs = [robot("zebra", use_case_fit=0.9), robot("alpha", use_case_fit=0.9)]
    assert slugs(match(req(use_case="warehouse-logistics"), rs)) == ["alpha", "zebra"]


# ---- shortlist size + categories ----------------------------------------

def test_at_most_four_survivors_no_padding_with_excluded() -> None:
    good = [robot(f"g{i}", use_case_fit=0.9 - i * 0.05, offers=(offer(),)) for i in range(6)]
    excluded_one = robot("bad", payload_kg=1)
    out = match(req(use_case="warehouse-logistics", payload_min_kg=99), good + [excluded_one])
    assert len(out.matches) == 4
    assert "bad" not in slugs(out)


def test_categories_best_overall_then_labels() -> None:
    a = robot("a", use_case_fit=0.95, offers=(offer(),), prices=(price(amount=1000),),
              deployment_count=2)
    b = robot("b", use_case_fit=0.9, offers=(offer(status="AVAILABLE"),))  # commercial
    c = robot("c", use_case_fit=0.85, has_sdk=True)                        # developer
    out = match(req(use_case="warehouse-logistics", budget_currency="USD",
                    budget_max=5000, preferred_transaction="BUY"), [a, b, c])
    cats = {m.slug: m.category for m in out.matches}
    assert cats["a"] == "BEST_OVERALL"
    assert set(cats.values()) >= {"BEST_OVERALL"}
    assert "BEST_COMMERCIAL" in cats.values() or "BEST_LOWER_COST" in cats.values()


# ---- correction 1: BEST_COMMERCIAL requires an accessible offer ---------

def test_best_commercial_requires_accessible_offer_not_just_subscore() -> None:
    a = robot("a", use_case_fit=0.99, offers=(offer(),))          # rank 1
    b = robot("b", use_case_fit=0.80, offers=(offer(status="ON_REQUEST"),))  # accessible
    c = robot("c", use_case_fit=0.79)                             # NO offer -> 0.5, not accessible
    out = match(req(use_case="warehouse-logistics"), [a, b, c])
    cats = {m.slug: m.category for m in out.matches}
    assert cats["b"] == "BEST_COMMERCIAL"      # ON_REQUEST is accessible
    assert cats["c"] != "BEST_COMMERCIAL"      # no confirmed availability -> never


def test_constrained_statuses_stay_commercially_eligible() -> None:
    for status in ("ON_REQUEST", "WAITLIST", "LIMITED", "PREORDER"):
        a = robot("a", use_case_fit=0.99, offers=(offer(),))
        b = robot("b", use_case_fit=0.80, offers=(offer(status=status),))
        out = match(req(use_case="warehouse-logistics"), [a, b])
        cats = {m.slug: m.category for m in out.matches}
        assert cats["b"] == "BEST_COMMERCIAL", status


# ---- correction 2: BEST_LOWER_COST is a real lowest numeric price -------

def test_best_lower_cost_picks_lowest_known_numeric_price() -> None:
    a = robot("a", use_case_fit=0.99, offers=(offer(),))                 # rank 1
    cheap = robot("cheap", use_case_fit=0.80, prices=(price(amount=10000),))
    exp = robot("exp", use_case_fit=0.81, prices=(price(amount=90000),))
    out = match(req(use_case="warehouse-logistics", preferred_transaction="BUY"),
                [a, cheap, exp])
    cats = {m.slug: m.category for m in out.matches}
    assert cats["cheap"] == "BEST_LOWER_COST"   # 10k beats 90k, not slug order


def test_quote_only_never_best_lower_cost() -> None:
    a = robot("a", use_case_fit=0.99, offers=(offer(),))
    q = robot("q", use_case_fit=0.80, prices=(price(ptype="QUOTE_ONLY", amount=None),))
    out = match(req(use_case="warehouse-logistics", preferred_transaction="BUY"), [a, q])
    cats = {m.slug: m.category for m in out.matches}
    assert cats.get("q") != "BEST_LOWER_COST"


def test_mixed_currencies_yield_no_best_lower_cost_without_buyer_currency() -> None:
    a = robot("a", use_case_fit=0.99, offers=(offer(),))
    usd = robot("usd", use_case_fit=0.80, prices=(price(amount=10000, cur="USD"),))
    eur = robot("eur", use_case_fit=0.81, prices=(price(amount=9000, cur="EUR"),))
    out = match(req(use_case="warehouse-logistics", preferred_transaction="BUY"),
                [a, usd, eur])
    assert "BEST_LOWER_COST" not in {m.category for m in out.matches}  # no FX


# ---- correction 3: geography must not leak across transaction modes ------

def _offer(txn, status, region, geo, avail=None) -> OfferInput:
    return OfferInput(
        transaction_type=txn, availability_status=status, is_current=True,
        region_code=region, geo_applicable=geo, available_from=avail,
    )


def test_geography_does_not_leak_across_transaction_modes() -> None:
    # Buyer wants RENT in DE; RENTAL only in US, PURCHASE available in DE.
    r = robot("r", offers=(
        _offer("RENTAL", "AVAILABLE", "US", geo=False),
        _offer("PURCHASE", "AVAILABLE", "DE", geo=True),
    ))
    out = match(req(country="DE", preferred_transaction="RENT"), [r])
    # geo active with commercial(20)+geo(15)+deployment(10)=45 => geo eff 33.33.
    assert out.matches[0].breakdown["geographic_fit"] == round(0.5 * (15 * 100 / 45), 2)


def test_geography_negative_only_when_transaction_matches() -> None:
    r = robot("r", offers=(
        _offer("RENTAL", "NOT_AVAILABLE", "DE", geo=True),
        _offer("PURCHASE", "AVAILABLE", "DE", geo=True),
    ))
    out = match(req(country="DE", preferred_transaction="RENT"), [r])
    # The applicable RENTAL DE offer is not accessible -> 0.0, PURCHASE can't rescue it.
    assert out.matches[0].breakdown["geographic_fit"] == 0.0


# ---- correction 4: multi-price budget is order-independent ---------------

def test_budget_evaluation_is_order_independent() -> None:
    p1 = price(ptype="QUOTE_ONLY", amount=None)
    p2 = price(amount=5000, period="MONTHLY")
    r = req(use_case="warehouse-logistics", budget_currency="USD", budget_max=100000,
            preferred_transaction="BUY")
    a = match(r, [robot("r", use_case_fit=0.9, offers=(offer(),), prices=(p1, p2))])
    b = match(r, [robot("r", use_case_fit=0.9, offers=(offer(),), prices=(p2, p1))])
    assert a == b  # identical score, reasons AND warnings regardless of price order


# ---- correction 5: count ALL violations for the dominant constraint -----

def test_no_match_explanation_counts_all_violations() -> None:
    both = [robot(f"b{i}", payload_kg=1, autonomy="TELEOPERATED") for i in range(6)]
    auto = [robot(f"a{i}", payload_kg=None, autonomy="TELEOPERATED") for i in range(5)]
    out = match(req(payload_min_kg=50, autonomy_required="HIGHLY_AUTONOMOUS"), both + auto)
    assert out.matches == ()
    # autonomy=11 (6 both + 5 auto), payload=6 -> autonomy dominates, not payload.
    assert "autonomy" in out.no_match_explanation.lower()


# ---- correction 6: reasons are genuine, never manufacturer/tracking filler

def test_sparse_reasons_are_genuine_and_at_least_two() -> None:
    r = robot("r", commercial_status="COMMERCIAL", offers=(offer(status="ON_REQUEST"),))
    out = match(req(use_case="warehouse-logistics"), [r])
    m = out.matches[0]
    assert len(m.reasons) >= 2
    joined = " ".join(m.reasons).lower()
    assert "tracked platform" not in joined
    assert "maker" not in joined  # no manufacturer-name filler


# ---- final-1: every survivor gets >= 2 genuine reasons ------------------

def _no_filler(reasons) -> bool:
    joined = " ".join(reasons).lower()
    return "tracked platform" not in joined and "maker" not in joined


def test_completely_sparse_survivor_has_two_genuine_reasons() -> None:
    # No offers, no deployments, no fits; buyer states nothing.
    out = match(req(), [robot("r", commercial_status="COMMERCIAL")])
    m = out.matches[0]
    assert len(m.reasons) >= 2 and _no_filler(m.reasons)


def test_late_accessible_offer_still_has_two_reasons() -> None:
    r = robot("r", offers=(offer(status="AVAILABLE", avail=date(2030, 1, 1)),))
    out = match(req(required_by=date(2026, 1, 1)), [r])
    m = out.matches[0]
    assert len(m.reasons) >= 2 and _no_filler(m.reasons)
    assert any("commercially accessible" in x for x in m.reasons)  # accessibility fact kept


def test_runtime_only_requirement_has_two_reasons() -> None:
    r = robot("r", runtime_minutes=600)  # >= 8h*60
    out = match(req(operating_hours_day=8), [r])
    m = out.matches[0]
    assert len(m.reasons) >= 2 and _no_filler(m.reasons)
    assert any("runtime covers" in x for x in m.reasons)


# ---- final-2: over-budget numeric prices warn ---------------------------

def _budget_case(**price_kw):
    r = robot("a", offers=(offer(),), prices=(price(**price_kw),))
    out = match(req(budget_currency="USD", budget_max=100000, preferred_transaction="BUY"), [r])
    return out.matches[0]


def test_public_over_budget_warns_and_ramps() -> None:
    m105 = _budget_case(amount=105000)
    assert m105.breakdown["budget_fit"] == round(0.5 * 25, 2)  # ramp, not a cliff
    assert "price exceeds the stated budget" in m105.warnings
    m110 = _budget_case(amount=110000)
    assert m110.breakdown["budget_fit"] == 0.0
    assert "price exceeds the stated budget" in m110.warnings


def test_range_starting_above_budget_warns() -> None:
    m = _budget_case(ptype="RANGE", amount=None, pmin=105000, pmax=150000)
    assert m.breakdown["budget_fit"] == round(0.5 * 25, 2)  # ramp on price_min
    assert "price range starts above the stated budget" in m.warnings


# ---- final-3: full-reference mixed-currency blocks BEST_LOWER_COST -------

def test_single_robot_with_two_currencies_blocks_lower_cost() -> None:
    a = robot("a", use_case_fit=0.99, offers=(offer(),))
    b = robot("b", use_case_fit=0.80,
              prices=(price(amount=10000, cur="USD"), price(amount=9000, cur="EUR")))
    out = match(req(use_case="warehouse-logistics", preferred_transaction="BUY"), [a, b])
    assert "BEST_LOWER_COST" not in {m.category for m in out.matches}


def test_disjoint_currency_union_blocks_lower_cost() -> None:
    a = robot("a", use_case_fit=0.99, offers=(offer(),))
    b = robot("b", use_case_fit=0.80,
              prices=(price(amount=9000, cur="EUR"), price(amount=10000, cur="USD")))
    c = robot("c", use_case_fit=0.79,
              prices=(price(amount=8000, cur="EUR"), price(amount=7000, cur="GBP")))
    out = match(req(use_case="warehouse-logistics", preferred_transaction="BUY"), [a, b, c])
    assert "BEST_LOWER_COST" not in {m.category for m in out.matches}


# ---- final-2a: currency comparison spans ALL ranks 2-4 (incl. taken) -----

def test_lower_cost_currency_universe_includes_taken_commercial_winner() -> None:
    a = robot("a", use_case_fit=0.99, offers=(offer(),))  # rank 1
    # rank 2: accessible + USD-priced -> becomes BEST_COMMERCIAL (taken).
    r2 = robot("r2", use_case_fit=0.90, offers=(offer(status="AVAILABLE"),),
               prices=(price(amount=10000, cur="USD"),))
    # rank 3: EUR-priced, not accessible.
    r3 = robot("r3", use_case_fit=0.80, prices=(price(amount=8000, cur="EUR"),))
    out = match(req(use_case="warehouse-logistics", preferred_transaction="BUY"), [a, r2, r3])
    cats = {m.slug: m.category for m in out.matches}
    assert cats["r2"] == "BEST_COMMERCIAL"
    # USD (taken r2) + EUR (r3) across ranks 2-4 -> incomparable -> NO label.
    assert "BEST_LOWER_COST" not in cats.values()


# ---- final-2b: maturity never implies obtainability ---------------------

def test_maturity_reason_never_implies_obtainability() -> None:
    out = match(req(), [robot("r", commercial_status="COMMERCIAL")])  # no availability offer
    m = out.matches[0]
    joined = " ".join(m.reasons).lower()
    assert "commercial maturity: commercial" in joined       # maturity stated verbatim
    assert any("unconfirmed" in x for x in m.reasons)         # neutral availability explanation
    assert "no confirmed commercial availability" in m.warnings
    # maturity must NOT be translated into an obtainability claim.
    assert "generally commercially available" not in joined
    assert "obtainable" not in joined


def test_commercial_maturity_with_not_available_offer_is_not_contradictory() -> None:
    r = robot("r", commercial_status="COMMERCIAL", offers=(offer(status="NOT_AVAILABLE"),))
    out = match(req(preferred_transaction="BUY"), [r])
    m = out.matches[0]
    joined = " ".join(m.reasons).lower()
    assert "commercial maturity: commercial" in joined
    assert any("no accessible commercial offer" in x for x in m.reasons)
    assert "commercially available" not in joined  # no contradictory obtainability wording


# ---- final-4: no-match wording is quantified, not absolute ---------------

def test_no_match_wording_is_quantified_not_absolute() -> None:
    payloaders = [robot(f"p{i}", payload_kg=1) for i in range(6)]
    disc = [robot(f"d{i}", commercial_status="DISCONTINUED", payload_kg=50) for i in range(5)]
    out = match(req(payload_min_kg=40), payloaders + disc)
    assert out.matches == ()
    expl = out.no_match_explanation
    assert expl.lower().startswith("no platform matched")
    assert "every" not in expl.lower()       # dominant eliminated a subset, not all
    assert "6 of 11 candidates" in expl      # quantified


# ---- required-by soft penalty (never a hard exclude) --------------------

def test_required_by_soft_penalty_not_exclusion() -> None:
    late = robot("late", offers=(offer(status="AVAILABLE", avail=date(2030, 1, 1)),))
    out = match(req(required_by=date(2026, 1, 1)), [late])
    assert slugs(out) == ["late"]  # not excluded
    m = out.matches[0]
    # Only commercial(20)+deployment(10) active -> commercial eff weight 66.67;
    # the soft penalty halves the subscore (0.5), so 33.33 not the full 66.67.
    assert m.breakdown["commercial_availability"] == 33.33
    assert any("after the required-by" in w for w in m.warnings)
