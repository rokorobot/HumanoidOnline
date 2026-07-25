"""FastAPI application entrypoint.

WS1 established the infrastructure surface (health/readiness). WS2 adds the
Knowledge-Layer READ API (robots, manufacturers, use-cases) plus a minimal
internal admin. WS5 adds the first Decision-layer write path — buyer intent
(`POST /api/buyer-requirements`) with a canonical regions read. WS6 adds
deterministic matching. WS7 adds the first commercial conversion —
`POST /api/commercial-leads` (the transaction layer / monetization seam).

Run locally:  uv run python -m uvicorn app.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI

import app.models  # noqa: F401  (register all ORM models on Base.metadata)
from app.admin import mount_admin
from app.config import get_settings
from app.routers import (
    buyer_requirements,
    commercial_leads,
    health,
    manufacturers,
    regions,
    robots,
    stats,
    use_cases,
)

settings = get_settings()

app = FastAPI(title=settings.api_title, version=settings.api_version)

app.include_router(health.router)
app.include_router(robots.router)
app.include_router(manufacturers.router)
app.include_router(use_cases.router)
app.include_router(regions.router)
app.include_router(stats.router)
# WS5 — Phase-2 buyer intent (first write path).
app.include_router(buyer_requirements.router)
# WS7 — commercial lead (first commercial conversion / monetization seam).
app.include_router(commercial_leads.router)

# Internal-only admin at /admin (network-gate in deployment; not public).
mount_admin(app)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "status": "ok",
    }
