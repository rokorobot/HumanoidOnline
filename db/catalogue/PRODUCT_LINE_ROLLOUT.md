# Product lines (migration 0027, DR-L1 PR a) — rollout and rollback runbook

Scope: PR #226. This runbook applies migration 0027 (`product_line` table and `robot.product_line_id`), loads `db/catalogue/product_lines.json` with `--product-lines-only`, and deploys the API that serves `/api/product-lines`. The web page (DR-L1 PR b) is not part of this.

Every numbered production step below needs the owner approval it names. **Nothing here is pre-authorized.**

## Facts this plan depends on

- **Merging to `main` deploys immediately.** The Vercel project `humanoidonline-api` and the Netlify site `humanoidonline` publish production on every push to `main` (as verified for the 0026 rollout, 2026-10-19; re-check before relying on it). Merging is therefore a deployment.
- **The new API refuses to start without 0027, in a strict environment.** Its bundled migration manifest (`app/db/migration_manifest.py`) lists `0027_product_line`. `verify_migration_state()` in `apps/api/app/db/migration_state.py` raises `MigrationStateError` when a migration the build expects is *missing* (or has drifted). `enforce_migration_state_at_startup()` re-raises it when `settings.is_strict` (staging/production). A relaxed environment only logs a warning.
- **The old API accepts a database that has 0027.** A database *ahead* of a build is logged (`database is ahead of this build …`) and served ("WS8-L7 rollback compatibility"). The old ORM never names `product_line` or `robot.product_line_id`, and 0027 is additive with a nullable column, so old reads and writes are unaffected.
- **The new API works with an empty `product_line` table.** Before the import, `GET /api/product-lines` returns `[]`, `GET /api/product-lines/{slug}` returns 404, and every robot detail has `product_line: null`. Importing the lines changes only those responses.
- **`--product-lines-only` writes only `product_line` rows and `robot.product_line_id` of the 16 listed robots.** No robot file is read; no offer, evidence, manufacturer or child row is reconciled. It is idempotent, refuses an unknown robot, a manufacturer mismatch or a robot in two lines, and runs in one transaction. It cannot be combined with `--only` or `--manufacturers-only`.
- **Role proposals.** `docs/discovery/promotion_executor_proposal/*.sql` now list `product_line`. They are proposals; if the production import role is a restricted role, it needs `SELECT, INSERT, UPDATE` on `product_line` and `UPDATE (product_line_id)` on `robot` before step 10. `neondb_owner` needs nothing.

The safe order is **migrate, import, then merge**. The new API is not live until the merge, and the old API ignores the new data. This is the order used for 0026.

## Production sequence (each approval is separate)

1. **Check the PR.** Confirm the PR #226 head is the approved SHA, every required CI check is green, `mergeable = CLEAN`, and the file scope is unchanged. Record `sha256` of `db/migrations/0027_product_line.sql` and of `db/catalogue/product_lines.json` at that head.
2. **Merge authorization (owner).** Obtain it now, but do not merge yet. The merge happens at step 12.
3. **Safety branch.** Create a fresh pre-migration Neon branch from `production`, named `pre-product-line-0027-<date>`. Record its id and LSN.
4. **Production-migration authorization (owner).**
5. **Apply 0027.** From a checkout of the approved head, run `uv run db/bootstrap.py` with `DATABASE_URL` set to production (role `neondb_owner`). Expected output: `applying 0027_product_line … Applied 1 migration(s).`
6. **Verify the migrated database.**
   - `schema_migrations` has `0027_product_line` with the recorded checksum.
   - `SELECT count(*) FROM humanoid.product_line` is 0, and `SELECT count(*) FROM humanoid.robot WHERE product_line_id IS NOT NULL` is 0.
   - The robot count and published count are unchanged (43 published).
   - The live, still-old API keeps serving (database ahead); a robot list and detail return 200.
7. **Rehearse the import on a Neon branch of production.** Branch `production` again as `rehearsal-product-lines-<date>` (after step 5, so it holds 0027). On the rehearsal branch run
   `uv run db/import_catalogue.py --product-lines-only`
   with `DATABASE_URL` set to the rehearsal branch. Expected: `product_line … 5 inserted`, `robot_product_line … 16 updated`, every other row of the summary zero. Run it a second time: everything `unchanged`, nothing inserted or updated.
8. **Preflight the rehearsal.** Against the safety state (production, read-only) and the rehearsal:
   `uv run db/import_preflight.py --before "$PROD_URL" --after "$REHEARSAL_URL" --manifest db/catalogue/product_lines_expected.json`
   Expected: `PREFLIGHT PASS: every business change is accounted for` (exit 0). The manifest lists exactly 5 `product_line` ADDED and 16 `robot` CHANGED (`product_line` NULL → slug). Any other change, or an expected one that is absent, exits 2: **stop**. If production moved since the branch (a lead, a freshness observation), re-branch and repeat steps 7–8.
