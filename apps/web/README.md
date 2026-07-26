# apps/web — HumanoidOnline frontend (WS3 Intelligence UI)

Next.js (App Router, Next 15 + React 19) + TypeScript. Vitest + Playwright.

WS3 productionizes the FROZEN UI-D1 visual system (`docs/07_VISUAL_SYSTEM.md`)
against the WS2A read API + WS2B verified catalogue. Next.js Server Components
fetch the API server-side and render; **FastAPI decides, Next renders**
(`docs/02_ARCHITECTURE.md`). Every commercial fact — price, availability,
maturity, evidence, counts — comes from the API at runtime. UNKNOWN is a designed
state; QUOTE_ONLY ("Price on request") never collapses into UNKNOWN ("No confirmed
pricing").

## Layout

- `app/tokens.css` — the UI-D1 design tokens + grammar, ported **verbatim** from
  `docs/design/tokens.css`.
- `app/globals.css` — layout classes lifted from the approved reference
  compositions (`docs/design/*.html`).
- `lib/` — `server.ts` (server base URL), `types.ts` (API contract mirror),
  `api-client.ts` (typed fetch), `format.ts` (frozen price/availability state
  logic), `search-params.ts` (URL ⇄ API filter mapping).
- `components/` — the UI-D1 primitives as React components.
- `app/` — routes: `/`, `/robots`, `/robots/[slug]`, `/compare`,
  `/manufacturers[/slug]`, `/use-cases[/slug]`, `/find-a-humanoid` (dormant ref).

## Prerequisites

- Node.js 20+ and npm.

## Install & run

```bash
cd apps/web
npm ci
API_BASE_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

Configure the backend URL via `API_BASE_URL` (server) — see `.env.example`.

## Verify (same checks CI runs — `web-build`)

```bash
npm run typecheck   # tsc --noEmit
npm run test        # vitest run (pure state-logic unit tests)
npm run build       # next build
```

## Integration gate (the `web-integration` CI job)

Proves the frontend renders the **verified catalogue**, not seed/mock. The full
chain — fresh Postgres → `db/bootstrap.py` → `db/import_catalogue.py` → FastAPI →
Next (built) → Playwright:

```bash
# 1. fresh DB + verified catalogue
docker exec humanoidonline-db psql -U humanoid -d postgres -c "DROP DATABASE IF EXISTS ws3_catalogue;"
docker exec humanoidonline-db psql -U humanoid -d postgres -c "CREATE DATABASE ws3_catalogue;"
export DATABASE_URL="postgresql+psycopg://humanoid:humanoid@localhost:5432/ws3_catalogue"
uv run db/bootstrap.py && uv run db/import_catalogue.py

# 2. API
(cd apps/api && uv sync && DATABASE_URL="$DATABASE_URL" uv run python -m uvicorn app.main:app --port 8000)

# 3. web + e2e (Playwright starts `next start` itself, pointed at the API)
cd apps/web && npm ci && npx playwright install chromium && npm run build
API_BASE_URL=http://127.0.0.1:8000 npm run e2e
# or against an already-running server: WEB_BASE_URL=http://127.0.0.1:3000 npm run e2e
```

Asserted regression truths (WS2B): G1 = **$13,500 PUBLIC** (never $16,000),
unitree-h1 = **QUOTE_ONLY / "Price on request"** (never $90,000), figure-02 =
**DISCONTINUED**, agility-digit = explicit **"No confirmed pricing"** (never $0),
and QUOTE_ONLY vs UNKNOWN render as visibly distinct states.
