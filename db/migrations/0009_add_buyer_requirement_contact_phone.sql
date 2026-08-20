-- 0009_add_buyer_requirement_contact_phone
--
-- The Find a Humanoid questionnaire now collects buyer identity (full name,
-- organization, business email, optional telephone) on a final contact step
-- before submission — a product decision reversing WS5's original anonymous
-- intake. contact_name/contact_email/organization already had columns on
-- buyer_requirement (added for WS7's lead-capture denormalization); telephone
-- did not. Nullable and free-text on purpose, matching commercial_lead.
-- contact_phone exactly: telephone stays OPTIONAL, and international phone
-- numbers are not normalized or format-validated here or in the API schema.
--
-- Historical rows are untouched: contact_name/contact_email/organization stay
-- nullable too (this migration does not add any NOT NULL constraint), so every
-- anonymous requirement captured before this change remains a valid row.
-- "Required" is enforced only at the API layer for NEW submissions
-- (BuyerRequirementCreate), never by a DB constraint.
--
-- `db/schema.sql` (baseline `0000_schema`) already carries this column, so on a
-- fresh database the baseline creates it and this migration is a no-op. On a
-- database created before this change the column is added here so the two
-- converge — hence `IF NOT EXISTS` (db/migrations/README.md: migrations must
-- never drift from schema.sql).

SET search_path TO humanoid, public;

ALTER TABLE buyer_requirement ADD COLUMN IF NOT EXISTS contact_phone TEXT;
