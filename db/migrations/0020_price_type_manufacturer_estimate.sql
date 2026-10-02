-- 0020_price_type_manufacturer_estimate.sql
--
-- DR-A5 stage G2-4 (owner decision): a new canonical `price_type`,
-- `MANUFACTURER_ESTIMATE`: a numeric price estimate explicitly published by the robot
-- manufacturer itself. It is distinct from `ESTIMATED`, which keeps meaning
-- HumanoidOnline's own estimate; no existing value is changed.
--
-- This migration DECLARES the label and does nothing else. PostgreSQL permits
-- ALTER TYPE ... ADD VALUE inside a transaction, but the new label cannot be USED until
-- that transaction commits, and the bootstrap runs each migration file in its own
-- transaction (db/bootstrap.py::run_migrations, same as 0006/0007). The CHECK constraint
-- that accepts the new value therefore lives in 0021.
--
-- Placed AFTER 'ESTIMATED' so a migrated database has the identical enum order to one
-- created fresh from db/schema.sql. Additive and idempotent.

SET search_path TO humanoid, public;

ALTER TYPE price_type ADD VALUE IF NOT EXISTS 'MANUFACTURER_ESTIMATE' AFTER 'ESTIMATED';
