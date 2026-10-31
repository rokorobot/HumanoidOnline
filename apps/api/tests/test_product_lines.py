"""Product lines (DR-L1 PR a): importer validation and the read API. DB-backed.

The whole repository catalogue is imported into a throwaway database with the real importer
and the API is pointed at it, as in test_use_case_assessment_api.py.
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.session import get_session
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]
LINES = json.loads(
    (REPO_ROOT / "db" / "catalogue" / "product_lines.json").read_text(encoding="utf-8")
)
EXPECTED = {ln["slug"]: ln["robots"] for ln in LINES["product_lines"]}


def _importer():
    spec = importlib.util.spec_from_file_location(
        "import_catalogue", REPO_ROOT / "db" / "import_catalogue.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["import_catalogue"] = mod
    spec.loader.exec_module(mod)
    return mod


def _libpq(url) -> str:
    return url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )


@pytest.fixture(scope="module")
def env(database_url):
    """(TestClient, libpq dsn, importer, first-run reconciliation, second-run reconciliation)."""
    settings = get_settings()
    url = make_url(settings.resolved_database_url)
    admin = _libpq(url.set(database="postgres"))
    name = f"ho_dr_l1_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    scratch = url.set(database=name)
    engine = None
    try:
        dsn = _libpq(scratch)
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute((REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        ic = _importer()
        with contextlib.redirect_stdout(io.StringIO()):
            first = ic.run(dsn)
            second = ic.run(dsn)

        engine = create_engine(
            scratch.set(drivername="postgresql+psycopg"),
            connect_args={"options": f"-csearch_path={settings.db_schema},public"},
        )
        factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

        def scratch_session():
            with factory() as session:
                yield session

        app.dependency_overrides[get_session] = scratch_session
        from fastapi.testclient import TestClient

        yield TestClient(app), dsn, ic, first, second
    finally:
        app.dependency_overrides.pop(get_session, None)
        if engine is not None:
            engine.dispose()
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                         " WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _sql(dsn: str, query: str, params=()):
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET search_path TO humanoid, public")
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else None


# --- importer ---------------------------------------------------------------

def test_import_sets_lines_and_membership(env):
    _, dsn, *_ = env
    assert len(EXPECTED) == 5
    stored = {}
    for line, robot in _sql(
        dsn, "SELECT l.slug, r.slug FROM robot r JOIN product_line l ON l.id = r.product_line_id"
    ):
        stored.setdefault(line, []).append(robot)
    assert {k: sorted(v) for k, v in stored.items()} == {
        k: sorted(v) for k, v in EXPECTED.items()
    }
    assert all(p for (p,) in _sql(dsn, "SELECT is_published FROM product_line"))


def test_first_run_inserts_and_second_run_is_a_noop(env):
    *_, first, second = env
    assert first.counts["product_line"]["inserted"] == 5
    assert first.counts["robot_product_line"]["updated"] == 16
    for table in ("product_line", "robot_product_line"):
        c = second.counts[table]
        assert c["inserted"] == c["updated"] == c["removed"] == 0, table
    assert second.counts["product_line"]["unchanged"] == 5
    assert second.counts["robot_product_line"]["unchanged"] == 16


def _import_with(env, mutate):
    """Run import_product_lines on mutated data in a transaction that is always rolled back."""
    _, dsn, ic, *_ = env
    data = copy.deepcopy(LINES)
    mutate(data["product_lines"])
    with psycopg.connect(dsn) as conn:
        cur = conn.cursor()
        cur.execute("SET search_path TO humanoid, public")

        def manufacturer_id(slug):
            return cur.execute("SELECT id FROM manufacturer WHERE slug=%s", (slug,)).fetchone()[0]

        recon = ic.Reconciliation()
        try:
            ic.import_product_lines(cur, data, manufacturer_id, recon)
            recon.finish()
        finally:
            conn.rollback()


def test_unknown_robot_slug_is_refused(env):
    _, _, ic, *_ = env
    with pytest.raises(ic.ReconcileRefused, match="unknown robot slug 'no-such-robot'"):
        _import_with(env, lambda ls: ls[0]["robots"].append("no-such-robot"))


def test_manufacturer_mismatch_is_refused(env):
    _, _, ic, *_ = env
    def mismatch(ls):
        ls[4]["robots"].remove("booster-t2-education")      # keep it out of two lines
        ls[0]["robots"].append("booster-t2-education")

    with pytest.raises(ic.ReconcileRefused, match="different manufacturer"):
        _import_with(env, mismatch)


def test_robot_in_two_lines_is_refused(env):
    _, _, ic, *_ = env
    with pytest.raises(ic.ReconcileRefused, match="in two product lines"):
        _import_with(env, lambda ls: ls[1]["robots"].append("unitree-g1"))


def test_duplicate_line_slug_and_missing_source_are_refused(env):
    _, _, ic, *_ = env
    with pytest.raises(ic.ReconcileRefused, match="listed twice"):
        _import_with(env, lambda ls: ls.append(copy.deepcopy(ls[0])))
    with pytest.raises(ic.ReconcileRefused, match="source_url is required"):
        _import_with(env, lambda ls: ls[0].pop("source_url"))


def test_import_does_not_republish_a_line_the_owner_unpublished(env):
    _, dsn, ic, *_ = env
    _sql(dsn, "UPDATE product_line SET is_published = FALSE WHERE slug = 'unitree-h2'")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ic.run(dsn)
        assert _sql(dsn, "SELECT is_published FROM product_line WHERE slug='unitree-h2'") == [
            (False,)
        ]
    finally:
        _sql(dsn, "UPDATE product_line SET is_published = TRUE WHERE slug = 'unitree-h2'")


def test_lines_hold_no_commercial_columns(env):
    _, dsn, *_ = env
    cols = {c for (c,) in _sql(
        dsn, "SELECT column_name FROM information_schema.columns "
             "WHERE table_schema='humanoid' AND table_name='product_line'")}
    assert cols == {"id", "slug", "manufacturer_id", "name", "source_url", "observed_at",
                    "is_published", "created_at", "updated_at"}


# --- API --------------------------------------------------------------------

def test_list_returns_published_lines_with_member_slugs(env):
    client = env[0]
    body = client.get("/api/product-lines").json()
    assert {ln["slug"] for ln in body} == set(EXPECTED)
    k1 = next(ln for ln in body if ln["slug"] == "booster-k1")
    assert k1["name"] == "Booster K1"
    assert k1["manufacturer"]["slug"] == "booster-robotics"
    assert k1["source_url"].startswith("https://www.booster.tech/")
    assert k1["observed_at"] == "2026-10-31"
    assert sorted(k1["robot_slugs"]) == sorted(EXPECTED["booster-k1"])


def test_detail_carries_full_robot_detail_objects(env):
    client = env[0]
    body = client.get("/api/product-lines/unitree-g1").json()
    assert body["slug"] == "unitree-g1"
    assert sorted(r["slug"] for r in body["robots"]) == sorted(EXPECTED["unitree-g1"])
    for r in body["robots"]:
        direct = client.get(f"/api/robots/{r['slug']}").json()
        assert r == direct                      # the same serialization, nothing re-derived
        assert r["product_line"] == {"slug": "unitree-g1", "name": "Unitree G1"}


def test_unknown_and_unpublished_lines_are_404(env):
    client, dsn, *_ = env
    assert client.get("/api/product-lines/nope").status_code == 404
    _sql(dsn, "UPDATE product_line SET is_published = FALSE WHERE slug = 'booster-t2'")
    try:
        assert client.get("/api/product-lines/booster-t2").status_code == 404
        assert "booster-t2" not in {ln["slug"] for ln in client.get("/api/product-lines").json()}
        # a member's detail does not expose an unpublished line
        assert client.get("/api/robots/booster-t2-education").json()["product_line"] is None
    finally:
        _sql(dsn, "UPDATE product_line SET is_published = TRUE WHERE slug = 'booster-t2'")


def test_robot_outside_any_line_has_null_product_line(env):
    client, dsn, *_ = env
    (slug,) = _sql(dsn, "SELECT slug FROM robot WHERE product_line_id IS NULL "
                        "AND is_published ORDER BY slug LIMIT 1")[0]
    assert client.get(f"/api/robots/{slug}").json()["product_line"] is None


def test_unpublished_member_robots_are_excluded(env):
    client, dsn, *_ = env
    _sql(dsn, "UPDATE robot SET is_published = FALSE WHERE slug = 'unitree-r1-edu-u6'")
    try:
        lst = {ln["slug"]: ln for ln in client.get("/api/product-lines").json()}
        assert "unitree-r1-edu-u6" not in lst["unitree-r1"]["robot_slugs"]
        assert len(lst["unitree-r1"]["robot_slugs"]) == 6
        detail = client.get("/api/product-lines/unitree-r1").json()
        assert "unitree-r1-edu-u6" not in {r["slug"] for r in detail["robots"]}
        assert len(detail["robots"]) == 6
    finally:
        _sql(dsn, "UPDATE robot SET is_published = TRUE WHERE slug = 'unitree-r1-edu-u6'")
