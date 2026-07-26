# WS8 — MVP Hardening / Release

> ## STATUS: DRAFT v0.1 — AWAITING RATIFICATION — NO IMPLEMENTATION
>
> Drafted 2026-07-26 against the complete deployable surface on `main @ 217460a`.
> Nothing in this document authorizes implementation. Per the project's
> ratify-before-build discipline, WS8 hardening begins only after the product owner
> ratifies this contract and issues an explicit **`build WS8`** trigger.
>
> This contract is **subordinate** to every existing frozen contract and law:
> `01_PRODUCT_CONTRACT.md` (baseline v0.1 FROZEN), `02_ARCHITECTURE.md`,
> `03_DATA_DICTIONARY.md`, `04_API_CONTRACT.md`, `05_ACCEPTANCE_CRITERIA.md`,
> `06_WIREFRAMES.md`, `07_VISUAL_SYSTEM.md`, `09_MEDIA_CONTRACT.md` (MEDIA-01),
> `10_AGENT_CONTRACT.md` (AGENT-01), `11_DATA_D1_CONTRACT.md` (DATA-D1).
> **Where this contract conflicts with a frozen contract, the frozen contract wins.**

---

## 1. Purpose

WS8 is the **final release gate for MVP v0.1**. Its job is not to add product — it is
to prove that what already exists on `main` is fit to deploy, operate, and be trusted
by users, operators, crawlers and auditors.

WS8 is the last numbered workstream in the WS0–WS8 delivery sequence
(`08_DEVELOPMENT_ROADMAP.md` §1). Its exit state is:

```
HUMANOIDONLINE MVP v0.1 — READY FOR PRODUCTION
```

After WS8 exits, the next programme is the **post-MVP Commercial Architecture**
(Rent → Buy → Lease/RaaS → shared payments/reservations/contracting → operational
hardening), and only after *that* matures does **AGENT-01.5** (typed action parity +
MCP) open. WS8 does not touch either.

## 2. The release candidate is the WHOLE current surface

WS8 is **not** "WS0–WS7 regression." The release candidate is everything a user or
operator would actually deploy from `main`, including the three governance slices that
merged after WS7 outside the numbered sequence:

```
WS0–WS7 product surface
+ MEDIA-01  verified imagery
+ DATA-D1   discovery / admin layer
+ AGENT-01  machine-readable projections
= HumanoidOnline MVP v0.1 release candidate
```

Those additions are **in scope as part of the release candidate**, but their own
scope is **not expanded** by WS8. WS8 hardens them as they are.

## 3. Frozen laws (proposed — become FROZEN on ratification)

- **WS8-L1 — No New Capability.** WS8 adds no product capability. It hardens,
  verifies, documents, configures, and instruments what exists. Any change that a
  user could perceive as a new feature is out of scope by definition.
- **WS8-L2 — Whole-Surface Release Candidate.** The release gate covers the entire
  deployable surface (§2). A surface that ships is a surface that must be hardened;
  nothing ships un-gated because it arrived outside the numbered sequence.
- **WS8-L3 — Differentiated Depth.** Hardening depth is per-surface and specified in
  §5, not uniform. Public product carries the full quality bar; governance layers
  carry invariant-regression bars; deployment carries an operational bar.
- **WS8-L4 — No Law Weakening To Pass A Gate.** If a hardening test fails, the
  product or the test is fixed — never the governed law, gate, or contract. A
  frozen semantic (UNKNOWN ≠ 0/false/unavailable; maturity ≠ obtainability ≠
  evidence; QUOTE_ONLY ≠ UNKNOWN; candidate ≠ canonical; unpublished ≠ public;
  real robots show real verified images only; no commercial fact without evidence)
  may never be relaxed to make WS8 green.
- **WS8-L5 — Fail Closed In Production.** Production configuration must fail loudly
  when required inputs are absent. No production surface may silently fall back to a
  development default (credentials, hostnames, canonical URLs).
- **WS8-L6 — PII Containment.** No unauthenticated or public surface may expose
  `commercial_lead` / `buyer_requirement` contact data. PII containment is a release
  blocker, not a hardening nice-to-have.
