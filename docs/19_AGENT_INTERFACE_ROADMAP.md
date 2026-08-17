# HumanoidOnline Agent Interface Development Overview
## AGENT-01 → AGENT-04 Roadmap

**Document status:** DRAFT — development overview for product-owner review  
**Project:** HumanoidOnline / Humanoid Company  
**Date:** 2026-08-17  
**Intended repository location:** `docs/19_AGENT_INTERFACE_ROADMAP.md`

---

## 1. Purpose

HumanoidOnline is being designed not only as a human-facing humanoid robotics catalogue, but as a governed machine-readable and eventually machine-actionable commercial intelligence platform.

The agent roadmap is split into four progressive layers:

| Layer | Name | Primary purpose | Status |
|---|---|---|---|
| **AGENT-01** | Discover & Understand | Let search engines, LLMs and AI systems discover, interpret and cite HumanoidOnline correctly | **Ratified / implemented foundation** |
| **AGENT-02** | Query & Decide | Give connected AI agents explicit governed read/query tools over the same canonical catalogue and decision logic | **Next development stream** |
| **AGENT-03** | Act | Let authenticated agents submit buyer requirements, request quotes/availability and create governed commercial leads | **Planned** |
| **AGENT-04** | Transact | Support agent-mediated Buy / Rent / Lease / RaaS transactions through standard commerce/payment protocols | **Future** |

The four layers are cumulative. AGENT-02 does not replace AGENT-01; AGENT-03 does not replace AGENT-02. Human users, search/LLM systems, connected agents and later transactional agents must all project the same governed HumanoidOnline truth.

---

## 2. Core Architectural Principle

> **The agent interface is a governed capability layer over HumanoidOnline's existing service/read/action architecture. MCP, UCP, ACP or any later protocol is an adapter — never an independent business-logic path.**

HumanoidOnline must not develop separate interpretations of robot status, availability, price, evidence, publication state or uncertainty for different consumers.

```text
                    CANONICAL HUMANOIDONLINE TRUTH
                               │
                     GOVERNED SERVICE LAYER
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
       HUMAN UI             AGENT-01             AGENT-02
      Next.js UI        Web / SEO / LLM             MCP
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
                     SAME READ / DECISION LOGIC
                               │
                  Catalogue / Matching / Evidence
                               │
                            Postgres
```

Later, governed write/action capabilities are added below the same boundary:

```text
                         AGENT-03
                    GOVERNED COMMERCIAL ACT
                              │
               submit_requirement / request_quote
               request_availability / create_lead
                              │
                    GOVERNED ACTION LAYER
                              │
                   Audit / Auth / Idempotency
```

And only after the transaction phases are commercially ready:

```text
                         AGENT-04
                    TRANSACTION PROTOCOLS
                              │
                     UCP / ACP / equivalent
                              │
                     Commerce Adapter Layer
                              │
                   Buy / Rent / Lease / RaaS
```

---

# 3. AGENT-01 — Discover & Understand

## 3.1 Mission

AGENT-01 makes HumanoidOnline understandable to machines without requiring a special agent connection.

Its purpose is:

> An AI/search/LLM system should be able to discover a canonical HumanoidOnline entity, understand what the page represents, extract trustworthy structured facts, distinguish uncertainty from negative claims, and cite the canonical source.

AGENT-01 is primarily a **public discovery and semantic-readability contract**.

## 3.2 Current surfaces

The AGENT-01 foundation includes or is designed around:

| Surface | Purpose |
|---|---|
| `robots.txt` | Public crawler/discovery policy |
| `sitemap.xml` | Stable discovery of published canonical entities |
| `llms.txt` | Machine-oriented explanation of HumanoidOnline and its semantics |
| Server-rendered semantic HTML | Human + machine-readable canonical entity pages |
| JSON-LD / schema.org | Structured entity representation |
| Stable canonical robot/manufacturer/use-case URLs | Durable identity |
| Governed public API/read models | Structured retrieval from the same underlying truth |

## 3.3 AGENT-01 laws

AGENT-01 must preserve the following rules:

**Published-canonical-only.** Public agent/discovery surfaces must never leak unpublished or discovery-review records.

**Semantic parity.** Human UI, structured data and public machine-readable projections must describe the same canonical robot truth.

**Explicit uncertainty.** `UNKNOWN` or `NULL` must remain unknown. It must never silently become `0`, `false`, unavailable, unsupported or another asserted value.

