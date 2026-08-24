-- 0010_add_freshness_layer
--
-- DATA-D1 Scheduled Freshness (docs/22_DATA_D1_SCHEDULED_FRESHNESS_
-- IMPLEMENTATION_CONTRACT.md, RATIFIED v0.1; amends docs/16 LIVE.4 per
-- docs/21_DATA_D1_LIVE_AMENDMENT_A2_SCHEDULED_FRESHNESS.md, RATIFIED v0.1).
-- FOUNDATION SLICE: this migration creates the freshness bookkeeping layer
-- only. It adds no adapter, no HTTP client, and no scheduler — nothing in
-- this repository can perform a fetch after applying it. AUTO_CHECK target
-- count is, and must remain, zero until a later, separately-gated slice
-- performs DATA-D1.9 eligibility reviews and registers targets.
--
-- STRUCTURALLY ISOLATED, exactly as 0003/0004 (§5 / DATA-D1.10 / Gate K /
-- docs/22 Phase 2): no canonical table is altered, and discovery_candidate
-- gains NO column — the observation -> candidate lineage FK lives entirely
-- on the new freshness_observation table, pointing TO discovery_candidate,
-- never the reverse. crawl_trigger is untouched (still exactly {'MANUAL'});
-- freshness_trigger is a dedicated, unrelated enum with no shared table or
-- FK to crawl_run (docs/22 Phase 4 — reusing crawl_trigger was considered
-- and rejected as the design that makes misuse easiest, not hardest).
--
-- Mirrors db/schema.sql SECTION 10. Guarded (pg_type / IF NOT EXISTS) so a
-- fresh database's baseline creates these objects and this migration is a
-- no-op, while a database at 0009 converges to the same shape.

SET search_path TO humanoid, public;

-- ---------------------------------------------------------------------------
-- 1. Enum types (docs/22 Phase 2 — all four new, none shared with any
--    existing type)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    -- Stored ONLY as freshness_observation.execution_mode_at_check, an
    -- immutable observation-time snapshot — never as a mutable column on
    -- freshness_target (docs/22 Phase 3.2, correction 3: effective mode must
    -- not be persisted as target truth, since it can go stale the moment an
    -- unrelated discovery_source review expires).
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'freshness_execution_mode' AND n.nspname = 'humanoid') THEN
        CREATE TYPE freshness_execution_mode AS ENUM (
            'AUTO_CHECK', 'MANUAL_CHECK', 'ELIGIBILITY_REVIEW_REQUIRED', 'INACTIVE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'freshness_result' AND n.nspname = 'humanoid') THEN
        CREATE TYPE freshness_result AS ENUM (
            'UNCHANGED', 'CHANGED', 'FETCH_ERROR', 'SOURCE_REMOVED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'freshness_fact_area' AND n.nspname = 'humanoid') THEN
        CREATE TYPE freshness_fact_area AS ENUM (
            'SPEC', 'PRICE', 'AVAILABILITY', 'COMMERCIAL_STATUS', 'DEPLOYMENT',
            'OFFICIAL_EVIDENCE', 'OTHER');
    END IF;
    -- docs/22 Phase 4: a DEDICATED enum, deliberately not an addition to
    -- crawl_trigger. crawl_trigger keeps its single ratified value ('MANUAL')
    -- and is not touched anywhere in this migration.
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'freshness_trigger' AND n.nspname = 'humanoid') THEN
        CREATE TYPE freshness_trigger AS ENUM ('MANUAL', 'SCHEDULED_FRESHNESS');
    END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 2. freshness_target (docs/22 Phase 2) — durable config only, no derived
--    eligibility verdict stored here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS freshness_target (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id                UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    discovery_source_id     UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    url                     TEXT NOT NULL,
    purpose                 freshness_fact_area NOT NULL,
    manual_override         BOOLEAN NOT NULL DEFAULT FALSE,
    interval_days           INTEGER NOT NULL DEFAULT 7,
    active                  BOOLEAN NOT NULL DEFAULT TRUE,
    last_checked_at         TIMESTAMPTZ,
    last_result             freshness_result,
    etag                    TEXT,
    last_modified           TEXT,
    content_fingerprint     TEXT,
    last_change_detected_at TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_freshness_target_interval CHECK (interval_days >= 7),
    CONSTRAINT uq_freshness_target_robot_url UNIQUE (robot_id, url)
);
COMMENT ON TABLE freshness_target IS
    'DATA-D1 Scheduled Freshness (docs/22). Durable config only (active, manual_override, '
    'purpose, interval_days) -- NO execution_mode column: effective mode is computed fresh at '
    'runtime (compute_execution_mode), never persisted here, so it cannot go stale.';

-- ---------------------------------------------------------------------------
-- 3. freshness_observation (docs/22 Phase 2) — append-only per-attempt log.
--    NO page body, ever (DATA-D1.10 minimal retention, applied here).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS freshness_observation (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    freshness_target_id     UUID NOT NULL REFERENCES freshness_target(id) ON DELETE CASCADE,
    trigger                 freshness_trigger NOT NULL,
    execution_mode_at_check freshness_execution_mode NOT NULL,
    result                  freshness_result NOT NULL,
    etag                    TEXT,
    last_modified           TEXT,
    content_fingerprint     TEXT,
    detected_change_type    freshness_fact_area,
    http_status             INTEGER,
    error_detail            TEXT,
    -- The explicit lineage FK (docs/22 Phase 2/6, correction 2). Points TO
    -- discovery_candidate; discovery_candidate itself gains no column. NULL
    -- on every UNCHANGED/FETCH_ERROR observation by construction -- those
    -- result paths never call the create-or-reuse function at all.
    discovery_candidate_id  UUID REFERENCES discovery_candidate(id) ON DELETE SET NULL,
    checked_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_freshness_observation_error_detail_len CHECK (
        error_detail IS NULL OR char_length(error_detail) <= 1000
    )
);
COMMENT ON TABLE freshness_observation IS
    'DATA-D1 Scheduled Freshness (docs/22). One row per check attempt, manual or scheduled. '
    'Append-only by convention (no UPDATE path in the service layer). discovery_candidate_id '
    'is the explicit observation->work lineage; NULL except on a CHANGED (or manual '
    'CHANGE_FOUND) result that created or reused governed DATA-D1 work.';

-- ---------------------------------------------------------------------------
-- 4. Indexes (docs/22 Phase 2 / Phase 11)
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_freshness_target_due
    ON freshness_target (active, last_checked_at);
CREATE INDEX IF NOT EXISTS idx_freshness_observation_target
    ON freshness_observation (freshness_target_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_freshness_observation_candidate
    ON freshness_observation (discovery_candidate_id)
    WHERE discovery_candidate_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5. updated_at maintenance for freshness_target (freshness_observation is
--    append-only and carries no updated_at column).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_freshness_target_updated') THEN
        CREATE TRIGGER trg_freshness_target_updated
            BEFORE UPDATE ON freshness_target
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
