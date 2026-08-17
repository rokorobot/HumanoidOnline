# HumanoidOnline — AGENT-02 Tool Contract

> ## STATUS: RATIFIED v0.1 — 2026-08-17 — implementation underway under an owner build trigger
>
> Defines the **transport-independent semantic contract** for the AGENT-02
> *Query & Decide* read-only interface. This document adds no law. Every rule
> below is inherited from an existing frozen or ratified contract and cited to
> it; where this document appears to say something new, the cited source wins.
>
> **The governance rule is unchanged: ratification freezes semantics and
> authorizes no code.** It never did. Building AGENT-02 required an explicit
> owner build trigger, per the pattern in `docs/10`; that trigger was
> subsequently given and implementation is underway. Ratification and
> authorization remain two separate acts, and a future slice still needs its own
> trigger.
>
> Implementation status is tracked per section rather than here (§5, §10.3.1,
> §10.5, §12). This document is a contract, not a changelog.

**Document:** `docs/20_AGENT_TOOL_CONTRACT.md`
**Semantic contract version:** **v0.1** (the one normative version)
**Wire identifier:** `agent-tools/0.1` — the string carried in
`meta.contract_version`; an interface label, not a second version scheme
**Date:** 2026-08-17
**Depends on:** `db/schema.sql`, `docs/01`, `docs/03`, `docs/04`, `docs/05`, `docs/10`, `docs/18`
**Roadmap context:** `docs/19_AGENT_INTERFACE_ROADMAP.md` §4 (DRAFT)

---

## 1. Status and scope

AGENT-02 v0.1 exposes **three read-only tools** over the **published canonical
catalogue**, through the **same governed service/read layer** the website and
public API already use.

In scope: semantic tool definitions, input/output shapes, enum vocabulary,
UNKNOWN encoding, pagination, errors, versioning, transport boundary.

Out of scope: implementation, MCP server code, HTTP routing, authentication
business logic, any write, and everything listed in §22.

This document does not supersede any frozen contract and does not restate
sequencing decisions recorded elsewhere.

## 2. Normative dependencies — inherited, not redefined

| Source | Status | What AGENT-02 inherits |
|---|---|---|
| `db/schema.sql` | Canonical (AGENTS.md rule 2) | Entity model, every enum, `chk_price_type_shape`, `commercially_accessible()`, `commercial_offer` region resolution |
| `docs/03_DATA_DICTIONARY.md` | Frozen | Enum meanings; §1 maturity ladder + `UNKNOWN`; §3 price-type trichotomy; §4 availability; §6 UNKNOWN never 0/false; §7 provenance |
| `docs/10_AGENT_CONTRACT.md` | RATIFIED v0.1 | AGENT-01.1 canonical identity · 01.2 semantic parity · 01.3 explicit uncertainty · 01.4 provenance preservation · 01.6 projection only · 01.7 published-canonical-only |
| `docs/18_SYSTEM_ARCHITECTURE.md` | RATIFIED v0.1 | §18.1 agent → governed typed API → services → canonical rules; `Agent → database` marked **Never** |
| `docs/05_ACCEPTANCE_CRITERIA.md` | Binding | A2 price trichotomy · G2 evidence · G2.1 `UNKNOWN` needs none |
| `docs/04_API_CONTRACT.md` | Frozen shape | Envelope, pagination defaults, error shape, "unknown values are `null`, never `0`/`false`/`""`" |
| `docs/01_PRODUCT_CONTRACT.md` | Frozen | §7 matching; "UNKNOWN never excludes" (ranking only — see §9.3); three independent dimensions; no `robot.available` boolean |
| `docs/decisions/DR-C1` | Decided | Publication is editorial; records are never deleted as a side effect |

**No new enum vocabulary is introduced by this contract.** Every accepted value
is exactly a `db/schema.sql` enum member.

## 3. AGENT-02 v0.1 boundary

AGENT-02 v0.1 is **read-only over published canonical data**. It performs no
write of any kind, holds no catalogue of its own, and reaches the database only
through the existing governed service/read layer.

**Deployment.** Tools run in the existing application process. No separate
service, datastore, cache or parallel catalogue (AGENTS.md rule 4).

**Identity.** The semantic contract is **anonymous-capable**: no tool input or
output carries account identity, API-key semantics, user profile, lead
attribution or commercial identity. Transport-level rate limiting may exist
(§19) but is not part of tool semantics.

## 4. Tool surface

v0.1 is exactly three tools:

| Tool | Purpose |
|---|---|
| `search_robots` | Filter published canonical robots and return list projections |
| `get_robot` | Return one published canonical robot's full governed detail |
| `get_evidence` | Return provenance for a published canonical fact |

**These three names are frozen for v0.1, and there are no aliases.** A second
name for the same capability is a second contract to keep consistent.

`get_current_offers` and `get_availability` are **not separate tools**: offers
and availability are already embedded in the `get_robot` detail projection with
their provider, region and evidence intact. A separate tool would duplicate
surface over the same governed read. They remain represented through the
governed robot-detail commercial projection unless a later contract proves a
separate tool necessary.

Deferred: see §22.

## 5. `search_robots`

**Purpose.** Find published canonical robots matching structured constraints.

