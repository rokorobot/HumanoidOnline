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

### 4.3 Explicit negative facts (owner ruling 2026-10-03)

An explicit negative is a **factual assertion** and uses the **same governed provenance chain as a positive
fact**:

```
source statement -> proposal -> ACCEPT -> accepted claim
  -> provenance-bearing canonical specification (product- or variant-scoped, the source's own wording)
  -> registered negative projection -> resolved boolean false
```

Example: the manufacturer states `SDK not supported`. The wording is preserved as a canonical specification
with normal source provenance; only an owner-ratified rule `<registered spec key> / "SDK not supported"` ->
`has_sdk = false` may then resolve `false`. `No teleoperation support` -> `has_teleoperation = false` likewise,
and only after that exact mapping is separately ratified. The initial registry contains **no** negative
mapping.

* **`spec_caveats` is explanatory metadata only** (why a field remains UNKNOWN, or that sources disagree).
  It never establishes `false` and is never the evidence or the home of a negative.
* Absence of a positive token is never `false`; absence of an option is not absence of a broader capability.
* A core column is not a home for a new negative: a new or changed `false` (or implausible `0`) written
  directly is an integrity failure (section 13).
* **Legacy hand-entered `false` values** remain coverage review findings until sourced. Do not invent source
  wording to justify an existing `false`; when one is reviewed and no explicit negative source is found,
  prefer `NULL`/UNKNOWN.
* No schema change is required where an existing product/variant-scoped `specification` row can carry the
  wording and provenance. A negative that cannot be represented faithfully that way comes back as a semantic
  decision, never as a `spec_caveats` shortcut.

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

## 7. Integrity versus coverage (G4-3, as corrected by the owner on 2026-10-03)

> **Incomplete is publishable. Misleading is not.**
> Fresh + truthful + incomplete is preferable to complete-but-late.

HumanoidOnline is a live market-intelligence source, not a static encyclopedia: publish early, attribute
clearly, distinguish fact from uncertainty, update continuously. G4-3 therefore keeps **two separate
concepts**, and only the first may ever block publication:

| Concept | Question | Effect |
|---|---|---|
| **INTEGRITY / TRUTHFULNESS** | could the public record be materially false, self-contradictory or unverifiable? | **blocks** publication (and the integrity CI job) |
| **COVERAGE / COMPLETENESS** | how much do we know, and what could we still normalize or enrich? | **never blocks**: warnings and audit findings that feed the enrichment queue |

A robot may be `publication_integrity = PASS` with `coverage = LOW` and publish. Coverage is an internal
audit result only: **no public label and no schema field is introduced** for it.

### 7.1 Hard publication blockers (integrity)

Publication may be refused only for a condition that makes the public record materially false,
internally contradictory or unverifiable:

* **A. Identity unresolved:** we cannot establish which robot/product the record represents.
* **B. Canonical `CONFLICT` on a fact we intend to publish** (e.g. two equally current accepted statements
  for the same configuration, 76 versus 82 body DoF, with no temporal or configuration explanation).
  Never choose arbitrarily.
* **C. Public value contradicts canonical evidence** (e.g. the public output asserts a product-wide
  "supported" where the resolved state is `UNKNOWN`/`PARTIAL`, or asserts `false` where only `UNKNOWN` exists).
* **D. Fabricated precision or unsupported inference:** `NULL` converted to `false` or `0`, "planned in
  2027" converted to `2027-01-01`, a manufacturer estimate presented as MSRP, a variant-specific capability
  presented as product-wide.
* **E. Required provenance missing** for an asserted fact whose contract requires it: commercial status,
  pricing, availability, deployment, regional availability, image identity / display policy.
* **F. Publication mechanics or invariants broken:** an invalid canonical record, importer corruption, an
  unrelated catalogue mutation, a publication flag that cannot be applied deterministically.
* **G. Loss (`UNACCOUNTED_LOSS`) affecting the intended public representation** (see 7.3).

### 7.2 Never blockers (coverage)

These must **not** prevent publication by themselves: UNKNOWN physical specifications, developer
capabilities or autonomy; a missing price, availability, dimensions, runtime, payload or battery capacity;
`DETAIL_ONLY` information; `NO_CATALOGUE_HOME` facts; a manufacturer statement that has not yet gained a
semantic projection; a missing optional projection mapping; incomplete use-case classification; incomplete
historical chronology; an accepted fact safely preserved verbatim but not yet normalized into a first-class
field. A first-class property need not be populated merely for publication: *Pro — teleoperation /
Standard — UNKNOWN* is truthful and publishable without a robot-wide `has_teleoperation`.

### 7.3 Fact accounting: observability and loss prevention

