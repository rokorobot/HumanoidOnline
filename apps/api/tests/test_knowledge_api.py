"""WS2 knowledge-layer read API tests (against the seeded database).

Asserts the frozen semantics that must never regress:
  - known public price      -> price_display {type: PUBLIC, amount: N}
  - quote-gated             -> price_display {type: QUOTE_ONLY, amount: null}
  - unknown (no rows)       -> price_display: null
  - available_modes/deployment_count come from the canonical snapshot view
These require the seed; they skip when DATABASE_URL is unset (see conftest).
"""
from __future__ import annotations

import pytest


def _get(client, url, **params):
    resp = client.get(url, params=params)
    assert resp.status_code == 200, (url, resp.status_code, resp.text)
    return resp.json()


# ---- Robots list ---------------------------------------------------------

def test_robots_list_shape(client, database_url) -> None:
    body = _get(client, "/api/robots")
    assert {"items", "total", "limit", "offset"} <= body.keys()
    assert body["total"] >= 15
    assert body["limit"] == 24
    slugs = {it["slug"] for it in body["items"]}
    assert {"unitree-g1", "digit", "optimus"} <= slugs


def test_price_trichotomy(client, database_url) -> None:
    items = {it["slug"]: it for it in _get(client, "/api/robots", limit=100)["items"]}

    # Known public price.
    g1 = items["unitree-g1"]
    assert g1["price_display"]["type"] == "PUBLIC"
    assert g1["price_display"]["amount"] == 16000
    assert "PURCHASE" in g1["available_modes"]

    # Quote-gated: known fact, amount null (must NOT collapse to unknown).
    digit = items["digit"]
    assert digit["price_display"]["type"] == "QUOTE_ONLY"
    assert digit["price_display"]["amount"] is None
    assert digit["available_modes"] == ["RAAS"]
    assert digit["deployment_count"] >= 1

    # Unknown: no pricing rows -> whole object null.
    optimus = items["optimus"]
    assert optimus["price_display"] is None
    assert optimus["available_modes"] == []


def test_robots_filter_commercial_status(client, database_url) -> None:
    body = _get(client, "/api/robots", commercial_status="COMMERCIAL", limit=100)
    assert body["total"] >= 1
    assert all(it["commercial_status"] == "COMMERCIAL" for it in body["items"])


def test_robots_filter_use_case(client, database_url) -> None:
    body = _get(client, "/api/robots", use_case="warehouse-logistics", limit=100)
    slugs = {it["slug"] for it in body["items"]}
    assert "digit" in slugs


# ---- Robot detail --------------------------------------------------------

def test_robot_detail_three_dimensions(client, database_url) -> None:
    body = _get(client, "/api/robots/digit")
    assert body["slug"] == "digit"
    assert body["commercial_status"] == "RAAS_DEPLOYMENT"  # maturity dimension
    modes = [a["transaction_type"] for a in body["availability_offers"]]
    assert "RAAS" in modes  # obtainability dimension
    assert len(body["deployments"]) >= 1  # evidence dimension
    # Deployments carry provenance (no commercial fact without evidence).
    assert any(d.get("evidence") for d in body["deployments"])
    assert isinstance(body["specs"], dict)


def test_robot_detail_404(client, database_url) -> None:
    resp = client.get("/api/robots/does-not-exist")
    assert resp.status_code == 404


# ---- AGENT-02.2c non-regression -----------------------------------------
# The detail load moved into services/reads.py so `get_robot` could share it.
# These prove the HTTP surface did not move with it.

def test_robot_detail_still_excludes_unpublished(client, database_url) -> None:
    """The publication predicate travelled *inside* the shared loader, so it
    cannot have been left behind at the router's call site."""
    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        slug = conn.execute(
            text("SELECT slug FROM robot WHERE NOT is_published LIMIT 1")
        ).scalar_one_or_none()
    if slug is None:
        pytest.skip("catalogue has no unpublished robot to probe")
    assert client.get(f"/api/robots/{slug}").status_code == 404