**Maturity ≠ availability.** Commercial maturity and current obtainability are independent dimensions.

**Evidence ≠ commercial status.** Evidence supports claims; it is not itself equivalent to maturity or availability.

**Provenance preservation.** Evidence, source, confidence and timestamps must remain attributable when surfaced.

**Canonical identity.** One canonical robot/manufacturer identity must underlie all projections.

## 3.4 What AGENT-01 does not provide

AGENT-01 does not expose explicit callable agent functions such as:

```text
search_robots(...)
compare_robots(...)
match_robots(...)
request_quote(...)
```

An LLM may discover and reason over public pages/read endpoints, but HumanoidOnline has not yet exposed a formal machine capability interface for queries or actions.

That is the boundary between AGENT-01 and AGENT-02.

---

# 4. AGENT-02 — Query & Decide

## 4.1 Mission

AGENT-02 turns HumanoidOnline's governed catalogue and decision logic into explicit machine-callable tools.

Example agent request:

> Find humanoids available for purchase in Europe, below €30,000, with SDK access.

The agent should not have to scrape pages and independently decide what `COMMERCIAL`, `UNKNOWN`, availability, provider or evidence mean. HumanoidOnline should perform that interpretation through its own governed logic.

## 4.2 Initial read-only tool set

The first AGENT-02 implementation should expose a small, stable read-only capability surface:

| Tool | Purpose |
|---|---|
| `search_robots` | Search/filter published canonical humanoids |
| `get_robot` | Retrieve one canonical robot profile |
| `compare_robots` | Compare selected robots using governed comparison fields |
| `get_manufacturer` | Retrieve canonical manufacturer information |
| `get_current_offers` | Retrieve current governed pricing/commercial offers |
| `get_availability` | Retrieve transaction- and region-specific availability |
| `get_evidence` | Retrieve evidence/provenance behind published claims |
| `match_robots` | Execute the existing governed buyer-matching logic |

Additional tools should be added only when a clear capability contract exists.

## 4.3 MCP placement

MCP is the first intended protocol adapter for AGENT-02.

```text
AI AGENT
   │
   ▼
MCP SERVER / ADAPTER
   │
   ▼
GOVERNED HUMANOIDONLINE SERVICE / READ LAYER
   │
   ├── catalogue reads
   ├── evidence reads
   ├── offers / availability reads
   └── matching engine
```

### Critical rule

> **The MCP server must not query PostgreSQL as an independent data-access implementation when the equivalent governed service/read path already exists.**

The MCP layer should call the same application services used by the website/API so that semantics cannot drift.

## 4.4 Required response semantics

AGENT-02 results must preserve:

| Field / concept | Required behavior |
|---|---|
| `UNKNOWN` | Remains explicitly unknown |
| Commercial maturity | Independent from availability |
| Availability | Scoped to transaction type / provider / region where applicable |
| Provider | Preserved rather than collapsed |
| Price | Preserved as offer data, never a single invented robot price |
| Evidence | Source, confidence, timestamps and subject relationship preserved |
| Canonical URL | Returned when a public canonical entity page exists |
| Publication state | Only published canonical records visible externally |
| Missing fact | Omitted/UNKNOWN, never synthesized |
| Evidence timestamp | Exposed when relevant to freshness decisions |

## 4.5 Example

Conceptual call:

```text
search_robots(
    region="EU",
    transaction_type="PURCHASE",
    max_price_eur=30000,
    has_sdk=true
)
```

HumanoidOnline, not the calling model, must apply the platform's semantics.

For example:

- `COMMERCIAL` does not automatically mean `AVAILABLE`.
- `UNKNOWN` SDK support does not automatically mean `false`.
- A missing price does not become `0`.
- An unpublished robot must never appear.
- Region-specific offers must not be generalized globally.
- An evidence-backed offer must remain linked to its provider/source.

## 4.6 AGENT-02 non-goals

AGENT-02 v0.1 should be **read-only**.

It should not:

- create leads,
- send RFQs,
- request quotes,
- modify user/customer data,
- change catalogue records,
- change publication state,
- place orders,
- execute payments.

Those belong to AGENT-03 and AGENT-04.

## 4.7 AGENT-02 acceptance direction

AGENT-02 should be considered ready only when:

