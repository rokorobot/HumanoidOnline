"""AGENT-02 governed tool layer (`docs/20_AGENT_TOOL_CONTRACT.md`, RATIFIED v0.1).

Transport-independent callables. No MCP, no HTTP routing and no agent-specific
database access live here: every tool terminates in the same governed
service/read layer the website and public API use.

v0.1 surface is exactly three tools. Only `search_robots` is implemented so far
(AGENT-02.1); `get_robot` and `get_evidence` follow in their own slices.
"""
from app.services.agent_tools.errors import (
    AgentToolError,
    InvalidArgument,
    InvalidEnum,
    InvalidPagination,
    NotFound,
)
from app.services.agent_tools.search_robots import (
    CONTRACT_VERSION,
    DEFAULT_LIMIT,
    HARD_CONSTRAINT_EXCLUDED_UNKNOWN,
    MAX_LIMIT,
    SearchResult,
    search_robots,
)

__all__ = [
    "AgentToolError",
    "InvalidArgument",
    "InvalidEnum",
    "InvalidPagination",
    "NotFound",
    "CONTRACT_VERSION",
    "DEFAULT_LIMIT",
    "HARD_CONSTRAINT_EXCLUDED_UNKNOWN",
    "MAX_LIMIT",
    "SearchResult",
    "search_robots",
]
