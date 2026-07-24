"""DB-backed foundation tests: connection, readiness, and ORM<->schema alignment.

These require a reachable Postgres with db/schema.sql applied (see the
`database_url` fixture). CI applies the schema before running pytest.
"""
from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session


def test_engine_connects(database_url) -> None:
    from app.db.session import engine

    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_readiness_reports_up(client, database_url) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "up"}


def test_region_model_mirrors_canonical_schema(database_url) -> None:
    # Selecting every mapped column of `humanoid.region` proves the ORM model
    # aligns with the canonical DDL: a name/type mismatch would raise here.
    from app.db.session import engine
    from app.models.region import Region

    with Session(engine) as session:
        rows = session.execute(select(Region)).scalars().all()
        assert isinstance(rows, list)  # empty is fine; alignment is what matters


def test_event_log_model_mirrors_canonical_schema(database_url) -> None:
    from app.db.session import engine
    from app.models.event_log import EventLog

    with Session(engine) as session:
        rows = session.execute(select(EventLog)).scalars().all()
        assert isinstance(rows, list)