**Canonical read path (implementation must reuse).**
`apps/api/app/services/robot_filters.py::apply_catalogue_filters` →
`services/reads.py::serialize_list_item`. The governed predicates were moved out
of `routers/robots.py::_apply_filters` (which remains only as an alias) so the
public API and the tool layer share one implementation rather than two
interpretations. The unconditional `Robot.is_published.is_(True)` predicate in
`apply_catalogue_filters` **is** the publication gate; it must not be
re-implemented or bypassed.

Geography resolves through `services/robot_filters.py::resolve_region_filter` →
`services/regions.py::applicable_region_ids` (§12), and the comparable-purchase-price
rule through `services/pricing.py` (§10.3). Both are shared services, not
agent-owned SQL.

**Required inputs.** None. An empty call returns the first page of all published
robots.

**Optional inputs** (all pass through to the existing filter; no new filters):

| Input | Type | Vocabulary |
|---|---|---|
| `q` | string | free text |
| `manufacturer` | string | manufacturer slug |
| `commercial_status` | list | `commercial_status` enum, incl. `UNKNOWN` |
| `transaction_type` | list | `transaction_type` enum |
| `availability_status` | list | `availability_status` enum |
| `region` | string | `region.code` (see §12) |
| `use_case` | string | use-case slug |
| `payload_min` | number | kg |
| `height_min` / `height_max` | number | cm |
| `price_max` | number | see §10.3 — **requires `price_currency`** |
| `price_currency` | string | ISO-4217 code matching `pricing_offer.currency`; **required with `price_max`, rejected without it** |
| `mobility` | string | `mobility_type` enum |
| `autonomy_min` | string | `autonomy_level` enum (ordered) |
| `has_sdk`, `ros_support`, `developer_edition`, `has_manipulation` | boolean | tri-state source (§9.2) |
| `sort` | string | `name` \| `price` \| `payload` \| `newest`, `-` prefix for desc — see §10.5 for `price` under a currency-constrained query |
| `limit`, `offset` | integer | §16 |

**`price_max` and `price_currency` are a pair.** `price_max` without
`price_currency` → `INVALID_ARGUMENT`: a bare number cannot be compared to money
that carries a denomination. `price_currency` without `price_max` →
`INVALID_ARGUMENT` as well: it has no independent meaning in v0.1, and accepting
an inert input invites the belief that it filters something. Full semantics in
§10.3.

**Hard-filter semantics.** Every input above is a **hard constraint**: a robot
is returned only if it *confirmedly satisfies* it. See §9.2 for the UNKNOWN rule
and §9.3 for why this differs from matching.

**Output.** A paged envelope (§15) of list projections. Each item:

| Field | Nullability |
|---|---|
| `slug`, `name`, `commercial_status`, `canonical_url` | mandatory |
| `manufacturer` `{slug, name}` | mandatory |
| `payload_kg`, `height_cm`, `mobility` | **UNKNOWN-capable** (`null`, key present) |
| `price_display` | conditional — see §10.4 |
| `available_modes` | conditional, possibly empty — see §11 |
| `deployment_count` | mandatory integer (a true count, not a claim) |
| `primary_image` | conditional (MEDIA-01 display-eligible only) |
| `updated_at` | mandatory |

**Errors.** Unknown enum member → `INVALID_ENUM`. Out-of-range pagination →
`INVALID_PAGINATION`. An unmatched filter is **not** an error: it returns an
empty page with `total: 0`.

## 6. `get_robot`

**Purpose.** Full governed detail for one published canonical robot.

**Canonical read path.** `apps/api/app/routers/robots.py` detail route (which
applies `Robot.is_published.is_(True)`) → `services/reads.py::serialize_detail`.

**Required input.** `slug` (string, canonical — §8).
**Optional inputs.** None in v0.1.

**Output.** The existing detail projection, unaltered in meaning:

| Group | Notes |
|---|---|
| Identity | `slug`, `name`, `model_code`, `manufacturer{slug,name}`, `canonical_url` |
| `commercial_status` | mandatory; may be `UNKNOWN` (§9.1) |
| `specs` | every field **UNKNOWN-capable**, key always present (§9.1) |
| `pricing_offers[]` | conditional; each carries `price_type`, `provider`, `region`, `evidence` (§10) |
| `availability_offers[]` | conditional; each carries `transaction_type`, `availability_status`, `provider`, `region`, `evidence` (§11) |
| `deployments[]` | conditional, evidence-linked |
| `images[]` | conditional; MEDIA-01 display-eligible only, provenance intact |
| `variants[]`, `capabilities[]`, `use_case_fits[]` | conditional |
| `extended_specs[]` | conditional |

An **absent list is not a negative claim** (§9.4).

**Errors.** Unknown, unpublished or non-canonical slug → `NOT_FOUND`. The
response must be identical for "does not exist" and "exists but unpublished"
(AGENT-01.7 — a distinguishable response would leak publication state).

## 7. `get_evidence`

**Purpose.** Return the provenance behind a published canonical commercial fact.

**Canonical read path.** `services/reads.py::load_evidence`, whose documented
selection rule is *best evidence per `(subject_type, subject_id)`: verified
first, then newest*. That pair is an **internal** selection key, not the
caller-facing address — see §7.1.

**Required input.** `evidence_ref` — the opaque reference returned alongside any
fact that has evidence (see below). No other addressing form is accepted.

### 7.1 `evidence_ref` — the public evidence address

Raw internal database UUIDs are **not** the public agent contract. Facts that
carry evidence are returned with an `evidence_ref`, which is:

