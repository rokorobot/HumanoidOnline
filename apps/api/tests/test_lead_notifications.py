"""Lead-capture operational email notification tests.

Covers the mandatory list for the notification feature: persistence always
wins over delivery, notifications never gate the public 201/200 response, the
feature is inert unless fully configured, and no buyer PII ever reaches a log
line. The external email API is always faked — these tests never send real
email (`app.services.lead_notifications._send_email` is monkeypatched).
"""
from __future__ import annotations

import logging
import urllib.error
import uuid

from sqlalchemy import text

import app.services.lead_notifications as notif
from app.db.session import SessionLocal, engine
from app.models.commercial_lead import CommercialLead


class _FakeSettings:
    lead_notification_enabled = True
    lead_notification_to = "ops@example.com, ops2@example.com"
    lead_notification_from = "noreply@humanoidonline.example"
    email_api_key = "fake-key"
    email_api_endpoint = "https://api.resend.example/emails"


class _DisabledSettings(_FakeSettings):
    lead_notification_enabled = False


class _MissingKeySettings(_FakeSettings):
    email_api_key = None


def _enable(monkeypatch, settings=None) -> None:
    monkeypatch.setattr(notif, "get_settings", lambda: (settings or _FakeSettings()))


def _record_sends(monkeypatch, *, raise_exc: BaseException | None = None) -> list[dict]:
    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        if raise_exc is not None:
            raise raise_exc

    monkeypatch.setattr(notif, "_send_email", fake)
    return calls


def _scalar(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        return conn.execute(text(sql), params).scalar_one()


def _any_published_slug() -> str:
    return _scalar("SELECT slug FROM robot WHERE is_published LIMIT 1")


def _warehouse_requirement(client) -> str:
    raw = {
        "wizard_version": 1,
        "answers": {
            "task": {"state": "ANSWERED", "use_case": "warehouse-logistics"},
            "country": {"state": "ANSWERED", "value": "US"},
            "payload": {"state": "ANSWERED", "value": 10},
        },
    }
    resp = client.post("/api/buyer-requirements", json={
        "contact_name": "Test Buyer", "organization": "Test Org",
        "contact_email": "buyer@example.com",
        "use_case": "warehouse-logistics", "country": "US", "payload_min_kg": 10,
        "preferred_transaction": "RAAS", "raw_input": raw,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _matched_slug(client, rid: str) -> str:
    resp = client.get(f"/api/buyer-requirements/{rid}/matches")
    assert resp.status_code == 200, resp.text
    matches = resp.json()["matches"]
    assert matches, "fixture requirement must surface at least one match"
    return matches[0]["robot"]["slug"]


def _load_lead(lead_id: str) -> CommercialLead:
    # A fresh session -> `.robots` (lazy="selectin") loads eagerly alongside
    # the row itself, no separate refresh needed.
    with SessionLocal() as session:
        lead = session.get(CommercialLead, uuid.UUID(lead_id))
        assert lead is not None
        return lead


# ---- readiness gate (pure, no DB) ------------------------------------------


def test_notification_ready_requires_all_four_fields():
    assert notif._notification_ready(_FakeSettings()) is True
    assert notif._notification_ready(_DisabledSettings()) is False
    assert notif._notification_ready(_MissingKeySettings()) is False

    class _NoTo(_FakeSettings):
        lead_notification_to = None

    class _NoFrom(_FakeSettings):
        lead_notification_from = None

    assert notif._notification_ready(_NoTo()) is False
    assert notif._notification_ready(_NoFrom()) is False


# ---- 1 — new lead: persisted + exactly one attempt -------------------------


def test_new_lead_triggers_exactly_one_notification(client, database_url, monkeypatch):
    _enable(monkeypatch)
    calls = _record_sends(monkeypatch)
    rid = _warehouse_requirement(client)
    slug = _matched_slug(client, rid)

    resp = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "notif-new@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [slug],
    })
    assert resp.status_code == 201, resp.text
    assert len(calls) == 1
    assert "[HumanoidOnline] NEW commercial lead" in calls[0]["subject"]
    assert calls[0]["to_addrs"] == ["ops@example.com", "ops2@example.com"]


# ---- 2 — extension: persisted + labelled UPDATED ---------------------------


def test_extension_triggers_updated_notification(client, database_url, monkeypatch):
    _enable(monkeypatch)
    calls = _record_sends(monkeypatch)
    rid = _warehouse_requirement(client)
    slug = _matched_slug(client, rid)

    first = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "notif-ext@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [slug],
    })
    assert first.status_code == 201, first.text
    second = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "notif-ext@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": [slug], "message": "following up",
    })
    assert second.status_code == 200, second.text

    assert len(calls) == 2
    assert "NEW commercial lead" in calls[0]["subject"]
    assert "UPDATED commercial lead" in calls[1]["subject"]


# ---- 3 — invalid request: no attempt ---------------------------------------


