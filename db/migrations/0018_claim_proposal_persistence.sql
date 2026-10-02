-- 0018_claim_proposal_persistence.sql
--
-- DR-A5 B-prime, stage G2-1 (owner-authorized): persistence foundation for governed
-- claim proposals. Three NEW tables (immutable proposals, append-only proposal
-- sightings, append-only human decisions), one enum and one refuse-mutation trigger
-- function with six statement-level triggers.
--
-- Additive and idempotent. No existing table, column, row or privilege is touched,
-- `candidate_claim` is NOT modified, and an application build that does not know these
-- tables keeps working. Nothing here reads or writes the catalogue: the tables have no
-- foreign key to any canonical table (robots are referenced by slug text), so no
-- referential action can ever update or delete an immutable row.
--
-- The schema is named explicitly (the production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'proposal_decision_kind' AND n.nspname = 'humanoid') THEN
        CREATE TYPE proposal_decision_kind AS ENUM ('ACCEPT', 'REJECT', 'DEFER');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS discovery_claim_proposal (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_seq           BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    -- Content identity: sha256 over extractor key/version, source url, kind, edition,
    -- target, verbatim value and parsed parts. A changed value is a NEW digest.
    digest                 TEXT NOT NULL UNIQUE,
    -- Slot identity: sha256 over (source key, robot_slug, kind, edition, evidence_locator)
    -- -- the page position a proposal is a claim ABOUT, never its value. Same slot + new digest =
    -- the older proposal is SUPERSEDED (derived, never stored).
    slot_key               TEXT NOT NULL,
    source_id              UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    source_url             TEXT NOT NULL,
    -- Soft reference to the catalogue robot by slug. Deliberately NOT a foreign key:
    -- an FK action would UPDATE/DELETE an immutable row, and this layer must never
    -- reach into the catalogue. Standard/Pro are `edition`, never robot identities.
    robot_slug             TEXT NOT NULL,
    edition                TEXT,
    kind                   TEXT NOT NULL,
    target                 TEXT NOT NULL,
    representability       TEXT NOT NULL,
    value                  TEXT NOT NULL,
    structured             JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_excerpt       TEXT NOT NULL,
    evidence_locator       TEXT NOT NULL,
    extraction_method      extraction_method NOT NULL,
    extraction_confidence  extraction_confidence NOT NULL,
    claim_status           TEXT NOT NULL DEFAULT 'NOT_VERIFIED',
    gap                    TEXT,
    review_questions       JSONB NOT NULL DEFAULT '[]'::jsonb,
    extractor_key          TEXT NOT NULL,
    extractor_version      TEXT NOT NULL,
    -- Origin observation (first sighting). Later sightings are rows of
    -- discovery_proposal_observation. No dependency on evidence_source row ids.
    origin_fetched_page_id UUID NOT NULL REFERENCES fetched_page(id) ON DELETE RESTRICT,
    origin_crawl_run_id    UUID NOT NULL REFERENCES crawl_run(id) ON DELETE RESTRICT,
    origin_content_hash    TEXT NOT NULL,
    origin_retrieved_at    TIMESTAMPTZ NOT NULL,
    ingested_by            TEXT NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_claim_proposal_digest CHECK (digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_claim_proposal_slot CHECK (slot_key ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_claim_proposal_representability
        CHECK (representability IN ('CLEAN', 'PARTIAL', 'UNREPRESENTABLE')),
    CONSTRAINT ck_claim_proposal_not_verified CHECK (claim_status = 'NOT_VERIFIED'),
    CONSTRAINT ck_claim_proposal_review_questions
        CHECK (jsonb_typeof(review_questions) = 'array'),
    CONSTRAINT ck_claim_proposal_structured CHECK (jsonb_typeof(structured) = 'object'),
    CONSTRAINT ck_claim_proposal_excerpt CHECK (btrim(evidence_excerpt) <> ''),
    CONSTRAINT ck_claim_proposal_locator CHECK (btrim(evidence_locator) <> ''),
    CONSTRAINT ck_claim_proposal_robot_slug CHECK (btrim(robot_slug) <> ''),
    CONSTRAINT ck_claim_proposal_attributed CHECK (btrim(ingested_by) <> '')
);
COMMENT ON TABLE discovery_claim_proposal IS
    'DR-A5 B-prime (G2-1): immutable extraction proposal. NOT a claim and NOT verified; '
    'never read by the public API, the catalogue or promotion. A changed value is a new row.';

CREATE INDEX IF NOT EXISTS idx_claim_proposal_slot ON discovery_claim_proposal (slot_key, proposal_seq DESC);
CREATE INDEX IF NOT EXISTS idx_claim_proposal_robot ON discovery_claim_proposal (robot_slug);
CREATE INDEX IF NOT EXISTS idx_claim_proposal_source ON discovery_claim_proposal (source_id);
CREATE INDEX IF NOT EXISTS idx_claim_proposal_page ON discovery_claim_proposal (origin_fetched_page_id);
CREATE INDEX IF NOT EXISTS idx_claim_proposal_run ON discovery_claim_proposal (origin_crawl_run_id);

CREATE TABLE IF NOT EXISTS discovery_proposal_observation (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    observation_seq  BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    proposal_id      UUID NOT NULL REFERENCES discovery_claim_proposal(id) ON DELETE RESTRICT,
    fetched_page_id  UUID NOT NULL REFERENCES fetched_page(id) ON DELETE RESTRICT,
    crawl_run_id     UUID NOT NULL REFERENCES crawl_run(id) ON DELETE RESTRICT,
    content_hash     TEXT NOT NULL,
    retrieved_at     TIMESTAMPTZ NOT NULL,
    observed_by      TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_proposal_observation UNIQUE (proposal_id, fetched_page_id),
    CONSTRAINT ck_proposal_observation_attributed CHECK (btrim(observed_by) <> '')
);
COMMENT ON TABLE discovery_proposal_observation IS
    'DR-A5 B-prime (G2-1): append-only sightings of a proposal on an observed page. An '
    'unchanged re-observation adds a row here and never a new proposal.';
CREATE INDEX IF NOT EXISTS idx_proposal_observation_page ON discovery_proposal_observation (fetched_page_id);
CREATE INDEX IF NOT EXISTS idx_proposal_observation_run ON discovery_proposal_observation (crawl_run_id);

CREATE TABLE IF NOT EXISTS discovery_proposal_decision (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_seq     BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    proposal_id      UUID NOT NULL REFERENCES discovery_claim_proposal(id) ON DELETE RESTRICT,
    decision         proposal_decision_kind NOT NULL,
    decided_by       TEXT NOT NULL,
    rationale        TEXT NOT NULL,
    -- The human's explicit answer to each review question (DR-A5 section 13).
    resolved_choices JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_proposal_decision_attributed CHECK (btrim(decided_by) <> ''),
    CONSTRAINT ck_proposal_decision_reasoned CHECK (btrim(rationale) <> ''),
    CONSTRAINT ck_proposal_decision_choices CHECK (jsonb_typeof(resolved_choices) = 'object')
);
COMMENT ON TABLE discovery_proposal_decision IS
    'DR-A5 B-prime (G2-1): append-only human decisions on a proposal. Newest decision_seq is '
    'effective; a reversal is a new row. G2-1 creates no accepted claim from any decision.';
CREATE INDEX IF NOT EXISTS idx_proposal_decision_proposal
    ON discovery_proposal_decision (proposal_id, decision_seq DESC);

CREATE OR REPLACE FUNCTION refuse_claim_proposal_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        '% is append-only (DR-A5 B-prime): % refused. Record a NEW row instead.',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END$$;
COMMENT ON FUNCTION refuse_claim_proposal_mutation() IS
    'DR-A5 G2-1: refuses UPDATE/DELETE on the proposal, observation and decision tables.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_claim_proposal_no_update'
                   AND tgrelid = 'humanoid.discovery_claim_proposal'::regclass) THEN
        CREATE TRIGGER trg_claim_proposal_no_update
            BEFORE UPDATE ON discovery_claim_proposal FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_claim_proposal_no_delete'
                   AND tgrelid = 'humanoid.discovery_claim_proposal'::regclass) THEN
        CREATE TRIGGER trg_claim_proposal_no_delete
            BEFORE DELETE ON discovery_claim_proposal FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_proposal_observation_no_update'
                   AND tgrelid = 'humanoid.discovery_proposal_observation'::regclass) THEN
        CREATE TRIGGER trg_proposal_observation_no_update
            BEFORE UPDATE ON discovery_proposal_observation FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_proposal_observation_no_delete'
                   AND tgrelid = 'humanoid.discovery_proposal_observation'::regclass) THEN
        CREATE TRIGGER trg_proposal_observation_no_delete
            BEFORE DELETE ON discovery_proposal_observation FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_proposal_decision_no_update'
                   AND tgrelid = 'humanoid.discovery_proposal_decision'::regclass) THEN
        CREATE TRIGGER trg_proposal_decision_no_update
            BEFORE UPDATE ON discovery_proposal_decision FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_proposal_decision_no_delete'
                   AND tgrelid = 'humanoid.discovery_proposal_decision'::regclass) THEN
        CREATE TRIGGER trg_proposal_decision_no_delete
            BEFORE DELETE ON discovery_proposal_decision FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
END $$;
