"""Offer condition (migration 0024): NEW / USED / OPEN_BOX / REFURBISHED on both offer tables.

Pins the owner-approved semantics:

- migration 0024 upgrades a pre-0024 database onto db/schema.sql, defaults every existing row to
  NEW, refuses to default a row whose own text says it is used, and is idempotent;
- a NEW and a USED offer of the same robot x variant x provider x region x transaction COEXIST
  (pricing and availability), while a true duplicate (same condition) is still rejected;
- the API returns `condition`, and a used offer never promotes the new unit's availability or
  replaces its headline price.
"""
from __future__ import annotations

import pathlib
import re
import uuid

import psycopg
import pytest
from sqlalchemy import text
from test_identity_decision_migration import INSPECT, _shape, scratch_db  # noqa: F401

from app.db.session import SessionLocal, engine
from app.services.agent_tools import search_robots

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "db" / "schema.sql"
M0024 = ROOT / "db" / "migrations" / "0024_offer_condition.sql"


def pre_0024_schema() -> str:
    s = SCHEMA_SQL.read_text(encoding="utf-8")
    s, n = re.subn(r"-- Condition of the unit an offer is for\..*?\);\n\n", "", s,
                   count=1, flags=re.S)
    assert n == 1
    s, n = re.subn(r"(?:    --[^\n]*\n)+    condition +offer_condition NOT NULL DEFAULT 'NEW',\n",
                   "", s)
    assert n == 1                                    # pricing_offer (a CHECK follows it)
    s, n = re.subn(r",\n(?:    --[^\n]*\n)+    condition +offer_condition NOT NULL DEFAULT 'NEW'\n",
                   "\n", s)
    assert n == 1                                    # availability_offer (last column)
    s = s.replace("    transaction_type,\n    condition\n) WHERE is_current;",
                  "    transaction_type\n) WHERE is_current;")
    s = s.replace(" AND a.condition = 'NEW'", "")
    s = re.sub(r"      AND po\.condition = a\.condition[^\n]*\n", "", s)
    assert "offer_condition" not in s
    return s


def _seed_old(conn) -> None:
    conn.execute("""
        INSERT INTO manufacturer (slug, name) VALUES ('m-0024', 'Maker 0024');
        INSERT INTO robot (slug, manufacturer_id, name)
            SELECT 'r-0024', id, 'R 0024' FROM manufacturer WHERE slug = 'm-0024';
        INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency, price)
            SELECT id, 'PURCHASE', 'PUBLIC', 'EUR', 1000 FROM robot WHERE slug = 'r-0024';
        INSERT INTO availability_offer (robot_id, transaction_type, availability_status)
            SELECT id, 'PURCHASE', 'AVAILABLE' FROM robot WHERE slug = 'r-0024';
    """)