- **WS8-L7 — Reversibility.** Every production change step (deploy, migration,
  release) has a documented, tested rollback or an explicit written statement of why
  it is irreversible and how the risk is bounded.
- **WS8-L8 — Evidence Of Readiness.** Release readiness is *proven by executed
  gates*, never asserted in prose. Every claim in the release checklist maps to a
  runnable command or a CI job.

## 4. Dependency & sequencing

```
WS7 merged (#14 @ 7056031)
  -> post-WS7 governance slices merged (MEDIA-01, DATA-D1, AGENT-01; main @ 217460a)
  -> roadmap status corrected (WS7 COMPLETE / WS8 CURRENT)
  -> WS8 contract drafted (this document)
  -> WS8 contract RATIFIED by owner            <-- gate: not yet passed
  -> WS8 build slices execute, each PR-gated
  -> release checklist proven on exact head
  -> MVP v0.1 RELEASED
  -> (post-MVP) Commercial Architecture programme
  -> (later, separately ratified) AGENT-01.5 typed actions + MCP
```

## 5. Per-surface hardening depth (WS8-L3)

### 5.1 Public product — full quality bar

Surfaces: `/`, `/robots`, `/robots/[slug]`, `/compare`, `/manufacturers`,
`/manufacturers/[slug]`, `/use-cases`, `/use-cases/[slug]`, `/find-a-humanoid`,
`/matches/[id]`, 404.

Depth: end-to-end journeys (Product Contract §5.1 Journeys A/B/C) · responsive
behaviour · WCAG accessibility incl. keyboard navigation and screen-reader semantics ·
error / loading / empty states (Product Contract §5.2 rules, each state proven, not
assumed) · performance budget · SEO (per-page titles/descriptions/canonicals) ·
security headers · analytics/observability hooks.

### 5.2 MEDIA-01 verified imagery — provenance regression bar

Depth: image display-eligibility regression across the **full enum matrix** ·
missing-image behaviour (`IMAGE UNAVAILABLE`, never a placeholder fill, never a
fabricated image) · no restricted / unverified / unofficial leakage on any read path ·
attribution rendered wherever `ATTRIBUTION_REQUIRED` is the basis of display.

### 5.3 DATA-D1 discovery / admin — isolation & authorization bar

Depth: structural isolation (no canonical→discovery FK; no discovery import reachable
from a public read path) · admin authorization (the `/admin` surface is the single
biggest release blocker, §7) · promotion and audit invariants (human gate, gate
failures write nothing canonical, idempotency, audit durability, append-only audit) ·
candidate-never-public regression proven at the **response-body** level, not only by
route-path absence.

**No live crawling.** Fixture-only stays fixture-only. WS8 does not enable a network
adapter; each live source still requires its own DATA-D1.9 affirmative review.

### 5.4 AGENT-01 machine projections — parity & correctness bar

Depth: JSON-LD parity with the rendered page (no fact in JSON-LD that the page does
not assert, and none invented) · sitemap / robots.txt / llms.txt correctness ·
`is_published` filtering proven by **exclusion** (an unpublished entity must be absent
from every machine surface, not merely a published one present) · UNKNOWN and
provenance regression (no coercion; no fabricated provenance).

### 5.5 Commercial Lead — abuse & privacy bar

Depth: abuse resistance and rate limiting on the two public write paths · input
validation regression · idempotency / create-or-extend semantics under repeat and
concurrent submission · privacy (no PII in URLs, logs, or analytics payloads) ·
deterministic provider-routing regression (PENDING-only; never auto-contact).

### 5.6 Deployment — operational bar

Depth: production configuration (required, fail-closed) · migration application
strategy on a live database · post-deploy smoke tests · rollback procedure · release
checklist · runbook for the operator (including the network-gated internal surfaces).

## 6. Delivery slices (each a reviewable PR, in this order)

```
WS8.1  Release-blocking security & PII containment
WS8.2  Production configuration & fail-closed boot
WS8.3  Governance invariant regression (MEDIA-01 / DATA-D1 / AGENT-01)
WS8.4  Public product quality: a11y, keyboard, screen-reader, responsive
WS8.5  Error / loading / empty state proof + SEO metadata
WS8.6  Performance budget & observability/analytics
WS8.7  Deployment: container, migration strategy, smoke, rollback, runbook
WS8.8  Full-surface regression sweep on exact head
WS8.9  Release checklist execution -> MVP v0.1 RELEASED
```

