"""`GET /api/regions/{code}/scope` — the canonical resolvers, exposed as codes.

The compare view annotates recorded offers with "applies to this region" and
"belongs to this market". It must not re-derive geography to do so, so this
endpoint hands it the two governed scopes verbatim. The property pinned here is
the same one `test_region_discovery.py` pins on the resolvers: a member
country's offer is in the EU *market* and is NOT *applicable* to the EU region.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.region import Region


def _require(*codes: str) -> None:
    with SessionLocal() as s:
        present = set(
            s.execute(select(Region.code).where(Region.code.in_(codes))).scalars().all()
        )
    missing = [c for c in codes if c not in present]
    if missing:
        pytest.skip(f"regions not present in this dataset: {', '.join(missing)}")


def test_zone_scope_separates_eligibility_from_market(client) -> None:
    _require("EU", "DE", "GLOBAL")
    body = client.get("/api/regions/EU/scope").json()
    assert body["code"] == "EU"
    # Eligibility walks upward only: a German offer does not apply to the EU.
    assert "EU" in body["applicable"] and "GLOBAL" in body["applicable"]
    assert "DE" not in body["applicable"]
    # Market discovery also walks downward: a German supplier is in the EU market.
    assert {"EU", "DE", "GLOBAL"} <= set(body["market"])


def test_country_scope_includes_its_zone(client) -> None:
    _require("EU", "DE", "GLOBAL")
    body = client.get("/api/regions/DE/scope").json()
    # An EU-wide or worldwide offer applies to a buyer in Germany.
    assert {"DE", "EU", "GLOBAL"} <= set(body["applicable"])
    assert set(body["applicable"]) <= set(body["market"])


def test_unknown_code_is_404_not_an_empty_scope(client) -> None:
    res = client.get("/api/regions/NOT-A-REGION/scope")
    assert res.status_code == 404
