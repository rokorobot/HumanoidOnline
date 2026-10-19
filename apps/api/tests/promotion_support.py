"""Shared fixtures for the catalogue-promotion tests (PR B).

Everything here is SYNTHETIC and local: a throwaway Postgres database built from db/schema.sql,
the repository's own catalogue JSON copied into a temp directory (never production data), one
fake discovery source / candidate / claim inserted by SQL, and recording fakes for GitHub and
the public web. `LocalBranches` (CREATE DATABASE ... TEMPLATE) stands in for Neon branches.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import uuid
from datetime import date
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.discovery import promotion_execute as px
from app.services.discovery import promotion_manifest as pm

ROOT = Path(__file__).resolve().parents[3]
REAL_CATALOGUE = ROOT / "db" / "catalogue"
SCHEMA_SQL = ROOT / "db" / "schema.sql"
ROBOT = "unitree-g1"
KEY = "synthetic_compute"
VALUE = "SYNTHETIC 8-core test CPU"
TODAY = date(2026, 10, 19)
RETRIEVED = "2026-10-18 22:06:58+00"


def plain(url) -> str:
    text = url if isinstance(url, str) else url.render_as_string(hide_password=False)
    return text.replace("postgresql+psycopg://", "postgresql://", 1)


def _admin_url() -> str:
    return plain(make_url(get_settings().resolved_database_url).set(database="postgres"))


def _db_url(name: str) -> str:
    return plain(make_url(get_settings().resolved_database_url).set(database=name))


def _drop(name: str) -> None:
    with psycopg.connect(_admin_url(), autocommit=True) as conn:
        conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                     "WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
        conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def copy_catalogue(target: Path) -> Path:
    shutil.copytree(REAL_CATALOGUE, target, ignore=shutil.ignore_patterns("promotions"))
    return target


def add_definition(catalogue: Path, key: str = KEY) -> None:
    path = catalogue / "spec_definitions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if all(d["key"] != key for d in data["spec_definitions"]):
        data["spec_definitions"].append({
            "key": key, "label": "Onboard computer (synthetic)", "category": "AI_AUTONOMY",
            "value_type": "TEXT", "unit": None, "sort_order": 99})
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_import(url: str, catalogue: Path, robots=(ROBOT,)) -> str:
    ic = pm.load_db_tool("import_catalogue")
    ic.CATALOGUE_DIR, ic.ROBOTS_DIR = catalogue, catalogue / "robots"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ic.run(plain(url), only=set(robots))
    return out.getvalue()


@pytest.fixture(scope="module")
def template_db(tmp_path_factory, database_url):
    """schema + the G1 record imported from a SYNTHETIC-extended catalogue + fake discovery."""
    name = f"promo_tpl_{uuid.uuid4().hex[:10]}"
    base = tmp_path_factory.mktemp("tplcat")
    catalogue = add_definition(copy_catalogue(base / "c")) or base / "c"
    with psycopg.connect(_admin_url(), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    url = _db_url(name)
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
            conn.execute("SET search_path TO humanoid, public")
            conn.execute(
                "INSERT INTO spec_definition (key, label, category, value_type, sort_order,"
                " managed_by) VALUES (%s, 'Onboard computer (synthetic)', 'AI_AUTONOMY',"
                " 'TEXT', 99, 'CATALOGUE_IMPORT')", (KEY,))
        run_import(url, catalogue)
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("SET search_path TO humanoid, public")
            conn.execute(_SYNTHETIC_DISCOVERY_SQL)
        yield name
    finally:
        _drop(name)


_SYNTHETIC_DISCOVERY_SQL = f"""
INSERT INTO discovery_source (key, name, source_class, homepage_url, tos_status, robots_status,
    access_basis, owner_authorized_by, owner_authorized_at, owner_authorization_reason,
    owner_authorized_path_prefixes, eligibility_reviewed_at, eligibility_reviewed_by,
    is_enabled, allowed_path_prefixes)
VALUES ('synthetic-maker', 'Synthetic Maker', 'MANUFACTURER', 'https://synthetic.example/',
    'UNKNOWN', 'ALLOWED', 'OWNER_AUTHORIZED', 'test', now(), 'synthetic fixture',
    ARRAY['/g1'], now(), 'test', true, ARRAY['/g1']);
INSERT INTO crawl_run (source_id, adapter_key, adapter_version, operator, status, started_at,
    finished_at)
SELECT id, 'synthetic', '1', 'test', 'COMPLETED', now(), now()
FROM discovery_source WHERE key = 'synthetic-maker';
INSERT INTO fetched_page (crawl_run_id, source_id, url, http_status, content_type, content_hash,
    outcome, retrieved_at)
SELECT c.id, c.source_id, 'https://synthetic.example/g1', 200, 'text/html',
    'abc123def4567890abc123def4567890abc123def4567890abc123def4567890', 'FETCHED',
    '{RETRIEVED}'::timestamptz
FROM crawl_run c;
INSERT INTO discovery_candidate (source_id, external_ref, candidate_name, identity_status,
    possible_robot_id)
SELECT s.id, 'synthetic-g1', 'G1', 'MATCHED_EXISTING', r.id
FROM discovery_source s, robot r WHERE s.key = 'synthetic-maker' AND r.slug = '{ROBOT}';
INSERT INTO candidate_claim (candidate_id, field_key, claimed_value, claim_status,
    discovery_source_id, evidence_url, extraction_method, extraction_confidence, fetched_page_id)
SELECT d.id, 'synthetic.spec[G1]/Electrical/Computing Power', '{VALUE}', 'NOT_VERIFIED',
    d.source_id, 'https://synthetic.example/g1', 'SELECTOR', 'HIGH', p.id