Every accepted **current** fact, or atomic registered token inside a list-valued claim, is classified for
the audit as exactly one of:

* `CANONICAL_DIRECT` — written to a core column, `robot_variant` or an offer
* `CANONICAL_PROJECTED` — has a registered projection
* `DETAIL_ONLY` — deliberately preserved verbatim, with an explicit recorded reason
* `NO_CATALOGUE_HOME` — accepted knowledge with provenance and no home (e.g. the reservation fee)
* `UNMAPPED_KNOWLEDGE` — accepted and safely retained with provenance, but with **no semantic projection
  yet** (e.g. `digital twin access`, a new manufacturer-specific feature): shown as detail and recorded as
  a *projection candidate / owner mapping required*. **Not a blocker.**

and two **error** states that are not valid terminal classes:

* `UNACCOUNTED_LOSS` — accepted knowledge that should exist in the canonical/public chain but has
  accidentally disappeared (e.g. a Python SDK fact was materialized, but neither the canonical detail nor
  the resolved projection contains it). An **integrity defect**; it blocks only when the robot is about to
  be published with misleading output.
* `CONFLICT` — see section 3.

`NOT_YET_REVIEWED` (discovered or proposed information that has not crossed the human acceptance boundary)
is **not canonical knowledge**, does not affect publication eligibility, and stays in the review pipeline.

The audit reports, per robot and in total: accepted canonical facts, direct, projected, detail-only, no
catalogue home, unmapped knowledge, lost/unrepresented, conflicts. For publication, **lost = 0 for the facts
required by the intended public representation** and **conflicts = 0 for current public assertions**; detail
only, no-home and unmapped counts may be any value without blocking.

## 8. Readiness (G4-3): the integrity gate, the fresh-announcement path and the coverage audit

### 8.1 The lightweight readiness concept for a newly announced robot

A newly announced humanoid is **publication-ready** when we have, at minimum: a resolved robot identity and
manufacturer; at least one authoritative first-party or approved source; an honest commercial maturity
(`UNKNOWN` where appropriate); enough summary / identity information to explain what the robot is;
provenance for the facts actually asserted; no unresolved contradiction in those asserted facts; a safe image
state or `IMAGE_UNAVAILABLE`; and no fabricated values. Everything else may remain UNKNOWN. A manufacturer
announcing "Robot X, 80 body DoF, a new AI processor, commercial release planned in 2028" is enough for a
useful page; height, weight, payload, runtime, SDK, ROS, price, availability, battery capacity and
teleoperation are never awaited.

### 8.2 Two outputs

* **Integrity gate** (must be green): truthfulness and representation invariants, evaluated generically for
  every robot. CI fails on an integrity failure. It **never unpublishes** an existing robot by itself.
* **Coverage audit** (informational, non-blocking unless the owner explicitly upgrades it): UNKNOWN density,
  unmapped knowledge, detail-only facts, missing projections, enrichment opportunities (no price, no
  availability, no SDK evidence, no deployment evidence, historical data not yet normalized). It drives the
  enrichment queue and never suppresses a fresh page.

### 8.3 Publication transition (`is_published` false to true)

* **BLOCK:** identity ambiguity; a current canonical contradiction; a fabricated or unsupported public value;
  missing required provenance; a scoped fact falsely flattened; a known accepted fact lost from the
  canonical/public representation; an invalid image display; a destructive catalogue-invariant failure.
* **WARN / ALLOW:** missing optional facts; UNKNOWN values; `DETAIL_ONLY` facts; unmapped but preserved
  knowledge; missing normalization or projection; incomplete chronology; incomplete commercial information;
  low overall coverage.

### 8.4 Existing published robots

Low coverage never unpublishes a robot. Existing published robots stay live unless a genuine integrity
problem means their public information is materially false or unsafe. Coverage findings feed the
enrichment queue.

### 8.5 Genericity

The gate is generic and deterministic. Robot-specific golden tests (4NE1 Mini, IRON) are regressions only.

## 9. Backfill (G4-4)

G4-4 uses the **coverage audit** to find high-value enrichment opportunities across the catalogue. It is
**not** a mass requirement to normalize every fact before a robot may remain public. Priority order:
(1) public contradictions or loss, (2) fresh announced robots, (3) high-value buyer fields, (4) semantic
projections, (5) optional enrichment.

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

## 12. G4-2 implementation record (API / consumer integration)

* **Adapter:** `apps/api/app/services/resolved_facts.py` turns catalogue rows into the plain inputs of
  the pure resolver and shapes its output. It holds no semantics. Batch resolution is three queries
  (robots, variants, specifications), never one per property or variant.
