"""Foundation CLI behavior without a database or external retrieval."""
from __future__ import annotations

import ast
import os
import socket
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from app.cli import discovery_check
from app.db import session as db_session
from app.services.discovery import readiness
from app.services.discovery.readiness import DiscoveryReadiness


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("foundation CLI attempted network access")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


def test_help_and_invalid_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        discovery_check.main(["--help"])
    assert exc.value.code == 0
    assert "status" in capsys.readouterr().out
    for args in ([], ["crawl"], ["run", "--force"]):
        with pytest.raises(SystemExit) as exc:
            discovery_check.main(args)
        assert exc.value.code == 2


@pytest.mark.parametrize("ready", [False, True])
def test_status_distinguishes_prerequisites_from_execution(monkeypatch, capsys, ready):
    report = DiscoveryReadiness(
        baseline_source_present=ready, expected_lead_count=1,
        missing_lead_refs=() if ready else ("maker/model",),
        eligible_source_keys=("manufacturer",) if ready else (),
    )
    monkeypatch.setattr(db_session, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(readiness, "check_readiness", lambda session: report)
    assert discovery_check.main(["status"]) == (0 if ready else 3)
    output = capsys.readouterr().out
    assert f"Prerequisites: {'READY' if ready else 'NOT_READY'}" in output
    assert "Execution: NOT_IMPLEMENTED" in output
    if not ready:
        assert "LEAD_BASELINE_INCOMPLETE" in output
        assert "maker/model" in output


def test_run_never_connects_or_inspects_even_if_setup_is_ready(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("run must be inert, independently of initialization")

    monkeypatch.setattr(db_session, "SessionLocal", forbidden)
    monkeypatch.setattr(readiness, "check_readiness", forbidden)
    assert discovery_check.main(["run"]) == 4
    assert "NOT_IMPLEMENTED" in capsys.readouterr().err


def test_database_error_is_nonzero_and_does_not_disclose_credentials(monkeypatch, capsys):
    def failed():
        raise OperationalError("secret-url", {}, Exception("secret-password"))

    monkeypatch.setattr(db_session, "SessionLocal", failed)
    assert discovery_check.main(["status"]) == 1
    error = capsys.readouterr().err
    assert "STATUS_ERROR" in error
    assert "secret" not in error


def test_fresh_process_without_database_configuration():
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "APP_ENV")}
    for args, expected in [(["--help"], 0), (["run"], 4), (["status"], 1)]:
        result = subprocess.run(
            [sys.executable, "-m", "app.cli.discovery_check", *args],
            env=env, capture_output=True, text=True, check=False,
        )
        assert result.returncode == expected, result.stderr
        assert "Traceback" not in result.stderr


def test_foundation_has_no_browser_dependency_in_app_imports():
    for path in (Path(__file__).resolve().parents[1] / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            assert all(m.split(".")[0] != "playwright" for m in modules), path
