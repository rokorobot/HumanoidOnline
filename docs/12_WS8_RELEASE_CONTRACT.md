# WS8 — MVP Hardening / Release

> ## STATUS: DRAFT v0.2 — AWAITING REVIEW & RATIFICATION — NO IMPLEMENTATION
>
> Drafted 2026-07-26 against the complete deployable surface on `main`. v0.2 folds the
> product owner's seven ratification calls (§10), the B2 reframing (§7.1), and the
> ratified execution order (§6). Nothing here authorizes implementation: per the
> ratify-before-build discipline, WS8 begins only after this revised contract is
> reviewed and ratified and an explicit **`build WS8`** trigger is issued.
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

## 3. Frozen laws (become FROZEN on ratification)

- **WS8-L1 — No New Capability.** WS8 adds no product capability. It hardens,
  verifies, documents, configures, and instruments what exists. Any change a user
  could perceive as a new feature is out of scope by definition. Corollary: dead
  infrastructure is not activated merely because it exists (§10 D3).
- **WS8-L2 — Whole-Surface Release Candidate.** The release gate covers the entire
  deployable surface (§2). A surface that ships is a surface that must be hardened;
  nothing ships un-gated because it arrived outside the numbered sequence.
- **WS8-L3 — Differentiated Depth.** Hardening depth is per-surface and specified in
  §5, not uniform.
- **WS8-L4 — No Law Weakening To Pass A Gate.** If a hardening test fails, the
  product or the test is fixed — never the governed law, gate, or contract. A frozen
  semantic (UNKNOWN ≠ 0/false/unavailable; maturity ≠ obtainability ≠ evidence;
  QUOTE_ONLY ≠ UNKNOWN; candidate ≠ canonical; unpublished ≠ public; real robots show
  real verified images only; no commercial fact without evidence) may never be
  relaxed to make WS8 green.
- **WS8-L5 — Fail Closed In Production.** Production configuration must fail loudly
  when required inputs are absent. No production surface may silently fall back to a
  development default (credentials, hostnames, canonical URLs).
- **WS8-L6 — PII Containment.** No unauthenticated or public surface may expose
  `commercial_lead` / `buyer_requirement` contact data. PII containment is a release
  blocker, not a hardening nice-to-have.
- **WS8-L7 — Reversibility.** Every production change step (deploy, migration,
  release) has a documented, rehearsed rollback, or an explicit written statement of
  why it is irreversible and how that risk is bounded.
- **WS8-L8 — Evidence Of Readiness.** Release readiness is *proven by executed
  gates*, never asserted in prose. Every claim in the release checklist maps to a
  runnable command or a CI job.
- **WS8-L9 — Explicit Policy Over Implicit Default.** Where a security or
  cross-origin posture is currently implicit (e.g. relying on same-origin browser
  policy), WS8 makes the chosen policy **explicit, documented, and tested**. Absence
  of middleware is not itself a defect; an *unstated, untested* posture is.
- **WS8-L10 — Anonymity Preserved Under Abuse Control.** Abuse controls on anonymous
  buyer-intent paths must not introduce authentication or identity requirements.
  WS5's anonymity (contact identity begins only at WS7 lead capture) survives WS8.

## 4. Dependency & sequencing

