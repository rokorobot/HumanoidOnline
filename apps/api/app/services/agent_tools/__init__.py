"""AGENT-02 governed tool layer (`docs/20_AGENT_TOOL_CONTRACT.md`, RATIFIED v0.1).

Transport-independent callables. No MCP, no HTTP routing and no agent-specific
database access live here: every tool terminates in the same governed
service/read layer the website and public API use.

v0.1 surface is exactly three tools, and all three are now implemented:
`search_robots` (AGENT-02.1), `get_robot` (AGENT-02.2c) and `get_evidence`
(AGENT-02.2d), which closes the provenance loop — a reference handed out beside a
fact is redeemable for that fact's source, and for nothing else.

The MCP binding is still pending, so these remain callables with no transport.
"""
from app.services.agent_tools.errors import (
    AgentToolError,
    InvalidArgument,
    InvalidEnum,
    InvalidPagination,
    NotFound,
)
from app.services.agent_tools.get_evidence import (
    NOT_FOUND_MESSAGE,
    EvidenceResult,
    get_evidence,
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
    build_agent_evidence,
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
    "build_agent_evidence",
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
    "NOT_FOUND_MESSAGE",
    "NO_CURRENT_AVAILABILITY_OFFER",
    "NO_CURRENT_PRICING_OFFER",
    "NO_DISPLAY_ELIGIBLE_IMAGE",
    "NO_RECORDED_DEPLOYMENT",
    "EvidenceResult",
    "RobotResult",
    "SearchResult",
    "get_evidence",
    "get_robot",
    "search_robots",
]
