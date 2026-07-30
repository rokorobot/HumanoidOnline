"""PostgreSQL ENUM types, mirrored from db/schema.sql.

Each type already exists in the database (the schema owns it), so every ENUM is
declared with ``create_type=False``: the ORM never CREATEs or DROPs enum types.
Reuse these shared instances across model columns.
"""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM


def _pg_enum(name: str, *values: str) -> ENUM:
    return ENUM(*values, name=name, schema="humanoid", create_type=False)


region_type = _pg_enum(
    "region_type", "GLOBAL", "CONTINENT", "ECONOMIC_ZONE", "COUNTRY", "SUBREGION"
)
commercial_status = _pg_enum(
    "commercial_status",
    "ANNOUNCED", "DEVELOPMENT", "PROTOTYPE", "PILOT", "EARLY_ACCESS",
    "LIMITED_COMMERCIAL", "COMMERCIAL", "RAAS_DEPLOYMENT", "DISCONTINUED",
)
transaction_type = _pg_enum(
    "transaction_type",
    "PURCHASE", "RENTAL", "SUBSCRIPTION", "LEASE", "RAAS", "PILOT", "DEVELOPER", "OTHER",
)
price_type = _pg_enum(
    "price_type", "PUBLIC", "ESTIMATED", "QUOTE_ONLY", "FROM", "RANGE"
)
billing_period = _pg_enum(
    "billing_period",
    "ONE_TIME", "HOURLY", "DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "ANNUAL",
)
availability_status = _pg_enum(
    "availability_status",
    "NOT_AVAILABLE", "WAITLIST", "PREORDER", "LIMITED", "AVAILABLE",
    "ON_REQUEST", "DISCONTINUED",
)
provider_type = _pg_enum(
    "provider_type",
    "OEM", "DISTRIBUTOR", "INTEGRATOR", "RENTAL_PROVIDER", "LEASING_PROVIDER",
    "RAAS_PROVIDER", "SERVICE_PROVIDER",
)
mobility_type = _pg_enum(
    "mobility_type", "BIPEDAL", "WHEELED", "HYBRID", "QUADRUPED", "STATIONARY", "OTHER"
)
autonomy_level = _pg_enum(
    "autonomy_level",
    "TELEOPERATED", "ASSISTED", "SUPERVISED_AUTONOMY", "TASK_AUTONOMOUS",
    "HIGHLY_AUTONOMOUS",
)
capability_category = _pg_enum(
    "capability_category",
    "MANIPULATION", "MOBILITY", "PERCEPTION", "AI_AUTONOMY", "INTERACTION",
    "SOFTWARE", "SAFETY", "OTHER",
)
source_type = _pg_enum(
    "source_type",
    "MANUFACTURER_STORE", "MANUFACTURER_SITE", "PRESS_RELEASE", "NEWS_ARTICLE",
    "ANALYST_REPORT", "FINANCIAL_FILING", "DIRECT_QUOTE", "CONFERENCE",
    "INTERVIEW", "OTHER",
)
confidence_level = _pg_enum(
    "confidence_level", "LOW", "MEDIUM", "HIGH", "VERIFIED"
)
evidence_subject = _pg_enum(
    "evidence_subject",
    "MANUFACTURER", "ROBOT", "ROBOT_VARIANT", "SPECIFICATION", "CAPABILITY",
    "COMMERCIAL_STATUS", "PRICING_OFFER", "AVAILABILITY_OFFER", "DEPLOYMENT", "PROVIDER",
)
spec_value_type = _pg_enum(
    "spec_value_type", "NUMBER", "BOOLEAN", "TEXT", "ENUM"
)
# Decision-layer (Phase 2 / WS5 buyer intent).
transaction_preference = _pg_enum(
    "transaction_preference", "UNKNOWN", "RENT", "BUY", "LEASE", "RAAS", "FLEXIBLE"
)
buyer_type = _pg_enum(
    "buyer_type",
    "COMMERCIAL_BUYER", "TECHNICAL_EVALUATOR", "INDUSTRY_PARTICIPANT", "UNKNOWN",
)
# Verified product imagery (MEDIA-01). No 'GENERATED' identity-image source exists.
image_source_type = _pg_enum(
    "image_source_type",
    "MANUFACTURER", "PRESS_KIT", "DISTRIBUTOR", "EDITORIAL", "VIDEO_FRAME",
)
image_type = _pg_enum(
    "image_type",
    "FRONT", "SIDE", "REAR", "ACTION", "WORKPLACE", "DETAIL", "DIMENSIONS",
)
image_identity_status = _pg_enum("image_identity_status", "VERIFIED", "UNVERIFIED")
image_rights_status = _pg_enum(
    "image_rights_status",
    "PERMITTED", "ATTRIBUTION_REQUIRED", "UNKNOWN", "RESTRICTED",
)
image_usage_basis = _pg_enum(
    "image_usage_basis", "NONE", "OFFICIAL_MANUFACTURER_MEDIA"
)
match_category = _pg_enum(
    "match_category",
    "BEST_OVERALL", "BEST_COMMERCIAL", "BEST_LOWER_COST", "BEST_DEVELOPER",
    "BEST_TECHNICAL", "ALTERNATIVE",
)
# Transaction-layer (Phase 2 / WS7 commercial lead). Lifecycle is admin-only:
# the public capture path always writes 'NEW' and never transitions it.
lead_status = _pg_enum(
    "lead_status",
    "NEW", "QUALIFYING", "QUALIFIED", "MATCHED", "INTRODUCED", "IN_DISCUSSION",
    "WON", "LOST", "DISQUALIFIED",
)

