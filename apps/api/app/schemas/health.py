"""Health/readiness response models."""
from __future__ import annotations

from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str = "ok"


class ReadinessStatus(BaseModel):
    status: str
    database: str