Ordering rationale: security and configuration first (they are release blockers and
they change how everything else is tested), then invariant regression (protects the
frozen laws before broader refactoring pressure), then user-facing quality, then
operations, then the sweep and the release itself.

## 7. Current-state gap register (verified against `main @ 217460a`)

This register is **evidence, not opinion** — every line was confirmed by reading the
code at the cited location. It exists so WS8 scoping is not guesswork.

### 7.1 Release blockers

| # | Gap | Evidence |
|---|---|---|
| B1 | **`/admin` is completely unauthenticated** — SQLAdmin mounted with no `authentication_backend`, 21 model views with full CRUD, on the same ASGI app as the public API. Includes `CommercialLeadAdmin` exposing buyer `contact_email` / `organization`. | `apps/api/app/admin.py:214-218`, `:127-138`; `apps/api/app/main.py:46`. Only mitigation is the aspirational comment "network-gate in deployment" (`admin.py:5-6`, `main.py:45`) — undocumented and unimplemented. |
| B2 | **No CORS, no rate limiting, no auth, no throttle on the two public write paths.** No middleware of any kind is registered. | `apps/api/app/main.py` (no `add_middleware`); `POST /api/buyer-requirements` `buyer_requirements.py:70`; `POST /api/commercial-leads` `commercial_leads.py:27`; web proxies `apps/web/app/api/*/route.ts`. No rate-limit dependency in `apps/api/pyproject.toml`. |
| B3 | **`DATABASE_URL` silently defaults to dev credentials** — an API booted without it tries `humanoid:humanoid@localhost` instead of failing (violates WS8-L5). Contrast `db/bootstrap.py:127-128`, which does hard-error. | `apps/api/app/config.py:20-22` |
| B4 | **`NEXT_PUBLIC_SITE_URL` defaults to the production URL and is documented nowhere** — a staging/preview deploy emits production canonical URLs into JSON-LD, sitemap, robots.txt and llms.txt. | `apps/web/lib/site.ts:5`; absent from all three `.env.example` files |
| B5 | **`PromotionAudit` is declared append-only but admin exposes full CRUD** — nothing in the application enforces the declaration. | `apps/api/app/admin.py:194-200` vs `models/discovery.py:227`, `db/schema.sql:1187-1189` |

### 7.2 Deployment / operations gaps

| # | Gap | Evidence |
|---|---|---|
| D1 | No Dockerfile anywhere; no production container for API or web. Only artifact is a dev-only Postgres compose file. | `docker-compose.yml:1-3` ("Not for production") |
| D2 | No deploy target or platform config of any kind (no Procfile/vercel/fly/render/railway/terraform/k8s/nginx/systemd). | repo-wide search |
| D3 | No deploy job, `environment:`, or `secrets.*` reference in CI; six jobs, all validation. No release/tag/dispatch trigger. No smoke test against a deployed URL. | `.github/workflows/ci.yml:3-6` and all six jobs |
| D4 | No deployment, release, runbook, or rollback documentation exists. | repo-wide search; `DEVELOPMENT.md:72-76` states scope is local foundation only |
| D5 | Migrations are forward-only with **no rollback path**, and the recorded `sha256` is written but **never compared**, so an edited already-applied migration is silently skipped. | `db/bootstrap.py:77-79`, `:89-92`, `:99-106` |
| D6 | `README.md` teaches a **divergent bootstrap path** (`psql -f db/schema.sql`) that bypasses `db/bootstrap.py`, applying none of the three forward migrations and no tracking table. | `README.md:52-56` |
| D7 | `db/migrations/README.md` documents `0001` and `0002` only — `0003_add_discovery_layer.sql` is undocumented. | `db/migrations/README.md:37-44` |
| D8 | **`event_log` is dead** — the table and index exist and nothing writes to them; the only runtime touch is a read in a test. `02_ARCHITECTURE.md:21` specifies an ingestion endpoint for v0.1; none exists. | `models/event_log.py`; `tests/test_db.py:36-41`; no events router in `main.py:34-43` |
| D9 | No application logging, error tracking, metrics, or request-ID middleware anywhere. | repo-wide search (zero application matches) |
| D10 | No scheduled catalogue re-verification; verification runs only on PR/push, though `11_DATA_D1_CONTRACT.md:78,346` describes staleness triggers. | `.github/workflows/` (single `ci.yml`, no `schedule:`) |