# Discovery layer (DATA-D1 / docs/11_DATA_D1_CONTRACT.md). Noncanonical research
# queue — competitors are radar only; nothing here is a canonical fact until it
# passes the promotion gate (§7). Mirrors db/migrations/0003_add_discovery_layer.sql.
# DATA-D1.LIVE §4 widened this ADDITIVELY (migration 0004): every value DATA-D1
# shipped in 0003 is retained verbatim and four classes are appended. Source class
# predicts nothing about eligibility — an aggregator is reviewed exactly as a
# manufacturer is (§5).
discovery_source_class = _pg_enum(
    "discovery_source_class",
    "COMPETITOR_DIRECTORY", "MARKETPLACE", "EDITORIAL", "SEARCH_RESULT",
    "DISTRIBUTOR", "MANUFACTURER", "PRESS_RELEASE", "OFFICIAL_DOCUMENT",
    "OFFICIAL_VIDEO", "OTHER",
    "AGGREGATOR", "AUTHORIZED_DISTRIBUTOR", "OFFICIAL_STORE", "COMMUNITY",
)
# DATA-D1.9: affirmative access decisions (reviewing != being allowed).
tos_status = _pg_enum(
    "tos_status", "UNKNOWN", "ALLOWED", "RESTRICTED", "PROHIBITED"
)
robots_status = _pg_enum(
    "robots_status", "UNKNOWN", "ALLOWED", "DISALLOWED", "NOT_APPLICABLE"
)
candidate_entity_type = _pg_enum(
    "candidate_entity_type",
    "ROBOT", "MANUFACTURER", "VARIANT", "SPEC", "PRICING", "AVAILABILITY",
    "DEPLOYMENT", "IMAGE", "OTHER",
)
candidate_identity_status = _pg_enum(
    "candidate_identity_status",
    "UNRESOLVED", "MATCHED_EXISTING", "NEW_ENTITY", "AMBIGUOUS", "POSSIBLE_DUPLICATE",
)
candidate_status = _pg_enum(
    "candidate_status",
    "DISCOVERED", "IDENTITY_REVIEW", "SOURCE_TRACE", "VERIFICATION",
    "READY_FOR_PROMOTION", "PROMOTED", "POSSIBLE_DUPLICATE", "CONFLICT",
    "INSUFFICIENT_EVIDENCE", "REJECTED", "STALE", "RECHECK_REQUIRED",
)
trace_state = _pg_enum(
    "trace_state", "NOT_TRACED", "TRACE_CONFIRMED", "TRACE_PARTIAL", "TRACE_FAILED"
)
claim_status = _pg_enum(
    "claim_status", "NOT_VERIFIED", "VERIFIED", "CONFLICT", "REJECTED", "UNKNOWN"
)

# --- DATA-D1.LIVE (docs/16, RATIFIED v0.1) — live-acquisition types ----------
# Slice A is schema only: these exist so a run can be RECORDED. No adapter, HTTP
# client, robots fetcher or crawler exists in this slice.
crawl_run_status = _pg_enum(
    "crawl_run_status",
    "RUNNING", "COMPLETED", "FAILED", "HALTED_BY_POLICY", "CANCELLED",
)
# LIVE.4: exactly one legal trigger. A single value means adding an automated
# trigger is a visible schema change rather than a configuration flag.
crawl_trigger = _pg_enum("crawl_trigger", "MANUAL")
fetch_outcome = _pg_enum(
    "fetch_outcome",
    "FETCHED", "NOT_MODIFIED", "FROM_CACHE", "BLOCKED_BY_ROBOTS",
    "BLOCKED_BY_SOURCE", "ERROR", "SKIPPED_UNCHANGED",
)
extraction_method = _pg_enum(
    "extraction_method", "SELECTOR", "JSONLD", "MICRODATA", "PATTERN", "MANUAL"
)
# LIVE.8 / owner decision D-6: deliberately has NO VERIFIED value. How sure the
# parser is is not evidence quality, and a parser must not be able to express
# verification — that is a human act on claim_status.
extraction_confidence = _pg_enum("extraction_confidence", "LOW", "MEDIUM", "HIGH")
# LIVE.7: the three axes that must never collapse into one status label.
signal_axis = _pg_enum("signal_axis", "MATURITY", "OBTAINABILITY", "PRICE")
eligibility_decision = _pg_enum(
    "eligibility_decision", "ALLOWED", "RESTRICTED", "PROHIBITED", "UNKNOWN"
)
extraction_status = _pg_enum(
    "extraction_status", "EXTRACTED", "NOTHING_FOUND", "AMBIGUOUS", "ERROR"
)
evidence_subject_type = _pg_enum(
    "evidence_subject_type", "CLAIM", "COMMERCIAL_SIGNAL", "IMAGE_REF"
)

# Autonomy ordered low->high, for the `autonomy_min` catalogue filter.
AUTONOMY_ORDER = [
    "TELEOPERATED", "ASSISTED", "SUPERVISED_AUTONOMY", "TASK_AUTONOMOUS",
    "HIGHLY_AUTONOMOUS",
]
