"""WS8.6 / R25 — observability: request correlation, structured logging with no
PII, log-and-re-raise error handling, and `event_log` dormancy.

The request logger (`app.request`) does not propagate, so these tests attach
their own capturing handler rather than relying on pytest's caplog.
"""
from __future__ import annotations

import logging
import pathlib
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability import (
    REQUEST_ID_HEADER,
    JsonLogFormatter,
    RequestObservabilityMiddleware,
    sanitize_request_id,
)

REQUEST_LOGGER = "app.request"


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def rendered(self) -> str:
        """Everything a JSON log line would contain — for PII scanning."""
        fmt = JsonLogFormatter()
        return "\n".join(fmt.format(r) for r in self.records)


@pytest.fixture
def logs():
    logger = logging.getLogger(REQUEST_LOGGER)
    handler = _Capture()
    logger.addHandler(handler)
    prev = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)


# A tiny app exercising the middleware in isolation (no DB), so the 2xx/4xx/5xx,
# route-template and PII-body behaviours are deterministic and self-contained.
def _probe_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestObservabilityMiddleware)

    @app.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @app.post("/echo")
    def echo(payload: dict) -> dict[str, bool]:
        return {"received": True}

    @app.get("/boom")
    def boom() -> None:
        # The message deliberately embeds "user input" that must never be logged.
        raise RuntimeError("secret-boom contact user@example.com token=abc123")

    return app


@pytest.fixture
def probe() -> TestClient:
    # raise_server_exceptions=False so a 500 returns a response we can assert on.
    return TestClient(_probe_app(), raise_server_exceptions=False)


# --------------------------------------------------------------------------- #
# Correlation id
# --------------------------------------------------------------------------- #
def test_sanitize_request_id_rules() -> None:
    assert sanitize_request_id("abc-123_.Z") == "abc-123_.Z"
    assert sanitize_request_id("x" * 128) == "x" * 128
    assert sanitize_request_id(None) is None
    assert sanitize_request_id("") is None
    assert sanitize_request_id("has spaces") is None
    assert sanitize_request_id("bad!chars$") is None
    assert sanitize_request_id("x" * 129) is None  # oversized


def test_correlation_id_generated_when_absent(probe: TestClient) -> None:
    r = probe.get("/ok")
    rid = r.headers.get(REQUEST_ID_HEADER)
    assert rid and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", rid)


def test_valid_inbound_request_id_is_propagated(probe: TestClient) -> None:
    r = probe.get("/ok", headers={REQUEST_ID_HEADER: "trace-abc_1.2"})
    assert r.headers[REQUEST_ID_HEADER] == "trace-abc_1.2"


def test_hostile_request_id_is_replaced_not_reflected(
    probe: TestClient, logs: _Capture
) -> None:
    hostile = "hostile value with spaces " + "x" * 300
    r = probe.get("/ok", headers={REQUEST_ID_HEADER: hostile})
    echoed = r.headers[REQUEST_ID_HEADER]
    assert echoed != hostile
    assert " " not in echoed and len(echoed) <= 128
    # Never reflected into the logs either.
    assert "hostile value" not in logs.rendered()


# --------------------------------------------------------------------------- #
# Structured logging — fields present, no PII
# --------------------------------------------------------------------------- #
def test_2xx_logs_structured_fields_without_query(probe: TestClient, logs: _Capture) -> None:
    probe.get("/ok?q=SECRET_QUERY_VALUE")
    completed = [r for r in logs.records if getattr(r, "status", None) == 200]
    assert completed, "a completed-request line must be logged"
    rec = completed[-1]
    assert rec.method == "GET"
    assert rec.route == "/ok"
    assert isinstance(rec.duration_ms, (int, float))
    assert getattr(rec, "request_id", None)
    assert "SECRET_QUERY_VALUE" not in logs.rendered()


def test_dynamic_route_logs_template_not_raw_path(probe: TestClient, logs: _Capture) -> None:
    probe.get("/items/SECRET-SLUG-42")
    routes = [getattr(r, "route", None) for r in logs.records]
    assert "/items/{item_id}" in routes
    assert "SECRET-SLUG-42" not in logs.rendered()


