"""Truth semantics: TRACKED is not PUBLISHED.

*Tracked* = every robot record the intelligence catalogue holds. *Published* =
the editorially approved subset that has a public profile. Before this
correction the market snapshot reported the published count under the name
`total_tracked`, and a manufacturer card reported only published robots as its
robot count — so a manufacturer whose records exist but are unpublished
rendered as "0 ROBOTS", a false statement about that manufacturer rather than a
statement about our own publication state.

These tests pin BOTH halves at once, because either half alone is a regression
waiting to happen: the counts must widen to include unpublished records, while
the publication gate on robot lists and detail routes must not move at all.

Follows the injection convention of `test_truth_regressions.py`: every fixture
is created inside the test and removed afterwards, so the shared seeded
database is left exactly as found.
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


def _snapshot(client) -> dict:
    resp = client.get("/api/market-snapshot")
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
def unpublished_maker():
    """A manufacturer with four tracked robots and none published.

    Mirrors the real Booster Robotics shape that exposed the defect.
    """
    mfr_slug = _uniq("tracked-only-maker")
    mfr_id = _exec(
        "INSERT INTO manufacturer (slug, name) VALUES (:s, :n) RETURNING id",
        s=mfr_slug,
        n=f"Tracked Only Robotics {mfr_slug[-6:]}",
    ).scalar_one()

    robot_slugs = [_uniq(f"tracked-only-robot-{i}") for i in range(4)]
    for slug in robot_slugs:
        _exec(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
            "VALUES (:s, :m, :n, FALSE)",
            s=slug,
            m=mfr_id,
            n=slug.upper(),
        )
    try:
        yield {"id": mfr_id, "slug": mfr_slug, "robot_slugs": robot_slugs}
    finally:
        _exec("DELETE FROM robot WHERE manufacturer_id = :m", m=mfr_id)
        _exec("DELETE FROM manufacturer WHERE id = :m", m=mfr_id)


def _find(client, slug: str) -> dict | None:
    items = client.get("/api/manufacturers", params={"limit": 100}).json()["items"]
    return next((m for m in items if m["slug"] == slug), None)


# --------------------------------------------------------------------------
# G1/G2 — a tracked unpublished robot moves `total_tracked`, never `total_published`
# --------------------------------------------------------------------------


def test_unpublished_robot_counts_as_tracked_but_not_published(client) -> None:
    before = _snapshot(client)
    mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
    slug = _uniq("tracked-probe")
    robot_id = _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
        "VALUES (:s, :m, :n, FALSE) RETURNING id",
        s=slug,
        m=mfr_id,
        n=_uniq("TRACKED-PROBE-NAME"),
    ).scalar_one()
    try:
        after = _snapshot(client)
        # Tracked widens by exactly one...
        assert after["total_tracked"] == before["total_tracked"] + 1
        # ...and published does not move at all.
        assert after["total_published"] == before["total_published"]
    finally:
        _exec("DELETE FROM robot WHERE id = :i", i=robot_id)


# --------------------------------------------------------------------------
# G3/G4 — the publication gate is unchanged (counting is not exposure)
# --------------------------------------------------------------------------


def test_tracked_robot_is_still_absent_from_public_robot_surfaces(client) -> None:
    """Raising a count must not create a public profile."""
    mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
    slug = _uniq("gate-probe")
    name = _uniq("GATE-PROBE-NAME")
    robot_id = _exec(
        "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
        "VALUES (:s, :m, :n, FALSE) RETURNING id",
        s=slug,
        m=mfr_id,
        n=name,
    ).scalar_one()
    try:
        # It is counted...
        assert _snapshot(client)["total_tracked"] >= 1
        # ...but it has no listing entry and no detail route.
        listing = client.get("/api/robots", params={"limit": 100}).json()
        assert slug not in {item["slug"] for item in listing["items"]}
        assert name not in {item["name"] for item in listing["items"]}
        assert client.get(f"/api/robots/{slug}").status_code == 404
    finally:
        _exec("DELETE FROM robot WHERE id = :i", i=robot_id)


# --------------------------------------------------------------------------
# G5/G6/G7 — the manufacturer card can no longer claim "0 robots"
# --------------------------------------------------------------------------


def test_maker_with_four_unpublished_robots_reports_four_tracked_zero_published(
    client, unpublished_maker
) -> None:
    row = _find(client, unpublished_maker["slug"])
    assert row is not None, "a tracked manufacturer disappeared from the public list"
    assert row["tracked_robot_count"] == 4
    assert row["published_robot_count"] == 0


def test_maker_with_zero_published_robots_stays_in_the_public_list(
    client, unpublished_maker
) -> None:
    """Hiding the manufacturer is not an acceptable fix for the false count."""
    body = client.get("/api/manufacturers", params={"limit": 100}).json()
    assert unpublished_maker["slug"] in {m["slug"] for m in body["items"]}


def test_tracked_records_are_never_reported_as_zero(client, unpublished_maker) -> None:
    """The regression itself: records exist, so the tracked count must not be 0."""
    row = _find(client, unpublished_maker["slug"])
    assert row is not None
    assert row["tracked_robot_count"] != 0, (
        "a manufacturer with catalogue records reported zero tracked robots — "
        "this is the false '0 ROBOTS' claim the correction exists to prevent"
    )


def test_aggregate_counts_do_not_leak_unpublished_robot_content(
    client, unpublished_maker
) -> None:
    """Counts may include unpublished records; content may not accompany them."""
    detail = client.get(f"/api/manufacturers/{unpublished_maker['slug']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["robots"] == []
    serialized = detail.text
    for slug in unpublished_maker["robot_slugs"]:
        assert slug not in serialized
        assert slug.upper() not in serialized


# --------------------------------------------------------------------------
# G8 — the snapshot separates tracked makers from makers with published profiles
# --------------------------------------------------------------------------


def test_snapshot_separates_tracked_manufacturers_from_published(
    client, unpublished_maker
) -> None:
    snap = _snapshot(client)
    # The new manufacturer is tracked but contributes no published profile,
    # so the two figures must differ rather than move together.
    assert snap["manufacturers_tracked"] > snap["manufacturers_published"]
    listed = client.get("/api/manufacturers", params={"limit": 100}).json()
    assert snap["manufacturers_tracked"] == listed["total"]
