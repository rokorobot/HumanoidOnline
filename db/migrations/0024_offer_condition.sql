-- 0024_offer_condition.sql
--
-- Owner-approved schema change (2026-10-05): an offer states the CONDITION of the unit it is
-- for. Until now `pricing_offer` and `availability_offer` could not tell a new unit from a used
-- one, and `uq_availability_logical` would have made a used offer collide with (or replace) the
-- new offer of the same robot x variant x provider x region x transaction.
--
--  1. New enum `offer_condition` (NEW, USED, OPEN_BOX, REFURBISHED).
--  2. `condition offer_condition NOT NULL DEFAULT 'NEW'` on BOTH offer tables. Every existing
--     row is a new-product commercial offer (a catalogue/seed audit found no used, open-box or
--     refurbished listing); the guard below REFUSES the migration if any existing row's own
--     text says otherwise, so the default can never silently mislabel a used offer as NEW.
--  3. `condition` joins the availability logical-uniqueness index. `pricing_offer` has never had
--     a logical-uniqueness index and none is invented here.
--
-- Additive, backward compatible (existing readers/writers that never name `condition` get NEW)
-- and idempotent. The schema is named explicitly (the production role is not `humanoid`; 0013).

SET search_path TO humanoid, public;

-- Guard matching rule (owner decision 2026-10-05, after the production preflight found two
-- false positives). The guard looks for EXPLICIT condition-bearing wording in the offer's own
-- text fields: refurb*, open box / open-box, second-hand, pre-owned, bazaar / bazar, renewed,
-- ex-demo, the phrases "used unit|item|robot|product|offer|condition|stock", "condition: used"
-- and "(used)". The bare verb "used" is deliberately NOT a signal: "so LIMITED was not used",
-- "status was used", "label used" or "method used" are editorial prose about a decision, not
-- evidence that the offered unit is not new. Conservative on purpose (no language parser): a
-- wording this list does not know would default to NEW, which is why the list stays explicit
-- and why every existing production offer was also read before authorizing this migration.
DO $$
DECLARE
    offending bigint;
BEGIN
    SELECT
        (SELECT count(*) FROM pricing_offer
          WHERE concat_ws(' ', note, price_basis, package_contents, order_status_note,
                          edition_note, shipping_terms, warranty_terms)
                ~* '(refurb|open[ -]?box|second[ -]?hand|pre-?owned|bazaar|bazar|renewed|ex-?demo|\mused[ -](unit|item|robot|product|offer|condition|stock)s?\M|\mcondition\M[ :=-]{1,3}used\M|\(used\))')
      + (SELECT count(*) FROM availability_offer
          WHERE concat_ws(' ', note, seller_wording, delivery_estimate_label)
                ~* '(refurb|open[ -]?box|second[ -]?hand|pre-?owned|bazaar|bazar|renewed|ex-?demo|\mused[ -](unit|item|robot|product|offer|condition|stock)s?\M|\mcondition\M[ :=-]{1,3}used\M|\(used\))')
    INTO offending;
    IF offending > 0 THEN
        RAISE EXCEPTION
            '0024: % existing offer row(s) mention a used/open-box/refurbished unit; refusing to default them to NEW. Review them and set their condition explicitly first.',
            offending;
    END IF;
END $$;

DO $$
BEGIN
    IF to_regtype('offer_condition') IS NULL THEN
        CREATE TYPE offer_condition AS ENUM ('NEW', 'USED', 'OPEN_BOX', 'REFURBISHED');
    END IF;
END $$;

ALTER TABLE pricing_offer
    ADD COLUMN IF NOT EXISTS condition offer_condition NOT NULL DEFAULT 'NEW';
ALTER TABLE availability_offer
    ADD COLUMN IF NOT EXISTS condition offer_condition NOT NULL DEFAULT 'NEW';

DROP INDEX IF EXISTS uq_availability_logical;
CREATE UNIQUE INDEX uq_availability_logical ON availability_offer (
    robot_id,
    COALESCE(variant_id,  '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(provider_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(region_id,   '00000000-0000-0000-0000-000000000000'::uuid),
    transaction_type,
    condition
) WHERE is_current;

-- The commercial snapshot's "obtainable" dimension is about the NEW product: a used unit's
-- stock must not make a robot obtainable as new. Same columns, same order (CREATE OR REPLACE).
CREATE OR REPLACE VIEW robot_commercial_snapshot AS
SELECT
    r.id,
    r.slug,
    r.name,
    r.commercial_status                             AS maturity,
    EXISTS (SELECT 1 FROM availability_offer a
            WHERE a.robot_id = r.id AND a.is_current AND a.condition = 'NEW'
              AND commercially_accessible(a.availability_status))
                                                    AS is_obtainable,
    (SELECT count(*) FROM deployment d WHERE d.robot_id = r.id)
                                                    AS deployment_count,
    (SELECT sum(d.contract_value) FROM deployment d WHERE d.robot_id = r.id)
                                                    AS contracted_value,
    array(SELECT DISTINCT a.transaction_type::text FROM availability_offer a
          WHERE a.robot_id = r.id AND a.is_current AND a.condition = 'NEW'
            AND commercially_accessible(a.availability_status))
                                                    AS available_modes
FROM robot r;

-- The dormant Phase 3-5 offer views were built with `a.*`, which froze the availability_offer
-- column list at creation; they are recreated so they carry `condition`, and a price only
-- prices the availability offer of the SAME condition (a used price never prices a new offer).
DROP VIEW IF EXISTS lease_offer;
DROP VIEW IF EXISTS purchase_offer;
DROP VIEW IF EXISTS rental_offer;
DROP VIEW IF EXISTS commercial_offer;

CREATE VIEW commercial_offer AS
SELECT
    a.*,
    p.id             AS pricing_offer_id,
    p.price, p.price_min, p.price_max, p.currency,
    p.billing_period, p.price_type,
    p.provider_id    AS price_provider_id,
    p.region_id      AS price_region_id
FROM availability_offer a
LEFT JOIN LATERAL (
    SELECT po.*
    FROM pricing_offer po
    WHERE po.robot_id = a.robot_id
      AND po.is_current
      AND po.transaction_type = a.transaction_type
      AND po.condition = a.condition   -- a used price never prices the new offer
      AND (po.variant_id  = a.variant_id  OR po.variant_id  IS NULL)
      AND (po.provider_id = a.provider_id OR po.provider_id IS NULL)
      AND (   po.region_id = a.region_id
           OR po.region_id = (SELECT r.parent_id FROM region r WHERE r.id = a.region_id)
           OR po.region_id = (SELECT r2.id FROM region r2 WHERE r2.code = 'GLOBAL')
           OR po.region_id IS NULL)
    ORDER BY (po.provider_id IS NOT NULL) DESC,
             (po.region_id = a.region_id) DESC,
             (po.variant_id IS NOT NULL) DESC,
             po.updated_at DESC
    LIMIT 1
) p ON TRUE;
COMMENT ON VIEW commercial_offer IS
    'availability_offer + its single best-matching current price (semantics in '
    'the block comment above). Base projection for the Phase 3-5 vertical views.';

CREATE VIEW rental_offer   AS SELECT * FROM commercial_offer
    WHERE transaction_type IN ('RENTAL','SUBSCRIPTION');
CREATE VIEW purchase_offer AS SELECT * FROM commercial_offer
    WHERE transaction_type IN ('PURCHASE','DEVELOPER');
CREATE VIEW lease_offer    AS SELECT * FROM commercial_offer
    WHERE transaction_type IN ('LEASE','RAAS');
