# WS8 — MVP Hardening / Release

> ## STATUS: DRAFT v0.4 — RATIFICATION CANDIDATE — NO IMPLEMENTATION
>
> v0.4 folds the owner's **v0.3 verdict (REQUEST MINOR REVISION)** — four corrections,
> two blocking. It is a **narrow** revision: the Deployment Execution Profile is now
> actually frozen to values, the two mixed-evidence gates are split, the Q14/L7
> database-enforcement language is tightened, and gates are renumbered accordingly.
> No architectural change; C3–C8 are not reopened.
>
> Nothing here authorizes implementation. **`build WS8` remains CLOSED.**
>
> Revision history: v0.1 initial draft · v0.2 owner decisions D1–D7 + B2 reframing ·
> v0.3 owner corrections C1–C8 + sequencing · **v0.4 owner corrections E1–E4** (§14).
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

- **WS8-L1 — No New Product/Commercial Capability.** WS8 adds no product or
  commercial capability. **Security, operator, deployment, observability and
  correctness controls necessary to harden an already-authorized surface are not
  product capability** — authenticating the existing `/admin`, rate-limiting an
  existing endpoint, containerizing an existing app, or paginating an existing
  sitemap are hardening, not features. What is prohibited is new capability *for the
  product's users or counterparties*: new transactional actions, new commercial
  surfaces, new public routes, new canonical entities. Corollary: dead infrastructure
  is not activated merely because it exists (§11 D3). R34 uses this exact vocabulary.
- **WS8-L2 — Whole-Surface Release Candidate.** The release gate covers the entire
  deployable surface (§2). Nothing ships un-gated because it arrived outside the
  numbered sequence.
- **WS8-L3 — Differentiated Depth.** Hardening depth is per-surface (§5), not uniform.
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
  `commercial_lead` / `buyer_requirement` contact data.
- **WS8-L7 — Reversibility, With A Schema Rollback Doctrine.** Every production
  change step has a documented, rehearsed rollback. For schema specifically:
  > WS8 migrations must be **additive / backward-compatible** wherever practical.
  > **Application rollback must remain possible against the migrated schema.**
  > **Destructive schema changes are prohibited in WS8** unless separately ratified.
  > Schema rollback may use **restore or forward-fix** rather than synthetic
  > down-migrations.

  Synthetic down-migrations are **not** required, and must not be written merely to
  satisfy prose.

  **Database enforcement clause (E4).** Adding enforcement (a `CHECK`, `NOT NULL`, a
  unique index) is **not** automatically safe merely because the DDL is additive: it
  can still be behaviourally backward-incompatible with existing rows or with an
  older application binary. Therefore **any database enforcement introduced by WS8
  must satisfy L7: existing rows preflight clean or are safely remediated before
  enforcement is applied, and application rollback remains compatible with the
  migrated schema.** "ADD CONSTRAINT" never by itself equals "safe".
- **WS8-L8 — Evidence Of Readiness, By Declared Evidence Class.** Release readiness is
  *proven*, never asserted. **Every gate declares exactly one evidence class** and
  names its evidence artifact:
  - **Automated** — command or CI output
  - **Attested** — named human/operator + dated evidence artifact
  - **Observed** — measurement captured from the deployed production system

  A gate needing two kinds of proof is **split into two gates** (E2, E3). Hybrid
  classes are not permitted, and L8 is not weakened to accommodate them.
- **WS8-L9 — Explicit Policy Over Implicit Default.** Where a security or
  cross-origin posture is currently implicit (e.g. relying on same-origin browser
  policy), WS8 makes the chosen policy **explicit, documented, and tested**. Absence
  of middleware is not itself a defect; an *unstated, untested* posture is.
- **WS8-L10 — Anonymity Preserved Under Abuse Control.** Abuse controls on anonymous
  buyer-intent paths must not introduce authentication or identity requirements.
  WS5's anonymity survives WS8.
- **WS8-L11 — Prove What The Slice Can Actually Prove.** A gate may not require
  evidence that its slice is structurally incapable of producing. Where an invariant
  needs both pre-deployment and deployed proof, it is split into staged gates
  (§9.0.1). No slice claims a boundary it has not yet built.

## 4. Dependency & sequencing