- **opaque** to the caller;
- **stable** enough for the governed public interface;
- **issued by** the governed read/service layer, never by the client;
- **returned alongside** the fact it supports;
- **accepted by** `get_evidence` and nothing else;
- **not constructed or parsed** by an agent — it carries no semantics a client
  is required to understand, and clients must not depend on its shape;
- **never** a raw database identifier, and never requiring the caller to supply
  one.

`get_evidence` resolves an `evidence_ref` through the governed service/read
layer. The internal mapping from `evidence_ref` to canonical evidence storage is
an **implementation concern and is deliberately not frozen by this document** —
it may change without a contract version bump, provided the properties above
hold.

A fact that legitimately has **no** evidence under `docs/05` G2.1 — notably
`commercial_status = UNKNOWN` — carries **no** `evidence_ref`. A reference is
never fabricated to make a fact look sourced.

`evidence_subject` (`db/schema.sql`) remains the internal classification of what
a piece of evidence is about — `COMMERCIAL_STATUS`, `PRICING_OFFER`,
`AVAILABILITY_OFFER`, `DEPLOYMENT`, and so on — and may be **reported** in the
output. It is not an input, and a caller never assembles a subject address.

**Output** (mirrors `schemas/common.py::EvidenceRead` exactly):

| Field | Nullability | Meaning |
|---|---|---|
| `source_type` | mandatory | `source_type` enum |
| `confidence` | mandatory | `confidence_level` enum |
| `observed_at` | **mandatory** | when we read it — `TIMESTAMPTZ NOT NULL` |
| `verified_at` | **nullable, meaningful** | `null` = not re-checked at source; never treat as "unverified data" or as `observed_at` |
| `published_at` | nullable | source's own publication date |
| `source_url` | nullable | provenance page |
| `subject_type` | mandatory | `evidence_subject` enum — what this evidence is about |

**Evidence existence ≠ confidence.** A returned row proves a claim is sourced;
`confidence` grades that source. Neither implies the other (§13).

**Errors.** An `evidence_ref` that is unknown, expired, or resolves to a fact not
reachable from a **published** robot → `NOT_FOUND`, indistinguishable between
those cases so publication state cannot be probed. A malformed reference →
`INVALID_ARGUMENT`. A fact that legitimately has no evidence is **not** an
error — it simply carries no `evidence_ref` to call with (`docs/05` G2.1).

## 8. Canonical identifiers

Per AGENT-01.1, the **slug** is the canonical external identifier for robots and
manufacturers, and `canonical_url` (`/robots/{slug}`, `/manufacturers/{slug}`)
is the citable address.

**Internal database UUIDs are never the public contract.** Where a tool must
reference something without a slug — an offer, or a piece of evidence — it uses
an opaque reference issued by the governed read layer: `evidence_ref` for
evidence (§7.1). A caller never constructs, parses or supplies a database
identifier, and tools never accept or return a database selector (§20).

## 9. UNKNOWN semantics

### 9.1 Representation
`UNKNOWN` is transported as JSON `null` **with the key present**. Omitting the
key is forbidden: an absent key cannot be distinguished from a field this
contract does not model. Never `0`, `false`, `""`, `"UNKNOWN"` for a
non-enum field, or a synthetic default (`docs/03` §6, `docs/04` conventions,
AGENTS.md rule 6).

`commercial_status = UNKNOWN` is the enum member meaning *maturity not yet
verified* — an explicit value, not a null (`docs/03` §1).

### 9.2 Hard constraints (v0.1 ratified rule)
For a **hard search constraint**, an UNKNOWN value **does not satisfy an
explicitly requested positive requirement**.

`has_sdk=true` returns robots whose `has_sdk` is `true`. Robots with `false`
**and** robots with `null` are both excluded — but for different reasons, and
the distinction stays observable: any excluded-then-inspected robot still
reports `has_sdk: null`, never `false`.

A tool must never rewrite an unknown value to make a filter decision explicable.

### 9.3 Relationship to matching
This differs deliberately from `docs/01` §7.1 *"UNKNOWN never excludes"*, which
governs **ranking**: there an unknown value survives with a scoring penalty and
a warning. Filtering answers *"does this robot confirmedly meet my constraint?"*;
ranking answers *"how well does it fit?"*. **This contract does not alter the
matching contract**, which is reached only via the deferred `match_robots`
(§22).

### 9.4 Absence is not negation
An empty `pricing_offers`, `availability_offers`, `deployments` or `images` list
means *nothing is on record* — never "free", "not available", "never deployed"
or "no image exists". Where a consumer could misread absence, the response
carries a `warnings[]` entry (§15).

## 10. Pricing semantics

### 10.1 Four distinct states, never conflated
Per `docs/03` §3 and `docs/05` A2:

| State | Representation |
|---|---|
| Public/starting/estimated price | `price_type ∈ {PUBLIC, FROM, ESTIMATED}`, `amount` non-null |
| Range | `price_type = RANGE`, `price_min` + `price_max` non-null, `amount` null |
| Quote-gated | `price_type = QUOTE_ONLY`, **`amount` null** |
| Unknown price | **no `pricing_offer` row at all** |

`QUOTE_ONLY` is a *positive claim about the seller's commercial model* requiring
evidence; absence of pricing rows claims nothing. They are different facts and
must never be merged.

