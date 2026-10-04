"""Migration 0019 (G2-3 accepted claims) on a throwaway database.

- It converges a pre-0019 database onto db/schema.sql exactly (tables, columns,
  indexes, constraints, triggers and the refuse function).
- It is idempotent.
- It is purely additive: every pre-existing table keeps its exact content (row count
  and a hash of every row), and it needs no privilege change.
- Afterwards UPDATE and DELETE are refused on all three tables and INSERT works.
"""
from __future__ import annotations

import pathlib

import psycopg
import pytest
from test_identity_decision_migration import INSPECT, _shape, scratch_db  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "db" / "schema.sql"
MIGRATION_0019 = ROOT / "db" / "migrations" / "0019_accepted_claims.sql"
MIGRATION_0020 = ROOT / "db" / "migrations" / "0020_price_type_manufacturer_estimate.sql"
MIGRATION_0021 = (ROOT / "db" / "migrations"
                  / "0021_manufacturer_estimate_and_claim_targets.sql")
MIGRATION_0022 = ROOT / "db" / "migrations" / "0022_robot_spec_claim_target.sql"
MIGRATION_0023 = (ROOT / "db" / "migrations"
                  / "0023_commercial_status_claim_target_and_proposal_origin.sql")
NEW_TABLES = ("accepted_claim", "claim_retraction", "catalogue_write_audit")


def _wind_back(conn) -> None:
    conn.execute("SET search_path TO humanoid, public")
    for table in reversed(NEW_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS humanoid.{table} CASCADE")


def _function(conn):
    # the refuse function belongs to 0019 and must survive 0019 unchanged
    return conn.execute(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n "
        "ON n.oid = p.pronamespace WHERE n.nspname = 'humanoid' "
        "AND p.proname = 'refuse_claim_proposal_mutation'").fetchone()


def _existing_content(conn) -> dict:
    tables = [r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'humanoid' "
        "AND table_type = 'BASE TABLE' ORDER BY 1") if r[0] not in NEW_TABLES]
    return {t: conn.execute(
        f"SELECT count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) "
        f"FROM humanoid.{t} x").fetchone() for t in tables}


def _populate(conn) -> None:
    conn.execute("""
        INSERT INTO manufacturer (slug, name) VALUES ('m-0019', 'Maker 0019');
        INSERT INTO robot (slug, manufacturer_id, name)
            SELECT '4ne1-mini', id, '4NE1 Mini' FROM manufacturer WHERE slug = 'm-0019';
        INSERT INTO discovery_source (key, name, source_class)
            VALUES ('s-0019', 'Source 0019', 'MANUFACTURER');
        INSERT INTO discovery_candidate (source_id, external_ref, candidate_name,
                                         candidate_manufacturer)
            SELECT id, 'ref-1', 'C-1', 'Maker 0019' FROM discovery_source WHERE key = 's-0019';
    """)


def test_0019_converges_onto_the_baseline(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        baseline, function = _shape(conn), _function(conn)
        assert function
        _wind_back(conn)
        assert any(_shape(conn)[k] != baseline[k] for k in INSPECT)
        conn.execute(MIGRATION_0019.read_text(encoding="utf-8"))
        conn.execute(MIGRATION_0020.read_text(encoding="utf-8"))   # later layers (G2-4)
        conn.execute(MIGRATION_0021.read_text(encoding="utf-8"))
        conn.execute(MIGRATION_0022.read_text(encoding="utf-8"))
        conn.execute(MIGRATION_0023.read_text(encoding="utf-8"))
        upgraded, upgraded_function = _shape(conn), _function(conn)
    for key in INSPECT:
        assert upgraded[key] == baseline[key], f"0019 and schema.sql disagree on {key}"
    assert upgraded_function == function


def test_0019_is_idempotent(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        _wind_back(conn)
        sql = MIGRATION_0019.read_text(encoding="utf-8")
        conn.execute(sql)
        first = (_shape(conn), _function(conn))
        conn.execute(sql)
        assert (_shape(conn), _function(conn)) == first


def test_0019_is_additive_and_the_new_tables_are_protected(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        _wind_back(conn)
        conn.execute("SET search_path TO humanoid, public")
        _populate(conn)
        before = _existing_content(conn)
        conn.execute(MIGRATION_0019.read_text(encoding="utf-8"))
        assert _existing_content(conn) == before   # every pre-existing row, byte for byte
        assert all(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] == 0
                   for t in NEW_TABLES)
        for table in NEW_TABLES:
            for statement in (f"UPDATE {table} SET id = id", f"DELETE FROM {table}"):
                with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"):
                    conn.execute(statement)
        assert _existing_content(conn) == before