1. All tools resolve through governed service/read paths.
2. No tool leaks unpublished/discovery records.
3. `UNKNOWN` is preserved end-to-end.
4. Maturity and availability cannot be accidentally collapsed.
5. Evidence/provenance remain retrievable.
6. Tool schemas are typed and versioned.
7. Errors are deterministic and machine-readable.
8. The same query produces semantically consistent results between UI/API/MCP.
9. Tool output includes canonical entity identifiers/URLs where appropriate.
10. Automated tests cover publication, uncertainty, evidence and filter boundaries.

---

# 5. AGENT-03 — Governed Commercial Actions

## 5.1 Mission

AGENT-03 moves HumanoidOnline from agent-readable intelligence to controlled commercial action.

The goal is not immediate autonomous purchasing. The first commercial value is enabling an enterprise/procurement agent to convert researched buyer intent into a qualified commercial interaction.

Conceptual flow:

```text
ENTERPRISE / PROCUREMENT AGENT
             │
             ▼
       HumanoidOnline MCP
             │
       search / compare
       evidence / match
             │
             ▼
     submit_buyer_requirement
     request_availability
     request_quote
     create_commercial_lead
             │
             ▼
      HumanoidOnline lead
             │
             ▼
 OEM / distributor / integrator
             │
             ▼
 attribution / commission opportunity
```

This aligns directly with HumanoidOnline's intended low-inventory commercial model.

## 5.2 Candidate AGENT-03 tools

| Tool | Purpose |
|---|---|
| `submit_buyer_requirement` | Create a structured governed buyer requirement |
| `request_availability` | Ask for current availability for a robot/region/transaction mode |
| `request_quote` | Initiate a quote request against a provider/offer context |
| `create_commercial_lead` | Create an attributable qualified lead |
| `get_lead_status` | Let an authorized agent inspect progression of its own lead/request |

The exact tool list must be ratified in a separate Agent Action Contract before implementation.

## 5.3 Required governance for write actions

AGENT-03 must introduce stronger controls than AGENT-02.

Every consequential action should support:

| Control | Requirement |
|---|---|
| Authentication | Agent/user/customer identity must be known where required |
| Authorization | Explicit scopes per action |
| Idempotency | Repeated calls must not accidentally duplicate leads/RFQs |
| Request identity | Durable request/action IDs |
| Audit trail | Immutable or append-only action/event evidence |
| Consent | Contact and personal-data use must be authorized |
| Rate limits | Prevent spam, abuse and runaway agent loops |
| Replay protection | Prevent unintended repeated execution |
| Deterministic failure states | Agents must know whether an action executed |
| Human confirmation | Required for actions above defined consequence thresholds |
| Attribution | Commercial source/agent/referral path preserved |

## 5.4 Human-in-the-loop principle

HumanoidOnline should distinguish among:

```text
READ
→ agent may execute automatically

PROPOSE / PREPARE
→ agent may prepare a commercial action

SUBMIT LOW-RISK INTENT
→ agent may submit where authorized

CONSEQUENTIAL COMMITMENT
→ explicit human/customer confirmation required unless a later contract
  deliberately authorizes autonomous execution
```

The exact boundaries must be ratified before AGENT-03 writes are enabled.

## 5.5 AGENT-03 commercial opportunity

AGENT-03 may become a stronger near-term differentiator than autonomous checkout.

A procurement agent that can:

1. determine requirements,
2. search HumanoidOnline,
3. compare candidates,
4. inspect evidence,
5. identify current provider/availability,
6. submit a structured RFQ or lead,

already creates commercial value.

HumanoidOnline can therefore monetize **qualified agent-generated buyer intent** before operating inventory or payment infrastructure.

---

# 6. AGENT-04 — Transactional Agent Commerce

## 6.1 Mission

AGENT-04 enables agent-mediated transactions when HumanoidOnline activates the later commercial phases:

- Buy,
- Rent,
- Lease,
- RaaS,
- potentially subscription/pilot/developer modes.

AGENT-04 must remain separate from AGENT-03 because requesting a quote or creating a lead is materially different from committing funds or entering a contract.

## 6.2 Candidate capabilities

Future tools/capabilities may include:

```text
create_cart
create_checkout
reserve_robot
initiate_purchase
initiate_rental
initiate_lease
initiate_raas
complete_checkout
get_transaction_status
```

These names are placeholders until the transaction architecture is ratified.

## 6.3 Do not invent a proprietary commerce protocol

HumanoidOnline should not hard-wire its business model to MCP alone.

The intended architecture is:

