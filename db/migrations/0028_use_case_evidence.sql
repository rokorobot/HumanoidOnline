-- 0028_use_case_evidence.sql
--
-- DR-C2 (owner-approved 2026-11-02): use-case text (description,
-- typical_requirements, key_limitations) carries factual claims -- named
-- deployments, orders, published figures -- and AGENTS.md rule 7 requires
-- provenance. evidence_source had no use-case subject, so those sources had
-- nowhere to live.
--
-- Adds the evidence_subject label USE_CASE. Rows reuse the existing pattern:
-- subject_type = 'USE_CASE', subject_id = use_case.id, claim_fields naming the
-- use-case fields the source supports. No new table, no column change.
--
-- Additive and idempotent: no value is renamed or removed. The label is
-- appended last, matching the order in db/schema.sql. This migration only
-- DECLARES the label; PostgreSQL does not allow a new enum label to be used in
-- the transaction that adds it, and the bootstrap runs each migration file in
-- its own transaction, so nothing here inserts a USE_CASE row.

-- The schema is named explicitly (production role is not `humanoid`; see 0013).
SET search_path TO humanoid, public;

ALTER TYPE evidence_subject ADD VALUE IF NOT EXISTS 'USE_CASE';