9. **Production-import authorization (owner).**
10. **Production import.** `uv run db/import_catalogue.py --product-lines-only` with `DATABASE_URL` set to production, from the approved head. Expected summary identical to step 7. Run it again: all `unchanged`.
11. **Verify the data.** `SELECT l.slug, count(r.id) FROM humanoid.product_line l LEFT JOIN humanoid.robot r ON r.product_line_id = l.id GROUP BY 1` gives unitree-g1 2, unitree-h2 2, unitree-r1 7, booster-k1 3, booster-t2 2 (16 in total). The published count is still 43. The old API still serves robot pages unchanged.
12. **Merge PR #226** with a normal merge of the pinned head. This auto-deploys the API and web. Confirm the merged tree's 0027 file and `product_lines.json` have the recorded checksums.
13. **Verify the API.** The Vercel production deploy for the merge SHA succeeds and starts (the migration check passes). `GET /api/product-lines` lists 5 lines with the member slugs above (published members only). `GET /api/product-lines/unitree-g1` returns 2 robots, and `GET /api/product-lines/nope` returns 404. `GET /api/robots/unitree-g1` carries `product_line: {slug: "unitree-g1", name: "Unitree G1"}`; a robot outside any line (for example `figure-03`) carries `null`.
14. **Verify robot pages.** Robot list and detail, compare and manufacturer pages return 200 with unchanged counts. No catalogue fact changed in this rollout.

If step 5 fails, the transaction rolls back and production stays at 0026. If step 7 or 8 does not pass, nothing has touched production data: fix forward and rehearse again. If step 10 is refused, nothing is committed. Do not merge unless steps 6, 10 and 11 are clean.

## Rollback A — application rollback (preferred)

Use this if the new API or web misbehaves after step 12. **Keep migration 0027 and the imported lines.**

1. Redeploy the previous production deployments: promote the previous production deployment of `humanoidonline-api` in Vercel, and use Netlify "Publish deploy" on the previous web deploy.
2. The previous API starts against the migrated database because the ahead state is allowed. Confirm its startup log warns `database is ahead of this build … 0027_product_line`, and that robot pages return 200.

No data change and no ledger change. The lines stay in the database, unused by the old API.

## Rollback B — database rollback (exceptional)

Use this **only** with separate owner approval, and only if the 0027 objects themselves are shown to be the problem. Rollback A is not enough in that case.

**Prerequisites:**
- Rollback A is done first. Once the ledger row is deleted, the new API refuses to start.
- A fresh Neon safety branch has been taken.
- Nobody is writing to the catalogue. Hold the promotion executor and imports.

One transaction, no `CASCADE`, so an unexpected dependent fails the whole statement.

```sql
BEGIN;
SET search_path TO humanoid, public;

-- 0. Inventory: expect only the FK from robot.product_line_id, the index and the trigger.
SELECT conname, conrelid::regclass FROM pg_constraint WHERE confrelid = 'product_line'::regclass;
SELECT tgname FROM pg_trigger WHERE tgrelid = 'product_line'::regclass AND NOT tgisinternal;

-- 1. The column (drops its FK and partial index with it).
ALTER TABLE robot DROP COLUMN product_line_id;

-- 2. The table (membership data only; no fact lives on a line).
DROP TABLE product_line;

-- 3. Migration ledger: only as part of this governed rollback.
DELETE FROM public.schema_migrations WHERE version = '0027_product_line';

-- 4. Post-check: both must return 0 before COMMIT.
SELECT count(*) FROM information_schema.tables
 WHERE table_schema = 'humanoid' AND table_name = 'product_line';
SELECT count(*) FROM information_schema.columns
 WHERE table_schema = 'humanoid' AND table_name = 'robot' AND column_name = 'product_line_id';
COMMIT;
```

**Verify the catalogue data is unchanged.** Before `BEGIN` and after `COMMIT`, compare a per-table row count and content hash of every other `humanoid` table, e.g. `SELECT count(*), md5(string_agg(t::text, '|' ORDER BY t::text)) FROM humanoid.<table> t` (for `robot`, exclude the dropped column). Only `product_line`, `robot.product_line_id` and the ledger row may differ.

To remove the lines but keep the schema (no ledger change), set `robot.product_line_id` to NULL and delete the `product_line` rows in one transaction, or unpublish a line (`is_published = FALSE`) to hide it from the API without deleting it.