```text
AGENT / AI COMMERCE CLIENT
          │
          ├── MCP binding
          ├── UCP
          ├── ACP
          └── later compatible protocol
                    │
                    ▼
             COMMERCE ADAPTER
                    │
                    ▼
      GOVERNED HUMANOIDONLINE COMMERCIAL LAYER
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
       Buy         Rent      Lease / RaaS
```

The platform's internal commercial objects and governance should remain stable even if protocol standards change.

## 6.4 AGENT-04 safety and approval

AGENT-04 requires stricter controls than AGENT-03, potentially including:

- strong customer and agent authentication,
- delegated spending authority,
- explicit transaction scopes,
- amount/quantity limits,
- human confirmation policies,
- durable idempotency,
- payment tokenization,
- fraud controls,
- legal entity and regional eligibility,
- quote/contract version binding,
- price/availability freshness checks,
- transaction audit evidence,
- cancellation/refund state,
- partner/provider settlement and attribution.

No autonomous purchase capability should be enabled merely because the protocol technically permits it.

---

# 7. Cross-Layer Laws

The following principles apply to AGENT-01 through AGENT-04.

## 7.1 One canonical truth

No agent layer owns a parallel catalogue.

All interfaces project from the same canonical robot/manufacturer/provider/offer/evidence model.

## 7.2 Publication is an editorial boundary

External agent interfaces may expose only records deliberately approved for publication.

Internal tracked records, discovery-review candidates and unpublished canonical records remain private to the appropriate internal workflow.

## 7.3 UNKNOWN remains UNKNOWN

HumanoidOnline now explicitly supports:

```text
commercial_status = UNKNOWN
```

Meaning:

> Current commercial maturity has not yet been verified.

It is not:

```text
ANNOUNCED
DEVELOPMENT
NOT_AVAILABLE
DISCONTINUED
false
0
```

The same principle applies across specifications, capabilities, availability and evidence-backed facts.

## 7.4 Maturity and obtainability remain separate

```text
COMMERCIAL MATURITY
≠
TRANSACTION AVAILABILITY
```

An agent must not infer that a `COMMERCIAL` robot is presently purchasable.

Availability must come from the correct availability/offer dimension.

## 7.5 Evidence follows assertions

An asserted commercial status, price, availability, deployment or other governed commercial fact must satisfy the existing evidence contracts.

`UNKNOWN` requires no fabricated evidence because it is the explicit absence of an asserted fact.

## 7.6 Protocol adapters cannot bypass governance

MCP, UCP, ACP, REST or any future protocol must call governed service/action logic rather than implement independent rules.

## 7.7 Human and agent parity

If an agent can perform an action, the underlying action must have the same validation, evidence and authorization semantics as the equivalent human/API path.

Protocol convenience must never create a lower-governance route.

---

# 8. Proposed Development Sequence

```text
CURRENT
│
├── Complete governed catalogue
│   ├── canonical robot records
│   ├── imagery/provenance
│   ├── evidence
│   ├── publication
│   ├── UNKNOWN semantics
│   └── maturity/availability separation
│
▼
AGENT-02 DESIGN PACKAGE
│
├── Agent Tool Contract v0.1   (docs/20 — RATIFIED)
└── Agent Interface Architecture
│
▼
AGENT-02 v0.1
│
├── MCP server/adapter
├── search_robots
├── get_robot
├── compare_robots
├── get_manufacturer
├── get_current_offers
├── get_availability
├── get_evidence
└── match_robots
│
▼
LIVE AGENT VALIDATION
│
├── ChatGPT / MCP-capable client
├── Claude / MCP-capable client
├── other compatible agents
└── semantic parity / evidence / UNKNOWN tests
│
▼
AGENT-03 v0.1
│
├── Agent Action Governance v0.1   (prerequisite for writes)
├── authentication / scopes
├── idempotency / audit
├── submit_buyer_requirement
├── request_availability
├── request_quote
├── create_commercial_lead
└── get_lead_status
│
▼
PARTNER / PROVIDER INTEGRATIONS
│
├── OEM
├── distributor
├── integrator
└── attribution / commission
│
▼
AGENT-04
│
├── commerce protocol adapter
├── UCP / ACP / compatible standards
├── Buy
├── Rent
├── Lease
└── RaaS
```

---

# 9. Documentation Package

