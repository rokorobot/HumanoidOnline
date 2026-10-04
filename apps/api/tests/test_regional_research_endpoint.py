"""Regional Research Resource: projection, publication gate and loader (ADR-027 Step 3).

The projection tests are pure (no DB). The gate tests need no data because a
closed gate answers before any query. The loader/endpoint-success tests are
DB-backed and skip locally without DATABASE_URL (CI runs them).
"""
from __future__ import annotations

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


def test_published_body_has_no_readiness_and_is_cacheable(client, gate, database_url):
    gate(published="europe", token="tok")
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.region import Region

    with SessionLocal() as s:
        if s.execute(select(Region.id).where(Region.code == "EUROPE")).first() is None:
            pytest.skip("EUROPE region not present in this dataset")
    r = client.get(URL)
    assert r.status_code == 200
    assert r.json()["published"] is True and "readiness" not in r.json()
    assert "x-robots-tag" not in {k.lower() for k in r.headers}
    assert "max-age=300" in r.headers["cache-control"]
