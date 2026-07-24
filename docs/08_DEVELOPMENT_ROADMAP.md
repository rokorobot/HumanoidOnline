# HumanoidOnline — Development Roadmap

> **Status:** Living delivery roadmap
> **Current stage:** WS4 — Advanced Compare / Decision
> **Last updated:** 2026-07-24

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

**Where this roadmap conflicts with a frozen contract, the frozen contract wins.**
`01–07` define *what the product is and how it behaves*; this file defines *the
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
WS4    Advanced Compare / Decision        🟠 CURRENT
WS5    Buyer Intent                       ⏳ PLANNED
WS6    Deterministic Matching             ⏳ PLANNED
WS7    Commercial Lead                    ⏳ PLANNED
WS8    MVP Hardening / Release            ⏳ PLANNED
```

Each workstream is PR-gated and lands with its tests (AGENTS.md rule 5). A stage
begins only once the previous stage's exit gate is green on the exact PR head.

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

## 4. WS4 — Advanced Compare / Decision ⏳

Base `/compare` shipped as part of WS3, so WS4 does **not** re-implement it. WS4 owns:
```
advanced comparison behavior · comparison normalization · saved comparisons
shareable decision states · objective best-in-row analysis
deeper evidence comparison · comparison persistence · decision-support refinements
```

---

## 5. WS5 — Buyer Intent ⏳

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

## 6. WS6 — Deterministic Matching ⏳

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

## 7. WS7 — Commercial Lead ⏳

Connect buyer demand to commercial action:
```
buyer_requirement → match_result → Request Availability
                  → commercial_lead → OEM / provider / distributor / integrator
```
Still **no** marketplace custody or checkout in v0.1 — lead capture is the only
commercial action.

---

## 8. WS8 — MVP Hardening / Release ⏳

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

**HumanoidOnline, RentHumanoid, HumanoidMart and HumanoidLease are verticals over
one shared platform and knowledge/transaction model — not four independent software
stacks.** MVP v0.1 implements Phases 1–2; Phases 3–5 exist dormant in the data model
(`transaction_type`, `provider`, offer views, lead-routing tables) and need no schema
migration to activate.

---

## 10. Current project state

*(This section is deliberately updated after every merge.)*

```
Current canonical main:   b31d81b8adf65bbe80c17ccccc31decee51f9bdb
Current workstream:       WS4 — Advanced Compare / Decision
Current branch:           (not yet cut — branch fresh from main)

Completed:  ✅ WS0  ✅ WS1  ✅ WS2A  ✅ WS2B  ✅ UI-D1  ✅ WS3
Current:    🟠 WS4
Next:       WS5 → WS6 → WS7 → WS8
```
