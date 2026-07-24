"""Application settings (Pydantic v2 foundation).

Values come from the environment (or an optional local `.env`). The default
`database_url` matches docker-compose.yml so a laptop works out of the box; CI
overrides it via the DATABASE_URL environment variable.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # SQLAlchemy URL (note the "+psycopg" driver token). Matches docker-compose.yml.
    database_url: str = (
        "postgresql+psycopg://humanoid:humanoid@localhost:5432/humanoidonline"
    )
    # Canonical schema that db/schema.sql installs into.
    db_schema: str = "humanoid"

    api_title: str = "HumanoidOnline API"
    api_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