Operational assets that **do** exist and should be preserved: `GET /health` +
`GET /ready` with a real DB check and 503 on failure (`routers/health.py:13-28`),
`pool_pre_ping` (`db/session.py:16-20`), idempotent tracked bootstrap + forward
migrations (`db/bootstrap.py`), two independent G2 gates
(`db/seed/seed.sql:406-426`, `db/validate_catalogue.py:29-45`), and a 6-job CI.

### 7.3 Quality / test-coverage gaps

| # | Gap | Evidence |
|---|---|---|
| Q1 | **No accessibility tooling at all** — no axe, pa11y, Lighthouse, budget file, or `web-vitals`. `e2e/agent-accessibility.spec.ts` is *machine* accessibility (SEO/LLM), not WCAG. | repo-wide search; `apps/web/e2e/agent-accessibility.spec.ts:8-54` |
| Q2 | Playwright runs a **single** `chromium` / Desktop Chrome project — no mobile, webkit, or firefox project, so "responsive testing" has no execution surface. | `apps/web/playwright.config.ts:27-29` |
| Q3 | **No `generateMetadata` anywhere** — every detail page inherits the root title/description verbatim; no per-page SEO, no OG/Twitter images. | `apps/web/app/layout.tsx:6`; repo-wide search |
| Q4 | No `lint` script and no ESLint config/dependency in `apps/web`; CI runs no lint step for web. | `apps/web/package.json:5-14`; `.github/workflows/ci.yml:104-124` |
| Q5 | MEDIA-01: no unit test on `is_display_eligible()` itself; the SQL twin `DISPLAY_ELIGIBLE_CLAUSE` is **dead and untested**; the matrix test covers 9 of 16 enum combinations. | `models/robot_image.py:84-96`, `:100-107`; `tests/test_robot_images.py:73-99` |
| Q6 | MEDIA-01 **bypass surface**: `hero_image_url` is serialized unfiltered on both read paths, never passing the eligibility gate (currently rendered by no component, so latent). | `services/reads.py:185`, `:341`; `models/robot_image.py:10-11` |
| Q7 | DATA-D1 `test_I_public_api_excludes_candidates` asserts **route-path substrings only** — it would not catch discovery data leaking through an existing canonical route response body. | `tests/test_discovery.py:278-283` |
| Q8 | `check_gates()` implements **P1, P2, P4, P6** + readiness; **P3, P5, P7 have no branch**, while three docstrings advertise "P1–P8". P8 is enforced separately as the `approved_by` requirement. Documentation overstates enforcement. | `services/discovery/promotion.py:43-70`, `:109-110`; docstrings `promotion.py:4`, `cli/promote_candidate.py:11`, `services/discovery/__init__.py:18` |
| Q9 | AGENT-01: **no test asserts an unpublished entity is ABSENT** from sitemap / llms.txt / JSON-LD; only presence of a published one is covered. | `apps/web/e2e/agent-accessibility.spec.ts:24-54`; `__tests__/jsonld.test.ts:36-79` |
| Q10 | AGENT-01 **scale gap**: both `sitemap.xml` and `llms.txt` hard-cap at `limit: 100` with no pagination loop (self-documented as a known gap). Untested truncation. | `apps/web/app/sitemap.ts:22-25`, `:47-48`; `apps/web/app/llms.txt/route.ts:14` |
| Q11 | AGENT-01 `lastMod()` NaN fallback is untested. | `apps/web/app/sitemap.ts:14-17` |
| Q12 | JSON-LD UNKNOWN guard is `!== null && !== undefined` only — a `0` or `""` would be emitted as a fact. Needs an explicit regression decision. | `apps/web/lib/jsonld.ts:50`, `:56` |
| Q13 | Commercial Lead has no abuse/rate-limit/throttle test because no such mechanism exists (see B2). | `tests/test_commercial_leads.py` (20 tests, none adversarial on volume) |
| Q14 | No `robot_image` CHECK constraint requiring `attribution` when `rights_status='ATTRIBUTION_REQUIRED'` — documented in a comment only. | `db/schema.sql:460` |

