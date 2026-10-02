-- 0021_manufacturer_estimate_and_claim_targets.sql
--
-- DR-A5 stage G2-4 (owner-authorized), second half (0020 declared the enum label).
--
-- 1. `chk_price_type_shape` now accepts MANUFACTURER_ESTIMATE as a point price (a number in
--    `price`, no range bounds), exactly like PUBLIC / FROM / ESTIMATED. The other three
--    arms are unchanged, so every existing row still satisfies it.
-- 2. The accepted-claim layer (0019) gains the two catalogue targets this slice
--    materializes, `pricing_offer` and `availability_offer`: the `accepted_claim` target
--    kind, a `JSON` value type for a structured offer, and the same two offer tables as
--    `catalogue_write_audit` targets. Only CHECK constraints are replaced; the append-only
--    triggers and every existing row are untouched (a widened CHECK validates, never
--    updates).
--
-- Additive and backward compatible; idempotent (drop-if-exists, then add). The schema is
-- named explicitly (the production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

ALTER TABLE pricing_offer DROP CONSTRAINT IF EXISTS chk_price_type_shape;
ALTER TABLE pricing_offer ADD CONSTRAINT chk_price_type_shape CHECK (
    (price_type = 'QUOTE_ONLY'
        AND price IS NULL AND price_min IS NULL AND price_max IS NULL)
 OR (price_type = 'RANGE'
        AND price IS NULL AND price_min IS NOT NULL AND price_max IS NOT NULL
        AND price_max >= price_min)
 OR (price_type IN ('PUBLIC','FROM','ESTIMATED','MANUFACTURER_ESTIMATE')
        AND price IS NOT NULL AND price_min IS NULL AND price_max IS NULL)
);

ALTER TABLE accepted_claim DROP CONSTRAINT IF EXISTS ck_accepted_claim_target_kind;
ALTER TABLE accepted_claim ADD CONSTRAINT ck_accepted_claim_target_kind
    CHECK (target_kind IN ('robot_variant', 'specification', 'pricing_offer',
                           'availability_offer', 'NO_CATALOGUE_HOME'));
ALTER TABLE accepted_claim DROP CONSTRAINT IF EXISTS ck_accepted_claim_value_type;
ALTER TABLE accepted_claim ADD CONSTRAINT ck_accepted_claim_value_type
    CHECK (value_type IN ('TEXT', 'JSON'));

ALTER TABLE catalogue_write_audit DROP CONSTRAINT IF EXISTS ck_catalogue_write_audit_table;
ALTER TABLE catalogue_write_audit ADD CONSTRAINT ck_catalogue_write_audit_table
    CHECK (target_table IN ('robot_variant', 'specification', 'pricing_offer',
                            'availability_offer'));
