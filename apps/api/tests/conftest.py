"""Shared pytest fixtures."""
from __future__ import annotations

import os
import time

# WS8.2 / R7 — the suite IS the test environment, and it must say so before
# anything imports the app. With APP_ENV unset the contract resolves to
# production, which (correctly) refuses to start without an explicit
# DATABASE_URL; declaring it here keeps a DB-less local run importable while
# leaving the strict path fully exercised by test_config_contract.py.
os.environ.setdefault("APP_ENV", "test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.security.rate_limit import RATE_LIMITER, RateLimitPolicy
from app.services import compare_cache  # noqa: E402

#: WS8.1 / R3. The limiter is a process-local singleton (DEP P2/P3), so state
#: leaks between tests unless it is reset. The rest of the suite predates rate
#: limiting and legitimately posts repeatedly, so it runs under permissive
#: policies; `test_rate_limiting.py` installs tight policies itself and proves
#: the enforcement, and `test_security_boundaries.py` separately asserts that
#: the *shipped defaults* are strict.
_PERMISSIVE = 10_000


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    RATE_LIMITER.reset()
    for name in ("buyer_requirements", "commercial_leads"):
        RATE_LIMITER.set_policy(
            RateLimitPolicy(
                name=name,
                burst_limit=_PERMISSIVE,
                burst_window_seconds=60,
                sustained_limit=_PERMISSIVE,
                sustained_window_seconds=3600,
            )
        )
    yield
    RATE_LIMITER.reset()
    RATE_LIMITER.load_from_settings()


@pytest.fixture(autouse=True)
def reset_compare_cache():
    """The compare cache (app/services/compare_cache.py) is a process-local
    singleton, same story as the rate limiter above: the `client` fixture is
    session-scoped, so without a reset a cache entry warmed by one test would
    silently serve stale (or just cross-test-polluting) data to the next."""
    compare_cache.clear()
    compare_cache.clock = time.monotonic
    yield
    compare_cache.clear()
    compare_cache.clock = time.monotonic


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def database_url() -> str:
    """DB-backed tests require a reachable Postgres.

    CI always sets DATABASE_URL, so these tests run there. Locally, if it is
    unset, the DB-backed tests skip (run `docker compose up -d db` +
    `uv run db/bootstrap.py` first, then export DATABASE_URL).
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set; skipping DB-backed test")
    return url


@pytest.fixture
def no_external_network(monkeypatch):
    """Discovery Stage B (docs/16 Gate P): the suite never contacts a real site.

    Loopback stays reachable because the DB-backed tests talk to a local
    Postgres; any other address — or any name resolution for a non-loopback
    host — fails the test. Acquisition tests use httpx.MockTransport, which
    never opens a socket, so this guard only fires if something bypasses it.
    """
    import socket

    loopback = ("127.0.0.1", "::1", "localhost")
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def guarded_connect(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in loopback:
            pytest.fail(f"external network access attempted: {address!r}")
        return real_connect(sock, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in loopback and host is not None:
            pytest.fail(f"external name resolution attempted: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