Current test baseline to protect (must not regress): **145** backend pytest ·
**74** web vitest · **53** Playwright specs (52 main + 1 isolated `@zeromatch`).

## 8. Explicitly OUT of scope (WS8-L1)

WS8 adds **no** product capability. Specifically out:

```
Rent / Buy / Lease / RaaS activation      Commercial Architecture programme
payments · checkout · escrow · custody    reservations · contracting
AGENT-01.5 typed actions · MCP            live DATA-D1 network adapters
new canonical DB model                    parallel agent API
new public routes                         new pages
CRM · supplier dashboard                  automated outreach / notification
public authentication / user accounts      lead scoring · AI qualification
LLM anywhere in a scoring or fact path    schema redesign
UI redesign (UI-D1 stays frozen)          new catalogue entities
```

Boundary note: hardening an **existing** surface is in scope even when it requires new
code (e.g. authenticating the existing `/admin`, rate-limiting an existing endpoint,
adding a Dockerfile for an existing app). Creating a **new** capability a user could
use is not. Where a line is genuinely ambiguous, §10 escalates it as an open decision
rather than assuming.

## 9. Acceptance gates (release-blocking; each must be a runnable command or CI job)

**Security & privacy**
- **R1** — `/admin` is unreachable without authorization in a production configuration;
  proven by an automated test, not by a deployment note.
- **R2** — No unauthenticated surface returns `commercial_lead` / `buyer_requirement`
  PII. Proven by response-body assertion.
- **R3** — Both public write paths enforce a documented abuse/rate limit; proven under
  repeat-submission load.
- **R4** — Security headers and CORS policy are explicit and asserted.
- **R5** — No PII in URLs, query strings, logs, or analytics payloads.

**Configuration & deployment**
- **R6** — Production boot fails loudly with an actionable error when `DATABASE_URL`
  or the site URL is absent (WS8-L5); dev defaults cannot reach production.
- **R7** — Canonical URL emission (JSON-LD / sitemap / robots.txt / llms.txt) is
  environment-correct; a non-production deploy never emits production canonicals.
- **R8** — A documented, executed migration strategy applies cleanly to a
  production-shaped database, with checksum-drift detection and a rollback procedure
  (WS8-L7).
- **R9** — One documented bootstrap path only; the divergent `README.md` path is
  reconciled or removed (D6), and all migrations are documented (D7).
- **R10** — Post-deploy smoke test proves liveness, readiness, one public read, and
  one governed write path against the deployed URL.
- **R11** — A release checklist and operator runbook exist, including rollback and the
  network-gating requirement for internal surfaces.

**Public product quality**
- **R12** — Journeys A, B, C pass end-to-end on the release candidate.
- **R13** — Accessibility gate: automated WCAG scan on every public route with zero
  criticals, plus keyboard-only traversal and screen-reader semantics for nav,
  catalogue, detail, wizard, matches, and the lead dialog.
- **R14** — Responsive gate executes on at least one mobile and one desktop viewport
  project (Q2 must be fixed for this gate to mean anything).
- **R15** — Every §5.2 empty/error state is individually proven: "No confirmed
  pricing" vs "Price on request" vs `ESTIMATED`/`FROM`/`RANGE`; "No confirmed
  commercial availability"; NULL spec → Unknown/em-dash; zero-match explanation; 404
  on unknown slug; `/compare` with <2 ids. Never `$0`, never blank, never
  "unavailable".
- **R16** — Per-page SEO metadata on every route; no page inherits a generic root
  title (Q3).
- **R17** — A stated performance budget is measured and met on the key routes.

