"""GET /api/robots/compare caching (perf task): the response body/shape must
be byte-for-byte unaffected by whether it came from the cache, and an invalid
or differently-ordered request must never share a cache entry with a valid or
differently-ordered one. See app/services/compare_cache.py for the mechanism
and app/routers/robots.py::compare_robots for how it's wired in.
"""
from __future__ import annotations

from app.services import compare_cache


def _get(client, **params):
    return client.get("/api/robots/compare", params=params)


# ---- MISS then HIT ---------------------------------------------------------


def test_first_request_is_a_cache_miss(client, database_url) -> None:
    resp = _get(client, ids="unitree-g1,digit")
    assert resp.status_code == 200
    assert resp.headers["x-app-cache"] == "MISS"
    assert "s-maxage=" in resp.headers["cache-control"]


def test_identical_subsequent_request_is_a_cache_hit(client, database_url) -> None:
    first = _get(client, ids="unitree-g1,digit")
    assert first.headers["x-app-cache"] == "MISS"

    second = _get(client, ids="unitree-g1,digit")
    assert second.headers["x-app-cache"] == "HIT"


def test_hit_response_body_is_identical_to_the_miss_response(client, database_url) -> None:
    first = _get(client, ids="unitree-g1,digit")
    second = _get(client, ids="unitree-g1,digit")
    assert first.json() == second.json()
    assert first.status_code == second.status_code == 200


# ---- separate cache keys ----------------------------------------------------


def test_different_robot_ids_use_a_separate_cache_key(client, database_url) -> None:
    a = _get(client, ids="unitree-g1,digit")
    assert a.headers["x-app-cache"] == "MISS"

    # A different combination has never been requested: still a MISS, not
    # accidentally served the first pair's cached response.
    b = _get(client, ids="unitree-g1,optimus")
    assert b.headers["x-app-cache"] == "MISS"
    assert b.json() != a.json()


def test_reordered_ids_are_not_treated_as_the_same_key(client, database_url) -> None:
    """compare_robots iterates ids in the caller's order to build both the
    `robots` array and each row's `values` mapping, so ids=a,b and ids=b,a are
    genuinely different responses (different key/array ordering) — canonicalizing
    the cache key by sorting would make one silently receive the other's shape.
    """
    forward = _get(client, ids="unitree-g1,digit")
    reverse = _get(client, ids="digit,unitree-g1")

    assert forward.headers["x-app-cache"] == "MISS"
    # If this were "HIT", the cache key would have been order-independent —
    # exactly the bug requirement #4 warns against.
    assert reverse.headers["x-app-cache"] == "MISS"

    assert [r["slug"] for r in forward.json()["robots"]] == ["unitree-g1", "digit"]
    assert [r["slug"] for r in reverse.json()["robots"]] == ["digit", "unitree-g1"]

    row_f = next(r for r in forward.json()["rows"] if r["key"] == "commercial_status")
    row_r = next(r for r in reverse.json()["rows"] if r["key"] == "commercial_status")
    assert list(row_f["values"].keys()) == ["unitree-g1", "digit"]
    assert list(row_r["values"].keys()) == ["digit", "unitree-g1"]

    # A second call in each order now hits its OWN entry, not the other's.
    assert _get(client, ids="unitree-g1,digit").headers["x-app-cache"] == "HIT"
    assert _get(client, ids="digit,unitree-g1").headers["x-app-cache"] == "HIT"


# ---- TTL expiry --------------------------------------------------------------


def test_cache_entry_expires_after_the_configured_ttl(client, database_url, monkeypatch) -> None:
    fake_now = [1_000.0]
    monkeypatch.setattr(compare_cache, "clock", lambda: fake_now[0])

    first = _get(client, ids="unitree-g1,digit")
    assert first.headers["x-app-cache"] == "MISS"

    # Still within TTL (default 60s; move the clock forward but not past it).
    fake_now[0] += 30
    still_cached = _get(client, ids="unitree-g1,digit")
    assert still_cached.headers["x-app-cache"] == "HIT"

    # Past TTL: must recompute, not serve the stale entry.
    fake_now[0] += 31  # 61s total since the MISS
    expired = _get(client, ids="unitree-g1,digit")
    assert expired.headers["x-app-cache"] == "MISS"


# ---- errors are never cached -------------------------------------------------


def test_invalid_request_is_not_cached(client, database_url) -> None:
    bad = _get(client, ids="unitree-g1")  # only one valid slug: 422
    assert bad.status_code == 422

    # A subsequent VALID request for an overlapping-looking key must still be
    # computed fresh (i.e. the 422 must not have written anything cacheable).
    good = _get(client, ids="unitree-g1,digit")
    assert good.status_code == 200
    assert good.headers["x-app-cache"] == "MISS"


def test_unknown_slug_alone_with_a_valid_one_stays_uncached_until_two_valid(
    client, database_url
) -> None:
    """A slug that doesn't resolve to a published robot is silently dropped
    (existing behaviour, unchanged) — if that drops the valid count below 2,
    it's still the same 422-and-don't-cache path as any other invalid request."""
    bad = _get(client, ids="unitree-g1,does-not-exist")
    assert bad.status_code == 422
    assert compare_cache.get(compare_cache.cache_key(["unitree-g1", "does-not-exist"])) is None


# ---- response payload unaffected by caching ----------------------------------


def test_three_and_four_way_compare_still_match_contract_when_cached(
    client, database_url
) -> None:
    ids = "unitree-g1,digit,optimus"
    first = _get(client, ids=ids)
    second = _get(client, ids=ids)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert {"robots", "rows"} <= first.json().keys()
