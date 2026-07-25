-- 0001_add_commercial_lead_message
--
-- Reconciles the frozen public API (`POST /api/commercial-leads` accepts
-- `{ "message": "..." }`, API contract §5) with the canonical database: the
-- buyer's free-text commercial inquiry had nowhere semantically correct to live
-- on `commercial_lead` (contact data, commercial context, snapshot, status and
-- `outcome` exist, but no inquiry/message field). This is reconciliation, not
-- feature expansion (WS7 contract §2).
--
-- `db/schema.sql` (baseline `0000_schema`) already carries this column, so on a
-- fresh database the baseline creates it and this migration is a no-op. On a
-- database created before WS7 the column is added here so the two converge —
-- hence `IF NOT EXISTS` (db/migrations/README.md: migrations must never drift
-- from schema.sql).

SET search_path TO humanoid, public;

ALTER TABLE commercial_lead ADD COLUMN IF NOT EXISTS message TEXT;
