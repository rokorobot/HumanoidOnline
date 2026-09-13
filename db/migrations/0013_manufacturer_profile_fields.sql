-- 0013_manufacturer_profile_fields.sql
--
-- Additive, idempotent. The manufacturer profile could not say several true
-- things, and said one false thing by default:
--
--  1. PUBLIC STATUS. `is_public_company` was BOOLEAN NOT NULL DEFAULT FALSE and
--     the importer filled FALSE for a missing key, so "listing status not
--     researched" rendered as "PUBLIC CO.: NO". NULL now means unknown; TRUE and
--     FALSE are asserted facts for the exact entity the record represents.
--     Existing FALSE values are left untouched here — the catalogue importer
--     rewrites every manufacturer from source, which is where each value is
--     re-decided against evidence.
--
--  2. LISTED PARENT. A subsidiary or business unit of a listed group is not
--     itself listed. `parent_company` / `parent_listing` / `parent_relationship`
--     record that ownership separately from the manufacturer's own status.
--     (`funding_status` is deliberately not reused.)
--
--  3. HEADQUARTERS vs INCORPORATION vs OPERATIONS. `country_region_id` is the
--     headquarters country. `headquarters_city`, `incorporation` and
--     `operating_locations` keep the other location facts distinct, so a
--     registered office or a factory is never presented as the headquarters.
--
--  4. HUMANOID DEPLOYMENT. `deployment_status` is scoped to humanoid deployment;
--     `deployment_note` states what the status rests on (announcement, pilot,
--     documented deployment, sale).
--
--  5. FIELD ATTRIBUTION. `evidence_source.claim_fields` names the profile
--     fields a MANUFACTURER evidence row supports, so each company fact can be
--     attributed to its source. NULL on every pre-existing row (no claim made).

ALTER TABLE manufacturer ALTER COLUMN is_public_company DROP NOT NULL;
ALTER TABLE manufacturer ALTER COLUMN is_public_company DROP DEFAULT;

ALTER TABLE manufacturer ADD COLUMN IF NOT EXISTS headquarters_city   TEXT;
ALTER TABLE manufacturer ADD COLUMN IF NOT EXISTS incorporation       TEXT;
ALTER TABLE manufacturer ADD COLUMN IF NOT EXISTS operating_locations TEXT[];
ALTER TABLE manufacturer ADD COLUMN IF NOT EXISTS parent_company      TEXT;
ALTER TABLE manufacturer ADD COLUMN IF NOT EXISTS parent_listing      TEXT;
ALTER TABLE manufacturer ADD COLUMN IF NOT EXISTS parent_relationship TEXT;
ALTER TABLE manufacturer ADD COLUMN IF NOT EXISTS deployment_note     TEXT;

ALTER TABLE evidence_source ADD COLUMN IF NOT EXISTS claim_fields TEXT[];

COMMENT ON COLUMN manufacturer.country_region_id IS
    'Headquarters country. Not the incorporation jurisdiction and not an operating '
    'location. NULL when the headquarters is unresolved.';
COMMENT ON COLUMN manufacturer.is_public_company IS
    'Whether THIS entity''s own shares are publicly listed. NULL = unknown (never '
    'rendered as NO). A listed parent is recorded in parent_* instead.';
COMMENT ON COLUMN manufacturer.deployment_status IS
    'Humanoid deployment status of the company (commercial_status vocabulary), '
    'not the maturity of non-humanoid products. Evidence-gated like robot status.';
COMMENT ON COLUMN evidence_source.claim_fields IS
    'MANUFACTURER rows: the profile fields this source supports. NULL = no field claim.';
