"""FastAPI application entrypoint (WS1 foundation).

Infrastructure surface only — health/readiness and a root descriptor. No product
features (catalogue, matching, leads, admin) are implemented here; those belong
to later workstreams.

Run locally:  uv run python -m uvicorn app.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings
from app.routers import health

settings = get_settings()

app = FastAPI(title=settings.api_title, version=settings.api_version)
app.include_router(health.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "status": "ok",
    }
