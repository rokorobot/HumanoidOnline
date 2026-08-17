# HumanoidOnline — System Architecture

> **Document:** `18_SYSTEM_ARCHITECTURE.md`  
> **Version:** v0.1  
> **Status:** **RATIFIED — v0.1 frozen integration architecture**  
> **Date:** 2026-08-07  
> **Product:** HumanoidOnline  
> **Repository:** `rokorobot/HumanoidOnline`

---

## 0. Purpose, authority, and precedence

This document describes the **end-to-end system architecture** of HumanoidOnline: how the human website, API, canonical knowledge model, discovery/acquisition system, verification gates, deterministic decision engine, buyer-intent pipeline, commercial lead layer, media truth system, machine-readable projections, and future Rent / Buy / Lease-RaaS verticals fit together as **one platform**.

It is an **integration architecture**. It exists so implementation agents can answer:

> **“Where does this capability belong, what may it read or write, what trust boundary does it cross, and how does it evolve through Phases 1–5 without creating a second platform?”**

This document does **not** silently amend the existing frozen contracts.

### 0.1 Authority order

1. `db/schema.sql` — **canonical data model**
2. Frozen core product & architecture contracts (`docs/01–07` + **this document**, `docs/18_SYSTEM_ARCHITECTURE.md`)
3. Specialized ratified contracts for their own specific domains, including:
   - `docs/09_MEDIA_CONTRACT.md` (MEDIA-01)
   - `docs/10_AGENT_CONTRACT.md` (AGENT-01)
   - `docs/11_DATA_D1_CONTRACT.md` (DATA-D1)
   - later ratified specialized contracts in `docs/12+`
   *(These govern their specific domain and override general statements in 18 for their specific scope.)*
4. `docs/08_DEVELOPMENT_ROADMAP.md` — delivery sequencing only

If this document appears to authorize something that a higher-authority contract forbids, **the higher-authority contract wins**.

### 0.2 What this document does not authorize

This document by itself does **not** authorize:

- a canonical schema change;
- a new public route;
- a new commercial transaction workflow;
- Phase 3 Rent activation;
- Phase 4 Buy activation;
- Phase 5 Lease/RaaS activation;
- checkout, payment, escrow, custody, booking, or settlement;
- a new crawler target or external-source access;
- a new infrastructure service;
- a second API or database for a vertical;
- an LLM in deterministic matching;
- automated canonical promotion;
- generated identity imagery for real robots.

Those changes retain their existing product-owner / contract / PR gates.

---

# 1. Architectural mission

HumanoidOnline is:

> **The commercial intelligence and transaction infrastructure for the humanoid robotics economy.**

The permanent strategic sequence is:

```text
Phase 1                  Phase 2             Phase 3          Phase 4          Phase 5
INTELLIGENCE      →      BUYER INTENT   →     RENT       →      BUY       →    LEASE / RAAS
HumanoidOnline           HumanoidOnline       RentHumanoid     HumanoidMart     HumanoidLease
```

The architecture must therefore do two things at once:

1. deliver the **Phase 1–2 product now**; and
2. preserve the structures required to activate Phases 3–5 **without rebuilding the platform or duplicating truth**.

The core architectural law is:

> **One humanoid-market platform, many future commercial experiences.**

RentHumanoid, HumanoidMart, and HumanoidLease are not independent technical platforms. They are future transaction-specific projections and workflows over the same HumanoidOnline identity, evidence, provider, pricing, availability, requirement, matching, lead, and analytics systems.

---

# 2. System context

HumanoidOnline sits between the external humanoid ecosystem and human/machine users.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL HUMANOID ECOSYSTEM                          │
│                                                                              │
│ Manufacturers · Official documents · Stores · Distributors · Integrators     │
│ Aggregators · Marketplaces · Editorial sources · Customer/deployment sources │
│ APIs / feeds / files where explicitly permitted · Human research             │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       │ governed acquisition / research
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              HUMANOIDONLINE                                  │
│                                                                              │
│  Discovery / Acquisition  ──►  Verification  ──►  Canonical Knowledge        │
│                                                     │                        │
│                                                     ▼                        │
│                                             Decision Engine                  │
│                                                     │                        │
│                                                     ▼                        │
│                                           Buyer Intent / Leads               │
│                                                     │                        │
│                                                     ▼                        │
│                                       Future Transaction Verticals           │
└───────────────────────────┬─────────────────────────┬────────────────────────┘
                            │                         │
                            ▼                         ▼
                     HUMAN USERS                MACHINE USERS
                  Buyers / evaluators         Search / LLMs / later
                  industry participants       governed procurement agents