This overview leads to three narrower contracts. They are **not** all
prerequisites for AGENT-02: only §9.2 governs read-only tools, and it is now
ratified as `docs/20_AGENT_TOOL_CONTRACT.md`. §9.3 governs writes and is an
**AGENT-03** prerequisite, not an AGENT-02 one.

## 9.1 Agent Interface Architecture

Defines:

- architectural boundaries,
- relationship to AGENT-01,
- MCP placement,
- service/read-layer reuse,
- identity and authorization model,
- versioning,
- error model,
- observability,
- publication/evidence boundaries,
- protocol adapter rules.

## 9.2 Agent Tool Contract v0.1 — RATIFIED as `docs/20_AGENT_TOOL_CONTRACT.md`

Ratified v0.1. It, not this overview, governs AGENT-02 read-only semantics;
where the two differ, `docs/20` wins. Defines every AGENT-02 tool:

- exact tool name,
- purpose,
- input schema,
- output schema,
- enum behavior,
- `UNKNOWN` behavior,
- evidence/provenance fields,
- canonical URLs,
- pagination,
- freshness,
- errors,
- examples,
- versioning/deprecation policy.

## 9.3 Agent Action Governance v0.1 — an AGENT-03 prerequisite, not an AGENT-02 one

AGENT-02 v0.1 is read-only and creates, mutates and authorizes nothing, so it
does not depend on this contract. AGENT-03 is the first write/action-capable
layer and may not be implemented until this is ratified. Defines AGENT-03 and
future AGENT-04 authorization boundaries:

- which actions are read-only,
- which actions may be proposed,
- which actions agents may submit directly,
- which require human confirmation,
- identity/scopes,
- idempotency,
- audit,
- privacy/consent,
- rate limits,
- transaction thresholds,
- failure/retry semantics.

No transactional/write tool should be implemented until this contract is ratified.

---

# 10. Suggested AGENT-02 Internal Architecture

A clean implementation should keep protocol-specific code thin.

```text
apps/
├── api/
│   └── existing governed API/service layer
│
├── agent/                       # illustrative location only
│   ├── mcp/
│   │   ├── server
│   │   ├── tool_registry
│   │   └── serializers
│   │
│   └── contracts/
│       ├── search_robots
│       ├── get_robot
│       ├── compare_robots
│       ├── get_evidence
│       └── match_robots
│
└── web/
    └── existing human/AGENT-01 projections
```

The exact repository location must be chosen after inspection of the current codebase. This document does not freeze a directory structure.

The invariant is more important than the folder:

> **MCP tooling delegates to the governed domain/read layer and does not become an alternate backend.**

---

# 11. AGENT-02 Example Contract Direction

A conceptual robot-search result should expose enough information for an agent to reason without reconstructing hidden assumptions:

```json
{
  "robot_id": "canonical-id",
  "slug": "unitree-g1",
  "name": "G1 Basic",
  "manufacturer": {
    "slug": "unitree",
    "name": "Unitree"
  },
  "commercial_status": "COMMERCIAL",
  "availability": [
    {
      "transaction_type": "PURCHASE",
      "region": "EU",
      "status": "AVAILABLE",
      "provider": "provider-id",
      "evidence_id": "evidence-id"
    }
  ],
  "offers": [
    {
      "transaction_type": "PURCHASE",
      "currency": "EUR",
      "amount": null,
      "price_type": "QUOTE_ONLY",
      "provider": "provider-id",
      "evidence_id": "evidence-id"
    }
  ],
  "specs": {
    "payload_kg": 2.0,
    "reach_cm": 45.0,
    "arm_span_cm": null
  },
  "canonical_url": "/robots/unitree-g1"
}
```

**Important:** the example above is structural only. Production tool output must never use an amount of `0` to mean an unknown price. Unknown numeric values must be `null`/absent according to the final contract. `QUOTE_ONLY` must be represented as its own price semantics, not as zero.

---

# 12. Observability and Audit

Agent interactions should be observable independently of protocol.

AGENT-02 read operations should minimally support:

- request/tool ID,
- tool name/version,
- timing,
- success/failure class,
- rate-limit events,
- no logging of unnecessary sensitive data.

AGENT-03/04 actions should additionally support:

- actor/customer/agent identity,
- authorization scope,
- idempotency key,
- canonical target entity,
- action payload digest,
- created commercial object ID,
- approval/confirmation state,
- immutable action chronology,
- downstream provider handoff,
- outcome/status.

The audit model should allow HumanoidOnline to answer:

> Which agent did what, for whom, against which evidence and commercial state, under which authorization, and what happened afterward?