```
WS7 merged (#14 @ 7056031)
  -> post-WS7 governance slices merged (MEDIA-01, DATA-D1, AGENT-01; main @ 217460a)
  -> roadmap status corrected: WS7 COMPLETE / WS8 CURRENT (#22 @ a9a9ce5)   [DONE]
  -> WS8 contract drafted v0.1, revised v0.2 with owner decisions (this document)
  -> WS8 contract REVIEWED + RATIFIED by owner          <-- gate: not yet passed
  -> WS8 build slices execute in the §6 order, each PR-gated
  -> hosting provider selected                          <-- prerequisite for WS8.7 only
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
behaviour · **WCAG 2.2 AA** accessibility (§10 D5) · error / loading / empty states
(Product Contract §5.2 rules, each state proven, not assumed) · Core Web Vitals
performance targets (§10 D6) · SEO (per-page titles/descriptions/canonicals) ·
explicit, tested security posture · observability appropriate to the deployed service.

### 5.2 MEDIA-01 verified imagery — provenance regression bar

Depth: image display-eligibility regression across the **full enum matrix** ·
missing-image behaviour (`IMAGE UNAVAILABLE`, never a placeholder fill, never a
fabricated image) · no restricted / unverified / unofficial leakage on any read path ·
attribution rendered wherever `ATTRIBUTION_REQUIRED` is the basis of display.

### 5.3 DATA-D1 discovery / admin — isolation & authorization bar

Depth: structural isolation (no canonical→discovery FK; no discovery import reachable
from a public read path) · **layered admin authorization** (§10 D1) · promotion and
audit invariants (human gate; gate failures write nothing canonical; idempotency;
audit durability; **append-only enforced in code, not merely documented**) ·
candidate-never-public regression proven at the **response-body** level, not only by
route-path absence.

**No live crawling.** Fixture-only stays fixture-only. WS8 does not enable a network
adapter; each live source still requires its own DATA-D1.9 affirmative review.

### 5.4 AGENT-01 machine projections — parity & correctness bar

Depth: JSON-LD parity with the rendered page (no fact in JSON-LD that the page does
not assert, and none invented) · sitemap / robots.txt / llms.txt correctness ·
**complete published canonical set, not a truncated first page** (§10 D4) ·
`is_published` filtering proven by **exclusion** (an unpublished entity must be absent
from every machine surface, not merely a published one present) · UNKNOWN and
provenance regression (no coercion; no fabricated provenance).

### 5.5 Commercial Lead — abuse & privacy bar

Depth: endpoint-aware abuse controls on the two public write paths (§10 D7) · input
validation regression · idempotency / create-or-extend semantics under repeat and
concurrent submission, **proven not to be misclassified as abuse** · privacy (no PII
in URLs, logs, or telemetry) · deterministic provider-routing regression (PENDING-only;
never auto-contact) · anonymity preserved (WS8-L10).

### 5.6 Deployment — operational bar

The **deployment shape is frozen here; the hosting provider is not** (§10 D2):

```
production domain
  -> reverse proxy / TLS
    -> Next.js web
    -> FastAPI API
      -> PostgreSQL
```

Required properties of that shape, provider-independent:

- explicit production secrets — **no credential defaults** (WS8-L5)
- immutable / reproducible build
- **migration-before-app-start gate** (app never serves against an unmigrated schema)
- health / readiness checks wired to the proxy
- backup + rollback procedure (WS8-L7)
- **admin not publicly routable** except through its protected path (§10 D1)

## 6. Delivery slices (ratified order — each a reviewable PR)

```
WS8.1  Security boundaries
       admin auth + network boundary · rate limiting
       append-only audit enforcement · fail-closed production config

WS8.2  Deployment/config correctness
       env contract · canonical origin · DB configuration · migration integrity

WS8.3  Data/truth regressions
       UNKNOWN / G2 / provenance · MEDIA-01 · DATA-D1 isolation · AGENT-01 parity

WS8.4  UX correctness
       loading/error/empty · responsive · keyboard · WCAG 2.2 AA

WS8.5  SEO / machine surface
       metadata · sitemap pagination · JSON-LD / robots / llms

WS8.6  Performance + observability

WS8.7  Production deployment
       concrete hosting provider MUST be selected before this slice begins

WS8.8  Production smoke + rollback drill

WS8.9  Release evidence / sign-off
       HUMANOIDONLINE MVP v0.1 — READY FOR PRODUCTION
