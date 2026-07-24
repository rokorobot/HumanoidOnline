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

# Autonomy ordered low->high, for the `autonomy_min` catalogue filter.
AUTONOMY_ORDER = [
    "TELEOPERATED", "ASSISTED", "SUPERVISED_AUTONOMY", "TASK_AUTONOMOUS",
    "HIGHLY_AUTONOMOUS",
]
