"""Operational email notification for a newly captured/extended commercial
lead (WS7 follow-on). This module is NOT part of the lead-capture transaction:
it is called by the router only AFTER `capture_lead()` has already committed,
and it is a pure side channel — a notification failure can never lose, reject
or retry the persisted lead. The database record remains the sole
authoritative source; this is a best-effort heads-up to HumanoidOnline
operations.

Delivery is synchronous and blocking, with a short fixed timeout, and runs
inline in the request path rather than being deferred to a background task
after the response. This FastAPI backend deploys to Vercel (frontend on
Netlify, database on Neon) — synchronous delivery is simply the smallest way
to guarantee a real attempt happens for every request, without adding a
queue/background-worker dependency for v0.1.

Privacy: the EMAIL this module sends deliberately DOES carry buyer PII — an
internal lead notification is useless without contact details, and it goes
only to HumanoidOnline's own configured operational address. Its LOGS never
do: only `lead_id`, the NEW/UPDATED event, the provider's numeric HTTP
status, its machine-readable error `name` field (e.g. "invalid_api_key" —
never its "message" text), and the exception type are ever logged — never
the recipient, subject, body, headers, API key, or the buyer's email/name/
organization/message. Every field written into the email body comes from
server-owned persisted state (the committed lead row, its frozen
`requirements_snapshot`, and fresh lookups of canonical robot/region facts)
— this module never receives or reads the raw client payload.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.commercial_lead import CommercialLead
from app.models.match_result import MatchResult
from app.models.region import Region
from app.models.robot import Robot

logger = logging.getLogger("app.lead_notifications")

#: The email provider must never be allowed to hold the request open. Fixed
#: for v0.1 (not environment-tunable) — there is no legitimate reason for
#: this to vary per deployment.
_TIMEOUT_SECONDS = 5.0

_UNKNOWN = "UNKNOWN"


def _s(value: Any) -> str:
    """Render a possibly-missing persisted value honestly: UNKNOWN stays
    UNKNOWN, never a fabricated 0 / false / empty string."""
    if value is None:
        return _UNKNOWN
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _email_domain(email: str) -> str | None:
    if "@" not in email:
        return None
    domain = email.rsplit("@", 1)[-1].strip()
    return domain or None


def _subject_identifier(lead: CommercialLead, country_code: str | None) -> str:
    """Organization, else the buyer's email domain, else country — never the
    raw email address (kept out of the subject line only; it is still in the
    body, which is what an internal operational inbox is for)."""
    if lead.organization:
        return lead.organization
    domain = _email_domain(lead.contact_email)
    if domain:
        return domain
    if country_code:
        return country_code
    return _UNKNOWN


def _resolve_region_code(session: Session, region_id: Any) -> str | None:
    if region_id is None:
        return None
    return session.execute(
        select(Region.code).where(Region.id == region_id)
    ).scalar_one_or_none()


def _robot_interest(session: Session, lead: CommercialLead) -> list[str]:
    """Selected robot names + canonical slugs only — the buyer's actual ask."""
    selected_ids = [r.robot_id for r in lead.robots if r.is_selected]
    if not selected_ids:
        return []
    rows = session.execute(
        select(Robot.name, Robot.slug).where(Robot.id.in_(selected_ids))
    ).all()
    return [f"  - {name} ({slug})" for name, slug in rows]


def _match_context(session: Session, lead: CommercialLead) -> list[str]:
    """The full surfaced shortlist with persisted rank/score, server-owned
    only. Empty for a direct Robot-Detail capture (nothing was matched)."""
    if not lead.robots:
        return []
    robot_ids = [r.robot_id for r in lead.robots]
    facts = {
        rid: (name, slug)
        for rid, name, slug in session.execute(
            select(Robot.id, Robot.name, Robot.slug).where(Robot.id.in_(robot_ids))
        ).all()
    }
    ranks: dict[Any, int] = {}
    if lead.requirement_id is not None:
        ranks = dict(
            session.execute(
                select(MatchResult.robot_id, MatchResult.rank).where(
                    MatchResult.requirement_id == lead.requirement_id,
                    MatchResult.robot_id.in_(robot_ids),
                )
            ).all()
        )
    ordered = sorted(
        lead.robots,
        key=lambda r: (ranks.get(r.robot_id) is None, ranks.get(r.robot_id, 0)),
    )
    lines = []
    for r in ordered:
        name, slug = facts.get(r.robot_id, (_UNKNOWN, _UNKNOWN))
        rank = ranks.get(r.robot_id)
        lines.append(
            f"  - {name} ({slug}) — rank: {_s(rank)}, score: {_s(r.match_score)}, "
            f"selected: {'YES' if r.is_selected else 'NO'}"
        )
    return lines


