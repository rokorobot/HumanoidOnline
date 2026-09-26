"""Initialization checks against PostgreSQL, isolated by rollback."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, update
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import DiscoverySource
from app.services.discovery.bootstrap import bootstrap, bootstrap_source_key, load_dataset
from app.services.discovery.readiness import BASELINE_DATASET, check_readiness


@pytest.fixture
def dsession(database_url):
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        try:
            # Hide any existing setup without deleting rows or relying on DB history.
            session.execute(update(DiscoverySource).values(is_enabled=False))
            session.execute(update(DiscoverySource).where(
                DiscoverySource.key == bootstrap_source_key(BASELINE_DATASET)
            ).values(key=f"test-hidden:{uuid.uuid4().hex}"))
            yield session
        finally:
            session.close()
            transaction.rollback()


def live_source(session, **overrides):
    fields = dict(
        key=f"test-live:{uuid.uuid4().hex}", name="Fixture manufacturer",
        source_class="MANUFACTURER", homepage_url="https://example.invalid/",
        allowed_path_prefixes=["/products/"], is_enabled=True,
        tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime.now(UTC), eligibility_reviewed_by="fixture@test",
    )
    fields.update(overrides)
    source = DiscoverySource(**fields)
    session.add(source)
    session.flush()
    return source


def test_uninitialized_layer_names_missing_prerequisites(dsession):
    report = check_readiness(dsession)
    assert not report.prerequisites_ready
    assert not report.execution_ready
    assert report.missing_prerequisites == (
        "LEAD_BASELINE_SOURCE_MISSING", "LEAD_BASELINE_INCOMPLETE",
        "NO_RADAR_ELIGIBLE_LIVE_SOURCE",
    )
    assert set(report.missing_lead_refs) == {
        r["external_ref"] for r in load_dataset(BASELINE_DATASET)
    }


def test_complete_baseline_alone_is_not_a_live_source(dsession):
    bootstrap(dsession, dataset=BASELINE_DATASET, operator="fixture@test")
    report = check_readiness(dsession)
    assert report.baseline_source_present
    assert not report.missing_lead_refs
    assert report.missing_prerequisites == ("NO_RADAR_ELIGIBLE_LIVE_SOURCE",)


def test_complete_initialization_never_enables_execution(dsession):
    bootstrap(dsession, dataset=BASELINE_DATASET, operator="fixture@test")
    source = live_source(dsession)
    report = check_readiness(dsession)
    assert report.prerequisites_ready
    assert report.eligible_source_keys == (source.key,)
    assert not report.execution_ready


def test_equal_count_with_wrong_reference_is_incomplete(dsession):
    records = load_dataset(BASELINE_DATASET)
    missing = records[0]["external_ref"]
    records[0] = {**records[0], "external_ref": "fixture/unexpected"}
    bootstrap(dsession, dataset=BASELINE_DATASET, operator="fixture@test", records=records)
    live_source(dsession)
    report = check_readiness(dsession)
    assert report.missing_lead_refs == (missing,)
    assert report.missing_prerequisites == ("LEAD_BASELINE_INCOMPLETE",)


def test_full_dataset_under_other_source_does_not_satisfy_baseline(dsession):
    bootstrap(dsession, dataset=f"test-{uuid.uuid4().hex}", operator="fixture@test",
              records=load_dataset(BASELINE_DATASET))
    live_source(dsession)
    assert not check_readiness(dsession).baseline_source_present
    assert not check_readiness(dsession).prerequisites_ready


@pytest.mark.parametrize("overrides", [
    {"is_enabled": False},
    {"is_enabled": False, "tos_status": "UNKNOWN"},
    {"is_enabled": False, "robots_status": "DISALLOWED"},
    {"is_enabled": False, "eligibility_reviewed_by": None},
])
def test_ineligible_source_cannot_satisfy_initialization(dsession, overrides):
    live_source(dsession, **overrides)
    assert not check_readiness(dsession).eligible_source_keys


@pytest.mark.parametrize("overrides", [
    {"homepage_url": None},
    {"allowed_path_prefixes": None},
    {"allowed_path_prefixes": ["products/"]},
])
def test_source_without_approved_host_or_paths_is_not_counted(dsession, overrides):
    live_source(dsession, **overrides)
    assert not check_readiness(dsession).eligible_source_keys


@pytest.mark.parametrize("overrides", [
    {"tos_expires_at": None},
    {"tos_expires_at": datetime.now(UTC) - timedelta(days=365)},
    {"tos_page_hash": "0" * 64},
])
def test_tos_currency_does_not_affect_readiness(dsession, overrides):
    """Owner decision DR-A4: ToS expiry and page-hash changes never gate."""
    source = live_source(dsession, **overrides)
    assert check_readiness(dsession).eligible_source_keys == (source.key,)


def test_readiness_does_not_flush_pending_writes(dsession):
    dsession.add(DiscoverySource(key="pending-invalid", name="Unflushed"))

    def refuse_flush(*args):
        pytest.fail("readiness must not flush pending writes")

    event.listen(dsession, "before_flush", refuse_flush)
    assert not check_readiness(dsession).prerequisites_ready
    assert dsession.new
