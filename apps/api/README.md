# apps/api — HumanoidOnline backend (WS1 foundation)

FastAPI (Python 3.12+) · SQLAlchemy 2.x · Pydantic v2 · Postgres via psycopg.

WS1 scope: the executable backend foundation only — settings, DB engine/session,
ORM models that **mirror** the canonical `db/schema.sql`, health/readiness, and
the pytest harness. No product features.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages Python 3.12 and dependencies)
- A reachable Postgres with the schema applied. From the repo root:
  ```bash
  docker compose up -d db
  uv run db/bootstrap.py            # apply db/schema.sql
  uv run db/bootstrap.py --seed     # optional: load the seed dataset
  ```

## Install & run

```bash
cd apps/api
uv sync
uv run python -m uvicorn app.main:app --reload   # http://localhost:8000
```

Endpoints: `GET /` (descriptor) · `GET /health` (liveness) · `GET /ready`
(readiness — 200 if Postgres is reachable, else 503).

## Test

```bash
cd apps/api
uv run pytest
```

DB-backed tests skip automatically unless `DATABASE_URL` is set:

```bash
export DATABASE_URL=postgresql+psycopg://humanoid:humanoid@localhost:5432/humanoidonline
uv run pytest
```

## Conventions (binding — see ../../AGENTS.md)

- `db/schema.sql` is canonical. Models mirror it; we never `create_all()` or
  autogenerate DDL, and PG enums use `create_type=False`.
- Business logic lives here, not in the frontend.
