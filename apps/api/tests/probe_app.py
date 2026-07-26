"""A minimal app served by REAL uvicorn to probe the COMPLETE process log stream
for PII on an unhandled 500 (WS8.6 / R25 — B1).

Kept separate from the main app so it can carry a route that deliberately raises
an exception whose *message* embeds user-input-like data. `test_observability_
probe.py` runs this under uvicorn and asserts that data never appears in ANY log
output (app.request, uvicorn.error, uvicorn.access, stdout or stderr).
"""
from __future__ import annotations

from fastapi import FastAPI

from app.observability import RequestObservabilityMiddleware, configure_logging

# Production config: JSON logs + uvicorn access log silenced.
configure_logging("production")

app = FastAPI()
app.add_middleware(RequestObservabilityMiddleware)


@app.get("/ok")
def ok() -> dict[str, bool]:
    return {"ok": True}


@app.get("/boom")
def boom() -> None:
    # The message embeds "user input" that must never reach any log.
    raise RuntimeError("secret-boom contact user@example.com token=abc123")
