-- discovery_reviewer — the least-privilege database role for human claim-proposal
-- review (DR-A5 section 16, G2-1). Applied by the schema owner; idempotent.
--
-- The role itself is created with plain SQL (`CREATE ROLE discovery_reviewer LOGIN
-- PASSWORD ...`) by the owner, NOT through the Neon console/API (those roles join
-- `neon_superuser`, which would defeat this file). It is not created or used until a
-- later G2 phase adds the governed review commands (G2-2 applies it).
--
-- What it can do: READ proposals, their sightings, the observation context needed to
--   derive CURRENT / SUPERSEDED / STALE (sources, runs, fetched pages) and the robot row
--   the identity gate checks (read-only), and INSERT attributed human decisions.
-- What it cannot do: write or change a proposal or a sighting, run observation, write
--   any catalogue table (robot, manufacturer, evidence_source, offers, ...), or any
--   DDL. UPDATE and DELETE of decisions are additionally refused by trigger.

SET search_path TO humanoid, public;

GRANT USAGE ON SCHEMA humanoid TO discovery_reviewer;

GRANT SELECT ON
    robot, discovery_source, crawl_run, fetched_page,
    discovery_claim_proposal, discovery_proposal_observation, discovery_proposal_decision
TO discovery_reviewer;

GRANT INSERT ON discovery_proposal_decision TO discovery_reviewer;

-- G2-3 (migration 0019): the reviewer turns an effective ACCEPT into an immutable accepted
-- claim (and may append a retraction). It can read the claim tables and the audit, and it
-- can NEVER write the catalogue write audit (that is the verification command's record) or
-- any catalogue table; UPDATE and DELETE are refused by trigger for everyone.
GRANT SELECT ON accepted_claim, claim_retraction, catalogue_write_audit TO discovery_reviewer;
GRANT INSERT ON accepted_claim, claim_retraction TO discovery_reviewer;
