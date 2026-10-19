-- catalogue_importer - PROPOSED least-privilege database role for the approved catalogue
-- promotion workflow (docs/discovery/CATALOGUE_PROMOTION_AUTOMATION_DESIGN_2026-10-19.md,
-- section 5). THIS FILE IS A PROPOSAL: nothing applies it, and nothing in the repository
-- depends on it existing until the owner provisions it and sets the environment secret.
--
-- Provisioning is an OWNER action, with plain SQL, the same way as discovery_observer:
--
--     CREATE ROLE catalogue_importer LOGIN PASSWORD '<generated>';   -- as the schema owner
--     \i db/roles/catalogue_importer.sql
--
-- Do NOT create the role through the Neon console or API: roles created there join
-- `neon_superuser`, which would defeat this file. The password lives only in the GitHub
-- environment `catalogue-production`, as part of the secret CATALOGUE_DATABASE_URL.
--
-- What it can do is exactly what `db/import_catalogue.py --only <robots>` does (one
-- transaction, reconciling the selected robots' rows by natural key, no --authorize):
--   WRITE  the catalogue tables the importer writes. A robot's child rows may be inserted,
--          updated and deleted (the importer's own reconcile; it refuses deletions unless
--          authorised, which the promotion workflow never passes). Shared entities (regions,
--          manufacturers, providers, capabilities, use cases, spec definitions, robots) get
--          INSERT and UPDATE only, never DELETE.
--   READ   the schema, because the pre/post verification gates (db/import_preflight.py and
--          db/import_identity_check.py) snapshot every table. OWNER DECISION: that includes
--          the lead tables, which those tools reduce to a content hash in memory and never
--          print or store. If that is unacceptable, revoke SELECT on commercial_lead,
--          commercial_lead_robot, commercial_lead_provider, buyer_requirement and
--          match_result; the post-verification step then fails closed (an incident), and the
--          snapshot would have to be taken with a separate read-only credential.
-- What it cannot do: DDL or migrations (it owns nothing; migrations stay with the owner
-- role), any write to the discovery, lead, claim, audit, source-registry or event tables,
-- TRUNCATE, or any privilege on sequences.

SET search_path TO humanoid, public;

GRANT USAGE ON SCHEMA humanoid TO catalogue_importer;

-- Verification snapshots and the importer's own reads (see the OWNER DECISION above).
GRANT SELECT ON ALL TABLES IN SCHEMA humanoid TO catalogue_importer;

-- Shared entities: reconciled by natural key, never deleted by the importer.
GRANT INSERT, UPDATE ON
    region, manufacturer, provider, capability, use_case, spec_definition, robot
TO catalogue_importer;

-- A robot's child rows and their evidence.
GRANT INSERT, UPDATE, DELETE ON
    robot_variant, specification, pricing_offer, availability_offer, deployment,
    robot_image, robot_capability, use_case_fit, evidence_source
TO catalogue_importer;

-- Intentionally NOT granted: default privileges on future tables (a new table is invisible
-- to this role until the owner adds it here), and any write on discovery_*, candidate_*,
-- crawl_run, fetched_page, commercial_lead*, buyer_requirement, match_result, event_log,
-- accepted_claim, claim_retraction, catalogue_write_audit, promotion_audit.
