"""Deterministic fixture tests for the regional availability read model (ADR-027 Step 2).

Pure: no database, clock, network or randomness. Synthetic fixtures pin each rule;
one block loads the real catalogue files and asserts invariants only.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services.regional_research.inputs import (
    DeploymentRow,
    EvidenceRow,
    OfferRow,
    PriceRow,
    RegionalSnapshot,
    RegionNode,
    RobotRow,
)
from app.services.regional_research.readmodel import (
    CONFIRMED_NOT_OBTAINABLE,
    GLOBAL_ONLY,
    NO_OFFERS,
    OFFER_WITHOUT_EVIDENCE,
    OTHER_REGION_ONLY,
    PRICE_ONLY,
    QUALIFYING,
    STALE_OR_NON_CURRENT,
    UNRESOLVED_REGION,
    build_regional_availability,
    region_members,
)

SNAP = date(2026, 10, 4)

REGIONS = (
    RegionNode("GLOBAL", "Global", None),
    RegionNode("EUROPE", "Europe", None),
    RegionNode("EU", "European Union", "EUROPE"),
    RegionNode("DE", "Germany", "EU"),
    RegionNode("BG", "Bulgaria", "EU"),
    RegionNode("UK", "United Kingdom", "EUROPE"),
    RegionNode("US", "United States", None),
    RegionNode("TR", "Türkiye", None),
)


def ev(days_old: int = 10, *, conf: str = "MEDIUM", verified: bool = False, url: str = "https://x.example/p"):
    d = SNAP - timedelta(days=days_old)
    return EvidenceRow(url, conf, observed_at=d, verified_at=d if verified else None)


def offer(region="DE", status="AVAILABLE", tx="PURCHASE", *, current=True, evidence=None,
          provider="shop", ptype="DISTRIBUTOR"):
    return OfferRow(provider, ptype, region, tx, status, current,
                    (ev(),) if evidence is None else tuple(evidence))


def price(region="DE", ptype="PUBLIC", amount=1000.0, *, tx="PURCHASE", cur="EUR", basis="incl VAT",
          current=True, evidence=None, provider="shop", pmin=None, pmax=None, period="ONE_TIME"):
    return PriceRow(provider, region, tx, ptype, cur, amount, pmin, pmax, period, basis, current,
                    (ev(),) if evidence is None else tuple(evidence))


def robot(slug, *, maker="m1", published=True, offers=(), prices=()):
    return RobotRow(slug, slug.title(), maker, maker.title(), published, "COMMERCIAL",
                    tuple(offers), tuple(prices))


def snap(*robots, regions=REGIONS):
    return RegionalSnapshot(SNAP, regions, tuple(robots))


def build(*robots, **kw):
    return build_regional_availability(snap(*robots), "EUROPE", **kw)


def group_of(result, slug):
    return next(g.reason for g in result.groups if any(r.slug == slug for r in g.robots))


# --- region membership --------------------------------------------------------

def test_members_are_the_region_and_all_descendants_never_global():
    assert region_members(REGIONS, "EUROPE") == {"EUROPE", "EU", "DE", "BG", "UK"}
    assert region_members(REGIONS, "EU") == {"EU", "DE", "BG"}
    assert "GLOBAL" not in region_members(REGIONS, "EUROPE")
    assert "TR" not in region_members(REGIONS, "EUROPE")


def test_unknown_region_is_an_error_not_an_empty_page():
    with pytest.raises(ValueError):
        region_members(REGIONS, "ATLANTIS")


def test_region_tree_cycles_do_not_hang():
    cyc = (RegionNode("A", "A", "B"), RegionNode("B", "B", "A"))
    assert region_members(cyc, "A") == {"A", "B"}


def test_eu_zone_offer_and_country_offer_both_count_as_europe():
    r = build(robot("a", offers=[offer("EU")]), robot("b", offers=[offer("BG")]))
    assert {o.robot_slug for o in r.qualifying_offers} == {"a", "b"}


# --- population ----------------------------------------------------------------

def test_unpublished_robots_never_appear_anywhere():
    r = build(robot("pub", offers=[offer()]),
              robot("secret-unpublished", published=False, offers=[offer()]))
    assert r.key_figures.population == 1
    assert "secret-unpublished" not in repr(r)


# --- what qualifies --------------------------------------------------------------

def test_a_current_evidenced_fresh_obtainable_regional_offer_qualifies():
    r = build(robot("a", offers=[offer()]))
    assert group_of(r, "a") == QUALIFYING
    assert r.qualifying_offers[0].region_code == "DE"


@pytest.mark.parametrize("kwargs,expected", [
    (dict(current=False), STALE_OR_NON_CURRENT),
    (dict(evidence=[ev(91)]), STALE_OR_NON_CURRENT),
    (dict(evidence=[]), OFFER_WITHOUT_EVIDENCE),
    (dict(status="NOT_AVAILABLE"), CONFIRMED_NOT_OBTAINABLE),
    (dict(status="DISCONTINUED"), CONFIRMED_NOT_OBTAINABLE),
])
def test_each_disqualifier_lands_in_its_own_group(kwargs, expected):
    r = build(robot("a", offers=[offer(**kwargs)]))
    assert group_of(r, "a") == expected
    assert r.key_figures.qualifying_robots == 0


def test_freshness_boundary_is_90_days_inclusive():
    assert group_of(build(robot("a", offers=[offer(evidence=[ev(90)])])), "a") == QUALIFYING
    stale = build(robot("a", offers=[offer(evidence=[ev(91)])]))
    assert group_of(stale, "a") == STALE_OR_NON_CURRENT


def test_freshness_is_configurable():
    r = build(robot("a", offers=[offer(evidence=[ev(40)])]), freshness_days=30)
    assert group_of(r, "a") == STALE_OR_NON_CURRENT


def test_evidence_dated_after_the_snapshot_is_not_fresh():
    future = EvidenceRow("https://x.example", "MEDIUM", observed_at=SNAP + timedelta(days=1))
    r = build(robot("a", offers=[offer(evidence=[future])]))
    assert group_of(r, "a") == STALE_OR_NON_CURRENT


def test_freshness_uses_verified_at_when_present_else_observed_at():
    old_observed_new_verified = EvidenceRow(
        "https://x.example", "HIGH",
        observed_at=SNAP - timedelta(days=200), verified_at=SNAP - timedelta(days=5))
    r = build(robot("a", offers=[offer(evidence=[old_observed_new_verified])]))
    assert group_of(r, "a") == QUALIFYING


def test_one_fresh_evidence_row_is_enough_when_another_is_old():
    r = build(robot("a", offers=[offer(evidence=[ev(300), ev(5)])]))
    assert group_of(r, "a") == QUALIFYING
    assert r.qualifying_offers[0].evidence_date == SNAP - timedelta(days=5)


# --- GLOBAL, price-only, other regions, unresolved ---------------------------------

def test_global_offer_is_never_regional_availability():
    r = build(robot("g", offers=[offer("GLOBAL")], prices=[price("GLOBAL")]))
    assert group_of(r, "g") == GLOBAL_ONLY
    assert r.key_figures.qualifying_robots == 0
    assert r.gate.qualifying_robots == 0


def test_price_row_alone_never_qualifies():
    r = build(robot("p", prices=[price("DE")]))
    assert group_of(r, "p") == PRICE_ONLY
    assert r.key_figures.qualifying_robots == 0


def test_offer_in_another_region_is_other_region_only():
    assert group_of(build(robot("u", offers=[offer("US")])), "u") == OTHER_REGION_ONLY
    assert group_of(build(robot("t", offers=[offer("TR")])), "t") == OTHER_REGION_ONLY


def test_null_region_offer_is_unresolved_never_europe():
    r = build(robot("n", offers=[offer(None, "WAITLIST")], prices=[price(None)]))
    assert group_of(r, "n") == UNRESOLVED_REGION
    assert r.key_figures.qualifying_robots == 0


def test_no_offers_at_all_is_its_own_group():
    assert group_of(build(robot("z")), "z") == NO_OFFERS


# --- missing offer is not NOT_AVAILABLE ------------------------------------------------

def test_missing_offer_is_never_reported_as_not_available():
    r = build(robot("z"), robot("p", prices=[price("DE")]),
              robot("a", offers=[offer()]))
    assert "NOT_AVAILABLE" not in repr(r)
    assert "not available" not in r.direct_answer.lower()
    assert "no confirmed Europe offer on file" in r.direct_answer


def test_evidenced_not_available_row_is_distinct_and_not_counted():
    r = build(robot("x", offers=[offer(status="NOT_AVAILABLE")]), robot("a", offers=[offer()]))
    assert group_of(r, "x") == CONFIRMED_NOT_OBTAINABLE
    assert r.key_figures.qualifying_robots == 1


# --- UNKNOWN stays UNKNOWN ------------------------------------------------------------------

def _prices_of(result, slug):
    return next(o for o in result.qualifying_offers if o.robot_slug == slug).prices


def test_no_price_is_not_published_never_zero():
    r = build(robot("a", offers=[offer()]))
    (p,) = _prices_of(r, "a")
    assert p.kind == "NOT_PUBLISHED" and p.amount is None
    assert r.key_figures.purchase_robots_price_not_published == 1


def test_null_amount_on_a_public_price_row_is_not_published():
    r = build(robot("a", offers=[offer()], prices=[price(amount=None)]))
    assert _prices_of(r, "a")[0].kind == "NOT_PUBLISHED"


def test_quote_only_is_price_on_request_not_unknown_not_zero():
    r = build(robot("a", offers=[offer()], prices=[price(ptype="QUOTE_ONLY", amount=None)]))
    (p,) = _prices_of(r, "a")
    assert p.kind == "PRICE_ON_REQUEST" and p.amount is None
    assert r.key_figures.purchase_robots_price_on_request == 1


def test_estimates_are_never_counted_as_a_published_price():
    r = build(robot("a", offers=[offer()],
                    prices=[price(ptype="MANUFACTURER_ESTIMATE", amount=19999.0)]))
    assert _prices_of(r, "a")[0].kind == "ESTIMATE"
    assert r.key_figures.purchase_robots_with_published_price == 0


def test_price_without_fresh_evidence_or_not_current_is_not_published():
    r = build(robot("a", offers=[offer()],
                    prices=[price(evidence=[]), price(evidence=[ev(200)]), price(current=False)]))
    assert [p.kind for p in _prices_of(r, "a")] == ["NOT_PUBLISHED"]


def test_price_must_match_the_offers_provider_region_and_transaction():
    r = build(robot("a", offers=[offer("DE", provider="shop")],
                    prices=[price("BG"), price("DE", provider="other"), price("DE", tx="RENTAL")]))
    assert _prices_of(r, "a")[0].kind == "NOT_PUBLISHED"


def test_weekly_rental_price_is_kept_apart_from_purchase_price():
    r = build(robot("a", offers=[offer(tx="RENTAL")],
                    prices=[price(tx="RENTAL", amount=6500.0, period="WEEKLY")]))
    (p,) = _prices_of(r, "a")
    assert (p.kind, p.billing_period, p.amount) == ("PUBLISHED", "WEEKLY", 6500.0)
    assert r.key_figures.purchase_robots == 0


# --- confidence is never upgraded --------------------------------------------------------------

def test_offer_reports_weakest_in_window_confidence_and_no_false_verification():
    r = build(robot("a", offers=[offer(evidence=[ev(5, conf="VERIFIED", verified=True),
                                                  ev(6, conf="MEDIUM")])]))
    o = r.qualifying_offers[0]
    assert o.confidence == "MEDIUM"
    assert o.human_verified is False


def test_human_verified_only_when_every_in_window_row_is_verified():
    r = build(robot("a", offers=[offer(evidence=[ev(5, conf="VERIFIED", verified=True)])]))
    o = r.qualifying_offers[0]
    assert (o.confidence, o.human_verified) == ("VERIFIED", True)


def test_an_old_weak_row_does_not_downgrade_a_fresh_strong_one():
    r = build(robot("a", offers=[offer(evidence=[ev(5, conf="HIGH"), ev(400, conf="LOW")])]))
    assert r.qualifying_offers[0].confidence == "HIGH"


# --- reconciliation and gate ---------------------------------------------------------------------

def _mixed_population():
    return [
        robot("q1", maker="a", offers=[offer()]),
        robot("q2", maker="b", offers=[offer("EU", "ON_REQUEST")]),
        robot("q3", maker="c", offers=[offer("BG", "WAITLIST")]),
        robot("stale", offers=[offer(current=False)]),
        robot("noev", offers=[offer(evidence=[])]),
        robot("na", offers=[offer(status="NOT_AVAILABLE")]),
        robot("unres", offers=[offer(None)]),
        robot("ponly", prices=[price()]),
        robot("glob", offers=[offer("GLOBAL")]),
        robot("us", offers=[offer("US")]),
        robot("none"),
        robot("hidden", published=False, offers=[offer()]),
    ]


def test_groups_reconcile_to_the_published_population():
    r = build(*_mixed_population())
    assert r.reconciles
    assert sum(g.count for g in r.groups) == r.key_figures.population == 11
    assert [g.count for g in r.groups] == [3, 1, 1, 1, 1, 1, 1, 1, 1]
    assert r.key_figures.no_confirmed_offer == 8


def test_gate_passes_at_the_adopted_minimum_and_reports_failures_below_it():
    ok = build(*_mixed_population(), min_robots=3, min_manufacturers=3)
    assert ok.gate.passes and ok.gate.failures == ()
    low = build(*_mixed_population())  # defaults: 5 robots / 3 manufacturers
    assert not low.gate.passes
    assert low.gate.failures == ("qualifying robots 3 < 5",)


def test_gate_needs_manufacturer_diversity_not_just_robot_count():
    same_maker = [robot(f"r{i}", maker="solo", offers=[offer()]) for i in range(6)]
    g = build(*same_maker).gate
    assert not g.passes
    assert g.qualifying_robots == 6 and g.qualifying_manufacturers == 1
    assert g.failures == ("qualifying manufacturers 1 < 3",)


# --- determinism ---------------------------------------------------------------------------------

def test_output_is_independent_of_input_order_and_repeatable():
    robots = _mixed_population()
    base = build(*robots)
    for seed in range(5):
        shuffled = robots[:]
        random.Random(seed).shuffle(shuffled)
        assert build(*shuffled) == base
    assert build(*robots) == base


def test_offer_and_evidence_order_does_not_change_output():
    a = robot("a", offers=[offer("DE"), offer("BG", "ON_REQUEST")],
              prices=[price("DE", amount=2.0), price("DE", amount=1.0)])
    b = robot("a", offers=[offer("BG", "ON_REQUEST"), offer("DE")],
              prices=[price("DE", amount=1.0), price("DE", amount=2.0)])
    assert build(a) == build(b)


# --- direct answer -------------------------------------------------------------------------------

def test_direct_answer_exact_text_for_a_known_fixture():
    r = build(
        robot("a", maker="a", offers=[offer("DE", "AVAILABLE")],
              prices=[price("DE", amount=9930.0)]),
        robot("b", maker="b", offers=[offer("EU", "ON_REQUEST")],
              prices=[price("EU", amount=11731.49)]),
        robot("c", maker="c", offers=[offer("BG", "AVAILABLE", tx="RENTAL")]),
        robot("d"),
    )
    assert r.direct_answer == (
        "As of 2026-10-04, HumanoidOnline lists 3 published humanoid robots with a confirmed "
        "offer in Europe. 2 can be purchased: 1 available and 1 on request. "
        "2 of the 2 purchasable robots have a published purchase price (9,930–11,731.49 EUR). "
        "Additionally, 1 of these robots has a confirmed rental offer. "
        "1 other published robot has no confirmed Europe offer on file. "
        "Evidence sources, confidence and observation dates are listed below."
    )


def test_price_range_is_omitted_when_currencies_differ():
    r = build(robot("a", offers=[offer("DE")], prices=[price("DE", cur="EUR")]),
              robot("b", offers=[offer("BG")], prices=[price("BG", cur="USD")]))
    assert "published purchase price." in r.direct_answer
    assert "(" not in r.direct_answer.split("published purchase price")[1].split(".")[0]


def test_price_range_is_omitted_when_price_basis_differs_or_is_unstated():
    differing = build(robot("a", offers=[offer("DE")], prices=[price("DE", basis="incl VAT")]),
                      robot("b", offers=[offer("BG")], prices=[price("BG", basis="excl VAT")]))
    unstated = build(robot("a", offers=[offer("DE")], prices=[price("DE", basis=None)]))
    for r in (differing, unstated):
        assert "–" not in r.direct_answer and "EUR)" not in r.direct_answer


def test_single_price_renders_without_a_range():
    r = build(robot("a", offers=[offer()], prices=[price(amount=9930.0)]))
    assert "(9,930 EUR)" in r.direct_answer


def test_price_sentence_is_omitted_when_no_price_is_published():
    r = build(robot("a", offers=[offer()]))
    assert "published purchase price" not in r.direct_answer
    assert "can be purchased: 1 available." in r.direct_answer


def test_answer_for_a_region_with_no_qualifying_offer_makes_no_availability_claim():
    r = build(robot("a", prices=[price()]), robot("b"))
    assert r.direct_answer.startswith(
        "As of 2026-10-04, HumanoidOnline has no confirmed offer on file for a published "
        "humanoid robot in Europe.")
    assert "2 other published robots have no confirmed Europe offer on file." in r.direct_answer
    assert "can be purchased" not in r.direct_answer


def test_singular_and_plural_wording():
    one = build(robot("a", offers=[offer()]))
    assert "lists 1 published humanoid robot with" in one.direct_answer
    assert "1 can be purchased" in one.direct_answer


def test_waitlist_and_preorder_are_reported_together():
    r = build(robot("a", offers=[offer(status="WAITLIST")]),
              robot("b", offers=[offer("BG", "PREORDER")]))
    assert "2 can be purchased: 2 waitlist or preorder." in r.direct_answer


def test_best_status_per_robot_is_used_for_the_purchase_sentence():
    r = build(robot("a", offers=[offer("DE", "ON_REQUEST"), offer("BG", "AVAILABLE")]))
    assert r.key_figures.purchase_by_best_status == (
        ("AVAILABLE", 1), ("LIMITED", 0), ("PREORDER", 0), ("WAITLIST", 0), ("ON_REQUEST", 0))


# --- real catalogue (invariants only; no DB) -----------------------------------------------------

REPO = Path(__file__).resolve().parents[3]
CAT = REPO / "db" / "catalogue"


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s[:10]) if s else None


def _evidence(rows):
    return tuple(EvidenceRow(e["source_url"], e.get("confidence", "MEDIUM"),
                             _d(e["observed_at"]), _d(e.get("verified_at"))) for e in rows)


def _catalogue_snapshot(snapshot_date: date) -> RegionalSnapshot:
    regions = tuple(RegionNode(r["code"], r["name"], r["parent_code"])
                    for r in json.loads((CAT / "regions.json").read_text("utf-8"))["regions"])
    providers = {p["slug"]: p["type"]
                 for p in json.loads((CAT / "providers.json").read_text("utf-8"))["providers"]}
    makers = {m["slug"]: m["name"]
              for m in json.loads((CAT / "manufacturers.json").read_text("utf-8"))["manufacturers"]}
    robots = []
    for path in sorted((CAT / "robots").glob("*.json")):
        d = json.loads(path.read_text("utf-8"))
        offers = tuple(
            OfferRow(o.get("provider_slug"), providers.get(o.get("provider_slug")),
                     o.get("region_code"), o["transaction_type"],
                     o.get("availability_status", "ON_REQUEST"), o.get("is_current", True),
                     _evidence(o.get("evidence", [])))
            for o in d.get("availability_offers", []))
        prices = tuple(
            PriceRow(p.get("provider_slug"), p.get("region_code"), p["transaction_type"],
                     p["price_type"], p.get("currency"), p.get("price"), p.get("price_min"),
                     p.get("price_max"), p.get("billing_period", "ONE_TIME"), p.get("price_basis"),
                     p.get("is_current", True), _evidence(p.get("evidence", [])))
            for p in d.get("pricing_offers", []))
        deployments = tuple(
            DeploymentRow(x.get("region_code"), x.get("customer_name"), x.get("provider_slug"),
                          x.get("transaction_type"), x.get("unit_count"), _d(x.get("started_on")),
                          x.get("status"), _evidence(x.get("evidence", [])))
            for x in d.get("deployments", []))
        robots.append(RobotRow(d["slug"], d["name"], d["manufacturer_slug"],
                               makers.get(d["manufacturer_slug"], d["manufacturer_slug"]),
                               d["is_published"], d["commercial_status"], offers, prices,
                               deployments))
    return RegionalSnapshot(snapshot_date, regions, tuple(robots))


def test_real_catalogue_europe_invariants():
    s = _catalogue_snapshot(date(2026, 10, 4))
    r = build_regional_availability(s, "EUROPE")
    published = {x.slug for x in s.robots if x.is_published}
    qualifying = {o.robot_slug for o in r.qualifying_offers}
    assert r.reconciles and r.key_figures.population == len(published)
    assert qualifying <= published
    assert {o.region_code for o in r.qualifying_offers} <= set(r.member_region_codes)
    assert "GLOBAL" not in r.member_region_codes
    assert {o.confidence for o in r.qualifying_offers} <= {"LOW", "MEDIUM", "HIGH", "VERIFIED"}
    assert r.direct_answer.startswith("As of 2026-10-04,")
    assert build_regional_availability(s, "EUROPE") == r


def test_real_catalogue_known_europe_robots_qualify_at_the_adoption_snapshot():
    """Monotone check (superset), so unrelated catalogue growth cannot break it."""
    r = build_regional_availability(_catalogue_snapshot(date(2026, 10, 4)), "EUROPE")
    known = {"agibot-a2-ultra", "booster-k1-educational", "booster-k1-geek",
             "booster-k1-professional", "booster-t2-professional", "unitree-r1",
             "unitree-r1-edu-u4"}
    assert known <= {o.robot_slug for o in r.qualifying_offers}
    assert r.gate.passes


# --- deployments (separate from purchasability) --------------------------------------

def _dep(region="DE", *, evidence=None, customer="Acme GmbH", started=date(2024, 6, 1)):
    return DeploymentRow(
        region, customer, None, "RAAS", 10, started, "production",
        (ev(400),) if evidence is None else tuple(evidence),
    )


def test_a_regional_evidenced_deployment_is_listed_even_when_old_but_never_qualifies():
    r = build(RobotRow("d", "D", "m1", "M1", True, "COMMERCIAL", (), (), (_dep(),)))
    assert [d.robot_slug for d in r.deployments] == ["d"]
    assert r.deployments[0].customer_name == "Acme GmbH"
    assert r.key_figures.qualifying_robots == 0
    assert group_of(r, "d") == NO_OFFERS


def test_deployments_outside_the_region_unresolved_or_unevidenced_are_excluded():
    robots = RobotRow(
        "d", "D", "m1", "M1", True, "COMMERCIAL", (), (),
        (_dep("US"), _dep(None), _dep("DE", evidence=[])),
    )
    assert build(robots).deployments == ()


def test_deployments_of_unpublished_robots_never_appear():
    r = build(RobotRow("hidden", "H", "m1", "M1", False, "COMMERCIAL", (), (), (_dep(),)))
    assert r.deployments == ()
    assert "hidden" not in repr(r)


def test_undisclosed_customer_stays_none_and_confidence_is_not_upgraded():
    r = build(RobotRow("d", "D", "m1", "M1", True, "COMMERCIAL", (), (),
                       (_dep(customer=None, evidence=[ev(5, conf="HIGH"), ev(6, conf="LOW")]),)))
    d = r.deployments[0]
    assert d.customer_name is None
    assert (d.confidence, d.human_verified) == ("LOW", False)


def test_deployments_do_not_change_the_pinned_direct_answer():
    base = build(robot("a", offers=[offer()]))
    with_dep = build(RobotRow("a", "A", "m1", "M1", True, "COMMERCIAL",
                              (offer(),), (), (_dep(),)))
    assert base.direct_answer == with_dep.direct_answer
