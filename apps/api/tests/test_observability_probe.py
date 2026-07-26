"""WS8.6 / R25 — B1: no PII anywhere in the COMPLETE deployed log stream.

TestClient exercises the ASGI app directly and never invokes uvicorn's error
logging, so a unit test cannot see a framework traceback leak. This probe runs
the app under a REAL uvicorn process, captures its entire stdout+stderr, triggers
an unhandled 500 whose exception message embeds user-input-like data, and asserts
that data appears in NO log output — proving the sanitized unhandled-error
mechanism contains it (and that correlation survives the 5xx case).
"""
from __future__ import annotations

import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

API_DIR = pathlib.Path(__file__).resolve().parents[1]
PII = ("user@example.com", "token=abc123", "secret-boom")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(url: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"probe server not ready at {url}")


def test_no_pii_in_full_uvicorn_log_stream_on_500() -> None:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "APP_ENV": "production"}
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "tests.probe_app:app",
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "info",
        ],
        cwd=str(API_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    boom_status = None
    boom_body = ""
    boom_rid = None
    ok_rid = None
    try:
        _wait_ready(f"{base}/ok")
        with urllib.request.urlopen(f"{base}/ok") as r:
            ok_rid = r.headers.get("x-request-id")
        try:
            urllib.request.urlopen(f"{base}/boom")
        except urllib.error.HTTPError as e:  # 500 arrives as HTTPError
            boom_status = e.code
            boom_body = e.read().decode("utf-8", "replace")
            boom_rid = e.headers.get("x-request-id")
    finally:
        proc.terminate()
        try:
            output = proc.communicate(timeout=10)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            output = proc.communicate()[0]

    output = output or ""

    # Correlation works on 2xx and, crucially, survives the 5xx case (B2).
    assert ok_rid and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", ok_rid)
    assert boom_status == 500
    assert boom_rid and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", boom_rid)

    # The generic 500 body leaks nothing.
    for secret in PII:
        assert secret not in boom_body

    # THE gate (B1): no PII anywhere in the entire process log stream — including
    # any framework/uvicorn error output, not just our structured line.
    for secret in PII:
        assert secret not in output, (
            f"PII {secret!r} leaked into the deployed log stream:\n{output[-3000:]}"
        )

    # Sanity: logging is actually active (the error WAS recorded, sans PII).
    assert "request errored" in output


if __name__ == "__main__":  # allow a quick standalone run
    test_no_pii_in_full_uvicorn_log_stream_on_500()
    print("probe OK")
