"""Runtime eligibility + effective execution mode — docs/22 Phase 3.

`DiscoverySource.radar_eligible` (app/models/discovery.py) is DATA-D1.9's base
gate, verified by direct inspection to check exactly five conditions
(is_enabled, tos_status, robots_status, reviewer attribution) and NOT to check
`tos_expires_at` or `last_robots_checked_at` recency at all. This module
composes the missing, already-ratified currentness requirements on top of it
— `radar_eligible` itself is never modified (it has other callers, notably
`adapters.ingest()`, whose scope this module does not touch).

No new expiry period is invented here: both numbers below (90 days, 24 hours)
are exactly the ones already ratified in docs/16 §7 and LIVE.2.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models.discovery import DiscoverySource
from app.models.freshness import FreshnessTarget

#: docs/16 LIVE.2 — robots policy is re-read at the start of every run and
#: cached at most 24 hours; a stored robots_status older than this must not
#: be trusted as current.
ROBOTS_RECENCY_CEILING = timedelta(hours=24)


def freshness_auto_check_eligible(source: DiscoverySource | None, now: datetime) -> bool:
    """DATA-D1.9 (`radar_eligible`, unmodified) PLUS the currentness
    requirements docs/16 §7 (90-day ToS expiry) and LIVE.2 (24h robots
    recheck ceiling) already ratify but `radar_eligible` does not itself
    check. Fails closed on every axis — a missing source or a missing/None
    timestamp is treated as NOT current, never as "no expiry means forever
    eligible."
    """
    if source is None:
        return False
    if not source.radar_eligible:
        return False
    if source.tos_expires_at is None or now > source.tos_expires_at:
        return False  # docs/16 §7 requirement 9 — no verifiable current review
    if (
        source.last_robots_checked_at is None
        or now - source.last_robots_checked_at > ROBOTS_RECENCY_CEILING
    ):
        return False  # docs/16 LIVE.2 — robots cache ceiling
    return True


def compute_execution_mode(
    target: FreshnessTarget, source: DiscoverySource | None, now: datetime
) -> str:
    """The sole authority for a target's current mode. Never read from a
    stored column — `FreshnessTarget` carries no `execution_mode` field
    (docs/22 Phase 2/3, correction 3), so this is recomputed fresh on every
    call and cannot go stale. Precedence, exactly as ratified:

      inactive           -> INACTIVE
      manual_override     -> MANUAL_CHECK (eligibility never consulted)
      current affirmative -> AUTO_CHECK
      otherwise           -> ELIGIBILITY_REVIEW_REQUIRED
    """
    if not target.active:
        return "INACTIVE"
    if target.manual_override:
        return "MANUAL_CHECK"
    if freshness_auto_check_eligible(source, now):
        return "AUTO_CHECK"
    return "ELIGIBILITY_REVIEW_REQUIRED"


def mode_reason(target: FreshnessTarget, source: DiscoverySource | None, mode: str) -> str:
    """A short, human-readable explanation of why `mode` is what it is — for
    the manual review queue (docs/22 Phase 9 / WorkOrder Phase 8: "why
    AUTO_CHECK is unavailable"). Informational only; never re-derives a
    different mode than `compute_execution_mode` already decided."""
    if mode == "INACTIVE":
        return "target is inactive"
    if mode == "MANUAL_CHECK":
        return "manual_override is set (hard operational override)"
    if mode == "AUTO_CHECK":
        return "eligible"
    # ELIGIBILITY_REVIEW_REQUIRED — walk the same checks freshness_auto_check_eligible
    # does, in order, and report the first one that fails.
    if source is None:
        return "no DiscoverySource is registered for this target's source"
    if not source.is_enabled:
        return "source is not enabled"
    if source.tos_status != "ALLOWED":
        return f"tos_status={source.tos_status} (DATA-D1.9 requires ALLOWED)"
    if source.robots_status not in ("ALLOWED", "NOT_APPLICABLE"):
        return f"robots_status={source.robots_status} (DATA-D1.9 requires ALLOWED/NOT_APPLICABLE)"
    if source.eligibility_reviewed_at is None or not source.eligibility_reviewed_by:
        return "no attributed eligibility review is recorded"
    if source.tos_expires_at is None:
        return "no recorded ToS expiry (docs/16 §7 requires a current, non-expired review)"
    if source.last_robots_checked_at is None:
        return "robots policy has never been checked (docs/16 LIVE.2 requires a recheck within 24h)"
    return "eligibility review or robots recheck has expired (docs/16 §7 / LIVE.2)"