def test_robot_detail_gains_model_code_and_nothing_else(client, database_url) -> None:
    """`model_code` is the one additive field of this slice (docs/20 §6, §18).

    Everything else the detail carried, it still carries — and the agent-only
    additions (`evidence_ref`, `subject_type`, a warnings envelope) stay off the
    HTTP surface, where no consumer asked for them.
    """
    body = _get(client, "/api/robots/digit")
    assert "model_code" in body

    for existing in (
        "id", "slug", "name", "manufacturer", "commercial_status", "summary",
        "description", "hero_image_url", "announced_year", "status_history",
        "specs", "extended_specs", "capabilities", "variants", "use_case_fits",
        "pricing_offers", "availability_offers", "deployments", "images",
    ):
        assert existing in body, existing
    assert "warnings" not in body

    for offers in ("pricing_offers", "availability_offers", "deployments"):
        for item in body[offers]:
            evidence = item.get("evidence")
            if evidence is not None:
                assert "evidence_ref" not in evidence
                assert "subject_type" not in evidence
                assert "id" not in evidence
                assert "subject_id" not in evidence


def test_compare_uses_the_same_publication_gated_loader(
    client, database_url
) -> None:
    """`compare` reads through the shared loader too, so an unpublished slug is
    simply not a valid member — and `model_code` reaches it by the same path."""
    body = _get(client, "/api/robots/compare", ids="unitree-g1,digit")
    assert {r["slug"] for r in body["robots"]} == {"unitree-g1", "digit"}
    for robot in body["robots"]:
        assert "model_code" in robot

    resp = client.get(
        "/api/robots/compare", params={"ids": "unitree-g1,digit,does-not-exist"}
    )
    assert resp.status_code == 200
    assert len(resp.json()["robots"]) == 2


def test_evidence_exposes_observed_at(client, database_url) -> None:
    """observed_at (TIMESTAMPTZ NOT NULL) reaches the API response on every
    evidence object — on the detail endpoint and through /compare. Additive,
    read-only; the other provenance dates stay separate (no freshness score)."""
    body = _get(client, "/api/robots/digit")
    evs = [d["evidence"] for d in body["deployments"] if d.get("evidence")]
    assert evs, "expected at least one deployment carrying evidence"
    for ev in evs:
        # Always present (never null); distinct from published_at/verified_at.
        assert ev.get("observed_at"), "observed_at must always be present"
        assert "published_at" in ev and "verified_at" in ev

    # Same fact-level evidence, carried through the compare endpoint.
    comp = _get(client, "/api/robots/compare", ids="unitree-g1,digit")
    digit = next(r for r in comp["robots"] if r["slug"] == "digit")
    comp_evs = [d["evidence"] for d in digit["deployments"] if d.get("evidence")]
    assert comp_evs and all(e.get("observed_at") for e in comp_evs)


# ---- Compare -------------------------------------------------------------

def test_compare_two(client, database_url) -> None:
    body = _get(client, "/api/robots/compare", ids="unitree-g1,digit")
    assert len(body["robots"]) == 2
    assert len(body["rows"]) >= 1
    row = next(r for r in body["rows"] if r["key"] == "commercial_status")
    assert set(row["values"].keys()) == {"unitree-g1", "digit"}


def test_compare_requires_two(client, database_url) -> None:
    resp = client.get("/api/robots/compare", params={"ids": "unitree-g1"})
    assert resp.status_code == 422


# ---- Manufacturers -------------------------------------------------------

def test_manufacturers_list_and_detail(client, database_url) -> None:
    body = _get(client, "/api/manufacturers", limit=100)
    assert body["total"] >= 10
    slug = body["items"][0]["slug"]
    assert "tracked_robot_count" in body["items"][0]
    assert "published_robot_count" in body["items"][0]

    detail = _get(client, f"/api/manufacturers/{slug}")
    assert detail["slug"] == slug
    assert isinstance(detail["robots"], list)
    assert isinstance(detail["providers"], list)


def test_manufacturer_robots_governed_thumbnail(client, database_url) -> None:
    """MEDIA-01: the manufacturer portfolio thumbnail is the SAME governed primary
    image as the catalogue card — identical display-eligibility gate, no alternate
    or unverified image path. Present-or-null, never a fabricated fill."""
    catalogue = {
        it["slug"]: it["primary_image"]
        for it in _get(client, "/api/robots", limit=100)["items"]
    }
    detail = _get(client, "/api/manufacturers/unitree")
    assert detail["robots"]  # Unitree has published robots
    for r in detail["robots"]:
        assert "primary_image" in r
        assert r["slug"] in catalogue
        # The row image is byte-for-byte the catalogue card's governed selection.
        assert r["primary_image"] == catalogue[r["slug"]]
        if r["primary_image"] is not None:
            assert r["primary_image"]["image_url"]


