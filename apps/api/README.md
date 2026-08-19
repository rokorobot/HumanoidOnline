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
  uv run db/bootstrap.py            # schema baseline + forward migrations
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

## Lead notification (operational email)

`POST /api/commercial-leads` (`app/routers/commercial_leads.py`) sends an
operational email to HumanoidOnline ops whenever it creates or extends a
commercial lead — see `app/services/lead_notifications.py`.

- **Database capture is authoritative.** The lead is validated, persisted and
  committed by `app/services/leads/service.py` *before* a notification is ever
  attempted. Email delivery is an operational notification only — a side
  channel, never part of the write.
- **Mail delivery failure never deletes, rejects, or retries an already-valid
  commercial lead.** `notify_lead_captured()` never raises; any failure
  (timeout, network error, non-2xx from the provider) is caught, logged
  without PII, and the endpoint still returns its normal 201/200.
- Delivery is synchronous, inline in the request, with a short fixed timeout —
  deliberately not a fire-and-forget background task after the response, kept
  simple rather than adding a queue/worker dependency for v0.1.

HumanoidOnline's deployment split: this FastAPI backend runs on **Koyeb**, the
frontend on **Netlify**, and the database on **Neon**. This notification runs
entirely server-side in the FastAPI backend, so its configuration (see
`.env.example` for the full documented block) belongs in **Koyeb's**
production environment variables (Koyeb Console -> service -> Settings ->
Environment variables) — **never in source control, and never in Netlify or
as a `NEXT_PUBLIC_*` variable**:

- `LEAD_NOTIFICATION_ENABLED` — off by default; the feature is fully inert
  until this and the other three are all set.
- `LEAD_NOTIFICATION_TO` — comma-separated recipient address(es).
- `LEAD_NOTIFICATION_FROM` — the sending address.
- `EMAIL_API_KEY` — the email provider's API key (never logged).
- `EMAIL_API_ENDPOINT` — optional, non-secret; defaults to Resend's send
  endpoint.
