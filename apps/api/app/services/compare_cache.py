"""In-process, TTL-based cache for `GET /api/robots/compare` responses.

This is a **secondary, defense-in-depth** layer, not the primary caching
mechanism. The primary mechanism is the `Cache-Control` header the router sets
on a successful response (see `routers/robots.py`), which Vercel's CDN honours
for a public GET with no cookies/auth: a cache HIT there never re-invokes this
serverless function at all, which is what actually avoids repeated origin
compute for the common case of many edge requests during the TTL window.

This module exists for two things a CDN cache cannot give us:

  1. Avoiding recomputation *within one warm process* — e.g. several near-
     simultaneous first-requests for the same comparison landing on the same
     already-warm serverless instance before any CDN entry exists yet.
  2. Testability — a CDN's edge cache is not something a local test suite can
     observe or control, so the HIT/MISS/TTL-expiry behaviour this feature
     needs tests for is written against this layer instead.

Deliberately NOT relied on as the sole mechanism (see the module read before
this was written, and the caller in `routers/robots.py`): a Vercel serverless
deployment may run this code as several independent, non-shared processes, so
a dict living in one process's memory is never a complete cache on its own.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.schemas.robot import CompareResponse

#: Overridable by tests (monkeypatch this attribute) so TTL expiry can be
#: exercised deterministically without a real sleep.
clock = time.monotonic


@dataclass(frozen=True)
class _Entry:
    expires_at: float
    response: CompareResponse


_lock = threading.Lock()
_store: dict[str, _Entry] = {}


def cache_key(slugs: list[str]) -> str:
    """Build the cache key from the already-normalized (trimmed, de-duplicated)
    slug list the router computes.

    Emergency Compare Traffic Containment (2026-08-22): the key is now SORTED —
    order-INDEPENDENT — so `ids=a,b` and `ids=b,a` share one cache entry instead
    of each permutation separately re-running the expensive per-robot detail +
    evidence load. Production evidence showed the same 4-robot sets requested
    repeatedly in different permutations in a short window; an order-preserving
    key made every permutation a fresh MISS.

    This does NOT change what a caller receives: `ids=a,b` and `ids=b,a` remain
    genuinely different RESPONSES (different `robots` array / `values` order) —
    that ordering is caller-requested and preserved end-to-end (routers/robots.py
    reorders a cache HIT to match the requesting call's own slug order before
    returning it). Only the underlying computation is now shared across
    permutations of the same set; the key is an internal cache identity, never
    part of the API contract. A `\\x1f` (unit separator) join is used instead of
    a printable delimiter so a slug that happens to contain a comma or pipe can
    never collide two distinct sets onto one key.
    """
    return "\x1f".join(sorted(slugs))


def get(key: str) -> CompareResponse | None:
    """Return the cached response for `key`, or None on a miss/expiry.

    An expired entry is evicted on read (lazy expiry) rather than by a
    background sweep — simplest correct behaviour for a cache this size, and
    it means an entry never outlives its TTL even under a clock that a test
    has advanced manually.
    """
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        if entry.expires_at <= clock():
            del _store[key]
            return None
        return entry.response


def put(key: str, response: CompareResponse, ttl_seconds: float) -> None:
    """Cache `response` under `key` for `ttl_seconds`.

    Callers must only invoke this after a fully successful computation — never
    on an error path — so an invalid or failed request can never poison the
    cache for a later valid, identical request.
    """
    with _lock:
        _store[key] = _Entry(expires_at=clock() + ttl_seconds, response=response)


def clear() -> None:
    """Test-only: drop all entries. Also used to reset state between tests
    sharing the session-scoped TestClient (see conftest.py)."""
    with _lock:
        _store.clear()
