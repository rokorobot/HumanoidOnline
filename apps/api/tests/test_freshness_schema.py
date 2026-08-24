"""DATA-D1 Scheduled Freshness — schema + structural-isolation gates
(docs/22, RATIFIED v0.1; migration 0010).

WorkOrder "Scheduled Freshness Foundation v0.1" tests:
  A. FreshnessTarget uniqueness
  B. Robot FK integrity
  C. DiscoverySource FK integrity
  V. freshness_trigger cannot authorize generic DATA-D1 radar ingest
     (structurally: no shared table/FK with crawl_run)
  W. crawl_trigger remains MANUAL-only
  Z. schema introspection confirms NO new freshness column was added to
     discovery_candidate

Every DB test runs inside a transaction that is rolled back, so nothing
touches the shared seeded database (same convention as
test_acquisition_schema.py / test_discovery.py).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models import freshness as freshness_models
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.models.freshness import FreshnessObservation, FreshnessTarget
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot

#: Canonical catalogue tables. Nothing in the freshness layer may reference
#: these except FreshnessTarget.robot_id itself (an outbound FK, which is
#: expected and ratified — docs/22 Phase 2).
CANONICAL_TABLES = {
    "robot", "manufacturer", "robot_variant", "specification", "spec_definition",
    "pricing_offer", "availability_offer", "deployment", "provider", "region",
    "capability", "robot_capability", "use_case", "use_case_fit", "evidence_source",
    "robot_image", "commercial_lead", "buyer_requirement", "match_result",
}

FRESHNESS_TABLES = {"freshness_target", "freshness_observation"}

#: The single, unmodified ratified value (LIVE.4). This set must never change
#: because of the freshness layer.
CRAWL_TRIGGER_VALUES = {"MANUAL"}
FRESHNESS_TRIGGER_VALUES = {"MANUAL", "SCHEDULED_FRESHNESS"}


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


def _robot(session: Session) -> Robot:
    mfr = Manufacturer(slug=f"mfr-{_uniq()}", name=f"Fixture Mfr {_uniq()}")
    session.add(mfr)
    session.flush()
    robot = Robot(slug=f"rob-{_uniq()}", manufacturer_id=mfr.id, name="Fixture Robot")
    session.add(robot)
    session.flush()
    return robot


def _source(session: Session) -> DiscoverySource:
    src = DiscoverySource(key=f"fixture-{_uniq()}", name="Fixture", source_class="MANUFACTURER")
    session.add(src)
    session.flush()
    return src


def _target(
    session: Session, robot: Robot, source: DiscoverySource, **overrides
) -> FreshnessTarget:
    kwargs = dict(robot_id=robot.id, discovery_source_id=source.id,
                  url="https://example.invalid/g1", purpose="SPEC")
    kwargs.update(overrides)
    target = FreshnessTarget(**kwargs)
    session.add(target)
    session.flush()
    return target


# ---- Tables exist with the ratified shape -----------------------------------


def test_both_freshness_tables_exist(database_url) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names(schema="humanoid"))
    assert FRESHNESS_TABLES <= tables


# ---- A: FreshnessTarget (robot_id, url) uniqueness --------------------------


def test_A_duplicate_robot_url_is_refused(dsession: Session) -> None:
    robot = _robot(dsession)
    source = _source(dsession)
    _target(dsession, robot, source, url="https://example.invalid/g1")
    with pytest.raises(IntegrityError):
        _target(dsession, robot, source, url="https://example.invalid/g1")


def test_A_same_url_on_a_different_robot_is_fine(dsession: Session) -> None:
    source = _source(dsession)
    r1, r2 = _robot(dsession), _robot(dsession)
    _target(dsession, r1, source, url="https://example.invalid/shared")
    _target(dsession, r2, source, url="https://example.invalid/shared")  # no error


def test_A_two_urls_on_the_same_robot_is_fine(dsession: Session) -> None:
    robot = _robot(dsession)
    source = _source(dsession)
    _target(dsession, robot, source, url="https://example.invalid/spec")
    _target(dsession, robot, source, url="https://example.invalid/price")  # no error


# ---- B: robot_id FK integrity ------------------------------------------------


def test_B_nonexistent_robot_is_refused(dsession: Session) -> None:
    source = _source(dsession)
    target = FreshnessTarget(
        robot_id=uuid.uuid4(), discovery_source_id=source.id,
        url="https://example.invalid/x", purpose="SPEC",
    )
    dsession.add(target)
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_B_deleting_the_robot_cascades_to_its_freshness_targets(dsession: Session) -> None:
    from app.models.robot import authorized_robot_deletion

    robot = _robot(dsession)
    source = _source(dsession)
    target = _target(dsession, robot, source)
    target_id = target.id
    # DR-C1 (unrelated to freshness): the catalogue is cumulative and an
    # ordinary session.delete(robot) is refused by an ORM guard. The FK
    # CASCADE this test actually proves only fires through the one
    # sanctioned deletion path.
    with authorized_robot_deletion(
        authorized_by="tester@humanoid.company", reason="freshness FK cascade test"
    ):
        dsession.delete(robot)
        dsession.flush()
    assert dsession.get(FreshnessTarget, target_id) is None


# ---- C: discovery_source_id FK integrity ------------------------------------


def test_C_nonexistent_source_is_refused(dsession: Session) -> None:
    robot = _robot(dsession)
    target = FreshnessTarget(
        robot_id=robot.id, discovery_source_id=uuid.uuid4(),
        url="https://example.invalid/x", purpose="SPEC",
    )
    dsession.add(target)
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_C_deleting_a_referenced_source_is_restricted(dsession: Session) -> None:
    robot = _robot(dsession)
    source = _source(dsession)
    _target(dsession, robot, source)
    dsession.delete(source)
    with pytest.raises(IntegrityError):
        dsession.flush()


# ---- interval_days CHECK (>= 7, A2's weekly ceiling) ------------------------


def test_interval_days_below_seven_is_refused(dsession: Session) -> None:
    robot = _robot(dsession)
    source = _source(dsession)
    with pytest.raises(IntegrityError):
        _target(dsession, robot, source, interval_days=1)


def test_interval_days_of_exactly_seven_is_the_default_and_is_accepted(dsession: Session) -> None:
    robot = _robot(dsession)
    source = _source(dsession)
    target = _target(dsession, robot, source)
    assert target.interval_days == 7


# ---- observation error_detail length CHECK ----------------------------------


def test_observation_error_detail_over_1000_chars_is_refused(dsession: Session) -> None:
    robot = _robot(dsession)
    source = _source(dsession)
    target = _target(dsession, robot, source)
    obs = FreshnessObservation(
        freshness_target_id=target.id, trigger="MANUAL",
        execution_mode_at_check="MANUAL_CHECK", result="FETCH_ERROR",
        error_detail="x" * 1001,
    )
    dsession.add(obs)
    with pytest.raises(IntegrityError):
        dsession.flush()


# ---- observation -> discovery_candidate FK (correction 2 lineage) ----------


def test_observation_discovery_candidate_fk_set_null_on_candidate_delete(dsession: Session) -> None:
    robot = _robot(dsession)
    source = _source(dsession)
    target = _target(dsession, robot, source)
    candidate = DiscoveryCandidate(source_id=source.id, external_ref=f"freshness/{target.id}/x")
    dsession.add(candidate)
    dsession.flush()
    obs = FreshnessObservation(
        freshness_target_id=target.id, trigger="MANUAL",
        execution_mode_at_check="MANUAL_CHECK", result="CHANGED",
        discovery_candidate_id=candidate.id,
    )
    dsession.add(obs)
    dsession.flush()
    obs_id = obs.id

    dsession.delete(candidate)
    dsession.flush()

    # The FK's ON DELETE SET NULL fires server-side; `obs` is already in this
    # session's identity map from the flush above, so session.get() would
    # return the same cached Python object with its stale pre-delete value
    # instead of re-querying. refresh() forces the re-SELECT that actually
    # observes what the database did.
    dsession.refresh(obs)
    assert dsession.get(FreshnessObservation, obs_id) is not None  # observation survives
    assert obs.discovery_candidate_id is None  # SET NULL, not RESTRICT


# ---- V / W: freshness_trigger is dedicated; crawl_trigger is untouched -----


def test_V_freshness_trigger_has_no_shared_table_or_fk_with_crawl_run(database_url) -> None:
    """Structural, not behavioural: freshness_observation cannot even NAME a
    crawl_run row, so there is no column through which a SCHEDULED_FRESHNESS
    trigger could reach the radar/discovery ingest path."""
    inspector = inspect(engine)
    fk_targets = {
        fk["referred_table"]
        for fk in inspector.get_foreign_keys("freshness_observation", schema="humanoid")
    }
    assert "crawl_run" not in fk_targets
    assert fk_targets == {"freshness_target", "discovery_candidate"}


def test_V_freshness_trigger_enum_is_a_distinct_pg_type_from_crawl_trigger() -> None:
    """The PG enum type backing FreshnessObservation.trigger is its own type
    (`freshness_trigger`), never `crawl_trigger` reused."""
    trigger_col = freshness_models.FreshnessObservation.__table__.c.trigger
    assert trigger_col.type.name == "freshness_trigger"


def test_W_crawl_trigger_values_are_unchanged(database_url) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT unnest(enum_range(NULL::humanoid.crawl_trigger))::text")
        ).scalars().all()
    assert set(rows) == CRAWL_TRIGGER_VALUES


def test_W_freshness_trigger_values_are_exactly_manual_and_scheduled(database_url) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT unnest(enum_range(NULL::humanoid.freshness_trigger))::text")
        ).scalars().all()
    assert set(rows) == FRESHNESS_TRIGGER_VALUES


# ---- Z: discovery_candidate gains no column ---------------------------------


def test_Z_discovery_candidate_gains_no_column(database_url) -> None:
    inspector = inspect(engine)
    columns = {
        c["name"] for c in inspector.get_columns("discovery_candidate", schema="humanoid")
    }
    # The ratified, pre-freshness column set (docs/11/docs/16). Any name here
    # NOT in this set would indicate the freshness migration altered the table.
    expected = {
        "id", "source_id", "entity_type", "candidate_name", "candidate_manufacturer",
        "discovery_url", "external_ref", "candidate_data", "identity_status", "status",
        "trace_state", "trace_url", "trace_source_type", "trace_verified_by",
        "trace_verified_at", "possible_robot_id", "possible_manufacturer_id",
        "promoted_robot_id", "discovered_at", "last_seen_at", "created_at", "updated_at",
    }
    assert columns == expected, f"unexpected columns on discovery_candidate: {columns - expected}"


def test_Z_freshness_observation_declares_the_lineage_fk(database_url) -> None:
    """...and discovery_candidate does not (correction 2)."""
    inspector = inspect(engine)
    dc_fks = {
        fk["referred_table"]
        for fk in inspector.get_foreign_keys("discovery_candidate", schema="humanoid")
    }
    assert "freshness_target" not in dc_fks
    assert "freshness_observation" not in dc_fks


# ---- Structural isolation, restated for this layer (Gate K) ----------------


def test_no_canonical_table_references_the_freshness_layer(database_url) -> None:
    inspector = inspect(engine)
    offenders: list[str] = []
    for table in sorted(CANONICAL_TABLES):
        for fk in inspector.get_foreign_keys(table, schema="humanoid"):
            if fk["referred_table"] in FRESHNESS_TABLES:
                offenders.append(f"{table}.{fk['constrained_columns']} -> {fk['referred_table']}")
    assert offenders == [], offenders


def test_no_freshness_model_maps_a_canonical_table(database_url) -> None:
    mapped = {
        obj.__tablename__
        for obj in vars(freshness_models).values()
        if isinstance(obj, type) and hasattr(obj, "__tablename__")
    }
    assert mapped & CANONICAL_TABLES == set(), mapped & CANONICAL_TABLES
    assert mapped == FRESHNESS_TABLES
