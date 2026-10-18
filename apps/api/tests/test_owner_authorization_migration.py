"""Migration 0025 (docs/28 A4 OWNER_AUTHORIZED access basis), throwaway database.

- It converges a pre-0025 database onto db/schema.sql exactly (columns,
  constraints, triggers, indexes).
- It is idempotent.
- Existing rows are untouched: on a database shaped like production on
  2026-10-18 (three enabled ToS-ALLOWED sources, six disabled UNKNOWN ones),
  every source keeps its state, gets SOURCE_PERMISSION, nothing is enabled and
  no owner authorization is invented.
"""
from __future__ import annotations

import pathlib

import psycopg
import pytest
from test_identity_decision_migration import INSPECT, _shape, scratch_db  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "db" / "schema.sql"
MIGRATION_0025 = ROOT / "db" / "migrations" / "0025_owner_authorized_source_access.sql"
NEW_COLUMNS = ("access_basis", "owner_authorized_by", "owner_authorized_at",
               "owner_authorization_reason", "owner_authorized_path_prefixes")
PRE_0025_ELIGIBLE = """
    ALTER TABLE discovery_source ADD CONSTRAINT ck_discovery_source_eligible CHECK (
        NOT is_enabled OR (
            tos_status = 'ALLOWED'
            AND robots_status IN ('ALLOWED', 'NOT_APPLICABLE')
            AND eligibility_reviewed_at IS NOT NULL
            AND eligibility_reviewed_by IS NOT NULL
        )
    )"""
#: The registry as read (read-only) from production on 2026-10-18.
PRODUCTION_SHAPE = """
    INSERT INTO discovery_source (key, name, source_class, homepage_url, is_enabled, tos_status,
                                  robots_status, eligibility_reviewed_at, eligibility_reviewed_by,
                                  allowed_path_prefixes, observation_interval_hours,
                                  observation_cadence_set_by, observation_cadence_set_at)
    VALUES
      ('neura-robotics-official', 'NEURA Robotics', 'MANUFACTURER', 'https://neura-robotics.com/',
       true, 'ALLOWED', 'ALLOWED', now(), 'robert@humanoid.company',
       ARRAY['/products/', '/product/', '/product-sitemap.xml', '/news/'], 48, 'Robert', now()),
      ('neura-documents-official', 'NEURA Robotics documents (px.media)', 'OFFICIAL_DOCUMENT',
       'https://neurarobotics.px.media/', true, 'ALLOWED', 'ALLOWED', now(), 'Robert',
       ARRAY['/plk/'], 168, 'Robert', now()),
      ('xpeng-official', 'XPENG', 'MANUFACTURER', 'https://www.xpeng.com/', true, 'ALLOWED',
       'ALLOWED', now(), 'Robert', ARRAY['/technology/ai_robot_iron', '/news/', '/au/news/'],
       120, 'Robert', now());
    INSERT INTO discovery_source (key, name, source_class, homepage_url, notes)
    VALUES ('unitree-robotics-official', 'Unitree Robotics', 'MANUFACTURER',
            'https://www.unitree.com/', '2026-10-18 owner instruction'),
           ('booster-robotics-official', 'Booster Robotics', 'MANUFACTURER',
            'https://www.booster.tech/', '2026-10-18 owner instruction'),
           ('agibot-official', 'AgiBot', 'MANUFACTURER', 'https://www.agibot.com/', NULL),
           ('agility-robotics-official', 'Agility Robotics', 'MANUFACTURER',
            'https://www.agilityrobotics.com/', NULL),
           ('figure-ai-official', 'Figure AI', 'MANUFACTURER', 'https://www.figure.ai/', NULL),
           ('alza-cz', 'Alza.cz', 'DISTRIBUTOR', 'https://www.alza.cz/', NULL);
"""


def _pre_0025(conn) -> None:
    """db/schema.sql as it was before 0025."""
    conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.execute("SET search_path TO humanoid, public")
    conn.execute("DROP TABLE discovery_source_owner_authorization_event")
    conn.execute("DROP FUNCTION refuse_source_owner_authorization_mutation()")
    for column in NEW_COLUMNS:  # drops the three CHECKs that read them
        conn.execute(f"ALTER TABLE discovery_source DROP COLUMN {column}")
    conn.execute(PRE_0025_ELIGIBLE)


def _fingerprints(conn) -> dict:
    out = {}
    for (table,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'humanoid' ORDER BY 1"):
        drop = "".join(f" - '{c}'" for c in NEW_COLUMNS) if table == "discovery_source" else ""
        out[table] = conn.execute(
            f"SELECT count(*), md5(coalesce(string_agg((to_jsonb(t){drop})::text, '|'"
            f" ORDER BY (to_jsonb(t){drop})::text), '')) FROM humanoid.{table} t").fetchone()
    return out


def test_0025_converges_onto_the_baseline(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        baseline = _shape(conn)
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute("DROP SCHEMA humanoid CASCADE")
        _pre_0025(conn)
        assert _shape(conn) != baseline
        conn.execute(MIGRATION_0025.read_text(encoding="utf-8"))
        upgraded = _shape(conn)
    for key in INSPECT:
        assert upgraded[key] == baseline[key], f"0025 and schema.sql disagree on {key}"


def test_0025_is_idempotent(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        sql = MIGRATION_0025.read_text(encoding="utf-8")
        conn.execute(sql)
        first = _shape(conn)
        conn.execute(sql)
        assert _shape(conn) == first


def test_0025_keeps_production_rows_and_authorizes_nothing(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        _pre_0025(conn)
        conn.execute(PRODUCTION_SHAPE)
        before = _fingerprints(conn)
        state = "SELECT key, is_enabled, tos_status::text FROM discovery_source ORDER BY key"
        state_before = conn.execute(state).fetchall()
        conn.execute(MIGRATION_0025.read_text(encoding="utf-8"))
        after = _fingerprints(conn)
        assert after.pop('discovery_source_owner_authorization_event')[0] == 0   # new, empty
        assert after == before
        assert conn.execute(state).fetchall() == state_before
        assert conn.execute(
            "SELECT DISTINCT access_basis, owner_authorized_by, owner_authorized_path_prefixes "
            "FROM discovery_source").fetchall() == [("SOURCE_PERMISSION", None, None)]
        assert conn.execute("SELECT key FROM discovery_source WHERE is_enabled ORDER BY key"
                            ).fetchall() == [("neura-documents-official",),
                                             ("neura-robotics-official",), ("xpeng-official",)]
        assert conn.execute("SELECT count(*) FROM discovery_source_owner_authorization_event"
                            ).fetchone() == (0,)
        # The six A4 sources cannot be enabled by the migration's new rule alone.
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("UPDATE discovery_source SET is_enabled = true "
                         "WHERE key = 'unitree-robotics-official'")
