"""Deterministic buyer-intent matching (WS6).

`engine.match` is the pure scorer (no I/O / clock / randomness / LLM);
`inputs` holds its materialized dataclasses; `repository` (impure) loads
PostgreSQL into those inputs and persists the result.
"""
from app.services.matching.engine import BASE_WEIGHTS, match
from app.services.matching.inputs import (
    MatchOutcome,
    OfferInput,
    PriceInput,
    RequirementInput,
    RobotInput,
    ScoredMatch,
)

__all__ = [
    "BASE_WEIGHTS",
    "MatchOutcome",
    "OfferInput",
    "PriceInput",
    "RequirementInput",
    "RobotInput",
    "ScoredMatch",
    "match",
]
