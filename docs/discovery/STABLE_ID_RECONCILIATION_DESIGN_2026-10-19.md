# Stable-ID reconciliation: design (Importer Hardening Phase 1)

**Status: IMPLEMENTED in PR A (draft; not deployed, no migration).** This expands Phase 1 of
`docs/IMPORTER_HARDENING_PLAN_2026-10-19.md`. `db/import_catalogue.py` now reconciles by natural
key; `_reset_robot_children` is gone. The acceptance tests in
`apps/api/tests/test_importer_stable_ids.py` pass without any `xfail`. Section 8 is the
update/ownership contract as implemented. It is reconciled with owner decisions D1-D3 of
`docs/discovery/AUTOMATED_COMMERCIAL_INTELLIGENCE_PIPELINE_2026-10-19.md`: where §2 and §4 below
describe deleting keys that left the JSON, and where §3/§7 propose a deployment key and an
evidence hash, §8 and the subsection "Reconciliation with owner decisions D1-D5" govern.
Production use needs owner approval.

## 1. Problem

`import_robot` calls `_reset_robot_children`, which deletes every child row of the robot and then
reinserts it from JSON:
- `pricing_offer`, `availability_offer`, `deployment` and their evidence;
- `COMMERCIAL_STATUS` evidence;
- `robot_capability`, `use_case_fit`, `robot_variant`, `robot_image`;
- importer-owned `specification` rows.

