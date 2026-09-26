-- discovery_observer — the least-privilege database role for Stage F scheduled
-- observation (docs/16 §17.2). Applied by the schema owner; idempotent.
--
-- The role itself is created with plain SQL (`CREATE ROLE discovery_observer
-- LOGIN PASSWORD ...`) by the owner, NOT through the Neon console/API: roles
-- created there join `neon_superuser`, which would defeat this file. Its
-- password lives only in the GitHub environment secret DISCOVERY_DATABASE_URL.
--
-- What it can do is exactly what one observation cycle does:
--   READ   the discovery layer, the Stage E decisions and audit (review queue),
--          and region/manufacturer/robot (the deterministic identity resolver
--          and the rows those models eagerly load);
--   WRITE  (INSERT/UPDATE, never DELETE) crawl runs, fetched pages, candidates,
--          claims, signals, image refs, evidence excerpts and extraction
--          results; on discovery_source only the run bookkeeping columns.
-- What it cannot do: DDL or migrations (it owns nothing; migrations stay with
-- the owner role), any canonical write (robot, manufacturer, evidence_source,
-- offers, ...), Stage E decisions, promotion, source approval or cadence
-- changes, or reading leads, buyer requirements or any other table.

SET search_path TO humanoid, public;

GRANT USAGE ON SCHEMA humanoid TO discovery_observer;

GRANT SELECT ON
    region, manufacturer, robot, robot_image,
    discovery_source, crawl_run, fetched_page, discovery_candidate, candidate_claim,
    candidate_image_ref, extraction_result, candidate_commercial_signal,
    discovery_evidence_excerpt, promotion_audit, candidate_identity_decision
TO discovery_observer;

GRANT INSERT, UPDATE ON
    crawl_run, fetched_page, discovery_candidate, candidate_claim, candidate_image_ref,
    extraction_result, candidate_commercial_signal, discovery_evidence_excerpt
TO discovery_observer;

-- Run bookkeeping only: robots hash/check time, last crawl, and the robots-
-- disallow auto-disable (docs/16 Gate B). Never approval, ToS, paths or cadence.
GRANT UPDATE (last_robots_hash, last_robots_checked_at, last_crawled_at, is_enabled)
    ON discovery_source TO discovery_observer;
