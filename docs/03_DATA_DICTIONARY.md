# HumanoidOnline — Data Dictionary (enum semantics)

**Status:** Frozen. These meanings are binding. **Do not invent new enum values or reinterpret existing ones while coding.** Additions require a product-owner decision and a schema change in `db/schema.sql` (where each enum is defined).

Humanoid-market data is full of ambiguity; this document is the disambiguation layer.

---

## 1. `commercial_status` — DIMENSION 1: maturity of the platform

Ordered ladder. Says how far the *product* has progressed — **not** whether you can obtain it.

| Value | Meaning | NOT to be confused with |
|---|---|---|
| `ANNOUNCED` | Publicly revealed; no hardware shipping | a launch |
| `DEVELOPMENT` | Actively engineered, internal only | prototype |
| `PROTOTYPE` | Working prototype(s) exist; not sold | pilot |
| `PILOT` | Deployed in customer pilots/trials | commercial availability |
| `EARLY_ACCESS` | Limited external units (design/dev partners) | general sale |
| `LIMITED_COMMERCIAL` | For sale but constrained (region/quota/waitlist) | full availability |
| `COMMERCIAL` | Generally commercially available | purchasable-by-you (check `availability_offer`) |
| `RAAS_DEPLOYMENT` | Commercially deployed as a service; units not sold | discontinued or unavailable — this is a *success* state |
| `DISCONTINUED` | No longer offered | never-launched |

**Canonical example:** Agility Digit = `RAAS_DEPLOYMENT`: formal commercial deployments and $300M+ contracted orders, yet no `PURCHASE` availability offer. Maturity, obtainability, and evidence are three independent dimensions.

## 2. `transaction_type` — the commercial mode of an offer

| Value | Meaning | Future vertical |
|---|---|---|
| `PURCHASE` | Outright unit sale | HumanoidMart (Phase 4) |
| `RENTAL` | Short-term paid use (day/week/event) | RentHumanoid (Phase 3) |
| `SUBSCRIPTION` | Recurring paid access to a unit | — |
| `LEASE` | Long-term financed use | HumanoidLease (Phase 5) |
| `RAAS` | Robots-as-a-service: outcome/service contract | HumanoidLease (Phase 5) |
| `PILOT` | Paid/structured pilot engagement | — |
| `DEVELOPER` | Developer/research edition acquisition | — |
| `OTHER` | Anything else (must carry a `note`) | — |

All six core modes are supported by the schema **now**, even though only Phase 1–2 UI is active.

## 3. `price_type` — the epistemic quality of a price

| Value | Meaning | Display rule |
|---|---|---|
| `PUBLIC` | Published MSRP/store price | show as-is |
| `FROM` | Published starting price | prefix "From" |
| `RANGE` | Known band (`price_min`–`price_max`) | show band |
| `QUOTE_ONLY` | Price on request | "Price on request" — never a number |
| `ESTIMATED` | HumanoidOnline estimate | must be visibly marked "Estimated" |

`ESTIMATED` without an `evidence_source` row is not publishable.

**Unknown price is NOT `QUOTE_ONLY`.** They are different facts with different displays:

| Fact | Data state | Display |
|---|---|---|
| We do not know the price | no `pricing_offer` rows | **"No confirmed pricing"** |
| The commercial model requires a quote | `price_type = QUOTE_ONLY` | **"Price on request"** |

Recording `QUOTE_ONLY` is a positive claim about the seller's commercial model and needs evidence like any other commercial fact. Absence of pricing rows claims nothing.

## 4. `availability_status` — DIMENSION 2: can you obtain it, per mode × region

| Value | Meaning |
|---|---|
| `NOT_AVAILABLE` | Confirmed not obtainable in this mode/region (a *positive* negative fact — requires evidence) |
| `WAITLIST` | Orderable onto a waitlist |
| `PREORDER` | Orderable ahead of availability |
| `LIMITED` | Obtainable with constraints (quota, qualification) |
| `AVAILABLE` | Obtainable |
| `ON_REQUEST` | Contact/quote required (default when engagement is bespoke) |
| `DISCONTINUED` | Was obtainable in this mode; no longer |

**Absence of any `availability_offer` row ≠ `NOT_AVAILABLE`.** Absence means *unknown* → UI renders "No confirmed commercial availability."

**Canonical access predicate.** Whenever a yes/no "commercially accessible?" decision is needed, there is exactly one rule, implemented as the schema function `commercially_accessible(status)`:

