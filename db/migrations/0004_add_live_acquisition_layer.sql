-- 0004_add_live_acquisition_layer
--
-- DATA-D1.LIVE (docs/16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md, RATIFIED
-- v0.1, main @ 6875a34). SLICE A IS SCHEMA ONLY: this migration creates the
-- records an acquisition run would write. It adds no adapter, no HTTP client, no
-- robots fetcher and no crawler, and nothing in this repository can perform a
-- fetch after applying it.
--
-- STRUCTURALLY SEPARATE from canonical, exactly as 0003 (§5 / DATA-D1.10 /
-- Gate K): no canonical table is altered and none gains a foreign key to an
-- acquisition table. Cross-references point FROM the discovery layer TO
-- canonical, never the reverse.
--
-- Mirrors db/schema.sql SECTION 10. Guarded (pg_type / IF NOT EXISTS / pg_attribute)
-- so a fresh database's baseline creates these objects and this migration is a
-- no-op, while a database at 0003 converges to the same shape.

SET search_path TO humanoid, public;

-- ---------------------------------------------------------------------------
-- 1. Enum types
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'crawl_run_status' AND n.nspname = 'humanoid') THEN
        CREATE TYPE crawl_run_status AS ENUM (
            'RUNNING', 'COMPLETED', 'FAILED', 'HALTED_BY_POLICY', 'CANCELLED');
    END IF;
    -- LIVE.4: exactly one legal trigger in v0.1. One value means adding an
    -- automated trigger is a visible schema change, not a configuration flag.
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'crawl_trigger' AND n.nspname = 'humanoid') THEN
        CREATE TYPE crawl_trigger AS ENUM ('MANUAL');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'fetch_outcome' AND n.nspname = 'humanoid') THEN
        CREATE TYPE fetch_outcome AS ENUM (
            'FETCHED', 'NOT_MODIFIED', 'FROM_CACHE', 'BLOCKED_BY_ROBOTS',
            'BLOCKED_BY_SOURCE', 'ERROR', 'SKIPPED_UNCHANGED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'extraction_method' AND n.nspname = 'humanoid') THEN
        CREATE TYPE extraction_method AS ENUM (
            'SELECTOR', 'JSONLD', 'MICRODATA', 'PATTERN', 'MANUAL');
    END IF;
    -- LIVE.8 / D-6: no VERIFIED value exists, so a parser cannot express
    -- verification. That is a human act on claim_status.
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'extraction_confidence' AND n.nspname = 'humanoid') THEN
        CREATE TYPE extraction_confidence AS ENUM ('LOW', 'MEDIUM', 'HIGH');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'signal_axis' AND n.nspname = 'humanoid') THEN
        CREATE TYPE signal_axis AS ENUM ('MATURITY', 'OBTAINABILITY', 'PRICE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'eligibility_decision' AND n.nspname = 'humanoid') THEN
        CREATE TYPE eligibility_decision AS ENUM (
            'ALLOWED', 'RESTRICTED', 'PROHIBITED', 'UNKNOWN');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'extraction_status' AND n.nspname = 'humanoid') THEN
        CREATE TYPE extraction_status AS ENUM (
            'EXTRACTED', 'NOTHING_FOUND', 'AMBIGUOUS', 'ERROR');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'evidence_subject_type' AND n.nspname = 'humanoid') THEN
        CREATE TYPE evidence_subject_type AS ENUM (
            'CLAIM', 'COMMERCIAL_SIGNAL', 'IMAGE_REF');
    END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 2. ADDITIVE widening of discovery_source_class (DATA-D1.LIVE §4)
--
-- ADD VALUE IF NOT EXISTS only. Every value shipped by 0003 is retained verbatim
-- — no rename, no removal, no re-mapping of existing rows — so a database
-- already carrying MANUFACTURER/EDITORIAL/... rows is unaffected. This is an
-- additive change to a NONCANONICAL discovery-layer type, not a canonical
-- schema change.
-- ---------------------------------------------------------------------------
ALTER TYPE discovery_source_class ADD VALUE IF NOT EXISTS 'AGGREGATOR';
ALTER TYPE discovery_source_class ADD VALUE IF NOT EXISTS 'AUTHORIZED_DISTRIBUTOR';
ALTER TYPE discovery_source_class ADD VALUE IF NOT EXISTS 'OFFICIAL_STORE';
ALTER TYPE discovery_source_class ADD VALUE IF NOT EXISTS 'COMMUNITY';

-- ---------------------------------------------------------------------------
-- 3. discovery_source — eligibility validity columns (§5 / LIVE.2 / D-2)
-- ---------------------------------------------------------------------------
ALTER TABLE discovery_source
    ADD COLUMN IF NOT EXISTS allowed_path_prefixes  TEXT[],
    ADD COLUMN IF NOT EXISTS tos_reviewed_at        TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS tos_expires_at         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS tos_page_hash          TEXT,
    ADD COLUMN IF NOT EXISTS last_robots_hash       TEXT,
    ADD COLUMN IF NOT EXISTS last_robots_checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_crawled_at        TIMESTAMPTZ;

