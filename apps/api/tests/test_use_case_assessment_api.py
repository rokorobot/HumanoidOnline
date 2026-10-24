"""Use-case assignments reach the public API (HO-UC-01). DB-backed; skips without DATABASE_URL.

The shared test database holds the seed, not the catalogue, so this module imports the WHOLE
repository catalogue into a throwaway database with the real importer and points the API at it.
It then checks, against the robot files themselves:

* every `use_case_fits` row imports (the files are ready for the existing importer);
* a published robot appears at `/api/use-cases/<slug>` (the data behind the web page
  `/use-cases/[slug]`) for every use case it is assigned, with the file's score and readiness;
* an unpublished robot appears on none, and the list's robot_count matches.
"""
from __future__ import annotations

import contextlib
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
CATALOGUE = REPO_ROOT / "db" / "catalogue"
ROBOTS = {
    p.stem: json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((CATALOGUE / "robots").glob("*.json"))
}
USE_CASES = [
    u["slug"]
    for u in json.loads((CATALOGUE / "use_cases.json").read_text(encoding="utf-8"))["use_cases"]
]


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
def catalogue_api(database_url):
    """The real catalogue, imported into a scratch database, behind the real API."""
    settings = get_settings()
    url = make_url(settings.resolved_database_url)
    admin = _libpq(url.set(database="postgres"))
    name = f"ho_uc01_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    scratch = url.set(database=name)
    engine = None
    try:
        with psycopg.connect(_libpq(scratch), autocommit=True) as conn:
            conn.execute((REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        with contextlib.redirect_stdout(io.StringIO()):
            _importer().run(_libpq(scratch))

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

        yield TestClient(app), _libpq(scratch)
    finally:
        app.dependency_overrides.pop(get_session, None)
        if engine is not None:
            engine.dispose()
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                         " WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _detail(client, use_case: str) -> dict:
    resp = client.get(f"/api/use-cases/{use_case}")
    assert resp.status_code == 200, (use_case, resp.status_code, resp.text)
    return {r["slug"]: r for r in resp.json()["suitable_robots"]}


def test_every_fit_row_in_the_files_is_imported(catalogue_api):
    _, dsn = catalogue_api
    expected = {
        (slug, f["use_case_slug"])
        for slug, robot in ROBOTS.items()
        for f in robot.get("use_case_fits") or []
    }
    with psycopg.connect(dsn) as conn:
        conn.execute("SET search_path TO humanoid, public")
        stored = set(conn.execute(
            "SELECT r.slug, u.slug FROM use_case_fit f JOIN robot r ON r.id = f.robot_id"
            " JOIN use_case u ON u.id = f.use_case_id"
        ).fetchall())
    assert stored == expected


def test_published_assignments_appear_on_every_assigned_use_case_page(catalogue_api):
    client, _ = catalogue_api
    pages = {u: _detail(client, u) for u in USE_CASES}
    problems = []
    for slug, robot in ROBOTS.items():
        assigned = {f["use_case_slug"]: f for f in robot.get("use_case_fits") or []}
        for use_case, listed in pages.items():
            row = listed.get(slug)
            if robot.get("is_published") and use_case in assigned:
                fit = assigned[use_case]
                if row is None:
                    problems.append(f"{slug} missing from /use-cases/{use_case}")
                    continue
                if row["fit_score"] != fit.get("fit_score"):
                    problems.append(f"{slug}/{use_case}: score {row['fit_score']}")
                if row["commercial_readiness"] != fit.get("commercial_readiness"):
                    problems.append(f"{slug}/{use_case}: readiness {row['commercial_readiness']}")
            elif row is not None:
                problems.append(f"{slug} listed on /use-cases/{use_case} without a published fit")
    assert not problems, "\n".join(problems)


def test_the_use_case_list_counts_published_assigned_robots(catalogue_api):
    client, _ = catalogue_api
    items = client.get("/api/use-cases", params={"limit": 100}).json()["items"]
    counts = {i["slug"]: i["robot_count"] for i in items}
    for use_case in USE_CASES:
        expected = sum(
            1
            for robot in ROBOTS.values()
            if robot.get("is_published")
            and any(f["use_case_slug"] == use_case for f in robot.get("use_case_fits") or [])
        )
        assert counts[use_case] == expected, use_case
