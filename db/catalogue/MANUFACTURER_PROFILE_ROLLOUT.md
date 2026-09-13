# Manufacturer profile rollout — migration 0013 + manufacturer data

Operational runbook for the manufacturer profile enrichment (PR #60). **Every
production step below needs its own explicit owner authorization**; approving one
step does not authorize the next.

## Topology and constraints

| Layer | Where | Deploys |
|---|---|---|
| Web (Next.js) | Netlify | automatically from `main` |
| API (FastAPI) | Vercel `humanoidonline-api` | automatically from `main` |
| Database | Neon, schema `humanoid` | manually (`db/bootstrap.py`, `db/import_catalogue.py`) |

- The API refuses to start when a migration it expects is **missing**; it only
  warns when the database is **ahead** of it (`app/db/migration_state.py`).
- Manufacturer reads in the web app use Next's Data Cache
  (`CATALOGUE_REVALIDATE_S = 300`), so a data change reaches cached pages some
  time after the database changes.
- `--manufacturers-only` writes `manufacturer` rows and MANUFACTURER evidence
  only. It never reads robot files and never writes robots, publication state,
  specifications, offers, capabilities, variants, deployments, images, providers,
  regions or robot-level evidence.

## Compatibility matrix (verified on throwaway databases; re-verify in production)

| Combination | Result |
|---|---|
| Previous API + migrated schema (0013, no import yet) | Works. The database is ahead; the previous API selects no new column and 0013 writes no data. |
| New web + previous API | Works. The detail page renders absent 0013 fields as UNKNOWN / not shown (`lib/manufacturer-profile.ts`). |
| New API + migrated schema before import | Works. Old values, new fields empty. |
| Previous API + **imported** data | **Fails**: a NULL `is_public_company` does not fit the previous API's boolean, so manufacturer detail returns 500. |
| Previous web + **imported** data | Misleading: the previous page renders an unknown listing status as "NO". |

The last two rows are why the import runs only after **both** the new API and
the new web are confirmed live.

## Rollout

### 1. Recovery safeguard
Create a Neon branch (point-in-time checkpoint) of `production`, e.g.
`pre-manufacturer-0013-<YYYYMMDD>`. It is a last-resort safeguard, **not** the
routine rollback (see *Recovery*).

### 2. Confirm only the reviewed migration is pending
From a checkout of the exact commit that will be merged, against production,
read-only:

```bash
cd apps/api
DATABASE_URL="<production URL>" APP_ENV=development uv run python - <<'EOF'
from app.db.migration_state import inspect_migration_state
from app.db.session import engine
with engine.connect() as connection:
    state = inspect_migration_state(connection)
print("missing:", state.missing)
print("drifted:", state.drifted)
print("ahead:  ", state.ahead)
EOF
```

Proceed only if `missing == ['0013_manufacturer_profile_fields']` and `drifted`
and `ahead` are both `[]`. Anything else: stop and report.

### 3. Apply migration 0013 (before merge)
```bash
DATABASE_URL="<production URL>" uv run db/bootstrap.py
```
Expect exactly `applying 0013_manufacturer_profile_fields` and `Applied 1 migration(s).`
Never pass `--seed`.

### 4. Verify the previous API and web tolerate the migrated schema
- `GET /ready` → 200.
- `GET /api/manufacturers` and `GET /api/manufacturers/figure-ai` → 200; the
  detail JSON still has **no** `sources` key (previous API).
- `/manufacturers` and `/manufacturers/figure-ai` on the site → 200 with content.

### 5. Merge, then confirm BOTH deployments are live
Merging deploys web and API independently, in either order; the new web tolerates
the previous API meanwhile. Before continuing, confirm both on the merge SHA:
- **API:** the production deployment's commit is the merge SHA, and
  `GET /api/manufacturers/figure-ai` contains the keys `sources`,
  `operating_locations`, `tracked_robot_count`.
- **Web:** the Netlify production deploy's commit is the merge SHA, and
  `/manufacturers/figure-ai` returns 200 with the labels `Headquarters` and
  `04 — COMPANY SOURCES`; `/manufacturers` cards show `PUBLISHED MODEL STATUS`.

Do not import until both are confirmed.

### 6. Scoped pre-import backup
Record what the import can change — manufacturer rows and MANUFACTURER evidence —
so recovery never needs a whole-database restore. Store the files off the machine.

```sql
-- psql "<production libpq URL>" -v ON_ERROR_STOP=1
\copy (SELECT * FROM humanoid.manufacturer ORDER BY id) TO 'pre-import-manufacturer.csv' WITH (FORMAT csv, HEADER)
\copy (SELECT * FROM humanoid.evidence_source WHERE subject_type = 'MANUFACTURER' ORDER BY id) TO 'pre-import-manufacturer-evidence.csv' WITH (FORMAT csv, HEADER)
SELECT count(*) AS manufacturers,
       md5(string_agg((to_jsonb(m) - 'updated_at')::text, '|' ORDER BY m.id)) AS manufacturer_md5
  FROM humanoid.manufacturer m;
SELECT count(*) AS company_evidence,
       md5(string_agg(to_jsonb(e)::text, '|' ORDER BY e.id)) AS company_evidence_md5
  FROM humanoid.evidence_source e WHERE subject_type = 'MANUFACTURER';
SELECT now() AS backup_taken_at;
```

### 7. Import manufacturer data only
From the merge SHA:
```bash
DATABASE_URL="<production URL>" uv run db/import_catalogue.py --manufacturers-only
DATABASE_URL="<production URL>" uv run db/validate_catalogue.py
```
Record `import_finished_at`. Review the output:
- `unmarked row(s) preserved` — company evidence without the
  `CATALOGUE_IMPORT` marker. The importer never deletes, rewrites or takes
  ownership of these rows, whatever their content.
- `EVIDENCE COLLISION (unmarked row preserved, ownership not assumed)` lines — an
  unmarked row shares a catalogue source's URL, type and observed date (exact
  content or edited). It was kept as it is and the catalogue's own copy was
  written beside it. The line asserts nothing about who wrote the row.
  **Stop and report each one** before treating the rollout as complete.