* **API (additive):** `RobotDetail.resolved_facts[]` (`property`, `state`, `value`, `product_value`,
  `product_source`, `variants[]` with `slug`, `name`, `value`, projection `evidence` and verbatim
  `source_facts`, `registry_version`, `detail`). The `specs` object is unchanged and the robot-level
  columns are never written. `CompareRow.resolved` carries the per-robot state; a Teleoperation compare
  row was added. List items carry `scope_notes` and the agent search result carries `scope_notes` per
  slug ("Available on some configurations").
* **Consumers on the one resolver:** detail, compare, list filters (`has_sdk`, `ros_support`,
  `has_manipulation`: ANY-VARIANT, positive match only; an explicit `false` matches only a known
  product-wide absence), the matching inputs (conservative: only `PRODUCT_VALUE` / `UNIFORM_VARIANTS`
  true is true), the agent `get_robot` and `search_robots`. `CONFLICT` is exposed, never counted as support.
* **Web:** PR #105's client-side reconciliation (`variant-facts.ts`) is removed. The web layer only
  displays the API's resolved facts; a test forbids registry tokens in the web sources. The synthetic
  "Connectivity & interfaces" row of PR #105 is not carried over (it required token logic); those
  verbatim facts remain in the SOFTWARE long-tail group.
* **JSON-LD:** the structured data never asserted these capabilities and still does not; a test pins
  that PARTIAL / VARIES facts are not published as product-wide claims.
* **Deferred to G4-3:** generic fact accounting, the readiness / publication gate and the audit command.

## 13. G4-3 implementation record (integrity gate and coverage audit)

* **Code:** `apps/api/app/services/readiness.py` (pure; stdlib plus the G4 resolver), `readiness_loader.py`
  (a read-only DB-API loader, fixed number of queries), `db/readiness_check.py` (`integrity`, `coverage`,
  `publish`), and the publication-transition hook in `db/import_catalogue.py`.
* **Integrity (`integrity_check`)** blocks only: identity (blank name, no manufacturer, invalid slug, a
  CURRENT unresolved `POSSIBLE_DUPLICATE` / `AMBIGUOUS` candidate attached to the robot; the candidate's
  effective state is read, never the append-only history, so a resolved ambiguity does not block);
  `CANONICAL_CONFLICT`; `PUBLIC_CONTRADICTS_CANONICAL`; fabricated transformations (year-level statement to
  exact date, accepted price type changed on publication, a historical figure given a catalogue home, a
  variant flattened to product scope, a NEW `false`/implausible `0` written outside the governed
  chain of section 4.3);
  missing required provenance; broken publication mechanics; `UNACCOUNTED_LOSS`; and, only at the
  false-to-true transition, a missing or placeholder summary.
* **Public-assertion findings apply to published or publishing robots.** For an UNPUBLISHED record they are
  reported as coverage warnings ("resolve before publishing"): an unpublished stub is not a public assertion.
* **New versus legacy:** `db/catalogue/legacy_readiness_baseline.json` lists the 8 pre-existing hand-entered
  `false` values (unitree-g1, unitree-g1-edu-plus-u2, unitree-h2, unitree-r1) and the 4 published robots
  without a summary (honda-asimo, rainbow-hubo, softbank-nao, softbank-pepper). They are coverage review
  findings, never integrity failures, never unpublished, never a CI failure. A test fails when an entry has
  been fixed (the baseline may only shrink) and when any NEW unexplained `false`/zero appears in the catalogue
  source. An explicit negative is established only by the governed chain of section 4.3 (never a core
  column, never `spec_caveats`); when a legacy `false` is reviewed without a source it becomes
  `NULL`/UNKNOWN, and the entry leaves the baseline.
* **Coverage (`coverage_audit`)** has no failing outcome. It reports UNKNOWN density, no price/availability/
  SDK/deployment evidence, legacy findings, `DETAIL_ONLY` (with the recorded reason), `UNMAPPED_KNOWLEDGE`
  (projection candidates), `NO_CATALOGUE_HOME`, `NOT_YET_REVIEWED`, an informational band (LOW / PARTIAL /
  GOOD) and the fact accounting. The band thresholds are informational and never gate anything.
* **Publication transition:** `--apply-publication-state` judges every robot going false to true; an
  integrity failure aborts the whole transaction (nothing written, nothing published); coverage warnings are
  printed and allowed.
* **CI:** `db/readiness_check.py integrity` is a required step; `coverage` is an informational step that exits
  0 unless the command itself fails technically.
* **Golden:** a synthetic fresh announcement (identity, source, summary, ANNOUNCED, one technical fact, no
  price or availability, everything else UNKNOWN) is publishable with coverage LOW, and a robot that is 90%
  UNKNOWN publishes when the known part is truthful. These tests exist so the gate cannot drift into an
  encyclopedia-style completeness check.