```
WS7 merged (#14 @ 7056031)
  -> governance slices merged (MEDIA-01, DATA-D1, AGENT-01; main @ 217460a)
  -> roadmap corrected: WS7 COMPLETE / WS8 CURRENT (#22 @ a9a9ce5)        [DONE]
  -> WS8 contract v0.1 -> v0.2 -> v0.3 -> v0.4 (ratification candidate)
  -> WS8 contract RATIFIED, freezing DEP P1-P5 (§6)    <-- gate: not yet passed
  -> WS8.1 .. WS8.6 execute provider-agnostically against the frozen DEP
  -> provider selection (WS8.7 prerequisite — confirmed deferred, §11 D2)
  -> WS8.7 .. WS8.9
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
behaviour · **WCAG 2.2 AA** (§11 D5) · error / loading / empty states (Product
Contract §5.2, each proven) · pre-production performance budgets (§11 D6) · SEO ·
explicit tested security posture · observability appropriate to the deployed service.

### 5.2 MEDIA-01 verified imagery — provenance regression bar

Full enum-matrix eligibility regression · missing-image behaviour (`IMAGE
UNAVAILABLE`, never a placeholder fill, never a fabricated image) · no restricted /
unverified / unofficial leakage on any read path, **including the `hero_image_url`
bypass** · attribution present wherever `ATTRIBUTION_REQUIRED` is the display basis.

### 5.3 DATA-D1 discovery / admin — isolation & authorization bar

Structural isolation · **layered admin authorization** (§11 D1, staged per §9.0.1) ·
promotion and audit invariants (human gate; gate failure writes nothing canonical;
idempotency; audit durability; **append-only enforced in code**) ·
candidate-never-public proven at the **response-body** level · **promotion
documentation truthful to implemented gates**.

**No live crawling.** Fixture-only stays fixture-only.

### 5.4 AGENT-01 machine projections — parity & correctness bar

JSON-LD parity with the rendered page · sitemap / robots.txt / llms.txt correctness ·
**complete published canonical set, not a truncated first page** (§11 D4) ·
`is_published` proven by **exclusion** · UNKNOWN and provenance regression.

### 5.5 Commercial Lead — abuse & privacy bar

Endpoint-aware abuse controls (§11 D7, staged per §9.0.1) · validation regression ·
idempotency / create-or-extend under repeat and concurrent submission, **proven not
misclassified as abuse** · privacy · PENDING-only routing · anonymity (WS8-L10).

### 5.6 Deployment — operational bar

Deployment **shape** (provider-independent):

```
production domain
  -> reverse proxy / TLS
    -> Next.js web
    -> FastAPI API
      -> PostgreSQL
```

Required properties: explicit production secrets, **no credential defaults** ·
immutable / reproducible build · **migration-before-app-start gate** ·
health/readiness wired to the proxy · backup + rollback · **admin not publicly
routable** except through its protected path.

The shape alone is **insufficient** to build WS8.1 — see §6.

## 6. Deployment Execution Profile (DEP) — FROZEN VALUES

**Correction E1.** v0.3 defined a DEP *template* whose P2/P4/P5 still offered choices.
A profile containing choices cannot be frozen, and WS8.1 cannot build against it.
The MVP v0.1 profile below is **frozen to values at ratification**, without naming a
vendor. WS8.7 **binds** these to the selected infrastructure.

| # | Invariant | **Frozen value for MVP v0.1** |
|---|---|---|
| **P1** | **Trusted ingress** | Forwarding headers are trusted **only** when they arrive from an **explicitly configured trusted ingress**. Forwarding headers supplied directly by a client are **ignored — never parsed as truth**. Frozen as trusted-source / proxy-chain **semantics**, deliberately not a numeric hop count (a hop count is spoofable precisely when the trust boundary is unstated). |
| **P2** | **API cardinality** | **Singleton FastAPI application instance for MVP v0.1.** Horizontal replication requires a later operational change and **automatically invalidates process-local abuse-control state** (see P3). |
| **P3** | **Abuse-control state** | **Process-local state is permitted for the frozen singleton MVP topology (P2)**, but **only behind a storage abstraction** so shared/durable state can replace it **before any horizontal scaling**. Scaling without that replacement is a defect, not a deployment choice. |
| **P4** | **Admin exposure** | **A separate protected host/listener — not merely `/admin` on the unrestricted public ingress.** Network restriction **and** application authentication both remain mandatory (§11 D1); neither substitutes for the other. |
| **P5** | **Proxy capability** | Require an ingress whose **trust semantics and admin-boundary semantics are explicitly operator-configurable and testable**. This freezes the **capability required of the ingress**, not the implementation technology — "provider-managed" vs "operator-owned" is deliberately **not** frozen, which removes the circular dependency on selecting a provider. |

**Consequence.** WS8.1–WS8.6 now have sufficient topology semantics to be built
correctly, so **provider selection genuinely remains deferred to WS8.7** (§11 D2).
P1–P5 additionally act as an **acceptance filter** on any candidate provider: a
platform that cannot satisfy P5 is not viable regardless of other merits.

## 7. Delivery slices (ratified order)

```
WS8.1  Security boundaries
       admin application authorization · abuse controls (adversarial proof)
       append-only audit enforcement
