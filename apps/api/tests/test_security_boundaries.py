"""WS8.1 — security boundaries: R1 (admin authz), R4 (posture), R6 (audit).

These are the gates that close release blockers B1 (stage 1), B2 (the stated
policy half) and B5. Scope discipline matters as much as coverage here: R1 is
*application* authorization only. The network boundary that puts admin on a
separate protected host/listener (DEP P4) is WS8.7 / R27, and the external
probe proving it cannot be bypassed is WS8.8 / R29. Nothing below pretends
otherwise.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.admin import PromotionAuditAdmin, admin_is_configured, mount_admin
from app.config import Settings, get_settings
from app.db.session import engine
from app.models.discovery import (
    DiscoveryCandidate,
    DiscoverySource,
    PromotionAudit,
    PromotionAuditImmutableError,
    _promotion_audit_block_delete,
    _promotion_audit_block_update,
)
from app.security.headers import (
    BASE_SECURITY_HEADERS,
    HSTS_HEADER,
    parse_allowed_origins,
)

ADMIN_ENV = {
    "ADMIN_USERNAME": "operator",
    "ADMIN_PASSWORD": "correct-horse-battery-staple",
    "ADMIN_SESSION_SECRET": "x" * 48,
}


@pytest.fixture
def admin_client(monkeypatch):
    """A throwaway app with the admin configured, so the real app under test
    keeps its unconfigured (fail-closed) posture."""
    for key, value in ADMIN_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app = FastAPI()
    assert mount_admin(app) is not None
    try:
        yield TestClient(app, follow_redirects=False)
    finally:
        get_settings.cache_clear()


# ---- R1 — admin application authorization (B1 stage 1) ---------------------


def test_r1_admin_is_not_mounted_when_unconfigured(client) -> None:
    """Fail closed (WS8-L5): missing credentials means no admin surface at all,
    never an unauthenticated one. This is the state the test app runs in."""
    assert admin_is_configured() is False
    for path in ("/admin", "/admin/", "/admin/robot/list"):
        assert client.get(path).status_code == 404, path


def test_r1_unauthenticated_admin_request_is_refused(admin_client) -> None:
    """With the admin mounted, an anonymous request must not reach a model view."""
    resp = admin_client.get("/admin/")
    assert resp.status_code in (302, 303, 307)
    assert "/admin/login" in resp.headers.get("location", "")


def test_r1_model_views_are_not_reachable_anonymously(admin_client) -> None:
    """The specific B1 exposure: buyer PII behind SQLAdmin CRUD."""
    resp = admin_client.get("/admin/commercial-lead/list")
    assert resp.status_code in (302, 303, 307)
    assert "/admin/login" in resp.headers.get("location", "")


def test_r1_wrong_credentials_do_not_authenticate(admin_client) -> None:
    resp = admin_client.post(
        "/admin/login", data={"username": "operator", "password": "wrong"}
    )
    assert resp.status_code in (200, 400, 401, 302, 303, 307)
    # Whatever the framework renders, no session was granted.
    assert admin_client.get("/admin/").status_code in (302, 303, 307)


def test_r1_correct_credentials_authenticate_and_persist(admin_client) -> None:
    login = admin_client.post(
        "/admin/login",
        data={"username": ADMIN_ENV["ADMIN_USERNAME"], "password": ADMIN_ENV["ADMIN_PASSWORD"]},
    )
    assert login.status_code in (200, 302, 303, 307)
    # The session cookie now satisfies the backend; no redirect to login.
    after = admin_client.get("/admin/")
    assert after.status_code not in (302, 303, 307) or "/admin/login" not in after.headers.get(
        "location", ""
    )


def test_r1_partial_configuration_still_fails_closed(monkeypatch) -> None:
    """Two of three secrets is not 'nearly configured' — it is unconfigured."""
    for omitted in ADMIN_ENV:
        for key, value in ADMIN_ENV.items():
            monkeypatch.setenv(key, "" if key == omitted else value)
        get_settings.cache_clear()
        app = FastAPI()
        assert mount_admin(app) is None, f"mounted with {omitted} missing"
        assert TestClient(app).get("/admin/").status_code == 404
    get_settings.cache_clear()


# ---- R4 — explicit cross-origin / security-header posture ------------------


def test_r4_security_headers_present_on_every_response(client) -> None:
    # DB-free paths on purpose: the middleware is global, so proving it here
    # keeps the R4 gate runnable without a database.
    for path in ("/", "/health"):
        headers = client.get(path).headers
        for name, value in BASE_SECURITY_HEADERS.items():
            assert headers.get(name) == value, (path, name)


def test_r4_default_posture_is_strict_same_origin(client) -> None:
    """The default emits no Access-Control-Allow-Origin at all — a stated
    decision (WS8-L9), not an accident of missing middleware."""
    resp = client.get("/", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}


def test_r4_hsts_is_opt_in_only(client) -> None:
    """TLS terminates at the ingress (WS8.7); a non-TLS environment must never
    advertise HSTS."""
    assert HSTS_HEADER[0] not in client.get("/").headers
    assert get_settings().enable_hsts is False


def test_r4_wildcard_origin_is_not_an_accepted_policy() -> None:
    assert parse_allowed_origins("*") == []
    assert parse_allowed_origins("") == []
    assert parse_allowed_origins("https://a.example, https://b.example") == [
        "https://a.example",
        "https://b.example",
    ]


# ---- R3 defaults (the shipped configuration, not the test overrides) -------


def test_shipped_rate_limit_defaults_are_strict_and_endpoint_aware() -> None:
    """The suite runs under permissive policies (see conftest), so the defaults
    that actually ship are asserted here instead — and they must differ per
    endpoint (§11 D7: never one arbitrary global number)."""
    s = Settings(_env_file=None)
    assert s.rate_limit_enabled is True
    assert 0 < s.buyer_requirements_burst <= 20
    assert 0 < s.commercial_leads_burst <= 20
    assert s.commercial_leads_sustained < s.buyer_requirements_sustained, (
        "the PII-bearing conversion endpoint should be the stricter of the two"
    )
    # DEP P1 default: no ingress trusted, so forwarding headers are never believed.
    assert s.trusted_proxy_ips == ""
    # R4 default: strict same-origin.
    assert s.cors_allowed_origins == ""


# ---- R6 — promotion_audit is append-only, enforced (B5) --------------------


def test_r6_admin_cannot_create_edit_or_delete_audit_rows() -> None:
    assert PromotionAuditAdmin.can_create is False
    assert PromotionAuditAdmin.can_edit is False
    assert PromotionAuditAdmin.can_delete is False


def test_r6_orm_listeners_are_registered() -> None:
    """The admin flags are UI-level; these listeners are the backstop that also
    covers the promotion CLI and any other session."""
    assert event.contains(PromotionAudit, "before_update", _promotion_audit_block_update)
    assert event.contains(PromotionAudit, "before_delete", _promotion_audit_block_delete)


def _seed_audit_row(session: Session) -> PromotionAudit:
    """Build the candidate this audit row hangs off, rather than depending on
    one happening to exist in the seeded database. Everything is created inside
    the test transaction and rolled back."""
    suffix = uuid.uuid4().hex[:8]
    source = DiscoverySource(
        key=f"ws8-audit-{suffix}",
        name="WS8 audit-guard fixture",
        source_class="COMPETITOR_DIRECTORY",
    )
    session.add(source)
    session.flush()
    candidate = DiscoveryCandidate(
        source_id=source.id,
        external_ref=f"ws8-{suffix}",
        candidate_name="Audit guard fixture",
        entity_type="ROBOT",
    )
    session.add(candidate)
    session.flush()
    audit = PromotionAudit(
        candidate_id=candidate.id, action="PROMOTED", approved_by="ws8-test"
    )
    session.add(audit)
    session.flush()
    return audit


@pytest.fixture
def dsession(database_url) -> Session:
    conn = engine.connect()
    trans = conn.begin()
    conn.execute(text("SET search_path TO humanoid, public"))
    session = Session(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        conn.close()


def test_r6_insert_is_still_allowed(dsession) -> None:
    """Append-only means append *works* — the guard must not break promotion."""
    audit = _seed_audit_row(dsession)
    assert audit.id is not None


def test_r6_update_is_refused(dsession) -> None:
    audit = _seed_audit_row(dsession)
    audit.approved_by = "someone-else"
    with pytest.raises(PromotionAuditImmutableError):
        dsession.flush()


def test_r6_delete_is_refused(dsession) -> None:
    audit = _seed_audit_row(dsession)
    dsession.delete(audit)
    with pytest.raises(PromotionAuditImmutableError):
        dsession.flush()