def _build_email(session: Session, lead: CommercialLead, created: bool) -> tuple[str, str]:
    """Returns (subject, plain-text body). Reads ONLY server-owned persisted
    state — the committed lead row, its frozen `requirements_snapshot`, and
    fresh canonical lookups. Never receives the client's raw request payload."""
    event = "NEW" if created else "UPDATED"
    country_code = _resolve_region_code(session, lead.country_region_id)
    subject = (
        f"[HumanoidOnline] {event} commercial lead — "
        f"{_subject_identifier(lead, country_code)}"
    )

    snap = lead.requirements_snapshot or {}
    robot_interest = _robot_interest(session, lead)
    match_context = _match_context(session, lead)

    budget = (
        f"{_s(snap.get('budget_min'))} - {_s(snap.get('budget_max'))} "
        f"{_s(snap.get('budget_currency'))}"
    )

    lines = [
        f"Lead ID: {lead.id}",
        f"Event: {event}",
        f"Created: {_s(lead.created_at)}",
        f"Updated: {_s(lead.updated_at)}",
        "",
        "BUYER",
        f"  Email: {lead.contact_email}",
        f"  Name: {_s(lead.contact_name)}",
        f"  Organization: {_s(lead.organization)}",
        f"  Phone: {_s(lead.contact_phone)}",
        f"  Country: {_s(country_code)}",
        "",
        "COMMERCIAL INTENT",
        f"  Preferred transaction: {_s(lead.preferred_transaction)}",
        f"  Message: {_s(lead.message)}",
        "",
        "REQUIREMENT",
        f"  Requirement ID: {_s(lead.requirement_id)}",
        f"  Use case: {_s(snap.get('use_case'))}",
        f"  Task: {_s(snap.get('task_description'))}",
        f"  Industry: {_s(snap.get('industry'))}",
        f"  Country/deployment region: {_s(snap.get('country'))}",
        f"  Environment: {_s(snap.get('environment'))}",
        f"  Payload (min kg): {_s(snap.get('payload_min_kg'))}",
        f"  Operating hours/day: {_s(snap.get('operating_hours_day'))}",
        f"  Manipulation required: {_s(snap.get('manipulation_required'))}",
        f"  Autonomy: {_s(snap.get('autonomy_required'))}",
        f"  Budget: {budget}",
        f"  Timeline: {_s(snap.get('required_by'))}",
        f"  Transaction preference (requirement): {_s(snap.get('preferred_transaction'))}",
        "",
        "ROBOT INTEREST",
        *(robot_interest or ["  (none selected)"]),
        "",
        "MATCH CONTEXT",
        *(match_context or ["  (no persisted match — direct capture)"]),
        "",
        "This is an internal HumanoidOnline operational notification.",
        "The authoritative lead record remains in the HumanoidOnline database.",
    ]
    return subject, "\n".join(lines)


def _readiness_reason(settings: Settings) -> str | None:
    """`None` means ready to send. Otherwise a short machine-readable reason
    for why not — distinguishes "off on purpose" from "on but incomplete",
    which is a real (and different) production misconfiguration to spot."""
    if not settings.lead_notification_enabled:
        return "disabled"
    if not (
        settings.lead_notification_to
        and settings.lead_notification_from
        and settings.email_api_key
    ):
        return "incomplete_config"
    return None


def _notification_ready(settings: Settings) -> bool:
    """All four of enabled/to/from/key must be set. Anything less is treated
    as "feature not configured", never a boot-time failure (see config.py)."""
    return _readiness_reason(settings) is None


