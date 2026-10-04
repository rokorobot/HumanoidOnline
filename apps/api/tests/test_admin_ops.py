"""HO CONTROL V1 (/admin/ops) — auth boundary, read-only, escaping, fail-closed."""
from __future__ import annotations

import socket
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import admin_ops
from app.admin import mount_admin
from app.config import get_settings
from app.db.session import engine
from app.main import app as public_app
from app.models.discovery import DiscoverySource

ADMIN_ENV = {
    "ADMIN_USERNAME": "operator",
    "ADMIN_PASSWORD": "correct-horse-battery-staple",
    "ADMIN_SESSION_SECRET": "x" * 48,
}


@pytest.fixture
def admin_app(monkeypatch):
    for key, value in ADMIN_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app = FastAPI()
    assert mount_admin(app) is not None
    try:
        yield app
    finally:
        get_settings.cache_clear()


@pytest.fixture
def anon(admin_app):
    return TestClient(admin_app, follow_redirects=False)


@pytest.fixture
def operator(admin_app):
    client = TestClient(admin_app, follow_redirects=False)
    resp = client.post("/admin/login", data={
        "username": ADMIN_ENV["ADMIN_USERNAME"], "password": ADMIN_ENV["ADMIN_PASSWORD"]})
    assert resp.status_code in (200, 302)
    return client


def test_unauthenticated_cannot_see_dashboard(anon):
    resp = anon.get("/admin/ops")
    assert resp.status_code in (302, 303, 307, 401, 403)
    assert "HO CONTROL" not in resp.text
    assert "/admin/login" in resp.headers.get("location", "/admin/login")


def test_operator_gets_dashboard(operator, database_url):
    resp = operator.get("/admin/ops")
    assert resp.status_code == 200
    assert "HO CONTROL" in resp.text
    assert "OPERATIONS / READ ONLY" in resp.text
    assert "HUMANOID. ONLINE" in resp.text
    assert any(s in resp.text for s in ("HEALTHY", "ATTENTION"))
    for section in ("NEEDS ATTENTION", "CATALOGUE", "DISCOVERY", "GOVERNANCE",
                    "FRESHNESS", "SCHEDULED SOURCE STATUS", "RECENT ACTIVITY",
                    "EXTERNAL SIGNALS"):
        assert section in resp.text
    assert "NOT CONNECTED — V1" in resp.text
    assert "UNKNOWN — EXTERNAL SIGNAL NOT WIRED" in resp.text
    assert 'href="/admin/"' in resp.text


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_only_get_is_exposed(operator, method):
    assert getattr(operator, method)("/admin/ops").status_code == 405


def test_no_public_api_endpoint_added():
    paths = {getattr(r, "path", "") for r in public_app.routes}
    assert not any("ops" in p.split("/") or "control" in p for p in paths)
    # /admin is mounted by the app factory only when credentials exist; the
    # dashboard module must never register an /api route of its own.
    assert not any(p.startswith("/api") and "ops" in p for p in paths)


def test_makes_no_external_network_requests(operator, database_url, monkeypatch):
    real_connect = socket.socket.connect

    def guarded(self, address, *a, **kw):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"external connect attempted: {host!r}")
        return real_connect(self, address, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    assert operator.get("/admin/ops").status_code == 200


def test_no_external_assets_or_scripts():
    html = admin_ops.render_dashboard(admin_ops.Snapshot(generated_at=datetime.now(UTC),
                                                         database_ok=False))
    assert "<script" not in html and "http://" not in html and "https://" not in html
    assert "<link" not in html


def test_database_derived_text_is_escaped():
    now = datetime.now(UTC)
    snap = admin_ops.Snapshot(
        generated_at=now,
        catalogue={"robots": 1, "published": 0, "manufacturers": 1, "pricing": 0,
                   "availability": 0, "evidence": 0, "evidence_latest": None},
        discovery={"enabled": 1, "scheduled": 1, "due": 0, "running": 0, "failed_recent": 0,
                   "latest_status": "<b>x</b>", "latest_at": None},
        governance={"unresolved": 0, "proposals": 0, "undecided": 0, "deferred": 0,
                    "active_claims": 0, "write_audits": 0},
        freshness={"active": 0, "due": 0, "manual_due": 0, "fetch_errors_recent": 0,
                   "latest_check": None, "latest_change": None},
        schedule=[{"key": "<script>alert(1)</script>", "name": "<img src=x onerror=1>",
                   "hours": 24, "last": None, "next_due": None, "state": admin_ops.NEVER_RUN}],
        activity=[{"at": now, "process": "CRAWL", "ref": "<svg onload=1>", "outcome": "a&b"}],
    )
    html = admin_ops.render_dashboard(snap)
    for raw in ("<script>alert", "<img src=x", "<svg onload", "<b>x</b>"):
        assert raw not in html
    assert "&lt;script&gt;" in html and "a&amp;b" in html
    assert "NO HUMAN ACTION REQUIRED" in html


def test_database_down_fails_closed_without_exception_text(operator, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("password=hunter2 host=secret.internal")

    monkeypatch.setattr(admin_ops, "Session", boom)
    resp = operator.get("/admin/ops")
    assert resp.status_code == 200
    assert "CRITICAL / DATABASE DOWN" in resp.text
    assert "hunter2" not in resp.text and "secret.internal" not in resp.text


def test_overall_state_rules():
    now = datetime.now(UTC)
    base = dict(
        generated_at=now,
        governance={"unresolved": 0, "proposals": 0, "undecided": 0, "deferred": 0,
                    "active_claims": 0, "write_audits": 0},
        freshness={"manual_due": 0, "fetch_errors_recent": 0},
        discovery={"failed_recent": 0, "running": 3},
    )
    assert admin_ops.Snapshot(**base).overall == admin_ops.HEALTHY  # RUNNING is not an error
    base["discovery"] = {"failed_recent": 1, "running": 0}
    assert admin_ops.Snapshot(**base).overall == admin_ops.ATTENTION
    assert admin_ops.Snapshot(generated_at=now, database_ok=False).overall == admin_ops.CRITICAL


def test_schedule_state_vocabulary():
    now = datetime.now(UTC)
    assert admin_ops._schedule_state(24, None, now)[0] == admin_ops.NEVER_RUN
    assert admin_ops._schedule_state(24, now - timedelta(hours=25), now)[0] == admin_ops.DUE
    assert admin_ops._schedule_state(24, now - timedelta(hours=1), now)[0] == admin_ops.NOT_DUE


def test_snapshot_is_read_only_and_reports_scheduled_source(database_url):
    """Live DB: snapshot succeeds, counts are ints, and a never-run scheduled
    source shows as NEVER_RUN. The fixture row is committed then deleted;
    the snapshot itself writes nothing."""
    tag = uuid.uuid4().hex[:8]
    with Session(engine) as s:
        s.add(DiscoverySource(
            key=f"ops-{tag}", name="Ops fixture", source_class="MANUFACTURER",
            homepage_url="https://fixture.test", observation_interval_hours=24,
            observation_cadence_set_by="ops-test", observation_cadence_set_at=datetime.now(UTC)))
        s.commit()
    try:
        snap = admin_ops.collect_snapshot()
        assert snap.database_ok
        assert isinstance(snap.catalogue["robots"], int)
        row = next(r for r in snap.schedule if r["key"] == f"ops-{tag}")
        assert row["state"] == admin_ops.NEVER_RUN
    finally:
        with Session(engine) as s:
            s.query(DiscoverySource).filter_by(key=f"ops-{tag}").delete()
            s.commit()
