# HumanoidOnline — MVP v0.1 Product Contract

**Version:** 0.1
**Status:** **BASELINE v0.1 — FROZEN / READY FOR WS1** (after WS0 Contract Consistency Hardening, 2026-07-23). Visual UI deliberately *not* frozen.
**Companion artifacts:** `db/schema.sql` (canonical data contract) · `02_ARCHITECTURE.md` · `03_DATA_DICTIONARY.md` · `04_API_CONTRACT.md` · `05_ACCEPTANCE_CRITERIA.md` · `AGENTS.md`
**Date:** 2026-07-23

**The test this document must pass:** an implementation agent can answer *"What must exist when MVP v0.1 is complete?"* without guessing.

---

## 0. What this document is

This is the **product contract** for HumanoidOnline MVP v0.1: the binding definition of *what the product does, what it must contain, and what it explicitly does not do* in the first release. It pairs one-to-one with `schema.sql`. Every surface below names the schema entities it reads and writes, so the database and the product cannot drift apart.

It is intentionally **not** a visual design spec. It fixes *what each screen must accomplish and what data it consumes*, not typography, color, spacing, cards, or motion. Those are resolved in a later UI/UX stage, on top of this contract.

Two rules govern everything here:

1. **Build the intelligence + decision product now (Phases 1–2). Architect the transaction platform (Phases 3–5) from day one.** Phases 3–5 are supported by the data model and stay dormant in the UI. No rebuild, no migration to activate them.
2. **Commercial maturity, transaction availability, and deployment evidence are three independent dimensions** — never one `available` boolean. This is the lesson from Agility's Digit: a robot can be commercially deployed (RaaS), *not* directly purchasable, and carry $300M+ of contracted-order evidence simultaneously. The schema encodes all three separately.

---

## 1. Positioning

> **HumanoidOnline is the commercial intelligence and transaction infrastructure for the humanoid robotics economy.**

It is **not** a robotics news site, blog, or generic directory. Its job: help a person or organization understand *which humanoid robots exist, what they can actually do, whether they are commercially accessible, which ones fit a specific requirement, and how to proceed toward acquisition or deployment.*

---

## 2. The three permanent layers

| Layer | Job | Phase | Primary entities (`schema.sql`) |
|---|---|---|---|
| **A — Knowledge** | Structured truth about the market | Phase 1 | `manufacturer`, `robot`, `robot_variant`, `specification`, `capability`, `use_case`, `pricing_offer`, `availability_offer`, `deployment`, `region`, `provider`, `evidence_source` |
| **B — Decision** | Turn information into "which humanoid?" | Phase 1 → 2 | `buyer_requirement`, `match_result`, `use_case_fit` |
| **C — Transaction** | Turn interest into "help me obtain it" | Phase 2 → 3–5 | `commercial_lead`, `commercial_lead_robot`, `commercial_lead_provider`, `availability_offer`, `pricing_offer` |

v0.1 fully implements A and B, and the *lead-capture* front edge of C. The rest of C is built structurally and left dormant.

---

## 3. Strategic sequence (permanent)

```
Phase 1 Intelligence → Phase 2 Buyer Intent → Phase 3 Rent → Phase 4 Buy → Phase 5 Lease/RaaS
   (this MVP)             (this MVP)          RentHumanoid   HumanoidMart   HumanoidLease
```

Each phase de-risks the next: audience + data → buyer intent → transactions → proprietary market intelligence. The four domains **share one platform** (robot DB, manufacturers, identity, requirements, providers, matching, leads, evidence, analytics). They must never become four independent technical stacks.

---

## 4. Users v0.1 serves (`buyer_requirement.buyer_type`)

| Type | Examples | Their question |
|---|---|---|
| **Commercial buyer** (`COMMERCIAL_BUYER`) | manufacturing, logistics, warehouse, hospitality, events, retail, integrators | "What humanoid could solve my problem?" |
| **Technical evaluator** (`TECHNICAL_EVALUATOR`) | robotics/AI engineers, universities, labs, startups | "Which platform has the hardware/software I need?" |
| **Industry participant** (`INDUSTRY_PARTICIPANT`) | manufacturers, distributors, integrators, rental/RaaS operators | "How does HumanoidOnline bring me qualified customers?" |

