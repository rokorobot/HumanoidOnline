-- A4 owner-authorized discovery sources. Internal business authorization is NOT
-- a publisher ToS permission verdict. This migration is additive and does NOT
-- enable sources, assign cadences or initiate fetching.
SET search_path TO humanoid, public;

ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS access_basis TEXT NOT NULL DEFAULT 'SOURCE_PERMISSION';
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS owner_authorized_by TEXT;
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS owner_authorized_at TIMESTAMPTZ;
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS owner_authorization_reason TEXT;
ALTER TABLE discovery_source ADD COLUMN IF NOT EXISTS owner_authorized_path_prefixes TEXT[];

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid
    JOIN pg_namespace n ON n.oid=r.relnamespace
    WHERE c.conname='ck_discovery_access_basis' AND n.nspname='humanoid'
  ) THEN
    ALTER TABLE discovery_source ADD CONSTRAINT ck_discovery_access_basis
      CHECK (access_basis IN ('SOURCE_PERMISSION', 'OWNER_AUTHORIZED'));
  END IF;
END $$;

ALTER TABLE discovery_source DROP CONSTRAINT IF EXISTS ck_discovery_source_eligible;
ALTER TABLE discovery_source ADD CONSTRAINT ck_discovery_source_eligible CHECK (
  NOT is_enabled OR (
    robots_status IN ('ALLOWED', 'NOT_APPLICABLE')
    AND eligibility_reviewed_at IS NOT NULL
    AND eligibility_reviewed_by IS NOT NULL
    AND (
      (access_basis='SOURCE_PERMISSION' AND tos_status='ALLOWED')
      OR (access_basis='OWNER_AUTHORIZED'
          AND tos_status NOT IN ('PROHIBITED', 'RESTRICTED')
          AND owner_authorized_by IS NOT NULL
          AND owner_authorized_at IS NOT NULL
          AND nullif(btrim(owner_authorization_reason), '') IS NOT NULL
          AND cardinality(owner_authorized_path_prefixes) > 0)
    )
  )
);

CREATE TABLE IF NOT EXISTS discovery_source_owner_authorization_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    action TEXT NOT NULL CHECK (action IN ('AUTHORIZE', 'REVOKE')),
    decided_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    approved_path_prefixes TEXT[] NOT NULL DEFAULT '{}',
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION refuse_source_owner_authorization_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
    RAISE EXCEPTION 'discovery_source_owner_authorization_event is append-only';
END $$;
DROP TRIGGER IF EXISTS trg_source_owner_authorization_no_update
    ON discovery_source_owner_authorization_event;
CREATE TRIGGER trg_source_owner_authorization_no_update
BEFORE UPDATE ON discovery_source_owner_authorization_event
FOR EACH ROW EXECUTE FUNCTION refuse_source_owner_authorization_mutation();
DROP TRIGGER IF EXISTS trg_source_owner_authorization_no_delete
    ON discovery_source_owner_authorization_event;
CREATE TRIGGER trg_source_owner_authorization_no_delete
BEFORE DELETE ON discovery_source_owner_authorization_event
FOR EACH ROW EXECUTE FUNCTION refuse_source_owner_authorization_mutation();
