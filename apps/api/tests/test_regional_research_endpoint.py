"""Regional Research Resource: projection, publication gate and loader (ADR-027 Step 3).

The projection tests are pure (no DB). The gate tests need no data because a
closed gate answers before any query. The loader/endpoint-success tests are
DB-backed and skip locally without DATABASE_URL (CI runs them).
"""
from __future__ import annotations

import dataclasses
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_regional_availability_readmodel as fx  # noqa: E402

from app.services.regional_research.projection import build_projection  # noqa: E402
from app.services.regional_research.readmodel import build_regional_availability  # noqa: E402

URL = "/api/research/humanoid-availability/europe"


def _projection(*robots, readiness=False):
    result = build_regional_availability(fx.snap(*robots), "EUROPE")
    return build_projection(result, "europe", include_readiness=readiness)


def _sample():
    return [
        fx.robot("a", maker="m1", offers=[fx.offer("DE")], prices=[fx.price("DE", amount=9930.0)]),
        fx.robot("b", maker="m2", offers=[fx.offer("EU", "ON_REQUEST")]),
        fx.robot("hidden-unpublished", published=False, offers=[fx.offer()]),
        fx.robot("g", offers=[fx.offer("GLOBAL")]),
        fx.robot("none"),
    ]


# --- projection (pure) -------------------------------------------------------

def test_projection_is_json_serializable_and_stable():
    p = _projection(*_sample())
    assert json.loads(json.dumps(p)) == p
    assert _projection(*_sample()) == p


def test_projection_carries_the_declared_snapshot_and_region():
    p = _projection(*_sample())
    assert p["region"] == {"slug": "europe", "code": "EUROPE", "name": "Europe"}
    assert p["snapshot_date"] == "2026-10-04"
    assert p["freshness_days"] == 90
    assert p["latest_evidence_date"] == "2026-09-24"


def test_projection_never_leaks_unpublished_robots():
    assert "hidden-unpublished" not in json.dumps(_projection(*_sample()))


def test_readiness_is_review_only():
    assert "readiness" not in _projection(*_sample())
    ready = _projection(*_sample(), readiness=True)["readiness"]
    assert ready["groups_reconcile"] is True
    assert ready["gate_passes"] is False  # 2 robots / 2 manufacturers < 5 / 3


def test_offers_projection_keeps_price_states_and_unknowns():
    p = _projection(*_sample())
    by = {o["robot_slug"]: o for o in p["offers"]}
    assert by["a"]["prices"][0]["kind"] == "PUBLISHED"
    assert by["b"]["prices"] == [
        {"kind": "NOT_PUBLISHED", "price_type": None, "amount": None, "price_min": None,
         "price_max": None, "currency": None, "billing_period": None, "price_basis": None}
    ]
    assert by["a"]["confidence"] == "MEDIUM" and by["a"]["human_verified"] is False


def test_groups_exclude_qualifying_and_empty_groups_and_explain_each_reason():
    p = _projection(*_sample())
    reasons = [g["reason"] for g in p["no_confirmed_offer"]]
    assert reasons == ["GLOBAL_ONLY", "NO_OFFERS"]
    assert all(g["label"] and g["robots"] for g in p["no_confirmed_offer"])


def test_faq_is_generated_from_data_and_never_claims_unavailability():
    p = _projection(*_sample())
    faq = {f["question"]: f["answer"] for f in p["faq"]}
    assert len(faq) == 4
    assert "A and B" in faq["Can I buy a humanoid robot in Europe?"]
    assert faq["Which humanoid robots in Europe have a published price?"].count("A") >= 1
    meaning = faq['What does "no confirmed Europe offer" mean?']
    assert "never means the robot is not available in Europe" in meaning
    other = json.dumps([v for k, v in faq.items() if "no confirmed" not in k]).lower()
    assert "not available" not in other


def test_faq_with_no_offers_describes_evidence_not_the_market():
    p = _projection(fx.robot("x"))
    q1 = p["faq"][0]["answer"]
    assert "no confirmed purchase offer on file" in q1
    assert "not the market" in q1


def test_methodology_discloses_the_adr_required_items():
    m = _projection(*_sample())["methodology"]
    assert {"population", "region_membership", "qualifying_offer", "unknown_treatment",
            "confidence", "calculation"} <= set(m)
    assert "90 days" in m["qualifying_offer"]
    assert "Global offers are not counted" in m["region_membership"]


# --- publication gate --------------------------------------------------------

@pytest.fixture
def gate(monkeypatch):
    def set_(published="", token=None):
        monkeypatch.setattr(
            "app.routers.research.get_settings",
            lambda: SimpleNamespace(research_published_regions=published,
                                    research_preview_token=token),
        )
    return set_