The third type is the monetization counterparty (modeled as `provider`).

---

## 5. Page inventory (complete — no other routes in v0.1)

```
/                          Home
/robots                    Catalogue
/robots/[slug]             Robot Detail
/compare                   Comparison (robots selected via ?ids= query param)
/manufacturers             Manufacturer index
/manufacturers/[slug]      Manufacturer Detail
/use-cases                 Use Case index
/use-cases/[slug]          Use Case Detail
/find-a-humanoid           Buyer-intent wizard
/matches/[id]              Match Results for a buyer_requirement id
```

**Primary nav:** Robots · Compare · Manufacturers · Use Cases · **[Find a Humanoid]** (principal CTA).
**Not in nav yet:** Rent, Buy, Lease, News, Community, Jobs, Components.

Every page contract in §6 specifies: **Inputs** (data received), **Required content**, **Actions**, and **Empty/error states**. Appearance is *not* specified.

### 5.1 User-flow contract (critical journeys — do not invent navigation)

**Journey A — Explore & compare**
```
Visitor → /robots → filter catalogue → /robots/[slug] → add to compare → /compare
```

**Journey B — Buyer intent (the commercial spine)**
```
Visitor → /find-a-humanoid → submit requirements
       → buyer_requirement persisted → deterministic scoring engine
       → /matches/[id] → "Request commercial help" → commercial_lead created
```

**Journey C — Use-case entry**
```
/use-cases/[slug] → suitable robots → /robots/[slug] → /find-a-humanoid (pre-seeded with use case)
```

These three journeys must work end-to-end for v0.1 to be complete. No other journeys are required.

### 5.2 Empty/error states (global rules)

- Price display distinguishes *unknown* from *quote-gated* — they are different facts: a robot with **no `pricing_offer` rows** renders **"No confirmed pricing"** (we do not know the price); a robot with a **`QUOTE_ONLY`** offer renders **"Price on request"** (we know the commercial model requires a quote). `ESTIMATED` renders "Estimated $X", `FROM` renders "From $X", `RANGE` renders "$X–$Y". Never `$0`, never blank.
- A robot with no current `availability_offer` rows renders **"No confirmed commercial availability"** — never "unavailable" (absence of data ≠ negative fact).
- A NULL spec column renders **"Unknown"** or an em dash — never `0`, never `false`.
- `/matches/[id]` with zero surviving candidates renders an explicit "no match" state that explains which hard requirement eliminated the most candidates, and still offers lead capture ("Tell us anyway — we track the market").
- Unknown slug on any `[slug]` route → 404 page with a link back to the parent index.
- `/compare` with fewer than 2 valid ids → prompt to select robots, with a robot picker.

---

## 6. Surface contracts

Each surface below is a testable contract: **Purpose**, **Reads** (schema entities consumed), **Writes**, **Actions**, **Acceptance criteria**, and **Dormant extension point** (how Phases 3–5 light up without a redesign).

### 6.1 Home
- **Purpose:** Communicate utility ("Find the right humanoid robot"), not journalism.
- **Reads:** `robot` (commercially accessible subset via `robot_commercial_snapshot`), `use_case`, `manufacturer`, market counts.
- **Actions:** *Explore Humanoids*, *Find a Humanoid*, *Compare Robots*; browse-by-application; browse manufacturers; market snapshot (tracked humanoids, commercially accessible, pilot/deployment, R&D platforms, manufacturers).
- **Acceptance:** A first-time visitor understands within one screen that this is a live commercial database, and can reach the catalogue, the matcher, and compare in one click each.
- **Dormant point:** Market snapshot can later add rent/buy/lease counts from `availability_offer.transaction_type`.

