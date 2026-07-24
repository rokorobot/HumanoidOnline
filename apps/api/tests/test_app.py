"""The FastAPI app imports, starts, and exposes its infrastructure surface."""
from __future__ import annotations

from fastapi import FastAPI


def test_app_is_fastapi() -> None:
    from app.main import app

    assert isinstance(app, FastAPI)


def test_infra_routes_registered() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"].keys())
    assert {"/", "/health", "/ready"} <= paths


def test_health_ok(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_descriptor(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