```

---

# 3. Permanent platform decomposition

The permanent platform is divided into **five logical layers**.

```text
┌─────────────────────────────────────────────────────────────────────┐
│ 5. EXPERIENCE / PROJECTION                                         │
│ Human web UI · semantic HTML · JSON-LD · later vertical experiences│
├─────────────────────────────────────────────────────────────────────┤
│ 4. TRANSACTION / INTENT                                            │
│ buyer requirements · commercial leads · provider routing           │
│ future rental / purchase / lease / RaaS workflows                  │
├─────────────────────────────────────────────────────────────────────┤
│ 3. DECISION                                                        │
│ search · filters · compare · deterministic matching · explanations │
├─────────────────────────────────────────────────────────────────────┤
│ 2. CANONICAL KNOWLEDGE                                             │
│ robots · manufacturers · variants · specs · capabilities · offers  │
│ deployments · use cases · regions · providers · evidence · imagery │
├─────────────────────────────────────────────────────────────────────┤
│ 1. DISCOVERY / ACQUISITION                                         │
│ candidate identities · candidate claims · commercial signals       │
│ evidence excerpts · source eligibility · governed promotion        │
└─────────────────────────────────────────────────────────────────────┘
```

These are **logical boundaries inside a modular monolith**, not separate microservices.

---

# 4. Technology and runtime architecture

The frozen implementation stack remains:

```text
Frontend        Next.js + TypeScript, App Router
Backend API     FastAPI, Python 3.12+
ORM             SQLAlchemy 2.x
Validation      Pydantic v2
Database        PostgreSQL 14+
Search          PostgreSQL full-text + GIN/trigram + structured filters
Matching        Deterministic pure-Python scoring
Testing         pytest + Vitest/RTL + Playwright
Admin/Ops       Internal governed FastAPI/SQLAdmin surfaces
Migrations      SQL-first; db/schema.sql remains canonical
```

## 4.1 Runtime topology

```text
                                 INTERNET
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ CDN / EDGE / TLS    │
                         │ deployment concern  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   NEXT.JS WEB       │
                         │ apps/web            │
                         │                     │
                         │ SSR / HTML           │
                         │ navigation           │
                         │ forms                │
                         │ interaction          │
                         │ structured markup    │
                         └──────────┬──────────┘
                                    │ HTTPS
                                    ▼
                         ┌─────────────────────┐
                         │    FASTAPI API      │
                         │ apps/api            │
                         │                     │
                         │ application rules   │
                         │ query services      │
                         │ matching            │
                         │ lead services       │
                         │ governed admin      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   POSTGRESQL        │
                         │ canonical DDL       │
                         │ db/schema.sql       │
                         └─────────────────────┘
```

### 4.2 Architectural choice: modular monolith

HumanoidOnline remains a **modular monolith** until demonstrated scale or operational requirements justify otherwise.

That means:

- one principal web application;
- one principal backend API application;
- one canonical PostgreSQL database;
- explicit internal modules and service boundaries;
- no service split merely because a domain has a name.

This is intentional.

### 4.3 Infrastructure that is not justified by default

Do not introduce by anticipation:

- Kubernetes;
- a microservice mesh;
- Kafka or another event bus;
- Elasticsearch / OpenSearch;
- a vector database;
- Redis as a mandatory dependency;
- a generic workflow engine;
- a separate data warehouse;
- a separate database per future vertical.

Any such addition requires a concrete need and separately reviewed architecture change.

---

# 5. Frontend architecture — `apps/web`

The frontend is the **presentation and interaction layer**, not the source of business truth.

Its responsibilities:

```text
routing
server-side rendering
semantic HTML
SEO surfaces
responsive presentation
navigation
catalogue interaction
comparison interaction
requirement wizard interaction
match-result presentation
lead-capture forms
accessibility
client-side UI state
```

It must not independently decide:

```text
commercial accessibility
canonical availability semantics
price truth
evidence confidence
image display eligibility
robot identity
match scores
promotion eligibility
provider routing truth
```

Rule:

> **Next.js renders. FastAPI/application services decide. PostgreSQL defines the model.**

## 5.1 Principal human surfaces

Phase 1–2 surfaces remain centered on:

```text
/
├── /robots
│   └── /robots/[slug]
├── /compare
├── /manufacturers
│   └── /manufacturers/[slug]
├── /use-cases
│   └── /use-cases/[slug]
├── /find-a-humanoid
└── /matches/[id]
```

Commercial lead capture is embedded in the governed Phase-2 journeys rather than implemented as a separate marketplace checkout.

## 5.2 Frontend component boundary

Expected reusable component families:

```text
ENTITY
RobotCard
RobotThumb
RobotSummary
ManufacturerCard
UseCaseCard

TRUTH / STATUS
CommercialStatusBadge
AvailabilityBadge
PricingSummary
EvidenceBadge
ImageUnavailable

DECISION
ComparisonTable
ComparisonMetric
FindHumanoidWizard
MatchCard
MatchExplanation

COMMERCIAL INTENT
CommercialLeadForm
Provider/availability presentation

SYSTEM
SiteNav
PageShell
Error/empty-state primitives
```

Components display already-resolved semantics. They must not invent their own truth rules.

---

# 6. Backend application architecture — `apps/api`

FastAPI is the **application policy boundary** between presentation and stored truth.

Conceptually the API/application layer is divided into bounded modules:

```text
Catalogue / Knowledge
├── robots
├── manufacturers
├── use_cases
├── regions
├── commercial offers
└── evidence

Decision
├── compare support
├── buyer requirements
└── matching

