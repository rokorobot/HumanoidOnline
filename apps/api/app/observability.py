"""WS8.6 / R25 — production logging, request correlation, error observability.

Deployment-appropriate observability built on the standard-library ``logging``
module (no new dependency): one structured line per request carrying a
correlation id, the HTTP method, the matched **route template** (never the raw
path — no slugs/ids), the status and the duration.

Two deliberate design constraints from the WS8.6 review:

1. **Contain the error's PII, then correlate.** The default framework/uvicorn
   error handler emits the full traceback INCLUDING the exception message, which
   can echo user input — a real leak demonstrated by the production uvicorn
   no-PII probe (``tests/test_observability_probe.py``). That leak activates the
   review's authorization to add the minimal sanitized unhandled-error mechanism:
   this layer catches an unhandled exception, logs a MESSAGE-FREE record
   (exception type + traceback frames only), and RETURNS a generic 500 that still
   carries the correlation id — so no user-supplied text reaches any log AND
   correlation survives the 5xx case. It handles ONLY genuine unhandled
   exceptions; HTTPException / validation errors are turned into responses by the
   framework before ever reaching this layer.

2. **No PII (WS8-L6 / R5).** A request log record never contains a query string,
   request/response body, headers (no ``Authorization``/``Cookie``), the client
   IP, or a raw exception *message*. The error record carries the exception type
   and the traceback FRAMES only (file/line/func — never the message/args), so it
   is provably free of request data.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

#: The canonical correlation header, echoed on every response and propagated by
#: the web tier (Next) on its governed API calls so a request can be traced
#: across the Next -> FastAPI boundary.
REQUEST_ID_HEADER = "x-request-id"

#: A correlation id is opaque; accept only a conservative charset and bound the
#: length so a hostile inbound value can never inject into a log line or header,
#: nor be reflected verbatim as unbounded/again PII-bearing content.
_MAX_REQUEST_ID_LEN = 128
_REQUEST_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,128}\Z")

#: Bound to the current request so any log emitted while handling it carries the
#: same correlation id without threading it through every call site.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

logger = logging.getLogger("app.request")


def sanitize_request_id(raw: str | None) -> str | None:
    """Accept a client/proxy-supplied correlation id only if it is safe.

    Returns the id when it matches the conservative charset and length bound,
    else ``None`` (the caller then generates a fresh one). This is what stops a
    malicious or oversized ``X-Request-ID`` from being reflected into logs or the
    response header.
    """
    if not raw:
        return None
    if len(raw) > _MAX_REQUEST_ID_LEN:
        return None
    return raw if _REQUEST_ID_RE.match(raw) else None


def new_request_id() -> str:
    return uuid.uuid4().hex


def _route_template(request: Request) -> str:
    """The matched route's path TEMPLATE (e.g. ``/api/robots/{slug}``).

    Never the raw path: a raw path carries slugs/ids and, on an unmatched URL,
    arbitrary client-supplied text. When nothing matched (a 404 for an unknown
    URL) we log a fixed sentinel rather than echo the requested path.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else "<unmatched>"


class JsonLogFormatter(logging.Formatter):
    """Compact JSON lines. Only whitelisted structured fields are emitted, so a
    stray ``extra`` can never leak request data into the log."""

    _FIELDS = (
        "request_id",
        "method",
        "route",
        "status",
        "duration_ms",
        "exc_type",
        "stack",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if "request_id" not in payload:
            payload["request_id"] = request_id_var.get()
        if record.exc_info:
            # Operator-only traceback. It carries stack frames, not request data.
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(app_env: str) -> None:
    """Install structured logging on the ``app`` logger namespace.

    JSON in production/staging (machine-ingestible); human-readable in
    development/test. Idempotent — safe to call once at startup.
    """
    app_logger = logging.getLogger("app")
    for handler in list(app_logger.handlers):
        app_logger.removeHandler(handler)
    handler = logging.StreamHandler()
    if app_env in ("development", "test"):
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s [%(request_id)s] %(message)s")
        )
    else:
        handler.setFormatter(JsonLogFormatter())
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    # Own the output for this namespace; don't also bubble to uvicorn's root.
    app_logger.propagate = False

    # In deployed environments THIS structured, PII-safe line is the access log.
    # uvicorn's default access log records the raw path + query string, which can
    # carry user input (R5 / D9) — silence it so no query string is ever logged.
    # In development/test it stays on for convenience (our line is emitted too).
    if app_env not in ("development", "test"):
        logging.getLogger("uvicorn.access").disabled = True


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a correlation id, logs one line per request, and
    contains unexpected exceptions — logging a message-free record and returning a
    sanitized, still-correlated 500. See the module docstring."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = sanitize_request_id(
            request.headers.get(REQUEST_ID_HEADER)
        ) or new_request_id()
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                # Handle the unhandled exception HERE rather than re-raising.
                #
                # Re-raising would let the framework/uvicorn error handler emit the
                # full traceback INCLUDING the exception message, and an exception
                # message can echo user input (R5 / D9). A production uvicorn probe
                # demonstrated exactly that leak — which activates the WS8.6-review
                # authorization to add the minimal sanitized unhandled-error
                # mechanism. So we log a MESSAGE-FREE record (exception type + the
                # traceback FRAMES only — file/line/func, never the message/args)
                # and return a generic 500 that still carries the correlation id.
                # Nothing user-supplied reaches any log, and correlation survives
                # the 5xx case.
                duration_ms = round((time.perf_counter() - start) * 1000, 1)
                logger.error(
                    "request errored",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "route": _route_template(request),
                        "status": 500,
                        "duration_ms": duration_ms,
                        "exc_type": type(exc).__name__,
                        # Location-only frames (file:line:func) — deliberately NOT
                        # the source lines, so no source literal (nor the message)
                        # can carry data into the log. Enough to locate the fault.
                        "stack": " <- ".join(
                            f"{f.filename}:{f.lineno}({f.name})"
                            for f in traceback.extract_tb(exc.__traceback__)
                        ),
                    },
                )
                response = JSONResponse(
                    status_code=500, content={"detail": "Internal Server Error"}
                )
                response.headers[REQUEST_ID_HEADER] = request_id
                return response
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "route": _route_template(request),
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            request_id_var.reset(token)