### 10.2 Amount and type are inseparable
An amount is never returned without its `price_type`. `chk_price_type_shape` in
`db/schema.sql` already forbids the invalid shapes; the tool layer must not
produce a shape the database would reject. **A zero amount never means unknown
or quote-only.**

### 10.3 `price_max` — a hard numeric constraint, evaluated in one currency (ratified)

**The rule.** Given `price_max = X` and `price_currency = C`:

> Find the governed comparable purchase price(s) **denominated in `C`**, and
> evaluate the numeric hard constraint **only within that currency**.

A robot satisfies the constraint only when such a price exists, is numeric, and
is confirmed ≤ X.

**No foreign exchange, at all.** v0.1 performs no conversion and defines no
exchange rates, base currency, normalisation, conversion timestamps or FX
provider. `USD 29,000`, `GBP 29,000` and `EUR 29,000` are three different
amounts and are never treated as equivalent. Prices in a currency other than `C`
are **incomparable** for this constraint — not larger, not smaller, not
convertible. FX is explicitly out of scope for v0.1.

This inherits the principle the decision layer already applies: `_budget` in
`matching/engine.py` admits a price only when `p.currency == req.budget_currency`
and its own docstring records that *"a robot carrying two currencies makes the
comparison incomparable (**no FX**)"*. That engine is not modified by this
contract.

**Result semantics.** For `price_max = X`, `price_currency = C`:

| # | Robot's pricing state | Outcome |
|---|---|---|
| A | Comparable numeric price in `C` ≤ X | **satisfies** |
| B | Comparable numeric price in `C` > X | exclude — `price_max_excluded_above_limit` |
| C | Has prices, none safely comparable in `C` | exclude — `price_max_excluded_unprovable` |
| D | `QUOTE_ONLY` | exclude — `price_max_excluded_unprovable` |
| E | No pricing evidence / UNKNOWN price | exclude — `price_max_excluded_unprovable` |
| F | Prices exist **only in other currencies** | exclude — `price_max_excluded_unprovable`, **never** `above_limit` |

`RANGE` prices follow the existing frozen range semantics (`docs/03` §3) within
`C`, never by inventing a point value.

Case **F** is the one a careless implementation gets wrong: a EUR-only robot
under a USD ceiling has not failed on price, it has failed on *comparability*.
Reporting it as `above_limit` would assert a numeric relationship that was never
established.

**Failing the filter is not a claim about the robot.** None of B–F is ever
converted to `0`, `false`, "unavailable", or a guessed converted amount. A
`QUOTE_ONLY` robot is not expensive; an unpriced robot is not free; a EUR-only
robot is not over budget.

**Warn-and-exclude.** The response carries `warnings[]` entries so a caller can
tell the two kinds of absence apart:

| Reason code | Meaning |
|---|---|
| `price_max_excluded_unprovable` | Excluded because no comparable numeric price in `C` could be established (cases C–F) |
| `price_max_excluded_above_limit` | Excluded because a comparable price **in `C`** exceeded X (case B) |

These are **query-result exclusion reasons, not errors** — see §17. A buyer
asking "under €30,000" is not asking to hide quote-gated or USD-priced robots
silently, and an agent must distinguish "we cannot prove a price" from "the
price is too high" without issuing a second query.

**No `include_quote_only` override in v0.1.** A caller who wants quote-gated
robots issues a query **without** a numeric ceiling.

#### 10.3.1 The `lowest_purchase_price` cache is NOT the rule

`robot.lowest_purchase_price` **must not** be defined as the canonical basis for
this constraint. Its derivation (`db/import_catalogue.py::_refresh_lowest_price`)
selects

```sql
ORDER BY price ASC LIMIT 1
```

across **all** current PUBLIC/FROM purchase offers **with no currency
partition** — so for a robot priced in two currencies it caches whichever number
is numerically smallest, which is a cross-currency minimum and therefore
meaningless. `docs/01` §7 and `db/schema.sql` already describe the column as a
**sort/badge cache only**, with `pricing_offer` as the authoritative money.

The cache may be used as an optimisation **only** when both hold:

1. `robot.lowest_price_currency` equals the requested `price_currency`, **and**
2. its derivation is valid for that comparison (i.e. it did not select across
   currencies).

Otherwise the implementation must evaluate `pricing_offer` rows directly.

**Implementation status.** The comparable-price rule is implemented once, as
server-side SQL, in `services/pricing.py` — a shared catalogue service, not an
agent-owned one, so both surfaces can reach the same answer.

**CLOSED — both surfaces converged.** AGENT `search_robots` and HTTP
`/api/robots` apply the identical exact-currency predicate from
`services/pricing.py`, with `COUNT` and `LIMIT`/`OFFSET` over the price-filtered
set. `/api/robots` takes `price_max` + `price_currency` as a required pair
(`docs/04`) and no longer compares against `Robot.lowest_purchase_price`; the
cache-based hard-constraint path was removed from the shared filter rather than
left dormant, so no caller can reach it. The cache retains only its sanctioned
sort/badge role (§10.5).

### 10.4 No synthesized best price
No tool returns a single invented "best price" for a robot. `price_display` is
returned only because it is an **existing governed read** (`price_display_for`);
it is a display projection of real offers, not a new pricing concept.

### 10.5 `sort=price` under a currency-constrained query (ratified)

`sort` has always been one of four keys (§5, §16); this section specifies a case
the original draft left under-specified — **what `price` orders by when the query
also carries a price constraint.**

