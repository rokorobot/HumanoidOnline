-- PROPOSAL ONLY (owner decision D5, 2026-10-19): GitHub Actions is NOT authorized to write to
-- production. This file lives outside .github/workflows and db/roles so that nothing runs or
-- applies it. See ../PROMOTION_EXECUTOR_SECURITY_PROPOSAL_2026-10-19.md.
-- FUTURE PROPOSAL - NOT FOR THE PILOT. The pilot role is catalogue_promoter_routine
-- (catalogue_promoter_routine.sql): additions only, no UPDATE / DELETE / TRUNCATE. This broader
-- role (INSERT / UPDATE / DELETE on a robot's child rows) would only be needed for a promotion
-- lane that changes or removes facts, which does not exist and needs its own owner decision.
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
--   READ   the 39 non-lead tables of the schema (an explicit list, no blanket grant): the
--          pre/post verification gates (db/import_preflight.py, db/import_identity_check.py)
--          snapshot every table they are not told to exclude. OWNER DECISION: the lead tables
--          (commercial_lead, commercial_lead_robot, commercial_lead_provider,
--          buyer_requirement, match_result) are OUT OF SCOPE of this role: no SELECT and no
--          write privilege, so they cannot change through it. The executor passes them as the
--          explicit `exclude_tables` of the snapshot on BOTH sides of every comparison and
--          records them in the receipt; any other unreadable table fails the gate closed.
-- What it cannot do: DDL or migrations (it owns nothing; migrations stay with the owner
-- role), any write to the discovery, lead, claim, audit, source-registry or event tables,
-- TRUNCATE, or any privilege on sequences.

SET search_path TO humanoid, public;

GRANT USAGE ON SCHEMA humanoid TO catalogue_importer;

-- Verification snapshots and the importer's own reads (see the OWNER DECISION above).
GRANT SELECT ON
    region, manufacturer, provider, robot, robot_variant, robot_status_history,
    robot_image, spec_definition, specification, capability, robot_capability, use_case,
    use_case_fit, pricing_offer, availability_offer, deployment, evidence_source,
    event_log, discovery_source, discovery_source_owner_authorization_event,
    source_eligibility_review, crawl_run, fetched_page, discovery_candidate,
    candidate_claim, candidate_image_ref, extraction_result, candidate_commercial_signal,
    discovery_evidence_excerpt, promotion_audit, freshness_target, freshness_observation,
    candidate_identity_decision, discovery_claim_proposal, discovery_proposal_observation,
    discovery_proposal_decision, accepted_claim, claim_retraction, catalogue_write_audit,
    catalogue_freshness
TO catalogue_importer;

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
