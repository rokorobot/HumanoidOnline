"""SQLAlchemy 2.x engine and session factory."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# `search_path` mirrors db/schema.sql's `SET search_path TO humanoid, public`,
# so unqualified identifiers resolve to the canonical schema. `pool_pre_ping`
# keeps pooled connections healthy across idle periods.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"options": f"-csearch_path={settings.db_schema},public"},
)

SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a session and closes it after the request."""
    with SessionLocal() as session:
        yield session
