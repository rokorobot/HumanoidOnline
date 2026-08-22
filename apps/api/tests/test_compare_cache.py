"""GET /api/robots/compare caching (perf task; Emergency Compare Traffic
Containment 2026-08-22): the response body/shape must be byte-for-byte
unaffected by whether it came from the cache, an invalid request must never
poison the cache, and a differently-ordered request for the SAME robot set now
shares one cache entry with its permutations (order-independent key) while
still receiving its own requested display order. A request for a DIFFERENT
robot set always gets its own entry. See app/services/compare_cache.py for the
mechanism and app/routers/robots.py::compare_robots / _reordered_for_request
for how it's wired in.
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


def test_reordered_ids_share_one_cache_entry_but_the_response_still_follows_the_request(
    client, database_url
) -> None:
    """Emergency Compare Traffic Containment (2026-08-22): production logs showed
    the same robot SET requested repeatedly in different permutations in a short
    window, each one a separate cache MISS under the old order-preserving key.
    The cache key is now order-independent, so ids=a,b and ids=b,a share one
    underlying computation (one detail+evidence load, not two) — but the
    RESPONSE each caller receives must still be genuinely theirs: compare_robots
    still builds `robots` and each row's `values` in the CALLER's requested
    order (reshaped from the shared cache entry on a HIT, never recomputed).
    """
    forward = _get(client, ids="unitree-g1,digit")
    assert forward.headers["x-app-cache"] == "MISS"

    reverse = _get(client, ids="digit,unitree-g1")
    # Now a HIT — same robot set, one shared cache entry (the fix).
    assert reverse.headers["x-app-cache"] == "HIT"

    # But the OUTPUT order is still exactly what each request asked for.
    assert [r["slug"] for r in forward.json()["robots"]] == ["unitree-g1", "digit"]
    assert [r["slug"] for r in reverse.json()["robots"]] == ["digit", "unitree-g1"]

    row_f = next(r for r in forward.json()["rows"] if r["key"] == "commercial_status")
    row_r = next(r for r in reverse.json()["rows"] if r["key"] == "commercial_status")
    assert list(row_f["values"].keys()) == ["unitree-g1", "digit"]
    assert list(row_r["values"].keys()) == ["digit", "unitree-g1"]
    # Same underlying facts either way — only the order differs.
    assert row_f["values"] == row_r["values"]

    # Further calls in either order keep hitting the one shared entry.
    assert _get(client, ids="unitree-g1,digit").headers["x-app-cache"] == "HIT"
    assert _get(client, ids="digit,unitree-g1").headers["x-app-cache"] == "HIT"


def test_reordered_hit_matches_a_fresh_computation_byte_for_byte(
    client, database_url
) -> None:
    """The module docstring's invariant ('response body/shape must be
    byte-for-byte unaffected by whether it came from the cache') must hold
    across a reorder-on-hit too, not just a same-order hit: a permutation
    served from the shared cache entry must be indistinguishable from what a
    fresh computation in that exact order would have produced.
    """
    _get(client, ids="unitree-g1,digit")  # warm the shared entry (MISS)
    hit = _get(client, ids="digit,unitree-g1")
    assert hit.headers["x-app-cache"] == "HIT"

    compare_cache.clear()
    fresh = _get(client, ids="digit,unitree-g1")
    assert fresh.headers["x-app-cache"] == "MISS"

    assert hit.json() == fresh.json()


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


def test_more_than_four_valid_slugs_still_rejected_max_count_unchanged(
    client, database_url
) -> None:
    """Emergency Compare Traffic Containment touches WHICH requests share a
    cache entry, never the 2-4 count boundary itself — five valid, published,
    all-distinct robots must still 422, exactly as before."""
    resp = _get(client, ids="unitree-g1,unitree-h1,digit,optimus,figure-02")
    assert resp.status_code == 422
    assert (
        compare_cache.get(
            compare_cache.cache_key(
                ["unitree-g1", "unitree-h1", "digit", "optimus", "figure-02"]
            )
        )
        is None
    )


# ---- cache_key is a pure, order-independent, set-sensitive function ----------


def test_cache_key_is_permutation_invariant() -> None:
    """The core of the fix: any ordering of the same slug set produces the
    identical cache key."""
    a = compare_cache.cache_key(["unitree-g1", "digit", "optimus"])
    b = compare_cache.cache_key(["optimus", "unitree-g1", "digit"])
    c = compare_cache.cache_key(["digit", "optimus", "unitree-g1"])
    assert a == b == c


def test_cache_key_still_distinguishes_different_sets() -> None:
    """Permutation-invariance must not collapse genuinely different robot
    sets onto the same key."""
    assert compare_cache.cache_key(["unitree-g1", "digit"]) != compare_cache.cache_key(
        ["unitree-g1", "optimus"]
    )
    # Different SIZE sets (a strict subset) must also differ.
    assert compare_cache.cache_key(
        ["unitree-g1", "digit", "optimus"]
    ) != compare_cache.cache_key(["unitree-g1", "digit"])


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
