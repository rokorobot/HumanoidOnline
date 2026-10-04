"""Migrations 0020 + 0021 (MANUFACTURER_ESTIMATE, G2-4) on a throwaway database.

A pre-G2-4 database (db/schema.sql with the new label, the widened price-shape CHECK and the
widened claim/audit CHECKs removed) is upgraded by the two migrations and must:

- converge onto db/schema.sql exactly (enum label and its order, constraints);
- keep every existing pricing row byte-for-byte (PUBLIC, ESTIMATED, ... keep their meaning);
- start accepting MANUFACTURER_ESTIMATE as a point price while refusing it without a number;
- be idempotent.
"""
from __future__ import annotations

import pathlib
import re

import psycopg
import pytest
from test_identity_decision_migration import INSPECT, _shape, scratch_db  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "db" / "schema.sql"
M0020 = ROOT / "db" / "migrations" / "0020_price_type_manufacturer_estimate.sql"
M0021 = ROOT / "db" / "migrations" / "0021_manufacturer_estimate_and_claim_targets.sql"
M0022 = ROOT / "db" / "migrations" / "0022_robot_spec_claim_target.sql"
M0023 = (ROOT / "db" / "migrations"
         / "0023_commercial_status_claim_target_and_proposal_origin.sql")


def pre_g24_schema() -> str:
    s = SCHEMA_SQL.read_text(encoding="utf-8")
    s, n = re.subn(r"    'MANUFACTURER_ESTIMATE',  --[^\n]*\n(?:    --[^\n]*\n)*", "", s, count=1)
    assert n == 1
    s = s.replace("('PUBLIC','FROM','ESTIMATED','MANUFACTURER_ESTIMATE')",
                  "('PUBLIC','FROM','ESTIMATED')")
    s = s.replace("CHECK (target_kind IN ('robot_variant', 'specification', 'pricing_offer',\n"
                  "                               'availability_offer', 'NO_CATALOGUE_HOME')),",
                  "CHECK (target_kind IN ('robot_variant', 'specification', 'NO_CATALOGUE_HOME')),")
    s = s.replace("CHECK (value_type IN ('TEXT', 'JSON')),", "CHECK (value_type IN ('TEXT')),")
    s = s.replace("CHECK (target_table IN ('robot_variant', 'specification', 'pricing_offer',\n"
                  "                                'availability_offer')),",
                  "CHECK (target_table IN ('robot_variant', 'specification')),")
    s = s.replace("(PUBLIC/FROM/ESTIMATED/MANUFACTURER_ESTIMATE)", "(PUBLIC/FROM/ESTIMATED)")
    assert "MANUFACTURER_ESTIMATE" not in s
    return s


def _labels(conn):
    return [r[0] for r in conn.execute(
        "SELECT unnest(enum_range(NULL::humanoid.price_type))::text")]


def _offers(conn):
    return conn.execute("SELECT count(*), md5(coalesce(string_agg(p::text, '|' "
                        "ORDER BY p::text), '')) FROM humanoid.pricing_offer p").fetchone()


def _populate(conn) -> None:
    conn.execute("""
        INSERT INTO manufacturer (slug, name) VALUES ('m-0020', 'Maker 0020');
        INSERT INTO robot (slug, manufacturer_id, name)
            SELECT 'r-0020', id, 'R 0020' FROM manufacturer WHERE slug = 'm-0020';
        INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency, price)
            SELECT r.id, 'PURCHASE', t, 'USD', 1000
            FROM robot r, unnest(ARRAY['PUBLIC','ESTIMATED','FROM']::price_type[]) t
            WHERE r.slug = 'r-0020';
        INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency,
                                   price_min, price_max)
            SELECT id, 'PURCHASE', 'RANGE', 'USD', 1, 2 FROM robot WHERE slug = 'r-0020';
        INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency)
            SELECT id, 'RENTAL', 'QUOTE_ONLY', 'USD' FROM robot WHERE slug = 'r-0020';
    """)


def test_upgrade_converges_onto_the_baseline_and_keeps_existing_rows(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        baseline = _shape(conn)
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute("DROP SCHEMA humanoid CASCADE")
        conn.execute(pre_g24_schema())
        assert "MANUFACTURER_ESTIMATE" not in _labels(conn)
        conn.execute("SET search_path TO humanoid, public")
        _populate(conn)
        before = _offers(conn)
        with pytest.raises(psycopg.errors.InvalidTextRepresentation):
            conn.execute("INSERT INTO pricing_offer (robot_id, transaction_type, price_type, "
                         "currency, price) SELECT id, 'PURCHASE', 'MANUFACTURER_ESTIMATE', "
                         "'EUR', 1 FROM robot")
        conn.execute(M0020.read_text(encoding="utf-8"))
        conn.execute(M0021.read_text(encoding="utf-8"))
        conn.execute(M0022.read_text(encoding="utf-8"))
        conn.execute(M0023.read_text(encoding="utf-8"))
        upgraded = _shape(conn)
        assert _labels(conn) == ["PUBLIC", "ESTIMATED", "MANUFACTURER_ESTIMATE", "QUOTE_ONLY",
                                 "FROM", "RANGE"]
        assert _offers(conn) == before                      # every existing row identical
    for key in INSPECT:
        assert upgraded[key] == baseline[key], f"0020/0021 and schema.sql disagree on {key}"


def test_the_new_type_is_a_point_price_and_old_semantics_are_unchanged(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(pre_g24_schema())
        conn.execute("SET search_path TO humanoid, public")
        _populate(conn)
        conn.execute(M0020.read_text(encoding="utf-8"))
        conn.execute(M0021.read_text(encoding="utf-8"))
        ok = ("INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency, "
              "price%s) SELECT id, 'PURCHASE', 'MANUFACTURER_ESTIMATE', 'EUR', %s%s FROM robot "
              "WHERE slug = 'r-0020'")
        conn.execute(ok % ("", "19999", ""))
        for bad in (
            "INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency) "
            "SELECT id, 'PURCHASE', 'MANUFACTURER_ESTIMATE', 'EUR' FROM robot",
            ok % (", price_min, price_max", "1", ", 1, 2"),
            "INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency, "
            "price) SELECT id, 'PURCHASE', 'QUOTE_ONLY', 'EUR', 5 FROM robot",
        ):
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(bad)


def test_both_migrations_are_idempotent(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(pre_g24_schema())
        for _ in range(2):
            conn.execute(M0020.read_text(encoding="utf-8"))
            conn.execute(M0021.read_text(encoding="utf-8"))
        first = _shape(conn)
        conn.execute(M0020.read_text(encoding="utf-8"))
        conn.execute(M0021.read_text(encoding="utf-8"))
        assert _shape(conn) == first
        assert _labels(conn).count("MANUFACTURER_ESTIMATE") == 1
