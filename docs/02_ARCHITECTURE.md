# HumanoidOnline — Architecture Decisions (frozen for MVP v0.1)

**Status:** Frozen. Changing anything in §1 or §2 requires explicit approval from the product owner (see `AGENTS.md` rule 1).

---

## 1. Stack (decided — do not relitigate)

| Concern | Choice |
|---|---|
| Frontend | **Next.js + TypeScript** (App Router) |
| Backend API | **FastAPI** (Python 3.12+) |
| Database | **PostgreSQL 14+** — `db/schema.sql` is canonical |
| ORM | **SQLAlchemy 2.x** (models generated to mirror the DDL, never the other way around) |
| Validation | **Pydantic v2** (request/response models = the shapes in `04_API_CONTRACT.md`) |
| Search | **PostgreSQL** full-text (`robot.search_vector`, GIN) + structured filters. No external search engine. |
| Matching engine | **Deterministic scoring** (pure Python module, spec in `01_PRODUCT_CONTRACT.md` §7) |
| Testing | **pytest** (API + matching engine) + frontend tests (Playwright or Vitest/RTL) |
| Migrations | SQL-first (Alembic acceptable, but generated migrations must match `db/schema.sql`) |
| Admin | Minimal internal CRUD (FastAPI-admin, SQLAdmin, or hand-rolled) — internal only, not styled |
| Analytics | `event_log` table + simple ingestion endpoint. No third-party analytics required for v0.1. |

## 2. Architecture rules (binding)

1. **The PostgreSQL schema is canonical.** `db/schema.sql` is the single source of truth for the data model. ORM models conform to it. If code and schema disagree, the schema wins.
2. **Business logic does not live inside UI components.** Next.js renders; FastAPI decides. The frontend never computes scores, availability logic, or price display rules beyond formatting.
3. **Matching logic must be independently testable.** The scoring engine is a pure function with no I/O; it takes plain data structures and returns `match_result` rows. pytest fixtures exercise it without a database.
4. **Commercial transaction modes must remain extensible.** All commerce is keyed by `transaction_type`. Never special-case "purchase" in a way that rental/lease/RaaS cannot reuse.
5. **Evidence/provenance is first-class.** Commercially sensitive fields (price, availability, commercial status, deployment claims, regional availability) carry `evidence_source` records: `source_url`, `source_type`, `observed_at`, `verified_at`, `confidence`. **Core rule: no commercial fact without evidence.** Unverified values are displayable only with their confidence level exposed.
6. **Unknown stays unknown.** NULL is a meaningful state everywhere. Never coerce to 0, false, or "not available" (see Product Contract §5.2 and §7.2).
7. **Dormant Phase 3–5 structures are load-bearing.** Do not remove `provider`, offer views, `transaction_type` values, or lead-routing tables because "nothing uses them yet." They are the point.
8. **Prefer boring.** No microservices, Kubernetes, Elasticsearch, event buses, or vector databases in v0.1.

## 3. Repository layout

```
humanoidonline/
├── apps/
│   ├── web/        Next.js + TypeScript frontend
│   └── api/        FastAPI backend (SQLAlchemy models, Pydantic schemas,
│                   matching engine as apps/api/.../matching/, admin)
├── db/
│   ├── schema.sql      ← canonical DDL
│   ├── migrations/     ← migration history (must converge to schema.sql)
│   └── seed/seed.sql   ← stress-test seed dataset
├── docs/
│   ├── 01_PRODUCT_CONTRACT.md
│   ├── 02_ARCHITECTURE.md          (this file)
│   ├── 03_DATA_DICTIONARY.md
│   ├── 04_API_CONTRACT.md
│   ├── 05_ACCEPTANCE_CRITERIA.md
│   └── 06_WIREFRAMES.md
├── tests/           cross-cutting/e2e tests (unit tests live beside their code)
├── AGENTS.md        agent operating rules
└── README.md
```

## 4. Component boundaries (expected, not mandated)

Reusable frontend primitives the implementation should converge on — boundaries, not pixel specs:

```
RobotCard            RobotSummary          RobotSpecifications
CommercialStatusBadge AvailabilityBadge    PricingSummary
EvidenceBadge        ManufacturerCard      UseCaseCard
ComparisonTable      FindHumanoidWizard    MatchCard
MatchExplanation     CommercialLeadForm
```

Rules of thumb: badges render enum states from `03_DATA_DICTIONARY.md` verbatim (no invented labels); `PricingSummary` always shows `price_type` context ("From", "Estimated", "Quote only"); `EvidenceBadge` renders `verified_at` + `source_type` when present; `MatchExplanation` renders only data present in `match_result.score_breakdown` / `reasons` / `warnings`.

## 5. Workstreams (suggested implementation order)

```
WS1 Foundation      repo, Next.js, FastAPI, PostgreSQL, migrations, CI
WS2 Knowledge Model manufacturers, robots, variants, specs, evidence (API + admin)
WS3 Intelligence UI catalogue, filters, robot page, manufacturers, use cases
WS4 Compare         comparison normalization + UI
WS5 Buyer Intent    requirement wizard + persistence
WS6 Matching        scoring engine + explanations (pure module + pytest first)
WS7 Commercial Lead lead conversion + admin visibility
WS8 Hardening       tests, validation, accessibility, responsive, seed validation
```

Each workstream is PR-gated and must land with its tests (AGENTS.md rule 5).
