-- 0012_owner_approved_display_basis.sql
--
-- Additive, idempotent. MEDIA-01 (docs/09 §4) models three independent
-- dimensions — identity, rights evidence, display policy — and could express
-- exactly two display decisions: a real reuse licence on record
-- (rights PERMITTED/ATTRIBUTION_REQUIRED), or the ratified policy of showing
-- OFFICIAL manufacturer media whose licence is merely unknown.
--
-- Two facts about the Batch 01C imagery fit neither:
--
--  1. SOURCE. Some approved assets come from a DISTRIBUTOR (a reseller's own
--     product photography), not the manufacturer. Recording those as
--     OFFICIAL_MANUFACTURER_MEDIA would be false, and recording a licence in
--     rights_status would be worse: no source granted one.
--
--  2. IDENTITY. Some approved assets depict the product LINE rather than the
--     exact edition on the record (an H2 chassis standing in for H2 EDU, a T2
--     chassis for the Education and Professional packages). MEDIA-01's
--     identity_status is binary, so the only way to display them today would be
--     to write VERIFIED — asserting exact-edition verification that nobody
--     performed.
--
-- This migration adds the missing vocabulary so the decision can be recorded
-- truthfully instead of forced into a false value:
--
--   * image_usage_basis gains OWNER_APPROVED_DISPLAY — the platform owner
--     explicitly approved displaying this asset. It is a DISPLAY POLICY, and
--     it is emphatically NOT a licence: rights_status stays UNKNOWN, the
--     original source and attribution stay on the row, and a RESTRICTED rights
--     status still blocks display (enforced in the application gate, as the
--     existing policy basis already is).
--
--   * robot_image gains is_representative + representative_note — the asset
--     depicts the product line/chassis, not this exact edition, together with
--     the caption shown to readers. identity_status remains UNVERIFIED for such
--     a row, so identity uncertainty is preserved rather than papered over.
--
--   * robot_image gains display_approved_by + display_approved_at — who
--     approved the display decision and when, so the basis is attributable.
--
-- Nothing existing changes meaning: rows written before this migration keep
-- their usage_basis, and the eligibility rule for them is unchanged.

-- ADD VALUE cannot run inside a transaction block in older PostgreSQL, and is
-- idempotent with IF NOT EXISTS from PG 12 onward.
ALTER TYPE image_usage_basis ADD VALUE IF NOT EXISTS 'OWNER_APPROVED_DISPLAY';

ALTER TABLE robot_image
    ADD COLUMN IF NOT EXISTS is_representative    BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS representative_note  TEXT,
    ADD COLUMN IF NOT EXISTS display_approved_by  TEXT,
    ADD COLUMN IF NOT EXISTS display_approved_at  TIMESTAMPTZ;

COMMENT ON COLUMN robot_image.is_representative IS
    'TRUE when the asset depicts the product line/chassis rather than this exact '
    'edition. Such a row keeps identity_status = UNVERIFIED: it is displayed under '
    'an owner display approval WITH a caption, never by claiming exact-edition '
    'verification. representative_note carries the caption shown to readers.';
COMMENT ON COLUMN robot_image.representative_note IS
    'Reader-facing caption for a representative image, e.g. "H2 chassis shown; EDU '
    'package may vary." Required whenever is_representative is TRUE — an unlabelled '
    'stand-in is indistinguishable from a claim about the exact edition.';
COMMENT ON COLUMN robot_image.display_approved_by IS
    'Who approved displaying this asset when no reuse licence is on record '
    '(usage_basis = OWNER_APPROVED_DISPLAY). Attribution of the DECISION, not a '
    'grant of rights by the source.';
COMMENT ON COLUMN robot_image.display_approved_at IS
    'When the owner display approval was recorded.';
