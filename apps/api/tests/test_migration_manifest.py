"""Bundled migration manifest — the Vercel (Root Directory=apps/api) fix.

Some deployments bundle only the `apps/api` tree at runtime, so the canonical
repo-root `db/schema.sql` and `db/migrations/` that `expected_migrations()`
normally reads are not reachable. `app/db/migration_manifest.py` is a small,
generated, checked-in fallback (`db/generate_migration_manifest.py`) that
`expected_migrations()` uses when the canonical files are absent.

These tests prove three things:

1. the bundled manifest is never allowed to drift from the canonical files
   (it is never an independent source of truth — CI fails on drift);
2. the fallback actually engages, with baseline/forward-migration semantics
   preserved, when the canonical files are unavailable;
3. strict verification still fails loudly when NEITHER the canonical files
   NOR the bundled manifest are available — the fallback narrows what "the
   governed files are unreachable" means, it does not weaken R9.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import migration_manifest
from app.db.migration_state import (
    BASELINE_VERSION,
    MigrationStateError,
    expected_migrations,
    sha256_text,
)
from app.db.session import engine

REPO_ROOT = Path(__file__).resolve().parents[3]


class _StrictSettings:
    """Minimal stand-in for `Settings` — only the two attributes
    `enforce_migration_state_at_startup` actually reads."""

    is_strict = True
    app_env = "production"


class _SameConnectionEngine:
    """Lets `enforce_migration_state_at_startup(engine)` run against a
    connection/transaction the test already controls, so an uncommitted
    mutation is visible to it and nothing lasting touches the real database."""

    def __init__(self, connection):
        self._connection = connection

    def connect(self):
        return self

    def __enter__(self):
        return self._connection

    def __exit__(self, *exc_info):
        return False


def _canonical_expected() -> dict[str, str | None]:
    """Recompute straight from the canonical files, bypassing any fallback."""
    schema = REPO_ROOT / "db" / "schema.sql"
    root = REPO_ROOT / "db" / "migrations"
    expected: dict[str, str | None] = {BASELINE_VERSION: None}
    for path in sorted(root.glob("*.sql")):
        expected[path.stem] = sha256_text(path.read_text(encoding="utf-8"))
    assert schema.is_file()  # sanity: we are actually reading the real thing
    return expected


# ---- the manifest must never be an independent source of truth ------------


def test_bundled_manifest_matches_canonical_migrations():
    """The drift gate. Editing db/migrations/ without regenerating the bundled
    manifest (`uv run db/generate_migration_manifest.py`) must fail CI."""
    canonical = _canonical_expected()
    bundled: dict[str, str | None] = {migration_manifest.BASELINE_VERSION: None}
    bundled.update(migration_manifest.MIGRATIONS)
    assert canonical == bundled


def test_bundled_baseline_version_matches():
    assert migration_manifest.BASELINE_VERSION == BASELINE_VERSION


def test_bundled_manifest_has_no_baseline_entry_in_migrations_dict():
    """The baseline must stay presence-only through the fallback too — it must
    never appear inside MIGRATIONS with a real (checksum-comparable) value."""
    assert BASELINE_VERSION not in migration_manifest.MIGRATIONS


# ---- the fallback actually engages when canonical files are unreachable ---


def test_expected_migrations_falls_back_to_bundled_manifest(monkeypatch):
    """Simulate Vercel: repo-root db/schema.sql and db/migrations/ absent."""
    import app.db.migration_state as migration_state

    missing_root = REPO_ROOT / "nowhere" / "migrations"
    missing_schema = REPO_ROOT / "nowhere" / "schema.sql"
    monkeypatch.setattr(migration_state, "migrations_root", lambda: missing_root)
    monkeypatch.setattr(migration_state, "schema_file", lambda: missing_schema)

    result = expected_migrations()

    expected: dict[str, str | None] = {migration_manifest.BASELINE_VERSION: None}
    expected.update(migration_manifest.MIGRATIONS)
    assert result == expected


def test_fallback_preserves_baseline_presence_only_semantics(monkeypatch):
    """Same guarantee as `test_baseline_checksum_is_exempt_on_both_sides`, but
    for the fallback path: the baseline must still map to None, never a real
    checksum, so it stays exempt from drift comparison."""
    import app.db.migration_state as migration_state

    monkeypatch.setattr(
        migration_state, "migrations_root", lambda: REPO_ROOT / "nowhere"
    )
    monkeypatch.setattr(
        migration_state, "schema_file", lambda: REPO_ROOT / "nowhere" / "schema.sql"
    )

    result = expected_migrations()
    assert result[BASELINE_VERSION] is None


def test_canonical_files_are_preferred_over_the_bundled_manifest():
    """Repository/local execution must keep reading the canonical files
    directly — the manifest is a fallback, not a replacement."""
    assert expected_migrations() == _canonical_expected()


# ---- both unavailable must still fail loudly (R9 is not weakened) ---------


def test_raises_when_neither_canonical_files_nor_manifest_are_available(
    monkeypatch,
):
    import app.db.migration_state as migration_state

    monkeypatch.setattr(
        migration_state, "migrations_root", lambda: REPO_ROOT / "nowhere"
    )
    monkeypatch.setattr(
        migration_state, "schema_file", lambda: REPO_ROOT / "nowhere" / "schema.sql"
    )
    monkeypatch.setattr(migration_state, "_bundled_manifest", lambda: None)

    with pytest.raises(MigrationStateError) as exc:
        expected_migrations()
    message = str(exc.value)
    assert "cannot verify migration state" in message
    assert "migration_manifest.py" in message


# ---- end-to-end through enforce_migration_state_at_startup -----------------
#
# Everything above proves `expected_migrations()` in isolation. These prove
# the acceptance criteria against the real startup entry point: a strict
# environment, the canonical repo-root files hidden (as on Vercel with Root
# Directory=apps/api), and the bundled manifest doing the verifying.


def test_strict_startup_succeeds_via_bundled_manifest_when_canonical_unavailable(
    monkeypatch, database_url
):
    """Acceptance #3. Nothing is mutated: the real CI/dev database is already
    clean, so this runs directly against `engine` — no rollback needed."""
    import app.db.migration_state as migration_state

    monkeypatch.setattr(
        migration_state, "migrations_root", lambda: REPO_ROOT / "nowhere"
    )
    monkeypatch.setattr(
        migration_state, "schema_file", lambda: REPO_ROOT / "nowhere" / "schema.sql"
    )
    monkeypatch.setattr(migration_state, "get_settings", _StrictSettings)

    state = migration_state.enforce_migration_state_at_startup(engine)
    assert state is not None
    assert state.is_clean


def test_strict_startup_still_fails_on_missing_migration_via_the_fallback(
    monkeypatch, database_url
):
    """Acceptance #4. The fallback must not weaken R9: a database missing a
    governed migration must still refuse strict startup, exactly as it would
    reading the canonical files directly."""
    import app.db.migration_state as migration_state

    monkeypatch.setattr(
        migration_state, "migrations_root", lambda: REPO_ROOT / "nowhere"
    )
    monkeypatch.setattr(
        migration_state, "schema_file", lambda: REPO_ROOT / "nowhere" / "schema.sql"
    )
    monkeypatch.setattr(migration_state, "get_settings", _StrictSettings)

    conn = engine.connect()
    trans = conn.begin()
    try:
        victim = sorted(migration_manifest.MIGRATIONS)[-1]
        conn.execute(
            text("DELETE FROM public.schema_migrations WHERE version = :v"),
            {"v": victim},
        )
        with pytest.raises(migration_state.MigrationStateError) as exc:
            migration_state.enforce_migration_state_at_startup(
                _SameConnectionEngine(conn)
            )
        assert victim in str(exc.value)
    finally:
        trans.rollback()
        conn.close()


def test_strict_startup_still_fails_on_drift_via_the_fallback(monkeypatch, database_url):
    """Same guarantee as the missing-migration case, for a corrupted checksum
    instead of a missing row."""
    import app.db.migration_state as migration_state

    monkeypatch.setattr(
        migration_state, "migrations_root", lambda: REPO_ROOT / "nowhere"
    )
    monkeypatch.setattr(
        migration_state, "schema_file", lambda: REPO_ROOT / "nowhere" / "schema.sql"
    )
    monkeypatch.setattr(migration_state, "get_settings", _StrictSettings)

    conn = engine.connect()
    trans = conn.begin()
    try:
        victim = sorted(migration_manifest.MIGRATIONS)[-1]
        conn.execute(
            text(
                "UPDATE public.schema_migrations SET checksum = :bad "
                "WHERE version = :v"
            ),
            {"bad": "0" * 64, "v": victim},
        )
        with pytest.raises(migration_state.MigrationStateError) as exc:
            migration_state.enforce_migration_state_at_startup(
                _SameConnectionEngine(conn)
            )
        assert "checksum drift" in str(exc.value)
    finally:
        trans.rollback()
        conn.close()


def test_database_ahead_stays_non_blocking_via_the_fallback(monkeypatch, database_url):
    """Acceptance #5. L7 rollback compatibility must survive the fallback: a
    database record this build doesn't know about must not block startup."""
    import app.db.migration_state as migration_state

    monkeypatch.setattr(
        migration_state, "migrations_root", lambda: REPO_ROOT / "nowhere"
    )
    monkeypatch.setattr(
        migration_state, "schema_file", lambda: REPO_ROOT / "nowhere" / "schema.sql"
    )
    monkeypatch.setattr(migration_state, "get_settings", _StrictSettings)

    conn = engine.connect()
    trans = conn.begin()
    try:
        conn.execute(
            text(
                "INSERT INTO public.schema_migrations (version, checksum) "
                "VALUES (:v, :c)"
            ),
            {"v": "9999_from_a_newer_build", "c": "f" * 64},
        )
        state = migration_state.enforce_migration_state_at_startup(
            _SameConnectionEngine(conn)
        )
        assert state is not None
        assert "9999_from_a_newer_build" in state.ahead
        assert state.is_clean
    finally:
        trans.rollback()
        conn.close()
