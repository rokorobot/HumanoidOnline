"""Commercial-lead write schemas (API contract §5) — Pydantic v2.

`POST /api/commercial-leads` request/response. This is the first commercial
conversion and the point where WS5 anonymity ends: `contact_email` is required.

`contact_name` and `organization` are ALSO required as of the Find a Humanoid
contact-information enhancement — a deliberate reversal of the original
"identity is light-touch" design, not an oversight. This is enforced only here
(the API edge): the underlying `contact_name`/`organization` DB columns stay
nullable (`db/schema.sql`) so historical rows captured before this change
remain valid, and the create-or-extend service logic still fills a currently-
NULL lead value rather than requiring a DB migration to backfill one.

`contact_phone` is optional and free-text — never format-validated or
normalized, since international phone formats vary too widely to police safely
without rejecting valid numbers.

The client owns ONLY its contact information and declared commercial intent. The
server owns lead status, match scores, robot validation, provider routing, the
requirements snapshot and all timestamps. `extra="forbid"` therefore makes any
attempt to send `lead_status`, `outcome`, `match_score`, provider ids/status,
`contacted_at`, payment/price/commission fields a 422 at the edge (contract §18).

Canonical resolution (country code -> COUNTRY region id, robot slugs -> ids) and
all persistence semantics live in the service, which owns the DB.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

# Deliberately pragmatic: one @, no surrounding whitespace, a dotted domain. We
# validate shape only (a real address is proven by contacting it, later phases),
# and avoid taking on the email-validator dependency.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Generous cap for a formatted international number with an extension
# ("+1 (555) 123-4567 ext. 89") — not a shape constraint, just an abuse bound.
MAX_PHONE = 40

# None means "not provided" -> inherit the requirement (or UNKNOWN for a direct
# capture). This is distinct from the client explicitly sending "UNKNOWN".
TransactionPreferenceIn = Literal["UNKNOWN", "RENT", "BUY", "LEASE", "RAAS", "FLEXIBLE"]


def _clean(value: str | None) -> str | None:
    """Trim; a blank/whitespace string becomes None (never persisted as "")."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


class CommercialLeadCreate(BaseModel):
    """WS7 POST body (API contract §5). No payment fields — ever, in v0.1. No
    provider ids, no lead-status, no match scores from the browser: those are
    server-owned and rejected by extra=forbid."""

    model_config = ConfigDict(extra="forbid")

    # null for a direct Robot-Detail capture; a uuid for a /matches/[id] capture.
    requirement_id: str | None = None

    # Required (API-layer only — see module docstring): full name, unsplit.
    contact_name: str
    contact_email: str
    organization: str

    # Optional. Free-text; see module docstring for why it is never normalized.
    contact_phone: str | None = None

    # canonical COUNTRY code (resolved to an id in the service; invalid -> 422).
    country: str | None = None

    # For a matched requirement: a subset of the persisted shortlist (the buyer's
    # selection). For zero-match: must be []. For a direct capture: the robot(s)
    # being requested. Validated against persisted state in the service.
    robot_slugs: list[str] = []

    preferred_transaction: TransactionPreferenceIn | None = None

    message: str | None = None

    @field_validator("contact_email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        trimmed = (v or "").strip()
        if not _EMAIL_RE.match(trimmed):
            raise ValueError("contact_email must be a valid email address")
        return trimmed

    @field_validator("contact_name")
    @classmethod
    def _name(cls, v: str) -> str:
        cleaned = _clean(v)
        if cleaned is None:
            raise ValueError("contact_name is required")
        if len(cleaned) > 200:
            raise ValueError("contact_name must be at most 200 characters")
        return cleaned

    @field_validator("organization")
    @classmethod
    def _org(cls, v: str) -> str:
        cleaned = _clean(v)
        if cleaned is None:
            raise ValueError("organization is required")
        if len(cleaned) > 300:
            raise ValueError("organization must be at most 300 characters")
        return cleaned

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        # Trim + cap only — deliberately no shape/format regex (module
        # docstring): a generous cap accommodates real formatted numbers
        # ("+1 (555) 123-4567 ext. 89") without rejecting valid international
        # input this project has no authority to normalize.
        cleaned = _clean(v)
        if cleaned is not None and len(cleaned) > MAX_PHONE:
            raise ValueError(f"contact_phone must be at most {MAX_PHONE} characters")
        return cleaned

    @field_validator("message")
    @classmethod
    def _message(cls, v: str | None) -> str | None:
        cleaned = _clean(v)
        if cleaned is not None and len(cleaned) > 4000:
            raise ValueError("message must be at most 4000 characters")
        return cleaned

    @field_validator("country")
    @classmethod
    def _country(cls, v: str | None) -> str | None:
        return _clean(v)

    @field_validator("robot_slugs")
    @classmethod
    def _slugs(cls, v: list[str]) -> list[str]:
        # De-duplicate while preserving order; drop blanks. Membership/whitelist
        # validation against persisted state happens in the service.
        seen: set[str] = set()
        out: list[str] = []
        for s in v:
            cleaned = _clean(s)
            if cleaned is not None and cleaned not in seen:
                seen.add(cleaned)
                out.append(cleaned)
        return out


class CommercialLeadCreated(BaseModel):
    """`201` (first capture) / `200` (existing requirement-linked lead extended)
    response. Only the id and the (always-'NEW' at capture) lead_status — the
    record itself carries PII and has no public read endpoint (contract §15)."""

    id: str
    lead_status: str
