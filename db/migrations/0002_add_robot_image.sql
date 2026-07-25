-- 0002_add_robot_image
--
-- MEDIA-01 (docs/09_MEDIA_CONTRACT.md): the canonical verified-imagery entity
-- `robot_image`, plus its four enums. `robot.hero_image_url` stays dormant/
-- non-canonical (AGENTS.md rule 3) — not touched here.
--
-- `db/schema.sql` (baseline 0000_schema) already carries these objects, so on a
-- fresh database the baseline creates them and this migration is a no-op. On a
-- pre-MEDIA-01 database the objects are created here so the two converge — hence
-- the pg_type guards and CREATE TABLE/INDEX IF NOT EXISTS (migrations must never
-- drift from schema.sql; db/migrations/README.md).

SET search_path TO humanoid, public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'image_source_type' AND n.nspname = 'humanoid') THEN
        CREATE TYPE image_source_type AS ENUM (
            'MANUFACTURER', 'PRESS_KIT', 'DISTRIBUTOR', 'EDITORIAL', 'VIDEO_FRAME');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'image_type' AND n.nspname = 'humanoid') THEN
        CREATE TYPE image_type AS ENUM (
            'FRONT', 'SIDE', 'REAR', 'ACTION', 'WORKPLACE', 'DETAIL', 'DIMENSIONS');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'image_identity_status' AND n.nspname = 'humanoid') THEN
        CREATE TYPE image_identity_status AS ENUM ('VERIFIED', 'UNVERIFIED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'image_rights_status' AND n.nspname = 'humanoid') THEN
        CREATE TYPE image_rights_status AS ENUM (
            'PERMITTED', 'ATTRIBUTION_REQUIRED', 'UNKNOWN', 'RESTRICTED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'image_usage_basis' AND n.nspname = 'humanoid') THEN
        CREATE TYPE image_usage_basis AS ENUM ('NONE', 'OFFICIAL_MANUFACTURER_MEDIA');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS robot_image (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id        UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    image_url       TEXT NOT NULL,
    source_url      TEXT,
    source_name     TEXT,
    source_type     image_source_type NOT NULL,
    image_type      image_type NOT NULL DEFAULT 'FRONT',
    identity_status image_identity_status NOT NULL DEFAULT 'UNVERIFIED',
    rights_status   image_rights_status NOT NULL DEFAULT 'UNKNOWN',
    usage_basis     image_usage_basis NOT NULL DEFAULT 'NONE',
    is_official     BOOLEAN NOT NULL DEFAULT FALSE,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    attribution     TEXT,
    captured_at     DATE,
    last_verified_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_robot_image_primary ON robot_image (robot_id) WHERE is_primary;
CREATE INDEX IF NOT EXISTS idx_robot_image_robot ON robot_image (robot_id);
