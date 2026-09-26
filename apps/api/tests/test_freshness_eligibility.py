"""DATA-D1 Scheduled Freshness — runtime eligibility + execution mode
(docs/22 Phase 3; WorkOrder "Scheduled Freshness Foundation v0.1" tests
D, E, F, G, H, I).

Pure unit tests: `freshness_auto_check_eligible` / `compute_execution_mode`
read only the attributes of the objects passed in, so these run with no
database, no session, and no fixtures — plain in-memory model instances.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.discovery import DiscoverySource
from app.models.freshness import FreshnessTarget
from app.services.freshness.eligibility import (
    compute_execution_mode,
    freshness_auto_check_eligible,
    mode_reason,
)

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _eligible_source(**overrides) -> DiscoverySource:
    kwargs = dict(
        key="fixture", name="Fixture", source_class="MANUFACTURER",
        tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=NOW - timedelta(days=1),
        eligibility_reviewed_by="ops@humanoid.company",
        is_enabled=True,
        tos_expires_at=NOW + timedelta(days=60),
        last_robots_checked_at=NOW - timedelta(hours=1),
    )
    kwargs.update(overrides)
    return DiscoverySource(**kwargs)


def _target(**overrides) -> FreshnessTarget:
    kwargs = dict(
        url="https://example.invalid/g1", purpose="SPEC",
        manual_override=False, interval_days=7, active=True,
    )
    kwargs.update(overrides)
    return FreshnessTarget(**kwargs)


# ---- D: eligibility fails closed on a source that was never reviewed -------


def test_D_missing_source_fails_closed() -> None:
    assert freshness_auto_check_eligible(None, NOW) is False
    assert compute_execution_mode(_target(), None, NOW) == "ELIGIBILITY_REVIEW_REQUIRED"


def test_D_unreviewed_source_fails_closed() -> None:
    src = DiscoverySource(key="fixture", name="Fixture", source_class="MANUFACTURER")
    assert freshness_auto_check_eligible(src, NOW) is False


# ---- E: AUTO_CHECK impossible without an affirmative D1.9 decision ---------


def test_E_fully_eligible_source_reaches_auto_check() -> None:
    src = _eligible_source()
    assert freshness_auto_check_eligible(src, NOW) is True
    assert compute_execution_mode(_target(), src, NOW) == "AUTO_CHECK"


def test_E_owner_recorded_tos_not_allowed_blocks_auto_check() -> None:
    src = _eligible_source(tos_status="RESTRICTED")
    assert freshness_auto_check_eligible(src, NOW) is False


def test_E_robots_disallowed_blocks_auto_check() -> None:
    src = _eligible_source(robots_status="DISALLOWED")
    assert freshness_auto_check_eligible(src, NOW) is False


def test_E_not_enabled_blocks_auto_check() -> None:
    src = _eligible_source(is_enabled=False)
    assert freshness_auto_check_eligible(src, NOW) is False


def test_E_unattributed_review_blocks_auto_check() -> None:
    src = _eligible_source(eligibility_reviewed_by=None)
    assert freshness_auto_check_eligible(src, NOW) is False


# ---- F: manual_override prevents AUTO_CHECK, unconditionally ---------------


def test_F_manual_override_forces_manual_check_even_when_source_is_eligible() -> None:
    src = _eligible_source()
    target = _target(manual_override=True)
    assert compute_execution_mode(target, src, NOW) == "MANUAL_CHECK"


def test_F_manual_override_short_circuits_before_eligibility_is_consulted() -> None:
    # An ineligible source would ALSO produce a non-AUTO_CHECK mode, so prove
    # the precedence directly: manual_override wins even though a `source=None`
    # (missing DiscoverySource entirely) would otherwise map to
    # ELIGIBILITY_REVIEW_REQUIRED, not MANUAL_CHECK.
    target = _target(manual_override=True)
    assert compute_execution_mode(target, None, NOW) == "MANUAL_CHECK"


def test_F_inactive_takes_precedence_over_manual_override() -> None:
    target = _target(manual_override=True, active=False)
    assert compute_execution_mode(target, _eligible_source(), NOW) == "INACTIVE"


# ---- G: ToS currency is NOT a gate (owner decision DR-A4) -----------------
# The owner reads terms personally and records tos_status; that decision does
# not expire. These tests exist so a refactor cannot silently reintroduce the
# former 90-day expiry / page-hash gate.


def test_G_expired_tos_expiry_does_not_block_auto_check() -> None:
    src = _eligible_source(tos_expires_at=NOW - timedelta(days=365))
    assert freshness_auto_check_eligible(src, NOW) is True
    assert compute_execution_mode(_target(), src, NOW) == "AUTO_CHECK"


def test_G_missing_tos_expiry_does_not_block_auto_check() -> None:
    src = _eligible_source(tos_expires_at=None, tos_reviewed_at=None)
    assert freshness_auto_check_eligible(src, NOW) is True


def test_G_changed_tos_page_hash_does_not_block_auto_check() -> None:
    src = _eligible_source(tos_page_hash="0" * 64)
    assert freshness_auto_check_eligible(src, NOW) is True


# ---- H: a stale robots/access-policy check prevents AUTO_CHECK (LIVE.2) ----


def test_H_stale_robots_check_blocks_auto_check() -> None:
    src = _eligible_source(last_robots_checked_at=NOW - timedelta(hours=25))
    assert freshness_auto_check_eligible(src, NOW) is False


def test_H_robots_check_at_exactly_the_24h_ceiling_is_still_current() -> None:
    src = _eligible_source(last_robots_checked_at=NOW - timedelta(hours=24))
    assert freshness_auto_check_eligible(src, NOW) is True


def test_H_robots_check_one_second_past_24h_is_stale() -> None:
    src = _eligible_source(last_robots_checked_at=NOW - timedelta(hours=24, seconds=1))
    assert freshness_auto_check_eligible(src, NOW) is False


def test_H_radar_eligible_alone_does_not_catch_the_robots_recency_gap() -> None:
    src = _eligible_source(last_robots_checked_at=NOW - timedelta(hours=25))
    assert src.radar_eligible is True
    assert freshness_auto_check_eligible(src, NOW) is False


# ---- I: missing eligibility timestamps prevent AUTO_CHECK, never default ----
# ---- to "eligible forever" --------------------------------------------------


def test_I_missing_last_robots_checked_at_fails_closed_not_open() -> None:
    src = _eligible_source(last_robots_checked_at=None)
    assert freshness_auto_check_eligible(src, NOW) is False


def test_I_missing_eligibility_reviewed_at_fails_closed() -> None:
    src = _eligible_source(eligibility_reviewed_at=None)
    assert freshness_auto_check_eligible(src, NOW) is False


# ---- mode_reason: informational, never contradicts compute_execution_mode --


def test_mode_reason_matches_each_computed_mode() -> None:
    src = _eligible_source()
    assert "inactive" in mode_reason(_target(active=False), src, "INACTIVE")
    assert "override" in mode_reason(_target(manual_override=True), src, "MANUAL_CHECK")
    assert mode_reason(_target(), src, "AUTO_CHECK") == "eligible"


def test_mode_reason_identifies_the_specific_failing_currentness_check() -> None:
    not_allowed = _eligible_source(tos_status="RESTRICTED")
    reason = mode_reason(_target(), not_allowed, "ELIGIBILITY_REVIEW_REQUIRED")
    assert "tos_status=RESTRICTED" in reason

    stale_robots = _eligible_source(last_robots_checked_at=NOW - timedelta(hours=25))
    reason = mode_reason(_target(), stale_robots, "ELIGIBILITY_REVIEW_REQUIRED")
    assert "expired" in reason.lower()

    missing = mode_reason(_target(), None, "ELIGIBILITY_REVIEW_REQUIRED")
    assert "no DiscoverySource" in missing