def test_governed_4xx_is_logged_with_status(probe: TestClient, logs: _Capture) -> None:
    probe.get("/items")  # no trailing segment -> 404 from the router
    statuses = [getattr(r, "status", None) for r in logs.records]
    assert any(s and 400 <= s < 500 for s in statuses)


def test_post_body_pii_never_appears_in_logs(probe: TestClient, logs: _Capture) -> None:
    probe.post(
        "/echo",
        json={
            "contact_email": "buyer@example.com",
            "contact_name": "Jane Buyer",
            "organization": "Acme Robotics Inc",
            "message": "please call me",
        },
        headers={"Authorization": "Bearer super-secret-token", "Cookie": "sid=abc123"},
    )
    blob = logs.rendered()
    for secret in (
        "buyer@example.com",
        "Jane Buyer",
        "Acme Robotics Inc",
        "please call me",
        "super-secret-token",
        "sid=abc123",
    ):
        assert secret not in blob


# --------------------------------------------------------------------------- #
# Unexpected 5xx — logged (exc type only) + re-raised; response sanitized
# --------------------------------------------------------------------------- #
def test_5xx_is_sanitized_and_still_correlated(probe: TestClient, logs: _Capture) -> None:
    r = probe.get("/boom")
    assert r.status_code == 500
    # The generic 500 body must not leak the exception message...
    assert "secret-boom" not in r.text
    assert "user@example.com" not in r.text
    # ...and correlation must SURVIVE the 5xx case (B2): the response carries the id.
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,128}", r.headers.get(REQUEST_ID_HEADER) or "")
    # Our structured line logged the TYPE + a message-free stack + correlation.
    errored = [r for r in logs.records if getattr(r, "status", None) == 500]
    assert errored, "an error line must be logged"
    rec = errored[-1]
    assert rec.exc_type == "RuntimeError"
    assert getattr(rec, "request_id", None)
    assert getattr(rec, "stack", "")  # frames present for debuggability
    blob = logs.rendered()
    for secret in ("secret-boom", "user@example.com", "token=abc123"):
        assert secret not in blob


def test_health_and_ready_are_correlated_and_logged(
    client: TestClient, logs: _Capture, database_url: str
) -> None:
    """R25 health observability: the preserved /health + /ready endpoints stay
    functional and participate in correlation + structured logging."""
    for path in ("/health", "/ready"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert re.fullmatch(
            r"[A-Za-z0-9._-]{1,128}", r.headers.get(REQUEST_ID_HEADER) or ""
        ), f"{path} missing correlation id"
        assert any(
            getattr(rec, "route", None) == path for rec in logs.records
        ), f"{path} not logged"


# --------------------------------------------------------------------------- #
# event_log dormancy (D8): no application writer, and it stays unwritten
# --------------------------------------------------------------------------- #
def test_event_log_has_no_application_writer() -> None:
    """The stronger dormancy proof: no code path can populate `event_log`."""
    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    for path in app_dir.rglob("*.py"):
        if path.name == "event_log.py":  # the model definition itself
            continue
        text = path.read_text(encoding="utf-8")
        constructs = re.search(r"\bEventLog\s*\(", text)  # EventLog(...) instance
        raw_insert = re.search(r"insert\s+into\s+event_log", text, re.IGNORECASE)
        if constructs or raw_insert:
            offenders.append(str(path.relative_to(app_dir)))
    assert offenders == [], f"event_log must stay dormant; writers found: {offenders}"


def test_event_log_stays_empty_after_real_flows(
    client: TestClient, database_url: str
) -> None:
    """Regression: representative read + write flows never populate event_log."""
    from sqlalchemy import text

    from app.db.session import SessionLocal

    assert client.get("/api/robots").status_code == 200
    created = client.post(
        "/api/buyer-requirements",
        json={
            "country": "US",
            "preferred_transaction": "UNKNOWN",
            "raw_input": {
                "wizard_version": 1,
                "answers": {"country": {"state": "ANSWERED", "value": "US"}},
            },
        },
    )
    assert created.status_code == 201
    with SessionLocal() as session:
        count = session.execute(text("SELECT count(*) FROM event_log")).scalar_one()
    assert count == 0