def test_invalid_request_sends_no_notification(client, database_url, monkeypatch):
    _enable(monkeypatch)
    calls = _record_sends(monkeypatch)
    rid = _warehouse_requirement(client)
    _matched_slug(client, rid)  # ensure a real shortlist exists

    resp = client.post("/api/commercial-leads", json={
        # not in the persisted shortlist -> 422, zero writes
        "requirement_id": rid, "contact_email": "bad@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": ["unitree-g1"],
    })
    assert resp.status_code == 422, resp.text
    assert calls == []


# ---- 4 — provider success: normal 201/200 unchanged ------------------------


def test_provider_success_leaves_response_semantics_unchanged(client, database_url, monkeypatch):
    _enable(monkeypatch)
    _record_sends(monkeypatch)  # succeeds (no exception)
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "notif-success@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": [_any_published_slug()],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body.keys()) == {"id", "lead_status"}
    assert body["lead_status"] == "NEW"


# ---- 5 — provider timeout/failure: lead remains committed, response normal -


def test_notification_failure_does_not_affect_commit_or_response(client, database_url, monkeypatch):
    _enable(monkeypatch)
    calls = _record_sends(monkeypatch, raise_exc=TimeoutError("simulated provider timeout"))
    rid = _warehouse_requirement(client)
    slug = _matched_slug(client, rid)

    resp = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "notif-fail@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [slug],
    })
    assert resp.status_code == 201, resp.text
    lead_id = resp.json()["id"]
    assert len(calls) == 1
    stored = _scalar("SELECT contact_email FROM commercial_lead WHERE id=:i", i=lead_id)
    assert stored == "notif-fail@example.com"  # genuinely persisted despite the failure


# ---- 6 — disabled / unconfigured: zero network calls ------------------------


def test_disabled_notifications_send_zero_calls(client, database_url, monkeypatch):
    _enable(monkeypatch, _DisabledSettings())
    calls = _record_sends(monkeypatch)
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "notif-disabled@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": [_any_published_slug()],
    })
    assert resp.status_code == 201, resp.text
    assert calls == []


def test_partially_configured_notifications_send_zero_calls(client, database_url, monkeypatch):
    """enabled=True but EMAIL_API_KEY unset -> treated as not configured, not a crash."""
    _enable(monkeypatch, _MissingKeySettings())
    calls = _record_sends(monkeypatch)
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "notif-partial@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": [_any_published_slug()],
    })
    assert resp.status_code == 201, resp.text
    assert calls == []


# ---- 7 — UNKNOWN / missing values represented honestly ---------------------


def test_build_email_represents_unknown_honestly(client, database_url):
    # contact_name/organization are required by the API now, so a NULL name/org/
    # phone can no longer be produced by a live POST — this test exercises
    # `_build_email` directly against a lead object with those fields cleared
    # (a historical row, or any other route to a NULL value, renders the same).
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "notif-unknown@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": [_any_published_slug()],
    })
    assert resp.status_code == 201, resp.text
    lead = _load_lead(resp.json()["id"])
    lead.contact_name = None
    lead.organization = None

    with SessionLocal() as session:
        subject, body = notif._build_email(session, lead, True)

    # No country/budget/message/name/org/phone was supplied on a direct capture
    # (name/org cleared above; phone was never sent) — every one of those must
    # read UNKNOWN, never a fabricated 0/false/"".
    assert "Country: UNKNOWN" in body
    assert "Name: UNKNOWN" in body
    assert "Organization: UNKNOWN" in body
    assert "Phone: UNKNOWN" in body
    assert "Message: UNKNOWN" in body
    assert "Payload (min kg): UNKNOWN" in body
    assert "Manipulation required: UNKNOWN" in body
    assert "0" not in subject
    assert "This is an internal HumanoidOnline operational notification." in body
    assert "The authoritative lead record remains in the HumanoidOnline database." in body


def test_build_email_includes_a_supplied_phone_number(client, database_url):
    resp = client.post("/api/commercial-leads", json={
        "contact_email": "notif-phone@example.com", "contact_name": "Test Buyer",
        "organization": "Test Org", "contact_phone": "+1-555-0142",
        "robot_slugs": [_any_published_slug()],
    })
    assert resp.status_code == 201, resp.text
    lead = _load_lead(resp.json()["id"])

    with SessionLocal() as session:
        _, body = notif._build_email(session, lead, True)

    assert "Phone: +1-555-0142" in body


# ---- 8 — canonical server-owned data, never client-supplied ----------------


def test_email_uses_canonical_robot_name_from_persisted_state(client, database_url):
    slug = _any_published_slug()
    real_name = _scalar("SELECT name FROM robot WHERE slug=:s", s=slug)

    resp = client.post("/api/commercial-leads", json={
        "contact_email": "notif-canonical@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [slug],
    })
    assert resp.status_code == 201, resp.text
    lead = _load_lead(resp.json()["id"])

    # _build_email takes only (session, lead, created) — it structurally
    # cannot see the original client payload, which never even carried a
    # robot NAME (only a slug; CommercialLeadCreate has no name field at all).
    with SessionLocal() as session:
        _, body = notif._build_email(session, lead, True)

    assert real_name in body
    assert slug in body