**When `price_max` *and* `price_currency` are both present**, `sort=price` /
`sort=-price` order by **the same comparable purchase price in `price_currency`
that qualified the robot** (§10.3).

> A robot must never qualify on its EUR price and then be ordered by an
> unrelated cached USD amount.

- The per-robot sort figure is the **lowest comparable amount in
  `price_currency`**, where "comparable" is exactly §10.3's rule: `price` for
  `PUBLIC`/`FROM`/`ESTIMATED`, the **upper bound** for `RANGE`, and nothing at
  all for `QUOTE_ONLY`.
- Ascending: lowest comparable amount first. Descending: highest of those
  per-robot minima first.
- The stable `Robot.slug` tiebreak of §16 still applies, so paging remains
  deterministic.

Every robot in such a result has a comparable amount by construction — a robot
without one cannot have passed the ceiling — so this ordering has no null case.

**When there is no currency-constrained price query**, `sort=price` may continue
to use `robot.lowest_purchase_price`, the sort/badge cache `docs/01` §7 and
`db/schema.sql` sanction for exactly this purpose. The cache remains forbidden as
the *hard-constraint* basis (§10.3.1); ordering a list is not asserting that two
amounts are comparable.

**No standalone `price_currency` for sorting in v0.1.** `price_currency` keeps
its §5 meaning — valid only alongside `price_max` — and is not accepted merely
to select a sort denomination.

**Implementation status — IMPLEMENTED on both surfaces.** The constrained
ordering figure is `services/pricing.py::comparable_price_order_column`, derived
from the same `comparable_amount()` that decides qualification, so the two
cannot disagree about a robot's price. `robot_filters.py::resolve_sort` selects
the mode; it does not define either.

## 11. Availability semantics

Obtainability is **not** a boolean. `docs/01` §7 is explicit that there is *no*
`robot.available` boolean by design, and this contract introduces none.

Availability is always a set of rows scoped by
`(transaction_type × region × provider)` with an `availability_status`. The only
access predicate is the schema function `commercially_accessible()`
(`is_current AND status NOT IN (NOT_AVAILABLE, DISCONTINUED)`); no tool may use
an ad-hoc status list.

**Maturity ≠ obtainability.** `commercial_status = COMMERCIAL` must never be
reported or inferred as purchasable; `ANNOUNCED` must never be reported as
`NOT_AVAILABLE`. `NOT_AVAILABLE` is a *positive negative fact requiring
evidence* (`docs/03` §4) and must never be produced by absence.

## 12. Geography / region semantics

**`GLOBAL` means genuinely applicable worldwide.** It is a real scope that
applies to a buyer in any narrower region, ranked **least specific**. This is
settled by three concordant frozen sources:

1. `db/schema.sql`, `commercial_offer` block comment: geography correlates when
   *"price.region_id = availability.region_id, OR price.region is the
   availability region's direct parent …, **OR price.region is GLOBAL**, OR
   price.region is NULL"*, with precedence *"exact region > parent >
   GLOBAL/NULL"*.
2. `docs/03` §"Price↔availability matching (offer views)" restates the same rule
   as frozen dictionary semantics.
3. `apps/api/app/services/matching/repository.py::_applicable_region_ids` —
   *"The country itself + its ancestor regions (economic zone, …) + GLOBAL — the
   regions whose offers apply to a buyer in `country_code`"*, with region-agnostic
   (`NULL`) applying everywhere.
4. `apps/api/app/services/leads/routing.py::_applicable_region_ids` — the
   commercial layer independently implements the same walk and says so:
   *"A region + its ancestor regions … + GLOBAL … Mirrors the matching
   repository's country->applicable-regions walk."*

Two frozen documents and the two governed subsystems that consume geography
therefore agree. No source in the repository treats `GLOBAL` as a scope
inapplicable to a narrower region.

**Therefore `region` in `search_robots` is an *eligibility* constraint** (ratified):
a robot matches when it has a current, commercially-accessible offer whose region
is

- the **exact** requested region, or
- an **applicable ancestor** region (e.g. an `EU` offer for a `DE` query), or
- **`GLOBAL`**, or
- **region-agnostic** (`NULL`).

**Specificity stays observable.** Each returned offer reports its own
`region` verbatim, and precedence is **exact > ancestor > GLOBAL/NULL**. A
`GLOBAL` offer may *satisfy* a narrower geography query, because `GLOBAL` means
worldwide applicability — but it is reported as `GLOBAL` and must never be
relabelled, promoted or presented as an EU-specific (or any region-specific)
offer. The caller can always see which scope actually matched.

A region-scoped answer is never generalised in the other direction either: an
offer scoped to one region is not evidence of availability in a **sibling**
region.

**Implementation status — CLOSED.** The catalogue previously matched
`region.code` **exactly**, walking neither `parent_id` nor `GLOBAL`, so
`/api/robots?region=DE` and the agent tool answered the same question
differently. That drift is resolved: **both the HTTP catalogue and AGENT
`search_robots` now resolve geography through one canonical shared path**,
`services/robot_filters.py::resolve_region_filter` →
`services/regions.py::applicable_region_ids`. The exact-code branch was removed
rather than left dormant, so the divergence cannot reappear by a caller choosing
the older parameter.

An unresolvable region code is **invalid input** on both surfaces — a structured
client error over HTTP, `INVALID_ARGUMENT` for the tool (§17). It is never
treated as `GLOBAL`, never silently dropped, and never widened to
region-agnostic offers: an unknown region must fail, not return more than a
known one.

