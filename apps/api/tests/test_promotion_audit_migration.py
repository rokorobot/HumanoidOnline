"""Migration 0017 (promotion_audit append-only triggers) on a throwaway database.

- It converges a pre-0017 database onto db/schema.sql exactly (triggers and the two
  function definitions).
- It is idempotent.
- It leaves every existing audit row byte-for-byte unchanged, including rows whose
  reason text carries the historical "2026-10-03" wording, and the table's row count.
- After it, UPDATE and DELETE are refused and INSERT still works.
"""
from __future__ import annotations

import pathlib

import psycopg
import pytest
from test_identity_decision_migration import INSPECT, _shape, scratch_db  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "db" / "schema.sql"
MIGRATION_0017 = ROOT / "db" / "migrations" / "0017_promotion_audit_append_only.sql"
FUNCTIONS = ("refuse_promotion_audit_delete", "guard_promotion_audit_update")
TRIGGERS = ("trg_promotion_audit_no_update", "trg_promotion_audit_no_delete")


def _wind_back(conn) -> None:
    conn.execute("SET search_path TO humanoid, public")
    for trigger in TRIGGERS:
        conn.execute(f"DROP TRIGGER IF EXISTS {trigger} ON humanoid.promotion_audit")
    for function in FUNCTIONS:
        conn.execute(f"DROP FUNCTION IF EXISTS humanoid.{function}()")


def _functions(conn) -> list:
    return [conn.execute("SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                         "JOIN pg_namespace n ON n.oid = p.pronamespace "
                         "WHERE n.nspname = 'humanoid' AND p.proname = %s", (f,)).fetchone()
            for f in FUNCTIONS]


def _audit_fingerprint(conn):
    return conn.execute(
        "SELECT count(*), md5(coalesce(string_agg(a::text, '|' ORDER BY a::text), '')) "
        "FROM humanoid.promotion_audit a").fetchone()


def _populate(conn) -> None:
    """Candidates and audit rows as production has them, including the historical wording."""
    conn.execute("""
        INSERT INTO manufacturer (slug, name) VALUES ('m-0017', 'Maker 0017');
        INSERT INTO robot (slug, manufacturer_id, name)
            SELECT 'r-0017', id, 'R 0017' FROM manufacturer WHERE slug = 'm-0017';
        INSERT INTO discovery_source (key, name, source_class)
            VALUES ('s-0017', 'Source 0017', 'MANUFACTURER');
        INSERT INTO discovery_candidate (source_id, external_ref, candidate_name,
                                         candidate_manufacturer)
            SELECT id, 'ref-' || g, 'C-' || g, 'Maker 0017'
            FROM discovery_source, generate_series(1, 3) g WHERE key = 's-0017';
        INSERT INTO promotion_audit (candidate_id, action, approved_by, detail, promoted_robot_id)
            SELECT c.id, 'PROMOTED', 'robert', '{"fields": []}'::jsonb, r.id
            FROM discovery_candidate c, robot r
            WHERE c.external_ref = 'ref-1' AND r.slug = 'r-0017';
        INSERT INTO promotion_audit (candidate_id, action, approved_by, detail)
            SELECT id, 'REJECTED', 'robert',
                   '{"reason": "Owner scope decision 2026-10-03: out of scope", '
                   '"reason_code": "OUT_OF_SCOPE"}'::jsonb
            FROM discovery_candidate WHERE external_ref = 'ref-2';
    """)


def test_0017_converges_onto_the_baseline(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        baseline, functions = _shape(conn), _functions(conn)
        assert all(functions)
        _wind_back(conn)
        reduced = _shape(conn)
        assert len(reduced["triggers"]) == len(baseline["triggers"]) - 2
        conn.execute(MIGRATION_0017.read_text(encoding="utf-8"))
        upgraded, upgraded_functions = _shape(conn), _functions(conn)
    for key in INSPECT:
        assert upgraded[key] == baseline[key], f"0017 and schema.sql disagree on {key}"
    assert upgraded_functions == functions


def test_0017_is_idempotent(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        _wind_back(conn)
        sql = MIGRATION_0017.read_text(encoding="utf-8")
        conn.execute(sql)
        first = (_shape(conn), _functions(conn))
        conn.execute(sql)
        assert (_shape(conn), _functions(conn)) == first


def test_0017_leaves_existing_audit_rows_byte_identical_and_then_protects_them(
        scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        _wind_back(conn)
        conn.execute("SET search_path TO humanoid, public")
        _populate(conn)
        before = _audit_fingerprint(conn)
        assert before[0] == 2
        conn.execute(MIGRATION_0017.read_text(encoding="utf-8"))
        assert _audit_fingerprint(conn) == before          # count and every row, byte for byte
        assert conn.execute(
            "SELECT count(*) FROM promotion_audit WHERE detail::text LIKE '%2026-10-03%'"
        ).fetchone()[0] == 1                                # the historical wording is untouched

        for statement in ("UPDATE promotion_audit SET approved_by = 'x'",
                          "DELETE FROM promotion_audit"):
            with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"):
                conn.execute(statement)
        assert _audit_fingerprint(conn) == before

        conn.execute("INSERT INTO promotion_audit (candidate_id, action, approved_by) "
                     "SELECT id, 'NOTE', 'robert' FROM discovery_candidate "
                     "WHERE external_ref = 'ref-3'")
        assert conn.execute("SELECT count(*) FROM promotion_audit").fetchone()[0] == 3