Transaction / Intent
├── commercial leads
└── provider routing

Governance / Operations
├── catalogue import / validation
├── discovery review
├── promotion
├── acquisition governance
└── internal admin
```

The modules may live in the same FastAPI process. The boundary is conceptual and testable, not a deployment split.

## 6.1 Service rule

Routers should translate HTTP into typed application calls.

Business policy belongs in:

- application/domain services;
- deterministic policies;
- database constraints/functions where the invariant is data-level.

Avoid burying policy in route handlers or UI code.

---

# 7. Canonical data architecture

`db/schema.sql` is the single canonical data definition.

The canonical platform is permanently divided into:

```text
A. KNOWLEDGE
B. DECISION
C. TRANSACTION
```

## 7.1 Knowledge layer

```text
Manufacturer
    │
    ├── Robot
    │    ├── Robot Variant
    │    ├── Specifications
    │    ├── Capabilities
    │    ├── Use-case Fits
    │    ├── Robot Images
    │    ├── Pricing Offers
    │    ├── Availability Offers
    │    ├── Deployments
    │    └── Evidence
    │
    └── linked Provider(s)

Provider
    ├── OEM
    ├── Distributor
    ├── Integrator
    ├── Rental Provider
    ├── Leasing Provider
    ├── RaaS Provider
    └── Service Provider
```

### 7.2 Robot identity is permanent

A named robot has one canonical identity.

Future verticals must never create:

```text
rent_robot
buy_robot
lease_robot
```

as competing identity systems.

Instead:

```text
robot
  ├── rental offers
  ├── purchase offers
  ├── lease offers
  └── RaaS offers
```

all reference the same canonical `robot.id`.

### 7.3 Manufacturer is not provider

A manufacturer answers:

> **Who makes the robot?**

A provider answers:

> **Who can commercially fulfil a transaction or service path?**

One OEM may be both, but the concepts stay separate.

This separation is load-bearing for Phase 3–5.

---

# 8. Three independent commercial dimensions

The following may never be collapsed into one `available` flag:

```text
DIMENSION 1               DIMENSION 2                DIMENSION 3
COMMERCIAL MATURITY       TRANSACTION AVAILABILITY   DEPLOYMENT EVIDENCE

ANNOUNCED                  PURCHASE                   pilots
DEVELOPMENT                RENTAL                     customer deployments
PROTOTYPE                  LEASE                      contract values
PILOT                      RAAS                       geographic evidence
EARLY_ACCESS               DEVELOPER                  deployment records
COMMERCIAL                 ...
RAAS_DEPLOYMENT
DISCONTINUED
```

A robot may truthfully be:

```text
maturity:          RAAS_DEPLOYMENT
purchase:          no confirmed purchase offer
RaaS:              commercially accessible
deployments:       substantial
```

All three statements can be true simultaneously.

Architectural invariant:

> **maturity ≠ obtainability ≠ evidence**

---

# 9. Price and availability architecture

## 9.1 Price is an offer object

Never architect:

```text
robot.price = 16000
```

Authoritative pricing is contextual:

```text
robot
× variant
× provider
× transaction_type
× region
× price_type
× billing_period
× validity
× evidence
```

The robot-level lowest-purchase-price field, where present, is only a convenience/cache for sorting and presentation.

## 9.2 Availability is an offer object

Never architect:

```text
robot.available = true
```

Availability is contextual:

```text
robot
× variant
× provider
× transaction_type
× region
× availability_status
× validity
× evidence
```

Absence of a current availability offer means:

> **No confirmed commercial availability**

It does not mean:

> **Not available**

---

# 10. Evidence and provenance architecture

Evidence is part of the data model, not editorial decoration.

For material claims HumanoidOnline must be able to answer:

```text
WHAT is asserted?
ABOUT WHICH entity/field?
FROM WHICH source?
WHAT source class/type?
WHEN was it observed?
WHEN was it verified?
WITH WHAT confidence?
```

Architectural rule:

> **No commercial fact without evidence.**

This applies particularly to:

- price;
- availability;
- commercial maturity/status;
- deployments;
- regional commercial access;
- material commercial claims.

The public UI and machine projections may expose only provenance semantics authorized by their governing contracts.

---

# 11. UNKNOWN architecture

`UNKNOWN` is a first-class information state.

```text
UNKNOWN ≠ 0
UNKNOWN ≠ FALSE
UNKNOWN ≠ NOT_AVAILABLE
UNKNOWN ≠ SKIPPED
QUOTE_ONLY ≠ UNKNOWN
```

This is enforced across:

```text
database
API
matching
UI
discovery
machine projections
future transaction verticals
```

A missing fact must never be made more convenient by turning it into a negative fact.

---

# 12. Verified media architecture

Named robot imagery is governed by one permanent image-truth system.

```text
External image source
        │
        ▼
   robot_image
        │
        ├── exact model identity?
        ├── source/provenance?
        ├── rights evidence?
        ├── platform usage basis?
        ├── image type?
        └── primary?
        │
        ▼
Display-eligibility policy
        │
   ┌────┴────┐
   │         │
 DISPLAY   IMAGE_UNAVAILABLE
