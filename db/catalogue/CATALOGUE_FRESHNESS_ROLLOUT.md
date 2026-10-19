# Catalogue freshness (migration 0026) — rollout and rollback runbook

Scope: PR #186. This runbook applies migration 0026 (`catalogue_freshness` plus its triggers) and deploys the API and web that read it.

Every numbered production step below needs the owner approval it names. **Nothing here is pre-authorized.**

## Facts this plan depends on (verified 2026-10-19)

- **Merging to `main` deploys immediately.** The Vercel project `humanoidonline-api` creates a production deployment on every push to `main`. The Netlify site `humanoidonline` publishes production on every push to `main`. For example, `6266f2e` merged at 19:19 UTC, and the API and web production deploys started at 19:19 and the web was published at 19:20. Merging is therefore a deployment.
- **The new API refuses to start without 0026.** Its migration manifest lists 0026, and `migration_state.py` blocks a strict environment when a migration is *missing*.
- **The old API accepts a database that has 0026.** A database that is *ahead* of a build is logged and served ("WS8-L7 rollback compatibility"). The previous build never reads `catalogue_freshness`, and the triggers fire for its writes like any others.
- **The new web accepts the old API.** If `latest_catalogue_updated_at` is absent or null, the header field is omitted and the readout shows `UNKNOWN`.

