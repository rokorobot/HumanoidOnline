# DR-A5 — Governed Claim Proposal Review and Promotion Boundary

| | |
|---|---|
| **Status** | **DECIDED — RATIFIED, 2026-10-02, Robert Konecny (product owner).** The decisions are adopted; **implementation has not begun** (§18). |
| **Raised** | 2026-10-02 |
| **Decision owner** | Robert Konecny (product owner) — sole ratifying authority |
| **Stage** | Stage G2 of the discovery programme (`docs/08_DEVELOPMENT_ROADMAP.md` §1.1) |
| **Builds on** | Stage G1, PR #84 (`neura_mini_proposals.py`); `docs/16` §17.1 (Stage E review), §17.2 (Stage F observation) |
| **Amends** | `docs/16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md`: new §17.3 (the normative text) |
| **Related** | `DR-C1` (publication is editorial), `DR-A4`, `docs/03` §6–§7 (NULL semantics, provenance), AGENTS.md rules 2, 6, 7 |
| **Schema / code / migration** | **None in this record.** The persistence boundary in §6 is logical and illustrative, not DDL. Implementation is separate, reviewed PRs (§18). |

**Numbering.** This repository does not use sequential ADR numbers (that scheme belongs to
Cloudeo). Decision records here are `DR-<series><n>` under `docs/decisions/`: `DR-A1`, `DR-A2`,
`DR-A4` and `DR-C1` exist, and amendment A3 lives in `docs/26`. The A-series amends the DATA-D1.LIVE
acquisition contract, which is what this record does, so **`DR-A5` is the next free number in that
series. The owner confirmed this number on ratification (2026-10-02).**

This record captures **why the decision was asked for and what turns on it**. The normative text
is `docs/16` §17.3; where the two differ, §17.3 governs.

---

## 0. Summary and ratified decisions

| Question | Ratified decision |
|---|---|
| Where do extraction proposals live? | **Approach B′**: a *dedicated, immutable* proposal store, with **append-only human decisions** and a separate **accepted-claim** store. Not `candidate_claim` (A), not artifacts-only (C). |
| How does an accepted claim reach the catalogue? | Through a **governed materialization into the catalogue of record (`db/catalogue/`), applied by the existing importer** (boundary M2). **Direct production database writes are not used for G2 catalogue facts** (§11). |
| What is built first? | One vertical slice on `4ne1-mini`, in this order: **Standard → robot variant; Pro → robot variant; then ONE specification**, which materializes only through an **explicitly proposed, approved and registered field policy** (§11.3). The specification's target is **not** chosen by this record. |
| What stays open? | The seven G1 findings (§13) are designed for and **not decided**. **Price and availability are DEFERRED** as separate owner decisions (§13). |

Three facts found while preparing this record shape it. They are verified against the repository
and are **not** assumptions.

1. **The importer replaces facts.** For any robot with a JSON file in `db/catalogue/robots/`,
   `db/import_catalogue.py` deletes and re-inserts that robot's `robot_variant`, `pricing_offer`,
   `availability_offer`, `deployment`, `robot_capability`, `use_case_fit` and `robot_image` rows
   and rewrites its spec columns from the JSON on **every run**. A fact written straight into the
   database for such a robot would be silently reverted.
2. **Terminal candidates receive no claims.** The adapter run records an observation for a
   `PROMOTED` or `REJECTED` candidate and attaches nothing (`adapter_run._product`). The `4NE1 Mini`
   candidate is already `PROMOTED`, so the existing claim path **cannot** carry its proposals.
3. **`candidate_claim` is mutable and conflates layers.** Its `claim_status` is changed in place,
   and `VERIFIED` is set on the same row by a trace confirmation (`record_trace(confirmed_fields)`).
   Parser output and human acceptance share one row and one status word.

---

## 1. Context

### 1.1 What exists today

```
fetched_page (immutable observation) ──► candidate_claim / candidate_commercial_signal
                                          (parser output, NOT_VERIFIED, mutable status)
                                                        │ record_trace(confirmed_fields) sets VERIFIED
                                                        ▼
                                          promote(): writes ONLY height_cm, weight_kg,
                                          payload_kg into `robot`, plus an EvidenceSource row
                                          and a promotion_audit row
```

- Promotion is a **human act**; the approved field set is three robot columns
  (`promotion._APPROVED_FIELDS`). Everything else a claim could say is unwritable.
- `promotion_audit` and `candidate_identity_decision` are append-only. The identity-decision table
  is enforced by database triggers; **`promotion_audit` is enforced only by an ORM listener** (§19).
- The canonical schema can already hold what G1 proposes: `robot_variant`, `specification` (with
  `variant_id`, `edition_scope`, `managed_by`), `pricing_offer`, `availability_offer` and
  `evidence_source`.
