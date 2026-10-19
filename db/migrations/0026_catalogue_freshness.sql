-- 0026_catalogue_freshness.sql
--
-- Automatic catalogue freshness: ONE durable, database-maintained answer to "when did the
-- canonical catalogue content last change?", read by GET /api/market-snapshot as
-- `latest_catalogue_updated_at` (the homepage's CATALOGUE UPDATED date).
--
--  1. catalogue_freshness: a single row (id = 1) holding
--       latest_public_update_at  last committed change that touched PUBLIC content: a published
--                                robot (or a robot being published / unpublished), its variants,
--                                images, specifications, capabilities, use-case fits, offers and
--                                deployments, or a manufacturer / provider / capability / use
--                                case / spec definition that a published robot uses;
--       latest_update_at         last committed change to ANY canonical content row, unpublished
--                                drafts included (recorded, never shown on the homepage).
--  2. record_catalogue_change(): a row-level constraint trigger on INSERT/UPDATE/DELETE of
--     every canonical content table, DEFERRABLE INITIALLY DEFERRED: it runs at COMMIT, still
--     inside the writing transaction, so a rolled-back or failed write never advances the date,
--     and every write path (importer, promotion executor, internal admin, hand-written SQL) is
--     covered without code in any of them. An UPDATE that changes nothing but `updated_at` /
--     `search_vector` is ignored (no-op).
--     The timestamp is clock_timestamp() taken while the transaction commits - NOT now(), which
--     is the transaction's START: a long import begun before midnight UTC and committed after it
--     records the commit day. It only ever moves forward (GREATEST), and the row is written at
--     most twice per transaction (once for any change, once for the first public one): the
--     per-row trigger calls after that only read two transaction-local settings.
--     Because the row is written at commit, its row lock is held only for the commit itself:
--     concurrent catalogue writers queue briefly at commit instead of for their whole
--     transaction. (A session that runs SET CONSTRAINTS ALL IMMEDIATE gets the write at that
--     point instead - the date is then that moment, still inside its transaction.)
--  3. guard_catalogue_freshness(): the row may be changed only by that trigger (refused at
--     trigger depth 1, i.e. from any direct statement); DELETE and TRUNCATE are refused.
--
-- Deliberately NOT tracked: evidence_source (evidence observation is reported separately as
-- `latest_observed_at`), robot_status_history (derived history; the robot row change already
-- counts), region (reference data), and every discovery / lead / audit table.
--
-- Bootstrap (this migration only, one-time): the row is seeded from the newest `updated_at`
-- already stored on the trigger-maintained canonical tables, split public / all exactly as
-- above. Tables without `updated_at` (robot_variant, robot_capability, use_case_fit) cannot
-- contribute to the seed; from the first write after this migration they are tracked like
-- everything else. A fresh database built from db/schema.sql starts with
-- NULLs (UNKNOWN) and is set by its first catalogue write.
--
-- Additive and idempotent. No existing row changes. The schema is named explicitly
-- (production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

CREATE TABLE IF NOT EXISTS catalogue_freshness (
    id                       SMALLINT PRIMARY KEY DEFAULT 1,
    latest_public_update_at  TIMESTAMPTZ,
    latest_update_at         TIMESTAMPTZ,
    CONSTRAINT ck_catalogue_freshness_single_row CHECK (id = 1)
);
COMMENT ON TABLE catalogue_freshness IS
    'Single row. Maintained ONLY by record_catalogue_change() at commit of the writing transaction: '
    'latest_public_update_at = last committed change to public catalogue content, '
    'latest_update_at = last committed change to any canonical content (drafts included).';

CREATE OR REPLACE FUNCTION record_catalogue_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = humanoid, public AS $$
DECLARE
    old_row   JSONB;
    new_row   JSONB;
    ids       UUID[];
    is_public BOOLEAN;
    stamp     TIMESTAMPTZ;
BEGIN
    -- Transaction-local flags (set_config(..., true)): once the public date is recorded for
    -- this transaction, every later row event of it has nothing left to do.
    IF current_setting('humanoid.catalogue_public_recorded', true) = 'yes' THEN
        RETURN NULL;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        old_row := to_jsonb(OLD) - 'updated_at' - 'search_vector';
    END IF;
    IF TG_OP <> 'DELETE' THEN
        new_row := to_jsonb(NEW) - 'updated_at' - 'search_vector';
    END IF;
    IF TG_OP = 'UPDATE' AND old_row = new_row THEN
        RETURN NULL;                                   -- a rewrite that changes nothing
    END IF;

    IF TG_TABLE_NAME = 'robot' THEN                    -- publishing / unpublishing is public
        is_public := coalesce((old_row->>'is_published')::boolean, false)
                  OR coalesce((new_row->>'is_published')::boolean, false);
    ELSIF TG_TABLE_NAME IN ('manufacturer', 'provider', 'capability', 'use_case',
                            'spec_definition') THEN
        ids := ARRAY[(old_row->>'id')::uuid, (new_row->>'id')::uuid];
        is_public := CASE TG_TABLE_NAME
            WHEN 'manufacturer' THEN EXISTS (
                SELECT 1 FROM robot r WHERE r.is_published AND r.manufacturer_id = ANY(ids))
            WHEN 'provider' THEN EXISTS (
                SELECT 1 FROM robot r WHERE r.is_published AND (
                    EXISTS (SELECT 1 FROM pricing_offer o
                            WHERE o.robot_id = r.id AND o.provider_id = ANY(ids))
                    OR EXISTS (SELECT 1 FROM availability_offer o
                               WHERE o.robot_id = r.id AND o.provider_id = ANY(ids))
                    OR EXISTS (SELECT 1 FROM deployment d
                               WHERE d.robot_id = r.id AND d.provider_id = ANY(ids))))
            WHEN 'capability' THEN EXISTS (
                SELECT 1 FROM robot_capability c JOIN robot r ON r.id = c.robot_id
                WHERE r.is_published AND c.capability_id = ANY(ids))
            WHEN 'use_case' THEN EXISTS (
                SELECT 1 FROM use_case_fit f JOIN robot r ON r.id = f.robot_id
                WHERE r.is_published AND f.use_case_id = ANY(ids))
            ELSE EXISTS (
                SELECT 1 FROM specification s JOIN robot r ON r.id = s.robot_id
                WHERE r.is_published AND s.definition_id = ANY(ids))
        END;
    ELSE                                               -- a robot's own child rows
        ids := ARRAY[(old_row->>'robot_id')::uuid, (new_row->>'robot_id')::uuid];
        is_public := EXISTS (SELECT 1 FROM robot r WHERE r.is_published AND r.id = ANY(ids));
    END IF;

    -- Commit-time clock, never backwards: a transaction that commits after a newer one cannot
    -- move the date back.
    stamp := clock_timestamp();
    IF is_public THEN
        UPDATE catalogue_freshness
           SET latest_update_at = GREATEST(latest_update_at, stamp),
               latest_public_update_at = GREATEST(latest_public_update_at, stamp)
         WHERE id = 1;
        PERFORM set_config('humanoid.catalogue_public_recorded', 'yes', true);
        PERFORM set_config('humanoid.catalogue_change_recorded', 'yes', true);
    ELSIF current_setting('humanoid.catalogue_change_recorded', true) IS DISTINCT FROM 'yes' THEN
        UPDATE catalogue_freshness
           SET latest_update_at = GREATEST(latest_update_at, stamp)
         WHERE id = 1;
        PERFORM set_config('humanoid.catalogue_change_recorded', 'yes', true);
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION guard_catalogue_freshness() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND pg_trigger_depth() > 1 THEN
        RETURN NEW;                                    -- written by record_catalogue_change()
    END IF;
    RAISE EXCEPTION 'catalogue_freshness is maintained only by record_catalogue_change() '
                    '(% refused)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

DROP TRIGGER IF EXISTS trg_catalogue_freshness_guard ON catalogue_freshness;
CREATE TRIGGER trg_catalogue_freshness_guard
    BEFORE UPDATE OR DELETE ON catalogue_freshness
    FOR EACH ROW EXECUTE FUNCTION guard_catalogue_freshness();
DROP TRIGGER IF EXISTS trg_catalogue_freshness_no_truncate ON catalogue_freshness;
CREATE TRIGGER trg_catalogue_freshness_no_truncate
    BEFORE TRUNCATE ON catalogue_freshness
    FOR EACH STATEMENT EXECUTE FUNCTION guard_catalogue_freshness();

DO $$
DECLARE t TEXT;
BEGIN
    FOR t IN
        SELECT unnest(ARRAY[
            'robot','robot_variant','robot_image','specification','robot_capability',
            'use_case_fit','pricing_offer','availability_offer','deployment',
            'manufacturer','provider','capability','use_case','spec_definition'
        ])
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_catalogue_freshness ON %1$s', t);
        EXECUTE format(
            'CREATE CONSTRAINT TRIGGER trg_%1$s_catalogue_freshness
             AFTER INSERT OR UPDATE OR DELETE ON %1$s
             DEFERRABLE INITIALLY DEFERRED
             FOR EACH ROW EXECUTE FUNCTION record_catalogue_change();', t);
    END LOOP;
END$$;

-- One-time bootstrap from what the database already records (see header).
INSERT INTO catalogue_freshness (id, latest_public_update_at, latest_update_at)
SELECT 1,
       (SELECT max(ts) FROM (
            SELECT r.updated_at AS ts FROM robot r WHERE r.is_published
            UNION ALL SELECT t.updated_at FROM specification t
                JOIN robot r ON r.id = t.robot_id WHERE r.is_published
            UNION ALL SELECT t.updated_at FROM pricing_offer t
                JOIN robot r ON r.id = t.robot_id WHERE r.is_published
            UNION ALL SELECT t.updated_at FROM availability_offer t
                JOIN robot r ON r.id = t.robot_id WHERE r.is_published
            UNION ALL SELECT t.updated_at FROM deployment t
                JOIN robot r ON r.id = t.robot_id WHERE r.is_published
            UNION ALL SELECT t.updated_at FROM robot_image t
                JOIN robot r ON r.id = t.robot_id WHERE r.is_published
            UNION ALL SELECT m.updated_at FROM manufacturer m
                WHERE EXISTS (SELECT 1 FROM robot r
                              WHERE r.is_published AND r.manufacturer_id = m.id)
        ) public_rows),
       (SELECT max(ts) FROM (
            SELECT updated_at AS ts FROM robot
            UNION ALL SELECT updated_at FROM specification
            UNION ALL SELECT updated_at FROM pricing_offer
            UNION ALL SELECT updated_at FROM availability_offer
            UNION ALL SELECT updated_at FROM deployment
            UNION ALL SELECT updated_at FROM robot_image
            UNION ALL SELECT updated_at FROM manufacturer
            UNION ALL SELECT updated_at FROM provider
        ) all_rows)
ON CONFLICT (id) DO NOTHING;
