"""Buyer-intent write schemas (API contract §4) — Pydantic v2.

`POST /api/buyer-requirements` request/response. Requirement fields are all
optional except the "at least one requirement signal" rule, enforced in the
router because an explicitly-UNKNOWN answer (preserved in `raw_input`) also
counts as a signal.

`contact_name`, `organization` and `contact_email` are REQUIRED (a product
decision reversing WS5's original anonymous intake — the Find a Humanoid
questionnaire now ends with a contact step before submission). This is
enforced only here (the API edge): the underlying DB columns stay nullable
(`db/schema.sql`) so historical rows captured before this change remain valid.
`contact_phone` is optional and free-text — never format-validated or
normalized, mirroring `app/schemas/commercial_lead.py` exactly (see that
module's docstring for the reasoning). Do not duplicate this validation
elsewhere: both schemas intentionally follow the identical shape.

Enum values are `Literal`s mirroring db/schema.sql, so a bad enum is a 422 at the
edge. Budget integrity (min<=max; currency required when a numeric budget is
given) is validated here. Canonical resolution (use_case slug / country code ->
ids) happens in the router, which owns the DB.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Identical to app/schemas/commercial_lead.py — one @, no surrounding
# whitespace, a dotted domain. Shape only, never proof of delivery.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Same generous cap as commercial_lead.py, for the same reason: a formatted
# international number with an extension, not a shape constraint.
MAX_PHONE = 40


def _clean(value: str | None) -> str | None:
    """Trim; a blank/whitespace string becomes None (never persisted as "")."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


AnswerStateIn = Literal["ANSWERED", "UNKNOWN", "SKIPPED"]

BuyerTypeIn = Literal[
    "COMMERCIAL_BUYER", "TECHNICAL_EVALUATOR", "INDUSTRY_PARTICIPANT", "UNKNOWN"
]
TransactionPreferenceIn = Literal["UNKNOWN", "RENT", "BUY", "LEASE", "RAAS", "FLEXIBLE"]
AutonomyIn = Literal[
    "TELEOPERATED", "ASSISTED", "SUPERVISED_AUTONOMY", "TASK_AUTONOMOUS",
    "HIGHLY_AUTONOMOUS",
]


class BudgetIn(BaseModel):
    """A stated budget. Present only when the buyer answered the BUDGET step."""

    model_config = ConfigDict(extra="forbid")

    currency: str | None = None
    min: Decimal | None = Field(default=None, ge=0)
    max: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check(self) -> BudgetIn:
        has_amount = self.min is not None or self.max is not None
        # No 0/false defaulting: a numeric budget must name its currency; the DB
        # column's DEFAULT 'USD' must never manufacture a currency the buyer never
        # gave (that would fabricate a demand signal).
        if has_amount and not (self.currency and self.currency.strip()):
            raise ValueError("currency is required when a budget amount is given")
        if self.currency is not None and len(self.currency) != 3:
            raise ValueError("currency must be a 3-letter code")
        if self.min is not None and self.max is not None and self.max < self.min:
            raise ValueError("budget max must be >= budget min")
        return self


class RawAnswer(BaseModel):
    """One wizard answer inside raw_input. `state` is validated; the value shape
    varies per step (value / use_case / currency / min / max), so extras are
    allowed and preserved verbatim."""

    model_config = ConfigDict(extra="allow")

    state: AnswerStateIn


class RawInput(BaseModel):
    """Versioned wizard payload. WS5 REQUIRES this — the write path never persists
    an unversioned requirement — and each answer's state must be one of
    ANSWERED / UNKNOWN / SKIPPED so the UNKNOWN vs SKIPPED distinction is real."""

    model_config = ConfigDict(extra="forbid")

    wizard_version: int = Field(ge=1)
    answers: dict[str, RawAnswer]


class BuyerRequirementCreate(BaseModel):
    """WS5 POST body (API contract §4). Matching and leads have no fields here —
    those stay owned by WS6/WS7. With extra=forbid, sending a server-owned field
    (e.g. `lead_status`) is a 422."""

    model_config = ConfigDict(extra="forbid")

    buyer_type: BuyerTypeIn = "UNKNOWN"

    # Required (API-layer only — see module docstring): full name, unsplit.
    contact_name: str
    organization: str
    contact_email: str
    # Optional. Free-text; see module docstring for why it is never normalized.
    contact_phone: str | None = None

    # canonical references (resolved to ids in the router; invalid -> 422 there)
    use_case: str | None = None
    country: str | None = None

    industry: str | None = None
    task_description: str | None = None
    environment: str | None = None

    payload_min_kg: Decimal | None = Field(default=None, ge=0)
    operating_hours_day: Decimal | None = Field(default=None, ge=0)
    # Tri-state on purpose: true / false / null. A known FALSE is a real answer.
    manipulation_required: bool | None = None
    autonomy_required: AutonomyIn | None = None
    budget: BudgetIn | None = None
    required_by: date | None = None

    preferred_transaction: TransactionPreferenceIn = "UNKNOWN"

    # Required, versioned. Preserves ANSWERED/UNKNOWN/SKIPPED per answer.
    raw_input: RawInput

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

    @field_validator("contact_email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        trimmed = (v or "").strip()
        if not _EMAIL_RE.match(trimmed):
            raise ValueError("contact_email must be a valid email address")
        return trimmed

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        cleaned = _clean(v)
        if cleaned is not None and len(cleaned) > MAX_PHONE:
            raise ValueError(f"contact_phone must be at most {MAX_PHONE} characters")
        return cleaned


class BuyerRequirementCreated(BaseModel):
    """`201` response — the persisted requirement's id (kept internal; WS6 will
    use it to generate matches). Not surfaced as a shareable product feature."""

    id: str
