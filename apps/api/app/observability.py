"""WS8.6 / R25 — production logging, request correlation, error observability.

Deployment-appropriate observability built on the standard-library ``logging``
module (no new dependency): one structured line per request carrying a
correlation id, the HTTP method, the matched **route template** (never the raw
path — no slugs/ids), the status and the duration.

Two deliberate design constraints from the WS8.6 review:

1. **Observe, don't handle.** Unhandled exceptions are LOGGED here (with the
   correlation id) and then **re-raised** so the framework's existing error
   machinery produces the response. This layer must never quietly become an
   error-response layer; it does not translate exceptions into responses.

2. **No PII (WS8-L6 / R5).** A request log record never contains a query string,
   request/response body, headers (no ``Authorization``/``Cookie``), the client
   IP, or a raw exception *message* (which could echo user input). On an error
   only the exception *type* and the correlation id are logged as structured
   fields — never the message or a traceback. The full traceback for debugging is
   emitted separately by the framework's own error handler once the re-raise
   reaches it (standard operator logging, outside this structured line).
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

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

    _FIELDS = ("request_id", "method", "route", "status", "duration_ms", "exc_type")

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
    """Assigns/propagates a correlation id, logs one line per request, and logs
    (then re-raises) unexpected exceptions. See the module docstring."""

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
                # Observe only: log a CORRELATED line, then RE-RAISE so the
                # framework's error handling produces the (sanitized) response.
                # We deliberately log only the exception *type* — NOT its message
                # or a traceback — because an exception message can echo user
                # input (R5 / D9). The full traceback for debugging is emitted by
                # the framework/uvicorn error handler when the re-raise reaches
                # it; this structured line stays provably free of request data and
                # correlates it by request_id + route.
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
                    },
                )
                raise
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
