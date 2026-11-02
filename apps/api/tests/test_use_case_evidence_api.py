"""DR-C2: `GET /api/use-cases/{slug}` returns the use case's evidence as `sources`, in the
shape `GET /api/manufacturers/{slug}` uses. Every fixture row is created inside the test
and removed afterwards, so the shared seeded database is left as found."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import engine

AGENT_NOTE = (
    "RETRIEVAL: AGENT_ASSISTED_RESEARCH (docs/26) - retrieved 2026-11-02 in a session "
    "initiated by INTERNAL-PROVENANCE-MARKER. Not human-verified."
)


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


@pytest.fixture
def use_case(database_url):
    slug = f"uc-api-{uuid.uuid4().hex[:10]}"
    uc_id = _exec(
        "INSERT INTO use_case (slug, name, description) VALUES (:s, 'Evidence test', 'Text.') "
        "RETURNING id", s=slug).scalar_one()
    # A MANUFACTURER row with the same subject id value must never leak into a use case.
    _exec(
        "INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type, "
        "observed_at, confidence, claim_fields) VALUES "
        "('MANUFACTURER', :u, 'https://example.test/not-a-use-case', 'MANUFACTURER_SITE', "
        "'2026-11-03', 'HIGH', ARRAY['description'])", u=uc_id)
    try:
        yield {"id": uc_id, "slug": slug}
    finally:
        _exec("DELETE FROM evidence_source WHERE subject_id = :u", u=uc_id)
        _exec("DELETE FROM use_case WHERE id = :u", u=uc_id)


def _add(uc_id, url, observed, fields, *, note=None, verified=None):
    _exec(
        "INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type, "
        "source_title, excerpt, observed_at, verified_at, confidence, note, claim_fields) "
        "VALUES ('USE_CASE', :u, :url, 'PRESS_RELEASE', 'A title', 'INTERNAL-EXCERPT', "
        ":obs, :ver, 'HIGH', :note, :f)",
        u=uc_id, url=url, obs=observed, ver=verified, note=note, f=fields)


def test_a_use_case_without_evidence_has_empty_sources(client, use_case) -> None:
    body = client.get(f"/api/use-cases/{use_case['slug']}").json()
    assert body["sources"] == []


def test_sources_carry_fields_and_retrieval_but_not_notes(client, use_case) -> None:
    _add(use_case["id"], "https://example.test/old", "2026-10-01", ["description"])
    _add(use_case["id"], "https://example.test/new", "2026-11-02",
         ["description", "key_limitations"], note=AGENT_NOTE)
    resp = client.get(f"/api/use-cases/{use_case['slug']}")
    assert resp.status_code == 200
    sources = resp.json()["sources"]

    # Newest observation first; the MANUFACTURER row is not included.
    assert [s["source_url"] for s in sources] == ["https://example.test/new",
                                                 "https://example.test/old"]
    new, old = sources
    assert new["claim_fields"] == ["description", "key_limitations"]
    assert new["retrieval"] == "AGENT_ASSISTED_RESEARCH"
    assert new["verified_at"] is None and new["confidence"] == "HIGH"
    assert new["source_type"] == "PRESS_RELEASE" and new["source_title"] == "A title"
    assert old["retrieval"] is None
    # Same keys as ManufacturerDetail.sources; the internal note is not a public field.
    assert set(new) == {"claim_fields", "source_type", "source_title", "source_url",
                        "published_at", "observed_at", "verified_at", "confidence",
                        "retrieval"}
    assert "INTERNAL-PROVENANCE-MARKER" not in resp.text


def test_the_shape_matches_the_manufacturer_sources(client, use_case) -> None:
    from app.schemas.manufacturer import ManufacturerSource
    from app.schemas.use_case import UseCaseDetail

    field = UseCaseDetail.model_fields["sources"]
    assert field.annotation == list[ManufacturerSource]