- The verified catalogue is **authored as code**: JSON under `db/catalogue/`, loaded by
  `db/import_catalogue.py`, with `db/catalogue_entries.py` for stubs. The database is the loaded,
  derived copy of that catalogue (and `is_published` is deliberately not importer-owned, DR-C1).

### 1.2 What G1 established

`propose_neura_mini_claims` returns 20 unverified, evidence-bearing proposals for the Mini page
(`VARIANT` ×2, specifications, estimated prices, reservation fees, availability, terms, interfaces,
use cases, a datasheet reference), each with a digest, a verbatim bounded excerpt, a logical
locator and explicit review questions. It writes nothing and is not wired into observation.

G1's findings, to be designed for here without being decided: the edition dimension; the semantics
of a manufacturer's own *estimated* price; the reservation deposit and its terms; "expected in
2026" availability; free-text use-case mapping; interface/connectivity mapping; and promotion
beyond height, weight and payload (§13).

---

## 2. Six layers, and the rule between them

```
source observation      what bytes the source returned, when, from where
        ↓
parser interpretation   what a deterministic extractor read from those bytes
        ↓
proposal                an unverified, evidence-bearing statement ABOUT what the source says
        ↓
human factual acceptance a named human confirms the extraction is faithful AND resolves how it is meant
        ↓
catalogue representation the accepted claim written into a catalogue field/row, with evidence
        ↓
publication             a separate editorial decision (DR-C1)
```

**A value may validly exist at one layer without being promoted to the next.** For example, "a
refundable 100 € reservation fee" can be a faithful observation, a correct interpretation, a
proposal, and even an *accepted* statement, and still have **no catalogue representation**. The
design makes "accepted, no catalogue home" a first-class outcome, not an error.

| Layer | Artifact | Mutable? | Who/what creates it |
|---|---|---|---|
| Observation | `fetched_page` + cached body | no | acquisition (existing) |
| Interpretation | extractor output + digest | no (pure) | a deterministic extractor |
| Proposal | persisted proposal | **no** | an ingest step (never a reviewer) |
| Acceptance | decision, then accepted claim | **no** (append-only) | a named human, via a governed command |
| Representation | catalogue change + audit row | change is governed; audit append-only | the materialization boundary (§11) |
| Publication | `robot.is_published` | editorial | a separate human decision |

---

## 3. Decision (ratified)

1. **Proposals are persisted as immutable records** in a dedicated store, separate from
   `candidate_claim`. `candidate_claim` is not extended or overloaded.
2. **A proposal is never a claim.** Only an explicit human `ACCEPT`, which resolves every open
   question, can create an **accepted claim**, itself an append-only record with full lineage.
3. **Human decisions are append-only** (`ACCEPT` / `REJECT` / `DEFER`), attributed, with a mandatory
   rationale and the human's explicit resolution of each review question. The newest decision per
   proposal is effective; a reversal is a new row.
4. **Supersession and staleness are derived, not stored as mutable state.** A new proposal in the
   same *slot* supersedes the old one; a proposal the latest observation no longer confirms is
   stale. Neither can be accepted or materialized.
5. **The catalogue is changed only by a governed materialization** of accepted claims through a
   registered **field policy**. The boundary is a **deterministic, reviewable change to the
   catalogue of record (`db/catalogue/`), applied by the existing importer through the normal PR
   and validation path** (§11). Direct production database writes are **not** used for G2
   catalogue facts. It never touches `is_published`.
6. **Observation never decides.** The observation/extraction path and the review path run with
   separate, least-privilege database roles (§16).
7. **No new field is promotable until it is registered** in a code-reviewed field policy registry.
   Today that registry is the three approved robot columns; each addition, including the first
   slice's, is proposed and approved explicitly (§11.3).
8. **Unknown stays unknown.** An unresolved question produces no write and no default.

---

## 4. Persistence approaches compared

Four approaches were evaluated against sixteen criteria. **✅** = met by design,
**⚠** = met only with caveats or extra machinery, **❌** = not met.

- **A.** Extend or overload `candidate_claim`.
- **B.** A dedicated, *mutable* proposal table (status column updated on review).
- **B′.** Immutable proposal rows + append-only decisions + accepted claims **(ratified)**.
- **C.** Proposals stay immutable *extraction artifacts*; persist only decisions and references.