The semantics above are unchanged by this convergence; only the implementation
moved. Two independent region walks still exist in other subsystems
(`matching/repository.py` and `leads/routing.py`, the latter explicitly
mirroring the former). Migrating them onto the canonical resolver is separately
scoped work; their parity with it is pinned by tests so a third interpretation
cannot drift in unnoticed.

## 13. Evidence and provenance semantics

Every commercial fact returned — price, availability, commercial status,
deployment, regional claim — must remain traceable to evidence via
`get_evidence` (`docs/03` §7, `docs/05` G2, AGENTS.md rule 7).

Preserved distinctions:

- **`observed_at` ≠ `verified_at`.** Observed is when we read it; verified is
  when we re-checked it at source. `verified_at: null` is meaningful and must
  never be filled from `observed_at`.
- **Evidence existence ≠ confidence.** Presence proves sourcing; `confidence`
  grades it.
- **`UNKNOWN` requires no evidence** (`docs/05` G2.1). Its absence is correct,
  not a gap — and such a fact carries **no `evidence_ref`** (§7.1). A reference
  is never minted to make an unevidenced fact look sourced.
- Provenance fields are never fabricated, defaulted or inferred.

**Addressing.** Evidence is reached only through the opaque `evidence_ref`
issued by the governed read layer (§7.1, §8). Raw database identifiers are
neither exposed nor accepted.

## 14. Publication boundary

Per AGENT-01.7, tools expose **only** canonical rows with `is_published = true`.

Never exposed: unpublished canonical robots; DATA-D1 discovery candidates;
promoted-but-unpublished records; any internal review state.

The gate is the existing read layer's `is_published` predicate — inherited, not
re-implemented. Publication remains an editorial act under DR-C1; no tool reads,
reports or influences publication workflow, and `total` counts must never reveal
the existence of withheld records.

## 15. Response envelope

Derived from `docs/04` conventions, not a parallel shape.

```json
{
  "data": {},
  "meta": {
    "tool": "search_robots",
    "contract_version": "agent-tools/0.1",
    "canonical_source": "https://<site>/robots",
    "generated_at": "2026-08-17T00:00:00Z",
    "pagination": { "limit": 24, "offset": 0, "total": 13 }
  },
  "warnings": []
}
```

`data` holds the tool payload (`items` for list tools). `pagination` appears
only for paged tools. `warnings[]` carries machine-readable notices — absence of
pricing rows, a `price_max` filter excluding quote-only robots (§10.3), a hard
constraint excluding UNKNOWN-valued robots (§9.2) — and is **never** used to
smuggle a value that belongs in `data`.

## 16. Pagination and bounded queries

**The canonical API bounds apply unchanged** (`docs/04`): `limit` default **24**,
maximum **100**; `offset` ≥ 0. No larger agent-only bounds are invented.

**Out-of-range values are rejected, never silently clamped** (ratified). A
`limit` above the maximum, a negative `limit`/`offset`, or a non-integer returns
`INVALID_PAGINATION`. Clamping would hand back a different query than the one
asked for while reporting success, which an agent cannot detect.

**Continuation must be deterministic.** `meta.pagination` returns the effective
`limit`, `offset` and `total` for the query as executed, so the next page is
computable without guessing. `total` reflects the published, filtered result set
only and never reveals withheld records (§14). Ordering is stable for a given
`sort`, so paging cannot silently skip or repeat rows.

No unbounded query, and no client-controlled sort key outside the four
enumerated values.

## 17. Error taxonomy

Machine-readable and deterministic. Transport bindings map these to their own
status codes (§19); the semantic code is contractual.

| Code | Meaning |
|---|---|
| `NOT_FOUND` | Canonical published entity does not exist, or exists unpublished (indistinguishable by design) |
| `INVALID_ENUM` | Value is not a member of the cited `db/schema.sql` enum |
| `INVALID_ARGUMENT` | Malformed/contradictory input — e.g. `height_min > height_max`, `price_max` without `price_currency`, or `price_currency` without `price_max` (§5, §10.3) |
| `INVALID_PAGINATION` | `limit`/`offset` outside the bounds of §16 — rejected, never clamped |
| `RATE_LIMITED` | Transport/application-level throttle (§19); carries retry metadata where the transport knows it |
| `INTERNAL` | Unexpected failure; no internal detail leaked |

`NOT_FOUND` also covers an unknown or unresolvable `evidence_ref` (§7), kept
indistinguishable from "exists but unpublished" so publication state cannot be
probed.

**Errors are not exclusion reasons.** The codes in this table describe a call
that *failed*. The reason codes in `warnings[]` — `price_max_excluded_unprovable`,
`price_max_excluded_above_limit` (§10.3), and the UNKNOWN-exclusion notice
(§9.2) — describe a call that *succeeded* and explain why particular robots are
absent from a valid result. The two vocabularies are disjoint and must never be
merged: a quote-only robot failing a price ceiling is not an `INVALID_ARGUMENT`,
and a missing `price_currency` is not a warning.

Errors never partially succeed and never return fabricated data. An empty result
is a success with `total: 0`, not an error.

## 18. Contract versioning

**The semantic contract version is `v0.1`.** There is exactly one answer to
"which version of the AGENT-02 semantic tool contract is this?" — **v0.1**.

