"""Use-case fit safeguards against the database (seeded; skips without DATABASE_URL).

Two properties the use-case enrichment relies on
(docs/audit/USE_CASE_ENRICHMENT_REVIEW_2026-10-08.md):

1. The use-case API is published-only: an unpublished robot is absent from the
   use-case page AND from the robot_count beside it, even though its fit row
   exists.
2. A fit row with a NULL score ("associated, not rated") is invisible to
   matching: the engine input for that robot is identical with and without the
   row. It changes the use-case page only, where it lists after every scored
   robot.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.services.matching.inputs import RequirementInput
from app.services.matching.repository import load_candidates


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


def _get(client, url, **params):
    resp = client.get(url, params=params)
    assert resp.status_code == 200, (url, resp.status_code, resp.text)
    return resp.json()


def _count(client, use_case: str) -> int:
    items = _get(client, "/api/use-cases", limit=100)["items"]
    return next(i["robot_count"] for i in items if i["slug"] == use_case)


def _requirement(use_case: str) -> RequirementInput:
    return RequirementInput(
        use_case=use_case, country=None, payload_min_kg=None, operating_hours_day=None,
        manipulation_required=None, autonomy_required=None, budget_currency=None,
        budget_min=None, budget_max=None, required_by=None, preferred_transaction="UNKNOWN",
    )


def test_unpublished_robot_is_absent_from_the_use_case_page_and_its_count(
    client, database_url
) -> None:
    row = _exec(
        "SELECT r.id, r.slug, u.slug FROM use_case_fit f "
        "JOIN robot r ON r.id = f.robot_id JOIN use_case u ON u.id = f.use_case_id "
        "WHERE r.is_published ORDER BY r.slug, u.slug LIMIT 1"
    ).first()
    if row is None:
        pytest.skip("no published robot with a use-case fit to probe")
    robot_id, robot_slug, use_case = row

    before = _count(client, use_case)
    assert robot_slug in {
        r["slug"] for r in _get(client, f"/api/use-cases/{use_case}")["suitable_robots"]
    }
    _exec("UPDATE robot SET is_published = FALSE WHERE id = :i", i=robot_id)
    try:
        detail = _get(client, f"/api/use-cases/{use_case}")
        assert robot_slug not in {r["slug"] for r in detail["suitable_robots"]}
        assert _count(client, use_case) == before - 1
        # The fit row itself is untouched: exclusion is by publication, not deletion.
        assert _exec(
            "SELECT count(*) FROM use_case_fit WHERE robot_id = :i", i=robot_id
        ).scalar_one() >= 1
    finally:
        _exec("UPDATE robot SET is_published = TRUE WHERE id = :i", i=robot_id)


def test_a_null_score_fit_is_neutral_to_matching_and_lists_last(client, database_url) -> None:
    row = _exec(
        "SELECT r.id, r.slug, u.id, u.slug FROM robot r CROSS JOIN use_case u "
        "WHERE r.is_published AND NOT EXISTS ("
        "  SELECT 1 FROM use_case_fit f WHERE f.robot_id = r.id AND f.use_case_id = u.id) "
        "AND EXISTS (SELECT 1 FROM use_case_fit f2 JOIN robot r2 ON r2.id = f2.robot_id "
        "            WHERE f2.use_case_id = u.id AND r2.is_published AND f2.fit_score IS NOT NULL) "
        "ORDER BY r.slug, u.slug LIMIT 1"
    ).first()
    if row is None:
        pytest.skip("no published robot lacking a fit for a scored use case")
    robot_id, robot_slug, use_case_id, use_case = row
    req = _requirement(use_case)

    with SessionLocal() as s:
        before = {c.slug: c for c in load_candidates(s, req)}
    count_before = _count(client, use_case)

    _exec(
        "INSERT INTO use_case_fit (robot_id, use_case_id, fit_score, notes) "
        "VALUES (:r, :u, NULL, 'associated, not rated')",
        r=robot_id, u=use_case_id,
    )
    try:
        with SessionLocal() as s:
            after = {c.slug: c for c in load_candidates(s, req)}
        # Matching sees no difference at all — not for this robot, not for any other.
        assert after == before
        assert after[robot_slug].use_case_fit is None

        # The use-case page is where the row shows: present, unrated, after scored rows.
        suitable = _get(client, f"/api/use-cases/{use_case}")["suitable_robots"]
        scores = [r["fit_score"] for r in suitable]
        mine = next(r for r in suitable if r["slug"] == robot_slug)
        assert mine["fit_score"] is None
        first_unrated = scores.index(None)
        assert all(sc is None for sc in scores[first_unrated:])
        assert all(sc is not None for sc in scores[:first_unrated])
        assert _count(client, use_case) == count_before + 1
    finally:
        _exec(
            "DELETE FROM use_case_fit WHERE robot_id = :r AND use_case_id = :u",
            r=robot_id, u=use_case_id,
        )
