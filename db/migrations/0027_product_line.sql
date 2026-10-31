-- 0027_product_line.sql
--
-- Owner-approved (DR-L1, 2026-10-31): governed product-line membership.
--  1. `product_line` (slug, manufacturer, name, source_url, observed_at, is_published): the
--     editions a manufacturer presents together. Holds no price, availability or spec.
--  2. `robot.product_line_id` (nullable FK, ON DELETE SET NULL). A robot's line must share its
--     manufacturer; the catalogue importer enforces this.
--
-- Additive and idempotent. No existing row changes. The schema is named explicitly
-- (production role is not `humanoid`; see 0013).

SET search_path TO humanoid, public;

CREATE TABLE IF NOT EXISTS product_line (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug             TEXT NOT NULL UNIQUE,
    manufacturer_id  UUID NOT NULL REFERENCES manufacturer(id) ON DELETE RESTRICT,
    name             TEXT NOT NULL,
    source_url       TEXT NOT NULL CHECK (btrim(source_url) <> ''),
    observed_at      DATE NOT NULL,
    is_published     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE product_line IS
    'Editions of one product presented together by the manufacturer (DR-L1). Membership is '
    'robot.product_line_id; the line stores no price, availability or spec.';

DROP TRIGGER IF EXISTS trg_product_line_updated ON product_line;
CREATE TRIGGER trg_product_line_updated BEFORE UPDATE ON product_line
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE robot
    ADD COLUMN IF NOT EXISTS product_line_id UUID REFERENCES product_line(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_robot_product_line
    ON robot (product_line_id) WHERE product_line_id IS NOT NULL;