`agent-tools/0.1` is the **wire identifier** for that same version: the string a
binding puts in `meta.contract_version` so a client can recognise the interface.
It is a label, **not a second version scheme**, and it tracks the semantic
version rather than varying independently.

Adding an optional input, an output field or a `warnings` code is **additive**
and does not change the version.

A change to any of the following is **breaking** and requires an explicit new
contract version — it may **never** silently alter v0.1:

- tool names,
- input schemas,
- output schemas,
- `UNKNOWN` semantics,
- filtering semantics (including hard-constraint and geography rules),
- evidence addressing (`evidence_ref`),
- publication visibility semantics.

The internal resolution of an `evidence_ref` is explicitly **not** part of this
surface (§7.1) and may change without a version bump. A longer-term deprecation
policy is deliberately not defined here.

## 19. Transport / MCP binding boundary

The tool contract is **transport-independent**. MCP is the intended first
binding; a later HTTP/JSON or other binding must expose these same semantics.

A binding owns only: protocol framing, schema advertisement, transport errors,
rate limiting, and observability.

A binding owns **none** of: catalogue semantics, filtering, matching, UNKNOWN
conversion, publication rules, evidence selection, pricing or availability
interpretation.

**No binding may query PostgreSQL directly** (`docs/18` §18.1 marks
`Agent → database` as *Never*; AGENT-01.6 names MCP explicitly as a projection).
Bindings call the same service-layer callables the website and API use. A tool
must be callable in-process with identical results and no MCP present — that is
the test of correct layering (§21.1).

### 19.1 Rate limiting
The semantic contract **permits** transport/application-level rate limiting and
deliberately **freezes no numeric quota** in v0.1 — a number here would be an
operational setting masquerading as a contract term.

`RATE_LIMITED` (§17) is a valid contract error. Where the transport knows when a
retry may succeed, it exposes appropriate retry metadata alongside the error.

**Throttling must never change catalogue semantics or tool results.** A
rate-limited call fails cleanly; it never returns a truncated page presented as
complete, a filtered-down result set, a coerced `UNKNOWN`, or any answer
different from what the unthrottled call would have returned.

## 20. Security and prohibited inputs

No arbitrary SQL, SQL fragments, ORM expressions, column or table names. No
arbitrary URLs, no server-side fetching. No filesystem paths. No database
selectors, internal ids as query surface, or raw filter objects.

Inputs are strictly schema-validated against the enumerated vocabulary; unknown
input keys are rejected rather than ignored. Pagination is bounded (§16),
resource use predictable, and no tool mutates anything (§14).

## 21. Required implementation tests

Before AGENT-02 v0.1 may be considered complete:

1. **Layering** — each tool is callable in-process with no transport present and
   returns identical results; no tool module imports a DB session directly.
2. **Semantic parity** — the same query via the existing API and via a tool
   yields semantically identical results (AGENT-01.2).
3. **Publication exclusion by injection** — a real unpublished robot with
   sentinel slug and name appears in no tool output, and `get_robot` returns
   `NOT_FOUND` indistinguishable from a non-existent slug (extends the existing
   R14 pattern).
4. **Discovery isolation** — candidates never surface.
5. **UNKNOWN round-trip** — `null` survives service → serializer → transport with
   the **key present**; asserted not `0`, not `false`, not `""`.
6. **Hard-constraint semantics** — `has_sdk=true` excludes both `false` and
   `null` robots, and an excluded `null` robot still reports `null` when fetched.
7. **Price trichotomy** — `PUBLIC` vs `QUOTE_ONLY` vs no-rows are three distinct
   outputs; `QUOTE_ONLY` carries a null amount.
7a. **`price_max` currency safety** — the constraint is evaluated in exactly one
   currency, with no FX anywhere. Each of these must be asserted:
   - `price_max` without `price_currency` → `INVALID_ARGUMENT`;
   - `price_currency` without `price_max` → `INVALID_ARGUMENT`;
   - a EUR ceiling never evaluates a USD-only offer numerically;
   - a USD ceiling never evaluates a EUR-only offer numerically;
   - a same-currency price below the limit **qualifies**;
   - a same-currency price above the limit excludes as `above_limit`;
   - `QUOTE_ONLY` excludes as `unprovable`;
   - an UNKNOWN/absent price excludes as `unprovable`;
   - different-currency-only offers exclude as **`unprovable`, never
     `above_limit`**;
   - no converted amount appears anywhere in the response;
   - a **mixed-currency robot cannot obtain a numeric result from the
     cross-currency minimum cache** (§10.3.1) — the regression this rule exists
     to prevent.
8. **Maturity ≠ availability** — a `COMMERCIAL` robot with no current offer is
   never reported obtainable.
9. **Region eligibility** — a `GLOBAL` offer satisfies a narrower-region query
   (§12); a sibling-region offer does not.
10. **Provenance** — every commercial fact with evidence carries an
    `evidence_ref` that resolves via `get_evidence`; `verified_at: null` is
    preserved and never filled from `observed_at`; a fact with no evidence
    carries **no** `evidence_ref`; no raw database identifier appears in any
    request or response.
11. **Pagination bounds** — an out-of-range `limit`/`offset` returns
    `INVALID_PAGINATION` and is **never clamped**; `total` correct; paging is
    stable across pages.
12. **Error determinism** — each `§17` code is reachable and stable.
13. **Schema validation** — every response validates against the declared schema;
    a breaking change fails without a version bump.