```

Three dimensions remain separate:

```text
identity_status
rights_status
usage_basis
```

A non-null image URL is never sufficient.

Hard rule:

> **No generated / reconstructed / look-alike identity image may represent a specific existing robot.**

The same canonical `robot_image` records feed:

```text
Catalogue
Robot Detail
Compare
Rent
Buy
Lease/RaaS
Machine projections where authorized
```

There is no second marketplace image system.

---

# 13. Discovery and acquisition architecture

Discovery is a **research and verification system**, not a second catalogue.

```text
EXTERNAL SOURCE
      │
      ▼
RADAR / MANUAL RESEARCH
      │
      ▼
DISCOVERY CANDIDATE
      │
      ▼
IDENTITY RESOLUTION
      │
      ▼
AUTHORITATIVE TRACE
      │
      ▼
CLAIM VERIFICATION
      │
      ▼
PROMOTION PROPOSAL
      │
      ▼
HUMAN PROMOTION GATE
      │
      ▼
CANONICAL KNOWLEDGE
```

## 13.1 Trust boundary

```text
NONCANONICAL                               CANONICAL

discovery_source                           manufacturer
discovery_candidate                        robot
candidate_claim                            specification
candidate image reference                  robot_image
candidate commercial signal       X        pricing_offer
evidence excerpt                           availability_offer
crawl/acquisition records                  deployment
                                           evidence_source
```

`X` means **no direct write path**.

The promotion service / governed importer is the boundary.

## 13.2 Competitors are radar, not truth

An aggregator or competitor may cause HumanoidOnline to investigate:

```text
a robot
a changed price
a changed status
a possible supplier
a possible deployment
a candidate specification
```

It does not automatically establish canonical truth.

## 13.3 No shadow database

The discovery layer stores only what is necessary to investigate:

- identity leads;
- source references;
- specific claims;
- evidence excerpts;
- provenance;
- workflow state.

It must not become a copied external catalogue.

## 13.4 Identity before facts

Candidate facts cannot safely attach to canonical identity until identity is resolved.

Ambiguity:

```text
possible duplicate
model-generation uncertainty
alias uncertainty
manufacturer mismatch
```

routes to review, never silent auto-merge.

## 13.5 Conflicts are preserved

If sources say:

```text
Source A → 20 kg
Source B → 25 kg
Source C → 30 kg
```

HumanoidOnline stores the conflict as distinct evidence/claims.

It does not:

```text
average → 25 kg
majority-vote → "truth"
```

without an already-ratified deterministic rule.

---

# 14. Acquisition execution boundary

Outbound external acquisition must remain separated from the public request path.

Preferred conceptual topology:

```text
PUBLIC USER REQUEST PATH

browser
  → Next.js
  → FastAPI public read/write services
  → canonical PostgreSQL


GOVERNED ACQUISITION PATH

named operator / separately authorized job
  → source eligibility / policy gate
  → bounded acquisition adapter or manual bootstrap
  → discovery/acquisition tables
  → review
  → promotion service
  → canonical PostgreSQL
```

The public web request path must not opportunistically crawl third-party sites.

A page request for `/robots/unitree-g1` reads HumanoidOnline's governed data. It does not fetch Unitree in real time.

---

# 15. Decision architecture

The Decision layer turns structured market truth into buyer utility.

```text
Canonical Robot Knowledge
          │
          ├── Search / Filters
          ├── Compare
          └── Matching
                   │
                   ▼
             Buyer Requirement
                   │
                   ▼
         Deterministic Scoring
                   │
                   ▼
            Match Results
                   │
             ┌─────┴─────┐
             ▼           ▼
          Reasons      Warnings
             │           │
             └─────┬─────┘
                   ▼
          Explainable shortlist
```

## 15.1 Matching engine boundary

Matching is:

- deterministic;
- pure;
- independently testable;
- no I/O in the scoring function;
- no randomness;
- no LLM in the scoring path.

Same valid input:

```text
→ same candidates
→ same eliminations
→ same scores
→ same ranks
→ same explanations
```

LLMs may be considered in separately governed non-scoring support roles, but not as a hidden replacement for the ratified deterministic scorer.

## 15.2 Compare is not matching

Comparison may highlight objective per-metric differences.

It must not silently introduce a new global robot score.

```text
COMPARE = facts beside facts
MATCH   = requirement-specific governed scoring
```

---

# 16. Buyer-intent architecture

The permanent conversion spine is:

```text
Visitor
   │
   ▼
Find a Humanoid
   │
   ▼
buyer_requirement
   │
   ▼
match_result[]
   │
   ▼
Commercial action
   │
   ▼
commercial_lead
   │
   ├── commercial_lead_robot[]
   └── commercial_lead_provider[]
```

`buyer_requirement` is not disposable form state. It is a permanent Decision-layer object that also becomes proprietary demand intelligence.

Important early signal:

```text
preferred_transaction
  UNKNOWN
  RENT
  BUY
  LEASE
  RAAS
  FLEXIBLE
