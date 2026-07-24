"""Liveness and readiness endpoints (infrastructure surface only)."""
from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.db.session import engine
from app.schemas.health import HealthStatus, ReadinessStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    """Liveness: the process is up. No dependencies are checked."""
    return HealthStatus(status="ok")


@router.get("/ready", response_model=ReadinessStatus)
def ready(response: Response) -> ReadinessStatus:
    """Readiness: can the app reach Postgres? Returns 503 if not."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessStatus(status="unavailable", database="down")
    return ReadinessStatus(status="ok", database="up")
