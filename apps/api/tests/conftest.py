"""Shared pytest fixtures."""
from __future__ import annotations

import os

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