| Criterion | A. `candidate_claim` | B. mutable proposal table | **B′. immutable + append-only** | C. artifacts + decisions only |
|---|---|---|---|---|
| Edition / variant dimension | ❌ no column; unique-by-value rows | ✅ | ✅ | ⚠ lives in the artifact, copied into each decision |
| Immutable source provenance | ⚠ rows are updated in place (`claim_status`, `updated_at`) | ⚠ status columns mutate | ✅ DB-trigger immutable | ✅ while the artifact exists |
| Observation / run linkage | ✅ `fetched_page_id`, `crawl_run_id` | ✅ | ✅ plus a re-sighting record per observation | ⚠ implicit |
| Deterministic proposal identity | ❌ none | ✅ digest | ✅ digest + slot, unique | ✅ computed, not stored |
| Supersession when content changes | ❌ no slot concept | ⚠ by updating a row | ✅ derived from slot ordering | ⚠ implicit, recomputed |
| ACCEPT / REJECT / DEFER | ❌ status vocabulary is parser/verification, not decision | ⚠ a status column | ✅ append-only decisions | ✅ |
| Reviewer identity | ⚠ only `trace_verified_by` on the candidate | ⚠ | ✅ per decision | ✅ |
| Decision rationale | ❌ | ⚠ | ✅ mandatory | ✅ |
| Idempotency | ⚠ | ✅ | ✅ unique digest; no-op repeat decision | ⚠ re-derivation needed |
| Replayability | ⚠ | ✅ | ✅ stored excerpt + hash; re-extraction while the body is retained | ❌ after Gate Q pruning or an extractor change |
| Stale-proposal detection | ❌ | ✅ | ✅ | ⚠ must recompute from a body that may be gone |
| Accepted-claim lineage | ❌ the flag shares the row; lineage sits in `promotion_audit.detail` JSON | ⚠ | ✅ explicit FKs | ⚠ |
| Catalogue-write audit | ⚠ `promotion_audit`, free-text `action`, ORM-only immutability | ⚠ | ✅ dedicated, trigger-enforced | ⚠ |
| Rollback / correction | ❌ in-place edits | ⚠ edits | ✅ retraction and correction are new rows | ⚠ |
| Least-privilege execution | ❌ the observation role writes the table promotion trusts | ⚠ | ✅ observer inserts proposals only; reviewer inserts decisions only | ✅ (nothing to write) |
| Multiple manufacturers later | ⚠ candidate-scoped | ✅ | ✅ source-scoped | ✅ |

**A fails decisively, and for a concrete reason, not only on the matrix:** the Mini candidate is
`PROMOTED`, and the runner attaches nothing to a terminal candidate. Entity-level claims about an
already-promoted robot (the normal case once the first promotion is done) would have **no row to
live on**. A would also force an edition column onto a scalar `(field, value, unit)` row, and its
`VERIFIED` flag would keep parser output and human acceptance on one mutable record.

**B** is the right shape with the wrong discipline: a status column that reviewers update makes
the proposal itself a moving target and loses who changed what. **C** is attractive (nothing to
store) but not replayable: Gate Q keeps only the latest body per URL and prunes superseded bodies
after 90 days, and the extractor version changes what a body yields, so a decision that references
only a digest cannot be re-audited later.

**B′ is B's shape with C's immutability.** Proposals are written once. Everything that changes
over time is a new, append-only row that points at them.

---

## 5. Lifecycle and state machine

State is **derived** from append-only rows. There is no mutable status column on a proposal.

### 5.1 Proposal states

```
                ingest (idempotent on slot + digest)
                       │
                       ▼
                 ┌──────────┐   a newer proposal appears in the same slot
                 │ PROPOSED │ ─────────────────────────────────────────────► SUPERSEDED  (terminal)
                 └────┬─────┘
        human decision │ (newest decision is effective)
   ┌────────────┬──────┴──────┬─────────────┐
   ▼            ▼             ▼             ▼
 ACCEPTED    REJECTED      DEFERRED      (no decision)
   │            │             │
   │            └─ a later decision may reverse any of these (new row) ─┘
   │
   │  the latest observation no longer confirms the digest,
   ▼  or the source page is gone, or the extractor is retired
 STALE  (overlay: cannot be accepted, and an acceptance cannot be materialized)
```

- `SUPERSEDED` and `STALE` are overlays computed against the **current** observation set, so they
  are reproducible and never stored.
- A decision on a superseded proposal remains **history**. It can never create or materialize a
  claim.

### 5.2 Accepted-claim states

```
 ACCEPT decision (all questions resolved, proposal CURRENT)
        │
        ▼
 ACCEPTED_CLAIM ──► materialize (§11) ──► MATERIALIZED ──┬─► RETRACTED   (retraction row; catalogue correction is a new change)
        │                                                  └─► SUPERSEDED  (a newer accepted claim for the same target)
        └─ "no catalogue home": stays ACCEPTED_CLAIM, never materialized (by design)
```

### 5.3 Guards (all enforced in code and tested)

