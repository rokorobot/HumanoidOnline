"""Read schemas for WS6 matching + the Adjust-Requirements requirement read."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class RequirementRead(BaseModel):
    """Anonymous buyer_requirement (no contact identity) — powers the Adjust
    Requirements prefill. `raw_input` carries the full versioned wizard answers
    (states preserved), which is what the wizard re-seeds from."""

    id: str
    use_case: str | None = None
    country: str | None = None
    industry: str | None = None
    task_description: str | None = None
    environment: str | None = None
    payload_min_kg: float | None = None
    operating_hours_day: float | None = None
    manipulation_required: bool | None = None
    autonomy_required: str | None = None
    budget_currency: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    required_by: date | None = None
    preferred_transaction: str
    raw_input: dict | None = None


class MatchRobotRef(BaseModel):
    slug: str
    name: str
    manufacturer: str


class MatchItem(BaseModel):
    robot: MatchRobotRef
    score: int
    rank: int
    category: str
    score_breakdown: dict[str, float]
    reasons: list[str]
    warnings: list[str]


class MatchResponse(BaseModel):
    requirement_id: str
    matches: list[MatchItem]
    excluded_count: int
    no_match_explanation: str | None = None