**Governance invariants**
- **R18** — MEDIA-01: full 16-cell eligibility matrix regression; the SQL clause is
  either exercised or removed (Q5); `hero_image_url` cannot bypass the gate (Q6);
  missing-image renders `IMAGE UNAVAILABLE`; attribution present wherever required.
- **R19** — DATA-D1: candidate data absent from public **response bodies** (Q7);
  structural isolation holds; gate failure writes nothing canonical; promotion is
  human-gated and idempotent; audit is durable and enforced append-only (B5);
  promotion documentation matches implemented gates (Q8).
- **R20** — DATA-D1: no live crawling. Fixture-only proven; no network adapter enabled.
- **R21** — AGENT-01: an unpublished canonical entity is **absent** from JSON-LD,
  sitemap, and llms.txt (Q9); UNKNOWN is never coerced (incl. the `0`/`""` decision,
  Q12); no fabricated provenance; JSON-LD asserts nothing the page does not.
- **R22** — AGENT-01 scale behaviour beyond the 100-entity cap is either fixed or
  explicitly documented as a bounded, tested limitation (Q10, Q11).
- **R23** — Commercial Lead: validation, create-or-extend, concurrency, and
  PENDING-only routing regressions all pass; no auto-contact.

**Whole-surface**
- **R24** — Full baseline green on exact head with **no reduction** in coverage:
  ≥145 backend, ≥74 vitest, ≥53 Playwright, all six CI jobs, both G2 gates.
- **R25** — Every frozen law from WS0, MEDIA-01, DATA-D1 and AGENT-01 has at least one
  executing regression test; no law relies on prose alone (WS8-L8).
- **R26** — No new capability shipped (WS8-L1); the diff contains no new public route,
  no new canonical model, and no transactional action.

## 10. Open decisions for ratification (owner input required)

These change WS8's shape and are **not** for me to assume:

1. **Admin authorization mechanism.** Options: (a) app-level SQLAdmin auth backend
   with a credentialed operator login; (b) pure network gating (private network /
   VPN / IP allowlist) with `/admin` never bound publicly; (c) both, defence in depth.
   *Recommendation: (c) — B1 is severe and network gating alone is undocumented and
   unverifiable in CI.*
2. **Deploy target.** No platform is chosen anywhere in the repo. WS8.7 cannot be
   specified without it (container + platform config + secret management + how
   migrations run on deploy).
3. **Is `event_log` ingestion in scope?** `02_ARCHITECTURE.md:21` specifies it for
   v0.1 and WS8 lists "analytics", but the table is dead (D8) and adding an endpoint
   arguably brushes WS8-L1. *Recommendation: in scope, minimal, internal-only —
   analytics is an explicit WS8 line item and the model already exists; alternatively
   defer and mark the table explicitly dormant.*
4. **Sitemap/llms 100-entity cap** (Q10): fix pagination now, or document as a
   bounded limitation for v0.1? *Recommendation: document now, fix when the catalogue
   approaches the cap — the current catalogue is 7 robots, so this is not yet a real
   defect.*
5. **Performance budget numbers** — WS8 must measure against a stated budget; the
   thresholds are a product decision.
6. **Accessibility conformance target** — WCAG 2.1 AA assumed unless directed
   otherwise.
7. **Rate-limit policy** — thresholds and response behaviour for the two public write
   paths.

## 11. Exit criteria

WS8 exits, and MVP v0.1 is released, when:

1. Every gate R1–R26 has passed on the exact release head.
2. All six CI jobs are green on that same head.
3. The release checklist and runbook are merged and were actually executed.
4. A rollback procedure has been documented and rehearsed (WS8-L7).
5. The product owner explicitly approves the release.

Exit state recorded in `08_DEVELOPMENT_ROADMAP.md`:

```
HUMANOIDONLINE MVP v0.1 — READY FOR PRODUCTION
```

## 12. Ratification record

**STATUS: DRAFT — NOT RATIFIED.** No implementation is authorized. This section is
completed by the product owner at ratification, at which point the §3 laws become
FROZEN and the §10 open decisions are resolved into the contract.

```
Ratified by:      (pending)
Ratified on:      (pending)
Open decisions:   (pending — §10 items 1-7)
Build trigger:    `build WS8` (not yet issued)
```