The content comes back identical but every row gets a new UUID. As a result:
- **Audit targets dangle.** `catalogue_write_audit.target_row_id` points at deleted rows. Phase 0
  (#173) measured 25 of 45 in production, and all 25 are RELINKABLE.
- **Cascades.** Deleting a variant cascades its variant-scoped rows. Phase 0 found no unowned
  ones today, but nothing prevents them.
- **Churn hides real changes.** Every scoped import touches every child row, so the preflight
  has to compare content without ids.
- The robot's variant upsert (`ON CONFLICT (robot_id, slug)`) never fires, because the reset has
  already deleted the row.

`robot` itself, and the shared entities (manufacturer, provider, region, capability, use case,
spec definition), are already upserted by natural key and keep their ids.

## 2. Target behaviour

For each selected robot, reconcile each child table by its **natural key**:
- **update in place** a row whose key exists but whose content differs;
- **insert** a key that is new;
- **delete** a key that is no longer in the JSON;
- **leave untouched** a row whose key and content are unchanged.

Ids are never reassigned. The robot's whole reconciliation stays in **one transaction**, as
today.

## 3. Natural keys (from `db/schema.sql`)

| Table | Natural key | Enforced in schema today? |
|---|---|---|
| robot_variant | (robot_id, slug) | yes: `UNIQUE (robot_id, slug)` |
| specification (importer-owned) | (robot_id, variant_id, definition_id) | yes: `uq_specification_logical` (NULL-safe) |
| availability_offer | (robot_id, variant_id, provider_id, region_id, transaction_type, condition) WHERE is_current | yes: `uq_availability_logical` |
| pricing_offer | (robot_id, variant_id, provider_id, region_id, transaction_type, condition, price_type, billing_period) | **no** (see D1) |
| robot_image | (robot_id, image_url) | **no** (see D1) |
| deployment | candidate (robot_id, customer_name, region_id, started_on); `customer_name` may be undisclosed (NULL) | **no**; the key must be chosen (D2) |
| robot_capability | (robot_id, capability_id) | yes: primary key (no surrogate id) |
| use_case_fit | (robot_id, use_case_id) | yes: unique (no surrogate id) |
| evidence_source (importer-managed) | (subject_type, subject_id, source_url, source_type, sha256(excerpt)) | **no** (see D3) |

**Checked against the catalogue JSON (main @ b6afe89):**
- The proposed `pricing_offer` key is unique across all 35 pricing offers; the `robot_image`
  key across all 50 images. No collisions, so D1's indexes would build on today's data.
- The JSON carries **non-current offers**: `unitree-r1` pricing via quadruped-de (DE) and
  `unitree-r1-edu-u5` availability via reichelt (DE), each with `is_current: false` and no
  current sibling. `uq_availability_logical` is partial (`WHERE is_current`), so the reconcile
  key must include `is_current`. Otherwise a non-current row and a later current row with the
  same key would be collapsed into one.

Correction to the hardening plan: the spec key in the schema has **no `edition_scope`**. The
plan listed it, but the index does not include it.

## 4. Algorithm per table

1. **Load.** Read the current rows for the robot, keyed by natural key. For variant-scoped
   tables, resolve variants first (step 2), so variant ids are known.
2. **Variants first.** Upsert by (robot_id, slug), then delete only the slugs that are no
   longer present.
   - Phase 2 cascade protection runs **before** any variant delete: refuse if a row that is not
     importer-owned references the variant.
3. **Other tables.** For each JSON row, compute its key:
   - key exists and content is equal: do nothing;
   - key exists and content differs: `UPDATE ... WHERE id = <existing id>`;
   - key is missing: `INSERT`.
   Afterwards, delete the existing keys the JSON no longer lists.
4. **Evidence follows its subject.** Its `subject_id` is the subject's (now stable) id.
   Reconcile it by the evidence key under that subject, the same way.
5. **Duplicate keys in the JSON fail loudly** before any write. Today only the tables with a
   unique index reject them, and only at insert time.
6. **Ownership boundaries do not change:**
   - unowned `specification` and evidence rows are never touched;
   - `is_published` stays editorial;
   - `--apply-publication-state` semantics stay as they are.

The algorithm is deterministic, with no ordering or timing inputs.

## 5. Idempotency and no-ID-churn guarantees (the tests)

| Test | Today | After Phase 1 |
|---|---|---|
| `test_reimporting_unchanged_files_changes_no_business_content` (preflight id-stripped diff is empty) | pass | pass |
| `test_ids_that_are_already_stable_stay_stable[robot]` | pass | pass |
| `test_reimporting_unchanged_files_changes_no_ids[<table>]` for robot_variant, specification, pricing_offer, availability_offer, deployment, robot_image, evidence_source | **xfail (strict)** | pass, and the marker is removed |
| `test_a_one_value_edit_keeps_every_other_id` (an edited availability offer is updated in place; no other id changes) | **xfail (strict)** | pass, and the marker is removed |

**What strict means here:**
- A partial Phase 1 turns individual cases into XPASS, and strict mode turns those into
  failures, so the marker has to be removed table by table. Stability cannot arrive unnoticed.
- `raises=AssertionError` means an error (a broken query or fixture) is never counted as an
  expected failure.

**Fixture coverage.** The fixture imports three real catalogue robots: `4ne1-mini`,
`unitree-h2-edu` and `agility-digit`. Between them they have:
- variants and variant-scoped specs;
- manufacturer-estimate and retail offers, and availability;
- a deployment, images, use-case fits and capabilities;
- their evidence.

A guard test asserts that every id table is non-empty.

**Further tests the implementation PR adds:**
- Removing a JSON row deletes exactly that row.
- Adding a row inserts exactly one.
- Duplicate natural keys in the JSON are refused before any write.
- Phase 2: deleting a variant referenced by an unowned row is refused.
- A Phase 0 report after re-import shows **zero new RELINKABLE rows**. Audits written after
  Phase 1 stay CURRENT.

## 6. Rehearsal and rollout (implementation PR, not this one)

1. **Production copy, unchanged catalogue.** Run a scoped and then a full re-import with
   `import_preflight.py --report-only`. Require **zero business changes and zero id changes**,
   compared with an id snapshot taken before and after.
2. **Production copy, the next real content change.** The preflight lists exactly the expected
   rows, each with its id unchanged.
3. **Phase 0 report before and after.** No CURRENT audit becomes RELINKABLE.
4. **Production.** Owner approval, a Neon safety branch, and the same checks.

## 7. Owner decisions

- **D1.** Add unique indexes for the `pricing_offer` and `robot_image` natural keys. This is a
  migration and needs separate review. Without them, the importer enforces uniqueness itself
  (step 5), which is weaker.
- **D2.** The `deployment` natural key. The catalogue JSON has no stable deployment identifier.
  Options:
  - (customer_name, region, started_on), NULL-safe;
  - a new `slug` in the JSON;
  - keep delete-and-reinsert for deployments only, as a documented exception.
- **D3.** The evidence key. Hashing the excerpt means an edited excerpt is a new evidence row,
  not an update. That is arguably correct for provenance.
- **D4.** Phase order. Phase 1 (this design) first, then Phase 3, which relinks the 25 historical
  audits or records them as historical. Phase 0 shows they are all RELINKABLE.

## 8. The update and ownership contract (as implemented)

**Per row, inside one transaction per run:**

| Situation | What the importer does |
|---|---|
| Key in DB and JSON, every non-key column equal | **nothing** (no statement issued) |
| Key in DB and JSON, a non-key column differs | `UPDATE` in place, **same id** (a corrected price, a retired offer `is_current: false`, a reworded limitation) |
| Key only in JSON | `INSERT` once; the next run finds it unchanged |
| Key only in DB (missing from the JSON) | **preserved**: left untouched, counted in the summary `preserved` column and listed under "PRESERVED (not in JSON, left untouched)" (D1). Removed only by an explicit `remove` authorization |
| Same key twice in the JSON | refuse before any write |
| Two DB rows share one key | refuse as ambiguous; the importer never picks one |
| Matched evidence row whose non-key fields differ | refuse unless `update_evidence` is authorized: evidence is immutable to the importer |
| Evidence whose excerpt changed materially | a **new version** (D3): the excerpt is part of the key, so the new row is inserted and the old row is preserved with its id (and listed as preserved) |
| JSON gives NULL (absent or explicit null) for a column that holds a value, in **any** reconciled table, the robot row or a shared-entity upsert | refuse unless a `clear` entry names (table, robot/slug, key, column). Non-NULL to a different non-NULL value is a normal in-place update (D1) |
| Deployments | **no inferred identity (D2)**: an unchanged set (every column, as a multiset) is left alone with its ids and its evidence reconciled; a robot with no stored deployment gets its first ones inserted; any new, edited or missing deployment of a robot that already has some is refused, as is a `remove` for a deployment, until an explicit `deployment_key` exists (migration not approved) |
| Removing a variant that still has a specification or offer not itself being removed | refuse: the `ON DELETE CASCADE` would take it |
| `is_published` | written only when the robot row is first created; never by a routine import (`--apply-publication-state` is the separate, gated operation) |
| Robot, region, manufacturer, provider, capability, use case, spec definition upserts | `WHERE (cols) IS DISTINCT FROM (EXCLUDED.cols)`: an unchanged row is not rewritten and its `updated_at` does not move |

**What the importer owns, and what it leaves alone:**
- `specification`: only rows with `managed_by = 'CATALOGUE_IMPORT'`. An unmanaged row on the
  same key is preserved and reported as a collision, as before.
- MANUFACTURER evidence: only `managed_by = 'CATALOGUE_IMPORT'` rows. Unmarked rows are
  untouched; a URL/type/date collision is reported.
- Robot-child evidence (PRICING_OFFER, AVAILABILITY_OFFER, DEPLOYMENT, COMMERCIAL_STATUS): the
  rows under the importer's own subject rows, matched by key. Ownership is never backfilled.
  Other subject types, such as hand-written ROBOT evidence, are never read or written.
- Variants, offers, availability, deployments, images, capabilities and fits of a catalogue
  robot have no ownership column. They are matched by exact key. Nothing unmatched is ever
  deleted without an authorization naming that exact key.

**Snapshot versus patch.** A robot file is the statement of what is now known, not an order to
forget the rest. A field present in the file is written as the file says. A field or row
**absent** never erases data:
- an absent row is preserved and reported;
- an absent (or null) value over a stored one refuses unless a `clear` entry names it.

Whole-record replacement no longer happens.

**Explicit operations (`--authorize FILE`):**
- `{"version": 1, "entries": [{"action": "remove" | "update_evidence" | "clear", "table", "robot", "key", "column"?}]}`.
- A refusal (a `clear` or `update_evidence` that is needed) prints these entries ready to paste.
  A preserved row is listed with its key, from which a `remove` entry is written.
- An entry that matches nothing aborts the run, since it is a sign of drift.
- An authorized removal of an offer or deployment also removes that row's own evidence rows,
  and counts them.

**Evidence kinds** (A1.3):

| Kind | How it is expressed |
|---|---|
| New evidence | a new key (URL, type, excerpt, observed date) is an insert |
| New observation confirming unchanged information | the same excerpt with a new `observed_at` is a new row beside the old one (e.g. the 2026-09-11 and 2026-09-26 Reichelt rows) |
| Correction | a changed excerpt is a new key and so a new row (D3); the old row is preserved and reported until a `remove` is authorized, so a correction never overwrites history |
| Withdrawal | an authorized `remove` |

The importer never sets `verified_at`. A newly observed page is not human verification.

**Rehearsal on a production copy** (dump 2026-10-19 08:23 UTC, local only):
- A scoped re-import of unchanged `unitree-g1` gave every table unchanged, 0 writes, and
  `db/import_identity_check.py` PASS: 0 ID_CHANGED, 0 TOUCHED. The previous importer, on the
  same copy, gave 22 ID_CHANGED and 4 TOUCHED with 0 business changes.
- A full import touched only three real main-vs-production differences, which predate this
  change:
  - 2 H1 re-observation evidence rows (2026-09-26), inserted;
  - 1 changed provider (`alza-cz` description), updated.

  It gave 0 ID_CHANGED, 0 ambiguous keys and 0 lost audit targets. The 25 historical dangling
  audit targets are unchanged.

### Reconciliation with owner decisions D1-D5

The owner decisions in `AUTOMATED_COMMERCIAL_INTELLIGENCE_PIPELINE_2026-10-19.md` supersede the
conflicting parts of §2-§4 and §7 above:

- **D1, non-destructive reconciliation.** A row, or a field, missing from the JSON is never a
  reason to delete or blank anything. Omitted rows are preserved and reported; stored values
  are never turned into NULL without a `clear` entry (every column, not only provenance);
  deletion is the authorized `remove`, with the variant-dependency and own-evidence checks.
- **D2, deployment identity.** No key is inferred for deployments (this replaces the
  (customer, region, started_on) candidate in §3 and open question D2 in §7). Only an
  unchanged set is accepted, plus the first load of a robot that has none. Anything else waits
  for an explicit `deployment_key`, which needs a schema migration that is not approved.
- **D3, evidence versioning.** Replaces the open question D3 in §7: the excerpt stays in the
  evidence key, a changed excerpt is a new version, and the original is preserved.
- **D4, rehearsal.** A local database restored from a read-only production dump is an
  acceptable rehearsal environment; the rehearsal in §8 used one.
- **D5, production automation credentials.** Not applicable to PR A: the importer is run by
  an operator and gains no CI or production write path.
