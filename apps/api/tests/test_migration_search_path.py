"""Forward migrations must not depend on the applying role's name.

Migration 0013 failed in production with `relation "manufacturer" does not
exist`. It named its tables without a schema and set no `search_path`, so it
resolved them through the role's default `"$user", public`, which reaches the
`humanoid` schema only when the role is itself called `humanoid`. Local and CI
databases use exactly that role; production does not. Every earlier check passed.

A fresh bootstrap cannot catch this: `schema.sql` (the 0000 baseline) sets the
search path for the session, and every later migration then inherits it. So the
test reproduces the production shape: a scratch database at schema 0012 with the
baseline already recorded, and a separate role whose name differs from
`humanoid` and whose default search_path does not include it. That role applies
the pending migration through `db/bootstrap.py`, the production entry point.

A negative control first applies 0013 with its `SET search_path` line removed
and requires the original failure, so the test demonstrably detects the bug.

The scratch database and role are dropped afterwards; the shared database is
never modified.
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("bootstrap", REPO_ROOT / "db" / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bootstrap)

MIGRATION = "0013_manufacturer_profile_fields"
MIGRATION_FILE = REPO_ROOT / "db" / "migrations" / f"{MIGRATION}.sql"
SET_LINE = "SET search_path TO humanoid, public;"
ADDED_COLUMNS = {
    ("manufacturer", "headquarters_city"), ("manufacturer", "incorporation"),
    ("manufacturer", "operating_locations"), ("manufacturer", "parent_company"),
    ("manufacturer", "parent_listing"), ("manufacturer", "parent_relationship"),
    ("manufacturer", "deployment_note"), ("evidence_source", "claim_fields"),
    ("evidence_source", "managed_by"),
}

#: Undo 0013 on a freshly bootstrapped database, leaving the exact 0012 shape.
DOWNGRADE_TO_0012 = """
SET search_path TO humanoid, public;
ALTER TABLE manufacturer
    DROP COLUMN headquarters_city, DROP COLUMN incorporation,
    DROP COLUMN operating_locations, DROP COLUMN parent_company,
    DROP COLUMN parent_listing, DROP COLUMN parent_relationship,
    DROP COLUMN deployment_note;
ALTER TABLE evidence_source DROP COLUMN claim_fields, DROP COLUMN managed_by;
UPDATE manufacturer SET is_public_company = FALSE WHERE is_public_company IS NULL;
ALTER TABLE manufacturer ALTER COLUMN is_public_company SET DEFAULT FALSE;
ALTER TABLE manufacturer ALTER COLUMN is_public_company SET NOT NULL;
DELETE FROM public.schema_migrations WHERE version = '0013_manufacturer_profile_fields';
"""


def _conninfo(base: dict, **overrides) -> str:
    return make_conninfo(**{**base, **overrides})


@pytest.fixture
def scratch(database_url):
    """A scratch database at schema 0012 plus a non-`humanoid` migrator role."""
    base = conninfo_to_dict(bootstrap.normalize_url(database_url))
    admin_user = base.get("user")
    suffix = uuid.uuid4().hex[:10]
    db_name, role, password = f"migsp_{suffix}", f"migsp_owner_{suffix}", uuid.uuid4().hex

    with psycopg.connect(_conninfo(base), autocommit=True) as admin:
        can = admin.execute(
            "SELECT rolsuper OR (rolcreatedb AND rolcreaterole) FROM pg_roles "
            "WHERE rolname = current_user"
        ).fetchone()[0]
        if not can:
            pytest.skip("test role cannot create a scratch database and role")
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)))
        # Ownership rights over the baseline's objects, but not its name: exactly
        # what distinguishes the production role from the local `humanoid` one.
        admin.execute(sql.SQL("GRANT {} TO {}").format(
            sql.Identifier(admin_user), sql.Identifier(role)))
        # No role-level search_path: the server default `"$user", public` applies,
        # as it does for the production role.

    scratch_admin = _conninfo(base, dbname=db_name)
    try:
        bootstrap.run_migrations(scratch_admin)
        with psycopg.connect(scratch_admin, autocommit=True) as conn:
            conn.execute(DOWNGRADE_TO_0012)
        yield {
            "admin": scratch_admin,
            "migrator": _conninfo(base, dbname=db_name, user=role, password=password),
            "role": role,
        }
    finally:
        with psycopg.connect(_conninfo(base), autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (db_name,))
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def _state(conninfo: str) -> dict:
    with psycopg.connect(conninfo) as conn:
        columns = set(conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'humanoid' AND table_name IN ('manufacturer', 'evidence_source')"
        ).fetchall())
        public = conn.execute(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = 'humanoid' AND table_name = 'manufacturer' "
            "AND column_name = 'is_public_company'"
        ).fetchone()
        ledger = dict(conn.execute(
            "SELECT version, checksum FROM public.schema_migrations").fetchall())
    return {"columns": columns, "is_public_company": public, "ledger": ledger}


def test_scratch_database_reproduces_the_production_shape(scratch) -> None:
    with psycopg.connect(scratch["migrator"]) as conn:
        assert conn.execute("SELECT current_user").fetchone()[0] == scratch["role"]
        assert conn.execute("SHOW search_path").fetchone()[0] == '"$user", public'
        assert conn.execute("SELECT to_regclass('manufacturer')").fetchone()[0] is None
    state = _state(scratch["admin"])
    assert MIGRATION not in state["ledger"]
    assert "0012_owner_approved_display_basis" in state["ledger"]
    assert not ADDED_COLUMNS & state["columns"]
    assert state["is_public_company"] == ("NO", "false")


def test_migration_without_search_path_fails_for_that_role(scratch, tmp_path, monkeypatch) -> None:
    """Negative control: the unfixed file reproduces the production failure."""
    migrations = tmp_path / "migrations"
    shutil.copytree(REPO_ROOT / "db" / "migrations", migrations)
    unfixed = migrations / MIGRATION_FILE.name
    text = unfixed.read_text(encoding="utf-8")
    assert SET_LINE in text
    unfixed.write_text(text.replace(SET_LINE, ""), encoding="utf-8")
    monkeypatch.setattr(bootstrap, "MIGRATIONS_DIR", migrations)

    with pytest.raises(psycopg.errors.UndefinedTable, match="manufacturer"):
        bootstrap.run_migrations(scratch["migrator"])

    state = _state(scratch["admin"])
    assert MIGRATION not in state["ledger"]
    assert not ADDED_COLUMNS & state["columns"]


def test_bootstrap_applies_0013_as_a_role_not_named_humanoid(scratch) -> None:
    bootstrap.run_migrations(scratch["migrator"])

    state = _state(scratch["admin"])
    assert ADDED_COLUMNS <= state["columns"]
    assert state["is_public_company"] == ("YES", None)
    source = MIGRATION_FILE.read_text(encoding="utf-8")
    expected = hashlib.sha256(source.encode("utf-8")).hexdigest()
    assert state["ledger"][MIGRATION] == expected

    # Nothing left pending, no drift, and a re-run is a no-op for that role too.
    with psycopg.connect(scratch["migrator"], autocommit=True) as conn:
        assert bootstrap._pending(conn) == []
    bootstrap.run_migrations(scratch["migrator"])
    assert _state(scratch["admin"])["ledger"] == state["ledger"]
