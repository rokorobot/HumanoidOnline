-- 0003_add_discovery_layer
--
-- DATA-D1 (docs/11_DATA_D1_CONTRACT.md, RATIFIED v0.1): the competitive-discovery
-- layer. NONCANONICAL research work-queue — structurally separate from canonical
-- (§5 / DATA-D1.10 / Gate K). Canonical tables are NOT altered here and gain NO
-- foreign key to any discovery table; the only cross-references point FROM a
-- candidate TO canonical (`possible_*`/`promoted_robot_id`), never the reverse.
--
-- `db/schema.sql` (baseline 0000_schema) carries these same objects, so on a fresh
-- database the baseline creates them and this migration is a no-op; on a pre-DATA-D1
-- database the objects are created here so the two converge (pg_type guards +
-- CREATE ... IF NOT EXISTS; migrations must never drift from schema.sql).

SET search_path TO humanoid, public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'discovery_source_class' AND n.nspname = 'humanoid') THEN
        CREATE TYPE discovery_source_class AS ENUM (
            'COMPETITOR_DIRECTORY', 'MARKETPLACE', 'EDITORIAL', 'SEARCH_RESULT',
            'DISTRIBUTOR', 'MANUFACTURER', 'PRESS_RELEASE', 'OFFICIAL_DOCUMENT',
            'OFFICIAL_VIDEO', 'OTHER');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'candidate_entity_type' AND n.nspname = 'humanoid') THEN
        CREATE TYPE candidate_entity_type AS ENUM (
            'ROBOT', 'MANUFACTURER', 'VARIANT', 'SPEC', 'PRICING', 'AVAILABILITY',
            'DEPLOYMENT', 'IMAGE', 'OTHER');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'candidate_identity_status' AND n.nspname = 'humanoid') THEN
        CREATE TYPE candidate_identity_status AS ENUM (
            'UNRESOLVED', 'MATCHED_EXISTING', 'NEW_ENTITY', 'AMBIGUOUS', 'POSSIBLE_DUPLICATE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'candidate_status' AND n.nspname = 'humanoid') THEN
        CREATE TYPE candidate_status AS ENUM (
            'DISCOVERED', 'IDENTITY_REVIEW', 'SOURCE_TRACE', 'VERIFICATION',
            'READY_FOR_PROMOTION', 'PROMOTED', 'POSSIBLE_DUPLICATE', 'CONFLICT',
            'INSUFFICIENT_EVIDENCE', 'REJECTED', 'STALE', 'RECHECK_REQUIRED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'trace_state' AND n.nspname = 'humanoid') THEN
        CREATE TYPE trace_state AS ENUM (
            'NOT_TRACED', 'TRACE_CONFIRMED', 'TRACE_PARTIAL', 'TRACE_FAILED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'claim_status' AND n.nspname = 'humanoid') THEN
        CREATE TYPE claim_status AS ENUM (
            'NOT_VERIFIED', 'VERIFIED', 'CONFLICT', 'REJECTED', 'UNKNOWN');
    END IF;
END$$;

-- Radar registry. DATA-D1.9: a source is only crawler-eligible after its ToS +
-- robots/access policy have been reviewed. The CHECK encodes that gate in the
-- schema: is_enabled may not be true unless tos_reviewed AND robots_allowed.
CREATE TABLE IF NOT EXISTS discovery_source (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key             TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    source_class    discovery_source_class NOT NULL,
    homepage_url    TEXT,
    tos_reviewed    BOOLEAN NOT NULL DEFAULT FALSE,
    robots_allowed  BOOLEAN NOT NULL DEFAULT FALSE,
    is_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_discovery_source_eligible
        CHECK (NOT is_enabled OR (tos_reviewed AND robots_allowed))
);
COMMENT ON TABLE discovery_source IS
    'DATA-D1 radar registry. A source becomes a crawler target only after ToS/robots '
    'review (DATA-D1.9): is_enabled requires tos_reviewed AND robots_allowed.';

-- A discovered research candidate. `candidate_data` is MINIMAL by design
-- (DATA-D1.10): identity leads + the specific claimed values under investigation,
-- never a mirror of the competitor record/prose. possible_*_id point at canonical
-- for identity resolution; NO canonical table points back here (Gate K).
CREATE TABLE IF NOT EXISTS discovery_candidate (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id                 UUID NOT NULL REFERENCES discovery_source(id) ON DELETE CASCADE,
    entity_type               candidate_entity_type NOT NULL DEFAULT 'ROBOT',
    candidate_name            TEXT,
    candidate_manufacturer    TEXT,
    discovery_url             TEXT,
    external_ref              TEXT,
    candidate_data            JSONB,
    identity_status           candidate_identity_status NOT NULL DEFAULT 'UNRESOLVED',
    status                    candidate_status NOT NULL DEFAULT 'DISCOVERED',
    trace_state               trace_state NOT NULL DEFAULT 'NOT_TRACED',
    trace_url                 TEXT,
    possible_robot_id         UUID REFERENCES robot(id) ON DELETE SET NULL,
    possible_manufacturer_id  UUID REFERENCES manufacturer(id) ON DELETE SET NULL,
    promoted_robot_id         UUID REFERENCES robot(id) ON DELETE SET NULL,
    discovered_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_candidate_source_ref UNIQUE (source_id, external_ref)
);
COMMENT ON TABLE discovery_candidate IS
    'DATA-D1 noncanonical research candidate. Never public (§22/Gate I); never a '
    'canonical fact until it passes the promotion gate (§7). Minimal retention '
    '(DATA-D1.10): not a shadow copy of a competitor database.';

-- Per-field claims. Multiple rows for one (candidate, field_key) are KEPT (no
-- unique) so conflicting source values are preserved, never averaged (DATA-D1.8).
CREATE TABLE IF NOT EXISTS candidate_claim (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE CASCADE,
    field_key           TEXT NOT NULL,
    claimed_value       TEXT,
    unit                TEXT,
    claim_status        claim_status NOT NULL DEFAULT 'NOT_VERIFIED',
    discovery_source_id UUID REFERENCES discovery_source(id) ON DELETE SET NULL,
    evidence_url        TEXT,
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE candidate_claim IS
    'A single claimed field value under investigation. NULL claimed_value = UNKNOWN '
    '(never 0/false). Conflicting values are retained side-by-side (DATA-D1.8).';

-- Candidate imagery is REFERENCE-ONLY (R3): URL + metadata, never a stored binary.
-- There is deliberately no bytea/blob column. MEDIA-01 governs any eventual
-- promotion to robot_image (trace to OEM, verify identity/rights first).
CREATE TABLE IF NOT EXISTS candidate_image_ref (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE CASCADE,
    image_url           TEXT NOT NULL,
    discovery_source_id UUID REFERENCES discovery_source(id) ON DELETE SET NULL,
    credited_to         TEXT,
    media_status        TEXT NOT NULL DEFAULT 'CANDIDATE',
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE candidate_image_ref IS
    'DATA-D1 R3: reference-only candidate imagery (URL + metadata). No binary is '
    'cached. MEDIA-01/MEDIA-01.8 remain authoritative for any robot_image promotion.';

-- Promotion lineage (§19 / Gate J): reconstruct why a canonical fact entered.
CREATE TABLE IF NOT EXISTS promotion_audit (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE CASCADE,
    action              TEXT NOT NULL,
    promoted_entity_type candidate_entity_type,
    promoted_robot_id   UUID REFERENCES robot(id) ON DELETE SET NULL,
    evidence_source_id  UUID,   -- soft ref to evidence_source(id), mirrors that table's own soft-ref style
    approved_by         TEXT NOT NULL,
    detail              JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE promotion_audit IS
    'DATA-D1 §19/Gate J: append-only human-approval + promotion lineage '
    '(candidate -> evidence_source -> canonical robot).';

CREATE INDEX IF NOT EXISTS idx_candidate_source ON discovery_candidate (source_id);
CREATE INDEX IF NOT EXISTS idx_candidate_status ON discovery_candidate (status);
CREATE INDEX IF NOT EXISTS idx_candidate_possible_robot ON discovery_candidate (possible_robot_id);
CREATE INDEX IF NOT EXISTS idx_candidate_claim_candidate ON candidate_claim (candidate_id);
CREATE INDEX IF NOT EXISTS idx_candidate_image_candidate ON candidate_image_ref (candidate_id);
CREATE INDEX IF NOT EXISTS idx_promotion_audit_candidate ON promotion_audit (candidate_id);

-- updated_at maintenance triggers (set_updated_at() exists from the baseline).
-- Guarded so this is a no-op on a fresh DB where the baseline already created them.
DO $$
DECLARE t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY['discovery_source','discovery_candidate','candidate_claim'])
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_' || t || '_updated') THEN
            EXECUTE format(
                'CREATE TRIGGER trg_%1$s_updated BEFORE UPDATE ON %1$s
                 FOR EACH ROW EXECUTE FUNCTION set_updated_at();', t);
        END IF;
    END LOOP;
END$$;