The safe order is therefore **migrate first, then merge** (the merge deploys). This is the same order used for 0013 (PR #60). No deployment hold or platform setting change is needed.

## Production sequence (each approval is separate)

1. **Check the PR.** Confirm the PR #186 head is the approved SHA, every required CI check is green, `mergeable = CLEAN`, and the file scope is unchanged. Confirm `sha256` of `db/migrations/0026_catalogue_freshness.sql` at that head equals the rehearsed checksum.
2. **Merge authorization (owner).** Obtain it now, but do not merge yet. The merge happens at step 7.
3. **Safety branch.** Create a fresh pre-migration Neon branch from `production`, named `pre-catalogue-freshness-0026-<date>`. Record its id and LSN.
4. **Production-migration authorization (owner).**
5. **Apply 0026.** From a checkout of the approved head, run `uv run db/bootstrap.py` with `DATABASE_URL` set to production (role `neondb_owner`). The bootstrap applies only pending migrations, each in one transaction together with its ledger row. Expected output: `applying 0026_catalogue_freshness … Applied 1 migration(s).`
6. **Verify the migrated database.**
   - `schema_migrations` has `0026_catalogue_freshness` with the rehearsed checksum.
   - There are 14 deferred constraint triggers plus 2 guard triggers.
   - The seed row reads `latest_public_update_at` = 19 Oct 2026 UTC.
   - The robot count and published count are unchanged (43 published).
   - The live, still-old API keeps serving (database ahead), and `/api/market-snapshot` returns 200 without the new field.
7. **Merge PR #186** with a normal merge of the pinned head. This auto-deploys the API (Vercel) and web (Netlify). Confirm the merged tree's 0026 file has the same checksum as the applied one.
8. **Confirm the API deploy.** The Vercel production deploy for the merge SHA succeeds. `/api/market-snapshot` returns `latest_catalogue_updated_at` with a 19 Oct 2026 value, and `latest_observed_at` is unchanged.
9. **Confirm the web deploy.** Netlify is published on the merge SHA. Within the 300 s cache window, `https://humanoidonline.com/` shows `CATALOGUE UPDATED 19 OCT 2026` and the readout `UPDATED 19 OCT 2026`, and `DATA OBSERVED` no longer appears.
10. **Check for unrelated changes.** Robot list and detail, compare, and the manufacturer pages return 200 with unchanged counts. No catalogue data was written by the rollout.

If step 5 fails, the transaction rolls back and production stays at 0025. Stop and report. If step 6 shows anything unexpected, do not merge.

## Rollback A — application rollback (preferred)

Use this if the new API or web misbehaves after step 7. **Keep migration 0026 and all its database objects.**

1. Redeploy the previous production deployments. For the API, run `vercel redeploy` / promote the previous production deployment of `humanoidonline-api`. For the web, use Netlify "Publish deploy" on the previous production deploy.
2. The previous API starts against the migrated database because the ahead state is allowed. Confirm its startup log warns `database is ahead of this build … 0026_catalogue_freshness`, and that `/api/market-snapshot` and robot pages return 200.
3. The triggers keep recording catalogue changes while the old build is live. When the fixed build returns, the date is already current.

No data changes and no ledger change.

## Rollback B — database rollback (exceptional)

Use this **only** with separate owner approval, and only if the database objects themselves are shown to be the problem. Rollback A is not enough in that case: for example, the triggers block catalogue writes.

**Prerequisites:**
- Rollback A is done first. Once the ledger row is deleted, the new API refuses to start.
- A fresh Neon safety branch has been taken.
- Nobody is writing to the catalogue. Hold the promotion executor and imports.

The procedure is **one transaction, no `CASCADE`**, so an unexpected dependent fails the whole statement instead of being silently dropped.

```sql
BEGIN;
SET search_path TO humanoid, public;

-- 0. Inventory: expect exactly 16 rows (14 x record_catalogue_change on the content tables,
--    2 x guard_catalogue_freshness on catalogue_freshness) and nothing else depending on them.
SELECT tgname, tgrelid::regclass, tgfoid::regproc
FROM pg_trigger
WHERE tgfoid IN ('humanoid.record_catalogue_change'::regproc,
                 'humanoid.guard_catalogue_freshness'::regproc)
ORDER BY 1;

-- 1. The 14 deferred constraint triggers (dependents of record_catalogue_change).
DROP TRIGGER trg_robot_catalogue_freshness              ON robot;
DROP TRIGGER trg_robot_variant_catalogue_freshness      ON robot_variant;
DROP TRIGGER trg_robot_image_catalogue_freshness        ON robot_image;
DROP TRIGGER trg_specification_catalogue_freshness      ON specification;
DROP TRIGGER trg_robot_capability_catalogue_freshness   ON robot_capability;
DROP TRIGGER trg_use_case_fit_catalogue_freshness       ON use_case_fit;
DROP TRIGGER trg_pricing_offer_catalogue_freshness      ON pricing_offer;
DROP TRIGGER trg_availability_offer_catalogue_freshness ON availability_offer;
DROP TRIGGER trg_deployment_catalogue_freshness         ON deployment;
DROP TRIGGER trg_manufacturer_catalogue_freshness       ON manufacturer;
DROP TRIGGER trg_provider_catalogue_freshness           ON provider;
DROP TRIGGER trg_capability_catalogue_freshness         ON capability;
DROP TRIGGER trg_use_case_catalogue_freshness           ON use_case;
DROP TRIGGER trg_spec_definition_catalogue_freshness    ON spec_definition;

-- 2. The 2 guard triggers (dependents of guard_catalogue_freshness).
DROP TRIGGER trg_catalogue_freshness_guard       ON catalogue_freshness;
DROP TRIGGER trg_catalogue_freshness_no_truncate ON catalogue_freshness;

-- 3. The functions, now without dependents.
DROP FUNCTION record_catalogue_change();
DROP FUNCTION guard_catalogue_freshness();

-- 4. The table (derived data only; nothing references it).
DROP TABLE catalogue_freshness;

-- 5. Migration ledger: only as part of this governed rollback.
DELETE FROM public.schema_migrations WHERE version = '0026_catalogue_freshness';

-- 6. Post-check: both must return 0 before COMMIT.
SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'humanoid'
  AND p.proname IN ('record_catalogue_change', 'guard_catalogue_freshness');
SELECT count(*) FROM pg_trigger WHERE tgname LIKE '%catalogue_freshness%';
COMMIT;
```

**Verify the catalogue data is unchanged.** Before `BEGIN` and after `COMMIT`, take a per-table row count and a content hash of every other `humanoid` table, e.g. `SELECT count(*), md5(string_agg(t::text, '|' ORDER BY t::text)) FROM humanoid.<table> t`, and compare them. Only `catalogue_freshness` and the ledger row may differ. The procedure writes no catalogue row.
