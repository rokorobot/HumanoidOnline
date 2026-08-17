"""`arm_span_cm` / `reach_cm` must survive the read layer.

Migration 0005 added both columns and the importer writes them, but the API
`SpecsBlock` and `_specs_block()` projection omitted them — so a stored value
was silently invisible on every public surface. A column that exists in the
database and is never read is indistinguishable, to a consumer, from a column
that was never populated.

Span is fingertip-to-fingertip; reach is one arm from its shoulder. They are
separate measurements and neither may be derived from the other, so these tests
pin them independently and pin that a missing one stays null.

Follows the injection convention of `test_truth_regressions.py`: fixtures are
created inside the test and removed afterwards.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import engine


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def dimension_robot():
    """A published robot carrying a reach but deliberately no span."""
    mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
    slug = _uniq("dimension-probe")
    robot_id = _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published, "
        "                   arm_span_cm, reach_cm) "
        "VALUES (:s, :m, :n, TRUE, NULL, 45.0) RETURNING id",
        s=slug,
        m=mfr_id,
        n=_uniq("DIMENSION-PROBE"),
    ).scalar_one()
    try:
        yield slug
    finally:
        _exec("DELETE FROM robot WHERE id = :i", i=robot_id)


def _specs(client, slug: str) -> dict:
    resp = client.get(f"/api/robots/{slug}")
    assert resp.status_code == 200
    return resp.json()["specs"]


# --------------------------------------------------------------------------
# C1/C2 — stored values reach the API
# --------------------------------------------------------------------------


def test_stored_reach_cm_is_returned_by_the_api(client, dimension_robot) -> None:
    assert _specs(client, dimension_robot)["reach_cm"] == 45.0


def test_stored_arm_span_cm_is_returned_by_the_api(client) -> None:
    """Asserted on its own row so a single field cannot mask the other."""
    mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
    slug = _uniq("span-probe")
    robot_id = _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published, arm_span_cm) "
        "VALUES (:s, :m, :n, TRUE, 160.0) RETURNING id",
        s=slug,
        m=mfr_id,
        n=_uniq("SPAN-PROBE"),
    ).scalar_one()
    try:
        specs = _specs(client, slug)
        assert specs["arm_span_cm"] == 160.0
        # Reach was never set: it must stay null, not inherit the span.
        assert specs["reach_cm"] is None
    finally:
        _exec("DELETE FROM robot WHERE id = :i", i=robot_id)


# --------------------------------------------------------------------------
# C3 — absent stays null (never 0, never borrowed from the sibling field)
# --------------------------------------------------------------------------


def test_absent_dimension_stays_null(client, dimension_robot) -> None:
    specs = _specs(client, dimension_robot)
    assert specs["reach_cm"] == 45.0
    assert specs["arm_span_cm"] is None, (
        "a 45 cm reach must not be presented as a 45 cm fingertip-to-fingertip span"
    )


def test_both_keys_are_always_present_in_the_payload(client, dimension_robot) -> None:
    """Explicit-uncertainty contract: the key exists and is null, rather than
    being omitted so a consumer cannot tell 'unknown' from 'not modelled'."""
    specs = _specs(client, dimension_robot)
    assert "arm_span_cm" in specs
    assert "reach_cm" in specs


# --------------------------------------------------------------------------
# C4 — publication filtering is untouched by this change
# --------------------------------------------------------------------------


def test_publication_gate_unchanged_for_dimension_fields(client) -> None:
    """Exposing a spec must not expose an unpublished robot that carries it."""
    mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
    slug = _uniq("unpublished-dimension-probe")
    robot_id = _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published, reach_cm) "
        "VALUES (:s, :m, :n, FALSE, 99.0) RETURNING id",
        s=slug,
        m=mfr_id,
        n=_uniq("UNPUBLISHED-DIMENSION-PROBE"),
    ).scalar_one()
    try:
        assert client.get(f"/api/robots/{slug}").status_code == 404
        listing = client.get("/api/robots", params={"limit": 100}).json()
        assert slug not in {item["slug"] for item in listing["items"]}
    finally:
        _exec("DELETE FROM robot WHERE id = :i", i=robot_id)