```

Capturing preference in Phase 2 does **not** imply that the corresponding transaction product is already active.

---

# 17. Commercial lead architecture

For Phase 1–2, the platform's commercial action is:

> **qualified introduction / commercial lead routing**

not transaction custody.

```text
Buyer
  │
  ▼
commercial_lead
  │
  ├── requirement snapshot
  ├── selected/matched robots
  ├── organisation
  ├── geography
  ├── budget
  ├── timeline
  └── preferred transaction
  │
  ▼
Provider routing
  │
  ├── OEM
  ├── distributor
  ├── integrator
  └── other eligible provider
```

The same lead object survives future phases.

```text
Phase 2   qualified inquiry
            ↓
Phase 3   rental opportunity
            ↓
Phase 4   purchase opportunity
            ↓
Phase 5   lease / RaaS opportunity
```

No replacement CRM-shaped domain object should be created merely because a new vertical launches.

---

# 18. Machine and agent projection architecture

HumanoidOnline supports human and machine consumers from the same governed model.

```text
                         CANONICAL GOVERNED MODEL
                                   │
                             projection layer
                 ┌─────────────────┼─────────────────┐
                 │                 │                 │
                 ▼                 ▼                 ▼
             Human UI         Search/SEO         LLM / agent
           semantic HTML       JSON-LD           read surfaces
```

Permanent rules:

- machine surfaces are **projections**, never a second source of truth;
- published canonical entities only;
- discovery candidates stay excluded;
- `UNKNOWN` remains explicit/omitted, never fabricated;
- canonical provenance semantics are preserved where authorized;
- machine surfaces cannot promote a candidate by exposing it as if canonical;
- future transactional agent actions must call governed typed services, not screen-scrape the UI.

## 18.1 Future MCP / agent interfaces

A future MCP or procurement-agent layer, if ratified, should conceptually be:

```text
Agent
  │
  ▼
Governed typed action API / MCP projection
  │
  ▼
Existing application services
  │
  ▼
Canonical rules + database
```

Never:

```text
Agent
  → direct database write
```

and never:

```text
Agent API
  → independent robot truth store
```

---

# 19. API architecture

The API is organized by capability, not by future domain brand.

Conceptual public service groups:

```text
KNOWLEDGE
/api/robots
/api/manufacturers
/api/use-cases
/api/regions
commercial/evidence projections

DECISION
buyer requirements
matches
comparison-support reads

TRANSACTION / INTENT
commercial leads
governed provider routing
```

Internal/operator capabilities remain distinct from public product APIs.

Conceptually:

```text
PUBLIC
canonical published reads
buyer-requirement writes
commercial-lead writes

INTERNAL / GOVERNED
discovery review
source/acquisition governance
promotion
catalogue import
admin triage
```

Exact endpoint shapes remain governed by `docs/04_API_CONTRACT.md` and later ratified API amendments.

---

# 20. Write-authority matrix

| Component | Canonical reads | Canonical writes | Discovery reads | Discovery writes |
|---|---:|---:|---:|---:|
| Public Next.js UI | through API | no direct DB writes | no | no |
| Public FastAPI read services | yes | no | no | no |
| Buyer requirement service | required supporting reads | Decision-layer only | no | no |
| Matching engine | receives governed input | `match_result` through service | no | no |
| Commercial lead service | yes | Transaction-layer lead records | no | no |
| Discovery acquisition | limited identity/canonical resolution reads | **no** | yes | yes |
| Discovery review | limited governed reads | **no direct canonical write** | yes | workflow/review writes |
| Promotion service/importer | yes | **yes, gated** | yes | promotion/audit state |
| Internal admin | according to explicit view permissions | only explicitly authorized records | according to permissions | according to governed paths |
| Machine projections | yes, published only | no | no | no |
| Future vertical UI | through shared API/services | through shared governed services | no | no |

Hard law:

> **No frontend, crawler, projection, or external agent writes canonical robot truth directly.**

---

# 21. Trust boundaries

HumanoidOnline has four principal trust zones.

```text
┌───────────────────────────────────────────────────────────────┐
│ ZONE 1 — EXTERNAL / UNTRUSTED                                │
│ internet sources · browser input · candidate claims          │
└──────────────────────────────┬────────────────────────────────┘
                               │ validation / governance
                               ▼
┌───────────────────────────────────────────────────────────────┐
│ ZONE 2 — NONCANONICAL RESEARCH                               │
│ discovery candidates · acquisition records · excerpts        │
└──────────────────────────────┬────────────────────────────────┘
                               │ human + deterministic gates
                               ▼
┌───────────────────────────────────────────────────────────────┐
│ ZONE 3 — CANONICAL GOVERNED MODEL                            │
│ published/unpublished canonical entities · evidence · media  │
└──────────────────────────────┬────────────────────────────────┘
                               │ governed projections/services
                               ▼
┌───────────────────────────────────────────────────────────────┐
│ ZONE 4 — PUBLIC / COMMERCIAL PROJECTION                      │
│ website · API · structured data · later verticals            │
└───────────────────────────────────────────────────────────────┘
```

Moving data from Zone 1/2 into Zone 3 requires more authority than displaying Zone-3 data in Zone 4.

---

# 22. Publication boundary

Canonical does not automatically mean public.

The architecture recognizes:

```text
discovered
    ↓