# ---- 9 — failure logs carry no PII -----------------------------------------


def test_failure_logs_contain_no_pii(client, database_url, monkeypatch, caplog):
    _enable(monkeypatch)
    _record_sends(monkeypatch, raise_exc=TimeoutError("simulated provider timeout"))
    sentinel_email = f"pii-notif-{uuid.uuid4().hex[:10]}@example.com"
    rid = _warehouse_requirement(client)
    slug = _matched_slug(client, rid)

    with caplog.at_level(logging.DEBUG):
        resp = client.post("/api/commercial-leads", json={
            "requirement_id": rid, "contact_email": sentinel_email,
            "contact_name": "Notif PII Probe", "organization": "NotifOrg Ltd",
            "robot_slugs": [slug], "message": "please do not leak this message",
        })
    assert resp.status_code == 201, resp.text

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert sentinel_email not in logged
    assert "Notif PII Probe" not in logged
    assert "NotifOrg Ltd" not in logged
    assert "please do not leak this message" not in logged
    # and the failure really did log something (the assertion above isn't vacuous)
    assert "lead notification failed" in logged


# ---- observability — four distinguishable outcomes in the logs ------------


def test_log_distinguishes_disabled_from_incomplete_config(
    client, database_url, monkeypatch, caplog
):
    """Both are "no email sent", but a different production misconfiguration —
    the log line must say which, not just that nothing happened."""
    _enable(monkeypatch, _DisabledSettings())
    _record_sends(monkeypatch)
    with caplog.at_level(logging.INFO):
        resp = client.post("/api/commercial-leads", json={
            "contact_email": "notif-obs-disabled@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org",
            "robot_slugs": [_any_published_slug()],
        })
    assert resp.status_code == 201, resp.text
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "lead notification skipped" in logged
    assert "reason=disabled" in logged

    caplog.clear()
    _enable(monkeypatch, _MissingKeySettings())
    with caplog.at_level(logging.INFO):
        resp = client.post("/api/commercial-leads", json={
            "contact_email": "notif-obs-incomplete@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org",
            "robot_slugs": [_any_published_slug()],
        })
    assert resp.status_code == 201, resp.text
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "lead notification skipped" in logged
    assert "reason=incomplete_config" in logged


def test_log_records_attempt_before_outcome(client, database_url, monkeypatch, caplog):
    _enable(monkeypatch)
    _record_sends(monkeypatch)  # succeeds
    with caplog.at_level(logging.INFO):
        resp = client.post("/api/commercial-leads", json={
            "contact_email": "notif-obs-attempt@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org",
            "robot_slugs": [_any_published_slug()],
        })
    assert resp.status_code == 201, resp.text
    logged = [r.getMessage() for r in caplog.records]
    assert any("lead notification attempting" in m for m in logged)
    assert any("lead notification accepted" in m for m in logged)
    # attempting must precede accepted, not just both appear somewhere
    attempt_idx = next(i for i, m in enumerate(logged) if "lead notification attempting" in m)
    accepted_idx = next(i for i, m in enumerate(logged) if "lead notification accepted" in m)
    assert attempt_idx < accepted_idx


def test_log_reports_provider_status_class_on_http_error(client, database_url, monkeypatch, caplog):
    """A rejected send (e.g. an unverified Resend sender domain, 403) must be
    distinguishable from a network/timeout failure by its status class."""
    _enable(monkeypatch)
    http_error = urllib.error.HTTPError(
        "https://api.resend.example/emails", 403, "Forbidden", None, None
    )
    _record_sends(monkeypatch, raise_exc=http_error)
    with caplog.at_level(logging.INFO):
        resp = client.post("/api/commercial-leads", json={
            "contact_email": "notif-obs-4xx@example.com",
            "contact_name": "Test Buyer", "organization": "Test Org",
            "robot_slugs": [_any_published_slug()],
        })
    assert resp.status_code == 201, resp.text
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "lead notification failed" in logged
    assert "status_class=4xx" in logged


# ---- 10 — both capture surfaces share the one governed path ----------------


def test_both_capture_surfaces_use_same_notification_path(client, database_url, monkeypatch):
    _enable(monkeypatch)
    calls = _record_sends(monkeypatch)

    rid = _warehouse_requirement(client)
    slug = _matched_slug(client, rid)
    linked = client.post("/api/commercial-leads", json={
        "requirement_id": rid, "contact_email": "notif-path-a@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org", "robot_slugs": [slug],
    })
    assert linked.status_code == 201, linked.text

    direct = client.post("/api/commercial-leads", json={
        "contact_email": "notif-path-b@example.com",
        "contact_name": "Test Buyer", "organization": "Test Org",
        "robot_slugs": [_any_published_slug()],
    })
    assert direct.status_code == 201, direct.text

    assert len(calls) == 2
    assert all("commercial lead" in c["subject"] for c in calls)