```
commercially_accessible ⇔ is_current AND status NOT IN (NOT_AVAILABLE, DISCONTINUED)
```

So `WAITLIST` = accessible (constrained), `PREORDER` = accessible (future), `LIMITED` = accessible (constrained), `AVAILABLE` = accessible, `ON_REQUEST` = accessible (bespoke). `robot_commercial_snapshot.is_obtainable`, `available_modes`, the Home "Commercially accessible" section, and catalogue transaction filters all use this one predicate. Never write an ad-hoc status list.

**Price↔availability matching (offer views).** A price attaches to an availability offer only when robot, `transaction_type`, variant (equal or price variant-agnostic), provider (equal or price provider-agnostic — provider A's availability must never surface provider B's price) and geography (equal region, direct parent region, `GLOBAL`, or region-agnostic) all correlate; the most specific matching price wins (provider-specific > agnostic, exact region > parent > global, variant-specific > agnostic). Full semantics and implementation: `commercial_offer` view in `db/schema.sql`.

## 5. Other enums (summary — full definitions in `db/schema.sql`)

- `transaction_preference` (buyer intent): `UNKNOWN / RENT / BUY / LEASE / RAAS / FLEXIBLE`. Captured in Phase 2 before transaction products exist — this is demand intelligence.
- `billing_period`: `ONE_TIME / HOURLY / DAILY / WEEKLY / MONTHLY / QUARTERLY / ANNUAL`.
- `provider_type`: `OEM / DISTRIBUTOR / INTEGRATOR / RENTAL_PROVIDER / LEASING_PROVIDER / RAAS_PROVIDER / SERVICE_PROVIDER`.
- `mobility_type`: `BIPEDAL / WHEELED / HYBRID / QUADRUPED / STATIONARY / OTHER`.
- `autonomy_level` (ordered): `TELEOPERATED < ASSISTED < SUPERVISED_AUTONOMY < TASK_AUTONOMOUS < HIGHLY_AUTONOMOUS`.
- `capability_category`: `MANIPULATION / MOBILITY / PERCEPTION / AI_AUTONOMY / INTERACTION / SOFTWARE / SAFETY / OTHER`.
- `region_type`: `GLOBAL / CONTINENT / ECONOMIC_ZONE / COUNTRY / SUBREGION` (hierarchical via `region.parent_id`).
- `source_type`: `MANUFACTURER_STORE / MANUFACTURER_SITE / PRESS_RELEASE / NEWS_ARTICLE / ANALYST_REPORT / FINANCIAL_FILING / DIRECT_QUOTE / CONFERENCE / INTERVIEW / OTHER`.
- `confidence_level`: `LOW / MEDIUM / HIGH / VERIFIED`. Only `VERIFIED` may render a "Verified" indicator; it requires `verified_at`.
- `lead_status`: `NEW → QUALIFYING → QUALIFIED → MATCHED → INTRODUCED → IN_DISCUSSION → WON / LOST / DISQUALIFIED`.
- `match_category`: `BEST_OVERALL / BEST_COMMERCIAL / BEST_LOWER_COST / BEST_DEVELOPER / BEST_TECHNICAL / ALTERNATIVE`.
- `buyer_type`: `COMMERCIAL_BUYER / TECHNICAL_EVALUATOR / INDUSTRY_PARTICIPANT / UNKNOWN`.

## 6. NULL semantics (repeated because it matters)

| Situation | Meaning | Never |
|---|---|---|
| `robot.payload_kg IS NULL` | payload unknown | payload = 0 |
| `robot.has_sdk IS NULL` | unknown | false |
| no `pricing_offer` rows | price unknown → "No confirmed pricing" | free / $0 / "Price on request" |
| no `availability_offer` rows | availability unknown | not available |
| `evidence.verified_at IS NULL` | unverified claim | verified |

Unknown must never silently become zero or false — in matching (Product Contract §7.2), in filters, or in display (Product Contract §5.2).

## 7. Provenance rules

Commercially sensitive fields — **price, availability, commercial status, deployment claims, regional availability** — require an `evidence_source` row carrying `source_url`, `source_type`, `observed_at`, `verified_at` (when checked), `confidence`.

> **Core rule: no commercial fact without evidence.**

Operationally: a value with no evidence may exist in the database (e.g. freshly scraped) but must not be *published* (`robot.is_published` gate) until evidence is attached. Stale evidence (`verified_at` older than a policy window) downgrades display confidence; it does not delete the fact.
