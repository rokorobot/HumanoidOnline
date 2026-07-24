"""Shared pytest fixtures."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


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
