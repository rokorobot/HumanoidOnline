"""Buyer-intent write schemas (API contract §4) — Pydantic v2.

`POST /api/buyer-requirements` request/response. All fields optional except the
"at least one requirement signal" rule, which is enforced in the router because
an explicitly-UNKNOWN answer (preserved in `raw_input`) also counts as a signal.

Enum values are `Literal`s mirroring db/schema.sql, so a bad enum is a 422 at the
edge. Budget integrity (min<=max; currency required when a numeric budget is
given) is validated here. Canonical resolution (use_case slug / country code ->
ids) happens in the router, which owns the DB.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    """WS5 POST body (API contract §4). WS5 is ANONYMOUS intent: contact identity
    (name / email / organization) is NOT collected here — that is WS7 (commercial
    lead). With extra=forbid, sending a contact field is a 422. Matching and leads
    have no fields here."""

    model_config = ConfigDict(extra="forbid")

    buyer_type: BuyerTypeIn = "UNKNOWN"

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


class BuyerRequirementCreated(BaseModel):
    """`201` response — the persisted requirement's id (kept internal; WS6 will
    use it to generate matches). Not surfaced as a shareable product feature."""

    id: str
