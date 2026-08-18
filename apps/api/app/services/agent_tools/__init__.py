"""AGENT-02 governed tool layer (`docs/20_AGENT_TOOL_CONTRACT.md`, RATIFIED v0.1).

Transport-independent callables. No MCP, no HTTP routing and no agent-specific
database access live here: every tool terminates in the same governed
service/read layer the website and public API use.

v0.1 surface is exactly three tools. `search_robots` (AGENT-02.1) and
`get_robot` (AGENT-02.2c) are implemented; `get_evidence` follows in its own
slice, and until it does an `evidence_ref` is issued but not yet redeemable
through a tool.
"""
from app.services.agent_tools.errors import (
    AgentToolError,
    InvalidArgument,
    InvalidEnum,
    InvalidPagination,
    NotFound,
)
from app.services.agent_tools.get_robot import (
    NO_CURRENT_AVAILABILITY_OFFER,
    NO_CURRENT_PRICING_OFFER,
    NO_DISPLAY_ELIGIBLE_IMAGE,
    NO_RECORDED_DEPLOYMENT,
    RobotResult,
    get_robot,
)
from app.services.agent_tools.projections import (
    CONTRACT_VERSION,
    AgentAvailabilityOffer,
    AgentDeployment,
    AgentEvidence,
    AgentManufacturerRef,
    AgentPricingOffer,
    AgentRobotDetail,
    AgentRobotListItem,
    canonical_robot_url,
    project_detail,
    project_list_item,
)
from app.services.agent_tools.search_robots import (
    DEFAULT_LIMIT,
    HARD_CONSTRAINT_EXCLUDED_UNKNOWN,
    MAX_LIMIT,
    SearchResult,
    search_robots,
)

__all__ = [
    "AgentAvailabilityOffer",
    "AgentDeployment",
    "AgentEvidence",
    "AgentManufacturerRef",
    "AgentPricingOffer",
    "AgentRobotDetail",
    "AgentRobotListItem",
    "canonical_robot_url",
    "project_detail",
    "project_list_item",
    "AgentToolError",
    "InvalidArgument",
    "InvalidEnum",
    "InvalidPagination",
    "NotFound",
    "CONTRACT_VERSION",
    "DEFAULT_LIMIT",
    "HARD_CONSTRAINT_EXCLUDED_UNKNOWN",
    "MAX_LIMIT",
    "NO_CURRENT_AVAILABILITY_OFFER",
    "NO_CURRENT_PRICING_OFFER",
    "NO_DISPLAY_ELIGIBLE_IMAGE",
    "NO_RECORDED_DEPLOYMENT",
    "RobotResult",
    "SearchResult",
    "get_robot",
    "search_robots",
]
