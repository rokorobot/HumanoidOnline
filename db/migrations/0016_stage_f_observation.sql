-- 0016_stage_f_observation.sql
--
-- Discovery Stage F1 (docs/16 §17.2): scheduled observation of already-approved
-- sources. Two additive changes, and nothing else:
--
--  1. crawl_trigger gains 'SCHEDULED'. LIVE.4 kept the enum at one value so that
--     an automated trigger would arrive as a visible schema change; this is that
--     change. A scheduled run still records an operator string naming who set
--     the source's cadence.
--  2. discovery_source gains an attributed observation cadence. NULL interval =
--     not scheduled, which is what every existing source gets: applying this
--     migration starts no crawling. The interval is whole hours, 6 h to 90 days.
--  3. A partial unique index: at most one RUNNING crawl_run per source, so a
--     manual run and a scheduled cycle can never crawl one source at once. The
--     second run is refused before any request. (A dead process's RUNNING run
--     is released by the existing governed `discovery run fail`.)
--
-- Additive and idempotent. No existing row changes meaning.
--
-- The schema is named explicitly (production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

ALTER TYPE crawl_trigger ADD VALUE IF NOT EXISTS 'SCHEDULED';

ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS observation_interval_hours INTEGER;
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS observation_cadence_set_by TEXT;
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS observation_cadence_set_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class r ON r.oid = c.conrelid
                   JOIN pg_namespace n ON n.oid = r.relnamespace
                   WHERE c.conname = 'ck_discovery_source_cadence' AND n.nspname = 'humanoid') THEN
        ALTER TABLE discovery_source ADD CONSTRAINT ck_discovery_source_cadence CHECK (
            observation_interval_hours IS NULL OR (
                observation_interval_hours BETWEEN 6 AND 2160
                AND observation_cadence_set_by IS NOT NULL
                AND btrim(observation_cadence_set_by) <> ''
                AND observation_cadence_set_at IS NOT NULL
            )
        );
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_crawl_run_one_running_per_source
    ON crawl_run (source_id) WHERE status = 'RUNNING';
