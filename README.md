# HumanoidOnline

**The commercial intelligence and transaction infrastructure for the humanoid robotics economy.**

Not a robotics news website. HumanoidOnline helps buyers understand which humanoid robots exist, what they can actually do, whether they are commercially accessible, which fit a specific requirement, and how to proceed toward acquisition — and it is architected from day 1 as the core platform behind the future RentHumanoid.com (Phase 3), HumanoidMart.com (Phase 4) and HumanoidLease.com (Phase 5) verticals.

**Strategic sequence (permanent):** 1 Intelligence → 2 Buyer Intent → 3 Rent → 4 Buy → 5 Lease/RaaS.
MVP v0.1 implements Phases 1–2; Phases 3–5 exist dormant in the data model.

> **Pack status: BASELINE v0.1 — FROZEN / READY FOR WS1.** WS0 (Contract Consistency Hardening) completed 2026-07-23: unknown-price vs quote-only distinguished, seed satisfies G2 provenance by construction (self-checking load), B3a confidence-display test added, offer views correlate provider/region/variant with most-specific-price-wins semantics, one canonical `commercially_accessible()` predicate, PG14-safe NULL uniqueness, exact `price_type` shape constraints, RaaS exposed in the wizard.

## The implementation pack (read in this order)

| File | What it fixes |
|---|---|
| [`docs/01_PRODUCT_CONTRACT.md`](docs/01_PRODUCT_CONTRACT.md) | Scope, pages, journeys, matching behavior, lead capture, non-goals — *what must exist when v0.1 is complete* |
| [`db/schema.sql`](db/schema.sql) | **Canonical** PostgreSQL data model (validated: 22 tables, 5 views, 18 enums) |
| [`docs/02_ARCHITECTURE.md`](docs/02_ARCHITECTURE.md) | Frozen stack + architecture rules + component boundaries + workstreams |
| [`docs/03_DATA_DICTIONARY.md`](docs/03_DATA_DICTIONARY.md) | Enum semantics, NULL semantics, provenance rules |
| [`docs/04_API_CONTRACT.md`](docs/04_API_CONTRACT.md) | Endpoints + request/response shapes |
| [`docs/05_ACCEPTANCE_CRITERIA.md`](docs/05_ACCEPTANCE_CRITERIA.md) | Given/When/Then completion tests |
| [`docs/06_WIREFRAMES.md`](docs/06_WIREFRAMES.md) | Rough structural wireframes (appearance deliberately unspecified) |
| [`docs/07_VISUAL_SYSTEM.md`](docs/07_VISUAL_SYSTEM.md) | Frozen visual system (UI-D1): palette, typography, primitives, UI laws |
| [`docs/18_SYSTEM_ARCHITECTURE.md`](docs/18_SYSTEM_ARCHITECTURE.md) | End-to-end system architecture & cross-service integration topology |
| [`docs/20_AGENT_TOOL_CONTRACT.md`](docs/20_AGENT_TOOL_CONTRACT.md) | RATIFIED v0.1 — transport-independent semantic contract for AGENT-02 Query & Decide read-only tools |
| [`AGENTS.md`](AGENTS.md) | Binding operating rules for coding agents |
| [`db/seed/seed.sql`](db/seed/seed.sql) | Stress-test seed dataset (schema-validated) |

## Development roadmap

See [`docs/08_DEVELOPMENT_ROADMAP.md`](docs/08_DEVELOPMENT_ROADMAP.md) for the
current workstream sequence, completed stages, scope boundaries, exit gates and
long-term product phases. It controls delivery *sequencing*; the frozen contracts
above remain authoritative.

## Stack (frozen)

Next.js + TypeScript · FastAPI · PostgreSQL (canonical DDL) · SQLAlchemy · Pydantic · PostgreSQL full-text search · deterministic matching engine · pytest + frontend tests.

## Repository layout

```
apps/web        Next.js frontend
apps/api        FastAPI backend (incl. matching engine)
db/             schema.sql (canonical) · migrations/ · seed/
docs/           the implementation pack
tests/          cross-cutting/e2e tests
```

## Quick start (database)

`db/bootstrap.py` is the **only** governed way to initialise or migrate a
database. It applies `db/schema.sql` as the baseline, then every forward
migration in `db/migrations/`, and records each one in `schema_migrations` with
a checksum that is verified on later runs.

```bash
docker compose up -d db
export DATABASE_URL="postgresql+psycopg://humanoid:humanoid@localhost:5432/humanoidonline"
uv run db/bootstrap.py            # schema baseline + all forward migrations
uv run db/bootstrap.py --seed     # optional: load the seed dataset
```

> **Do not** run `psql -f db/schema.sql` to set up a database. It applies the
> baseline **without** the forward migrations and without the `schema_migrations`
> tracking table, producing a schema that looks right, is silently out of date,
> and cannot be verified. WS8.2 (R10) removed that path for exactly this reason.

## Three rules that must never regress

1. **Maturity ≠ obtainability ≠ evidence.** `commercial_status`, `availability_offer`, and `deployment` are independent dimensions. Never an `available` boolean.
2. **Price is never one column.** All money lives in `pricing_offer` (transaction type × price type × billing period × region × provider).
3. **Unknown stays unknown.** NULL never becomes 0, false, or "not available" — in code, matching, or display.
