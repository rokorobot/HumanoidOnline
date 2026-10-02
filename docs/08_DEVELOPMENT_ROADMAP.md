# HumanoidOnline — Development Roadmap

> **Status:** Living delivery roadmap
> **Current programme:** Governed Catalogue Discovery & Live Operations (§1.1)
> **Historical product-delivery programme:** WS0–WS8 (§1, §2–§8); the WS8 exit gate is not formally closed (§8)
> **Last updated:** 2026-10-02

This document defines **implementation sequencing and workstream boundaries**: in
what order we build the product, what each workstream owns, what is already
complete, and what must be true before moving forward.

It **does not override** the frozen contracts:

- [`01_PRODUCT_CONTRACT.md`](01_PRODUCT_CONTRACT.md)
- [`02_ARCHITECTURE.md`](02_ARCHITECTURE.md)
- [`03_DATA_DICTIONARY.md`](03_DATA_DICTIONARY.md)
- [`04_API_CONTRACT.md`](04_API_CONTRACT.md)
- [`05_ACCEPTANCE_CRITERIA.md`](05_ACCEPTANCE_CRITERIA.md)
- [`06_WIREFRAMES.md`](06_WIREFRAMES.md)
- [`07_VISUAL_SYSTEM.md`](07_VISUAL_SYSTEM.md)
- [`18_SYSTEM_ARCHITECTURE.md`](18_SYSTEM_ARCHITECTURE.md) (Cross-system topology & integration architecture)

**Where this roadmap conflicts with a frozen contract, the frozen contract wins.**
`01–07` and `18` define *what the product is, its architecture, and how it behaves*; this file defines *the
order in which we build it*.

---

## 1. Governing delivery sequence

```
WS0    Contract Hardening                 ✅ COMPLETE
WS1    Foundation                         ✅ COMPLETE
WS2A   Knowledge API                      ✅ COMPLETE
WS2B   Verified Catalogue                 ✅ COMPLETE
UI-D1  Visual System                      ✅ COMPLETE
WS3    Intelligence UI                    ✅ COMPLETE
WS4    Advanced Compare / Decision        ✅ COMPLETE
WS5    Buyer Intent                       ✅ COMPLETE
WS6    Deterministic Matching             ✅ COMPLETE
WS7    Commercial Lead                    ✅ COMPLETE
WS8    MVP Hardening / Release            🟠 PARTIAL — exit gate not formally closed (§8)
```

The numbered WS0–WS8 sequence is the **historical product-delivery programme** and is
kept as such. It is no longer the sole current programme: the active engineering
programme is **Governed Catalogue Discovery & Live Operations** (§1.1).

> **Post-WS7, pre-WS8 governance slices (merged out of the numbered sequence).**
> Between WS7 and WS8, several governed quality/accessibility slices merged rather
> than jumping straight to release hardening: **MEDIA-01** (verified product
> imagery), **DATA-D1** (competitive discovery + governed promotion, fixture-only),
> and **AGENT-01** (machine/agent read-only projections). They are live on `main`
> but are **not** part of the numbered WS0–WS8 MVP delivery sequence; WS8 remains the
> formal MVP release gate, and its exit state has not been recorded (§8).

Each workstream is PR-gated and lands with its tests (AGENTS.md rule 5). A stage
begins only once the previous stage's exit gate is green on the exact PR head.

### 1.1 Current programme — Governed Catalogue Discovery & Live Operations

The contract is [`16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md`](16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md).
It runs alongside the WS8 release train and does not alter it. **Stages A–F are
operational.** The operating model, one governed step at a time:

```
Scheduled source observation
        ↓
Change detection / bounded acquisition
        ↓
Candidate extraction
        ↓
Identity resolution
        ↓
Human identity + scope review
        ↓
Confirmed source trace
        ↓
Evidence promotion
        ↓
Structured proposal extraction              ← Stage G1 (foundation implemented)
        ↓
Human proposal / claim review               ← Stage G2 (next)
        ↓
Accepted claim promotion                    ← Stage G2
        ↓
Governed catalogue mutation                 ← Stage G2
        ↓
Separate publication decision
```

**Boundaries that hold at every step:**

```
observation ≠ catalogue mutation
candidate identity ≠ verified catalogue fact
identity promotion ≠ publication
evidence attachment ≠ field write
proposal extraction ≠ accepted claim
accepted claim ≠ publication
```

