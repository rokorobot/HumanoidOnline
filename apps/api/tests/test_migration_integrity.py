"""WS8.2 / R9 — migration checksum integrity and the app-start contract.

Two defects, both silent before WS8.2:

- `db/bootstrap.py` recorded a `sha256` per applied migration and never read it
  back, so editing an applied migration was a no-op that reported "up to date".
- Nothing stopped the API from serving a database missing a migration.

The tests pin the two implementations *together*: `db/bootstrap.py` and
`app/db/migration_state.py` must agree on the version set and hash the same way,
or the app-level check would be verifying something the bootstrap never wrote.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db.migration_state import (
    BASELINE_VERSION,
    MigrationState,
    MigrationStateError,
    applied_migrations,
    expected_migrations,
    inspect_migration_state,
    sha256_text,
    verify_migration_state,
)
from app.db.session import engine

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_bootstrap():
    """Import db/bootstrap.py (a PEP-723 script, not an installed module)."""
    spec = importlib.util.spec_from_file_location(
        "ws8_bootstrap", REPO_ROOT / "db" / "bootstrap.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---- the two implementations must not drift apart -------------------------


def test_bootstrap_and_app_agree_on_the_governed_migration_set():
    """If these ever disagree, the startup check verifies a different thing than
    the bootstrap wrote — the check would pass while the database is wrong."""
    bootstrap = _load_bootstrap()
    from_bootstrap = {version: path for version, path in bootstrap._governed_files()}
    from_app = expected_migrations()

    assert set(from_bootstrap) == set(from_app)
    assert BASELINE_VERSION in from_app
    # The baseline is presence-only on both sides (see below); every forward
    # migration must hash identically in both implementations.
    assert from_app[BASELINE_VERSION] is None
    for version, path in from_bootstrap.items():
        if version == BASELINE_VERSION:
            continue
        assert from_app[version] == sha256_text(path.read_text(encoding="utf-8"))


def test_every_migration_file_on_disk_is_governed():
    expected = expected_migrations()
    on_disk = {p.stem for p in (REPO_ROOT / "db" / "migrations").glob("*.sql")}
    assert on_disk <= set(expected)
    assert on_disk, "expected at least one forward migration"


# ---- bootstrap drift detection (R9) ---------------------------------------


def test_baseline_checksum_is_exempt_on_both_sides():
    """`db/schema.sql` is canonical and is EDITED whenever the model changes
    (schema wins, then a forward migration lets existing databases converge —
    db/migrations/README.md). Its hash therefore differs legitimately from what
    any older database recorded.

    Checksum-verifying the baseline would declare every pre-existing environment
    corrupt and — because bootstrap now refuses on drift — would block the very
    migrations meant to bring it up to date. This pins the exemption on both
    implementations so it cannot be "tidied up" later.
    """
    bootstrap = _load_bootstrap()
    assert expected_migrations()[BASELINE_VERSION] is None

    # A wrong baseline checksum must NOT be reported as drift.
    bootstrap.verify_no_drift({BASELINE_VERSION: "0" * 64})
    state = MigrationState(
        expected=expected_migrations(), applied={BASELINE_VERSION: "0" * 64}
    )
    assert BASELINE_VERSION not in state.drifted


def test_bootstrap_detects_edited_applied_migration():
    """The core R9 behaviour: a changed checksum must raise, not be skipped."""
    bootstrap = _load_bootstrap()
    applied = {
        version: "0" * 64
        for version, _ in bootstrap._governed_files()
        if version != BASELINE_VERSION
    }
    with pytest.raises(bootstrap.MigrationDriftError) as exc:
        bootstrap.verify_no_drift(applied)
    message = str(exc.value)
    assert "checksum drift" in message
    assert "Nothing has been applied." in message


def test_bootstrap_accepts_matching_checksums():
    bootstrap = _load_bootstrap()
    honest = {
        version: bootstrap._sha256(path.read_text(encoding="utf-8"))
        for version, path in bootstrap._governed_files()
    }
    bootstrap.verify_no_drift(honest)  # must not raise


def test_bootstrap_ignores_not_yet_applied_migrations():
    """A pending migration is not drift — it is simply pending."""
    bootstrap = _load_bootstrap()
    bootstrap.verify_no_drift({})


# ---- application-level state comparison -----------------------------------


def test_missing_drifted_and_unknown_are_reported_separately():
    expected = {"0000_schema": None, "0001_x": "bbb", "0002_y": "ccc"}
    state = MigrationState(
        expected=expected,
        applied={"0000_schema": "WHATEVER", "0002_y": "WRONG", "0009_future": "ddd"},
    )
    assert state.missing == ["0001_x"]
    # The baseline is exempt even with a completely different checksum.
    assert state.drifted == ["0002_y"]
    assert state.unknown == ["0009_future"]
    assert not state.is_clean


def test_clean_state_is_clean():
    assert MigrationState(
        expected={"0000_schema": None, "0001_x": "aaa"},
        applied={"0000_schema": "anything", "0001_x": "aaa"},
    ).is_clean


# ---- against the real database --------------------------------------------


def test_real_database_matches_the_governed_migration_set(database_url):
    """The CI database is bootstrapped by db/bootstrap.py, so the app-level
    check must find it clean. If this fails, either the bootstrap or the
    checker is wrong — which is exactly what it exists to catch."""
    with engine.connect() as conn:
        state = verify_migration_state(conn)
    assert state.applied
    assert BASELINE_VERSION in state.applied


def test_applied_migrations_reads_recorded_checksums(database_url):
    with engine.connect() as conn:
        applied = applied_migrations(conn)
    assert applied
    for version, checksum in applied.items():
        assert isinstance(version, str) and isinstance(checksum, str)
        assert len(checksum) == 64, version


def test_drift_against_the_real_database_is_detected(database_url):
    """Simulate an edited migration by corrupting the recorded checksum inside a
    rolled-back transaction, then prove the app refuses the database."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        victim = sorted(v for v in expected_migrations() if v != BASELINE_VERSION)[-1]
        conn.execute(
            text(
                "UPDATE public.schema_migrations SET checksum = :bad "
                "WHERE version = :v"
            ),
            {"bad": "0" * 64, "v": victim},
        )
        state = inspect_migration_state(conn)
        assert victim in state.drifted
        with pytest.raises(MigrationStateError) as exc:
            verify_migration_state(conn)
        assert "checksum drift" in str(exc.value)
        assert "bootstrap.py" in str(exc.value)
    finally:
        trans.rollback()
        conn.close()


def test_unapplied_migration_is_detected_against_the_real_database(database_url):
    """Delete a migration record inside a rolled-back transaction: the app must
    refuse to treat the database as migrated."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        victim = sorted(set(expected_migrations()) - {BASELINE_VERSION})[-1]
        conn.execute(
            text("DELETE FROM public.schema_migrations WHERE version = :v"),
            {"v": victim},
        )
        state = inspect_migration_state(conn)
        assert victim in state.missing
        with pytest.raises(MigrationStateError):
            verify_migration_state(conn)
    finally:
        trans.rollback()
        conn.close()


def test_missing_tracking_table_is_an_explicit_error(database_url):
    """A database that was never bootstrapped must be named as such, not
    produce a confusing SQL error deep in a request."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        conn.execute(text("DROP TABLE public.schema_migrations"))
        with pytest.raises(MigrationStateError) as exc:
            applied_migrations(conn)
        assert "never been initialised" in str(exc.value)
    finally:
        trans.rollback()
        conn.close()