def test_default_gate_hides_the_resource(client, gate):
    gate()
    assert client.get(URL).status_code == 404


def test_unknown_region_is_404_even_with_a_valid_token(client, gate):
    gate(published="europe", token="tok")
    for slug in ("atlantis", "north-america", "asia"):
        r = client.get(f"/api/research/humanoid-availability/{slug}",
                       headers={"X-Research-Preview": "tok"})
        assert r.status_code == 404, slug


def test_wrong_or_missing_token_is_404_when_unpublished(client, gate):
    gate(published="", token="secret")
    assert client.get(URL, headers={"X-Research-Preview": "nope"}).status_code == 404
    assert client.get(URL).status_code == 404


def test_no_configured_token_means_no_preview_access(client, gate):
    gate(published="", token=None)
    assert client.get(URL, headers={"X-Research-Preview": ""}).status_code == 404
    assert client.get(URL, headers={"X-Research-Preview": "anything"}).status_code == 404


# --- DB-backed (CI) -----------------------------------------------------------

def test_loader_snapshot_contains_only_published_robots(database_url):
    from app.db.session import SessionLocal
    from app.services.regional_research.loader import load_regional_snapshot

    with SessionLocal() as s:
        snap = load_regional_snapshot(s, date(2026, 10, 4))
    assert all(r.is_published for r in snap.robots)
    codes = {r.code for r in snap.regions}
    assert "GLOBAL" in codes
    result = build_regional_availability(snap, "EUROPE") if "EUROPE" in codes else None
    if result is not None:
        assert result.reconciles