### 6.2 Robots (catalogue) — `/robots`
- **Purpose:** Search and filter the full database.
- **Reads:** `robot` (+ first-class filter columns), `specification`, `robot_capability`, `availability_offer`, `pricing_offer`, `region`, `use_case_fit`.
- **Filter groups (schema-backed; not all need to be exposed in v0.1):**
  - *Commercial:* `robot.commercial_status`, `availability_offer.transaction_type` + `availability_status`, `region`, `pricing_offer` band.
  - *Physical:* height, weight, payload, walk speed, runtime, `mobility`, hand type, DOF.
  - *Intelligence:* `autonomy`, `has_teleoperation`, `has_vision`, `has_language_ui`, `has_manipulation`.
  - *Developer:* `has_sdk`, `has_api`, `ros_support`, `developer_edition`, `simulation_support`.
  - *Application:* `use_case_fit`.
- **Acceptance:** Every filter maps to a real column/relation (no dead filters). Full-text search hits `robot.search_vector`. Results sortable by price using `robot.lowest_purchase_price` (cache; authoritative money stays in `pricing_offer`).
- **Dormant point:** "Available to rent/buy/lease" filters are already expressible via `availability_offer`; simply expose them later.

### 6.3 Robot Detail — `/robots/{slug}`
- **Purpose:** The core information object. Must answer five questions: *What is it? · What can it do? · How good technically? · Can I actually obtain it? · Is it right for my requirement?*
- **Reads:** `robot`, `manufacturer`, `robot_variant`, `specification`+`spec_definition`, `robot_capability`+`capability`, `use_case_fit`+`use_case`, `commercial_status`, `pricing_offer`, `availability_offer`+`region`, `deployment`, `evidence_source`.
- **Information architecture (order fixed; visual style not):** Name · Manufacturer · Commercial status · Hero summary → Overview → Specifications → Capabilities → Manipulation → Mobility → AI/Autonomy → Software/SDK → Applications → Commercial Availability → Pricing → Regions → Deployments/Evidence → Compare → **Commercial Action**.
- **Commercial Action (the dormant hinge):** v0.1 renders a single generic CTA **"Request Availability"** which creates a `buyer_requirement` + `commercial_lead`. The same panel later renders **Rent / Buy / Lease-RaaS** buttons driven by which `availability_offer.transaction_type` rows exist — no page redesign.
- **Acceptance:** Maturity (`commercial_status`), obtainability (`availability_offer`), and evidence (`deployment` + `evidence_source`) are shown as *distinct* facts. A robot that is `RAAS_DEPLOYMENT`, not purchasable, and has $300M contracted deployments renders all three truthfully. Every price shows its `price_type` and, where present, an evidence "Verified: {date} / Source: {type}" indicator.

### 6.4 Compare — `/compare`
- **Purpose:** Side-by-side of 2–4 humanoids. Differentiator: not just *better specs* but *more deployable*.
- **Reads:** same entities as Robot Detail, for N robots.
- **Row groups:** Commercial (price, availability, `commercial_status`, purchase/rental/lease/RaaS) · Physical · Manipulation · Intelligence · Developer · Deployment (industries, known deployments, support model).
- **Writes (SHOULD):** shareable comparison via URL-encoded robot ids (no table required); saved comparisons deferred.
- **Acceptance:** Comparison renders the commercial group *first*, and shows availability per transaction type, not a single yes/no.

### 6.5 Manufacturers — `/manufacturers`, `/manufacturers/{slug}`
- **Purpose:** Company profiles + portfolios.
- **Reads:** `manufacturer`, its `robot` portfolio, `region`, `provider` (partners), `deployment`.
- **Detail IA:** Overview → Humanoids → Applications → Commercial Model → Deployment Geography → Customers/Deployments → Contact/Request Information.
- **Acceptance:** Every manufacturer field in the schema has a place to render; contact action creates a `commercial_lead` (industry-participant path optional in v0.1).

### 6.6 Use Cases — `/use-cases`, `/use-cases/{slug}`
- **Purpose:** First-class application entity (not tags). High SEO + buyer-acquisition value.
- **Reads:** `use_case` (`typical_tasks`, `typical_requirements`, `key_limitations`), `use_case_fit` → suitable `robot`s with readiness + limitations.
- **Actions:** "Find a robot for this application" → seeds `Find a Humanoid` with the use case.
- **Acceptance:** Each page lists suitable robots ranked by `use_case_fit.fit_score` with an explicit `commercial_readiness` and limitations per robot.

