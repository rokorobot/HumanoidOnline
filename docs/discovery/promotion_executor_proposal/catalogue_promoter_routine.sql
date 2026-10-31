-- PROPOSAL ONLY (owner decisions D5 and E3, 2026-10-19): nothing applies this file. It lives
-- outside .github/workflows and db/roles so that no workflow or migration runs it. See
-- ../PROMOTION_EXECUTOR_SECURITY_PROPOSAL_2026-10-19.md.
--
-- catalogue_promoter_routine - the database role for the INITIAL promotion executor (E3:
-- owner-controlled local execution). A ROUTINE promotion only ADDS: one `specification` row per
-- item (the importer keeps a long-tail spec's provenance inline, so no `evidence_source` row is
-- written for it today; INSERT on evidence_source is kept because the importer would write one
-- if the spec ever carried evidence, and an INSERT-only grant cannot change an existing row).
--
-- Provisioning is an OWNER action, with plain SQL, as the schema owner:
--
--     CREATE ROLE catalogue_promoter_routine LOGIN PASSWORD '<generated>';
--     \i catalogue_promoter_routine.sql
--
-- Do NOT create the role through the Neon console or API: roles created there join
-- `neon_superuser`, which would defeat this file. The executor refuses to run as a superuser, a
-- `neon_superuser` member, a table owner, or any role with UPDATE / DELETE / TRUNCATE on a
-- humanoid table (step `privileges`). The owner runs `promotion execute` with THIS role in
-- CATALOGUE_DATABASE_URL, never with neondb_owner.
--
-- What it can do:  READ the 39 non-lead tables of the schema (explicit list: the gates snapshot
--                  all of them) and INSERT into specification and evidence_source.
-- What it cannot:  UPDATE, DELETE, TRUNCATE anything; DDL; any privilege on the lead / buyer
--                  tables (commercial_lead, commercial_lead_robot, commercial_lead_provider,
--                  buyer_requirement, match_result) - out of scope of this role by owner
--                  decision, and it has no write privilege on them, so they cannot change
--                  through it; any sequence privilege; default privileges on future tables (a
--                  new table is invisible to the role until the owner adds it here, and the
--                  gates then fail closed).
--
-- The importer needs no UPDATE for a ROUTINE import: an unchanged row is detected with a SELECT
-- (db/import_catalogue.py `_upsert`) because INSERT ... ON CONFLICT DO UPDATE would demand the
-- UPDATE privilege even when it changes nothing.

SET search_path TO humanoid, public;

GRANT USAGE ON SCHEMA humanoid TO catalogue_promoter_routine;

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
    catalogue_freshness, product_line
TO catalogue_promoter_routine;

GRANT INSERT ON specification, evidence_source TO catalogue_promoter_routine;
