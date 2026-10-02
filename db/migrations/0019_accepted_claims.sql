-- 0019_accepted_claims.sql
--
-- DR-A5 B-prime, stage G2-3 (owner-authorized): the accepted-claim layer. Three NEW
-- tables: `accepted_claim` (immutable), `claim_retraction` (append-only withdrawal or
-- correction) and `catalogue_write_audit` (append-only record that a catalogue row
-- exists because of an accepted claim), all protected by the existing
-- refuse_claim_proposal_mutation() trigger function (UPDATE and DELETE refused).
--
-- Additive and idempotent. No existing table, column, row or privilege is touched.
-- No foreign key to any canonical table (robots and variants are referenced by slug
-- text): the catalogue is written only through db/catalogue/ and the importer (M2).
--
-- The schema is named explicitly (the production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

CREATE TABLE IF NOT EXISTS accepted_claim (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_seq                BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    -- Content identity: sha256 over proposal digest, robot, variant, target and accepted
    -- value. Rebuilt identically from stored proposals and decisions (replay).
    claim_digest             TEXT NOT NULL,
    decision_id              UUID NOT NULL REFERENCES discovery_proposal_decision(id)
                                 ON DELETE RESTRICT,
    proposal_id              UUID NOT NULL REFERENCES discovery_claim_proposal(id)
                                 ON DELETE RESTRICT,
    proposal_digest          TEXT NOT NULL,
    -- The sighting that confirmed currentness when the claim was made.
    observation_id           UUID NOT NULL REFERENCES discovery_proposal_observation(id)
                                 ON DELETE RESTRICT,
    observation_content_hash TEXT NOT NULL,
    observed_at              TIMESTAMPTZ NOT NULL,
    source_id                UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    source_url               TEXT NOT NULL,
    -- Soft references by slug text, never foreign keys: the catalogue of record is
    -- db/catalogue/ (DR-A5 M2), and an FK action must never reach an immutable row.
    robot_slug               TEXT NOT NULL,
    variant_slug             TEXT,
    edition_label            TEXT,
    target_kind              TEXT NOT NULL,
    target_key               TEXT NOT NULL,
    value_type               TEXT NOT NULL,
    accepted_value           TEXT NOT NULL,
    edition_scope            TEXT,
    verbatim_value           TEXT NOT NULL,
    evidence_excerpt         TEXT NOT NULL,
    evidence_locator         TEXT NOT NULL,
    policy_key               TEXT NOT NULL,
    registry_version         TEXT NOT NULL,
    resolved_choices         JSONB NOT NULL,
    created_by               TEXT NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_accepted_claim_digest CHECK (claim_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_accepted_claim_target_kind
        CHECK (target_kind IN ('robot_variant', 'specification', 'NO_CATALOGUE_HOME')),
    CONSTRAINT ck_accepted_claim_value_type CHECK (value_type IN ('TEXT')),
    CONSTRAINT ck_accepted_claim_scope
        CHECK (edition_scope IS NULL
               OR edition_scope IN ('THIS_EDITION', 'PRODUCT_LINE', 'PLATFORM')),
    CONSTRAINT ck_accepted_claim_variant
        CHECK (target_kind <> 'robot_variant' OR variant_slug IS NOT NULL),
    CONSTRAINT ck_accepted_claim_choices CHECK (jsonb_typeof(resolved_choices) = 'object'),
    CONSTRAINT ck_accepted_claim_attributed CHECK (btrim(created_by) <> ''),
    CONSTRAINT ck_accepted_claim_robot CHECK (btrim(robot_slug) <> ''),
    CONSTRAINT ck_accepted_claim_value CHECK (btrim(accepted_value) <> '')
);
COMMENT ON TABLE accepted_claim IS
    'DR-A5 B-prime (G2-3): immutable accepted claim, created only from an effective ACCEPT on a '
    'CURRENT, non-stale proposal for a registered field policy. One per (decision, target). '
    'Nothing here is a catalogue fact until it is materialized through the catalogue of record.';
CREATE UNIQUE INDEX IF NOT EXISTS uq_accepted_claim_target ON accepted_claim
    (decision_id, target_kind, target_key, COALESCE(variant_slug, ''));
CREATE INDEX IF NOT EXISTS idx_accepted_claim_digest ON accepted_claim (claim_digest);
CREATE INDEX IF NOT EXISTS idx_accepted_claim_robot ON accepted_claim (robot_slug, claim_seq);
CREATE INDEX IF NOT EXISTS idx_accepted_claim_proposal ON accepted_claim (proposal_id);
CREATE INDEX IF NOT EXISTS idx_accepted_claim_observation ON accepted_claim (observation_id);
CREATE INDEX IF NOT EXISTS idx_accepted_claim_source ON accepted_claim (source_id);

CREATE TABLE IF NOT EXISTS claim_retraction (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    retraction_seq       BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    claim_id             UUID NOT NULL UNIQUE REFERENCES accepted_claim(id) ON DELETE RESTRICT,
    replacement_claim_id UUID REFERENCES accepted_claim(id) ON DELETE RESTRICT,
    retracted_by         TEXT NOT NULL,
    reason               TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_claim_retraction_attributed CHECK (btrim(retracted_by) <> ''),
    CONSTRAINT ck_claim_retraction_reasoned CHECK (btrim(reason) <> ''),
    CONSTRAINT ck_claim_retraction_not_self CHECK (replacement_claim_id IS DISTINCT FROM claim_id)
);
COMMENT ON TABLE claim_retraction IS
    'DR-A5 B-prime (G2-3): append-only withdrawal of an accepted claim, optionally naming the '
    'corrected claim that replaces it. An accepted claim is never edited. A catalogue correction '
    'is a new reviewed change.';
CREATE INDEX IF NOT EXISTS idx_claim_retraction_replacement ON claim_retraction (replacement_claim_id);

CREATE TABLE IF NOT EXISTS catalogue_write_audit (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_seq       BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    claim_id        UUID NOT NULL REFERENCES accepted_claim(id) ON DELETE RESTRICT,
    robot_slug      TEXT NOT NULL,
    method          TEXT NOT NULL,
    change_ref      TEXT NOT NULL,
    importer_run_ref TEXT,
    target_table    TEXT NOT NULL,
    target_row_id   UUID NOT NULL,
    before_hash     TEXT,
    after_hash      TEXT NOT NULL,
    applied_by      TEXT NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_catalogue_write_audit_method CHECK (method IN ('IMPORTER_M2')),
    CONSTRAINT ck_catalogue_write_audit_table
        CHECK (target_table IN ('robot_variant', 'specification')),
    CONSTRAINT ck_catalogue_write_audit_after CHECK (after_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_catalogue_write_audit_change CHECK (btrim(change_ref) <> ''),
    CONSTRAINT ck_catalogue_write_audit_attributed CHECK (btrim(applied_by) <> '')
);
COMMENT ON TABLE catalogue_write_audit IS
    'DR-A5 B-prime (G2-3): append-only record that a catalogue row exists because of an accepted '
    'claim (method IMPORTER_M2: written to db/catalogue/, merged by PR, loaded by the importer, '
    'then verified). The importer is the only writer of the catalogue; this table records, it '
    'never writes one.';
CREATE INDEX IF NOT EXISTS idx_catalogue_write_audit_claim ON catalogue_write_audit (claim_id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_accepted_claim_no_update'
                   AND tgrelid = 'humanoid.accepted_claim'::regclass) THEN
        CREATE TRIGGER trg_accepted_claim_no_update
            BEFORE UPDATE ON accepted_claim FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_accepted_claim_no_delete'
                   AND tgrelid = 'humanoid.accepted_claim'::regclass) THEN
        CREATE TRIGGER trg_accepted_claim_no_delete
            BEFORE DELETE ON accepted_claim FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_claim_retraction_no_update'
                   AND tgrelid = 'humanoid.claim_retraction'::regclass) THEN
        CREATE TRIGGER trg_claim_retraction_no_update
            BEFORE UPDATE ON claim_retraction FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_claim_retraction_no_delete'
                   AND tgrelid = 'humanoid.claim_retraction'::regclass) THEN
        CREATE TRIGGER trg_claim_retraction_no_delete
            BEFORE DELETE ON claim_retraction FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_catalogue_write_audit_no_update'
                   AND tgrelid = 'humanoid.catalogue_write_audit'::regclass) THEN
        CREATE TRIGGER trg_catalogue_write_audit_no_update
            BEFORE UPDATE ON catalogue_write_audit FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_catalogue_write_audit_no_delete'
                   AND tgrelid = 'humanoid.catalogue_write_audit'::regclass) THEN
        CREATE TRIGGER trg_catalogue_write_audit_no_delete
            BEFORE DELETE ON catalogue_write_audit FOR EACH STATEMENT
            EXECUTE FUNCTION refuse_claim_proposal_mutation();
    END IF;
END $$;
