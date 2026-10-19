# Stable-ID reconciliation: design (Importer Hardening Phase 1)

**Status: DESIGN. No importer change, no migration.** This expands Phase 1 of
`docs/IMPORTER_HARDENING_PLAN_2026-10-19.md`. Its acceptance tests are in
`apps/api/tests/test_importer_stable_ids.py`; the ones the current importer cannot meet are
`xfail(strict=True)`. The implementation is a later PR that needs owner approval, a rehearsal on a
production copy, and a separate review for any migration.

**Owner decisions D1–D5 (2026-10-19) govern this design.** They are recorded in
`docs/discovery/AUTOMATED_COMMERCIAL_INTELLIGENCE_PIPELINE_2026-10-19.md` (#175) and supersede
anything here that conflicts with them. This revision aligns §2–§7 with them.

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
- **leave untouched** a row whose key and content are unchanged;
- **preserve** a row whose key the JSON no longer lists (**D1: no deletion by omission**).

A missing JSON field or child row is not an instruction to delete. Deletion, retirement,
replacement and retraction are **explicit, authorized operations**, separate from a routine
import, each with ownership and evidence checks (see §4 step 7). A routine import may report
omitted keys, but never removes them.

Ids are never reassigned. The robot's whole reconciliation stays in **one transaction**, as
today.

## 3. Natural keys (from `db/schema.sql`)

| Table | Natural key | Enforced in schema today? |
|---|---|---|
| robot_variant | (robot_id, slug) | yes: `UNIQUE (robot_id, slug)` |
| specification (importer-owned) | (robot_id, variant_id, definition_id) | yes: `uq_specification_logical` (NULL-safe) |
| availability_offer | (robot_id, variant_id, provider_id, region_id, transaction_type, condition) WHERE is_current | yes: `uq_availability_logical` |
| pricing_offer | (robot_id, variant_id, provider_id, region_id, transaction_type, condition, price_type, billing_period) | **no** (see U1) |
| robot_image | (robot_id, image_url) | **no** (see U1) |
| deployment | (robot_id, deployment_key): an explicit durable key (D2) | **no**; needs a separately approved migration (D2) |
| robot_capability | (robot_id, capability_id) | yes: primary key (no surrogate id) |
| use_case_fit | (robot_id, use_case_id) | yes: unique (no surrogate id) |
| evidence_source (importer-managed) | (subject_type, subject_id, source_url, source_type, sha256(excerpt)); a changed excerpt is a new version (D3) | **no** |

**Checked against the catalogue JSON (main @ b6afe89):**
- The proposed `pricing_offer` key is unique across all 35 pricing offers; the `robot_image`
  key across all 50 images. No collisions, so the U1 indexes would build on today's data.
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
2. **Variants first.** Upsert by (robot_id, slug). A slug the JSON no longer lists is
   **kept** (D1); a routine import never deletes a variant, so it never cascades.
3. **Other tables.** For each JSON row, compute its key:
   - key exists and content is equal: do nothing;
   - key exists and content differs: `UPDATE ... WHERE id = <existing id>`;
   - key is missing: `INSERT`.
   Existing keys the JSON no longer lists are left as they are and reported as **omitted** (D1).
4. **Evidence follows its subject.** Its `subject_id` is the subject's (now stable) id.
   Reconcile it by the evidence key under that subject, the same way. Because the key includes
   `sha256(excerpt)`, a changed excerpt is inserted as a **new evidence version**; the earlier
   version and its audit history stay (D3).
5. **Duplicate keys in the JSON fail loudly** before any write. Today only the tables with a
   unique index reject them, and only at insert time.
6. **Ownership boundaries do not change:**
   - unowned `specification` and evidence rows are never touched;
   - `is_published` stays editorial;
   - `--apply-publication-state` semantics stay as they are.

7. **Removal is a separate, explicit operation** (D1). Deleting, retiring, replacing or
   retracting a row needs an authorized instruction that names the row; its absence from the
   JSON is not one. Before acting, the operation checks ownership (importer-owned rows only)
   and evidence. For a variant it applies Phase 2 cascade protection: refuse if a row that is
   not importer-owned references the variant. The form of that instruction (a CLI flag, a
   manifest entry, a retirement status) is for the implementation PR to propose; it is not
   decided here.

The algorithm is deterministic, with no ordering or timing inputs.

## 5. Idempotency and no-ID-churn guarantees (the tests)

| Test | Today | After Phase 1 |
|---|---|---|
| `test_reimporting_unchanged_files_changes_no_business_content` (preflight id-stripped diff is empty) | pass | pass |
| `test_ids_that_are_already_stable_stay_stable[robot]` | pass | pass |
| `test_reimporting_unchanged_files_changes_no_ids[<table>]` for robot_variant, specification, pricing_offer, availability_offer, deployment, robot_image, evidence_source | **xfail (strict)** | pass, and the marker is removed |
| `test_a_one_value_edit_keeps_every_other_id` (an edited availability offer is updated in place; no other id changes) | **xfail (strict)** | pass, and the marker is removed |
| `test_an_omitted_row_is_preserved` (a pricing offer dropped from the JSON keeps its row, its evidence and every id; D1) | **xfail (strict)** | pass, and the marker is removed |

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
- An explicit, authorized removal deletes (or retires) exactly the named row and nothing else.
- Adding a row inserts exactly one.
- Duplicate natural keys in the JSON are refused before any write.
- A changed evidence excerpt adds a new evidence version and keeps the earlier one (D3).
- Phase 2: an explicit removal of a variant referenced by an unowned row is refused.
- A Phase 0 report after re-import shows **zero new RELINKABLE rows**. Audits written after
  Phase 1 stay CURRENT.

## 6. Rehearsal and rollout (implementation PR, not this one)

A **production copy** is either an isolated Neon rehearsal branch or a local database restored
from a read-only production dump (D4). Either is acceptable if it gives equivalent integrity,
isolation and recovery: the rehearsal never writes to production, production is unchanged by
it, and the copy can be discarded and recreated. No step needs, or may use, GitHub Actions
production write credentials (D5).

1. **Production copy, unchanged catalogue.** Run a scoped and then a full re-import with
   `import_preflight.py --report-only`. Require **zero business changes and zero id changes**,
   compared with an id snapshot taken before and after.
2. **Production copy, the next real content change.** The preflight lists exactly the expected
   rows, each with its id unchanged.
3. **Phase 0 report before and after.** No CURRENT audit becomes RELINKABLE.
4. **Production copy, an omitted row.** Drop one row from a copy of the JSON: the preflight
   reports it as omitted, and the row, its evidence and its id remain (D1).
5. **Production.** Owner approval, a Neon safety branch, and the same checks.

## 7. Owner decisions

Decided by the owner on 2026-10-19 (`AUTOMATED_COMMERCIAL_INTELLIGENCE_PIPELINE_2026-10-19.md`,
"Owner Architectural Decisions"). They are principles, not approvals: no implementation,
migration, import, deployment or credential is approved by them.

- **D1. Non-destructive reconciliation (decided).** Missing JSON fields or child rows do not
  authorize deletion; routine imports preserve existing records. Retirement, replacement,
  retraction and deletion are explicit authorized changes with ownership and evidence checks.
  Applied in §2 and §4 (step 7). This replaces the earlier proposal to delete omitted keys.
- **D2. Stable deployment identity (decided).** New deployments carry an explicit durable
  `deployment_key`. Existing deployments are **not** re-keyed by inference (for example from
  customer name, region and start date). Adding `deployment_key` is a migration that needs
  **separate approval**. Until it lands, the implementation PR must not reconcile deployments
  by an inferred key; how it handles existing keyless deployments in the meantime is for that
  PR to propose. The earlier options (an inferred NULL-safe key, a JSON slug, or
  delete-and-reinsert) are superseded.
- **D3. Evidence versioning (decided).** A materially changed excerpt is a **new evidence
  version**, not an update in place. The original evidence and its audit history are
  preserved. This matches the excerpt-hash key in §3.
- **D4. Rehearsals (decided).** An isolated Neon rehearsal branch or a local database restored
  from a read-only production dump; see §6.
- **D5. Production automation credentials (decided).** GitHub Actions gets no production write
  access. Nothing in this design requires it.

Still open, for owner review with the implementation PR:
- **U1.** Unique indexes for the `pricing_offer` and `robot_image` natural keys. This is a
  migration and needs separate review. Without them, the importer enforces uniqueness itself
  (§4 step 5), which is weaker.
- **U2.** Phase order. Phase 1 (this design) first, then Phase 3, which relinks the 25
  historical audits or records them as historical. Phase 0 shows they are all RELINKABLE.
