"""WS2 knowledge-layer read API tests (against the seeded database).

Asserts the frozen semantics that must never regress:
  - known public price      -> price_display {type: PUBLIC, amount: N}
  - quote-gated             -> price_display {type: QUOTE_ONLY, amount: null}
  - unknown (no rows)       -> price_display: null
  - available_modes/deployment_count come from the canonical snapshot view
These require the seed; they skip when DATABASE_URL is unset (see conftest).
"""
from __future__ import annotations


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
    assert "robot_count" in body["items"][0]

    detail = _get(client, f"/api/manufacturers/{slug}")
    assert detail["slug"] == slug
    assert isinstance(detail["robots"], list)
    assert isinstance(detail["providers"], list)


def test_manufacturer_404(client, database_url) -> None:
    assert client.get("/api/manufacturers/nope").status_code == 404


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


def test_use_case_404(client, database_url) -> None:
    assert client.get("/api/use-cases/nope").status_code == 404


# ---- Admin ---------------------------------------------------------------

def test_admin_mounted(client, database_url) -> None:
    resp = client.get("/admin/", follow_redirects=True)
    assert resp.status_code == 200
