-- 0015_candidate_identity_decision.sql
--
-- Discovery Stage E (docs/16 §17.1): one append-only table for attributed human
-- decisions that two discovery candidates are, or are not, the same entity.
-- Designed from the first real NEURA crawl (run 2c64d1f3): two same-source
-- candidate pairs needed a pairwise decision, which promotion_audit (a single
-- candidate FK) cannot represent with real foreign keys.
--
-- Additive and idempotent: a new enum, a new table, two indexes and an
-- append-only trigger. No existing table, column or row is touched.
--
-- The schema is named explicitly (the production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'candidate_identity_decision_kind'
                     AND n.nspname = 'humanoid') THEN
        CREATE TYPE candidate_identity_decision_kind AS ENUM ('SAME_ENTITY', 'NOT_SAME_ENTITY');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS candidate_identity_decision (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_seq    BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    candidate_a_id  UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE RESTRICT,
    candidate_b_id  UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE RESTRICT,
    decision        candidate_identity_decision_kind NOT NULL,
    decided_by      TEXT NOT NULL,
    reason          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_identity_decision_pair_ordered CHECK (candidate_a_id < candidate_b_id),
    CONSTRAINT ck_identity_decision_attributed CHECK (btrim(decided_by) <> ''),
    CONSTRAINT ck_identity_decision_reasoned CHECK (btrim(reason) <> '')
);
COMMENT ON TABLE candidate_identity_decision IS
    'Stage E (docs/16 §17.1): attributed, append-only human decisions that two discovery '
    'candidates are / are not the same entity. Newest decision_seq per pair is effective. '
    'Merges nothing; candidate<->catalogue identity stays in the confirmed alias register.';

CREATE INDEX IF NOT EXISTS idx_identity_decision_pair ON candidate_identity_decision
    (candidate_a_id, candidate_b_id, decision_seq DESC);
CREATE INDEX IF NOT EXISTS idx_identity_decision_b ON candidate_identity_decision (candidate_b_id);

CREATE OR REPLACE FUNCTION refuse_identity_decision_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'candidate_identity_decision is append-only (docs/16 §17.1): % refused. '
        'Record a NEW decision instead; the newest decision for a pair is effective.', TG_OP
        USING ERRCODE = 'restrict_violation';
END$$;
COMMENT ON FUNCTION refuse_identity_decision_mutation() IS
    'Stage E: refuses UPDATE/DELETE on candidate_identity_decision at the database level.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_identity_decision_no_update') THEN
        CREATE TRIGGER trg_identity_decision_no_update
            BEFORE UPDATE ON candidate_identity_decision
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_identity_decision_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_identity_decision_no_delete') THEN
        CREATE TRIGGER trg_identity_decision_no_delete
            BEFORE DELETE ON candidate_identity_decision
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_identity_decision_mutation();
    END IF;
END $$;