def test_preview_returns_the_projection_with_readiness_and_noindex(client, gate, database_url):
    gate(published="", token="tok")
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.region import Region

    with SessionLocal() as s:
        if s.execute(select(Region.id).where(Region.code == "EUROPE")).first() is None:
            pytest.skip("EUROPE region not present in this dataset")
    r = client.get(URL, headers={"X-Research-Preview": "tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["published"] is False and "readiness" in body
    assert r.headers["cache-control"] == "no-store"
    assert "noindex" in r.headers["x-robots-tag"]


# --- journey (no DB: the loader is replaced by a fixture snapshot) -------------

def _ready_snapshot():
    robots = [
        fx.robot(f"r{i}", maker=f"m{i % 3}", offers=[fx.offer("DE" if i % 2 else "EU")])
        for i in range(6)
    ]
    return fx.snap(*robots)


def _thin_snapshot():
    return fx.snap(fx.robot("only", offers=[fx.offer()]))


@pytest.fixture
def journey(monkeypatch, gate):
    def set_(snapshot, published="", token=None):
        gate(published=published, token=token)
        monkeypatch.setattr(
            "app.routers.research.load_regional_snapshot", lambda session, day: snapshot
        )
    return set_


def test_journey_closed_is_404_for_everyone_by_default(client, journey):
    journey(_ready_snapshot())
    assert client.get(URL).status_code == 404
    assert client.get(URL, headers={"X-Research-Preview": "x"}).status_code == 404


def test_journey_valid_preview_is_200_noindex_no_store_with_readiness(client, journey):
    journey(_ready_snapshot(), token="tok")
    r = client.get(URL, headers={"X-Research-Preview": "tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["published"] is False and body["readiness"]["gate_passes"] is True
    assert r.headers["cache-control"] == "no-store"
    assert "noindex" in r.headers["x-robots-tag"]


def test_journey_published_and_ready_is_public_indexable_without_readiness(client, journey):
    journey(_ready_snapshot(), published="europe", token="tok")
    r = client.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["published"] is True and "readiness" not in body
    assert "x-robots-tag" not in {k.lower() for k in r.headers}
    assert "max-age=300" in r.headers["cache-control"]
    assert body["key_figures"]["robots_with_confirmed_offer"] == 6


def _stale_snapshot():
    """Six robots from three manufacturers whose only evidence is long out of date."""
    robots = [
        fx.robot(f"s{i}", maker=f"m{i % 3}",
                 offers=[fx.offer("DE", evidence=[fx.ev(200)])],
                 prices=[fx.price("DE", amount=1000.0 + i, evidence=[fx.ev(200)])])
        for i in range(6)
    ]
    return fx.snap(*robots)


# The four publication-lifecycle states (ADR-027 section 12) ----------------------

def test_state_1_unpublished_and_ready_is_preview_only(client, journey):
    journey(_ready_snapshot(), token="tok")
    assert client.get(URL).status_code == 404
    r = client.get(URL, headers={"X-Research-Preview": "tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["published"] is False
    assert body["readiness"]["gate_passes"] is True  # 5/3 is verified here, before launch
    assert body["publication_health"] == {"status": "CURRENT", "reasons": []}
    assert "noindex" in r.headers["x-robots-tag"]


def test_state_2_published_and_ready_is_normal_public(client, journey):
    journey(_ready_snapshot(), published="europe", token="tok")
    r = client.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["published"] is True
    assert body["publication_health"] == {"status": "CURRENT", "reasons": []}
    assert "readiness" not in body
    assert "x-robots-tag" not in {k.lower() for k in r.headers}


def test_state_3_published_but_degraded_stays_public_with_a_limited_evidence_status(
    client, journey
):
    """The 5/3 threshold is a launch check, not a runtime kill switch."""
    journey(_thin_snapshot(), published="europe", token="tok")
    r = client.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["published"] is True
    assert body["publication_health"] == {
        "status": "LIMITED_EVIDENCE",
        "reasons": ["1 qualifying robot; minimum 5", "1 manufacturer; minimum 3"],
    }
    assert "max-age=300" in r.headers["cache-control"]
    assert "x-robots-tag" not in {k.lower() for k in r.headers}
    # The internal gate object is never exposed publicly just to explain the warning.
    assert "readiness" not in body
    assert "gate" not in json.dumps(body).lower()


def test_state_3b_evidence_ageing_degrades_visibly_without_resurrecting_old_facts(
    client, journey
):
    journey(_stale_snapshot(), published="europe")
    r = client.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["publication_health"]["status"] == "LIMITED_EVIDENCE"
    assert body["key_figures"]["robots_with_confirmed_offer"] == 0
    assert body["offers"] == []  # stale offers are excluded, never shown as current
    assert body["key_figures"]["purchase_robots_with_published_price"] == 0
    assert all(g["reason"] != "QUALIFYING" for g in body["no_confirmed_offer"])
    assert any(g["reason"] == "STALE_OR_NON_CURRENT" for g in body["no_confirmed_offer"])
    assert "no confirmed offer on file for a published humanoid robot" in body["direct_answer"]


def test_state_4_published_but_reconciliation_failure_fails_closed(
    client, journey, monkeypatch
):
    journey(_ready_snapshot(), published="europe", token="tok")
    real = build_regional_availability

    def broken(snapshot, region):
        return dataclasses.replace(real(snapshot, region), reconciles=False)

    monkeypatch.setattr("app.routers.research.build_regional_availability", broken)
    assert client.get(URL).status_code == 404
    # A reviewer can still see the review-only report; it is never public.
    r = client.get(URL, headers={"X-Research-Preview": "tok"})
    assert r.status_code == 200
    assert r.json()["published"] is False
    assert r.json()["readiness"]["groups_reconcile"] is False
    assert "noindex" in r.headers["x-robots-tag"]


def test_missing_region_structure_fails_closed_even_when_published(client, journey):
    no_europe = tuple(n for n in fx.REGIONS if n.code != "EUROPE")
    snap = fx.RegionalSnapshot(fx.SNAP, no_europe, _ready_snapshot().robots)
    journey(snap, published="europe", token="tok")
    assert client.get(URL).status_code == 404
    assert client.get(URL, headers={"X-Research-Preview": "tok"}).status_code == 404


def test_projection_failure_fails_closed(client, journey, monkeypatch):
    journey(_ready_snapshot(), published="europe")

    def boom(*a, **k):
        raise KeyError("missing label")

    monkeypatch.setattr("app.routers.research.build_projection", boom)
    assert client.get(URL).status_code == 404


def _partially_aged_snapshot():
    """Six current robots from three manufacturers (still clears 5/3) plus one robot
    whose only Europe offer has just aged past the 90-day window."""
    current = [
        fx.robot(f"c{i}", maker=f"m{i % 3}", offers=[fx.offer("DE" if i % 2 else "EU")])
        for i in range(6)
    ]
    aged = fx.robot("aged", maker="m1", offers=[fx.offer("DE", evidence=[fx.ev(91)])])
    return fx.snap(*current, aged)


def test_partial_ageing_is_visible_even_when_5_3_is_still_met(client, journey):
    journey(_partially_aged_snapshot(), published="europe")
    r = client.get(URL)
    assert r.status_code == 200  # still public
    body = r.json()
    assert body["published"] is True
    # the threshold is still met on current evidence alone...
    assert body["key_figures"]["robots_with_confirmed_offer"] == 6
    assert body["key_figures"]["manufacturers_with_confirmed_offer"] == 3
    # ...but the page says plainly that one robot's evidence aged out
    assert body["publication_health"] == {
        "status": "LIMITED_EVIDENCE",
        "reasons": [
            "1 published robot has only stale or non-current Europe offer evidence "
            "excluded from current figures."
        ],
    }
    # stale evidence stays excluded from offers and counts
    assert "aged" not in [o["robot_slug"] for o in body["offers"]]
    assert [g["robots"][0]["slug"] for g in body["no_confirmed_offer"]
            if g["reason"] == "STALE_OR_NON_CURRENT"] == ["aged"]
    assert "readiness" not in body


def test_health_stale_reason_is_pluralized_and_ordered_after_threshold_reasons():
    two = _projection(
        *[fx.robot(f"c{i}", maker=f"m{i % 3}", offers=[fx.offer()]) for i in range(6)],
        fx.robot("a1", offers=[fx.offer(evidence=[fx.ev(120)])]),
        fx.robot("a2", offers=[fx.offer(current=False)]),
    )
    assert two["publication_health"]["reasons"] == [
        "2 published robots have only stale or non-current Europe offer evidence "
        "excluded from current figures."
    ]
    both = _projection(fx.robot("c", offers=[fx.offer()]),
                       fx.robot("a", offers=[fx.offer(evidence=[fx.ev(120)])]))
    assert both["publication_health"]["reasons"] == [
        "1 qualifying robot; minimum 5",
        "1 manufacturer; minimum 3",
        "1 published robot has only stale or non-current Europe offer evidence "
        "excluded from current figures.",
    ]


def test_an_alternate_old_offer_on_a_still_current_robot_does_not_warn():
    robots = [
        fx.robot(f"c{i}", maker=f"m{i % 3}", offers=[fx.offer()]) for i in range(5)
    ]
    # This robot has a current Europe offer AND an older, aged one: it is QUALIFYING.
    robots.append(fx.robot("both", maker="m0", offers=[
        fx.offer("DE"), fx.offer("EU", evidence=[fx.ev(200)])]))
    p = _projection(*robots)
    assert p["publication_health"] == {"status": "CURRENT", "reasons": []}
    assert p["key_figures"]["robots_with_confirmed_offer"] == 6


def test_confirmed_not_obtainable_or_missing_offers_are_not_staleness():
    robots = [fx.robot(f"c{i}", maker=f"m{i % 3}", offers=[fx.offer()]) for i in range(5)]
    robots += [fx.robot("na", offers=[fx.offer(status="NOT_AVAILABLE")]),
               fx.robot("none"), fx.robot("glob", offers=[fx.offer("GLOBAL")])]
    assert _projection(*robots)["publication_health"] == {"status": "CURRENT", "reasons": []}


# publication_health (pure) --------------------------------------------------------

def test_health_current_and_limited_reasons_are_deterministic_and_factual():
    ready = _projection(*_ready_snapshot().robots)
    assert ready["publication_health"] == {"status": "CURRENT", "reasons": []}
    limited = _projection(fx.robot("a", maker="m1", offers=[fx.offer()]),
                          fx.robot("b", maker="m1", offers=[fx.offer("EU")]))
    assert limited["publication_health"] == {
        "status": "LIMITED_EVIDENCE",
        "reasons": ["2 qualifying robots; minimum 5", "1 manufacturer; minimum 3"],
    }
    assert _projection(fx.robot("z"))["publication_health"]["reasons"] == [
        "0 qualifying robots; minimum 5", "0 manufacturers; minimum 3"]


def test_health_manufacturer_shortfall_alone_is_reported_alone():
    robots = [fx.robot(f"r{i}", maker="solo", offers=[fx.offer()]) for i in range(6)]
    assert _projection(*robots)["publication_health"] == {
        "status": "LIMITED_EVIDENCE",
        "reasons": ["1 manufacturer; minimum 3"],
    }


def test_journey_json_equals_the_pure_projection(client, journey):
    snap = _ready_snapshot()
    journey(snap, published="europe")
    body = client.get(URL).json()
    expected = build_projection(build_regional_availability(snap, "EUROPE"), "europe")
    expected["published"] = True
    assert body == expected


def test_journey_unpublished_robots_never_reach_the_response(client, journey):
    snap = fx.snap(
        *[fx.robot(f"r{i}", maker=f"m{i % 3}", offers=[fx.offer()]) for i in range(6)],
        fx.robot("secret-unpublished", published=False, offers=[fx.offer()]),
    )
    journey(snap, published="europe")
    assert "secret-unpublished" not in client.get(URL).text