### 6.7 Find a Humanoid — `/find-a-humanoid` → Match Results (**most important commercial feature**)
- **Purpose:** A lightweight *decision engine*, not a contact form. "Describe your problem; HumanoidOnline identifies platforms."
- **Intake flow → `buyer_requirement`:** task → industry → specific task → country → environment → payload → operating hours → manipulation? → autonomy? → budget → required-by date → **transaction preference** (`Unknown / Rent / Buy / Lease / Robots-as-a-Service / Flexible`, stored as `preferred_transaction` — all six enum values exposed; RaaS preference is high-value Phase-2 demand intelligence).
- **Writes:** one `buyer_requirement` (with full `raw_input` JSON), N `match_result` rows; on contact capture, one `commercial_lead` (+ `commercial_lead_robot`).
- **Key rule:** transaction preference is collected **now**, before Rent/Buy/Lease launch — this generates proprietary demand intelligence from day one.
- **Acceptance:** Submitting the flow always returns an explainable ranked shortlist (see §7). No opaque "AI magic."

### 6.8 Match Results — `/matches/[id]`
- **Purpose:** Present 2–4 labeled matches with *why*.
- **Inputs:** `buyer_requirement.id`; reads `match_result` (score, `category`, `reasons`, `warnings`, `score_breakdown`) joined to `robot`.
- **Labels (`match_result.category`):** Best Overall · Best Commercial (available) · Best Lower-Cost · Best Developer.
- **Actions:** "Request commercial help" per card or for the shortlist → creates `commercial_lead` (+ `commercial_lead_robot`); "Compare these" → `/compare`; "Adjust requirements" → back to wizard pre-filled.
- **Empty state:** see §5.2 — explain the eliminating constraint, still capture the lead.
- **Acceptance:** Each card shows a % score, ≥2 concrete `reasons` (e.g. "✓ commercial deployment available", "✓ suitable payload") and any `warnings` (e.g. "⚠ runtime may require charging strategy"). Each card's next step creates/extends a `commercial_lead`.

---

## 7. Matching contract (deterministic + explainable)

The recommendation resolves to **structured, weighted criteria** — repeatable, testable, explainable. An LLM may *interpret* natural-language input into structured `buyer_requirement` fields, but must **not** be the scorer.

Default weights (stored per result in `match_result.score_breakdown`):

| Criterion | Weight | Source |
|---|---:|---|
| Use-case fit | 25% | `use_case_fit.fit_score` |
| Commercial availability | 20% | `availability_offer` for preferred/any transaction type |
| Technical requirements | 20% | `robot` specs vs `buyer_requirement` (payload, autonomy, manipulation…) |
| Geographic availability | 15% | `availability_offer.region` vs requirement country |
| Budget | 10% | `pricing_offer` vs `budget_min/max` |
| Deployment readiness | 10% | `commercial_status` + `deployment` evidence |

Weights may later become use-case-dependent. `score` is 0–100; `score_breakdown` records each criterion's contribution so the UI can render the exact "why."

### 7.1 Hard exclusions (applied before scoring)

A candidate robot is **rejected** (never ranked) when a *known* value violates a *stated* hard requirement:

```
REJECT if requirement.payload_min_kg        > robot.payload_kg          (robot value known)
REJECT if requirement.manipulation_required = true AND robot.has_manipulation = false
REJECT if requirement.autonomy_required     > robot.autonomy            (ordered enum, robot value known)
REJECT if robot.commercial_status           = 'DISCONTINUED'
```

**UNKNOWN never excludes.** If the robot's value is NULL, the candidate passes the exclusion but takes a scoring penalty and a warning ("payload unverified"). Unknown must never silently equal zero or `false` — this distinction matters enormously in this dataset.

### 7.2 Missing-data behavior

- Requirement field left blank → that criterion redistributes its weight proportionally across the stated criteria (a buyer who states no budget is not scored on budget).
- Robot field NULL for a stated requirement → that criterion scores **0.5 of its weight** (neutral-uncertain, not zero) and emits a `warnings[]` entry.
- Budget vs `QUOTE_ONLY` pricing → neutral-uncertain (0.5), warning "pricing is quote-only".

### 7.3 Normalization