verified/promoted canonical
    ↓
published canonical
    ↓
public human + machine projection
```

A promoted but unpublished robot remains excluded from public catalogue and machine-readable canonical surfaces until publication is explicitly permitted.

This prevents the promotion mechanism from becoming an accidental publication mechanism.

---

# 23. Internal operations architecture

Operational/admin surfaces are tools for governance, not alternate business logic.

They may support:

- source registry inspection;
- discovery queue review;
- lead triage;
- evidence inspection;
- catalogue validation;
- publication inspection;
- promotion/audit review.

Internal admin must not become a bypass around domain services or database constraints.

Where a workflow has a governed state machine, a generic CRUD screen must not be allowed to forge a later state by editing internal fields directly.

---

# 24. Phase activation architecture

The data model is already shaped so later commercial phases are activated by **workflow and UI exposure**, not by replacing the platform.

## 24.1 Phase 1 — Intelligence

Active platform capabilities:

```text
robot catalogue
manufacturer intelligence
specifications
capabilities
use cases
commercial maturity
pricing evidence
availability evidence
deployment evidence
verified imagery
search
compare
```

Principal value:

> **What exists, what can it do, and what is commercially true?**

## 24.2 Phase 2 — Buyer Intent

Adds:

```text
buyer requirements
deterministic matching
explainable recommendations
transaction preference
commercial lead capture
provider routing
demand analytics
```

Principal value:

> **Which humanoid fits this buyer and what does the buyer intend to do?**

## 24.3 Phase 3 — Rent

Future activation:

```text
transaction_type = RENTAL / SUBSCRIPTION
rental-specific offer discovery
rental availability UX
rental provider participation
rental lead/workflow extensions
RentHumanoid experience
```

Must reuse:

```text
robot identity
manufacturer
provider
region
pricing_offer
availability_offer
evidence
buyer_requirement
match_result
commercial_lead
robot_image
analytics
```

## 24.4 Phase 4 — Buy

Future activation:

```text
transaction_type = PURCHASE / DEVELOPER
purchase offer UX
seller/provider participation
HumanoidMart experience
```

Again, this is the same robot and commercial model.

## 24.5 Phase 5 — Lease / RaaS

Future activation:

```text
transaction_type = LEASE / RAAS
lease pricing
RaaS commercial structures
eligible providers
HumanoidLease experience
```

The model must continue to distinguish:

```text
lease
RaaS
purchase
rental
subscription
pilot
developer
```

rather than treating all access as “available”.

---

# 25. Future vertical topology

The target ecosystem is:

```text
                         ┌──────────────────────┐
                         │   HumanoidOnline     │
                         │ Intelligence Core    │
                         └──────────┬───────────┘
                                    │
                    shared API + shared services
                                    │
               ┌────────────────────┼────────────────────┐
               │                    │                    │
               ▼                    ▼                    ▼
       ┌──────────────┐     ┌──────────────┐     ┌───────────────┐
       │ RentHumanoid │     │ HumanoidMart │     │ HumanoidLease │
       │ RENT         │     │ BUY          │     │ LEASE / RAAS  │
       └──────┬───────┘     └──────┬───────┘     └───────┬───────┘
              │                    │                     │
              └────────────────────┼─────────────────────┘
                                   │
                                   ▼
                         ┌──────────────────────┐
                         │ Provider Network     │
                         │ OEMs / distributors │
                         │ integrators / RaaS   │
                         └──────────┬───────────┘
                                    │
                                    ▼
                                  BUYERS
```

### 25.1 One core, multiple experiences

A vertical may own:

- branding;
- landing pages;
- transaction-specific navigation;
- transaction-specific filtering;
- workflow steps specifically ratified for that phase.

A vertical may **not** independently own:

- robot identity;
- manufacturer identity;
- canonical specs;
- evidence;
- media truth;
- generic provider identity;
- duplicated pricing truth;
- duplicated availability truth;
- duplicated buyer requirements;
- duplicated matching logic;
- duplicated lead identity.

---

# 26. Commercial neutrality architecture

HumanoidOnline's intelligence and matching must not become pay-to-rank infrastructure.

Commercial relationships may affect:

```text
whether a provider can receive a routed lead
how a referral is tracked
how HumanoidOnline is compensated
```

They must not silently alter:

```text
canonical facts
match scores
robot ranking
evidence confidence
commercial maturity
availability truth
```

Matching and intelligence are product truth. Monetization is a separate concern.

---

# 27. Analytics architecture

The v0.1 architecture uses the existing lightweight `event_log` model rather than introducing a separate analytics platform by default.

Events may describe product interactions such as:

```text
robot_view
compare
match_run
lead_capture
```

Analytics must not become a source of canonical robot truth.

Future warehouse/BI architecture may be added only when justified by concrete scale or business requirements.

---

# 28. Search architecture

Search remains PostgreSQL-based for MVP architecture:

```text
robot.search_vector
GIN full-text index
trigram indexes
structured relational filters
```

Do not introduce an external search engine merely for theoretical future scale.

A later search-service decision requires evidence that PostgreSQL no longer meets measured requirements.

---

# 29. Deployment evolution

## 29.1 Initial production shape

```text
DNS / TLS / CDN
       │
       ▼
