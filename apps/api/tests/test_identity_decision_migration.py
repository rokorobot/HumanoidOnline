"""Migration 0015 (Stage E candidate_identity_decision) on a throwaway database.

- It converges a pre-0015 database onto db/schema.sql exactly (columns,
  constraints, triggers).
- It is idempotent.
- It leaves every existing table's rows untouched, proven with row counts and
  content hashes taken before and after on a populated database.
"""
from __future__ import annotations

import pathlib
import uuid

import psycopg
import pytest
from sqlalchemy import make_url

from app.config import get_settings

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "db" / "schema.sql"
MIGRATION_0015 = ROOT / "db" / "migrations" / "0015_candidate_identity_decision.sql"

INSPECT = {
    "columns": """SELECT table_name, column_name, data_type, udt_name, is_nullable,
                         is_identity, identity_generation
                  FROM information_schema.columns WHERE table_schema = 'humanoid'
                  ORDER BY table_name, column_name""",
    "constraints": """SELECT rel.relname, c.conname, c.contype, pg_get_constraintdef(c.oid)
                      FROM pg_constraint c JOIN pg_class rel ON rel.oid = c.conrelid
                      JOIN pg_namespace n ON n.oid = rel.relnamespace
                      WHERE n.nspname = 'humanoid' ORDER BY 1, 2""",
    "triggers": """SELECT tgname, tgrelid::regclass::text FROM pg_trigger
                   WHERE NOT tgisinternal ORDER BY 1""",
    "indexes": """SELECT indexname, indexdef FROM pg_indexes
                  WHERE schemaname = 'humanoid' ORDER BY 1""",
}


def _dsn(url) -> str:
    return url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture
def scratch_db(database_url):
    url = make_url(get_settings().resolved_database_url)
    admin = _dsn(url.set(database="postgres"))
    name = f"stage_e_upgrade_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        yield _dsn(url.set(database=name))
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                         " WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _shape(conn) -> dict:
    return {k: conn.execute(q).fetchall() for k, q in INSPECT.items()}


def _wind_back(conn) -> None:
    conn.execute("SET search_path TO humanoid, public")
    conn.execute("DROP TABLE IF EXISTS humanoid.candidate_identity_decision CASCADE")
    conn.execute("DROP FUNCTION IF EXISTS humanoid.refuse_identity_decision_mutation()")
    conn.execute("DROP TYPE IF EXISTS humanoid.candidate_identity_decision_kind")


def _table_fingerprints(conn) -> dict:
    tables = [r[0] for r in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'humanoid' ORDER BY 1")]
    out = {}
    for table in tables:
        out[table] = conn.execute(
            f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), ''))"
            f" FROM humanoid.{table} t").fetchone()
    return out


def test_0015_converges_onto_the_baseline(scratch_db):
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        baseline = _shape(conn)
        _wind_back(conn)
        reduced = _shape(conn)
        assert len(reduced["columns"]) < len(baseline["columns"])
        conn.execute(MIGRATION_0015.read_text(encoding="utf-8"))
        upgraded = _shape(conn)
    for key in INSPECT:
        assert upgraded[key] == baseline[key], f"0015 and schema.sql disagree on {key}"


def test_0015_is_idempotent(scratch_db):
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        sql = MIGRATION_0015.read_text(encoding="utf-8")
        conn.execute(sql)
        first = _shape(conn)
        conn.execute(sql)
        assert _shape(conn) == first


def test_0015_leaves_existing_rows_unchanged(scratch_db):
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        _wind_back(conn)
        conn.execute("""
            INSERT INTO manufacturer (slug, name) VALUES ('m-0015', 'Maker 0015');
            INSERT INTO discovery_source (key, name, source_class)
                VALUES ('s-0015', 'Source 0015', 'MANUFACTURER');
            INSERT INTO discovery_candidate (source_id, external_ref, candidate_name,
                                             candidate_manufacturer)
                SELECT id, 'ref-' || g, 'EX-' || g, 'Maker 0015'
                FROM discovery_source, generate_series(1, 3) g WHERE key = 's-0015';
        """)
        before = _table_fingerprints(conn)
        assert before["discovery_candidate"][0] == 3
        conn.execute(MIGRATION_0015.read_text(encoding="utf-8"))
        after = _table_fingerprints(conn)
    assert after.pop("candidate_identity_decision") == (0, "d41d8cd98f00b204e9800998ecf8427e")
    assert after == before
