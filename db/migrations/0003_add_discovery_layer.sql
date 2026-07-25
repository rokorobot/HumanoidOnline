-- 0003_add_discovery_layer
--
-- DATA-D1 (docs/11_DATA_D1_CONTRACT.md, RATIFIED v0.1). Noncanonical
-- competitive-discovery research queue. STRUCTURALLY SEPARATE from canonical
-- (§5 / DATA-D1.10 / Gate K): no canonical table is altered and none gains a
-- foreign key to a discovery table. The only cross-references point FROM a
-- candidate TO canonical (possible_*/promoted_robot_id), never the reverse.
--
-- Mirrors db/schema.sql SECTION 10. Guarded (pg_type / IF NOT EXISTS) so a fresh
-- DB's baseline creates these objects and this migration is a no-op.

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
    -- DATA-D1.9: an AFFIRMATIVE decision that automated access is permitted — not
    -- merely that a review happened. PROHIBITED/RESTRICTED/UNKNOWN block enablement.
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'tos_status' AND n.nspname = 'humanoid') THEN
        CREATE TYPE tos_status AS ENUM ('UNKNOWN', 'ALLOWED', 'RESTRICTED', 'PROHIBITED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'robots_status' AND n.nspname = 'humanoid') THEN
        CREATE TYPE robots_status AS ENUM ('UNKNOWN', 'ALLOWED', 'DISALLOWED', 'NOT_APPLICABLE');
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

-- Radar registry. DATA-D1.9: is_enabled requires an AFFIRMATIVE ToS-permits-
-- automation decision, a robots decision that is not a disallow, and recorded
-- review attribution + time. Reviewing a source is NOT the same as being allowed.
CREATE TABLE IF NOT EXISTS discovery_source (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key                     TEXT NOT NULL UNIQUE,
    name                    TEXT NOT NULL,
    source_class            discovery_source_class NOT NULL,
    homepage_url            TEXT,
    tos_status              tos_status NOT NULL DEFAULT 'UNKNOWN',
    robots_status           robots_status NOT NULL DEFAULT 'UNKNOWN',
    eligibility_reviewed_at TIMESTAMPTZ,
    eligibility_reviewed_by TEXT,
    is_enabled              BOOLEAN NOT NULL DEFAULT FALSE,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_discovery_source_eligible CHECK (
        NOT is_enabled OR (
            tos_status = 'ALLOWED'
            AND robots_status IN ('ALLOWED', 'NOT_APPLICABLE')
            AND eligibility_reviewed_at IS NOT NULL
            AND eligibility_reviewed_by IS NOT NULL
        )
    )
);
COMMENT ON TABLE discovery_source IS
    'DATA-D1 radar registry. is_enabled requires an affirmative ToS-permits-automation '
    'decision + non-disallow robots decision + recorded review attribution (DATA-D1.9).';

CREATE TABLE IF NOT EXISTS discovery_candidate (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id                 UUID NOT NULL REFERENCES discovery_source(id) ON DELETE CASCADE,
    entity_type               candidate_entity_type NOT NULL DEFAULT 'ROBOT',
    candidate_name            TEXT,
    candidate_manufacturer    TEXT,
    discovery_url             TEXT,
    external_ref              TEXT NOT NULL,            -- required for dependable dedup
    candidate_data            JSONB,                   -- allowlisted leads only (DATA-D1.10)
    identity_status           candidate_identity_status NOT NULL DEFAULT 'UNRESOLVED',
    status                    candidate_status NOT NULL DEFAULT 'DISCOVERED',
    -- Trace = an EXPLICIT confirmation of an authoritative source, distinct from a
    -- discovered lead. A bare official-URL lead never sets these (DATA-D1.2/§9).
    trace_state               trace_state NOT NULL DEFAULT 'NOT_TRACED',
    trace_url                 TEXT,
    trace_source_type         source_type,
    trace_verified_by         TEXT,
    trace_verified_at         TIMESTAMPTZ,
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
    'DATA-D1 noncanonical research candidate. Never public (§22/Gate I); canonical '
    'only after the promotion gate (§7). Minimal retention (DATA-D1.10), not a shadow DB.';

CREATE TABLE IF NOT EXISTS candidate_claim (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE CASCADE,
    field_key           TEXT NOT NULL,
    claimed_value       TEXT,              -- NULL = UNKNOWN (never 0/false)
    unit                TEXT,
    claim_status        claim_status NOT NULL DEFAULT 'NOT_VERIFIED',
    discovery_source_id UUID REFERENCES discovery_source(id) ON DELETE SET NULL,
    evidence_url        TEXT,
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE candidate_claim IS
    'Per-field claims. Conflicting values are retained side-by-side, never averaged (DATA-D1.8).';

-- Reference-only candidate imagery (R3): http/https URL + metadata, NO binary.
CREATE TABLE IF NOT EXISTS candidate_image_ref (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE CASCADE,
    image_url           TEXT NOT NULL,
    discovery_source_id UUID REFERENCES discovery_source(id) ON DELETE SET NULL,
    credited_to         TEXT,
    media_status        TEXT NOT NULL DEFAULT 'CANDIDATE',
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_candidate_image_ref_scheme CHECK (image_url ~* '^https?://')
);
COMMENT ON TABLE candidate_image_ref IS
    'DATA-D1 R3: reference-only imagery (http/https URL + metadata, no binary). MEDIA-01 authoritative.';

-- Promotion lineage (§19 / Gate J). Durable: ON DELETE RESTRICT so a candidate
-- with promotion history cannot be deleted out from under the audit trail.
CREATE TABLE IF NOT EXISTS promotion_audit (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id         UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE RESTRICT,
    action               TEXT NOT NULL,
    promoted_entity_type candidate_entity_type,
    promoted_robot_id    UUID REFERENCES robot(id) ON DELETE SET NULL,
    evidence_source_id   UUID,   -- soft ref to evidence_source(id)
    approved_by          TEXT NOT NULL,
    detail               JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE promotion_audit IS
    'DATA-D1 §19/Gate J: human-approval + promotion lineage (candidate -> evidence -> robot). '
    'Append-only + delete-restricted so lineage survives.';

CREATE INDEX IF NOT EXISTS idx_candidate_source ON discovery_candidate (source_id);
CREATE INDEX IF NOT EXISTS idx_candidate_status ON discovery_candidate (status);
CREATE INDEX IF NOT EXISTS idx_candidate_possible_robot ON discovery_candidate (possible_robot_id);
CREATE INDEX IF NOT EXISTS idx_candidate_claim_candidate ON candidate_claim (candidate_id);
CREATE INDEX IF NOT EXISTS idx_candidate_image_candidate ON candidate_image_ref (candidate_id);
CREATE INDEX IF NOT EXISTS idx_promotion_audit_candidate ON promotion_audit (candidate_id);

-- updated_at maintenance triggers (set_updated_at() exists from the baseline).
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
