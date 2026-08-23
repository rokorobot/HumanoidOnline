"""Tests for the TEMPORARY Resend response-origin diagnostic route
(app/routers/_resend_diagnostic.py). This route is removed shortly after its
one authorized production invocation — these tests exist to prove, before
that invocation, that a missing/wrong token can never reach the real send
path, that the route needs no database, and that its response never carries
more than the approved safe fields. `_send_email` is always monkeypatched:
these tests never send a real email.
"""
from __future__ import annotations

import hashlib

import app.routers._resend_diagnostic as diag
from app.db.session import get_session

_PATH = diag.router.routes[0].path
_RAW_TOKEN = "test-only-token-never-the-real-one"


def _patch_token(monkeypatch) -> None:
    monkeypatch.setattr(
        diag, "_TOKEN_SHA256", hashlib.sha256(_RAW_TOKEN.encode("utf-8")).hexdigest()
    )


def _record_send_email(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(diag, "_send_email", lambda **kwargs: calls.append(kwargs))
    return calls


def test_missing_token_is_rejected_and_never_calls_send_email(client, monkeypatch):
    _patch_token(monkeypatch)
    calls = _record_send_email(monkeypatch)
    resp = client.post(_PATH)
    assert resp.status_code == 404
    assert calls == []


def test_incorrect_token_is_rejected_and_never_calls_send_email(client, monkeypatch):
    _patch_token(monkeypatch)
    calls = _record_send_email(monkeypatch)
    resp = client.post(_PATH, headers={"X-Humanoid-Diagnostic-Token": "wrong-token"})
    assert resp.status_code == 404
    assert calls == []


def test_correct_token_invokes_send_email_exactly_once(client, monkeypatch):
    _patch_token(monkeypatch)
    calls = _record_send_email(monkeypatch)
    resp = client.post(_PATH, headers={"X-Humanoid-Diagnostic-Token": _RAW_TOKEN})
    assert resp.status_code == 200, resp.text
    assert len(calls) == 1


def test_response_contains_only_the_approved_safe_fields(client, monkeypatch):
    _patch_token(monkeypatch)
    _record_send_email(monkeypatch)  # succeeds (no exception) -> "accepted"
    resp = client.post(_PATH, headers={"X-Humanoid-Diagnostic-Token": _RAW_TOKEN})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"] == "accepted"
    assert set(body.keys()) == {
        "result",
        "provider_status",
        "provider_error",
        "provider_content_type",
        "provider_body_bytes",
        "provider_body_is_json",
    }


def _collect_dependency_calls(dependant) -> list:
    calls = [dependant.call] if dependant.call else []
    for sub in dependant.dependencies:
        calls.extend(_collect_dependency_calls(sub))
    return calls


def test_route_has_no_db_dependency():
    # Inspect the un-included APIRoute directly (diag.router.routes[0]) rather
    # than app.routes -- this FastAPI version wraps included routers in an
    # internal _IncludedRouter, which doesn't expose .dependant the same way.
    route = diag.router.routes[0]
    calls = _collect_dependency_calls(route.dependant)
    assert get_session not in calls