## 22. Explicitly deferred capabilities

| Capability | Status |
|---|---|
| `match_robots` | **AGENT-02 v0.2** — deferred; the matching contract is untouched by this document |
| `compare_robots` | Later |
| `get_manufacturer` | Later |
| `get_current_offers`, `get_availability` | Merged into `get_robot` unless implementation evidence proves otherwise (§4) |
| Any write, lead creation, requirement capture, RFQ | **AGENT-03** — out of scope |
| Transactions, carts, checkout, payment | **AGENT-04** — out of scope |
| Account identity, API-key business logic, attribution | Not in the semantic contract (§3) |

## 23. Ratification decisions (all resolved)

The decisions this contract was drafted around (1–7) have been taken by the
product owner, and decision 8 was taken at the 2026-08-18 amendment. They are
recorded here as the reasoning behind the sections above, so a future reader can
see what was chosen and what was rejected.

| # | Decision | Resolution | Where it lives |
|---|---|---|---|
| 1 | Region eligibility | **Ratified applicability semantics**: exact region, applicable ancestor, or `GLOBAL`. Specificity stays observable; a `GLOBAL` offer may satisfy a narrower query but is never relabelled region-specific. The contract follows the frozen schema/dictionary rule rather than the exact-code behaviour the catalogue then had; that drift is now **closed**, both surfaces resolving through **one shared resolver** | §12 |
| 2 | `price_max` + `QUOTE_ONLY` | **Hard numeric constraint.** Satisfied only by a governed comparable numeric price ≤ X. `QUOTE_ONLY` and unpriced/UNKNOWN do not satisfy it, are never coerced to `0`/`false`/unavailable. **Warn-and-exclude**, with two distinct warning codes separating *unprovable* from *above limit*. **No `include_quote_only` override in v0.1** | §10.3 |
| 2a | Numeric price currency | **`price_currency` required with `price_max`** (and rejected without it) → otherwise `INVALID_ARGUMENT`. **Exact currency match, no FX** — no rates, base currency, normalisation or conversion. Other-currency prices are *incomparable*, excluded as **`unprovable`, never `above_limit`**. The `lowest_purchase_price` cache is **not** the canonical basis: its derivation takes a cross-currency minimum (§10.3.1) | §5, §10.3, §10.3.1 |
| 3 | Evidence addressing | **Opaque `evidence_ref`**, issued by the governed read layer, accepted by `get_evidence`, never constructed or parsed by a client, never a raw database identifier. Internal resolution deliberately not frozen. Unevidenced facts carry no `evidence_ref` | §7.1, §8, §13 |
| 4 | Pagination | **Canonical `docs/04` bounds reused** (default 24, max 100). Out-of-range → **`INVALID_PAGINATION`, never silently clamped**. Continuation metadata deterministic | §16, §17 |
| 5 | Tool names | **Frozen for v0.1**: `search_robots`, `get_robot`, `get_evidence`. **No aliases.** `match_robots` → v0.2; `compare_robots`, `get_manufacturer` later; `get_current_offers` / `get_availability` stay inside the robot-detail projection | §4, §22 |
| 6 | Rate limiting | Permitted at the transport/application boundary. **No numeric quota frozen in v0.1.** `RATE_LIMITED` is a valid error with retry metadata where known. Throttling must never change catalogue semantics or results | §19.1, §17 |
| 7 | Contract version | **Semantic version is `v0.1`** — the single normative answer. `agent-tools/0.1` is the wire identifier for that same version, not a second scheme. Enumerated breaking-change surface may never be altered silently | §18 |
| 8 | `sort=price` under a price constraint | **Ordering follows the qualifying price.** When `price_max` + `price_currency` are present, `price` orders by the lowest comparable amount in that currency (`RANGE` by upper bound), never by the cross-currency cache. Without a currency-constrained query the cache remains a legitimate sort basis. No standalone `price_currency` for sorting in v0.1 | §10.5 |

**No open ratification decisions remain in this contract.**

### Status

**RATIFIED v0.1 — 2026-08-17.** Amended **2026-08-18** by product-owner decision
(§10.5 sort-under-constraint, plus factual implementation-status corrections in
§5, §10.3.1 and §12, and the aligned `docs/04` price input). The semantic version
remains **v0.1**: §18 enumerates the breaking surface exhaustively, and ordering
is not among it — the result *set* of every query is unchanged, the four sort
keys are unchanged, and §16's stability requirement is preserved. §10.5 specifies
a case the original draft left under-specified rather than altering a settled
one.

Ratification authorizes **no implementation** — it never did, and that rule
stands for every future slice. A separate owner build trigger is required, per
the pattern in `docs/10`; one was given for AGENT-02, and implementation is
underway.

Drift status at this amendment:

- **§12 region — CLOSED.** Both the HTTP catalogue and `search_robots` resolve
  applicability through the one canonical shared resolver.
- **§10.3.1 price — CLOSED.** Both surfaces apply the same exact-currency
  predicate from `services/pricing.py`; the cache-based hard constraint has been
  removed from the shared filter.
- **§10.5 price sort — CLOSED.** Implemented on both surfaces from the same
  comparable-amount definition.

§21.2 semantic parity therefore holds for the region and price dimensions, on
identities and on order.

Remaining work is tracked as implementation status in the sections above, not as
unresolved semantics.
