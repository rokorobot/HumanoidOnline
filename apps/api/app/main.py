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
from app.security.headers import SecurityHeadersMiddleware, configure_cors

settings = get_settings()

app = FastAPI(title=settings.api_title, version=settings.api_version)

# WS8.1 / R4 — the security posture is now explicit and tested (WS8-L9) rather
# than an accident of same-origin browser rules. `configure_cors` installs CORS
# ONLY when an explicit allowlist is configured; the default is strict
# same-origin, and `CORS_ALLOWED_ORIGINS` is the documented opt-in.
app.add_middleware(SecurityHeadersMiddleware)
CORS_ALLOWED_ORIGINS = configure_cors(app)

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

# Internal admin at /admin — WS8.1 / R1: authenticated at the application layer
# and NOT mounted at all when unconfigured (fail closed). The production network
# boundary (DEP P4) is still owed by WS8.7 (R27) + WS8.8 (R29).
admin = mount_admin(app)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "status": "ok",
    }