WS8.2  Deployment/config correctness
       env contract · fail-closed boot (B3, B4) · canonical origin
       DB configuration · migration integrity
WS8.3  Data/truth regressions
       UNKNOWN / G2 / provenance · MEDIA-01 · DATA-D1 isolation · AGENT-01 parity
WS8.4  UX correctness
       loading/error/empty · responsive · keyboard · WCAG 2.2 AA · lint
WS8.5  SEO / machine surface
       metadata · sitemap pagination · JSON-LD / robots / llms
WS8.6  Performance + observability
WS8.7  Production deployment
       provider selected · DEP P1-P5 bound to infrastructure
       network boundary physically realized
WS8.8  Production smoke + external negative probe + rollback drill
WS8.9  Release evidence / sign-off
       HUMANOIDONLINE MVP v0.1 — READY FOR PRODUCTION
```

## 8. Current-state gap register — every gap carries a disposition

**Correction C6.** No registered gap may disappear between the register and the gate
list. Dispositions: **CLOSE** (fixed in WS8), **ACCEPT-DEFER** (real, not fixed now,
recorded in the runbook), **NOT A RELEASE DEFECT** (ratified correct-as-is). Owner is
the product owner for every ACCEPT-DEFER; slice-implementer for every CLOSE.

### 8.1 Release blockers

| # | Gap + evidence | Disposition | Gate |
|---|---|---|---|
| B1 | **`/admin` completely unauthenticated** — SQLAdmin, no `authentication_backend`, 21 model views, full CRUD, same ASGI app as the public API, exposing buyer `contact_email`/`organization`. `admin.py:214-218`, `:127-138`, `main.py:46`; sole mitigation is an aspirational comment (`admin.py:5-6`, `main.py:45`). | CLOSE | **R1** (app authz) → **R27** (boundary realized) → **R29** (external probe) |
| B2 | **No explicit abuse-control or security policy on public write paths.** *Framing: absent CORS middleware is **not** inherently a vulnerability — strict same-origin may be the intended architecture — and these endpoints are **intentionally** unauthenticated (WS5). The defect is an unstated/untested cross-origin policy (L9) plus missing abuse controls on anonymous mutation endpoints.* `main.py` (no `add_middleware`); `buyer_requirements.py:70`; `commercial_leads.py:27`. | CLOSE | **R3**, **R4** → **R29** (deployed ingress) |
| B3 | **`DATABASE_URL` silently defaults to dev credentials** (`config.py:20-22`) — production boots wrong instead of failing. Contrast `db/bootstrap.py:127-128`. | CLOSE | **R7** *(WS8.2)* |
| B4 | **`NEXT_PUBLIC_SITE_URL` defaults to the production URL, documented nowhere** (`lib/site.ts:5`) — staging emits production canonicals. | CLOSE | **R7**, **R8** *(WS8.2)* |
| B5 | **`PromotionAudit` declared append-only, admin exposes full CRUD** (`admin.py:194-200` vs `discovery.py:227`, `schema.sql:1187-1189`). | CLOSE | **R6** |

### 8.2 Deployment / operations gaps

| # | Gap + evidence | Disposition | Gate |
|---|---|---|---|
| D1 | No Dockerfile / production container anywhere; only a dev-only Postgres compose (`docker-compose.yml:1-3`). | CLOSE | R26 |
| D2 | No deploy target or platform config of any kind. | CLOSE | R26 |
| D3 | No deploy job, `environment:`, or `secrets.*` in CI; no release/tag/dispatch trigger; no deployed smoke test. | CLOSE | R26, R28 |
| D4 | No deployment, release, runbook, or rollback documentation exists. | CLOSE | R30 |
| D5a | Migration `sha256` recorded but **never compared** — an edited applied migration is silently skipped (`bootstrap.py:89-92`, `:99-106`). | CLOSE | R9 |
| D5b | Migrations forward-only, **no down-scripts**. | **NOT A RELEASE DEFECT** — ratified doctrine (L7): additive/backward-compatible migrations, rollback by restore or forward-fix. Synthetic down-migrations are not written to satisfy prose. | R9 (doctrine conformance) |
| D6 | `README.md:52-56` teaches a **divergent bootstrap** bypassing `bootstrap.py`, applying no migrations and no tracking table. | CLOSE | R10 |
| D7 | `db/migrations/README.md:37-44` omits `0003_add_discovery_layer.sql`. | CLOSE | R10 |
| D8 | `event_log` dead — table + index exist, nothing writes; only runtime touch is a test read. | **NOT A RELEASE DEFECT** — ratified dormant (§11 D3). Must be **documented as dormant**. | R25 |
| D9 | No application logging, error tracking, metrics, or request correlation anywhere. | CLOSE | R25 |
| D10 | No scheduled catalogue re-verification, though `11_DATA_D1_CONTRACT.md:78,346` describes staleness triggers. | **ACCEPT-DEFER** — a DATA-D1 *operational* concern, not MVP release eligibility: the catalogue is 7 robots, both G2 gates run on every PR/push, and a scheduled re-verify job trends toward DATA-D1's separately-gated live-network territory. **Owner:** product owner. Recorded in the runbook. | *(none — R30 runbook entry)* |

Preserved assets: `GET /health` + `GET /ready` with real DB check and 503
(`health.py:13-28`) · `pool_pre_ping` (`session.py:16-20`) · idempotent tracked
bootstrap (`bootstrap.py`) · two independent G2 gates (`seed.sql:406-426`,
`validate_catalogue.py:29-45`) · 6-job CI.

### 8.3 Quality / test-coverage gaps

| # | Gap + evidence | Disposition | Gate |
|---|---|---|---|
| Q1 | **No accessibility tooling at all** — no axe/pa11y/Lighthouse/`web-vitals`. `e2e/agent-accessibility.spec.ts` is *machine* accessibility, not WCAG. | CLOSE | R17, R18 |
| Q2 | Playwright runs a **single** chromium project (`playwright.config.ts:27-29`) — "responsive testing" has no execution surface. | CLOSE | R19 |
| Q3a | **No `generateMetadata` anywhere** — every detail page inherits the root title/description (`layout.tsx:6`). | CLOSE | R22 |
| Q3b | No OG/Twitter images. | **ACCEPT-DEFER** — social-preview imagery is presentation/marketing, not a release defect, **and it collides with MEDIA-01**: a per-robot OG card would need a verified image, and a generic brand card is an unmade design decision. **Owner:** product owner. | *(none — runbook entry)* |
| Q4 | No `lint` script, no ESLint config/dependency; CI runs no web lint (`package.json:5-14`). | CLOSE — cheap, and `eslint-plugin-jsx-a11y` supports (but does not by itself prove) the WCAG gate. | R21 |
| Q5 | MEDIA-01: no unit test on `is_display_eligible()`; SQL twin `DISPLAY_ELIGIBLE_CLAUSE` **dead and untested**; matrix covers 9 of 16 combinations. | CLOSE | R11 |
| Q6 | **`hero_image_url` bypasses the eligibility gate** on both read paths (`reads.py:185`, `:341`) — latent, rendered by no component today. | CLOSE | R11 |
| Q7 | DATA-D1 `test_I` asserts **route-path substrings only** (`test_discovery.py:278-283`) — would not catch leakage through a canonical route body. | CLOSE | R12 |
| Q8a | Promotion **documentation overstates enforcement**: three docstrings advertise "P1–P8"; `check_gates()` implements P1/P2/P4/P6 + readiness. | CLOSE — align documentation to implemented reality. | R12 |
| Q8b | P3/P5/P7 have no branch. | **ACCEPT-DEFER** — implementing absent promotion gates is **DATA-D1 scope**, not WS8 hardening (L1). **Owner:** product owner. | *(none — runbook entry)* |
| Q9 | **No test asserts an unpublished entity is ABSENT** from sitemap/llms/JSON-LD. | CLOSE | R14 |
| Q10 | sitemap + llms hard-cap at `limit: 100`, no pagination. | CLOSE (§11 D4) | R23 |
| Q11 | `lastMod()` NaN fallback untested (`sitemap.ts:14-17`). | CLOSE | R23 |
| Q12 | JSON-LD UNKNOWN guard is `!== null && !== undefined` only — `0` or `""` would be emitted as fact (`jsonld.ts:50`, `:56`). | CLOSE | R14 |
| Q13 | No abuse/rate-limit test, because no mechanism exists (see B2). | CLOSE | R3 |
| Q14 | No CHECK requiring `attribution` when `rights_status='ATTRIBUTION_REQUIRED'` (`schema.sql:460`, comment only) — such an image is display-eligible today, so it could render **without** its required attribution: a live rights exposure. | CLOSE — enforced and regression-tested. **Any database enforcement must satisfy L7's database-enforcement clause** (preflight-clean or safely remediated rows; application rollback stays compatible) — additive DDL is not by itself sufficient. | R11 |

Baseline test inventory: **145** backend pytest · **74** web vitest · **53**
Playwright (52 main + 1 isolated `@zeromatch`) — floor defined by R31.

## 9. Acceptance gates

### 9.0 Evidence classes (WS8-L8)

Every gate declares **exactly one** class and names its artifact:

- **[Automated]** — a command or CI job; artifact = job/run output
- **[Attested]** — a named operator + dated evidence artifact (log, capture, report)
- **[Observed]** — measurement from the deployed production system

Gates needing two kinds of proof are **split**, never hybridised (E2, E3).

### 9.0.1 Staged gates (WS8-L11)

| Invariant | Pre-deployment proof | Deployed proof |
|---|---|---|
| Admin unreachable without authorization | **R1** (WS8.1) application authorization + configuration contract + automated negative tests | **R27** (WS8.7) boundary realized → **R29** (WS8.8) external negative probe |
| Trusted-ingress / client-IP correctness | **R3** (WS8.1) adversarial unit/integration proof incl. spoofed forwarding headers | **R29** (WS8.8) deployed ingress probe |

### 9.1 WS8.1 — Security boundaries

- **R1 [Automated]** — Admin **application-level** authorization: `/admin` refuses
  unauthenticated, wrong-credential and absent-session access; the network-boundary
  **configuration contract** is defined here per DEP P4/P5. Physical realization is
  R27; external proof is R29.
- **R2 [Automated]** — No unauthenticated surface returns `commercial_lead` /
  `buyer_requirement` PII; proven by response-body assertion.
- **R3 [Automated]** — Endpoint-aware abuse controls on both public write paths: IP
  throttling, stricter repeated-submission control, `429` + `Retry-After`,
  per-environment limits; client-IP resolution honours **DEP P1** and **ignores
  forwarding headers from untrusted sources** (adversarial spoofing test required);
  limiter state is process-local **behind a storage abstraction** per **DEP P2/P3**.
  Must prove legitimate retries and the existing create-or-extend idempotency are
  **not** misclassified as abuse, and that **no authentication was added** (L10).
- **R4 [Automated]** — Cross-origin / security-header posture **explicit, documented,
  asserted** (L9), whether strict same-origin or an allowlist.
- **R5 [Automated]** — No PII in URLs, query strings, logs, or telemetry.
- **R6 [Automated]** — `PromotionAudit` append-only **enforced by the application**;
  admin cannot edit or delete audit rows.

### 9.2 WS8.2 — Deployment/config correctness

- **R7 [Automated]** — Fail-closed boot (L5): the API refuses to start without
  `DATABASE_URL` (**B3**) and the web tier without a canonical site origin (**B4**),
  with actionable errors; dev defaults cannot reach production.
- **R8 [Automated]** — Canonical origin emission (JSON-LD / sitemap / robots.txt /
  llms.txt) is environment-correct; a non-production deploy never emits production
  canonicals.
- **R9 [Automated]** — Migration integrity: recorded `sha256` is **actually
  compared** (drift detected and refused); the **migration-before-app-start** gate is
  specified and enforced (mechanism bound in WS8.7); migrations conform to the **L7
  doctrine and its database-enforcement clause** — additive/backward-compatible, no
  destructive change, preflight-clean or remediated rows before any new enforcement.
- **R10 [Automated]** — **One** documented bootstrap path (D6 reconciled/removed);
  every migration documented (D7).

### 9.3 WS8.3 — Data/truth regressions

- **R11 [Automated]** — MEDIA-01: full **16-cell** eligibility matrix; the SQL twin
  is exercised or removed (Q5); **`hero_image_url` cannot bypass the gate** (Q6);
  missing image renders `IMAGE UNAVAILABLE`; **an `ATTRIBUTION_REQUIRED` image never
  renders without its attribution** (Q14), with any database enforcement satisfying
  L7's database-enforcement clause.
- **R12 [Automated]** — DATA-D1: candidate data absent from public **response
  bodies** (Q7); structural isolation holds; gate failure writes nothing canonical;
  promotion human-gated, idempotent, audit durable; **promotion documentation
  truthful to implemented gates** (Q8a).
- **R13 [Automated]** — DATA-D1: no live crawling; fixture-only proven; no network
  adapter enabled.
- **R14 [Automated]** — AGENT-01: an unpublished canonical entity is **absent** from
  JSON-LD, sitemap and llms.txt (Q9); UNKNOWN never coerced, **including `0` and
  `""`** (Q12); no fabricated provenance; JSON-LD asserts nothing the page does not.
- **R15 [Automated]** — UNKNOWN / G2 / provenance regression green across the whole
  surface; both G2 gates pass.

### 9.4 WS8.4 — UX correctness

- **R16 [Automated]** — Journeys A, B, C pass end-to-end.
- **R17 [Automated]** — **WCAG 2.2 AA automated conformance**: automated checks on
  every public route, keyboard-only journeys, focus behaviour, semantic
  headings/forms/dialogs, and mobile target-size checks. Not "axe reports zero
  violations" — the automated suite must cover all five.
- **R18 [Attested]** — **Screen-reader spot checks** across nav, catalogue, robot
  detail, wizard, matches and the lead dialog. Named operator, dated report.
  *(Split from R17 per E2 — L8 permits exactly one evidence class per gate.)*
- **R19 [Automated]** — Responsive gate executes on ≥1 mobile and ≥1 desktop viewport
  project (Q2 fixed first, or the gate is meaningless).
- **R20 [Automated]** — Every §5.2 empty/error state individually proven: "No
  confirmed pricing" vs "Price on request" vs `ESTIMATED`/`FROM`/`RANGE`; "No
  confirmed commercial availability"; NULL spec → Unknown/em-dash; zero-match
  explanation; 404 on unknown slug; `/compare` with <2 ids. Never `$0`, never blank,
  never "unavailable".
- **R21 [Automated]** — Lint in CI, including `jsx-a11y` rules (Q4). Supporting
  evidence for accessibility; it does **not** by itself prove WCAG conformance.

### 9.5 WS8.5 — SEO / machine surface

- **R22 [Automated]** — Per-page SEO metadata on every route; no page inherits a
  generic root title (Q3a).
- **R23 [Automated]** — Sitemap and llms.txt enumerate the **entire** published
  canonical set via pagination/chunked retrieval — the 100-entity ceiling removed, not
  documented (Q10) — and `lastMod()` fallback behaviour is tested (Q11).

### 9.6 WS8.6 — Performance + observability

- **R24 [Automated]** — **Deterministic pre-production lab budgets** met on key
  routes. *This is the release-blocking performance gate.* Field CWV targets are
  **not** release-blocking (§11.1).
- **R25 [Automated]** — Production logging / error tracking / health observability
  with request correlation and **no PII in log output** (D9); `event_log` documented
  as **dormant** (D8).

### 9.7 WS8.7 — Production deployment

- **R26 [Attested]** — Deployment shape (§5.6) realized with explicit secrets,
  reproducible build, proxy-wired health/readiness (D1, D2, D3); **DEP P1–P5 bound**
  to the selected infrastructure, which must satisfy P5 as an acceptance filter.
- **R27 [Attested]** — **Network boundary physically realized** per DEP P4: admin on
  a separate protected host/listener, not publicly routable (B1, stage 2).

### 9.8 WS8.8 — Smoke, probe, drill

- **R28 [Automated]** — Post-deploy smoke against the deployed URL: liveness,
  readiness, one public read, one governed write path.
- **R29 [Automated]** — **External negative probe** from outside the deployment: the
  deployed admin **cannot** be reached bypassing the boundary (B1, stage 3), and
  spoofed forwarding headers **cannot** defeat client-IP resolution (B2, stage 2).
- **R30 [Attested]** — Release checklist and operator runbook exist and were
  executed; **rollback drill rehearsed**, including backup restore, conforming to the
  L7 doctrine. Runbook records every ACCEPT-DEFER gap (D10, Q3b, Q8b).

### 9.9 WS8.9 — Release evidence

- **R31 [Automated]** — **Baseline test inventory floor** (counts are *not*
  coverage): ≥145 backend, ≥74 vitest, ≥53 Playwright, six CI jobs, both G2 gates.
- **R32 [Attested]** — **Test-integrity / non-weakening review**: existing assertions
  were not deleted or weakened to preserve the R31 counts. Named reviewer, dated diff
  review of every test modification. *(Split from R31 per E3.)*
- **R33 [Attested]** — **Release Invariant Matrix** (§10) complete: every row has a
  declared evidence class and passing evidence.
- **R34 [Automated]** — **No new product/commercial capability** shipped, using
  WS8-L1's exact vocabulary: no new transactional action, no new commercial surface,
  no new public route, no new canonical entity. Operator/security/deployment/
  observability controls are explicitly permitted.

## 10. Release Invariant Matrix (deliverable)

Finite, auditable manifest replacing an unbounded "every law has a test" claim.
Created at WS8.1, completed at WS8.9:

```
invariant id | law / invariant | source contract | evidence class | test or artifact | gate | status
```

Every frozen law from WS0, MEDIA-01, DATA-D1 and AGENT-01 appears as a row. Laws
provable in code carry **[Automated]** rows; laws provable only by structural
inspection carry **[Attested]** rows. A law with no row is a release blocker; a row
with no evidence is a release blocker.

## 11. Owner decisions (folded)

| # | Decision | Ratified call |
|---|---|---|
| **D1** | Admin authorization | **Both** app-level authn/authz **and** a network boundary; network gating alone rejected. `internet → network restriction → admin authn/authz → SQLAdmin`. Staged across R1 / R27 / R29. Plus enforce `PromotionAudit` append-only (R6). |
| **D2** | Deployment target | Freeze the **shape** (§5.6) **and the DEP** (§6) — not a vendor. **Re-evaluation performed at v0.4: with P1–P5 frozen to values, WS8.1–WS8.6 have sufficient topology semantics to build correctly, so provider selection genuinely REMAINS DEFERRED to WS8.7.** P1–P5 additionally act as an acceptance filter on candidate providers. |
| **D3** | `event_log` | **Dormant / out of scope.** Dead infrastructure is not turned into a feature. Deployment-appropriate logging/observability instead (R25). |
| **D4** | Sitemap / llms 100-cap | **Fix in WS8** (R23) — hardening, not scope expansion. |
| **D5** | Accessibility | **WCAG 2.2 AA** (current W3C recommendation; ISO/IEC 40500:2025) — automated conformance suite (R17) **plus** attested screen-reader spot checks (R18). |
| **D6** | Performance | Release-blocking = **deterministic lab budgets** (R24). Field CWV = **post-release SLO** (§11.1), not release eligibility. |
| **D7** | Rate limiting | **Endpoint-aware**, not one global number; IP throttling, repeated-submission control, idempotency preserved, `429` + `Retry-After`, trusted-ingress-aware client IP (DEP P1), per-env config, tests proving valid retries are not misclassified. **No broad auth on anonymous buyer-intent flows** (L10). |

### 11.1 Post-release SLO (operational — NOT release-blocking)

Field CWV cannot exist before the release that produces it, so it cannot gate that
release. Recorded in the operator runbook, monitored after launch:

```
LCP <= 2.5 s   INP <= 200 ms   CLS <= 0.1     at p75, mobile and desktop,
                                              once sufficient field data exists
