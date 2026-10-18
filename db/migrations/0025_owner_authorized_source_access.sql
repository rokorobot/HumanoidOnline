-- 0025_owner_authorized_source_access.sql
--
-- docs/28 (DATA-D1.LIVE Amendment A4): a second, distinct access basis for
-- automated discovery acquisition, OWNER_AUTHORIZED, beside the existing
-- SOURCE_PERMISSION (an affirmative ToS-permits-automation decision).
--
--  1. discovery_source gains `access_basis` (default SOURCE_PERMISSION, which is
--     what every existing source keeps) and the owner-authorization projection
--     (`owner_authorized_by/_at`, `owner_authorization_reason`,
--     `owner_authorized_path_prefixes`), all set exactly when the basis is
--     OWNER_AUTHORIZED (ck_discovery_owner_authorization).
--  2. ck_discovery_source_eligible is replaced: an enabled source needs either
--     basis, and still a non-disallow robots decision and an attributed review.
--     OWNER_AUTHORIZED never applies over a recorded RESTRICTED/PROHIBITED.
--  3. discovery_source_owner_authorization_event: the append-only history of
--     owner AUTHORIZE / REVOKE decisions (UPDATE, DELETE and TRUNCATE refused).
--
-- Owner authorization is an internal business decision, NOT publisher consent:
-- nothing here reads or writes tos_status. Additive and idempotent. No existing
-- row changes meaning; applying this migration enables nothing, sets no cadence
-- and starts no crawling.
--
-- The schema is named explicitly (production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS access_basis TEXT NOT NULL
    DEFAULT 'SOURCE_PERMISSION';
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS owner_authorized_by TEXT;
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS owner_authorized_at TIMESTAMPTZ;
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS owner_authorization_reason TEXT;
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS owner_authorized_path_prefixes TEXT[];

-- Re-created on every run so a re-apply always converges on db/schema.sql.
ALTER TABLE discovery_source DROP CONSTRAINT IF EXISTS ck_discovery_access_basis;
ALTER TABLE discovery_source ADD CONSTRAINT ck_discovery_access_basis CHECK (
    access_basis IN ('SOURCE_PERMISSION', 'OWNER_AUTHORIZED')
);
ALTER TABLE discovery_source DROP CONSTRAINT IF EXISTS ck_discovery_owner_authorization;
ALTER TABLE discovery_source ADD CONSTRAINT ck_discovery_owner_authorization CHECK (
    (access_basis = 'SOURCE_PERMISSION'
     AND owner_authorized_by IS NULL AND owner_authorized_at IS NULL
     AND owner_authorization_reason IS NULL AND owner_authorized_path_prefixes IS NULL)
    OR (access_basis = 'OWNER_AUTHORIZED'
        AND coalesce(btrim(owner_authorized_by), '') <> ''
        AND owner_authorized_at IS NOT NULL
        AND coalesce(btrim(owner_authorization_reason), '') <> ''
        AND coalesce(cardinality(owner_authorized_path_prefixes), 0) > 0)
);
ALTER TABLE discovery_source DROP CONSTRAINT IF EXISTS ck_discovery_source_eligible;
ALTER TABLE discovery_source ADD CONSTRAINT ck_discovery_source_eligible CHECK (
    NOT is_enabled OR (
        robots_status IN ('ALLOWED', 'NOT_APPLICABLE')
        AND eligibility_reviewed_at IS NOT NULL
        AND eligibility_reviewed_by IS NOT NULL
        AND (
            (access_basis = 'SOURCE_PERMISSION' AND tos_status = 'ALLOWED')
            -- The owner's fields are guaranteed by ck_discovery_owner_authorization.
            OR (access_basis = 'OWNER_AUTHORIZED'
                AND tos_status NOT IN ('PROHIBITED', 'RESTRICTED'))
        )
    )
);
COMMENT ON TABLE discovery_source IS
    'DATA-D1 radar registry. is_enabled requires an access basis (affirmative ToS '
    'decision, or an attributed internal OWNER_AUTHORIZED decision that is not publisher '
    'consent; docs/28) + non-disallow robots decision + recorded review attribution (DATA-D1.9).';

CREATE TABLE IF NOT EXISTS discovery_source_owner_authorization_event (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id               UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    action                  TEXT NOT NULL,
    decided_by              TEXT NOT NULL,
    reason                  TEXT NOT NULL,
    approved_path_prefixes  TEXT[] NOT NULL DEFAULT '{}',
    decided_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_owner_authorization_event_action CHECK (action IN ('AUTHORIZE', 'REVOKE')),
    CONSTRAINT ck_owner_authorization_event_attributed CHECK (
        btrim(decided_by) <> '' AND btrim(reason) <> ''
    ),
    CONSTRAINT ck_owner_authorization_event_scope CHECK (
        action <> 'AUTHORIZE' OR cardinality(approved_path_prefixes) > 0
    )
);
CREATE INDEX IF NOT EXISTS idx_owner_authorization_event_source
    ON discovery_source_owner_authorization_event (source_id, decided_at DESC);

CREATE OR REPLACE FUNCTION refuse_source_owner_authorization_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'discovery_source_owner_authorization_event is append-only (docs/28)';
END $$;
CREATE OR REPLACE TRIGGER trg_source_owner_authorization_append_only
    BEFORE UPDATE OR DELETE ON discovery_source_owner_authorization_event
    FOR EACH ROW EXECUTE FUNCTION refuse_source_owner_authorization_mutation();
CREATE OR REPLACE TRIGGER trg_source_owner_authorization_no_truncate
    BEFORE TRUNCATE ON discovery_source_owner_authorization_event
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_source_owner_authorization_mutation();