---

# 13. Security Boundary

Read-only AGENT-02 can begin with a comparatively small attack surface, but it still requires:

- strict schema validation,
- output filtering,
- publication enforcement,
- rate limiting,
- bounded pagination,
- predictable resource limits,
- no arbitrary SQL,
- no arbitrary URL fetching,
- no arbitrary file access,
- no catalogue mutation.

AGENT-03/04 add:

- authentication,
- scoped authorization,
- replay/idempotency protection,
- anti-spam controls,
- human confirmation rules,
- privacy/consent handling,
- commercial abuse detection.

---

# 14. Relationship to HumanoidOnline Product Phases

The agent roadmap complements the existing commercial roadmap.

```text
HUMANOIDONLINE INTELLIGENCE
        │
        ├── AGENT-01 discovery
        └── AGENT-02 query/decision
        │
        ▼
BUYER INTENT
        │
        └── AGENT-03 requirements / RFQ / leads
        │
        ▼
RENT / BUY / LEASE / RAAS
        │
        └── AGENT-04 transaction protocols
```

This means agent development does not require HumanoidOnline to become a stock-holding retailer.

AGENT-03 can create commercial value by generating qualified, attributable demand for OEMs/distributors before AGENT-04 exists.

---

# 15. Competitive Intent

HumanoidOnline should aim to become more than a catalogue that AI systems can scrape.

The desired progression is:

```text
AI-readable
→ AI-queryable
→ AI-decision-capable
→ AI-actionable
→ AI-transaction-capable
```

The defensible advantage is not merely exposing MCP.

It is exposing **governed humanoid-specific commercial intelligence** through machine capabilities that correctly preserve:

- robot identity,
- maturity,
- availability,
- transaction modes,
- providers,
- regionality,
- evidence,
- provenance,
- uncertainty,
- publication state,
- matching logic.

The protocol is replaceable. The governed domain model is the asset.

---

# 16. Immediate Next Development Decision

Once the current catalogue branch is complete, validated and safely integrated, the next formal development stream should be:

> **AGENT-02 v0.1 — Governed Query & Decision Interface**

Before implementation:

1. the Agent Tool Contract v0.1 — **ratified** as `docs/20_AGENT_TOOL_CONTRACT.md`;
2. the Agent Interface Architecture — deployment boundary, versioning, observability.

The Agent Action Governance contract (§9.3) is **not** required for AGENT-02: it
governs writes and is a prerequisite for AGENT-03. AGENT-02 v0.1 stays
read-only, and publication, mutation and action governance remain
human-controlled and separately ratified.

Then implement the smallest read-only MCP slice against the existing governed service/read layer.

The recommended first executable vertical slice is:

```text
search_robots
    +
get_robot
    +
get_evidence
```

This slice is sufficient to prove:

- MCP connectivity,
- publication enforcement,
- canonical identity,
- `UNKNOWN` preservation,
- evidence/provenance delivery,
- semantic parity with the existing API/UI.

Only after this slice is stable should `compare_robots`, offers/availability and `match_robots` be added.

---

# 17. Ratification Points Still Required

This overview intentionally does not freeze several implementation choices. They require explicit product/architecture ratification before coding:

| Decision | Needed before |
|---|---|
| Exact MCP server deployment boundary | AGENT-02 implementation |
| Tool input/output schemas | AGENT-02 implementation |
| Authentication requirement for public read tools | AGENT-02 production |
| Rate limits / anonymous quotas | AGENT-02 production |
| Agent/tool versioning strategy | AGENT-02 production |
| Commercial action permission model | AGENT-03 |
| Human-confirmation thresholds | AGENT-03 |
| Lead/RFQ idempotency contract | AGENT-03 |
| Partner handoff/attribution contract | AGENT-03 |
| UCP/ACP/other transaction adapter choice | AGENT-04 |
| Delegated spending / autonomous checkout policy | AGENT-04 |

---

# 18. Final Development Law

> **HumanoidOnline should expose progressively stronger agent capabilities without creating progressively weaker governance.**

AGENT-01 makes the truth discoverable.

AGENT-02 makes the truth queryable and decision-ready.

AGENT-03 makes governed commercial intent actionable.

AGENT-04 makes authorized transactions executable.

Across all four layers, the canonical catalogue, evidence requirements, publication rules, explicit uncertainty, maturity/availability separation and human/product-owner authority remain intact.