- `validate_catalogue.py` must print the three OK lines.

### 8. Verify the API content
- `GET /api/manufacturers/unitree` → `is_public_company: true`, `ticker: "SSE STAR Market: 688836"`.
- `GET /api/manufacturers/figure-ai` → `deployment_status: "COMMERCIAL"`, 4 `sources`.
- `GET /api/manufacturers/clone-robotics` → `incorporation: "United States (Delaware)"`.

### 9. Verify the pages by content — not by elapsed time
Fetch the rendered pages and check the actual text; repeat until every check
passes, recording each fetch's time and the matching excerpt as evidence:

| Page | Must contain |
|---|---|
| `/manufacturers/unitree` | `YES · SSE STAR Market: 688836` |
| `/manufacturers/figure-ai` | `4 SOURCES` and `Agent-assisted research · not human-verified` |
| `/manufacturers/clone-robotics` | `United States (Delaware)` |
| `/manufacturers` | Unitree card `COMMERCIAL`; Figure card `ALL DISCONTINUED` |

Waiting 300 s is not proof. If pages still show pre-import content well after the
cache window, do not declare the rollout complete: report it and investigate the
cache rather than assuming it will clear.

## Rollback and recovery

Prefer fixing forward. The schema change stays in place in every case: 0013 is
additive, the previous API tolerates it, and no down-migration exists (WS8-L7).

### Web problem
Publish the previous Netlify production deploy. **After the import** the previous
page renders unknown listing status as "NO"; recover the manufacturer data first
(below) if that is not acceptable.

### API problem
Promote the previous Vercel deployment. **After the import** the previous API
returns 500 on manufacturer detail (NULL listing status), so recover the
manufacturer data first, then roll the API back.

### Manufacturer data recovery (scoped)
Restores only what the import changed — manufacturer profile columns and
MANUFACTURER evidence — from the step 6 backup. Leads, buyer requirements, robots,
robot-level evidence and every other table are untouched, including writes made
after the import.

Before running, review what the recovery would revert:
```sql
-- Manufacturer rows edited after the import (their import-written columns revert).
SELECT slug, updated_at FROM humanoid.manufacturer
 WHERE updated_at > '<import_finished_at>' ORDER BY updated_at;
-- Company evidence written after the backup (marked rows are removed, unmarked kept).
SELECT id, managed_by, source_url, created_at FROM humanoid.evidence_source
 WHERE subject_type = 'MANUFACTURER' AND created_at > '<backup_taken_at>' ORDER BY created_at;
```

