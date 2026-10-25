"""Asia Regional Research Resource (HO-RESEARCH-ASIA-01).

The same pure read model, projection and gate as Europe and North America,
driven by the ASIA region hierarchy (UN M49 142 minus CY, plus TW; see
test_catalogue_regions_asia.py). Pure fixture tests (no DB, clock or network),
one journey block with the loader replaced by a fixture snapshot, and one block
over the real catalogue files (invariants and the proposed ASIA-01 batch).
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_regional_availability_readmodel as fx  # noqa: E402

from app.services.regional_research.inputs import (  # noqa: E402
    DeploymentRow,
    RegionNode,
    RobotRow,
)
from app.services.regional_research.projection import (  # noqa: E402
    REGION_SLUGS,
    build_projection,
)
from app.services.regional_research.readmodel import (  # noqa: E402
    GLOBAL_ONLY,
    NO_OFFERS,
    OTHER_REGION_ONLY,
    QUALIFYING,
    STALE_OR_NON_CURRENT,
    UNRESOLVED_REGION,
    build_regional_availability,
    region_members,
)

URL = "/api/research/humanoid-availability/asia"

ASIA_REGIONS = fx.REGIONS[:6] + (  # GLOBAL, EUROPE, EU, DE, BG, UK unchanged
    RegionNode("CY", "Cyprus", "EU"),
    RegionNode("RU", "Russian Federation", "EUROPE"),
    RegionNode("NORTH_AMERICA", "North America", None),
    RegionNode("US", "United States", "NORTH_AMERICA"),
    RegionNode("ASIA", "Asia", None),
    RegionNode("CN", "China", "ASIA"),
    RegionNode("JP", "Japan", "ASIA"),
    RegionNode("KR", "Korea, Republic of", "ASIA"),
    RegionNode("SG", "Singapore", "ASIA"),
    RegionNode("IN", "India", "ASIA"),
    RegionNode("AE", "United Arab Emirates", "ASIA"),
    RegionNode("TW", "Taiwan", "ASIA"),
    RegionNode("AU", "Australia", None),
)


def snap(*robots, regions=ASIA_REGIONS):
    return fx.snap(*robots, regions=regions)


def build(*robots, **kw):
    return build_regional_availability(snap(*robots), "ASIA", **kw)


def project(*robots, readiness=False):
    return build_projection(build(*robots), "asia", include_readiness=readiness)


def group_of(result, slug):
    return fx.group_of(result, slug)


def _dep(region="CN", status="pilot"):
    return DeploymentRow(region, "Hitachi (China) Ltd.", None, "PILOT", None, None, status,
                         (fx.ev(80, conf="MEDIUM"),))


# --- region membership ------------------------------------------------------

def test_slug_maps_to_the_asia_region_and_existing_slugs_are_unchanged():
    assert REGION_SLUGS == {"europe": "EUROPE", "north-america": "NORTH_AMERICA", "asia": "ASIA"}


def test_members_never_include_global_cyprus_russia_or_australia():
    members = region_members(ASIA_REGIONS, "ASIA")
    assert members == {"ASIA", "CN", "JP", "KR", "SG", "IN", "AE", "TW"}
    assert not {"GLOBAL", "CY", "RU", "AU", "EUROPE", "US"} & members


def test_offers_in_every_sub_region_and_taiwan_each_qualify():
    codes = ("CN", "JP", "KR", "SG", "IN", "AE", "TW")
    r = build(*(fx.robot(c.lower(), offers=[fx.offer(c)]) for c in codes))
    assert {o.region_code for o in r.qualifying_offers} == set(codes)
    assert r.key_figures.qualifying_robots == 7


def test_a_cyprus_offer_counts_for_europe_not_asia():
    robots = [fx.robot("cy", offers=[fx.offer("CY")])]
    assert group_of(build(*robots), "cy") == OTHER_REGION_ONLY
    europe = build_regional_availability(snap(*robots), "EUROPE")
    assert group_of(europe, "cy") == QUALIFYING


# --- what does not count ------------------------------------------------------

def test_global_only_offer_is_never_asia_confirmed():
    r = build(fx.robot("g", offers=[fx.offer("GLOBAL")], prices=[fx.price("GLOBAL", cur="USD")]))
    assert r.key_figures.qualifying_robots == 0
    assert group_of(r, "g") == GLOBAL_ONLY
    assert "GLOBAL" not in r.member_region_codes


def test_europe_north_america_and_australia_offers_are_other_region_only():
    r = build(fx.robot("eu", offers=[fx.offer("DE")]), fx.robot("us", offers=[fx.offer("US")]),
              fx.robot("au", offers=[fx.offer("AU")]))
    assert {group_of(r, s) for s in ("eu", "us", "au")} == {OTHER_REGION_ONLY}


def test_unresolved_region_offer_is_not_counted():
    r = build(fx.robot("u", offers=[fx.offer(None, "ON_REQUEST")]))
    assert group_of(r, "u") == UNRESOLVED_REGION


def test_duplicate_sellers_and_countries_count_the_robot_once():
    r = build(fx.robot("g1", maker="unitree", offers=[
        fx.offer("CN", "ON_REQUEST", provider="unitree-cn", ptype="OEM"),
        fx.offer("JP", "ON_REQUEST", provider="gmo-air"),
    ]))
    assert len(r.qualifying_offers) == 2
    assert r.key_figures.qualifying_robots == 1
    assert r.key_figures.qualifying_manufacturers == 1


def test_missing_price_stays_unknown_and_currency_is_never_converted():
    p = project(fx.robot("a", offers=[fx.offer("JP", "ON_REQUEST")]),
                fx.robot("b", offers=[fx.offer("CN", "ON_REQUEST")],
                         prices=[fx.price("CN", amount=85000.0, cur="CNY")]))
    by = {o["robot_slug"]: o["prices"] for o in p["offers"]}
    assert by["a"][0]["kind"] == "NOT_PUBLISHED" and by["a"][0]["amount"] is None
    assert (by["b"][0]["amount"], by["b"][0]["currency"]) == (85000.0, "CNY")


def test_a_china_price_does_not_price_a_japan_offer():
    p = project(fx.robot("a", offers=[fx.offer("JP", "ON_REQUEST")],
                         prices=[fx.price("CN", amount=85000.0, cur="CNY")]))
    assert [x["kind"] for x in p["offers"][0]["prices"]] == ["NOT_PUBLISHED"]


def test_a_rental_is_counted_as_rental_never_as_purchase():
    r = build(fx.robot("pepper", maker="softbank",
                       offers=[fx.offer("JP", "AVAILABLE", tx="RENTAL", ptype="RENTAL_PROVIDER")]))
    assert r.key_figures.qualifying_robots == 1
    assert r.key_figures.purchase_robots == 0
    assert dict(r.key_figures.robots_by_other_transaction) == {"RENTAL": 1}


def test_old_evidence_stays_current_until_replaced():
    r = build(fx.robot("old", offers=[fx.offer("JP", evidence=[fx.ev(400)])]),
              fx.robot("gone", maker="m2", offers=[fx.offer("CN", current=False,
                                                            evidence=[fx.ev(2)])]))
    assert group_of(r, "old") == QUALIFYING
    assert r.qualifying_offers[0].evidence_date == fx.SNAP - timedelta(days=400)
    assert group_of(r, "gone") == STALE_OR_NON_CURRENT
    health = build_projection(r, "asia")["publication_health"]
    assert not any("aged" in s for s in health["reasons"])


def test_deployments_are_separate_and_never_establish_purchasability():
    r = build(RobotRow("walker-s2", "Walker S2", "ubtech", "UBTECH", True, "COMMERCIAL", (), (),
                       (_dep("CN"),)),
              RobotRow("digit", "Digit", "agility", "Agility", True, "COMMERCIAL", (), (),
                       (_dep("US", "production"),)),
              RobotRow("apollo", "Apollo", "apptronik", "Apptronik", True, "PILOT", (), (),
                       (_dep(None),)))
    assert [d.robot_slug for d in r.deployments] == ["walker-s2"]
    assert r.key_figures.qualifying_robots == 0
    assert group_of(r, "walker-s2") == NO_OFFERS


def test_unpublished_robots_never_appear():
    p = project(fx.robot("agibot-x2", maker="agibot", published=False, offers=[fx.offer("CN")]),
                fx.robot("shown", offers=[fx.offer("CN")]))
    assert "agibot-x2" not in json.dumps(p)
    assert p["key_figures"]["published_population"] == 1


def test_zero_offer_state_is_explicit_and_fails_the_gate():
    p = project(fx.robot("a", offers=[fx.offer("GLOBAL")]), fx.robot("b"), readiness=True)
    assert p["offers"] == [] and p["latest_evidence_date"] is None
    assert p["key_figures"]["robots_with_confirmed_offer"] == 0
    assert p["publication_health"]["status"] == "LIMITED_EVIDENCE"
    assert p["readiness"]["gate_passes"] is False
    assert "no confirmed Asia offer on file" in p["direct_answer"]


def test_unchanged_gate_is_five_robots_and_three_manufacturers():
    four = [fx.robot(f"r{i}", maker=f"m{i % 3}", offers=[fx.offer("CN")]) for i in range(4)]
    p = project(*four, readiness=True)
    assert (p["readiness"]["min_robots"], p["readiness"]["min_manufacturers"]) == (5, 3)
    assert p["readiness"]["failures"] == ["qualifying robots 4 < 5"]
    five_one_maker = [fx.robot(f"r{i}", maker="unitree", offers=[fx.offer("JP")]) for i in range(5)]
    assert project(*five_one_maker, readiness=True)["readiness"]["failures"] == [
        "qualifying manufacturers 1 < 3"]


def test_population_reconciles_across_every_group():
    r = build(fx.robot("q", offers=[fx.offer("JP")]),
              fx.robot("g", offers=[fx.offer("GLOBAL")]),
              fx.robot("s", offers=[fx.offer("CN", current=False)]),
              fx.robot("o", offers=[fx.offer("DE")]),
              fx.robot("n"))
    assert r.reconciles
    assert sum(g.count for g in r.groups) == r.key_figures.population == 5


def test_generated_text_names_asia_and_never_claims_unavailability():
    p = project(fx.robot("a", offers=[fx.offer("JP")]), fx.robot("b"))
    assert "in Asia" in p["direct_answer"]
    assert "no confirmed Asia offer on file" in p["direct_answer"]
    faq = {f["question"]: f["answer"] for f in p["faq"]}
    assert "Can I buy a humanoid robot in Asia?" in faq
    assert "never means the robot is not available in Asia" in \
        faq['What does "no confirmed Asia offer" mean?']
    membership = p["methodology"]["region_membership"]
    assert "ASIA region" in membership
    assert "Cyprus is counted in Europe" in membership and "Taiwan" in membership
    assert "Asia-Pacific" in membership


def test_the_coverage_statement_is_asia_only():
    eu = build_projection(build_regional_availability(snap(fx.robot("a")), "EUROPE"), "europe")
    na = build_projection(build_regional_availability(snap(fx.robot("a")), "NORTH_AMERICA"),
                          "north-america")
    for p in (eu, na):
        assert "Cyprus" not in p["methodology"]["region_membership"]
        assert p["methodology"]["region_membership"].endswith(
            "Global offers are not counted as regional availability.")


# --- Europe / North America regression ------------------------------------------

def test_adding_the_asia_hierarchy_does_not_change_europe_or_north_america():
    robots = [fx.robot("de", offers=[fx.offer("DE")]), fx.robot("us", offers=[fx.offer("US")]),
              fx.robot("cy", offers=[fx.offer("CY")]), fx.robot("cn", offers=[fx.offer("CN")]),
              fx.robot("g", offers=[fx.offer("GLOBAL")])]
    without_asia = tuple(
        RegionNode(r.code, r.name, None if r.parent_code == "ASIA" else r.parent_code)
        for r in ASIA_REGIONS if r.code != "ASIA")
    for code, slug in (("EUROPE", "europe"), ("NORTH_AMERICA", "north-america")):
        before = build_regional_availability(snap(*robots, regions=without_asia), code)
        after = build_regional_availability(snap(*robots), code)
        assert build_projection(before, slug) == build_projection(after, slug)


# --- endpoint journey (loader replaced by a fixture snapshot) -------------------------

@pytest.fixture
def journey(monkeypatch):
    def set_(snapshot, published="", token=None):
        monkeypatch.setattr(
            "app.routers.research.get_settings",
            lambda: SimpleNamespace(research_published_regions=published,
                                    research_preview_token=token),
        )
        monkeypatch.setattr(
            "app.routers.research.load_regional_snapshot", lambda session, day: snapshot
        )
    return set_


def _ready():
    return snap(*(fx.robot(f"r{i}", maker=f"m{i % 3}", offers=[fx.offer(("CN", "JP")[i % 2])])
                  for i in range(6)))


def test_closed_by_default_and_under_the_current_production_flag(client, journey):
    journey(_ready(), published="europe,north-america")
    assert client.get(URL).status_code == 404


def test_preview_is_200_noindex_no_store_with_readiness(client, journey):
    journey(snap(fx.robot("g1", offers=[fx.offer("CN")])), token="tok")
    assert client.get(URL, headers={"X-Research-Preview": "wrong"}).status_code == 404
    r = client.get(URL, headers={"X-Research-Preview": "tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["published"] is False
    assert body["region"] == {"slug": "asia", "code": "ASIA", "name": "Asia"}
    assert body["readiness"]["gate_passes"] is False
    assert r.headers["cache-control"] == "no-store"
    assert "noindex" in r.headers["x-robots-tag"]


def test_published_is_public_without_readiness(client, journey):
    journey(_ready(), published="europe,north-america,asia")
    r = client.get(URL)
    assert r.status_code == 200
    assert r.json()["published"] is True and "readiness" not in r.json()
    assert r.json()["key_figures"]["robots_with_confirmed_offer"] == 6


def test_apac_is_not_a_synonym_for_asia(client, journey):
    journey(_ready(), published="europe,north-america,asia,apac", token="tok")
    assert client.get("/api/research/humanoid-availability/apac",
                      headers={"X-Research-Preview": "tok"}).status_code == 404


def test_missing_hierarchy_is_404_even_with_a_token(client, journey):
    """Production today: ASIA is not imported yet, so preview cannot open."""
    journey(fx.snap(fx.robot("g1", offers=[fx.offer("US")])), token="tok")
    assert client.get(URL, headers={"X-Research-Preview": "tok"}).status_code == 404


# --- real catalogue (no DB) ----------------------------------------------------------------

AUDIT_DAY = date(2026, 10, 24)
ASIA01_ROBOTS = {
    "unitree-g1", "unitree-r1", "unitree-h2", "unitree-h2-edu", "unitree-g1-edu-plus-u2",
    "softbank-pepper", "booster-k1-professional",
}


def _real(code="ASIA", day=AUDIT_DAY):
    return build_regional_availability(fx._catalogue_snapshot(day), code)


def test_real_catalogue_asia_invariants():
    s = fx._catalogue_snapshot(AUDIT_DAY)
    r = _real()
    published = {x.slug for x in s.robots if x.is_published}
    assert r.reconciles and r.key_figures.population == len(published)
    assert {o.robot_slug for o in r.qualifying_offers} <= published
    assert {o.region_code for o in r.qualifying_offers} <= set(r.member_region_codes)
    assert len(r.member_region_codes) == 51  # ASIA + 49 M49 142 codes + TW
    assert "CY" not in r.member_region_codes
    assert not {"agibot-x2", "agibot-x2-ultra"} & {o.robot_slug for o in r.qualifying_offers}
    assert _real() == r


def test_real_catalogue_asia01_batch_reaches_the_gate_without_double_counting():
    """HO-RESEARCH-ASIA-01 batch (pending owner approval): Unitree China + GMO AI &
    Robotics (Japan), Switch Science (Japan, K1 Professional), Pepper for Home 2.0
    rental (Japan). G1/R1/H2 have a CN and a JP offer each; each is one robot."""
    r = _real()
    slugs = [o.robot_slug for o in r.qualifying_offers]
    assert ASIA01_ROBOTS <= set(slugs)
    assert r.key_figures.qualifying_robots == len(set(slugs))
    assert r.key_figures.qualifying_manufacturers >= 3
    assert r.gate.passes and r.reconciles
    for slug in ("unitree-g1", "unitree-r1", "unitree-h2"):
        assert {o.region_code for o in r.qualifying_offers if o.robot_slug == slug} == {"CN", "JP"}
    pepper = [o for o in r.qualifying_offers if o.robot_slug == "softbank-pepper"]
    assert [(o.transaction_type, o.region_code) for o in pepper] == [("RENTAL", "JP")]
    assert "agibot-a2-ultra" not in slugs  # store is worldwide (GLOBAL), no CN scope evidenced
    assert "unitree-h1" not in slugs       # no Asia-country H1 route evidenced
    # No purchase offer is AVAILABLE: each is a quote, an intent order or a special order.
    purchase = [o for o in r.qualifying_offers if o.transaction_type == "PURCHASE"]
    assert {o.availability_status for o in purchase} == {"ON_REQUEST"}


def test_real_catalogue_asia_deployment_is_walker_s2_in_china_only():
    r = _real()
    assert [(d.robot_slug, d.region_code) for d in r.deployments] == [("ubtech-walker-s2", "CN")]
    assert "ubtech-walker-s2" not in {o.robot_slug for o in r.qualifying_offers}


def test_real_catalogue_prices_are_as_published_and_never_invented():
    p = build_projection(_real(), "asia")
    got = {(o["robot_slug"], o["provider_slug"]): [(x["kind"], x["amount"], x["currency"])
                                                   for x in o["prices"]]
           for o in p["offers"]}
    assert got[("unitree-g1", "unitree-cn")] == [("PUBLISHED", 85000, "CNY")]
    assert got[("unitree-g1", "gmo-air")] == [("NOT_PUBLISHED", None, None)]
    assert got[("booster-k1-professional", "switch-science")] == [("PUBLISHED", 3148200, "JPY")]
    assert ("PUBLISHED", 43780, "JPY") in got[("softbank-pepper", "tent-pepper-rental")]
    assert all(c in (None, "CNY", "JPY") for v in got.values() for _, _, c in v)


def test_real_catalogue_europe_and_north_america_are_unchanged_by_the_batch():
    eu, na = _real("EUROPE"), _real("NORTH_AMERICA")
    assert (eu.key_figures.qualifying_robots, eu.key_figures.qualifying_manufacturers) == (10, 3)
    assert (na.key_figures.qualifying_robots, na.key_figures.qualifying_manufacturers) == (5, 5)
    assert not {"CN", "JP"} & {o.region_code for o in eu.qualifying_offers + na.qualifying_offers}
