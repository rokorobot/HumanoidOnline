# DR-G4 — Canonical Scoped Fact Resolution

**Status:** G4-0 (architecture and semantic ratification) — ratified by the owner, 2026-10-03.
**Stage:** G4 (new). Continues the stage letters G1, G2, G3. It does **not** renumber, reinterpret or
replace any existing identifier (see §1).
**Related:** DR-A5 (claim promotion), DR-C1 (master vs public catalogue), `docs/09_MEDIA_CONTRACT.md`,
`docs/20_AGENT_TOOL_CONTRACT.md`.

## 0. The problem and the target invariant

Accepted knowledge can exist at **variant scope** (e.g. the 4NE1 Mini *Standard* lists a Python SDK, the
*Pro* adds a C++ SDK and teleoperation) while the robot-level core column is NULL. A consumer that reads
only the core column then reports a blanket `UNKNOWN` although HumanoidOnline holds the information.

> **`UNKNOWN` means: HumanoidOnline has no accepted canonical knowledge for this property at product or
> variant scope. It never means "we have the information but the projection failed to expose it."**

PR #105 repaired the *detail page* only. The same core columns also feed list filters, the deterministic
matching engine, the agent tools, compare and JSON-LD. G4 introduces **one** resolver that all of them use.

## 1. Identifiers (history preserved)

| ID | Meaning |
|---|---|
| **G4** | Canonical Scoped Fact Resolution (this record) |
| **G4-0** | architecture + semantic ratification (this document, the design pins in tests) |
| **G4-1** | pure resolver + versioned projection registry |
| **G4-2** | API / read-model integration (detail, list filters, matching inputs, compare, agent tools, JSON-LD) |
| **G4-3** | readiness / audit gate and fact accounting |
| **G4-4** | catalogue-wide read-only backfill audit |

DR-A5 §18 defines **G2-6 — a second manufacturer** (separate source and ToS approval, adapter and
extractor; "This is Stage G3"). That milestone is **satisfied in substance** by the XPENG / Stage G3 work
(owner source approval 2026-10-03; adapter, extractor and scheduled ingest). G2-6 is **not** renumbered or
repurposed; DR-A5 §18 carries a one-line amendment recording this. No `G2-7` or later exists.

Each G4 phase is its own PR, and approval of one phase never authorizes the next.

## 2. Truth model (one coherent truth)

```
accepted claim  ->  catalogue JSON  ->  robot core columns | robot_variant | specification | offers
                    (M2, DR-A5)         (importer, DR-C1)
```

* **Accepted claims** are the governed origin of every discovered fact (DR-A5).
* **Catalogue JSON** is the canonical record; the importer loads it.
* **Variant-scoped `specification` rows** (`specification.variant_id`) are first-class canonical catalogue
  data. They are *not* a footnote to the robot-level columns.
* **Robot core columns** (`has_sdk`, `ros_support`, ...) hold **product-scope** values only.
* **`robot_variant.spec_overrides` is not used.** It is untyped JSONB with no per-fact provenance, nothing
  writes or reads it, and it is not exposed by the API. G4 neither populates nor relies on it.
* **Resolved facts are derived, never stored, never a second source of truth:**

  `resolved_fact = f(product core value, scoped canonical facts, projection registry version)`

  A resolved value is **never written back** into a robot-level column.
* **No derived database table** at this stage. Compute-on-read at the current scale (57 robots; two with
  variants; one with variant-scoped specifications). A derived/indexed read table is reconsidered only
  under the conditions in §10.

## 3. Resolution states

| State | Definition |
|---|---|
| `PRODUCT_VALUE` | an explicit product-scope canonical value exists (the core column, or a product-level registered projection). Authoritative for product scope **unless scoped evidence contradicts it** |
| `UNIFORM_VARIANTS` | every applicable documented variant has a known value and they agree |
| `VARIES_BY_VARIANT` | every applicable documented variant has a known value and at least two differ |
| `PARTIAL_VARIANTS` | at least one variant has a known value and at least one applicable variant is unknown |
| `UNKNOWN` | no accepted canonical knowledge for the property at product or variant scope |
| `CONFLICT` | canonical facts disagree in a way scope cannot explain. An **integrity failure**: it fails readiness / publication gating. A product value never silently wins over contradictory accepted evidence |

