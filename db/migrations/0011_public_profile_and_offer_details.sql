-- 0011_public_profile_and_offer_details.sql
--
-- Additive, idempotent. Two independent gaps, both of which forced supported
-- public facts to be dropped or flattened into prose:
--
--  1. OFFER DETAIL. A pricing_offer carried an amount but no way to say on what
--     basis it is quoted (VAT in or out), what ships with it, what the seller
--     warrants, whether it can be ordered right now, or whether the listed
--     edition has actually been matched to this record. Those are distinct
--     facts about distinct things and are therefore distinct columns, not one
--     free-text caveat: a reader filtering on "includes German VAT" must not
--     have to parse a paragraph. `edition_confirmed` is deliberately NULLABLE
--     with NO DEFAULT — see its comment.
--
--  2. PUBLIC PROFILE. `robot` had nowhere to keep the manufacturer's own
--     product page (the catalogue JSON carried `official_url`, and the importer
--     silently discarded it for want of a column) and nowhere to keep the
--     per-field caveats that explain why a spec is UNKNOWN or which sources
--     conflict. `specification` could hold long-tail specs but not say where a
--     value came from or which edition it describes, which made it unusable for
--     reseller-sourced or product-line-scoped facts.
--
-- `managed_by` on specification/spec_definition exists so a catalogue import can
-- refresh ONLY the rows it wrote. Seed rows and hand-authored rows are not the
-- importer's to rewrite, and a logical-key collision must preserve them rather
-- than win (db/import_catalogue.py reports such collisions).

ALTER TABLE robot
    ADD COLUMN IF NOT EXISTS official_url TEXT,
    ADD COLUMN IF NOT EXISTS spec_caveats JSONB;

COMMENT ON COLUMN robot.official_url IS
    'Manufacturer''s own product page for THIS model. Identity/provenance, not a '
    'commercial claim. Distinct from manufacturer.website_url (the company site).';
COMMENT ON COLUMN robot.spec_caveats IS
    'Per-field public caveats: [{"field":"degrees_of_freedom","text":"…"}]. Why a '
    'spec is UNKNOWN, or which sources conflict. Never a substitute for a value: a '
    'caveat explains a NULL, it never fills one.';

ALTER TABLE pricing_offer
    ADD COLUMN IF NOT EXISTS price_basis       TEXT,
    ADD COLUMN IF NOT EXISTS shipping_terms    TEXT,
    ADD COLUMN IF NOT EXISTS package_contents  TEXT,
    ADD COLUMN IF NOT EXISTS warranty_terms    TEXT,
    ADD COLUMN IF NOT EXISTS order_status_note TEXT,
    ADD COLUMN IF NOT EXISTS edition_confirmed BOOLEAN,
    ADD COLUMN IF NOT EXISTS edition_note      TEXT;

COMMENT ON COLUMN pricing_offer.price_basis IS
    'How this amount is quoted, in the seller''s own terms (e.g. "German supplier '
    'price · includes German VAT"). Never derived from the provider''s country: a '
    'seller''s location does not state its tax basis.';
COMMENT ON COLUMN pricing_offer.warranty_terms IS
    'Warranty as stated BY THIS SELLER. A manufacturer''s edition-level warranty is '
    'not a seller term and belongs on the robot (specification), not here.';
COMMENT ON COLUMN pricing_offer.edition_confirmed IS
    'Tri-state, and NULL is the default on purpose. NULL = not assessed (every '
    'pre-existing offer): treated exactly as before and never displayed as '
    'confirmed. TRUE = this listing was checked against the manufacturer''s '
    'specification for this record. FALSE = the listing''s own specification '
    'conflicts, so the offer is shown as a qualified listing and excluded from '
    'unqualified price selection (`edition_confirmed IS DISTINCT FROM FALSE`). '
    'Absence of assessment must never read as verification.';

ALTER TABLE availability_offer
    ADD COLUMN IF NOT EXISTS seller_wording          TEXT,
    ADD COLUMN IF NOT EXISTS delivery_estimate_label TEXT;

COMMENT ON COLUMN availability_offer.seller_wording IS
    'The seller''s availability sentence, verbatim. The enum is our normalization; '
    'this is what the seller actually said.';
COMMENT ON COLUMN availability_offer.delivery_estimate_label IS
    'Delivery estimate WITH its geographic scope stated (e.g. "Delivery estimate '
    'for Germany: 1-2 business days"). A seller''s domestic estimate is never '
    'presented as coverage of any other country.';

ALTER TABLE spec_definition
    ADD COLUMN IF NOT EXISTS managed_by TEXT;

ALTER TABLE specification
    ADD COLUMN IF NOT EXISTS managed_by    TEXT,
    ADD COLUMN IF NOT EXISTS source_label  TEXT,
    ADD COLUMN IF NOT EXISTS source_url    TEXT,
    ADD COLUMN IF NOT EXISTS source_kind   TEXT,
    ADD COLUMN IF NOT EXISTS edition_scope TEXT,
    ADD COLUMN IF NOT EXISTS observed_at   DATE;

COMMENT ON COLUMN specification.managed_by IS
    '''CATALOGUE_IMPORT'' for rows written by db/import_catalogue.py. NULL for seed '
    'or hand-authored rows, which the importer refreshes for no one: it deletes and '
    'upserts only its OWN rows and reports any logical-key collision instead of '
    'overwriting.';
COMMENT ON COLUMN specification.source_kind IS
    'Who stated this value: MANUFACTURER (the maker''s own page), MANUFACTURER_DOC '
    '(its manual/datasheet), COMPONENT_MANUFACTURER (a part maker, e.g. a hand '
    'vendor), or RESELLER_CLAIM (a distributor''s listing — a claim about the '
    'product, not the maker''s own statement).';
COMMENT ON COLUMN specification.edition_scope IS
    'What the value describes: THIS_EDITION, PRODUCT_LINE (stated for the family, '
    'not this configuration) or PLATFORM (vendor-wide). A line-level fact must '
    'never be rendered as edition-specific confirmation.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_specification_source_kind') THEN
        ALTER TABLE specification ADD CONSTRAINT chk_specification_source_kind CHECK (
            source_kind IS NULL OR source_kind IN (
                'MANUFACTURER', 'MANUFACTURER_DOC', 'COMPONENT_MANUFACTURER', 'RESELLER_CLAIM'
            )
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_specification_edition_scope') THEN
        ALTER TABLE specification ADD CONSTRAINT chk_specification_edition_scope CHECK (
            edition_scope IS NULL OR edition_scope IN ('THIS_EDITION', 'PRODUCT_LINE', 'PLATFORM')
        );
    END IF;
END
$$;
