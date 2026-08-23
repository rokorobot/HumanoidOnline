"""TEMPORARY, one-off diagnostic route — NOT part of the permanent API
surface. Exists solely to exercise the real `_send_email()` path against the
real production Resend configuration: Vercel's Sensitive-typed
`EMAIL_API_KEY` is unreadable through any channel (dashboard, CLI, API) —
the value only ever exists inside the deployed runtime — so this is the only
way to test it without creating a buyer_requirement/commercial_lead row via
a fake Find a Humanoid submission. Removed in a follow-up commit immediately
after its one authorized invocation; it must never remain a standing
feature.

Security: gated by a one-time token supplied via the
`X-Humanoid-Diagnostic-Token` header. Only its SHA-256 hash is committed
here — the raw token was generated locally, never logged, printed, or
committed anywhere, and is known only to the operator invoking this once.
Comparison is constant-time. A missing or wrong token returns 404
(indistinguishable from a nonexistent route) via a FastAPI dependency,
which always runs BEFORE the route body — so `_send_email()` structurally
cannot execute without the correct token.

Zero client input is accepted: no request body, no client-controlled
recipient or content — the subject/text are hardcoded synthetic strings,
never buyer data. No DB session is declared or reachable from this route.
The response never carries the API key, the raw token, the response body,
headers beyond a safe Content-Type media type, or any address/PII — only
the same classification fields `_classify_provider_error()` already
produces for the real notification path.
"""
from __future__ import annotations

import hashlib
import hmac
import urllib.error

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.security.rate_limit import RATE_LIMITER, RateLimitPolicy, rate_limited

# Deliberate reuse of lead_notifications' private internals: this diagnostic
# exists specifically to exercise the SAME send path and SAME response
# classifier the real notification flow uses, not a reimplementation of them.
from app.services.lead_notifications import _classify_provider_error, _send_email

router = APIRouter(tags=["diagnostic-temporary"])

# SHA-256 of the one-time raw token. The raw value exists only in a local,
# uncommitted scratch file, generated for this single diagnostic.
_TOKEN_SHA256 = "6a8b9efc45d21b9db6b9ae19ae000ec9030fec1a73df00c5821b034b7e7d3e15"

# Self-contained policy, not settings-driven — this route does not live long
# enough to warrant a new configurable Setting. At most 1 call/60s, 3/hour,
# so even a discovered path can't be used to spam the real ops inbox.
RATE_LIMITER.set_policy(
    RateLimitPolicy(
        name="resend_diagnostic",
        burst_limit=1,
        burst_window_seconds=60,
        sustained_limit=3,
        sustained_window_seconds=3600,
    )
)


class _DiagnosticResult(BaseModel):
    result: str
    provider_status: int | None = None
    provider_error: str | None = None
    provider_content_type: str | None = None
    provider_body_bytes: int | None = None
    provider_body_is_json: bool | None = None


def _require_diagnostic_token(request: Request) -> None:
    supplied = request.headers.get("X-Humanoid-Diagnostic-Token", "")
    supplied_hash = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(supplied_hash, _TOKEN_SHA256):
        # 404, not 401/403: a wrong guess must not even confirm this route
        # exists, and (as a FastAPI dependency) this raises before the route
        # body runs, so _send_email() is never reached on a bad token.
        raise HTTPException(status_code=404)


@router.post(
    "/api/_internal/resend-probe-09624eaef25ac213",
    response_model=_DiagnosticResult,
    dependencies=[
        Depends(_require_diagnostic_token),
        Depends(rate_limited("resend_diagnostic")),
    ],
)
def resend_probe() -> _DiagnosticResult:
    """Fires exactly one real send through the real production Resend
    configuration with hardcoded synthetic content — no buyer data, no DB
    row created, no DB session used."""
    settings = get_settings()
    to_addrs = (
        [a.strip() for a in settings.lead_notification_to.split(",") if a.strip()]
        if settings.lead_notification_to
        else []
    )
    try:
        _send_email(
            endpoint=settings.email_api_endpoint,
            api_key=settings.email_api_key,
            from_addr=settings.lead_notification_from,
            to_addrs=to_addrs,
            subject="HumanoidOnline Resend diagnostic (not a real lead)",
            text="One-off backend diagnostic. Safe to ignore/delete. No buyer data.",
        )
        return _DiagnosticResult(result="accepted")
    except urllib.error.HTTPError as exc:
        info = _classify_provider_error(exc)
        return _DiagnosticResult(
            result="failed",
            provider_status=exc.code,
            provider_error=info.name,
            provider_content_type=info.content_type,
            provider_body_bytes=info.body_bytes,
            provider_body_is_json=info.is_json,
        )
    except Exception:
        # Not classifiable via _classify_provider_error (HTTPError-specific,
        # e.g. a timeout/connection error) — report failure honestly rather
        # than fabricate fields that don't apply.
        return _DiagnosticResult(result="failed")
