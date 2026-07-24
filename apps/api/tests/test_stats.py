"""Market-snapshot endpoint (runs against the seeded DB in CI)."""
from __future__ import annotations


def test_market_snapshot_shape(client, database_url) -> None:
    resp = client.get("/api/market-snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert {
        "total_tracked",
        "commercially_accessible",
        "in_deployment_or_pilot",
        "manufacturers",
        "rental_offers_present",
        "latest_observed_at",
    } <= body.keys()
    # Derived from canonical facts; on the seed these are internally consistent.
    assert body["total_tracked"] >= 15
    assert 0 <= body["commercially_accessible"] <= body["total_tracked"]
    assert body["manufacturers"] >= 1
    assert isinstance(body["rental_offers_present"], bool)