Then, in one transaction (any failed check raises and rolls everything back):
```sql
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path TO humanoid, public;
CREATE TEMP TABLE bk_manufacturer (LIKE manufacturer) ON COMMIT DROP;
CREATE TEMP TABLE bk_manufacturer_evidence (LIKE evidence_source) ON COMMIT DROP;
\copy bk_manufacturer FROM 'pre-import-manufacturer.csv' WITH (FORMAT csv, HEADER)
\copy bk_manufacturer_evidence FROM 'pre-import-manufacturer-evidence.csv' WITH (FORMAT csv, HEADER)

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM manufacturer m
             WHERE NOT EXISTS (SELECT 1 FROM bk_manufacturer b WHERE b.id = m.id)) THEN
    RAISE EXCEPTION 'manufacturer rows exist that the backup does not contain; review before recovery';
  END IF;
END $$;

-- Profile columns the importer writes, restored by id.
UPDATE manufacturer m SET
  name = b.name, legal_name = b.legal_name, country_region_id = b.country_region_id,
  headquarters_city = b.headquarters_city, incorporation = b.incorporation,
  operating_locations = b.operating_locations, website_url = b.website_url,
  founded_year = b.founded_year, description = b.description,
  target_markets = b.target_markets, commercial_model = b.commercial_model,
  deployment_status = b.deployment_status, deployment_note = b.deployment_note,
  is_public_company = b.is_public_company, ticker = b.ticker,
  parent_company = b.parent_company, parent_listing = b.parent_listing,
  parent_relationship = b.parent_relationship
FROM bk_manufacturer b WHERE b.id = m.id;

-- Company evidence the import wrote: marked rows the backup does not contain.
DELETE FROM evidence_source e
 WHERE e.subject_type = 'MANUFACTURER' AND e.managed_by = 'CATALOGUE_IMPORT'
   AND NOT EXISTS (SELECT 1 FROM bk_manufacturer_evidence b WHERE b.id = e.id);

-- Pre-import company evidence the import replaced, restored byte-for-byte.
INSERT INTO evidence_source
SELECT * FROM bk_manufacturer_evidence b
 WHERE NOT EXISTS (SELECT 1 FROM evidence_source e WHERE e.id = b.id);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM manufacturer m JOIN bk_manufacturer b USING (id)
             WHERE (to_jsonb(m) - 'updated_at') IS DISTINCT FROM (to_jsonb(b) - 'updated_at')) THEN
    RAISE EXCEPTION 'manufacturer rows differ from the backup after recovery';
  END IF;
  IF EXISTS (SELECT 1 FROM bk_manufacturer_evidence b
             WHERE NOT EXISTS (SELECT 1 FROM evidence_source e WHERE to_jsonb(e) = to_jsonb(b))) THEN
    RAISE EXCEPTION 'pre-import company evidence was not fully restored';
  END IF;
  IF EXISTS (SELECT 1 FROM evidence_source e
             WHERE e.subject_type = 'MANUFACTURER' AND e.managed_by = 'CATALOGUE_IMPORT'
               AND NOT EXISTS (SELECT 1 FROM bk_manufacturer_evidence b WHERE b.id = e.id)) THEN
    RAISE EXCEPTION 'import-written company evidence remains';
  END IF;
END $$;
COMMIT;
```

After committing, re-run the step 6 count/md5 queries: the manufacturer md5 must
equal the backup's; company evidence equals the backup plus any unmarked rows
written after it (listed in the review query). Then verify the pages by content
as in step 9.

### Neon checkpoint
Restoring the step 1 checkpoint discards **every** write made after it — leads,
buyer requirements, discovery and freshness data included. Use it only when damage
extends beyond manufacturer data and scoped recovery cannot repair it, and only by
explicit owner decision with a plan for reconciling the intervening writes.

## Record: 2026-09-13 production rollout and evidence-ownership reconciliation

The rollout completed on 2026-09-13: migration 0013 applied at 17:52:27 UTC, PR #60
merged as `496eef2`, and `--manufacturers-only` ran from that commit at
18:04:52–18:05:03 UTC. It wrote 29 manufacturer profiles and 62 catalogue-managed
company-evidence rows. No robot, publication, image or unrelated record changed.

**What the deployed importer did with pre-existing company evidence.** The
importer at `496eef2` treated an unmarked row as its own when every importer-written
column (URL, type, title, excerpt, published/observed/verified dates, confidence,
note) matched a catalogue source and the row had no `claim_fields`. It deleted such
rows and wrote marked copies. Production had six unmarked rows, all matching, so all
six were replaced (1X, Agility Robotics, Apptronik, Engineered Arts, Figure, Unitree).
The import output called them "pre-marker importer row(s) adopted".

**That rule did not establish provenance.** It was a content match. A hand-entered
row with identical content would have been treated the same way, so the output's
claim that these were importer rows was not something the importer verified.

**Retrospective evidence does support the six rows' importer origin.** Checked
read-only against Neon checkpoint branches after the rollout:
- Each of the six carried the exact `created_at` of robot-level evidence written in
  the same catalogue-import transaction. PostgreSQL gives every row inserted in one
  transaction the same `now()`, and five rows date from the 2026-08-19 00:01:28.988428
  initial import.
- The Unitree row received a new id and exactly that import's timestamp each time
  Unitree was re-imported on 2026-09-12 (10:10:26, 13:20:10, 13:43:24). That is the
  earlier importer's delete-and-reinsert pattern.

A field-by-field comparison with the pre-import backup found no substantive change.
Each row received a new id, `managed_by = 'CATALOGUE_IMPORT'` and `claim_fields`.
Four of them carry `verified_at = 2026-07-24` (1X, Agility Robotics, Engineered Arts,
Unitree) and are now catalogue-managed, so a future import re-creates them from
`manufacturers.json`. They were equally replaceable before 0013, when every full
import deleted all company evidence. The six rows and all profile data are left as
they are.

**Correction.** The importer no longer takes ownership of any unmarked row. Every
unmarked row is preserved exactly, including exact-content matches, and a row that
shares a catalogue source's URL, type and observed date is reported as a collision
that asserts no ownership. The catalogue keeps its own marked copy beside it.
Migration 0013 is unchanged; see `db/migrations/README.md` for its historical note.
