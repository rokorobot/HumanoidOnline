-- 0008_add_commercial_lead_contact_phone
--
-- Adds the optional telephone field to the WS7 contact-capture step (Find a
-- Humanoid). Full name/organization/email already had columns; phone did not.
-- Nullable and free-text on purpose: telephone stays OPTIONAL in the product
-- (unlike name/organization/email, which the API now requires for new
-- submissions at the application layer only), and international phone numbers
-- are not normalized or format-validated here or in the API schema, so a
-- NOT NULL/CHECK constraint would either reject valid input or fabricate a
-- format this project has no authority to impose.
--
-- `db/schema.sql` (baseline `0000_schema`) already carries this column, so on a
-- fresh database the baseline creates it and this migration is a no-op. On a
-- database created before this change the column is added here so the two
-- converge — hence `IF NOT EXISTS` (db/migrations/README.md: migrations must
-- never drift from schema.sql).

SET search_path TO humanoid, public;

ALTER TABLE commercial_lead ADD COLUMN IF NOT EXISTS contact_phone TEXT;
