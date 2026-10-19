# Stable-ID reconciliation: design (Importer Hardening Phase 1)

**Status: DESIGN. No importer change, no migration.** This expands Phase 1 of
`docs/IMPORTER_HARDENING_PLAN_2026-10-19.md`. Its acceptance tests are in
`apps/api/tests/test_importer_stable_ids.py`; the ones the current importer cannot meet are
`xfail(strict=True)`. The implementation is a later PR that needs owner approval, a rehearsal on a
production copy, and a separate review for any migration.

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
