"""Market-snapshot endpoint (runs against the seeded DB in CI)."""
from __future__ import annotations


def test_market_snapshot_shape(client, database_url) -> None:
    resp = client.get("/api/market-snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert {
        "total_tracked",
        "total_published",
        "commercially_accessible",
        "in_deployment_or_pilot",
        "manufacturers_tracked",
        "manufacturers_published",
        "rental_offers_present",
        "latest_observed_at",
    } <= body.keys()
    # Derived from canonical facts; on the seed these are internally consistent.
    assert body["total_tracked"] >= 15
    # Published is a SUBSET of tracked, never the same measure by another name.
    assert 0 <= body["total_published"] <= body["total_tracked"]
    # Obtainability is a claim made on a public profile, so it is bounded by
    # published — not by tracked.
    assert 0 <= body["commercially_accessible"] <= body["total_published"]
    assert 0 <= body["in_deployment_or_pilot"] <= body["total_published"]
    assert body["manufacturers_tracked"] >= 1
    assert 0 <= body["manufacturers_published"] <= body["manufacturers_tracked"]
    assert isinstance(body["rental_offers_present"], bool)
    # The ambiguous pre-correction field must be gone, not merely supplemented:
    # leaving it would let a caller keep reading published counts as "tracked".
    assert "manufacturers" not in body
