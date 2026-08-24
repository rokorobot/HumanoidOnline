"""Compare Origin Performance v0.2 — batch the governed detail + evidence
reads across the whole requested robot set on a compare cache MISS, instead
of looping `reads.load_detail()` / evidence lookup once per robot (see
app/services/reads.py::load_details and app/routers/robots.py::compare_robots).

Behavioural contract this file proves: batching must be invisible to callers.
Requested order, de-duplication, missing/unpublished dropping, the 2-4 valid
count, cache HIT/MISS semantics and evidence attached to pricing/availability/
deployments are all byte-for-byte unchanged from the old per-robot-loop path
(app/services/agent_tools/get_robot.py's already-batched-for-one-robot
evidence_rows pattern is the existing precedent this generalises to N robots;
test_compare_cache.py covers cache mechanics and is untouched by this file).
"""
from __future__ import annotations

import warnings

import pytest
from sqlalchemy import event

from app.db.session import engine
from app.services import compare_cache, reads


def _get(client, ids_csv: str):
    return client.get("/api/robots/compare", params={"ids": ids_csv})


def _queries_during(fn) -> list[str]:
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return seen


# ---- A/B/C: batched-MISS requested order is preserved for 2/3/4 robots -----


@pytest.mark.parametrize(
    "ids_csv,expected_order",
    [
        ("digit,unitree-g1", ["digit", "unitree-g1"]),
        ("optimus,digit,unitree-g1", ["optimus", "digit", "unitree-g1"]),
        (
            "unitree-h1,optimus,digit,unitree-g1",
            ["unitree-h1", "optimus", "digit", "unitree-g1"],
        ),
    ],
)
def test_batched_miss_preserves_caller_order(
    client, database_url, ids_csv, expected_order
) -> None:
    compare_cache.clear()
    resp = _get(client, ids_csv)
    assert resp.status_code == 200
    assert resp.headers["x-app-cache"] == "MISS"
    body = resp.json()
    assert [r["slug"] for r in body["robots"]] == expected_order
    row = next(r for r in body["rows"] if r["key"] == "commercial_status")
    assert list(row["values"].keys()) == expected_order


# ---- D: duplicate ids still collapse to first occurrence -------------------


def test_duplicate_ids_collapse_to_first_occurrence(client, database_url) -> None:
    compare_cache.clear()
    resp = _get(client, "digit,digit,unitree-g1")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["slug"] for r in body["robots"]] == ["digit", "unitree-g1"]


# ---- E: missing/unpublished slugs are dropped, never fabricated ------------


def test_unknown_slug_is_dropped_not_fabricated_when_enough_valid_remain(
    client, database_url
) -> None:
    compare_cache.clear()
    resp = _get(client, "unitree-g1,does-not-exist,digit")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["slug"] for r in body["robots"]] == ["unitree-g1", "digit"]


def test_dropping_below_two_valid_still_422s(client, database_url) -> None:
    """Same 422 boundary as before batching — a slug that doesn't resolve to a
    published robot must not count toward the 2-4 valid range."""
    compare_cache.clear()
    resp = _get(client, "unitree-g1,does-not-exist")
    assert resp.status_code == 422


# ---- F: cache HIT/MISS semantics unchanged (batching only runs on MISS) ----


def test_cache_hit_never_calls_the_batched_loaders(
    client, database_url, monkeypatch
) -> None:
    compare_cache.clear()
    warmup = _get(client, "unitree-g1,digit")
    assert warmup.headers["x-app-cache"] == "MISS"

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("load_details called on a cache HIT")

    monkeypatch.setattr(reads, "load_details", fail_if_called)
    hit = _get(client, "unitree-g1,digit")
    assert hit.headers["x-app-cache"] == "HIT"


# ---- G: full behavioural equivalence against the solo detail route ---------
# app/routers/robots.py::get_robot still calls reads.serialize_detail() the
# OLD way (self-computing its own evidence_rows, unbatched) — so it is an
# untouched, independent reference implementation of the same governed
# projection. Byte-for-byte equality against it proves the batched compare
# path (including pricing/availability/deployment evidence) changed nothing.


def test_batched_robots_match_the_solo_detail_route_byte_for_byte(
    client, database_url
) -> None:
    compare_cache.clear()
    resp = _get(client, "unitree-g1,digit,optimus")
    assert resp.status_code == 200
    body = resp.json()

    for robot in body["robots"]:
        solo = client.get(f"/api/robots/{robot['slug']}")
        assert solo.status_code == 200
        assert robot == solo.json()


# ---- H: load_evidence_rows called ONCE per compare MISS, not once/robot ----


def test_load_evidence_rows_called_once_per_compare_miss(
    client, database_url, monkeypatch
) -> None:
    compare_cache.clear()
    original = reads.load_evidence_rows
    calls: list[set] = []

    def spy(session, subject_ids):
        calls.append(subject_ids)
        return original(session, subject_ids)

    monkeypatch.setattr(reads, "load_evidence_rows", spy)
    resp = _get(client, "unitree-h1,optimus,digit,unitree-g1")
    assert resp.status_code == 200
    assert len(calls) == 1, f"{len(calls)} load_evidence_rows calls for a 4-robot compare MISS"


# ---- I: the batched robot load itself is called ONCE per compare MISS -----


def test_load_details_called_once_per_compare_miss(
    client, database_url, monkeypatch
) -> None:
    compare_cache.clear()
    original = reads.load_details
    calls: list[list[str]] = []

    def spy(session, slugs):
        calls.append(list(slugs))
        return original(session, slugs)

    monkeypatch.setattr(reads, "load_details", spy)
    resp = _get(client, "unitree-h1,optimus,digit,unitree-g1")
    assert resp.status_code == 200
    assert len(calls) == 1, f"{len(calls)} load_details calls for a 4-robot compare MISS"
    assert set(calls[0]) == {"unitree-h1", "optimus", "digit", "unitree-g1"}


# ---- Query-count proof: growth must be sub-linear, not another full bundle -


def test_query_count_grows_sublinearly_not_a_full_bundle_per_robot(
    client, database_url
) -> None:
    """The diagnosis's central claim: the old per-robot loop repeated a whole
    eager-load + evidence query bundle once per compared robot, so query count
    scaled ~linearly with robot count. Batching should make it grow only by a
    small, roughly constant amount as robot count goes from 2 to 4 — never
    close to doubling. Real counts are unknown ahead of a DB-backed run, so
    this is measured here rather than asserted against a hardcoded number, and
    surfaced via warnings.warn so `uv run pytest` in CI prints it even though
    the test passes (no -s / stdout capturing assumed)."""
    compare_cache.clear()
    n2 = len(_queries_during(lambda: _get(client, "unitree-g1,digit")))
    compare_cache.clear()
    n4 = len(
        _queries_during(
            lambda: _get(client, "unitree-h1,optimus,digit,unitree-g1")
        )
    )

    warnings.warn(
        f"[compare-batching v0.2] measured query counts (previously only "
        f"statically estimated) — 2 robots={n2}, 4 robots={n4}",
        stacklevel=1,
    )

    assert n4 < 1.5 * n2, (
        f"query count grew too close to linearly with robot count "
        f"(2 robots={n2} queries, 4 robots={n4} queries) — batching may not "
        f"be effective"
    )
