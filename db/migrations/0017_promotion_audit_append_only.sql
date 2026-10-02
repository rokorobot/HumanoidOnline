-- 0017_promotion_audit_append_only.sql
--
-- DR-A5 section 19.3 (owner-authorized follow-up B): make `promotion_audit`
-- append-only AT THE DATABASE, matching the intent the application already enforces
-- with an ORM listener. UPDATE and DELETE are refused by PostgreSQL itself, so raw
-- SQL can no longer alter the human-approval and promotion lineage.
--
-- Additive and idempotent: two functions and two triggers. No table, column, index
-- or row is touched, so existing audit rows stay byte-for-byte identical, INSERT is
-- unaffected (every governed path only inserts), and an application build that does
-- not know about this migration keeps working (it never updates or deletes audit rows;
-- the ORM already refuses to).
--
-- One deliberate carve-out, tested: `promoted_robot_id` is `ON DELETE SET NULL`, so
-- deleting a robot makes PostgreSQL update the referencing audit rows. That internal
-- referential action may only null the robot link; a direct UPDATE is refused.
--
-- The schema is named explicitly (the production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

CREATE OR REPLACE FUNCTION refuse_promotion_audit_delete()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'promotion_audit is append-only (DR-A5 section 19.3): % refused. '
        'Record a NEW audit row instead; existing rows are never deleted.', TG_OP
        USING ERRCODE = 'restrict_violation';
END$$;
COMMENT ON FUNCTION refuse_promotion_audit_delete() IS
    'DR-A5 follow-up: refuses every DELETE on promotion_audit at the database level.';

-- UPDATE is refused too, with ONE exception that is not an application write: the
-- foreign key `promoted_robot_id ... ON DELETE SET NULL`. When a robot is deleted
-- PostgreSQL itself updates the referencing audit rows, inside the referential-action
-- trigger (pg_trigger_depth() > 1; a direct UPDATE runs this trigger at depth 1). That
-- internal update may ONLY null the robot link and change nothing else, so deleting a
-- robot keeps working exactly as before. A direct UPDATE, including one that nulls the
-- link, is refused.
CREATE OR REPLACE FUNCTION guard_promotion_audit_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF pg_trigger_depth() > 1
       AND OLD.promoted_robot_id IS NOT NULL
       AND NEW.promoted_robot_id IS NULL
       AND (to_jsonb(OLD) - 'promoted_robot_id') = (to_jsonb(NEW) - 'promoted_robot_id') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION
        'promotion_audit is append-only (DR-A5 section 19.3): % refused. '
        'Record a NEW audit row instead; existing rows are never changed.', TG_OP
        USING ERRCODE = 'restrict_violation';
END$$;
COMMENT ON FUNCTION guard_promotion_audit_update() IS
    'DR-A5 follow-up: refuses UPDATE on promotion_audit except the FK ON DELETE SET NULL action.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'trg_promotion_audit_no_update'
                     AND tgrelid = 'humanoid.promotion_audit'::regclass) THEN
        CREATE TRIGGER trg_promotion_audit_no_update
            BEFORE UPDATE ON promotion_audit
            FOR EACH ROW EXECUTE FUNCTION guard_promotion_audit_update();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'trg_promotion_audit_no_delete'
                     AND tgrelid = 'humanoid.promotion_audit'::regclass) THEN
        CREATE TRIGGER trg_promotion_audit_no_delete
            BEFORE DELETE ON promotion_audit
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_promotion_audit_delete();
    END IF;
END $$;
