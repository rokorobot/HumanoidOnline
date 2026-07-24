# Development — HumanoidOnline (WS1 foundation)

The complete local startup path from a clean checkout. CI runs exactly these
steps (see `.github/workflows/ci.yml`), so a green laptop means a green PR.

## Prerequisites

| Tool | Version | Used for |
|---|---|---|
| [Docker](https://docs.docker.com/get-docker/) | any recent | local Postgres |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | Python 3.12 + backend deps (auto-manages Python) |
| [Node.js](https://nodejs.org/) + npm | 20+ | frontend |

`git`, and that's it — uv fetches Python 3.12 itself.

## 1. Database

The canonical model is `db/schema.sql` (never edit it to make code fit — it
wins). Start Postgres and load the schema (and optionally the seed):

```bash
docker compose up -d db

# apply db/schema.sql (+ any db/migrations/*.sql), tracked in schema_migrations
uv run db/bootstrap.py

# optional: load the stress-test seed — its embedded G2 self-check aborts the
# load if any published commercial fact lacks evidence
uv run db/bootstrap.py --seed

# optional: assert object counts + connection
uv run db/validate.py
```

`DATABASE_URL` defaults to the docker-compose database. Override it by exporting
the variable or copying `.env.example` to `.env`.

## 2. Backend (`apps/api`)

```bash
cd apps/api
uv sync
export DATABASE_URL=postgresql+psycopg://humanoid:humanoid@localhost:5432/humanoidonline
uv run pytest                                   # DB-backed tests need the URL above
uv run python -m uvicorn app.main:app --reload  # http://localhost:8000
```

Check it: `GET /health` (liveness), `GET /ready` (readiness — 200 when Postgres
is reachable).

## 3. Frontend (`apps/web`)

```bash
cd apps/web
npm ci
npm run typecheck   # tsc --noEmit
npm run test        # vitest run
npm run build       # next build
npm run dev         # http://localhost:3000
```

## Full local check (mirrors CI)

```bash
docker compose up -d db
uv run db/bootstrap.py --seed && uv run db/validate.py
( cd apps/api && uv sync --frozen && uv run ruff check . && \
  DATABASE_URL=postgresql+psycopg://humanoid:humanoid@localhost:5432/humanoidonline uv run pytest )
( cd apps/web && npm ci && npm run typecheck && npm run test && npm run build )
```

## Scope reminder

WS1 is foundation only: no product features, no visual design. See the WS1 brief
and `AGENTS.md`. The canonical schema, seed, and `docs/` implementation pack are
frozen — changes to them are separate, product-owner-reviewed work.