```

Ordering rationale: security boundaries first (they are release blockers and they
change how everything else must be tested), then configuration correctness (every
later slice depends on a trustworthy environment contract), then the data/truth
regressions that protect the frozen laws before broader change pressure, then
user-facing correctness, machine surface, performance/observability, and only then
deployment, drill, and sign-off.

## 7. Current-state gap register (verified against the code)

This register is **evidence, not opinion** — every line was confirmed by reading the
code at the cited location. It exists so WS8 scoping is not guesswork.

### 7.1 Release blockers

| # | Gap | Evidence |
|---|---|---|
| B1 | **`/admin` is completely unauthenticated** — SQLAdmin mounted with no `authentication_backend`, 21 model views with full CRUD, on the same ASGI app as the public API. Includes `CommercialLeadAdmin` exposing buyer `contact_email` / `organization`. | `apps/api/app/admin.py:214-218`, `:127-138`; `apps/api/app/main.py:46`. Only mitigation is the aspirational comment "network-gate in deployment" (`admin.py:5-6`, `main.py:45`) — undocumented and unimplemented. |
| B2 | **No explicit abuse-control or security policy on public write paths.** The two anonymous mutation endpoints have no abuse protection of any kind, and the cross-origin posture is implicit rather than stated and tested. *Framing note: the absence of CORS middleware is **not** itself a vulnerability — same-origin browser policy may well be the intended architecture — and these endpoints are **intentionally** unauthenticated (WS5 anonymity). The defect is that the chosen cross-origin policy is unstated/untested (WS8-L9) and that anonymous mutation endpoints lack abuse controls.* | `apps/api/app/main.py` (no `add_middleware`); `POST /api/buyer-requirements` `buyer_requirements.py:70`; `POST /api/commercial-leads` `commercial_leads.py:27`; web proxies `apps/web/app/api/*/route.ts`; no rate-limit dependency in `apps/api/pyproject.toml` |
| B3 | **`DATABASE_URL` silently defaults to dev credentials** — an API booted without it tries `humanoid:humanoid@localhost` instead of failing (violates WS8-L5). Contrast `db/bootstrap.py:127-128`, which does hard-error. | `apps/api/app/config.py:20-22` |
| B4 | **`NEXT_PUBLIC_SITE_URL` defaults to the production URL and is documented nowhere** — a staging/preview deploy emits production canonical URLs into JSON-LD, sitemap, robots.txt and llms.txt. | `apps/web/lib/site.ts:5`; absent from all three `.env.example` files |
| B5 | **`PromotionAudit` is declared append-only but admin exposes full CRUD** — nothing in the application enforces the declaration. WS8 must enforce it in code. | `apps/api/app/admin.py:194-200` vs `models/discovery.py:227`, `db/schema.sql:1187-1189` |

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
| D8 | `event_log` is dead — table and index exist, nothing writes to them; the only runtime touch is a read in a test. **Ratified as dormant (§10 D3): WS8 does not activate it.** | `models/event_log.py`; `tests/test_db.py:36-41`; no events router in `main.py:34-43` |
| D9 | No application logging, error tracking, metrics, or request-ID middleware anywhere. | repo-wide search (zero application matches) |
| D10 | No scheduled catalogue re-verification; verification runs only on PR/push, though `11_DATA_D1_CONTRACT.md:78,346` describes staleness triggers. | `.github/workflows/` (single `ci.yml`, no `schedule:`) |

Operational assets that **do** exist and must be preserved: `GET /health` +
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
| Q10 | AGENT-01 **correctness ceiling**: both `sitemap.xml` and `llms.txt` hard-cap at `limit: 100` with no pagination loop. **Ratified as a WS8 fix (§10 D4)**, not a documented limitation. | `apps/web/app/sitemap.ts:22-25`, `:47-48`; `apps/web/app/llms.txt/route.ts:14` |
| Q11 | AGENT-01 `lastMod()` NaN fallback is untested. | `apps/web/app/sitemap.ts:14-17` |
| Q12 | JSON-LD UNKNOWN guard is `!== null && !== undefined` only — a `0` or `""` would be emitted as a fact. | `apps/web/lib/jsonld.ts:50`, `:56` |
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
event_log activation / analytics system   new canonical DB model
parallel agent API                        new public routes · new pages
CRM · supplier dashboard                  automated outreach / notification
public authentication / user accounts     lead scoring · AI qualification
LLM anywhere in a scoring or fact path    schema redesign
UI redesign (UI-D1 stays frozen)          new catalogue entities
```

Boundary note: hardening an **existing** surface is in scope even when it requires new
code (authenticating the existing `/admin`, rate-limiting an existing endpoint, adding
a Dockerfile for an existing app, paginating an existing sitemap). Creating a **new**
capability a user could use is not. Dead infrastructure is not revived to justify a
line item (§10 D3).

## 9. Acceptance gates (release-blocking; each a runnable command or CI job)

**Security & privacy** *(WS8.1)*
- **R1** — `/admin` is unreachable without **both** the network boundary and
  application-level authorization; proven by an automated test, not a deployment note.
- **R2** — No unauthenticated surface returns `commercial_lead` / `buyer_requirement`
  PII. Proven by response-body assertion.
- **R3** — Endpoint-aware abuse controls on both public write paths: IP-based
  throttling, stricter repeated-submission control, `429` + `Retry-After`,
  proxy-aware client-IP resolution, environment-configurable limits. Proven under
  repeat-submission load **and** proven not to misclassify legitimate retries or the
  existing create-or-extend idempotency as abuse (WS8-L10 — no authentication added).
- **R4** — The cross-origin / security-header posture is **explicit, documented, and
  asserted** (WS8-L9), whether that posture is strict same-origin or an allowlist.
- **R5** — No PII in URLs, query strings, logs, or telemetry.
- **R6** — `PromotionAudit` append-only is **enforced by the application** (admin
  cannot edit or delete audit rows), proven by test (B5).

**Configuration & deployment** *(WS8.2, WS8.7, WS8.8)*
- **R7** — Production boot fails loudly with an actionable error when `DATABASE_URL`
  or the canonical site origin is absent (WS8-L5); dev defaults cannot reach
  production.
- **R8** — Canonical origin emission (JSON-LD / sitemap / robots.txt / llms.txt) is
  environment-correct; a non-production deploy never emits production canonicals.
- **R9** — Migration integrity: checksum-drift detection (the recorded `sha256` is
  actually compared), a **migration-before-app-start gate**, and a documented
  rollback procedure (WS8-L7).
- **R10** — One documented bootstrap path only; the divergent `README.md` path is
  reconciled or removed (D6), and all migrations are documented (D7).
- **R11** — The frozen deployment shape (§5.6) is realized with explicit secrets, a
  reproducible build, proxy-wired health/readiness, and admin not publicly routable.
- **R12** — Post-deploy smoke test proves liveness, readiness, one public read, and
  one governed write path against the deployed URL.
- **R13** — A release checklist and operator runbook exist, were executed, and a
  **rollback drill was rehearsed** (WS8-L7), including backup restore.

**Data / truth regressions** *(WS8.3)*
- **R14** — MEDIA-01: full 16-cell eligibility matrix regression; the SQL clause is
  either exercised or removed (Q5); `hero_image_url` cannot bypass the gate (Q6);
  missing-image renders `IMAGE UNAVAILABLE`; attribution present wherever required.
- **R15** — DATA-D1: candidate data absent from public **response bodies** (Q7);
  structural isolation holds; gate failure writes nothing canonical; promotion is
  human-gated and idempotent; audit durable; promotion documentation matches
  implemented gates (Q8).
- **R16** — DATA-D1: no live crawling. Fixture-only proven; no network adapter enabled.
- **R17** — AGENT-01: an unpublished canonical entity is **absent** from JSON-LD,
  sitemap, and llms.txt (Q9); UNKNOWN never coerced, including the `0`/`""` case
  (Q12); no fabricated provenance; JSON-LD asserts nothing the page does not.
- **R18** — UNKNOWN / G2 / provenance regression green across the whole surface; both
  G2 gates pass.

**UX correctness** *(WS8.4)*
- **R19** — Journeys A, B, C pass end-to-end on the release candidate.
- **R20** — **WCAG 2.2 AA** gate, and not merely "axe reports zero violations": it
  must comprise automated checks on every public route **plus** keyboard-only
  journeys, focus behaviour, semantic headings/forms/dialogs, screen-reader spot
  checks, and mobile target-size checks (§10 D5).
- **R21** — Responsive gate executes on at least one mobile and one desktop viewport
  project (Q2 must be fixed for this gate to mean anything).
- **R22** — Every §5.2 empty/error state individually proven: "No confirmed pricing"
  vs "Price on request" vs `ESTIMATED`/`FROM`/`RANGE`; "No confirmed commercial
  availability"; NULL spec → Unknown/em-dash; zero-match explanation; 404 on unknown
  slug; `/compare` with <2 ids. Never `$0`, never blank, never "unavailable".

**SEO / machine surface** *(WS8.5)*
- **R23** — Per-page SEO metadata on every route; no page inherits a generic root
  title (Q3).
- **R24** — Sitemap and llms.txt enumerate the **entire** published canonical set via
  pagination / chunked retrieval — the 100-entity ceiling is removed, not documented
  (§10 D4, Q10) — and `lastMod()` fallback behaviour is tested (Q11).

**Performance & observability** *(WS8.6)*
- **R25** — Core Web Vitals targets adopted as the user-facing release goals:
  **LCP ≤ 2.5 s · INP ≤ 200 ms · CLS ≤ 0.1**, at the 75th percentile for mobile and
  desktop *once field data exists*. Pre-release CI uses **deterministic lab budgets as
  regression guards only** — the contract explicitly does not claim lab Lighthouse
  proves field INP (§10 D6).
- **R26** — Production logging / error tracking / health observability appropriate to
  the deployed services, with request correlation and no PII in log output.
  `event_log` remains dormant and is documented as such (§10 D3).

**Whole-surface** *(WS8.9)*
- **R27** — Full baseline green on exact head with **no reduction** in coverage:
  ≥145 backend, ≥74 vitest, ≥53 Playwright, all six CI jobs, both G2 gates.
- **R28** — Every frozen law from WS0, MEDIA-01, DATA-D1 and AGENT-01 has at least one
  executing regression test; no law relies on prose alone (WS8-L8).
- **R29** — No new capability shipped (WS8-L1); the diff contains no new public route,
  no new canonical model, and no transactional action.

## 10. Ratification decisions (owner calls folded into this contract)

| # | Decision | Ratified call |
|---|---|---|
| **D1** | Admin authorization | **Both** app-level authentication/authorization **and** a network boundary — network gating alone is **not** accepted. Layering: `internet → network restriction → admin authentication/authorization → SQLAdmin`. The admin surface holds PII **and** mutation capability, so defence in depth is warranted. Additionally, `PromotionAudit`'s append-only promise must be **enforced**, not merely documented (B5 → R6). |
| **D2** | Deployment target | **Do not invent a provider in the contract.** Freeze the deployment *shape* (§5.6) — production domain → reverse proxy/TLS → Next.js web → FastAPI API → PostgreSQL — with explicit production secrets, no credential defaults, immutable/reproducible build, migration-before-app-start gate, health/readiness checks, backup + rollback, and admin not publicly routable except via its protected path. **Provider selection is a prerequisite for WS8.7 implementation only — not a reason to block ratifying the rest of WS8.** No prior HumanoidOnline hosting decision exists that could be treated as frozen. |
| **D3** | `event_log` | **Keep dormant / out of scope.** WS8 does not turn dead infrastructure into a new feature merely because it exists. Use production logging/observability appropriate to the deployed services instead. A canonical application event system is not activated absent a contractual requirement for it. |
| **D4** | Sitemap / llms 100-item cap | **Fix in WS8.** A release-hardening workstream removes this latent correctness ceiling. Pagination / chunked retrieval must generate the entire published canonical set rather than assuming the catalogue stays under 100 entities. This is hardening, not scope expansion. |
| **D5** | Accessibility target | **WCAG 2.2 AA** — the current W3C recommendation, also ISO/IEC 40500:2025. Must comprise automated a11y checks **+** keyboard-only journeys **+** focus behaviour **+** semantic headings/forms/dialogs **+** screen-reader spot checks **+** mobile target-size checks. Not merely an axe run reporting zero violations. |
| **D6** | Performance budgets | Core Web Vitals "good" thresholds as user-facing release targets: **LCP ≤ 2.5 s**, **INP ≤ 200 ms**, **CLS ≤ 0.1**, at p75 for mobile and desktop once field data exists. For pre-release CI, use **deterministic lab budgets as regression guards** — do not pretend lab Lighthouse proves field INP. |
| **D7** | Rate-limit policy | Explicit abuse controls on public writes, **endpoint-aware rather than one arbitrary global number**. For `POST /api/buyer-requirements` and `POST /api/commercial-leads` at minimum: IP-based throttling; stricter repeated-submission controls; existing idempotency preserved; `429` + `Retry-After`; proxy-aware client-IP handling; limits configurable per environment; tests proving valid retries are **not** treated as duplicates or abuse. **Do not** add broad authentication to anonymous buyer-intent flows just to solve abuse (WS8-L10). |

## 11. Exit criteria

WS8 exits, and MVP v0.1 is released, when:

1. Every gate R1–R29 has passed on the exact release head.
2. All six CI jobs are green on that same head.
3. The release checklist and runbook are merged and were actually executed.
4. A rollback procedure has been documented **and rehearsed** (WS8-L7, R13).
5. The product owner explicitly approves the release.

Exit state recorded in `08_DEVELOPMENT_ROADMAP.md`:

```
HUMANOIDONLINE MVP v0.1 — READY FOR PRODUCTION
```

## 12. Ratification record

**STATUS: DRAFT v0.2 — NOT RATIFIED.** No implementation is authorized. The §10
decisions are the owner's ratification calls and are folded in above; this section is
completed when the owner reviews the revised contract and ratifies it, at which point
the §3 laws become FROZEN.

```
Decisions folded:  §10 D1-D7 (owner, 2026-07-26)
Ratified by:       (pending review of v0.2)
Ratified on:       (pending)
Build trigger:     `build WS8` (not yet issued)
Open prerequisite: hosting provider selection — blocks WS8.7 only
```
