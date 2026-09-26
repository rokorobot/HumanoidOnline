-- 0014_fetched_page_retrieval_provenance.sql
--
-- Discovery Stage B (bounded HTTP acquisition). Two provenance columns on
-- fetched_page, and nothing else:
--
--  1. final_url — where a bounded, policy-checked redirect chain ended. The
--     existing `url` column stays the REQUESTED url, so both are preserved.
--  2. retrieval_method — how the observation was retrieved. A one-value enum
--     ('HTTP_GET'): docs/16 §20 forbids browser/JavaScript execution in v0.1,
--     so another method must arrive as a visible schema change.
--
-- Additive and idempotent. Both columns are nullable with no default: rows
-- written before this migration keep their meaning, and NULL reads as "not
-- recorded", never as an invented value.
--
-- The schema is named explicitly (production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'retrieval_method' AND n.nspname = 'humanoid') THEN
        CREATE TYPE retrieval_method AS ENUM ('HTTP_GET');
    END IF;
END $$;

ALTER TABLE fetched_page ADD COLUMN IF NOT EXISTS final_url        TEXT;
ALTER TABLE fetched_page ADD COLUMN IF NOT EXISTS retrieval_method retrieval_method;

COMMENT ON COLUMN fetched_page.url IS
    'The REQUESTED url (operator-supplied, policy-checked).';
COMMENT ON COLUMN fetched_page.final_url IS
    'Where the bounded redirect chain ended; equals url when there was no redirect. '
    'NULL on rows written before migration 0014.';
COMMENT ON COLUMN fetched_page.retrieval_method IS
    'How the observation was retrieved. HTTP_GET only in v0.1 (docs/16 §20).';