Next.js web
       │
       ▼
FastAPI
       │
       ▼
PostgreSQL
```

External acquisition remains operator/job driven and policy-gated, outside user requests.

## 29.2 Scale-triggered additions

Possible future additions include:

```text
object storage / CDN for governed assets
background job worker
queue
cache
read replicas
dedicated analytics storage
external search
```

but only when triggered by a demonstrated requirement.

The architecture is intentionally designed so these can be added without changing canonical domain semantics.

---

# 30. Failure-mode architecture

The system must fail **closed and honestly** at trust boundaries.

Examples:

```text
No verified price
→ "No confirmed pricing"
NOT → $0

No current availability record
→ "No confirmed commercial availability"
NOT → Unavailable

No display-eligible robot image
→ IMAGE_UNAVAILABLE
NOT → generated substitute

Ambiguous robot identity
→ review / POSSIBLE_DUPLICATE
NOT → auto-merge

Conflicting claims
→ conflict retained
NOT → averaged fact

Discovery source cannot be safely used
→ acquisition blocked
NOT → fetch anyway

Promoted but unpublished canonical record
→ excluded from public projection
NOT → auto-publication
```

---

# 31. Security and policy boundaries

This architecture does not prescribe a new security product, but establishes these boundaries:

1. public users cannot access discovery-layer internals;
2. public API services do not expose noncanonical discovery candidates;
3. internal admin capabilities are explicitly permissioned;
4. acquisition authorization is separate from public application traffic;
5. third-party source policy/eligibility gates are checked before governed automated acquisition;
6. canonical mutation paths remain narrow and auditable;
7. agent/machine read surfaces are read-only unless a later typed-action contract explicitly authorizes writes/actions.

---

# 32. Testing architecture

Every architecture boundary must be testable.

## 32.1 Unit/policy tests

Use for:

```text
matching
availability policy
pricing semantics
image display eligibility
identity logic
promotion gates
provider routing
UNKNOWN semantics
```

## 32.2 API tests

Prove:

```text
request/response shapes
published-only public reads
write validation
no candidate leakage
lead persistence
requirement persistence
```

## 32.3 Integration / database tests

Prove:

```text
DDL constraints
migration convergence
provenance integrity
canonical/discovery isolation
offer uniqueness
append-only/audit invariants where applicable
```

## 32.4 End-to-end tests

Prove critical human journeys:

```text
explore → robot → compare
find a humanoid → requirement → matches
matches/detail → commercial lead
verified imagery / IMAGE_UNAVAILABLE
production public surfaces exclude internal discovery
```

No workstream is complete only because its happy-path UI renders.

---

# 33. Coding-agent implementation rules derived from this architecture

Claude, Fable, Codex, or any implementation agent must apply the following rules.

### SA-01 — Canonical DDL wins

Never modify ORM/API/UI semantics to contradict `db/schema.sql`.

### SA-02 — Respect document authority

This document integrates the architecture. It does not grant permission to change a frozen contract.

### SA-03 — Keep the modular monolith

Do not create a new service because a feature has a separate product name.

### SA-04 — Keep business logic below UI

Frontend components render policy outcomes; they do not invent them.

### SA-05 — Discovery cannot write canonical truth directly

All canonical mutation from discovery passes the governed promotion path.

### SA-06 — One identity system

Do not duplicate robot/manufacturer/provider identities for Rent, Buy, Lease, agent, media, or discovery surfaces.

### SA-07 — One evidence system

Do not create a second “marketplace evidence” or “agent evidence” model.

### SA-08 — One media truth system

No vertical-specific robot image database.

### SA-09 — Preserve independent commercial axes

Never replace maturity + availability + deployment with one availability boolean.

### SA-10 — Preserve contextual commerce

Price and availability remain transaction/provider/region/variant-aware offer records.

### SA-11 — Preserve deterministic decision logic

No LLM/random scoring shortcut.

### SA-12 — Keep UNKNOWN honest

Never infer a negative state merely because data is absent.

### SA-13 — Future structures are not dead code

Do not remove Phase 3–5 structures because they are dormant.

### SA-14 — No speculative infrastructure

Do not add services “for scale later” without a ratified requirement.

### SA-15 — Every boundary lands with tests

A boundary without an adversarial test is not considered protected.

---

# 34. Architecture acceptance gates

This system architecture is satisfied only while all of the following remain true.

### A — Single canonical database model

There is one canonical humanoid domain schema, owned by `db/schema.sql`.

### B — Single robot identity

Rent/Buy/Lease and machine projections reference the canonical robot, not copied entities.

### C — Canonical/discovery isolation

No noncanonical candidate can surface as canonical before the promotion gate.

### D — Human promotion boundary

No discovery/acquisition automation may auto-promote canonical truth in the current governed model.

### E — Evidence preservation

Commercial truth remains evidence-linked.

### F — UNKNOWN preservation

Absence never becomes zero/false/not-available.

### G — Commercial-axis separation

Maturity, availability, and deployment evidence remain independent.

### H — Offer contextuality

Price and availability remain transaction/provider/region aware.

### I — Deterministic matching

Matching remains reproducible and independently testable.

### J — Media truth

A named real robot is represented only by governed exact-model identity imagery or `IMAGE_UNAVAILABLE`.

### K — Projection-only machine access

Machine-readable surfaces derive from governed canonical data and do not create a second truth store.

### L — Published-only public canonical projection

Canonical-but-unpublished entities do not leak to public human or machine surfaces.

### M — No premature transaction custody

Phase 1–2 remains introduction/lead oriented unless a later phase is separately activated.

### N — No independent vertical stack

RentHumanoid, HumanoidMart, and HumanoidLease remain clients/experiences over shared platform services.

### O — No speculative distributed architecture

No microservice/event/search/vector infrastructure is added without demonstrated need and approval.

---

# 35. Current vs dormant vs future capability map

| Capability | Phase 1–2 role | Phase 3–5 role |
|---|---|---|
| Canonical robot identity | Active | Reused unchanged |
| Manufacturer model | Active | Reused unchanged |
| Provider model | Present / routing | Becomes increasingly active |
| Evidence | Active | Reused unchanged |
| Verified robot media | Active | Reused unchanged |
| Pricing offers | Intelligence | Transaction-specific display/workflows |
| Availability offers | Intelligence | Transaction-specific display/workflows |
| Use cases | Active | Reused for commercial discovery |
| Compare | Active | Reused |
| Buyer requirement | Active | Reused |
| Deterministic matching | Active | Reused / extended only by contract |
| Commercial lead | Active | Survives as opportunity object |
| Provider routing | Active bounded form | Expanded |
| Rental workflow | Dormant | Phase 3 |
| Purchase workflow | Dormant | Phase 4 |
| Lease workflow | Dormant | Phase 5 |
| RaaS workflow | Dormant | Phase 5 |
| Payment / settlement | Not authorized | Separate future contract |
| MCP transactional actions | Not authorized | Separate future contract |

---

# 36. System architecture summary

The complete architecture can be reduced to this:

```text
                                   EXTERNAL SOURCES
                                         │
                               governed acquisition
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │ DISCOVERY / RADAR   │
                              │ noncanonical        │
                              └──────────┬──────────┘
                                         │
                               verify + human gate
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          HUMANOIDONLINE CORE                                 │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ CANONICAL KNOWLEDGE                                                    │  │
│  │ robots · manufacturers · specs · capabilities · use cases · providers │  │
│  │ prices · availability · deployments · evidence · verified media       │  │
│  └───────────────────────────────┬────────────────────────────────────────┘  │
│                                  │                                           │
│                                  ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ DECISION                                                               │  │
│  │ search · filters · compare · buyer requirements · deterministic match │  │
│  └───────────────────────────────┬────────────────────────────────────────┘  │
│                                  │                                           │
│                                  ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ TRANSACTION / INTENT                                                   │  │
│  │ commercial leads · provider routing · future governed transactions    │  │
│  └───────────────────────────────┬────────────────────────────────────────┘  │
└──────────────────────────────────┼───────────────────────────────────────────┘
                                   │
                         shared governed services
                                   │
               ┌───────────────────┼───────────────────┐
               │                   │                   │
               ▼                   ▼                   ▼
        HUMANOIDONLINE        RENTHUMANOID        HUMANOIDMART
        Intelligence          Phase 3 Rent         Phase 4 Buy
               │
               └──────────────────────────┐
                                          ▼
                                  HUMANOIDLEASE
                                  Phase 5 Lease/RaaS