| Stage | Delivers | Status |
|---|---|---|
| **A–F** | Read-only foundation; bounded HTTP acquisition and change detection; the adapter framework and the first source adapter; deterministic candidate extraction and identity resolution; **Stage E** exception-only human review (identity decisions, out-of-scope rejection, source trace, same-entity promotion convergence); **Stage F** scheduled observation (per-source cadence, redirect and cache handling, one-running-run guard, least-privilege database role) | ✅ **OPERATIONAL** |
| **G1** | Proposal-only structured extraction | 🟢 **IMPLEMENTED FOUNDATION** (PR #84) |
| **G2** | Governed proposal review and claim promotion | 🟡 **IN PROGRESS** — architecture ratified in DR-A5; **G2-1 persistence (0018), G2-2 governed review, and the first G2-3 slice (accepted claims, materialization; 0019) implemented**; **G2-5 scheduled proposal ingestion operational for NEURA 4NE1 Mini only**; price/availability (G2-4) pending |
| **G3** | Source expansion | ⏸ After G2 is proven |

**NEURA is the first commissioned scheduled source.** Observation runs **Monday and
Thursday at 06:37 UTC**, governed by a **48-hour source cadence**, through the same
robots.txt and source-approval checks as a manual run. The scheduled extractor is
**identity-only**. The human identity-review queue is **0**. The commissioning
exercise demonstrated each outcome the review step can reach:

- **Match existing** (`MATCHED_EXISTING`) — NEURA's `4NE1` → catalogue record `neura-4ne-1`;
- **Create new** — `4NE1 Mini` → new record `4ne1-mini`;
- **Out of scope** (`OUT_OF_SCOPE`) — MiPA, MAiRA, LARA and MAV, under the humanoid-only
  catalogue scope (docs/16 §17.1).

**Both NEURA humanoid records remain unpublished.** Publication is a separate decision.

#### Stage G1 — Proposal-only structured extraction · IMPLEMENTED FOUNDATION

*Proposal extraction* is used deliberately instead of "claim extraction": the extractor
creates **unverified proposals**, not accepted catalogue claims. Initial implementation
(PR #84):

- **NEURA 4NE1 Mini only**, on the official 4NE1 Mini page;
- a **pure, offline** extractor; **Standard** and **Pro** are editions/configurations of
  **one** robot, never separate robots;
- structured, **evidence-bearing** proposals (source URL, verbatim bounded evidence,
  target field, and the open review questions);
- **no database writes**, **no live-adapter wiring**, **no catalogue mutation**, **no
  publication**; **human review is mandatory**.

Known findings: the current catalogue schema can represent variants, specifications,
pricing and availability, but the existing discovery claim model does not yet cleanly
represent **edition-scoped** proposals. Open semantic and schema questions, recorded
here **without being decided**:

- the edition dimension in proposal persistence;
- the semantics of a manufacturer's own *estimated* price;
- reservation deposit and its terms;
- availability wording such as "expected in 2026";
- mapping free-text use cases;
- claim promotion beyond height, weight and payload.

#### Stage G2 — Governed proposal review and claim promotion · architecture ratified (DR-A5); G2-1, G2-2 and the first G2-3 slice implemented

Expected responsibility:

- proposal persistence;
- edition-aware review;
- human **ACCEPT / REJECT / DEFER** decisions, with reviewer identity and rationale;
- provenance preservation;
- deterministic, idempotent promotion of accepted claims;
- catalogue mutation **only through an explicit governed boundary**;
- publication remains separate.

The persistence architecture and the catalogue boundary are **ratified** in
[`DR-A5`](decisions/DR-A5_GOVERNED_CLAIM_PROPOSAL_REVIEW_AND_PROMOTION_BOUNDARY.md); its normative
text is `docs/16` §17.3. **G2-1 (persistence foundation: immutable proposals,
append-only sightings and decisions, manual offline ingest; migration 0018) and G2-2 (governed
human review: list/show/accept/reject/defer, derived supersession and staleness, reviewer role) are
implemented; the first G2-3 vertical slice (immutable accepted claims, retraction, catalogue write
audit, deterministic materialization into the catalogue of record, variant-scoped specifications; 0019)
is implemented for `robot_variant` and `specification[dexterous_hand_option]` only. G2-5 scheduled
proposal ingestion is operational for the NEURA 4NE1 Mini page only (human review stays mandatory;
there is no automatic acceptance, materialization or publication). Price and availability (G2-4) and
every other mapping remain pending; any further manufacturer needs separate source approval**, and this roadmap authorizes **no catalogue-writing code**. **Price and availability
remain deferred**, as separate owner decisions. The open questions above are settled
phase by phase under DR-A5. The physical G2-1 design is recorded in DR-A5 §18.1.

#### Stage G3 — Source expansion · after G2 is proven

- extend proposal extraction to the full-size 4NE1;
- onboard further manufacturers only after individual source and ToS approval.

#### Deferred — not authorized

- automatic catalogue writes from extraction;
- automatic publication;
- the 43-lead baseline import;
- onboarding additional manufacturers without approval;
- automatic cache pruning;
- a web review UI.

**Rent / Buy / Lease / RaaS** remain the strategic product programme (§9). They are not
the immediate next engineering task.

---

## 2. Completed stages

### WS0 — Contract Hardening ✅
**Purpose:** freeze semantics before implementation.

Key laws frozen:
```
UNKNOWN ≠ 0
UNKNOWN ≠ FALSE
UNKNOWN ≠ NOT_AVAILABLE

QUOTE_ONLY ≠ UNKNOWN

commercial maturity ≠ obtainability ≠ evidence

No commercial fact without evidence.
```
**Exit state:** `BASELINE v0.1 — FROZEN`.

### WS1 — Foundation ✅
**Purpose:** prove the complete platform can build, test and connect *before* any
product feature exists.

Implemented:
```
Next.js + TypeScript · FastAPI · Python 3.12+ · PostgreSQL
SQLAlchemy 2.x · Pydantic v2 · SQL-first bootstrap/migrations
pytest · Vitest · GitHub Actions CI · Docker development PostgreSQL
```

### WS2A — Knowledge API ✅
Real PostgreSQL-backed **read** APIs for: robots, robot detail, robot comparison
data, manufacturers, use cases, filters, commercial data, evidence.

**Rule:** no hardcoded catalogue data — the API is the source of facts.

### WS2B — Verified Catalogue ✅
The production catalogue pipeline: primary-source research → catalogue JSON →
importer → provenance → confidence → G2 validation → NULL/UNKNOWN preservation.

Initial real platforms:
```
Unitree G1 · Unitree H1 · 1X NEO · Agility Digit
Apptronik Apollo · Figure 02 · Engineered Arts Ameca
```
**Seed data (`db/seed/seed.sql`) remains separate from production catalogue data
(`db/catalogue/`).** The seed is a schema stress-test; the catalogue is editorial
truth. They load into different databases.

### UI-D1 — Visual System ✅
**Frozen design direction:** industrial editorial brutalism + experimental systems
graphics + robotics control documentation.

Approved references: Home · Catalogue · Robot Detail · Compare · Find a Humanoid ·
Primitive Spec Sheet.

**Governing UI law:** *Graphic boldness around the data, never instead of the data.*
Full contract in [`07_VISUAL_SYSTEM.md`](07_VISUAL_SYSTEM.md).

---

## 3. WS3 — Intelligence UI ✅ COMPLETE

*Merged in #5 (`b31d81b`): all production routes wired to the live WS2A API + WS2B
catalogue, with a production-like Playwright integration gate proving the verified
truths. Base `/compare` shipped here — WS4 builds advanced comparison on top.*

**Objective:** productionize UI-D1 against the real WS2A API and WS2B catalogue.

**Production routes:**
```
/
/robots
/robots/[slug]
/compare
/manufacturers
/manufacturers/[slug]
/use-cases
/use-cases/[slug]
```

**Core implementation:** typed API client · shared React primitives · permanent
navigation · homepage · catalogue · filters · robot detail · manufacturers · use
cases · comparison matrix · evidence drill-down · responsive behavior · accessibility.

**Critical law — Do not redesign UI-D1. Productionize it.**
UI-D1 defines *presentation*; WS2A + WS2B define *facts*. Static illustrative
values from `docs/design/` must never become production constants.

**WS3 integration truths (production-like validation must prove):**
```
G1        → current verified public price (not illustrative $16,000)
H1        → PRICE ON REQUEST (not illustrative $90,000)
Figure 02 → DISCONTINUED
UNKNOWN   → UNKNOWN (never 0 / false / unavailable)
QUOTE_ONLY ≠ UNKNOWN
maturity ≠ obtainability ≠ evidence
```

**Explicitly out of scope for WS3:**
```
buyer requirement persistence · matching · match-result generation
lead capture · payments · transaction workflows
Rent / Buy / Lease activation
```
The **Find a Humanoid** nav/CTA and its approved visual reference may exist, but no
wizard persistence, scoring, results or lead capture is implemented.

---

## 4. WS4 — Advanced Compare / Decision ✅ COMPLETE

*Merged in #7 (`6c2d982`): additive to the shipped `/compare` — normalization +
Metric/Imperial, a single tested ComparisonPolicy, metric-local best-in-row (never
a score), like-for-like price comparison, deeper fact-level evidence comparison
(incl. the authorized additive `evidence.observed_at`), reference-robot deltas,
URL-canonical shareable state, localStorage-only saved views. No
matching/scoring/persistence/schema.*

Base `/compare` shipped as part of WS3, so WS4 does **not** re-implement it. WS4 owns:
```
advanced comparison behavior · comparison normalization · saved comparisons
shareable decision states · objective best-in-row analysis
deeper evidence comparison · comparison persistence · decision-support refinements
```

---

## 5. WS5 — Buyer Intent ✅ COMPLETE

*Merged in #10 (`0140393`): the real 12-step requirement wizard + the first
Decision-layer write path (`buyer_requirement`) via `POST /api/buyer-requirements`,
plus the canonical `GET /api/regions` read that seeds the Country step. Anonymous
capture (no contact/identity), `raw_input` required + versioned (UNKNOWN ≠ SKIP
preserved), `country` resolves only to canonical `COUNTRY` regions, and creation
makes zero `match_result` / `commercial_lead` rows. Contract-hardened per an
independent gate review before merge.*

Productionize **Find a Humanoid**. Requirement sequence:
```
TASK · INDUSTRY · COUNTRY · ENVIRONMENT · PAYLOAD · HOURS
MANIPULATION · AUTONOMY · BUDGET · TIMELINE · TRANSACTION · REVIEW
```
Persist to `buyer_requirement`. **`UNKNOWN ≠ SKIP`** — they are different demand
signals even if they score alike.

Transaction choices are a **preference**, not an offered product:
```
BUY · RENT · LEASE · RAAS · FLEXIBLE · UNKNOWN
```
Selecting one never implies HumanoidOnline already operates that transaction.

---

## 6. WS6 — Deterministic Matching ✅ COMPLETE

*Merged in #12 (`f3c8664`): the pure, deterministic, explainable scorer
(`app/services/matching`) + `match_result` persistence on first
`GET /api/buyer-requirements/{id}/matches` (lock → recheck → atomic; idempotent;
concurrent-safe; zero-survivor recomputes with no sentinel) + the `/matches/[id]`
results UI (SEE MATCHES, Compare These, Adjust Requirements). Three independent
review passes hardened the policy: accessibility-vs-maturity separation, real
lowest-price BEST_LOWER_COST with a no-FX full-currency-universe rule,
transaction-scoped geography, order-independent budget, count-all quantified
no-match wording, and genuine ≥2 reasons per survivor. No schema/LLM/randomness,
no leads. `maturity ≠ obtainability ≠ evidence` preserved end-to-end.*

The explainable matching engine (pure function; no I/O, no randomness, **no LLM in
the scoring path**). Initial weighting:
```
Use-case fit             25%
Commercial availability  20%
Technical requirements   20%
Geography                15%
Budget                   10%
Deployment readiness     10%
```
Output per requirement: 2–4 recommended humanoids · score · score breakdown ·
reasons · warnings · commercial constraints · supporting evidence.

---

## 7. WS7 — Commercial Lead ✅ COMPLETE

*Merged in #14 (`7056031`): the first commercial conversion — `POST /api/commercial-leads`
+ `app/services/leads/` (service + deterministic routing) writing `commercial_lead`,
`commercial_lead_robot`, and PENDING `commercial_lead_provider` routes via the canonical
`commercially_accessible()` function; four capture surfaces (per-card, whole-shortlist,
zero-match, and Robot-Detail direct); `CommercialLead`/`CommercialLeadProvider` SQLAdmin
triage; forward migration `0001_add_commercial_lead_message.sql`. Introduction-only — no
custody, checkout, or Rent/Buy/Lease activation. Contract-hardened over an independent
review pass (`df37d9d`): canonical accessibility routing, lead-only extension semantics,
exactly-one-robot direct capture, genuine zero-match coverage, API-contract sync.
Delivered as slices WS7.1 contract+lifecycle · WS7.2 service+API · WS7.3 entry points ·
WS7.4 provider routing · WS7.5 SQLAdmin triage+audit · WS7.6 e2e+adversarial hardening.*

Connect buyer demand to commercial action:
```
buyer_requirement → match_result → Request Availability
                  → commercial_lead → OEM / provider / distributor / integrator
```
Still **no** marketplace custody or checkout in v0.1 — lead capture is the only
commercial action.

---

## 8. WS8 — MVP Hardening / Release 🟠 PARTIAL — exit gate not formally closed

**Recorded status.** The repository does not record the exit state below as reached,
so WS8 is **not** claimed complete here:

- WS8.1–WS8.6 merged in July 2026 (R1–R25: security boundaries, deployment/config
  correctness, data/truth regressions, UX correctness, SEO/machine surface,
  performance and observability);
- WS8.7, the production deployment artifacts (R26–R27), is an **open Draft**
  (PR #32), not merged;
- the release invariant matrix ([`13_RELEASE_INVARIANT_MATRIX.md`](13_RELEASE_INVARIANT_MATRIX.md))
  is recorded as in progress, with the production-boundary invariants (P2, P4, P5)
  still pending.

Closing WS8 is a separate product-owner decision. It is not implied by the discovery
programme (§1.1).

Final release gate:
```
end-to-end testing · responsive testing · accessibility · keyboard navigation
screen-reader semantics · performance · SEO · security · error states
loading states · empty states · analytics · observability
production deployment · provenance regression · UNKNOWN regression · G2 regression
```
**Exit:** `HUMANOIDONLINE MVP v0.1 — READY FOR PRODUCTION`.

---

## 9. Strategic product phases

The engineering roadmap above delivers a permanent product sequence:
```
PHASE 1 — INTELLIGENCE       HumanoidOnline
        ↓
PHASE 2 — BUYER INTENT       HumanoidOnline
        ↓
PHASE 3 — RENT               RentHumanoid.com
        ↓
PHASE 4 — BUY                HumanoidMart.com
        ↓
PHASE 5 — LEASE / RAAS       HumanoidLease.com
```

These phases remain the **strategic** product programme. They are not the immediate
next engineering task (§1.1).

**HumanoidOnline, RentHumanoid, HumanoidMart and HumanoidLease are verticals over
one shared platform and knowledge/transaction model — not four independent software
stacks.** MVP v0.1 implements Phases 1–2; Phases 3–5 exist dormant in the data model
(`transaction_type`, `provider`, offer views, lead-routing tables) and need no schema
migration to activate.

---

## 10. Current project state

*(This section is deliberately updated after every merge. It records the
**last completed substantive workstream merge** — a stable anchor, not the literal
future commit the next branch is cut from (this file can never store its own future
merge SHA, and docs-only roadmap housekeeping like this update may itself merge
after this anchor and before the next branch is cut). The next workstream is cut
from whatever `main` is at cut time and verified 0 ahead / 0 behind then.)*

```
Last completed workstream merge:  7056031d7f46b100ed5b35728791caaddd581dfb  (WS7, PR #14)
Historical programme:             WS0–WS7 complete; WS8 partial (exit gate not formally closed, §8)
Current programme:                Governed Catalogue Discovery & Live Operations (§1.1)
Operational:                      Stages A–F; NEURA scheduled (Mon + Thu 06:37 UTC, 48 h cadence)
Latest foundation:                Stage G1 proposal-only extraction (PR #84, merge 42954ed)
Next:                             Stage G2 — governed proposal review and claim promotion
                                  (DR-A5; G2-1, G2-2 and the first G2-3 slice implemented; G2-5 operational for NEURA Mini; G2-4 pending)
Strategic, not immediate:         Commercial Architecture — Rent / Buy / Lease-RaaS

Completed:  ✅ WS0  ✅ WS1  ✅ WS2A  ✅ WS2B  ✅ UI-D1  ✅ WS3  ✅ WS4  ✅ WS5  ✅ WS6  ✅ WS7
Partial:    🟠 WS8
```

**Note on `main` vs. the WS7 anchor.** Per this section's convention the anchor is the
*last completed numbered-workstream merge* (WS7 @ `7056031`). `main` is deliberately
**ahead** of that anchor: the post-WS7 governance slices (MEDIA-01 @ `5b40c86`/`162abfd`,
DATA-D1 @ `d63f700`/`3dca8cc`, AGENT-01 @ `35c2576`/`217460a`), the WS8.1–WS8.6 slices,
catalogue growth and the discovery programme (§1.1) all merged afterward. A new
workstream is cut from whatever `main` is at cut time (verified 0-ahead / 0-behind
then), **not** from the WS7 anchor.