```

Evidence class **[Observed]**. Breach triggers operational follow-up, not a release
rollback by itself.

## 12. Explicitly OUT of scope (WS8-L1)

```
Rent / Buy / Lease / RaaS activation      Commercial Architecture programme
payments · checkout · escrow · custody    reservations · contracting
AGENT-01.5 typed actions · MCP            live DATA-D1 network adapters
event_log activation / analytics system   new canonical DB model
parallel agent API                        new public routes · new pages
CRM · supplier dashboard                  automated outreach / notification
public authentication / user accounts     lead scoring · AI qualification
LLM anywhere in a scoring or fact path    schema redesign · destructive migrations
UI redesign (UI-D1 stays frozen)          new catalogue entities
missing DATA-D1 promotion gates (Q8b)     OG/Twitter social imagery (Q3b)
scheduled catalogue re-verification (D10) horizontal API replication (DEP P2)
```

Per L1, operator/security/deployment/observability/correctness controls hardening an
already-authorized surface are **not** in this list.

## 13. Exit criteria

1. Every gate **R1–R34** passed on the exact release head, each with its declared
   evidence class satisfied.
2. All six CI jobs green on that head.
3. Release Invariant Matrix complete (R33).
4. Release checklist and runbook merged and executed; rollback drill rehearsed (R30).
5. Every ACCEPT-DEFER gap recorded in the runbook with its owner.
6. Product owner explicitly approves the release.

```
HUMANOIDONLINE MVP v0.1 — READY FOR PRODUCTION
```

## 14. Revision record

**v0.4 corrections folded (owner review of v0.3, 2026-07-26) — REQUEST MINOR REVISION:**

| # | Correction | Where |
|---|---|---|
| **E1** *(blocking)* | The DEP was **defined but not frozen** — P2/P4/P5 still contained choices, making it a template. **P1–P5 now frozen to values**: singleton API for MVP; process-local limiter behind a storage abstraction; admin on a **separate protected host/listener**, not `/admin` on public ingress; P5 freezes the **required ingress capability** (operator-configurable, testable trust and admin-boundary semantics) rather than provider-managed vs operator-owned — removing the circular provider dependency. | §6 |
| **E2** *(blocking)* | L8 said "exactly one evidence class" while **R17 was `[Automated + Attested]`** — the taxonomy failed its own law. R17 split: **R17 [Automated]** automated WCAG 2.2 AA conformance · **R18 [Attested]** screen-reader spot checks. L8 **not** weakened; hybrids explicitly prohibited. | L8, R17, R18 |
| **E3** | Same contradiction in R30 ([Automated] but demanding a reviewer-attested diff check). Split: **R31 [Automated]** baseline test inventory floor · **R32 [Attested]** test-integrity / non-weakening review. | R31, R32 |
| **E4** | Q14's "any DB constraint must be additive per L7" was dangerous — additive DDL can still be behaviourally backward-incompatible with existing rows or an older binary. L7 gains a **database-enforcement clause**: existing rows preflight clean or are safely remediated before enforcement, and application rollback remains compatible with the migrated schema. | L7, Q14, R9, R11 |
| **E5** | Consequent renumbering: **R1–R32 → R1–R34**; all cross-references in §8, §9.0.1, §11 and §13 updated. | throughout |
| **E6** | **§11 D2 updated**: the provider re-evaluation has now been *performed*, and its conclusion recorded — with the DEP frozen, provider selection genuinely remains deferred to WS8.7. | §11 D2 |

Accepted without change from v0.3: **C3–C8**, the **Q4** (lint) and **Q14** (attribution)
scope decisions.

**v0.3 corrections (owner review of v0.2):** C1 Deployment Execution Profile · C2 L8
evidence taxonomy · C3 field CWV → post-release SLO · C4 L7 schema rollback doctrine ·
C5 L1 redefined · C6 dispositions for every gap · C7 Release Invariant Matrix · C8
test inventory floor · C-seq B3/B4 → WS8.2, R1 staged, new law L11.

## 15. Ratification record

**STATUS: DRAFT v0.4 — RATIFICATION CANDIDATE — NOT RATIFIED.**
No implementation authorized. **`build WS8` remains CLOSED.**

```
v0.2 verdict:      REQUEST REVISION (owner, 2026-07-26) — C1-C8 + sequencing
v0.3 verdict:      REQUEST MINOR REVISION (owner, 2026-07-26) — E1-E4
v0.4 folds:        E1-E6; C3-C8 not reopened; Q4 + Q14 decisions accepted
Decisions folded:  D1-D7 (owner, 2026-07-26)
Ratified by:       (pending ratify-or-reject review of v0.4)
Ratified on:       (pending)
Build trigger:     `build WS8` (not yet issued)
Frozen at ratification: Deployment Execution Profile P1-P5 (§6), to values
Provider selection: confirmed DEFERRED to WS8.7 (§11 D2)
```
