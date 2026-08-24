"""DATA-D1 Scheduled Freshness — service behavior (docs/22, RATIFIED v0.1).

WorkOrder "Scheduled Freshness Foundation v0.1" tests:
  J. MANUAL_CHECK path makes ZERO HTTP requests
  K. unchanged fingerprint creates no DiscoveryCandidate
  L. changed fingerprint creates/reuses RECHECK_REQUIRED only
  M. same change retry creates no duplicate candidate
  N. same change whose existing candidate became terminal creates NO
     replacement candidate and does NOT resurrect terminal work
  O. new distinct changed fingerprint creates a distinct candidate
  P. observation -> candidate lineage is correct
  Q. canonical robot/catalogue data remains unchanged on every freshness path
  R. FETCH_ERROR preserves canonical state and UNKNOWN semantics
  S. SOURCE_REMOVED does not unpublish
  T. one target failure does not corrupt processing of another target
  U. 7-day due/not-due interval is enforced
  X. zero AUTO_CHECK targets is valid
  Y. manual and future scheduled modes share the same governed result/change
     service path

Every DB test runs inside a transaction that is rolled back (same convention
as test_discovery.py / test_acquisition_schema.py / test_freshness_schema.py).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.models.freshness import FreshnessObservation, FreshnessTarget
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery.pipeline import advance, record_trace
from app.services.discovery.promotion import promote, reject
from app.services.freshness import FreshnessError
from app.services.freshness.service import (
    CheckOutcome,
    create_or_reuse_recheck,
    due_manual_targets,
    due_targets,
    is_due,
    record_manual_check,
    record_observation,
    run_due_checks,
)


@pytest.fixture
def dsession(database_url) -> Session:
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        conn.close()


def _uniq() -> str:
    return uuid.uuid4().hex[:8]


def _robot(session: Session, *, published: bool = True) -> Robot:
    # Deliberately distinctive names (mirroring test_discovery.py's "Zeta
    # ZX-1" style): a generic "Fixture Robot" under "Fixture Mfr" would strip
    # down to an empty resolve_identity() model_key (both "fixture" and the
    # generic stopword "robot" get filtered), producing POSSIBLE_DUPLICATE
    # instead of MATCHED_EXISTING and blocking advance()/promote() in tests
    # that exercise the full pipeline.
    tag = _uniq()
    mfr = Manufacturer(slug=f"mfr-{tag}", name=f"Zeta{tag} Robotics")
    session.add(mfr)
    session.flush()
    robot = Robot(
        slug=f"rob-{tag}", manufacturer_id=mfr.id, name=f"ZX-{tag}",
        is_published=published,
    )
    session.add(robot)
    session.flush()
    return robot


def _eligible_source(session: Session) -> DiscoverySource:
    now = datetime.now(UTC)
    src = DiscoverySource(
        key=f"fixture-{_uniq()}", name="Fixture", source_class="MANUFACTURER",
        tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=now, eligibility_reviewed_by="ops@humanoid.company",
        is_enabled=True, tos_expires_at=now + timedelta(days=60),
        last_robots_checked_at=now,
    )
    session.add(src)
    session.flush()
    return src


def _unreviewed_source(session: Session) -> DiscoverySource:
    src = DiscoverySource(key=f"fixture-{_uniq()}", name="Fixture", source_class="MANUFACTURER")
    session.add(src)
    session.flush()
    return src


def _target(
    session: Session, robot: Robot, source: DiscoverySource, **overrides
) -> FreshnessTarget:
    kwargs = dict(
        robot_id=robot.id, discovery_source_id=source.id,
        url=f"https://example.invalid/{_uniq()}", purpose="SPEC",
    )
    kwargs.update(overrides)
    target = FreshnessTarget(**kwargs)
    session.add(target)
    session.flush()
    return target


class _RaisingChecker:
    """A FreshnessChecker whose .check() always raises — for test T/M (one
    failing target must not abort the run)."""

    def check(self, target: FreshnessTarget):
        raise RuntimeError("simulated network failure")


class _AlwaysChangedChecker:
    """Returns the same CHANGED outcome for every target it is asked about."""

    def __init__(self, fingerprint: str = "fp-1"):
        self._fingerprint = fingerprint

    def check(self, target: FreshnessTarget) -> CheckOutcome:
        return CheckOutcome(result="CHANGED", content_fingerprint=self._fingerprint)


def _row_counts(session: Session, *models) -> dict:
    return {m: session.execute(select(func.count()).select_from(m)).scalar_one() for m in models}


# ---- U: 7-day due/not-due interval is enforced ------------------------------


def test_U_never_checked_target_is_due() -> None:
    target = FreshnessTarget(interval_days=7, last_checked_at=None)
    assert is_due(target, datetime.now(UTC)) is True


def test_U_checked_three_days_ago_is_not_due() -> None:
    now = datetime.now(UTC)
    target = FreshnessTarget(interval_days=7, last_checked_at=now - timedelta(days=3))
    assert is_due(target, now) is False


def test_U_checked_eight_days_ago_is_due() -> None:
    now = datetime.now(UTC)
    target = FreshnessTarget(interval_days=7, last_checked_at=now - timedelta(days=8))
    assert is_due(target, now) is True


def test_U_checked_exactly_seven_days_ago_is_due() -> None:
    now = datetime.now(UTC)
    target = FreshnessTarget(interval_days=7, last_checked_at=now - timedelta(days=7))
    assert is_due(target, now) is True


def test_U_due_targets_query_respects_active_flag(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    active = _target(dsession, robot, source, active=True)
    _target(dsession, robot, source, active=False, url="https://example.invalid/inactive")
    due = due_targets(dsession)
    assert [t.id for t in due] == [active.id]


# ---- K: unchanged fingerprint creates no DiscoveryCandidate -----------------


def test_K_unchanged_result_creates_no_candidate(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)
    before = _row_counts(dsession, DiscoveryCandidate)

    obs = record_observation(
        dsession, target, trigger="MANUAL", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="UNCHANGED", content_fingerprint="abc123"),
    )

    assert obs.discovery_candidate_id is None
    assert _row_counts(dsession, DiscoveryCandidate) == before


# ---- L: changed fingerprint creates/reuses RECHECK_REQUIRED only -----------


def test_L_changed_result_creates_exactly_one_recheck_required_candidate(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )

    assert obs.discovery_candidate_id is not None
    candidate = dsession.get(DiscoveryCandidate, obs.discovery_candidate_id)
    assert candidate.status == "RECHECK_REQUIRED"
    assert candidate.possible_robot_id == robot.id


# ---- M: same change retry creates no duplicate candidate -------------------


def test_M_repeated_changed_fingerprint_reuses_the_same_candidate(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs1 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )
    obs2 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )

    assert obs1.discovery_candidate_id == obs2.discovery_candidate_id
    assert _row_counts(dsession, DiscoveryCandidate)[DiscoveryCandidate] == 1


def test_M_run_due_checks_scheduler_retry_is_idempotent(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)
    checker = _AlwaysChangedChecker()

    run_due_checks(dsession, trigger="SCHEDULED_FRESHNESS", checker=checker)
    dsession.refresh(target)
    # A "retry" of the same weekly run before the interval elapses again
    # finds the target no longer due — the natural idempotency guard.
    assert due_targets(dsession) == []


# ---- N: a terminal historical candidate is never resurrected ---------------


def test_N_terminal_promoted_candidate_not_touched(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs1 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )
    candidate = dsession.get(DiscoveryCandidate, obs1.discovery_candidate_id)
    record_trace(
        dsession, candidate, trace_url="https://example.invalid/g1",
        trace_source_type="MANUFACTURER_SITE", verified_by="ops@humanoid.company",
    )
    advance(dsession, candidate)
    promote(dsession, candidate, "ops@humanoid.company")
    dsession.flush()
    assert candidate.status == "PROMOTED"
    before = _row_counts(dsession, DiscoveryCandidate)

    # The SAME fingerprint recurs (e.g. a retry, or the page reverted to
    # already-reviewed content). Must NOT resurrect, must NOT create a
    # replacement candidate.
    obs2 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )

    assert _row_counts(dsession, DiscoveryCandidate) == before  # no new candidate
    assert obs2.discovery_candidate_id == candidate.id  # lineage still recorded
    dsession.refresh(candidate)
    assert candidate.status == "PROMOTED"  # never flipped back to RECHECK_REQUIRED


def test_N_terminal_rejected_candidate_not_touched(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs1 = record_observation(
        dsession, target, trigger="MANUAL", mode="MANUAL_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )
    candidate = dsession.get(DiscoveryCandidate, obs1.discovery_candidate_id)
    reject(dsession, candidate, "ops@humanoid.company", "not a real change")
    before = _row_counts(dsession, DiscoveryCandidate)

    obs2 = record_observation(
        dsession, target, trigger="MANUAL", mode="MANUAL_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )

    assert _row_counts(dsession, DiscoveryCandidate) == before
    assert obs2.discovery_candidate_id == candidate.id
    dsession.refresh(candidate)
    assert candidate.status == "REJECTED"


# ---- O: a genuinely new, distinct changed fingerprint creates a NEW --------
# ---- candidate, independent of any other candidate's state -----------------


def test_O_a_different_fingerprint_creates_a_second_distinct_candidate(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs1 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )
    obs2 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-2"),
    )

    assert obs1.discovery_candidate_id != obs2.discovery_candidate_id
    assert _row_counts(dsession, DiscoveryCandidate)[DiscoveryCandidate] == 2


def test_O_new_change_after_promotion_creates_new_candidate(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs1 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )
    c1 = dsession.get(DiscoveryCandidate, obs1.discovery_candidate_id)
    record_trace(dsession, c1, trace_url="https://example.invalid/g1",
                 trace_source_type="MANUFACTURER_SITE", verified_by="ops@humanoid.company")
    advance(dsession, c1)
    promote(dsession, c1, "ops@humanoid.company")
    dsession.flush()

    obs2 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-2"),
    )

    assert obs2.discovery_candidate_id != c1.id
    c2 = dsession.get(DiscoveryCandidate, obs2.discovery_candidate_id)
    assert c2.status == "RECHECK_REQUIRED"


# ---- P: observation -> candidate lineage is correct -------------------------


def test_P_lineage_resolves_to_the_exact_candidate_flag_recheck_acted_on(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )
    reloaded = dsession.get(FreshnessObservation, obs.id)
    candidate = dsession.get(DiscoveryCandidate, reloaded.discovery_candidate_id)
    assert candidate is not None
    assert candidate.external_ref == f"freshness/{target.id}/fp-1"


def test_P_unchanged_and_fetch_error_observations_carry_null_lineage(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    unchanged = record_observation(
        dsession, target, trigger="MANUAL", mode="MANUAL_CHECK",
        outcome=CheckOutcome(result="UNCHANGED"),
    )
    error = record_observation(
        dsession, target, trigger="MANUAL", mode="MANUAL_CHECK",
        outcome=CheckOutcome(result="FETCH_ERROR", error_detail="timeout"),
    )
    assert unchanged.discovery_candidate_id is None
    assert error.discovery_candidate_id is None


# ---- Q: canonical data is unchanged on every freshness path ----------------


@pytest.mark.parametrize(
    "outcome",
    [
        CheckOutcome(result="UNCHANGED", content_fingerprint="fp"),
        CheckOutcome(result="CHANGED", content_fingerprint="fp"),
        CheckOutcome(result="FETCH_ERROR", error_detail="boom"),
        CheckOutcome(result="SOURCE_REMOVED"),
    ],
)
def test_Q_canonical_robot_row_unchanged_by_result(dsession: Session, outcome) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)
    before = (robot.name, robot.is_published, robot.commercial_status, robot.height_cm)

    record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK", outcome=outcome
    )

    dsession.refresh(robot)
    after = (robot.name, robot.is_published, robot.commercial_status, robot.height_cm)
    assert before == after


def test_Q_no_canonical_table_row_count_changes(dsession: Session) -> None:
    from app.models.commercial import PricingOffer

    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)
    before = _row_counts(dsession, Robot, PricingOffer)

    record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-1"),
    )

    assert _row_counts(dsession, Robot, PricingOffer) == before


# ---- R: FETCH_ERROR preserves canonical state + UNKNOWN semantics ----------


def test_R_fetch_error_does_not_touch_target_validators(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(
        dsession, robot, source,
        etag="etag-1", last_modified="mod-1", content_fingerprint="fp-1",
    )

    record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="FETCH_ERROR", http_status=503, error_detail="timeout"),
    )

    dsession.refresh(target)
    assert target.etag == "etag-1"
    assert target.last_modified == "mod-1"
    assert target.content_fingerprint == "fp-1"  # carried forward, not cleared


def test_R_fetch_error_creates_no_candidate(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)
    before = _row_counts(dsession, DiscoveryCandidate)

    obs = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="FETCH_ERROR", error_detail="dns failure"),
    )

    assert obs.discovery_candidate_id is None
    assert _row_counts(dsession, DiscoveryCandidate) == before


# ---- S: SOURCE_REMOVED does not unpublish -----------------------------------


def test_S_source_removed_does_not_unpublish_the_robot(dsession: Session) -> None:
    robot, source = _robot(dsession, published=True), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="SOURCE_REMOVED"),
    )

    dsession.refresh(robot)
    assert robot.is_published is True


def test_S_source_removed_does_not_mutate_target_config(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source, manual_override=False, active=True)

    record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="SOURCE_REMOVED"),
    )

    dsession.refresh(target)
    assert target.manual_override is False  # no automatic config mutation
    assert target.active is True


def test_S_source_removed_creates_recheck_signal(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="SOURCE_REMOVED"),
    )

    assert obs.discovery_candidate_id is not None
    candidate = dsession.get(DiscoveryCandidate, obs.discovery_candidate_id)
    assert candidate.status == "RECHECK_REQUIRED"
    assert candidate.external_ref == f"freshness/{target.id}/SOURCE_REMOVED"


def test_S_repeated_source_removed_reuses_one_thread(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs1 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="SOURCE_REMOVED"),
    )
    obs2 = record_observation(
        dsession, target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="SOURCE_REMOVED"),
    )
    assert obs1.discovery_candidate_id == obs2.discovery_candidate_id


# ---- T: one failing target does not corrupt processing of another ---------


def test_T_one_checker_exception_becomes_fetch_error(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    ok_target = _target(dsession, robot, source, url="https://example.invalid/ok")
    bad_target = _target(dsession, robot, source, url="https://example.invalid/bad")

    class _MixedChecker:
        def check(self, target: FreshnessTarget) -> CheckOutcome:
            if target.id == bad_target.id:
                raise RuntimeError("simulated network failure")
            return CheckOutcome(result="UNCHANGED", content_fingerprint="fp")

    observations = run_due_checks(dsession, trigger="SCHEDULED_FRESHNESS", checker=_MixedChecker())

    by_target = {o.freshness_target_id: o for o in observations}
    assert by_target[ok_target.id].result == "UNCHANGED"
    assert by_target[bad_target.id].result == "FETCH_ERROR"
    assert "simulated network failure" in by_target[bad_target.id].error_detail


def test_T_a_failing_target_does_not_prevent_a_third_target_after_it(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    t1 = _target(dsession, robot, source, url="https://example.invalid/1")
    t2 = _target(dsession, robot, source, url="https://example.invalid/2")
    t3 = _target(dsession, robot, source, url="https://example.invalid/3")

    class _SecondFails:
        def check(self, target: FreshnessTarget) -> CheckOutcome:
            if target.id == t2.id:
                raise RuntimeError("boom")
            return CheckOutcome(result="UNCHANGED", content_fingerprint="fp")

    observations = run_due_checks(dsession, trigger="SCHEDULED_FRESHNESS", checker=_SecondFails())
    assert {o.freshness_target_id for o in observations} == {t1.id, t2.id, t3.id}


# ---- X: zero AUTO_CHECK targets is a valid state ----------------------------


def test_X_run_due_checks_against_an_empty_table_is_a_clean_noop(dsession: Session) -> None:
    result = run_due_checks(dsession, trigger="SCHEDULED_FRESHNESS", checker=_RaisingChecker())
    assert result == []


def test_X_non_eligible_targets_never_call_checker(dsession: Session) -> None:
    robot, source = _robot(dsession), _unreviewed_source(dsession)
    _target(dsession, robot, source)  # ELIGIBILITY_REVIEW_REQUIRED — never AUTO_CHECK

    class _CountingChecker:
        calls = 0

        def check(self, target: FreshnessTarget) -> CheckOutcome:
            self.calls += 1
            return CheckOutcome(result="UNCHANGED")

    checker = _CountingChecker()
    result = run_due_checks(dsession, trigger="SCHEDULED_FRESHNESS", checker=checker)
    assert result == []
    assert checker.calls == 0


# ---- J: MANUAL_CHECK path makes ZERO HTTP requests --------------------------


def test_J_record_manual_check_never_invokes_any_checker(dsession: Session) -> None:
    """record_manual_check() has no FreshnessChecker parameter at all — the
    manual path cannot invoke a fetch by construction, not merely by
    discipline."""
    import inspect as _inspect

    sig = _inspect.signature(record_manual_check)
    assert "checker" not in sig.parameters

    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)
    obs = record_manual_check(
        dsession, target, outcome="CHECKED_UNCHANGED", operator="ops@humanoid.company",
    )
    assert obs.result == "UNCHANGED"


def test_J_due_manual_targets_never_touches_a_checker_either(dsession: Session) -> None:
    robot, source = _robot(dsession), _unreviewed_source(dsession)
    _target(dsession, robot, source)
    result = due_manual_targets(dsession)  # no checker argument exists to pass
    assert len(result) == 1


def test_manual_check_requires_an_attributed_operator(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)
    with pytest.raises(FreshnessError):
        record_manual_check(dsession, target, outcome="CHECKED_UNCHANGED", operator="")


# ---- Y: manual and scheduled modes share the same governed change path ----


def test_Y_manual_and_automated_use_identical_function(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    manual_target = _target(dsession, robot, source, url="https://example.invalid/manual")
    auto_target = _target(dsession, robot, source, url="https://example.invalid/auto")

    manual_obs = record_manual_check(
        dsession, manual_target, outcome="CHANGE_FOUND", operator="ops@humanoid.company",
        content_fingerprint="fp-shared",
    )
    auto_obs = record_observation(
        dsession, auto_target, trigger="SCHEDULED_FRESHNESS", mode="AUTO_CHECK",
        outcome=CheckOutcome(result="CHANGED", content_fingerprint="fp-shared"),
    )

    manual_candidate = dsession.get(DiscoveryCandidate, manual_obs.discovery_candidate_id)
    auto_candidate = dsession.get(DiscoveryCandidate, auto_obs.discovery_candidate_id)
    # Different targets -> different external_ref -> different candidates,
    # but IDENTICAL resulting shape: both RECHECK_REQUIRED, both linked to
    # their robot, produced by the same create_or_reuse_recheck() call.
    assert manual_candidate.status == auto_candidate.status == "RECHECK_REQUIRED"
    assert manual_candidate.possible_robot_id == auto_candidate.possible_robot_id == robot.id


def test_Y_repeated_manual_change_found_is_idempotent(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    obs1 = record_manual_check(
        dsession, target, outcome="CHANGE_FOUND", operator="ops@humanoid.company",
        content_fingerprint="fp-1",
    )
    obs2 = record_manual_check(
        dsession, target, outcome="CHANGE_FOUND", operator="ops@humanoid.company",
        content_fingerprint="fp-1",
    )
    assert obs1.discovery_candidate_id == obs2.discovery_candidate_id


# ---- create_or_reuse_recheck: direct unit coverage of the ratified algorithm


def test_create_or_reuse_recheck_is_a_pure_reuse_for_the_same_key(dsession: Session) -> None:
    robot, source = _robot(dsession), _eligible_source(dsession)
    target = _target(dsession, robot, source)

    c1 = create_or_reuse_recheck(dsession, target, "same-key", reason="first")
    c2 = create_or_reuse_recheck(dsession, target, "same-key", reason="second")
    assert c1.id == c2.id