def _send_email(
    *,
    endpoint: str,
    api_key: str,
    from_addr: str,
    to_addrs: list[str],
    subject: str,
    text: str,
) -> None:
    """The one network call in this module. Raises on any failure (timeout,
    connection error, non-2xx status) — the caller is solely responsible for
    containment. Deliberately stdlib-only (`urllib`): a single JSON POST needs
    no provider SDK.

    Sets an explicit application `User-Agent` rather than leaving urllib's
    generic default (`Python-urllib/x.y`) in place — evidence from the
    production diagnostic (a 17-byte, non-JSON, text/plain 403 that never
    reaches Resend's own request log) points at an edge/WAF layer rejecting
    the generic library signature before the request reaches Resend's API,
    not at Resend's application logic itself."""
    body = json.dumps(
        {"from": from_addr, "to": to_addrs, "subject": subject, "text": text}
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "HumanoidOnline/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        response.read()


class _ProviderErrorInfo(NamedTuple):
    """Every observable this module is allowed to log about a failed send,
    all derived from ONE read of the response body — never the body,
    message, or headers themselves. `content_type` is the declared media
    type only (e.g. "application/json"), with any charset/parameter
    stripped; `body_bytes` is the raw byte length; `is_json` and `name`
    come from attempting to parse that same buffer, never a second read."""

    name: str
    content_type: str
    body_bytes: int
    is_json: bool


def _classify_provider_error(exc: urllib.error.HTTPError) -> _ProviderErrorInfo:
    """Reads the failed response body exactly ONCE and derives every
    observable from that single captured buffer — a second read of an
    HTTPError's stream returns nothing, so `name`, `body_bytes` and
    `is_json` must all come from the one buffer captured here, never from
    independent calls to `exc.read()`. Never raises: any header/read/parse
    failure degrades the corresponding field to its safe default rather
    than propagating."""
    content_type = "unknown"
    try:
        raw_ct = exc.headers.get("Content-Type") if exc.headers is not None else None
        if raw_ct:
            content_type = raw_ct.split(";", 1)[0].strip().lower()
    except Exception:
        pass

    try:
        raw = exc.read()
    except Exception:
        raw = b""
    body_bytes = len(raw)

    name = "unknown"
    is_json = False
    try:
        data = json.loads(raw.decode("utf-8"))
        is_json = True
        parsed_name = data.get("name") if isinstance(data, dict) else None
        if isinstance(parsed_name, str) and parsed_name:
            name = parsed_name
    except Exception:
        pass

    return _ProviderErrorInfo(
        name=name, content_type=content_type, body_bytes=body_bytes, is_json=is_json
    )


def notify_lead_captured(session: Session, lead: CommercialLead, created: bool) -> None:
    """Best-effort operational notification. NEVER raises: a failure here must
    never affect the already-committed lead or the HTTP response. Call this
    only AFTER `capture_lead()` has returned (i.e. already committed).

    Every outcome is logged as exactly one of four distinguishable states —
    skipped (disabled), skipped (incomplete_config), attempting, then either
    accepted or failed — so a production log can tell "the feature is off"
    apart from "it's on but broken" apart from "it tried and the provider
    rejected it". No PII, subject, body, recipient or API key ever appears in
    any of these lines; only lead_id, the NEW/UPDATED event, the skip reason,
    the provider's numeric HTTP status, its response's derived shape (see
    `_classify_provider_error`: a machine-readable error `name`, the
    declared Content-Type media type, the raw body's byte length, and
    whether it parsed as JSON — never the body, "message" text, or other
    headers themselves), and the exception TYPE (never str(exc))."""
    settings = get_settings()
    event = "NEW" if created else "UPDATED"
    lead_id = str(lead.id)

    reason = _readiness_reason(settings)
    if reason is not None:
        logger.info(
            "lead notification skipped lead_id=%s event=%s reason=%s",
            lead_id, event, reason,
        )
        return

    logger.info("lead notification attempting lead_id=%s event=%s", lead_id, event)
    try:
        # `expire_on_commit=False` (app/db/session.py) means the in-memory
        # `updated_at` was not refreshed by the DB trigger that just fired on
        # an extend (UPDATE) — reload it so the notification reports the true
        # persisted timestamp rather than a stale pre-update value.
        session.refresh(lead)
        subject, body = _build_email(session, lead, created)
        to_addrs = [a.strip() for a in settings.lead_notification_to.split(",") if a.strip()]
        _send_email(
            endpoint=settings.email_api_endpoint,
            api_key=settings.email_api_key,
            from_addr=settings.lead_notification_from,
            to_addrs=to_addrs,
            subject=subject,
            text=body,
        )
        logger.info("lead notification accepted lead_id=%s event=%s", lead_id, event)
    except urllib.error.HTTPError as exc:
        info = _classify_provider_error(exc)
        logger.error(
            "lead notification failed lead_id=%s event=%s status_class=%sxx "
            "provider_status=%s provider_error=%s provider_content_type=%s "
            "provider_body_bytes=%s provider_body_is_json=%s exc_type=%s",
            lead_id, event, exc.code // 100, exc.code, info.name, info.content_type,
            info.body_bytes, "YES" if info.is_json else "NO", type(exc).__name__,
        )
    except Exception as exc:
        # Deliberately broad: ANY failure while building or sending the
        # notification (network error, timeout, DB hiccup on the post-commit
        # refresh/lookup) must be contained here, never propagate to the
        # router. Message-free by construction — only the exception TYPE is
        # logged, never str(exc), which could echo request data.
        logger.error(
            "lead notification failed lead_id=%s event=%s outcome=error exc_type=%s",
            lead_id, event, type(exc).__name__,
        )
