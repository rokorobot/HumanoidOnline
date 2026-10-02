-- discovery_reviewer — the least-privilege database role for human claim-proposal
-- review (DR-A5 section 16, G2-1). Applied by the schema owner; idempotent.
--
-- The role itself is created with plain SQL (`CREATE ROLE discovery_reviewer LOGIN
-- PASSWORD ...`) by the owner, NOT through the Neon console/API (those roles join
-- `neon_superuser`, which would defeat this file). It is not created or used until a
-- later G2 phase adds the governed review commands.
--
-- What it can do: READ proposals, their sightings and the observation context, and
--   INSERT attributed human decisions (and read them back).
-- What it cannot do: write or change a proposal or a sighting, run observation, write
--   any catalogue table (robot, manufacturer, evidence_source, offers, ...), or any
--   DDL. UPDATE and DELETE of decisions are additionally refused by trigger.

SET search_path TO humanoid, public;

GRANT USAGE ON SCHEMA humanoid TO discovery_reviewer;

GRANT SELECT ON
    discovery_source, crawl_run, fetched_page,
    discovery_claim_proposal, discovery_proposal_observation, discovery_proposal_decision
TO discovery_reviewer;

GRANT INSERT ON discovery_proposal_decision TO discovery_reviewer;
