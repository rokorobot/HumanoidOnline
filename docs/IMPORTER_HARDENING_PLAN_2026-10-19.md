# Catalogue importer hardening: investigation and implementation plan (2026-10-19)

**Status: PLAN. Not implemented.** No importer change is authorized in Batch 2. Each phase below
is a separate, reviewed PR.

## 1. Findings (production, read-only, 2026-10-19)

**F1. Row IDs are not stable.** For every robot it imports, `import_catalogue.py`
(`_reset_robot_children`) deletes and re-inserts the following, which therefore get new UUIDs
with identical content:
- `pricing_offer`, `availability_offer`, `deployment`;
- `robot_capability`, `use_case_fit`, `robot_variant`, `robot_image`;
- importer-managed `specification` rows;
- their `evidence_source` rows (`PRICING_OFFER` / `AVAILABILITY_OFFER` / `DEPLOYMENT` /
  `COMMERCIAL_STATUS` subjects).

Shared entities (region, manufacturer, provider, capability, use case, spec definition) and
the `robot` row itself are upserted by natural key and keep their IDs. Observed churn: Batch 1
re-created 8 pricing, 6 availability, 54 evidence and 10 image rows; Batch 2 re-created 6, 6,
22 and 6. The semantic content is identical in both cases (preflight and an ID-stripped
comparison).

**F2. No hard FK breaks, but there is one cascade risk.** Nothing hard-references the
re-created tables except `variant_id → robot_variant(id) ON DELETE CASCADE` (from
`specification`, `pricing_offer`, `availability_offer`). Deleting a robot's variants
cascade-deletes every variant-scoped row, including any row the importer does not own. Today all
177+15 `specification` rows are `CATALOGUE_IMPORT`-managed, so nothing has been lost, but a
hand-authored, variant-scoped spec on a re-imported robot would be silently deleted.

**F3. Evidence lineage is consistent but not stable.** `evidence_source` is a polymorphic soft
reference (`subject_type`, `subject_id`). It is re-created with its subject row, so it always
points at the current row, but evidence IDs change on every import.

**F4. Audit lineage is broken for 25 of 45 rows.** `catalogue_write_audit.target_row_id` is a
soft UUID reference to the row a claim produced. **25 of 45** audit rows point at IDs that no
longer exist:
- 4ne1-mini 15 (7 specification, 2 pricing, 2 availability, 4 variant);
- unitree-h2-edu 4 (2 pricing, 2 availability);
- unitree-r1-edu-u4 2 and unitree-r1-edu-u5 2 (1 pricing + 1 availability each);
- xpeng-iron 2 (specification).

Reconciliation: an earlier report said "29"; that was an arithmetic error. The per-table and
per-robot breakdowns both total **25**. Batches 1 and 2 added none, because their robots had no
audit rows. Each audit row still carries `claim_id`, `robot_slug`, `target_table` and
`after_hash`, so it can be re-linked by content.

## 2. Plan

**Phase 0: measure (read-only, no schema change).** Add a `db/audit_integrity.py` report:
dangling audit targets, the evidence subjects missing their row, and the variant-scoped rows not
owned by the importer. Run it in CI against the seed and in the import preflight, as a report
(not a gate) at first.

**Phase 1: stable IDs via diff-based reconcile (importer code, no migration if natural keys
exist).** Replace delete-all/insert-all with upsert-by-natural-key and delete-only-missing:
- `pricing_offer` / `availability_offer`: their existing logical uniqueness (provider, region,
  transaction type, condition, variant…, e.g. `uq_availability_logical`). Verify an equivalent
  key for pricing; if it is missing, adding the unique index is a migration (a schema change,
  so owner review).
- `robot_variant` (robot, slug), `robot_image` (robot, image_url), `deployment` (robot,
  customer/site key), `specification` (robot, definition, variant, edition_scope).
- `evidence_source`: upsert by (subject, source_url, source_type, excerpt hash) and keep the ID
  when unchanged.

Acceptance: re-importing an unchanged robot changes **zero** IDs and zero rows; the preflight
`--report-only` shows no churn; existing import tests plus new idempotency tests pass.

**Phase 2: cascade protection.** Before deleting a variant, the importer refuses (fails loudly)
if any row not `CATALOGUE_IMPORT`-managed references it. Optionally, change the FK to
`ON DELETE RESTRICT` for `specification` (a migration, so owner review).

**Phase 3: audit repair and prevention.**
- *Prevention:* once Phase 1 makes IDs stable, newly materialized claims keep valid targets.
  Add an integrity check after each import: no audit target may dangle for the imported
  robots.
- *Repair* of the 25 existing rows: `catalogue_write_audit` is append-only, so it is not
  edited. Append a `catalogue_write_audit_relink` record (new table, a migration) mapping the
  old target to the current row found by (`robot_slug`, `target_table`, `after_hash`). Rows
  whose content no longer matches (the value changed since) are listed for human review, not
  guessed.

**Phase 4: preflight alignment.** Once Phase 1 lands, the semantic preflight gains an optional
"no ID churn" check for the imported robots, so stability is enforced, not just documented.

## 3. Risks and decisions

- Phases 1 and 3 may need migrations (unique indexes; the relink table): separate owner approval.
- Phase 1 changes the importer used for every production import. Rehearse it on a full
  production copy with `--report-only` and require zero semantic changes and zero ID churn before
  it is used for real.
- **Owner decisions:** the order of phases; whether to relink the 25 audit rows or record them
  as historical; FK `RESTRICT` vs importer-side refusal.
