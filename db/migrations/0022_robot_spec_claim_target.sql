-- 0022_robot_spec_claim_target.sql
--
-- DR-A5 (owner-authorized IRON current-configuration slice): the accepted-claim layer gains
-- one more catalogue target, `robot_spec`: a first-class `robot` column (here
-- `degrees_of_freedom`) written through the catalogue file's `specs` block. The
-- `catalogue_write_audit` target tables gain `robot` for the same reason.
--
-- Only two CHECK constraints are replaced (drop-if-exists, then add). The append-only
-- triggers and every existing row are untouched (a widened CHECK validates, never updates);
-- no existing value changes meaning. Additive, backward compatible and idempotent. The schema
-- is named explicitly (the production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

ALTER TABLE accepted_claim DROP CONSTRAINT IF EXISTS ck_accepted_claim_target_kind;
ALTER TABLE accepted_claim ADD CONSTRAINT ck_accepted_claim_target_kind
    CHECK (target_kind IN ('robot_variant', 'specification', 'pricing_offer',
                           'availability_offer', 'robot_spec', 'NO_CATALOGUE_HOME'));

ALTER TABLE catalogue_write_audit DROP CONSTRAINT IF EXISTS ck_catalogue_write_audit_table;
ALTER TABLE catalogue_write_audit ADD CONSTRAINT ck_catalogue_write_audit_table
    CHECK (target_table IN ('robot_variant', 'specification', 'pricing_offer',
                            'availability_offer', 'robot'));