| Transition | Guard |
|---|---|
| ingest | idempotent on `(slot, digest)`; identity gate passed; never writes a decision |
| ACCEPT | proposal is CURRENT and not STALE; named human; non-blank rationale; every review question resolved or explicitly marked "no catalogue home"; any prerequisite (e.g. the variant) already accepted |
| REJECT / DEFER | named human; rationale; no catalogue effect |
| accepted claim | created only from an effective ACCEPT; one per `(decision, target)` |
| materialize | the claim is current; its target is a **registered** field policy; the robot exists and is catalogue-backed; the output is deterministic |

---

## 6. Persistence boundary (logical, illustrative; not DDL)

Names and columns below describe responsibilities and key attributes. The physical design,
constraints and migration belong to the implementation phase (G2-1), as its own reviewed PR.

| Entity | Role | Immutability |
|---|---|---|
| **proposal** | One extracted statement about a source: source and page, extractor key/version, **slot key**, **digest**, kind, `edition_label`, target hint, verbatim value, structured parts, representability, gap, review questions, bounded verbatim excerpt, locator, observation (page hash, run, retrieved-at) | **write-once**; UPDATE/DELETE refused by DB trigger |
| **proposal_observation** | Each later sighting of the *same* proposal: page, run, observed-at. Records "still true on this date" without duplicating the proposal | append-only |
| **proposal_decision** | `ACCEPT` / `REJECT` / `DEFER`: proposal, decided-by, rationale, **resolved choices** (the human's answers, §13), decided-at, sequence | append-only; newest effective |
| **accepted_claim** | A confirmed claim: decision, proposal, robot, optional variant/edition, catalogue target or `NO_CATALOGUE_HOME`, typed accepted value, evidence plan | append-only |
| **claim_retraction** | Withdraws an accepted claim (who, why) | append-only |
| **catalogue_write_audit** | Every materialization: accepted claim, applied-by, method and reference (change set / commit / importer run), target rows, before/after content hashes | append-only; DB-trigger enforced |
| **field policy registry** | Which targets are promotable and how: type, unit, bounds, whether commercial (evidence required), representation rules | **code**, reviewed like any code |

Notes:

- The **slot key** identifies *what the proposal is about*: `(source, page URL, kind, edition,
  row locator)`. A changed value on the same slot produces a **new** proposal in that slot, and
  the old one becomes `SUPERSEDED`.
- A proposal anchors to **identity**, not to a candidate's lifecycle: it references the source and
  page, and the robot it concerns once that is known, so it works for a `PROMOTED` candidate.
- No existing table is altered by this boundary. `candidate_claim`, `candidate_commercial_signal`
  and `promotion_audit` keep their current roles for the current promotion path.

---

## 7. Provenance model

Every catalogue fact written under this design resolves, by foreign keys and stored hashes, back
through the six layers:

```
catalogue row ── catalogue_write_audit ── accepted_claim ── proposal_decision (who, why, resolved choices)
                                                                │
                                                        proposal (extractor@version, slot, digest,
                                                                  verbatim excerpt, locator)
                                                                │
                                              proposal_observation(s) ── fetched_page (url, run, retrieved_at,
                                                                         content_hash) ── cached body (raw sha256)
```

- The **excerpt and page hash are stored on the proposal**, so the chain survives cache pruning;
  only *re-extraction* depends on the body still being retained.
- At materialization the canonical `evidence_source` row is built **from this chain** (source URL,
  source type, excerpt, `observed_at` from the observation, `verified_at` from the human decision),
  satisfying AGENTS.md rule 7 (no commercial fact without evidence).
- Provenance is never edited. A correction is a new, linked row.

---

## 8. Review semantics

- **Reviewer** is an attributed human, recorded per decision, using the attribution convention
  already in use (the human's identity, "recorded by" the agent when an agent executes the command
  on instruction). The system cannot prove identity; it makes an unattributed decision impossible.
- **An agent never decides.** The review commands record what a named human decided; extraction
  and ingest run under a role that cannot write decisions (§16).
- **ACCEPT means two confirmations in one attributed act:** (1) *fidelity*, the extraction faithfully
  reflects the excerpt; and (2) *representation*, the human's explicit answers to the proposal's
  review questions (e.g. which `price_type`, which availability status, which specification key,
  whether this is "no catalogue home").
- **REJECT** means not faithful, not wanted, or out of scope; it blocks nothing else.
- **DEFER** records "needs more information" and has **no** downstream effect.
- **Resolution is explicit, never inferred.** If a question is unresolved, ACCEPT is refused
  rather than defaulted.
- **One proposal may yield several accepted claims** (for example a mixed "interfaces" cell split
  into several specification rows), each citing a verbatim part of the same excerpt and the same
  proposal lineage. The split is the human's, never the extractor's.
- Decisions are **idempotent**: repeating the effective decision with the same resolved choices
  writes nothing, as `record_identity_decision` already does.

---

## 9. Supersession and staleness

| Situation | Behaviour |
|---|---|
| The page re-observed with an unchanged value | a new `proposal_observation` only; no new proposal; the existing decision stands |
| The value or wording changes | a **new proposal** in the same slot (new digest); the old becomes `SUPERSEDED`; prior decisions stay as history; re-review is required |
| The source page removed (404/410) or the slot no longer extracted | the proposal becomes `STALE` (computed); it cannot be accepted or materialized |
| The extractor version retired or the identity gate fails | affected proposals are `STALE`; nothing is deleted |
| An accepted claim whose proposal was superseded | stays as a historical statement ("as retrieved at T"); **materialization refuses** until a current proposal is accepted |
| A cosmetic page change (navigation, footer) | no proposal changes: G1's extractor already ignores it, verified against the real 2 October change |

---

## 10. Idempotency and replay

- **Ingest:** unique on `(slot, digest)`. Re-ingesting the same observation changes nothing; a new
  sighting adds one `proposal_observation`.
- **Decision:** the same effective decision with the same resolved choices is a no-op.
- **Accepted claim:** one per `(decision, target)`; re-running claim creation is a no-op.
- **Materialization:** the output is a pure function of the accepted claims and the current
  catalogue file. Running it twice yields a byte-identical change, and applying an already-applied
  change yields no diff.
- **Replay:** from the stored proposals, decisions and registry version, the accepted claims rebuild
  with identical content hashes. Re-extraction from the *body* is replayable only while the body is
  retained (Gate Q); the stored excerpt and page hash are the durable record.

---

## 11. Catalogue mutation boundary

### 11.1 Why this is the hardest question

The repository has **two** places a catalogue fact can live, and they are not equal: the JSON
catalogue of record, and the database loaded from it. Today the database also receives
directly-written robots (`promote()` creates and links robots; `4ne1-mini` exists **only** in the
database, with no JSON file).

| Boundary | What it is | Verdict |
|---|---|---|
| **M1. Direct database write** by a governed command (the shape of today's `promote()`) | Fast and simple | **Rejected for G2 catalogue facts (owner decision, 2026-10-02).** It is also unsafe today for any JSON-backed robot: the next import reverts variants, offers and spec columns. Reconsidering it would need importer ownership rules for discovery-managed rows (as `specification.managed_by` already does for specs) and a **new decision record**. |
| **M2. Materialize into the catalogue of record, applied by the importer** | A deterministic, reviewable change to `db/catalogue/robots/<slug>.json`, merged through the normal PR ritual (CI runs `validate_catalogue.py`, the G2 evidence gate and importer idempotency), then loaded by the importer | **Ratified boundary.** It reuses owner review, CI and the existing import, and it cannot be silently reverted. |
| **M3. Hybrid** | DB-managed discovery rows plus importer carve-outs | Not adopted: needs importer changes and a new ownership model, hence a new decision record. |

### 11.2 Flow (M2)

1. **Precondition.** The robot must be catalogue-backed (a JSON file exists). A DB-only promoted
   robot first gets an identity-only stub through the existing `db/catalogue_entries.py`, a
   separate reviewed change (`4ne1-mini` currently needs one; see §19).
2. **Materialize.** A governed command renders the **pending accepted claims for one robot**
   through the field policy registry into a deterministic patch of that robot's JSON. It touches
   only registered keys, preserves everything else, builds the evidence blocks from the provenance
   chain, and refuses anything stale, unregistered or unresolved. `--dry-run` shows the diff.
3. **Review and merge.** The patch goes through a normal PR. The owner reviews the diff.
4. **Apply.** The existing importer loads it, using the existing operator ritual (checkpoint,
   migrations first, then import).
5. **Verify and record.** A verification command compares the database rows with the accepted
   claims and appends a `catalogue_write_audit` row (who, change reference, importer run, row ids,
   before/after hashes). Only then is a claim `MATERIALIZED`.

### 11.3 Registry and the "beyond height/weight/payload" finding

Each promotable target is a registry entry (type, unit, bounds, commercial or not, and for
edition-scoped targets the variant rule). An unregistered target is refused. The initial registry
is exactly today's three robot columns; every addition is a reviewed code change.

**No field mapping is chosen by default.** A target's exact mapping is **explicitly proposed and
approved by the owner before it is registered**, and the extractor's `target` hint is only a hint.
A registry proposal must state: the target (table and key); why it is semantically correct for
this source statement; how the value is represented, including any caveat; what the mapping
loses or cannot say; and its validation rules.

**First slice.** The order is fixed: `Standard` → a `robot_variant`; `Pro` → a `robot_variant`;
then **one** specification as the first edition-scoped factual materialization. That
specification does not materialize until its own registry proposal is approved. If
`specification[dexterous_hand_option]` is the candidate (as G1's hint suggests, and which is
**not a decision**), the proposal must first show why it is semantically correct: what the
definition means, how the "Manipulation" row's values ("Not included" and "12 DoF dexterous
hands") fit it, and what it does not say.

---

## 12. Publication separation

Publication is the editorial act of DR-C1. Under this design:

- no G2 operation reads, writes or implies `is_published`; materialization **never** sets it and the
  importer preserves it;
- an accepted claim, a materialized fact, and a published robot are three different states;
- a test asserts that every G2 command leaves `is_published` byte-identical.

---

## 13. The G1 findings: designed for, not decided

The design supplies a **mechanism** for each. The substantive answer is the owner's, recorded per
decision in `resolved choices` and, where it is a rule, folded into the registry by a reviewed
change. Each is **OPEN**, and two are explicitly **DEFERRED** by the owner (below).

| Finding | What the design provides | Options (none chosen) |
|---|---|---|
| **Edition dimension (Standard / Pro)** | `edition_label` on every proposal and accepted claim; an edition-scoped claim requires its `VARIANT` accepted first; a claim can never create a robot; catalogue representation is `robot_variant` plus `specification` rows with `variant_id` and `edition_scope` | variant slug/name wording; whether identical cells in both editions collapse to a product-level fact |
| **Manufacturer's own *estimated* price** | A price proposal carries an open `price_type` question the human must resolve | (a) a new `price_type` value for a manufacturer estimate (schema change, API and UI impact); (b) reuse `ESTIMATED`, whose documented meaning is a *HumanoidOnline* estimate, which overloads it; (c) no `pricing_offer` yet: accepted with `NO_CATALOGUE_HOME` until decided |
| **Reservation deposit and terms** | A first-class "accepted, no catalogue home" outcome, with the claim and its evidence preserved | stay unrepresented; record in an offer note; a new field |
| **"Expected in 2026" availability** | Open `availability_status` and date-precision questions; the date arrives as year-level text | `available_from` as a year-level date with an explanatory note (existing precedent); WAITLIST vs PREORDER; a precision field |
| **Free-text use cases** | The extractor never maps. The human selects the controlled use-case rows explicitly in the decision | a selection list per decision; no automatic mapping, ever |
| **Interfaces / connectivity** | One proposal may yield several accepted claims, split by the human with verbatim sub-excerpts | which `spec_definition` keys; whether new keys are needed |
| **Promotion beyond height / weight / payload** | The field policy registry (§11.3) | which targets to register first, and their validation |

**Price and availability are DEFERRED (owner decision, 2026-10-02).** They remain separate
owner decisions, and until the owner decides:

- NEURA's manufacturer-estimated price is **not** mapped to the existing HumanoidOnline
  `ESTIMATED` semantics;
- **no** availability status (WAITLIST or PREORDER) is chosen;
- "expected in 2026" is **not** converted into a stronger availability meaning.

Their proposals may exist and may be reviewed, but nothing about them is accepted into the
catalogue (phase G2-4 stays closed).

Anything unresolved at ACCEPT time means **no write**.

---

## 14. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **A. Extend or overload `candidate_claim`** | Terminal candidates get no claims; no edition dimension; mutable status; parser output and human acceptance on one row; the observation role would write the table promotion trusts (§4) |
| **B. Mutable proposal table** | Reviewers would rewrite the artifact; no tamper evidence; who changed what is lost |
| **C. Artifacts only, decisions by digest** | Not replayable after pruning or an extractor change; the excerpt shown to the reviewer would not be durable |
| **D. Review only as a pull request on generated JSON** | Reuses governance but has no structured per-claim decision, rationale, idempotency, supersession or stale detection. It *is* used, as the **materialization** step (§11), not as the review layer |
| **E. Generalize `promote()` to write many tables directly (M1)** | Reverted by the importer for JSON-backed robots and it creates database-only drift (§11.1) |
| **F. Auto-accept on high parser confidence** | Confidence is a parser's belief and is never verification (LIVE.8); acceptance is a human factual act |
| **G. LLM- or fuzzy-assisted mapping of proposals to fields** | Forbidden by the deterministic-matching rule (AGENTS.md rule 8) and the no-LLM identity rule |
| **H. Put acceptance state on `robot` or `specification` rows** | Mixes catalogue facts with workflow state and breaks DR-C1's separation |

---

## 15. Migration implications

- **This record: none.** No schema, code, migration or catalogue data changes.
- **Implementation** is expected to be **additive only**: new tables, triggers and indexes, plus
  new enum values only if an owner decision requires them. No existing table is altered, no
  destructive change is proposed, and existing rows are untouched, consistent with the WS8
  backward-compatibility rule (the previous application build must still run on the new schema).
- Following the established ritual: schema changes in `db/schema.sql` (canonical), a forward
  migration, the regenerated migration manifest, and the migration README entry; applied to
  production **before** the application that needs it, with a checkpoint taken first.
- A **`price_type` decision**, if it adds an enum value, is its own migration, taken only after the
  owner decides (§13).
- `docs/16` §17.3 is added with this ratification; `docs/03` gains the new entities when they are
  implemented (G2-1). Public API and
  machine surfaces are **unchanged**: they expose published canonical data only.

---

## 16. Security and least privilege

| Role / actor | May | May not |
|---|---|---|
| **Observation role** (`discovery_observer`, extended) | insert proposals and proposal-observations | read or write decisions, accepted claims or audit; write any catalogue table |
| **Review role** (new) | read proposals; insert decisions, accepted claims, retractions | write proposals or any catalogue table; run observation |
| **Materialization** (M2) | needs **no** database catalogue write at all, since it produces a git change | write to production catalogue tables directly |
| **Importer / operator** (existing) | load the merged catalogue | unchanged |
| **Any agent** | run commands on a named human's explicit instruction | decide, or accept its own proposals |

Additional controls:

- **DB-level immutability** (triggers, as for `candidate_identity_decision`) on every append-only
  G2 table. The `promotion_audit` ORM-only gap is a *separate* follow-up (§19).
- Excerpts are bounded (≤ 1000 characters) and stored as inert text, and any future UI escapes them.
- No credential, cart link or off-host URL is fetched or followed. A datasheet URL is a *reference*
  until its host has its own source eligibility review.
- Every command is attributed, audited and idempotent; failures are fail-closed (no write).

---

## 17. Testable invariants

| # | Invariant |
|---|---|
| I1 | A proposal row can never be updated or deleted (trigger and ORM). |
| I2 | Decisions are append-only; the effective decision is the newest; a repeat is a no-op; a reversal is a new row. |
| I3 | ACCEPT is refused unless the proposal is current, a named human and a rationale are present, and every review question is resolved or marked "no catalogue home". |
| I4 | An accepted claim exists only through an effective ACCEPT, with non-null lineage to the decision and proposal. |
| I5 | The observation and extraction path cannot write decisions, accepted claims, audit rows or any catalogue table (role-level test). |
| I6 | No catalogue change without an accepted claim **and** a registered field policy. |
| I7 | Materialization is deterministic and idempotent: twice gives a byte-identical change; already-applied gives no diff. |
| I8 | A superseded or stale proposal can be neither accepted nor materialized. |
| I9 | Every written catalogue fact resolves to a fetched page, a verbatim excerpt, a decision and an audit row. |
| I10 | No G2 operation changes `robot.is_published`. |
| I11 | An unresolved question produces no write, and no value is defaulted, coerced or inferred. |
| I12 | An edition-scoped claim requires its accepted variant, and no G2 operation creates a robot. |
| I13 | From stored proposals and decisions, accepted claims rebuild with identical content hashes. |
| I14 | Each role's grants are exactly as in §16 (a negative test per forbidden write). |
| I15 | An unregistered target is refused. |
| I16 | A correction or retraction adds rows; the original rows' hashes are unchanged. |
| I17 | A cosmetic change to a source page creates no proposal and no supersession. |

---

## 18. Phased implementation plan

Each phase is its own PR(s), stops at an owner gate, and **nothing in a later phase starts without
authorization**.

| Phase | Scope | Gate |
|---|---|---|
| **G2-0** | Ratify this record; decide the persistence approach and the catalogue boundary | **DONE: ratified 2026-10-02** |
| **G2-1** | Persistence foundation: migration, models and triggers for proposals, observations, decisions; the registry skeleton (still three columns); a **manual**, offline ingest of G1 proposals from a retained page. **No scheduled ingest, no accepted claims, no catalogue effect.** | migration applied to production before merge; tests I1, I2, I5, I14 |
| **G2-2** | Review commands (`list`, `show`, `decide`), supersession and stale detection, resolved-choice capture. Still no accepted claims. | I3, I8, I17 |
| **G2-3** | Accepted claims and the **materialization** generator, as a **vertical slice** on `4ne1-mini`: Standard → variant; Pro → variant; then **one** specification only through an explicitly proposed, approved and registered field policy (§11.3); end to end into the catalogue of record, applied by the importer, verified, `catalogue_write_audit` recorded. Requires the `4ne1-mini` catalogue stub first. | I4, I6, I7, I9–I13, I15, I16 |
| **G2-4** | Price and availability. **DEFERRED:** only after the owner settles their semantics (§13). | owner decision |
| **G2-5** | Wire proposal ingest into scheduled observation (observer role only). **Only after** review is proven on real proposals. | owner |
| **G2-6** | A second manufacturer: separate source and ToS approval, a separate adapter and extractor. This is Stage G3. | owner |

**Separately authorized follow-ups (owner, 2026-10-02):** the `4ne1-mini` catalogue stub and database-level immutability for `promotion_audit` (§19). They are their own narrowly scoped PRs and **begin only after this record's documentation (`docs/16` §17.3 and this record) is reviewed and merged**.

Out of scope for every phase until separately authorized: automatic catalogue writes,
automatic publication, the 43-lead baseline import, additional manufacturers without approval,
automatic cache pruning and a web review UI.

---

## 19. Pre-existing findings surfaced by this work, and their disposition

These were found while inspecting the repository. This record changes none of them; items 2 and 3
are authorized as separate PRs that have **not** started.

1. **Importer reversal of existing promotions.** For a JSON-backed robot, an importer run would
   overwrite spec columns that `promote()` wrote (today's three fields) and delete its variants and
   offers. No production robot is affected yet: the two NEURA promotions wrote no fields.
2. **`4ne1-mini` is database-only.** It was created by promotion and has no
   `db/catalogue/robots/` file. The importer neither reads nor removes it (DR-C1), but the
   catalogue of record does not describe it. Under M2 it needs an identity-only stub first.
   **Authorized (owner, 2026-10-02), as a separate narrowly scoped PR with explicit before/after
   verification.** The stub must: represent the existing robot identity `4ne1-mini`; reuse the
   existing NEURA manufacturer identity; contain no unsupported specs, no pricing, no
   availability and no inferred fields; contain **no variants** unless introduced by the
   separately governed G2 slice; remain unpublished; preserve UNKNOWN/null semantics; and not
   create a second database robot.
3. **`promotion_audit` is append-only only in the ORM.** There is no database trigger, unlike
   `candidate_identity_decision`. Direct SQL could alter it.
   **Authorized (owner, 2026-10-02), as a separate hardening PR:** an additive migration only;
   UPDATE and DELETE refused at the database layer; INSERT still permitted through the existing
   governed paths; existing rows unchanged; backward compatibility preserved; tests showing both
   forbidden operations fail in the database.
4. **A recorded audit-text discrepancy.** Five append-only rows (identity decisions #3 and #4 and the
   MiPA ×2 and MAiRA rejections in `promotion_audit`) say "2026-10-03" in their reason text while
   their database timestamps are 2026-10-02. The substantive decisions are correct. The repository
   has no append-only correction or annotation mechanism for these tables, and none is invented
   here. **Owner decision (2026-10-02):** the rows remain immutable historical rows with correct
   database timestamps and this documented discrepancy; the `promotion_audit` hardening above is
   not used to correct them.

---

## 20. Ratification record (owner decisions, 2026-10-02)

1. **Persistence approach B′ ratified:** immutable extraction proposals; append-only human proposal
   decisions; separate append-only accepted claims; derived proposal state. `candidate_claim` is
   **not** overloaded.
2. **Catalogue boundary M2 ratified:** `db/catalogue/` is the catalogue of record for catalogue
   facts; accepted claims materialize into deterministic, reviewable catalogue changes through the
   normal PR, validation and importer path; **no direct production database writes for G2 catalogue
   facts**; publication remains a completely separate decision.
3. **Number confirmed:** `DR-A5`, the next A-series decision (`DR-A1`, `DR-A2`, A3 in `docs/26`,
   `DR-A4`).
4. **First vertical slice ratified** on `4ne1-mini`: Standard → robot variant; Pro → robot variant;
   then **one** specification as the first edition-scoped materialization. The specification's
   target and key are **not chosen silently**: its exact field-policy mapping must be explicitly
   proposed and approved or registered first, with a semantic justification if
   `dexterous_hand_option` is the candidate (§11.3).
5. **Price and availability remain DEFERRED** (§13): the estimated price is not mapped to
   `ESTIMATED`, no WAITLIST or PREORDER is chosen, and "expected in 2026" is not strengthened.
6. **Follow-up A authorized:** the `4ne1-mini` identity-only catalogue stub (§19.2).
7. **Follow-up B authorized:** database-level immutability for `promotion_audit` (§19.3).
8. **Sequencing:** follow-ups A and B, and all G2 implementation, **begin only after this record and
   `docs/16` §17.3 are reviewed and merged**.

This record authorizes no implementation beyond items 6 and 7, and they have not started.
