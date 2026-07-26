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

from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401  (register all ORM models on Base.metadata)
from app.admin import mount_admin
from app.config import get_settings
from app.db.migration_state import enforce_migration_state_at_startup
from app.db.session import engine
from app.observability import (
    RequestObservabilityMiddleware,
    configure_logging,
)
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
from app.security.client_ip import validate_trusted_ingress_config
from app.security.headers import SecurityHeadersMiddleware, configure_cors

settings = get_settings()

# WS8.6 / R25 — structured logging + request correlation before anything logs.
configure_logging(settings.app_env)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """WS8.2 / R9 — migration-before-app-start, enforced at application level.

    Strict environments refuse to serve a database whose migration state does
    not match this build; relaxed ones log and continue. The mechanism that
    guarantees migrations have *run* before the process starts belongs to
    WS8.7 — this is the contract it will bind to.
    """
    enforce_migration_state_at_startup(engine)
    yield


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)

# WS8.1 / R4 — the security posture is now explicit and tested (WS8-L9) rather
# than an accident of same-origin browser rules. `configure_cors` installs CORS
# ONLY when an explicit allowlist is configured; the default is strict
# same-origin, and `CORS_ALLOWED_ORIGINS` is the documented opt-in.
app.add_middleware(SecurityHeadersMiddleware)
CORS_ALLOWED_ORIGINS = configure_cors(app)

# WS8.6 / R25 — added LAST so it is the OUTERMOST application middleware: it
# assigns the correlation id first and observes every request (and any exception
# propagating out), then re-raises so the framework produces the response.
app.add_middleware(RequestObservabilityMiddleware)

# DEP P1 — parse the trusted-ingress configuration at import so a malformed
# value refuses to boot. Silently reinterpreting it as "trust nobody" would
# collapse every client behind the proxy onto one address and rate-limit them
# as a single caller — an outage that looks nothing like a config error.
TRUSTED_INGRESS = validate_trusted_ingress_config()

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
