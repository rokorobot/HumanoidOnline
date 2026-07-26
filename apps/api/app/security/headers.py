"""R4 — explicit cross-origin and security-header posture.

WS8-L9: *absence of middleware is not itself a defect; an unstated, untested
posture is.* Before WS8.1 the API registered no middleware at all, which meant
the effective cross-origin policy was an accident of same-origin browser rules
rather than a decision. This module makes the decision explicit and testable.

**Chosen posture (default): strict same-origin.** `cors_allowed_origins` is
empty, so no CORS middleware is installed and no `Access-Control-Allow-Origin`
is ever emitted. The web tier reaches the API server-side, so no browser
cross-origin access is required. Setting the variable opts into an explicit
allowlist — never a wildcard, never with credentials.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings

#: Applied to every response. Deliberately conservative: this API serves JSON to
#: a server-side caller and an internal admin UI, so it needs no framing, no
#: sniffing and no referrer leakage.
BASE_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

#: Sent only when `enable_hsts` is on. TLS terminates at the ingress (WS8.7), so
#: a non-TLS environment must never advertise HSTS.
HSTS_HEADER = ("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in BASE_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if get_settings().enable_hsts:
            name, value = HSTS_HEADER
            response.headers.setdefault(name, value)
        return response


def parse_allowed_origins(raw: str) -> list[str]:
    """Explicit allowlist only. A `*` entry is dropped: a wildcard is not a
    stated policy, and this API has no cross-origin use case that needs one."""
    return [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*"]


def configure_cors(app: FastAPI) -> list[str]:
    """Install CORS *only* when an explicit allowlist is configured.

    Returns the effective allowlist (empty = strict same-origin) so startup and
    tests can assert the posture that is actually in force.
    """
    origins = parse_allowed_origins(get_settings().cors_allowed_origins)
    if not origins:
        return []

    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type"],
    )
    return origins
