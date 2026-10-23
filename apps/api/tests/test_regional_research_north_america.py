"""North America Regional Research Resource (HO-RESEARCH-NA-01).

The same pure read model, projection and gate as Europe, driven by the
NORTH_AMERICA region hierarchy. Pure fixture tests (no DB, clock or network),
one journey block with the loader replaced by a fixture snapshot, and one block
over the real catalogue files (invariants only).
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

URL = "/api/research/humanoid-availability/north-america"

NA_REGIONS = fx.REGIONS[:6] + (  # GLOBAL, EUROPE, EU, DE, BG, UK unchanged
    RegionNode("NORTH_AMERICA", "North America", None),
    RegionNode("US", "United States", "NORTH_AMERICA"),
    RegionNode("CA", "Canada", "NORTH_AMERICA"),
    RegionNode("MX", "Mexico", "NORTH_AMERICA"),
    RegionNode("PR", "Puerto Rico", "NORTH_AMERICA"),
    RegionNode("BR", "Brazil", None),
    RegionNode("TR", "Türkiye", None),
)


def snap(*robots, regions=NA_REGIONS):
    return fx.snap(*robots, regions=regions)


def build(*robots, **kw):
    return build_regional_availability(snap(*robots), "NORTH_AMERICA", **kw)


def project(*robots, readiness=False):
    return build_projection(build(*robots), "north-america", include_readiness=readiness)


def group_of(result, slug):
    return fx.group_of(result, slug)


def _dep(region="US", status="production"):
    return DeploymentRow(region, "Acme Logistics", None, "RAAS", None, date(2024, 6, 27), status,
                         (fx.ev(400, conf="HIGH"),))


# --- region membership ------------------------------------------------------

def test_slug_maps_to_the_north_america_region():
    assert REGION_SLUGS["north-america"] == "NORTH_AMERICA"
    assert REGION_SLUGS["europe"] == "EUROPE"


def test_members_are_the_continent_and_its_countries_never_global_or_south_america():
    members = region_members(NA_REGIONS, "NORTH_AMERICA")
    assert members == {"NORTH_AMERICA", "US", "CA", "MX", "PR"}
    assert not {"GLOBAL", "BR", "EUROPE", "DE"} & members


def test_us_canada_mexico_and_territory_offers_each_qualify():
    r = build(*(fx.robot(c.lower(), offers=[fx.offer(c)]) for c in ("US", "CA", "MX", "PR")))
    assert {o.region_code for o in r.qualifying_offers} == {"US", "CA", "MX", "PR"}
    assert r.key_figures.qualifying_robots == 4


# --- what does not count ------------------------------------------------------

def test_global_only_offer_is_never_region_confirmed():
    r = build(fx.robot("g", offers=[fx.offer("GLOBAL")], prices=[fx.price("GLOBAL", cur="USD")]))
    assert r.key_figures.qualifying_robots == 0
    assert group_of(r, "g") == GLOBAL_ONLY
    assert "GLOBAL" not in r.member_region_codes


def test_europe_and_south_america_offers_are_other_region_only():
    r = build(fx.robot("eu", offers=[fx.offer("DE")]), fx.robot("br", offers=[fx.offer("BR")]))
    assert group_of(r, "eu") == OTHER_REGION_ONLY
    assert group_of(r, "br") == OTHER_REGION_ONLY


def test_unresolved_region_offer_is_not_counted():
    r = build(fx.robot("u", offers=[fx.offer(None, "WAITLIST")]))
    assert group_of(r, "u") == UNRESOLVED_REGION


def test_duplicate_seller_offers_count_the_robot_once():
    r = build(fx.robot("dup", maker="m1", offers=[
        fx.offer("US", provider="shop-a"), fx.offer("US", provider="shop-b"),
        fx.offer("CA", provider="shop-a"),
    ]))
    assert len(r.qualifying_offers) == 3
    assert r.key_figures.qualifying_robots == 1
    assert r.key_figures.qualifying_manufacturers == 1
    assert r.key_figures.purchase_robots == 1


def test_missing_price_stays_unknown_never_zero():
    p = project(fx.robot("a", offers=[fx.offer("US")]))
    assert p["offers"][0]["prices"][0]["kind"] == "NOT_PUBLISHED"
    assert p["offers"][0]["prices"][0]["amount"] is None
    assert p["key_figures"]["purchase_robots_price_not_published"] == 1


def test_a_global_price_does_not_price_a_us_offer():
    p = project(fx.robot("a", offers=[fx.offer("US")],
                         prices=[fx.price("GLOBAL", amount=13500.0, cur="USD")]))
    assert [x["kind"] for x in p["offers"][0]["prices"]] == ["NOT_PUBLISHED"]


def test_old_evidence_stays_current_until_replaced():
    """The 1X NEO / Agility Digit shape: a current US offer last observed 91 days
    ago still counts (owner decision 2026-10-23), with its own last-observed date;
    only a withdrawal recorded on newer evidence removes an offer."""
    r = build(fx.robot("neo", offers=[fx.offer("US", "PREORDER", evidence=[fx.ev(91)])]),
              fx.robot("gone", maker="m2", offers=[fx.offer("CA", current=False,
                                                            evidence=[fx.ev(2)])]))
    assert group_of(r, "neo") == QUALIFYING
    assert r.qualifying_offers[0].evidence_date == fx.SNAP - timedelta(days=91)
    assert group_of(r, "gone") == STALE_OR_NON_CURRENT
    health = build_projection(r, "north-america")["publication_health"]
    assert not any("aged" in s for s in health["reasons"])


def test_deployments_never_establish_purchasability():
    r = build(RobotRow("digit", "Digit", "agility", "Agility", True, "COMMERCIAL", (), (),
                       (_dep("US"),)),
              RobotRow("apollo", "Apollo", "apptronik", "Apptronik", True, "PILOT", (), (),
                       (_dep(None, "pilot"),)))
    assert [d.robot_slug for d in r.deployments] == ["digit"]  # unresolved region excluded
    assert r.key_figures.qualifying_robots == 0
    assert group_of(r, "digit") == NO_OFFERS


def test_unpublished_robots_never_appear():
    p = project(fx.robot("hidden", published=False, offers=[fx.offer("US")]),
                fx.robot("shown", offers=[fx.offer("US")]))
    assert "hidden" not in json.dumps(p)
    assert p["key_figures"]["published_population"] == 1


def test_population_reconciles_across_every_group():
    r = build(fx.robot("q", offers=[fx.offer("US")]),
              fx.robot("g", offers=[fx.offer("GLOBAL")]),
              fx.robot("s", offers=[fx.offer("CA", evidence=[fx.ev(200)])]),
              fx.robot("o", offers=[fx.offer("DE")]),
              fx.robot("n"))
    assert r.reconciles
    assert sum(g.count for g in r.groups) == r.key_figures.population == 5
    kf = r.key_figures
    assert kf.qualifying_robots + kf.no_confirmed_offer == kf.population


def test_thin_dataset_fails_the_unchanged_launch_gate():
    p = project(fx.robot("g1", maker="unitree", offers=[fx.offer("US")]), readiness=True)
    assert p["readiness"]["gate_passes"] is False
    assert (p["readiness"]["min_robots"], p["readiness"]["min_manufacturers"]) == (5, 3)
    assert p["readiness"]["failures"] == ["qualifying robots 1 < 5",
                                          "qualifying manufacturers 1 < 3"]


def test_generated_text_names_north_america_and_never_claims_unavailability():
    p = project(fx.robot("a", offers=[fx.offer("US")]), fx.robot("b"))
    assert "in North America" in p["direct_answer"]
    assert "no confirmed North America offer on file" in p["direct_answer"]
    faq = {f["question"]: f["answer"] for f in p["faq"]}
    assert "Can I buy a humanoid robot in North America?" in faq
    assert "never means the robot is not available in North America" in \
        faq['What does "no confirmed North America offer" mean?']
    assert "NORTH_AMERICA region" in p["methodology"]["region_membership"]


# --- Europe regression ------------------------------------------------------------

def test_adding_the_north_america_hierarchy_does_not_change_europe():
    robots = [fx.robot("de", offers=[fx.offer("DE")]), fx.robot("us", offers=[fx.offer("US")]),
              fx.robot("g", offers=[fx.offer("GLOBAL")])]
    before = build_regional_availability(fx.snap(*robots), "EUROPE")
    after = build_regional_availability(snap(*robots), "EUROPE")
    assert build_projection(before, "europe") == build_projection(after, "europe")


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
    return snap(*(fx.robot(f"r{i}", maker=f"m{i % 3}", offers=[fx.offer(("US", "CA")[i % 2])])
                  for i in range(6)))


def test_closed_by_default_and_europe_publication_does_not_publish_it(client, journey):
    journey(_ready(), published="europe")
    assert client.get(URL).status_code == 404


def test_preview_is_200_noindex_no_store_with_readiness(client, journey):
    journey(snap(fx.robot("g1", offers=[fx.offer("US")])), token="tok")
    assert client.get(URL, headers={"X-Research-Preview": "wrong"}).status_code == 404
    r = client.get(URL, headers={"X-Research-Preview": "tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["published"] is False
    assert body["region"] == {"slug": "north-america", "code": "NORTH_AMERICA",
                              "name": "North America"}
    assert body["readiness"]["gate_passes"] is False
    assert r.headers["cache-control"] == "no-store"
    assert "noindex" in r.headers["x-robots-tag"]


def test_published_is_public_without_readiness(client, journey):
    journey(_ready(), published="europe,north-america")
    r = client.get(URL)
    assert r.status_code == 200
    assert r.json()["published"] is True and "readiness" not in r.json()
    assert r.json()["key_figures"]["robots_with_confirmed_offer"] == 6


def test_missing_hierarchy_is_404_even_with_a_token(client, journey):
    """Production today: NORTH_AMERICA is not imported yet, so preview cannot open."""
    journey(fx.snap(fx.robot("g1", offers=[fx.offer("US")])), token="tok")
    assert client.get(URL, headers={"X-Research-Preview": "tok"}).status_code == 404


# --- real catalogue (invariants only; no DB) ---------------------------------------------

AUDIT_DAY = date(2026, 10, 23)


def _real(day=AUDIT_DAY):
    return build_regional_availability(fx._catalogue_snapshot(day), "NORTH_AMERICA")


def test_real_catalogue_north_america_invariants():
    s = fx._catalogue_snapshot(AUDIT_DAY)
    r = _real()
    published = {x.slug for x in s.robots if x.is_published}
    assert r.reconciles and r.key_figures.population == len(published)
    assert {o.robot_slug for o in r.qualifying_offers} <= published
    assert {o.region_code for o in r.qualifying_offers} <= set(r.member_region_codes)
    assert len(r.member_region_codes) == 42  # NORTH_AMERICA + the 41 M49 003 codes
    assert _real() == r


def test_real_catalogue_known_findings_at_the_audit_snapshot():
    """Monotone only (like Europe's), so a later evidence refresh or a newly
    authorized source cannot break it."""
    r = _real()
    # Offers stay current until newer evidence replaces them (owner decision 2026-10-23).
    assert {"unitree-g1", "1x-neo", "agility-digit"} <= {o.robot_slug for o in r.qualifying_offers}
    deployed = {d.robot_slug for d in r.deployments}
    assert {"agility-digit", "figure-02"} <= deployed
    assert "apptronik-apollo" not in deployed  # deployment region unresolved