"Applicable documented variants" are the robot's `robot_variant` rows. A robot with no variants resolves
from product scope only.

## 4. Projection registry contract

A **single versioned registry** maps a registered specification key plus a registered, normalized token to a
canonical property and value:

```
(registered spec key, registered normalized token)  ->  (canonical property, value)
```

Rules:

1. **Exact matching only.** A token is the whitespace-normalized text between commas (a single-valued key
   such as `dexterous_hand_option` is one token). Comparison is exact and case-sensitive. No substring
   search, no stemming, no fuzzy match, no LLM interpretation during resolution.
2. **One registry.** No consumer scatters its own substring search.
3. **Projection is additive.** The verbatim accepted fact stays; the boolean never replaces it. The page and
   the agent still show "Dexterous hand option — Not included" next to any projected value.
4. **Absence is never false.** A variant without a token has no value for that property (unknown).
5. **A negative boolean** may come only from wording that explicitly negates the actual canonical property
   (e.g. `No teleoperation support`, `SDK not supported`, `ROS not supported`), and only after a separate
   registry ratification. *Absence of an option is not absence of a capability.*
6. **Unregistered wording is `DETAIL_ONLY`**, never `UNKNOWN`, and never inferred. The audit surfaces it as
   *projection candidate / owner mapping required*.
7. **Every new mapping is an owner decision** (like a claim policy) and bumps the registry version.

### 4.1 Initial registry (ratified 2026-10-03)

| Spec key | Exact token | Projects |
|---|---|---|
| `common_interfaces` | `Python SDK` | `has_sdk = true` |
| `additional_interfaces` | `C++ SDK` | `has_sdk = true` |
| `common_interfaces` | `ROS 2 interface` | `ros_support = true` |
| `additional_interfaces` | `teleoperation` | `has_teleoperation = true` |
| `dexterous_hand_option` | `12 DoF dexterous hands` | `has_manipulation = true` |

Either SDK token suffices for `has_sdk`; the language/tooling distinction stays in the detailed spec. The
`ROS 2 interface` token is **not** evidence of API support, and a generic SDK is **not** evidence of ROS.

**Explicitly NOT mapped (ratified rulings):**

* `dexterous_hand_option: Not included` does **not** project `has_manipulation = false`. It says only that
  the named hand option is not included in that configuration, not that the robot has no manipulation
  capability. For the Mini *Standard*, `has_manipulation` stays unknown; the detailed fact is retained.
* `12 DoF dexterous hands` does **not** derive `hand_dof = 12`: the hand-DoF convention (per hand) and the
  source scope do not independently permit it.
* `digital twin access`, `ready for Neura Gym training`, `Wi-Fi 6`, `Ethernet`, `NEURA Sync` are
  `DETAIL_ONLY` until a canonical property exists.
* Each of `teleoperation`, `ROS 2 interface`, `Python SDK` projects only **true**, never false.

### 4.2 Token drift

* An accepted current fact **with a registered projection that the resolver then loses** is a **FAIL**.
* **Source wording changes** and produces a new accepted fact with no registered mapping: the fact is
  `DETAIL_ONLY` and the audit reports it as *projection candidate / owner mapping required*. It is not
  `UNKNOWN` (the detailed fact is known) and not a production failure.

## 5. Resolution algorithm (deterministic)

For one robot and one property `P`:

1. `product` = the core column value if non-null, else the product-level (no variant) registered projection
   for `P`, else none.
2. For each documented variant: its value = the registered projection of that variant's specification rows
   for `P`, else unknown.
3. If any value (product or variant) is `true` and another is `false`, and the difference is not explained
   by scope (a product value contradicted by a variant value) -> `CONFLICT`.
4. Else if `product` exists -> `PRODUCT_VALUE`.
5. Else if no variant has a value -> `UNKNOWN`.
6. Else all variants known and equal -> `UNIFORM_VARIANTS` (value); all known and at least two differ ->
   `VARIES_BY_VARIANT`; some unknown -> `PARTIAL_VARIANTS`.