-- ---------------------------------------------------------------------------
-- 4. source_eligibility_review — APPEND-ONLY (§5)
--
-- ON DELETE RESTRICT on source_id: an eligibility decision is the artefact that
-- authorizes contacting a third party, so it must outlive attempts to tidy up
-- the source row. Append-only is additionally enforced at ORM level
-- (app/models/acquisition.py), the same pattern as promotion_audit.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source_eligibility_review (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    robots_url          TEXT,
    robots_decision     robots_status NOT NULL DEFAULT 'UNKNOWN',
    robots_page_hash    TEXT,
    robots_excerpt      TEXT,
    tos_url             TEXT,
    tos_decision        eligibility_decision NOT NULL DEFAULT 'UNKNOWN',
    tos_page_hash       TEXT,
    tos_excerpt         TEXT,
    path_prefixes       TEXT[],
    reviewed_by         TEXT NOT NULL,
    reviewed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ,
    recommendation      eligibility_decision NOT NULL DEFAULT 'UNKNOWN',
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_source_eligibility_review_excerpt_len CHECK (
        (robots_excerpt IS NULL OR char_length(robots_excerpt) <= 1000)
        AND (tos_excerpt IS NULL OR char_length(tos_excerpt) <= 1000)
    )
);

-- ---------------------------------------------------------------------------
-- 5. crawl_run (§7)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crawl_run (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id         UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    adapter_key       TEXT NOT NULL,
    adapter_version   TEXT NOT NULL,
    trigger           crawl_trigger NOT NULL DEFAULT 'MANUAL',
    operator          TEXT NOT NULL,
    status            crawl_run_status NOT NULL DEFAULT 'RUNNING',
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    resume_of_run_id  UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    run_manifest      JSONB,
    counters          JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_crawl_run_finished CHECK (
        (status = 'RUNNING' AND finished_at IS NULL)
        OR (status <> 'RUNNING' AND finished_at IS NOT NULL)
    ),
    CONSTRAINT ck_crawl_run_not_self_resume CHECK (resume_of_run_id IS DISTINCT FROM id)
);