def test_upgrade_converges_defaults_existing_rows_to_new_and_is_idempotent(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        baseline = _shape(conn)
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute("DROP SCHEMA humanoid CASCADE")
        conn.execute(pre_0024_schema())
        conn.execute("SET search_path TO humanoid, public")
        _seed_old(conn)
        conn.execute(M0024.read_text(encoding="utf-8"))
        conn.execute(M0024.read_text(encoding="utf-8"))          # idempotent
        assert conn.execute("SELECT DISTINCT condition::text FROM pricing_offer").fetchall() \
            == [("NEW",)]
        assert conn.execute("SELECT DISTINCT condition::text FROM availability_offer"
                            ).fetchall() == [("NEW",)]
        upgraded = _shape(conn)
    for key in INSPECT:
        assert upgraded[key] == baseline[key], f"0024 and schema.sql disagree on {key}"


@pytest.mark.parametrize("table,sql", [
    ("pricing_offer", "UPDATE pricing_offer SET note = 'Refurbished unit, bazaar'"),
    ("availability_offer", "UPDATE availability_offer SET seller_wording = 'Used, 1 pc in stock'"),
])
def test_migration_refuses_to_default_a_row_that_says_it_is_used(scratch_db, table, sql):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(pre_0024_schema())
        conn.execute("SET search_path TO humanoid, public")
        _seed_old(conn)
        conn.execute(sql)
        with pytest.raises(psycopg.errors.RaiseException, match="refusing to default"):
            conn.execute(M0024.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- DB + API ----


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


@pytest.fixture
def robot_with_provider(database_url):
    mfr = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
    slug = f"cond-probe-{uuid.uuid4().hex[:10]}"
    rid = _exec("INSERT INTO robot (slug, manufacturer_id, name, is_published) "
                "VALUES (:s, :m, :n, TRUE) RETURNING id", s=slug, m=mfr, n=slug.upper()
                ).scalar_one()
    pslug = f"cond-prov-{uuid.uuid4().hex[:8]}"
    pid = _exec("INSERT INTO provider (slug, type, name) VALUES (:s, 'DISTRIBUTOR', 'P') "
                "RETURNING id", s=pslug).scalar_one()
    yield slug, rid, pid
    _exec("DELETE FROM robot WHERE id = :i", i=rid)
    _exec("DELETE FROM provider WHERE id = :i", i=pid)


def _price(rid, pid, condition, amount):
    _exec("INSERT INTO pricing_offer (robot_id, provider_id, transaction_type, price_type,"
          " currency, price, condition) VALUES (:r, :p, 'PURCHASE', 'PUBLIC', 'CZK', :a,"
          " CAST(:c AS offer_condition))", r=rid, p=pid, a=amount, c=condition)


def _avail(rid, pid, condition, status):
    _exec("INSERT INTO availability_offer (robot_id, provider_id, transaction_type,"
          " availability_status, condition) VALUES (:r, :p, 'PURCHASE',"
          " CAST(:s AS availability_status), CAST(:c AS offer_condition))",
          r=rid, p=pid, s=status, c=condition)


def test_new_and_used_offers_coexist_and_true_duplicates_are_rejected(robot_with_provider):
    _, rid, pid = robot_with_provider
    _price(rid, pid, "NEW", 900000)
    _price(rid, pid, "USED", 500000)
    _avail(rid, pid, "NEW", "NOT_AVAILABLE")
    _avail(rid, pid, "USED", "AVAILABLE")
    _avail(rid, pid, "REFURBISHED", "LIMITED")
    assert _exec("SELECT count(*) FROM availability_offer WHERE robot_id=:r", r=rid
                 ).scalar_one() == 3
    with pytest.raises(Exception, match="uq_availability_logical"):
        _avail(rid, pid, "USED", "LIMITED")                  # same logical offer again
    with pytest.raises(Exception, match="uq_availability_logical"):
        _avail(rid, pid, "NEW", "AVAILABLE")


def test_condition_defaults_to_new_when_a_legacy_writer_omits_it(robot_with_provider):
    _, rid, pid = robot_with_provider
    _exec("INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency, price)"
          " VALUES (:r, 'PURCHASE', 'PUBLIC', 'EUR', 1)", r=rid)
    _exec("INSERT INTO availability_offer (robot_id, transaction_type) VALUES (:r, 'PURCHASE')",
          r=rid)
    assert _exec("SELECT condition::text FROM pricing_offer WHERE robot_id=:r", r=rid
                 ).scalar_one() == "NEW"
    assert _exec("SELECT condition::text FROM availability_offer WHERE robot_id=:r", r=rid
                 ).scalar_one() == "NEW"


def test_api_returns_condition_and_used_never_promotes_new(robot_with_provider, client):
    slug, rid, pid = robot_with_provider
    _price(rid, pid, "NEW", 900000)
    _price(rid, pid, "USED", 500000)
    _avail(rid, pid, "NEW", "NOT_AVAILABLE")
    _avail(rid, pid, "USED", "AVAILABLE")
    body = client.get(f"/api/robots/{slug}").json()
    prices = {(p["condition"], p["price"]) for p in body["pricing_offers"]}
    assert prices == {("NEW", 900000.0), ("USED", 500000.0)}
    avail = {(a["condition"], a["availability_status"]) for a in body["availability_offers"]}
    assert avail == {("NEW", "NOT_AVAILABLE"), ("USED", "AVAILABLE")}
    # the commercial snapshot (DB view) and the availability filter only count NEW stock
    assert _exec("SELECT is_obtainable FROM robot_commercial_snapshot WHERE id=:r", r=rid
                 ).scalar_one() is False
    with SessionLocal() as s:
        available = {i.slug for i in search_robots(s, limit=100,
                                                   availability_status=["AVAILABLE"]).items}
    assert slug not in available


def _headline(slug):
    """The headline the listing cards show: the same selector the list endpoint uses, looked up
    by slug (not by full-text search, which mis-parses an all-digit random suffix)."""
    from app.models.robot import Robot
    from app.services.reads import price_display_for
    with SessionLocal() as s:
        robot = s.query(Robot).filter_by(slug=slug).one()
        return price_display_for(robot)


def test_used_price_never_becomes_the_headline_price(robot_with_provider, client):
    slug, rid, pid = robot_with_provider
    _price(rid, pid, "USED", 100)                    # cheaper, but used
    body = client.get(f"/api/robots/{slug}").json()
    assert [p["condition"] for p in body["pricing_offers"]] == ["USED"]
    assert _headline(slug) is None                   # no NEW price -> no headline
    _price(rid, pid, "NEW", 900000)
    assert _headline(slug).amount == 900000.0
