"""AGENT tool error taxonomy (`docs/20` §17).

Transport-independent: these are the *semantic* codes. A binding (MCP, HTTP,
tests) maps them to its own status representation; the code itself is
contractual and must not be renamed without a contract version change.

Errors describe a call that FAILED. They are disjoint from the exclusion reason
codes in `warnings[]` (`docs/20` §10.3), which describe a call that SUCCEEDED
and explain why particular robots are absent from a valid result. A quote-only
robot failing a price ceiling is not an error; a missing `price_currency` is not
a warning.
"""
from __future__ import annotations


class AgentToolError(Exception):
    """Base class carrying a contractual `code` (`docs/20` §17)."""

    code = "INTERNAL"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(AgentToolError):
    """Canonical published entity does not exist, or exists unpublished.

    Deliberately indistinguishable between those two cases so publication state
    cannot be probed (AGENT-01.7).
    """

    code = "NOT_FOUND"


class InvalidEnum(AgentToolError):
    """Value is not a member of the cited `db/schema.sql` enum."""

    code = "INVALID_ENUM"


class InvalidArgument(AgentToolError):
    """Malformed or contradictory input — e.g. `price_max` without
    `price_currency`, or `height_min > height_max`."""

    code = "INVALID_ARGUMENT"


class InvalidPagination(AgentToolError):
    """`limit`/`offset` outside the canonical bounds. Rejected, never clamped
    (`docs/20` §16): clamping would answer a different question than the one
    asked while reporting success."""

    code = "INVALID_PAGINATION"