-- ---------------------------------------------------------------------------
-- 6. fetched_page (§8) — NO body column (LIVE.10)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fetched_page (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crawl_run_id             UUID NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    source_id                UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    url                      TEXT NOT NULL,
    canonical_url            TEXT,
    http_status              INTEGER,
    content_type             TEXT,
    content_length           BIGINT,
    content_hash             TEXT,
    etag                     TEXT,
    last_modified            TEXT,
    retrieved_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome                  fetch_outcome NOT NULL,
    robots_decision_at_fetch robots_status,
    error_class              TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 7. extraction_result (§9)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extraction_result (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crawl_run_id      UUID NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    fetched_page_id   UUID NOT NULL REFERENCES fetched_page(id) ON DELETE CASCADE,
    candidate_id      UUID REFERENCES discovery_candidate(id) ON DELETE SET NULL,
    extractor_key     TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    entity_type       candidate_entity_type NOT NULL DEFAULT 'ROBOT',
    status            extraction_status NOT NULL,
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 8. candidate_commercial_signal (§9 / LIVE.7)
--
-- The axis CHECK is the "three axes never merge" law expressed structurally: a
-- MATURITY signal physically cannot write availability, and vice versa.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidate_commercial_signal (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id          UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE CASCADE,
    discovery_source_id   UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    crawl_run_id          UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    fetched_page_id       UUID REFERENCES fetched_page(id) ON DELETE SET NULL,
    axis                  signal_axis NOT NULL,
    maturity_value        commercial_status,
    availability_value    availability_status,
    transaction_type      transaction_type,
    region_code           TEXT,
    buyer_type            buyer_type,
    price_type            price_type,
    price_amount          NUMERIC(14, 2),
    price_currency        CHAR(3),
    billing_period        billing_period,
    extractor_key         TEXT,
    extractor_version     TEXT,
    extraction_method     extraction_method,
    extraction_confidence extraction_confidence,
    claim_status          claim_status NOT NULL DEFAULT 'NOT_VERIFIED',
    note                  TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_commercial_signal_axis_value CHECK (
        (axis = 'MATURITY'      AND availability_value IS NULL AND price_type IS NULL)
     OR (axis = 'OBTAINABILITY' AND maturity_value     IS NULL AND price_type IS NULL)
     OR (axis = 'PRICE'         AND maturity_value     IS NULL AND availability_value IS NULL)
    ),
    CONSTRAINT ck_commercial_signal_price CHECK (
        price_amount IS NULL
        OR (price_currency IS NOT NULL AND price_type IS NOT NULL)
    )
);

-- ---------------------------------------------------------------------------
-- 9. discovery_evidence_excerpt (§9 / LIVE.6 / D-7)
--
-- char_length() counts CHARACTERS, not bytes — the ratified limit is 1000
-- Unicode characters, so a multi-byte excerpt is not silently truncated to a
-- smaller effective allowance.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS discovery_evidence_excerpt (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type    evidence_subject_type NOT NULL,
    subject_id      UUID NOT NULL,
    crawl_run_id    UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    fetched_page_id UUID REFERENCES fetched_page(id) ON DELETE SET NULL,
    excerpt_text    TEXT NOT NULL,
    page_url        TEXT NOT NULL,
    retrieved_at    TIMESTAMPTZ NOT NULL,
    page_hash       TEXT,
    locator         TEXT,
    ordinal         INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_evidence_excerpt_len CHECK (char_length(excerpt_text) <= 1000),
    CONSTRAINT ck_evidence_excerpt_not_blank CHECK (btrim(excerpt_text) <> ''),
    UNIQUE (subject_type, subject_id, ordinal)
);

-- ---------------------------------------------------------------------------
-- 10. candidate_claim / candidate_image_ref — additive provenance columns
--
-- Added AFTER crawl_run and fetched_page exist so the foreign keys resolve on an
-- upgrading database as well as a fresh one.
-- ---------------------------------------------------------------------------
ALTER TABLE candidate_claim
    ADD COLUMN IF NOT EXISTS extractor_key         TEXT,
    ADD COLUMN IF NOT EXISTS extractor_version     TEXT,
    ADD COLUMN IF NOT EXISTS extraction_method     extraction_method,
    ADD COLUMN IF NOT EXISTS extraction_confidence extraction_confidence,
    ADD COLUMN IF NOT EXISTS crawl_run_id          UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS fetched_page_id       UUID REFERENCES fetched_page(id) ON DELETE SET NULL;

ALTER TABLE candidate_image_ref
    ADD COLUMN IF NOT EXISTS page_url               TEXT,
    ADD COLUMN IF NOT EXISTS retrieved_at           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS declared_credit        TEXT,
    ADD COLUMN IF NOT EXISTS attribution_claimed    TEXT,
    ADD COLUMN IF NOT EXISTS alt_text               TEXT,
    ADD COLUMN IF NOT EXISTS retrieval_source_class discovery_source_class,
    ADD COLUMN IF NOT EXISTS crawl_run_id           UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS fetched_page_id        UUID REFERENCES fetched_page(id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- 11. Comments, indexes and the updated_at trigger
-- ---------------------------------------------------------------------------
COMMENT ON TABLE source_eligibility_review IS
    'DATA-D1.LIVE §5 append-only eligibility history (robots axis + terms axis, each with '
    'URL/hash/excerpt). Append-only: this record is what authorizes contacting a third party.';
COMMENT ON TABLE crawl_run IS
    'DATA-D1.LIVE §7 acquisition run. trigger is MANUAL-only in v0.1 (LIVE.4): no scheduler, '
    'queue or worker may start one. Slice A records runs; it cannot perform them.';
COMMENT ON TABLE fetched_page IS
    'DATA-D1.LIVE §8 per-URL fetch outcome. Deliberately has NO body column (LIVE.10): the '
    'evidence of what a page said is durable, the page itself is not.';
COMMENT ON TABLE extraction_result IS
    'DATA-D1.LIVE §9: one extractor pass over one page. AMBIGUOUS is a real outcome for a human, '
    'never a guess.';
COMMENT ON TABLE candidate_commercial_signal IS
    'DATA-D1.LIVE §9/LIVE.7: maturity, obtainability and price semantics as SEPARATE '
    'evidence-bound signals. A CHECK stops one axis writing another. Conflicts are separate rows.';
COMMENT ON TABLE discovery_evidence_excerpt IS
    'DATA-D1.LIVE §9/LIVE.6: exact supporting passages, <=1000 Unicode chars each, many per '
    'claim. A claim that cannot carry its supporting text is not recorded.';

CREATE INDEX IF NOT EXISTS idx_eligibility_review_source   ON source_eligibility_review (source_id, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_run_source            ON crawl_run (source_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_run_status            ON crawl_run (status);
CREATE INDEX IF NOT EXISTS idx_fetched_page_run            ON fetched_page (crawl_run_id);
CREATE INDEX IF NOT EXISTS idx_fetched_page_url            ON fetched_page (source_id, url);
CREATE INDEX IF NOT EXISTS idx_fetched_page_hash           ON fetched_page (content_hash);
CREATE INDEX IF NOT EXISTS idx_extraction_result_run       ON extraction_result (crawl_run_id);
CREATE INDEX IF NOT EXISTS idx_extraction_result_candidate ON extraction_result (candidate_id);
CREATE INDEX IF NOT EXISTS idx_commercial_signal_candidate ON candidate_commercial_signal (candidate_id);
CREATE INDEX IF NOT EXISTS idx_commercial_signal_source    ON candidate_commercial_signal (discovery_source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_excerpt_subject    ON discovery_evidence_excerpt (subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_candidate_claim_source      ON candidate_claim (discovery_source_id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_candidate_commercial_signal_updated') THEN
        CREATE TRIGGER trg_candidate_commercial_signal_updated
            BEFORE UPDATE ON candidate_commercial_signal
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