Identical input and registry version always give identical output (pure, no I/O, no randomness).

### 5.1 Expected 4NE1 Mini resolution (golden, pinned in `tests/fixtures/g4/`)

| Property | Standard | Pro | Overall |
|---|---|---|---|
| `has_sdk` | true | true | `UNIFORM_VARIANTS` = true |
| `ros_support` | true | true | `UNIFORM_VARIANTS` = true |
| `has_teleoperation` | unknown | true | `PARTIAL_VARIANTS` |
| `has_manipulation` | unknown | true | `PARTIAL_VARIANTS` |

No false value is fabricated. The Standard `Dexterous hand option — Not included` stays visible.

## 6. Consumer semantics (G4-2)

* **Detail page:** shows the resolved state and the verbatim detail; supersedes PR #105's client logic with
  the API's resolved facts (one source).
* **Compare:** exposes the resolved scoped state without collapsing it ("Supported on all documented
  configurations", "Pro only", "Some configurations; others unknown").
* **Agent / MCP tools:** use the same resolver and expose property key, state, product value, variant
  values and provenance, so agents can tell `UNKNOWN` from `PARTIAL_VARIANTS` from `VARIES_BY_VARIANT`.
* **Filters (discovery) — ANY-VARIANT:** a positive capability filter matches a robot when at least one
  current configuration has it. The result carries scope metadata and is labelled "Available on some
  configurations" when it is not product-wide. This is a search projection only and never mutates
  `robot.has_sdk`.
* **Matching engine — CONSERVATIVE:** only `PRODUCT_VALUE = true` and `UNIFORM_VARIANTS = true` satisfy a
  required boolean capability at robot scope. `VARIES_BY_VARIANT`, `PARTIAL_VARIANTS`, `UNKNOWN` and
  `CONFLICT` do not; they resolve as unknown/ineligible for a hard requirement. Variant-aware matching is a
  later step.

## 7. Fact accounting (G4-3)

Every accepted **current** fact, or atomic registered token inside a list-valued claim, ends in **exactly
one** class:

* `CANONICAL_DIRECT` — written to a core column, `robot_variant` or an offer
* `CANONICAL_PROJECTED` — has a registered projection
* `DETAIL_ONLY` — verbatim specification with **an explicit recorded reason**
* `NO_CATALOGUE_HOME` — accepted knowledge with provenance and no home (e.g. the reservation fee)

`CONFLICT` is an **error state**, not a terminal class. Invariant: **`unaccounted = 0`**.

## 8. Readiness / publication gate (G4-3)

The generic gate fails publication and CI when any of the following holds:

* accepted facts are unaccounted;
* a registered projection is missing;
* canonical facts are in `CONFLICT`;
* the public resolved output is blanket `UNKNOWN` despite registered canonical scoped evidence;
* scoped facts are flattened into a false universal product claim.

The gate is generic. Robot-specific golden tests (4NE1 Mini, IRON) are regressions only.

## 9. Backfill (G4-4)

A **read-only** audit first. It reports robots inspected, accepted facts, `CANONICAL_DIRECT`,
`CANONICAL_PROJECTED`, `DETAIL_ONLY`, `NO_CATALOGUE_HOME`, conflicts, unaccounted, and the public
resolved-value changes that would result. The audit applies already ratified mappings mechanically and never
introduces new semantic mappings; new mappings return as owner decisions.

## 10. Filtering implementation and the derived-table threshold

Use the simplest correct implementation: application-layer filtering after resolution. A derived, indexed
read table is reconsidered only if **either** the published catalogue grows to the point where per-request
resolution measurably breaks the performance budgets (`apps/web/scripts/perf-budget.mjs`), **or** SQL-level
filtering/ordering over resolved facts becomes a product requirement that application-layer filtering
cannot meet. Until then correctness and one truth model outrank query optimization.

## 11. Impact summary

| Area | G4-0 | G4-1 | G4-2 | G4-3 | G4-4 |
|---|---|---|---|---|---|
| Schema migration | none | none | none | none | none |
| API contract | none | none | additive (`resolved_facts`) | none | none |
| Catalogue JSON format | none | none | none | none | none |
| Stored data | none | none | none | none | none |
