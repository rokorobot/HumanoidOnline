-- 0023_commercial_status_claim_target_and_proposal_origin.sql
--
-- G5 (owner ruling 2026-10-04, "commercial maturity joins the governed claim pipeline").
--
-- 1. The accepted-claim layer gains one catalogue target, `commercial_status`: the robot's
--    own `commercial_status` column and its `commercial_status_evidence` rows, written through
--    the catalogue file. Only the CHECK constraint is replaced (drop-if-exists, then add); the
--    append-only triggers and every existing row are untouched (a widened CHECK validates, never
--    updates). `catalogue_write_audit` already allows target_table 'robot'.
--
-- 2. A proposal carries an operational ORIGIN: NEW_MODEL or CATALOGUE_ENRICHMENT. It is
--    review/reporting metadata only and never changes proposal semantics. Added as a column with a
--    constant default so the append-only table is not UPDATEd; every existing proposal attached to
--    an existing robot identity, which is exactly CATALOGUE_ENRICHMENT (G5-1 `lane_for_proposal`).
--
-- Additive, backward compatible and idempotent. The schema is named explicitly (the production
-- role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

ALTER TABLE accepted_claim DROP CONSTRAINT IF EXISTS ck_accepted_claim_target_kind;
ALTER TABLE accepted_claim ADD CONSTRAINT ck_accepted_claim_target_kind
    CHECK (target_kind IN ('robot_variant', 'specification', 'pricing_offer',
                           'availability_offer', 'robot_spec', 'commercial_status',
                           'NO_CATALOGUE_HOME'));

ALTER TABLE discovery_claim_proposal
    ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'CATALOGUE_ENRICHMENT';
ALTER TABLE discovery_claim_proposal DROP CONSTRAINT IF EXISTS ck_claim_proposal_origin;
ALTER TABLE discovery_claim_proposal ADD CONSTRAINT ck_claim_proposal_origin
    CHECK (origin IN ('NEW_MODEL', 'CATALOGUE_ENRICHMENT'));
