"""Migration 0016 (Stage F1 observation cadence + SCHEDULED trigger), throwaway DB.

- It converges a pre-0016 database onto db/schema.sql exactly (columns,
  constraints, triggers, indexes, and the crawl_trigger values).
- It is idempotent.
- Existing rows are untouched, and every existing source ends up NOT scheduled.
"""
from __future__ import annotations

import pathlib

import psycopg
from test_identity_decision_migration import INSPECT, _shape, scratch_db  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "db" / "schema.sql"
MIGRATION_0016 = ROOT / "db" / "migrations" / "0016_stage_f_observation.sql"
NEW_COLUMNS = ("observation_interval_hours", "observation_cadence_set_by",
               "observation_cadence_set_at")
TRIGGERS = "SELECT unnest(enum_range(NULL::humanoid.crawl_trigger))::text"


def _pre_0016(conn) -> None:
    """db/schema.sql as it was before 0016: one trigger value, no cadence columns."""
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    new_enum = "CREATE TYPE crawl_trigger AS ENUM ('MANUAL', 'SCHEDULED');"
    assert sql.count(new_enum) == 1
    conn.execute(sql.replace(new_enum, "CREATE TYPE crawl_trigger AS ENUM ('MANUAL');"))
    conn.execute("SET search_path TO humanoid, public")
    for column in NEW_COLUMNS:
        conn.execute(f"ALTER TABLE discovery_source DROP COLUMN {column}")  # drops the CHECK


def _fingerprints(conn) -> dict:
    out = {}
    for (table,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'humanoid' ORDER BY 1"):
        drop = "".join(f" - '{c}'" for c in NEW_COLUMNS) if table == "discovery_source" else ""
        out[table] = conn.execute(
            f"SELECT count(*), md5(coalesce(string_agg((to_jsonb(t){drop})::text, '|'"
            f" ORDER BY (to_jsonb(t){drop})::text), '')) FROM humanoid.{table} t").fetchone()
    return out


def test_0016_converges_onto_the_baseline(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        baseline = _shape(conn)
        baseline_triggers = conn.execute(TRIGGERS).fetchall()
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute("DROP SCHEMA humanoid CASCADE")
        _pre_0016(conn)
        assert conn.execute(TRIGGERS).fetchall() == [("MANUAL",)]
        conn.execute(MIGRATION_0016.read_text(encoding="utf-8"))
        upgraded = _shape(conn)
        assert conn.execute(TRIGGERS).fetchall() == baseline_triggers == [
            ("MANUAL",), ("SCHEDULED",)]
    for key in INSPECT:
        assert upgraded[key] == baseline[key], f"0016 and schema.sql disagree on {key}"


def test_0016_is_idempotent(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        sql = MIGRATION_0016.read_text(encoding="utf-8")
        conn.execute(sql)
        first = _shape(conn)
        conn.execute(sql)
        assert _shape(conn) == first


def test_0016_keeps_rows_and_schedules_nothing(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        _pre_0016(conn)
        conn.execute("""
            INSERT INTO discovery_source (key, name, source_class, homepage_url, is_enabled,
                                          tos_status, robots_status, eligibility_reviewed_at,
                                          eligibility_reviewed_by, allowed_path_prefixes)
                VALUES ('s-0016', 'Source 0016', 'MANUFACTURER', 'https://m.example/', true,
                        'ALLOWED', 'ALLOWED', now(), 'owner', ARRAY['/products']);
            INSERT INTO crawl_run (source_id, adapter_key, adapter_version, operator, status,
                                   finished_at)
                SELECT id, 'a', '1', 'robert', 'COMPLETED', now() FROM discovery_source;
        """)
        before = _fingerprints(conn)
        conn.execute(MIGRATION_0016.read_text(encoding="utf-8"))
        assert _fingerprints(conn) == before
        assert conn.execute(
            "SELECT count(*) FROM discovery_source WHERE observation_interval_hours IS NOT NULL"
        ).fetchone() == (0,)
        assert conn.execute("SELECT DISTINCT trigger::text FROM crawl_run").fetchall() == [
            ("MANUAL",)]
