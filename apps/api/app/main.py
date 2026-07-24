"""FastAPI application entrypoint.

WS1 established the infrastructure surface (health/readiness). WS2 adds the
Knowledge-Layer READ API (robots, manufacturers, use-cases) plus a minimal
internal admin. Decision/transaction features (matching, buyer intent, leads)
are later workstreams and are intentionally absent.

Run locally:  uv run python -m uvicorn app.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI

import app.models  # noqa: F401  (register all ORM models on Base.metadata)
from app.admin import mount_admin
from app.config import get_settings
from app.routers import health, manufacturers, robots, stats, use_cases

settings = get_settings()

app = FastAPI(title=settings.api_title, version=settings.api_version)

app.include_router(health.router)
app.include_router(robots.router)
app.include_router(manufacturers.router)
app.include_router(use_cases.router)
app.include_router(stats.router)

# Internal-only admin at /admin (network-gate in deployment; not public).
mount_admin(app)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "status": "ok",
    }