Each criterion produces a sub-score in [0,1]; final `score = round(Σ subscore_i × weight_i × 100)`. Numeric fits (payload margin, budget headroom) use clamped linear ramps, not cliffs — a robot at 105% of budget scores low on budget, it is not excluded.

### 7.4 Tie handling (deterministic)

Equal `score` → order by: (1) higher commercial-availability sub-score, (2) more `deployment` evidence rows, (3) more recently `verified_at` evidence, (4) `robot.slug` ascending as the final stable key. Identical input must always produce identical output — no randomness anywhere in the engine.

### 7.5 Explanation generation

`reasons[]` = top contributing criteria phrased as concrete facts ("✓ available in requested geography"). `warnings[]` = every neutral-uncertain fallback and every near-miss ("⚠ runtime may require charging strategy"). Every number shown to the buyer must be reproducible from `score_breakdown`. The engine is a pure function: `(buyer_requirement, robot*, offers*, fits*) → match_result*`, independently testable with fixture data, no LLM in the scoring path.

---

## 8. Data contract (the parts that must never regress)

These are contractual invariants enforced by `schema.sql`:

1. **Three independent dimensions.** Maturity = `robot.commercial_status` (enum). Obtainability = `availability_offer` rows (per `transaction_type` × `region` × `provider`, with `availability_status`). Evidence = `deployment` + `evidence_source`. There is **no** `robot.available` boolean, by design. The view `robot_commercial_snapshot` exposes all three side by side.
2. **Price is never one column.** All money lives in `pricing_offer`, keyed by `transaction_type` (`PURCHASE/RENTAL/SUBSCRIPTION/LEASE/RAAS/PILOT/DEVELOPER/OTHER`), `price_type` (`PUBLIC/ESTIMATED/QUOTE_ONLY/FROM/RANGE`), `billing_period`, `region`, `provider`. `robot.lowest_purchase_price` is a sort/badge cache only.
3. **Availability is never one boolean.** It is `availability_status` (`NOT_AVAILABLE/WAITLIST/PREORDER/LIMITED/AVAILABLE/ON_REQUEST/DISCONTINUED`) per transaction type and region. Where a yes/no access decision *is* needed (Home's "Commercially accessible", snapshot, filters), the one canonical predicate is the schema function `commercially_accessible()`: `is_current AND status NOT IN (NOT_AVAILABLE, DISCONTINUED)` — waitlist, preorder, limited and on-request all count as accessible. No ad-hoc status lists anywhere.
4. **Commercial maturity is an explicit ladder:** `ANNOUNCED → DEVELOPMENT → PROTOTYPE → PILOT → EARLY_ACCESS → LIMITED_COMMERCIAL → COMMERCIAL → RAAS_DEPLOYMENT → DISCONTINUED`. Maturity ≠ purchasability.
5. **Geography is a first-class hierarchy** (`region`), attachable independently to pricing, availability, deployment, and support — prep for Phases 3–5.
6. **Provenance is available for every changing commercial claim** via `evidence_source` (`source_url`, `source_type`, `published_at`, `observed_at`, `verified_at`, `confidence`). Verified commercial intelligence is the moat.
7. **The buyer intent object is permanent.** `buyer_requirement` → `match_result` → `commercial_lead` is one continuous chain; the same `commercial_lead` becomes a rental, purchase, or lease/RaaS opportunity across phases with **no** migration.
8. **Providers exist from day one** (`provider`, `provider_type`) as the bridge to RentHumanoid / HumanoidMart / HumanoidLease, even though mostly invisible in v0.1.

Entity map:

```
manufacturer ─┬─ robot ─┬─ robot_variant
              │         ├─ specification (+ spec_definition)
              │         ├─ robot_capability (+ capability)
              │         ├─ use_case_fit (+ use_case)
              │         ├─ robot_status_history        (maturity, DIM 1)
              │         ├─ pricing_offer               (money)
              │         ├─ availability_offer          (obtainability, DIM 2)
              │         └─ deployment                  (evidence, DIM 3)
              └─ provider ── (offers, leads routing)

buyer_requirement ─ match_result ─ commercial_lead ─┬─ commercial_lead_robot
                                                    └─ commercial_lead_provider

evidence_source  (polymorphic provenance over all of the above)
region           (hierarchy attached to pricing / availability / deployment)
```

---

## 9. Monetization contract (v0.1)

**No payments, no checkout, no escrow, no custody of robots in v0.1.** First revenue = **qualified commercial introductions**.

```
Buyer → Find a Humanoid → qualified buyer_requirement → matched robots
      → interested provider (supplier/distributor/integrator)
      → commercial introduction (commercial_lead_provider) → HumanoidOnline revenue
```

Modeled by `commercial_lead` + `commercial_lead_provider` (routing/introduction log) + `provider.accepts_leads` / `provider.lead_fee_model`. Later revenue models (fee per qualified lead, referral commission, supplier subscription, enhanced manufacturer profiles, commercial-intelligence subscriptions) attach to these same entities.

---

## 10. MVP boundary

**MUST HAVE:** robot DB · manufacturer DB · structured specifications · commercial status · pricing architecture · availability architecture · use cases · robot search/filter · robot detail · comparison · Find a Humanoid · match results · buyer lead capture · evidence/provenance · internal admin CRUD.

**SHOULD HAVE:** saved comparisons · shareable comparison URLs · use-case pages · geographic availability · basic provider records · deployment evidence.

**NOT IN MVP:** rental booking · checkout · escrow · fleet management · financing · leasing underwriting · insurance · logistics · teleoperation · community/social · news-publishing operation · complex CRM · marketplace seller dashboards.

**Explicitly NOT designed yet (deferred to UI/UX stage):** visual style · color palette · fonts · exact cards · spacing · animation · dashboard look · dark/light mode · detailed responsive layouts · icon system · hero imagery · microinteractions.

---

## 11. Dormant Phase 3–5 extension points (no rebuild required)

| Phase | Activation | What lights up |
|---|---|---|
| **3 — Rent** (RentHumanoid) | Populate `availability_offer` rows with `transaction_type='RENTAL'` + `provider` | "Rent this humanoid" CTA on Robot Detail; `rental_offer` view; rent filters |
| **4 — Buy** (HumanoidMart) | Populate `PURCHASE` offers + `pricing_offer` | "Buy this humanoid" CTA; `purchase_offer` view |
| **5 — Lease/RaaS** (HumanoidLease) | Populate `LEASE`/`RAAS` offers | "Lease / RaaS" CTA; `lease_offer` view |

The `rental_offer` / `purchase_offer` / `lease_offer` views already exist in `schema.sql` so vertical apps read "their" offers without re-implementing logic. The Robot Detail Commercial Action panel and the `commercial_lead` object are unchanged across all three activations.

---

## 12. Technical architecture (frozen — details in `02_ARCHITECTURE.md`)

**Next.js + TypeScript** (frontend) · **FastAPI** (backend) · **PostgreSQL** (`db/schema.sql`, canonical) · **SQLAlchemy** (ORM) · **Pydantic** (validation) · PostgreSQL full-text (`robot.search_vector`) + structured filters for search · internal admin CRUD · basic product/event analytics (`event_log`) · deterministic scoring service for matching · **pytest + frontend tests**.

**Do not introduce** (until the product demands it): Elasticsearch · microservices · pervasive vector infra · event buses · Kubernetes · multi-agent architecture · vector databases.

---

## 13. v0.1 success criterion

> A potential customer who arrives knowing almost nothing about humanoids leaves with: **"These are the 2–4 humanoid platforms relevant to my requirement, here is *why*, here is each one's current commercial status, and here is my next step toward obtaining one."**

That is the product. Everything else is secondary.

---

## 14. North-star flow (context for the frozen scope)

```
DISCOVER → HumanoidOnline → UNDERSTAND (robots + market data) → COMPARE → MATCH
        → BUYER INTENT ─┬─ RENT  → RentHumanoid
                        ├─ BUY   → HumanoidMart
                        └─ LEASE → HumanoidLease
        → TRANSACTION → PROPRIETARY MARKET DATA → HumanoidOnline (compounding moat)
```

MVP v0.1 delivers DISCOVER → UNDERSTAND → COMPARE → MATCH → BUYER INTENT (lead), with the transaction tail built structurally and dormant.
