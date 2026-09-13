"""Manufacturer profile read path: nullable listing status, attributed sources,
target markets and published-only portfolio status, through the real API.

Follows the injection convention of `test_tracked_vs_published.py`: every
fixture row is created inside the test and removed afterwards, so the shared
seeded database is left exactly as found and no seed fact is changed.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import engine

AGENT_NOTE = (
    "RETRIEVAL: AGENT_ASSISTED_RESEARCH (docs/26) — retrieved 2026-09-13 by a test "
    "agent in a session initiated by INTERNAL-PROVENANCE-MARKER. Not a MANUAL_BOOTSTRAP "
    "reading. Not human-verified."
)


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def profiled_maker(database_url):
    """A manufacturer with every 0013 profile field, two sources, one published
    DISCONTINUED robot and one unpublished robot — and NO listing claim."""
    slug = _uniq("profiled-maker")
    mfr_id = _exec(
        """
        INSERT INTO manufacturer
            (slug, name, headquarters_city, incorporation, operating_locations,
             target_markets, deployment_status, deployment_note,
             parent_company, parent_listing, parent_relationship)
        VALUES (:s, :n, 'Testville', 'United States (Delaware)', ARRAY['Plant A'],
                ARRAY['logistics', 'research'], 'PILOT', 'Customer trial; terms undisclosed',
                'Group Co', 'NYSE: GRP', 'Controlling shareholder')
        RETURNING id
        """,
        s=slug,
        n=f"Profiled Robotics {slug[-6:]}",
    ).scalar_one()
    _exec(
        """
        INSERT INTO evidence_source
            (subject_type, subject_id, source_url, source_type, source_title,
             observed_at, confidence, note, claim_fields)
        VALUES ('MANUFACTURER', :m, 'https://example.test/filing', 'FINANCIAL_FILING',
                'Test filing', '2026-09-13', 'HIGH', :note,
                ARRAY['deployment_status', 'deployment_note', 'parent_company'])
        """,
        m=mfr_id,
        note=AGENT_NOTE,
    )
    _exec(
        """
        INSERT INTO evidence_source
            (subject_type, subject_id, source_url, source_type, observed_at,
             verified_at, confidence, note)
        VALUES ('MANUFACTURER', :m, 'https://example.test/site', 'MANUFACTURER_SITE',
                '2026-07-24', '2026-07-24', 'HIGH', 'Legacy identity row.')
        """,
        m=mfr_id,
    )
    published = _uniq("profiled-retired-robot")
    unpublished = _uniq("profiled-hidden-robot")
    _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published, commercial_status) "
        "VALUES (:s, :m, :n, TRUE, 'DISCONTINUED')",
        s=published, m=mfr_id, n=published.upper(),
    )
    _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published, commercial_status) "
        "VALUES (:s, :m, :n, FALSE, 'ANNOUNCED')",
        s=unpublished, m=mfr_id, n=unpublished.upper(),
    )
    try:
        yield {"id": mfr_id, "slug": slug, "published": published, "unpublished": unpublished}
    finally:
        _exec(
            "DELETE FROM evidence_source WHERE subject_type='MANUFACTURER' AND subject_id=:m",
            m=mfr_id,
        )
        _exec("DELETE FROM robot WHERE manufacturer_id = :m", m=mfr_id)
        _exec("DELETE FROM manufacturer WHERE id = :m", m=mfr_id)


def _detail(client, slug: str):
    resp = client.get(f"/api/manufacturers/{slug}")
    assert resp.status_code == 200
    return resp


def test_unknown_listing_status_is_null_never_false(client, profiled_maker) -> None:
    body = _detail(client, profiled_maker["slug"]).json()
    assert body["is_public_company"] is None


def test_an_explicit_listing_claim_round_trips(client, profiled_maker) -> None:
    _exec("UPDATE manufacturer SET is_public_company = FALSE WHERE id = :m", m=profiled_maker["id"])
    assert _detail(client, profiled_maker["slug"]).json()["is_public_company"] is False
    _exec(
        "UPDATE manufacturer SET is_public_company = TRUE, ticker = 'TEST: 1' WHERE id = :m",
        m=profiled_maker["id"],
    )
    body = _detail(client, profiled_maker["slug"]).json()
    assert body["is_public_company"] is True
    assert body["ticker"] == "TEST: 1"


def test_location_ownership_deployment_and_markets_are_distinct_fields(
    client, profiled_maker
) -> None:
    body = _detail(client, profiled_maker["slug"]).json()
    assert body["headquarters_city"] == "Testville"
    assert body["incorporation"] == "United States (Delaware)"
    assert body["operating_locations"] == ["Plant A"]
    assert body["target_markets"] == ["logistics", "research"]
    assert body["deployment_status"] == "PILOT"
    assert body["deployment_note"] == "Customer trial; terms undisclosed"
    # The parent's listing is the parent's, reported beside — not as — the entity's.
    assert body["parent_company"] == "Group Co"
    assert body["parent_listing"] == "NYSE: GRP"
    assert body["parent_relationship"] == "Controlling shareholder"
    assert body["is_public_company"] is None


def test_company_sources_carry_fields_and_retrieval_but_not_internal_notes(
    client, profiled_maker
) -> None:
    resp = _detail(client, profiled_maker["slug"])
    sources = resp.json()["sources"]
    assert len(sources) == 2
    agent = next(s for s in sources if s["source_url"] == "https://example.test/filing")
    legacy = next(s for s in sources if s["source_url"] == "https://example.test/site")

    assert agent["claim_fields"] == ["deployment_status", "deployment_note", "parent_company"]
    assert agent["retrieval"] == "AGENT_ASSISTED_RESEARCH"
    assert agent["verified_at"] is None
    assert agent["source_type"] == "FINANCIAL_FILING"

    assert legacy["claim_fields"] == []
    assert legacy["retrieval"] is None
    assert legacy["verified_at"] is not None

    # Internal provenance wording (including the named session initiator) is not
    # a public field.
    assert "INTERNAL-PROVENANCE-MARKER" not in resp.text
    assert "note" not in agent


def test_counts_stay_derived_and_portfolio_status_speaks_for_published_only(
    client, profiled_maker
) -> None:
    detail = _detail(client, profiled_maker["slug"])
    body = detail.json()
    assert body["tracked_robot_count"] == 2
    assert body["published_robot_count"] == 1
    assert [r["slug"] for r in body["robots"]] == [profiled_maker["published"]]
    assert profiled_maker["unpublished"] not in detail.text

    items = client.get("/api/manufacturers", params={"limit": 100}).json()["items"]
    row = next(m for m in items if m["slug"] == profiled_maker["slug"])
    assert row["tracked_robot_count"] == 2
    assert row["published_robot_count"] == 1
    # The only published record is discontinued; the unpublished ANNOUNCED record
    # does not count. The label layer scopes this to published models.
    assert row["portfolio_status"] == "DISCONTINUED"