FROM discovery_candidate d, fetched_page p;
"""


class World:
    """One writable 'production' copy plus a catalogue base and a proposed manifest."""

    def __init__(self, tmp: Path, template: str):
        self.name = f"promo_w_{uuid.uuid4().hex[:10]}"
        with psycopg.connect(_admin_url(), autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{self.name}" TEMPLATE "{template}"')
        self.url = _db_url(self.name)
        self.admin = _admin_url()
        self.base = add_definition(copy_catalogue(tmp / "base")) or tmp / "base"
        self.head = tmp / "head"
        shutil.copytree(self.base, self.head)
        self.branches = px.LocalBranches(self.admin, self.name)
        self.github = FakeGithub()
        self.claim_id = self.sql("SELECT id::text FROM candidate_claim")[0][0]
        self._manifest: dict | None = None

    # -- database helpers --------------------------------------------------------------
    def sql(self, statement: str, params=()) -> list[tuple]:
        with psycopg.connect(self.url, autocommit=True) as conn:
            conn.execute("SET search_path TO humanoid, public")
            cur = conn.execute(statement, params)
            return cur.fetchall() if cur.description else []

    def fingerprints(self) -> dict:
        return pm.fingerprints_from_url(self.url, [ROBOT])

    def spec_rows(self) -> list[tuple]:
        return self.sql(
            "SELECT d.key, s.value_text FROM specification s JOIN spec_definition d ON "
            "d.id = s.definition_id JOIN robot r ON r.id = s.robot_id WHERE r.slug = %s "
            "AND d.key = %s", (ROBOT, KEY))

    def branch_dbs(self) -> list[str]:
        with psycopg.connect(self.admin, autocommit=True) as conn:
            rows = conn.execute("SELECT datname FROM pg_database WHERE datname LIKE 'promo%' "
                                "OR datname LIKE 'rehearse%'").fetchall()
        # Only this test's synthetic promotions: other branch databases on the same server
        # (e.g. a retained local pilot safety point) are not ours to count.
        return sorted(r[0] for r in rows if r[0] != self.name and "synthetic" in r[0])

    # -- proposals ---------------------------------------------------------------------
    def item(self, **over) -> dict:
        item = {"claim_id": self.claim_id, "definition": KEY, "proposed_value": VALUE,
                "edition": "G1", "evidence_locator": "synthetic row"}
        item.update(over)
        return item

    def propose(self, items=None, *, catalogue=None, edition_map="default", today=TODAY,
                promotion_id="synthetic-promo", **kw) -> dict:
        engine = create_engine(self.url.replace("postgresql://", "postgresql+psycopg://", 1),
                               connect_args={"options": "-csearch_path=humanoid,public"})
        try:
            with Session(engine) as session:
                return pm.propose(
                    session, ROBOT, items or [self.item()], catalogue_dir=catalogue or self.base,
                    base_commit="synthetic-base", promotion_id=promotion_id, today=today,
                    edition_map={ROBOT: "G1"} if edition_map == "default" else edition_map, **kw)
        finally:
            engine.dispose()

    @property
    def manifest(self) -> dict:
        """A ROUTINE manifest; `head` already carries its catalogue edit."""
        if self._manifest is None:
            self._manifest = self.propose()
            assert self._manifest["items"][0]["classification"] == pm.ROUTINE, self._manifest
            pm.apply_to_catalogue(self._manifest, self.head)
        return self._manifest

    def prepare(self) -> dict:
        return self.manifest

    def execute(self, manifest=None, **over):
        kwargs = dict(commit="c0ffee", production=px.StaticProduction(self.url),
                      branches=self.branches, github=self.github,
                      web=self.web_for(manifest or self.manifest), api_base="http://api.test",
                      web_base="http://web.test", catalogue_dir=self.head,
                      base_catalogue_dir=self.base, sleep=lambda s: None, retry_wait=0)
        kwargs.update(over)
        return px.execute(manifest or self.manifest, **kwargs)

    @staticmethod
    def web_for(manifest: dict, *, healthy: bool = True):
        return FakeWeb(manifest, healthy)

    def close(self) -> None:
        for db in self.branch_dbs():
            _drop(db)
        _drop(self.name)


class FakeGithub:
    def __init__(self):
        self.incident_open = False
        self.read_error = False
        self.incidents: list[tuple[str, str]] = []
        self.comments: list[str] = []

    def open_incident_exists(self) -> bool:
        if self.read_error:
            raise OSError("github unreachable")
        return self.incident_open

    def open_incident(self, title: str, body: str) -> None:
        self.incidents.append((title, body))

    def comment(self, body: str) -> None:
        self.comments.append(body)


class FakeWeb:
    """Serves the committed value on the API, the page and compare (or nothing)."""

    def __init__(self, manifest: dict, healthy: bool):
        self.manifest, self.healthy = manifest, healthy
        self.calls = 0

    def get(self, url: str) -> tuple[int, str]:
        self.calls += 1
        if not self.healthy:
            return 200, "<html>old page</html>"
        items = self.manifest["items"]
        if "/api/robots/" in url:
            return 200, json.dumps({"extended_specs": [
                {"key": i["definition"], "value": i["proposed_value"],
                 "source_url": i["source_url"], "variant_slug": i.get("variant_slug")}
                for i in items]})
        return 200, "<html>" + " ".join(
            f"{i['proposed_value']} {i['source_label']}" for i in items) + "</html>"


@pytest.fixture
def world(tmp_path, template_db):
    w = World(tmp_path, template_db)
    try:
        yield w
    finally:
        w.close()