def test_manufacturer_404(client, database_url) -> None:
    assert client.get("/api/manufacturers/nope").status_code == 404


def test_derive_portfolio_status_rules() -> None:
    """Pure derivation rules (no DB): DISCONTINUED excluded from the ranking and
    only chosen when EVERY robot is discontinued; null when empty."""
    from app.services.reads import derive_portfolio_status

    assert derive_portfolio_status([]) is None
    assert derive_portfolio_status(["DISCONTINUED"]) == "DISCONTINUED"
    assert derive_portfolio_status(["DISCONTINUED", "DISCONTINUED"]) == "DISCONTINUED"
    # An active status always outranks DISCONTINUED.
    assert derive_portfolio_status(["DISCONTINUED", "PILOT"]) == "PILOT"
    # Most commercially-mature ACTIVE status wins.
    assert derive_portfolio_status(["ANNOUNCED", "PILOT", "COMMERCIAL"]) == "COMMERCIAL"
    assert derive_portfolio_status(["PILOT", "ANNOUNCED"]) == "PILOT"
    assert derive_portfolio_status(["COMMERCIAL", "RAAS_DEPLOYMENT"]) == "RAAS_DEPLOYMENT"


def test_manufacturer_portfolio_status(client, database_url) -> None:
    body = _get(client, "/api/manufacturers", limit=100)
    by_slug = {m["slug"]: m for m in body["items"]}
    for item in body["items"]:
        assert "portfolio_status" in item
    # Honda: only ASIMO (DISCONTINUED) -> the all-discontinued rule.
    assert by_slug["honda"]["portfolio_status"] == "DISCONTINUED"
    # Figure: figure-02 PILOT + figure-03 ANNOUNCED -> most mature ACTIVE = PILOT
    # (derived from robots, NOT the coarse deployment_status company column).
    assert by_slug["figure-ai"]["portfolio_status"] == "PILOT"


# ---- Use cases -----------------------------------------------------------

def test_use_cases_list_and_detail(client, database_url) -> None:
    body = _get(client, "/api/use-cases", limit=100)
    assert body["total"] >= 1
    detail = _get(client, "/api/use-cases/warehouse-logistics")
    assert detail["slug"] == "warehouse-logistics"
    scores = [
        r["fit_score"] for r in detail["suitable_robots"] if r["fit_score"] is not None
    ]
    assert scores == sorted(scores, reverse=True)  # ordered by fit desc


def test_use_case_suitable_robots_governed_thumbnail(client, database_url) -> None:
    """MEDIA-01: the suitable-robots thumbnail is the SAME governed primary image
    as the catalogue card — identical display-eligibility gate, no alternate or
    unverified image path. Present-or-null, never a fabricated fill."""
    catalogue = {
        it["slug"]: it["primary_image"]
        for it in _get(client, "/api/robots", limit=100)["items"]
    }
    detail = _get(client, "/api/use-cases/warehouse-logistics")
    assert detail["suitable_robots"]  # the use case has ranked robots
    for r in detail["suitable_robots"]:
        assert "primary_image" in r
        # Every suitable robot is published, so it appears in the catalogue read.
        assert r["slug"] in catalogue
        # The row image is byte-for-byte the catalogue card's governed selection.
        assert r["primary_image"] == catalogue[r["slug"]]
        # Where present it is a real URL through the gate; never an empty fill.
        if r["primary_image"] is not None:
            assert r["primary_image"]["image_url"]


def test_use_case_404(client, database_url) -> None:
    assert client.get("/api/use-cases/nope").status_code == 404


# ---- Admin ---------------------------------------------------------------

def test_admin_is_not_anonymously_reachable(client, database_url) -> None:
    """WS8.1 / R1 — replaces the former `test_admin_mounted`.

    That test asserted `GET /admin/` returned **200 to an anonymous caller**.
    It passed, and what it pinned was gap B1 itself: unauthenticated SQLAdmin
    CRUD over buyer PII, expressed as a green test. The ratified contract
    forbids it — unconfigured means *not mounted* (404), configured means
    redirect to login. Anonymous 200 is never acceptable again.

    Both branches (fail-closed, and authenticated-when-configured) are covered
    in `test_security_boundaries.py`; this asserts the invariant on the real app.
    """
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code != 200
    # This suite runs with no admin credentials configured, so: fail closed.
    assert resp.status_code == 404