```

The defining architectural sentence is:

> **HumanoidOnline owns the canonical humanoid-market graph and commercial decision core; every current and future human, machine, rental, purchase, lease, and RaaS experience is a governed projection or workflow over that same core — never an independent source of truth.**

---

# 37. Ratification

**Current status:** PROPOSED.

Creating this document does not itself amend any frozen contract or authorize new implementation.

If the product owner ratifies this document, the intended effect is:

- freeze the cross-system topology and boundaries described here;
- preserve the existing higher-authority contracts;
- give implementation agents one architectural map across HumanoidOnline, DATA-D1, MEDIA-01, AGENT-01 and Phases 1–5;
- require an explicit owner-approved amendment before violating an architecture acceptance gate in §34.

Suggested ratification statement:

> **SYSTEM ARCHITECTURE v0.1 is RATIFIED.** `docs/18_SYSTEM_ARCHITECTURE.md` becomes the governing cross-system integration architecture for HumanoidOnline, subordinate to `db/schema.sql` and existing frozen/specialized contracts. It freezes the modular-monolith topology, canonical/discovery boundary, Knowledge → Decision → Transaction layering, shared identity/evidence/media systems, deterministic decision boundary, published-canonical projection boundary, and one-core/multiple-verticals model. Ratification does not activate Rent, Buy, Lease/RaaS, crawling, transactional MCP/actions, payment, or new infrastructure; each remains separately governed.

