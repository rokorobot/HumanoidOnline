"""AGENT-02 `get_robot` — full governed detail for one published robot (`docs/20` §6).

Transport-independent, like `search_robots`: a plain callable taking a session
and a canonical slug. The ratified read path is

    reads.load_detail → reads.serialize_detail → the agent projection

and nothing here reaches around it. The publication predicate lives inside the
shared loader, so this tool cannot forget it and has no parameter with which a
caller could ask for an unpublished robot (AGENT-01.7, §14). Agent code must not
import the HTTP router's private helper (§6) — that would invert `docs/18` §18.1's
layering, in which the agent sits *behind* the governed services rather than
behind the HTTP binding.

Evidence is selected **once**. `load_evidence_rows` runs a single canonical
best-evidence pass over the detail's subjects; those exact rows are handed to
`serialize_detail` and reused by the projection, so the metadata the response
shows and the row an `evidence_ref` addresses cannot come from two different
selections (§13.1).

Read-only. Creates nothing, mutates nothing, and exposes only published canonical
robots.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.evidence import EvidenceSource
from app.services import reads
from app.services.agent_tools.errors import AgentToolError, NotFound
from app.services.agent_tools.projections import (
    CONTRACT_VERSION,
    AgentRobotDetail,
    project_detail,
)
from app.services.evidence_refs import (
    EvidenceRefKeyring,
    EvidenceRefKeyUnavailable,
    issue_evidence_ref,
)

#: `docs/20` §6.1 — the four frozen absence notices. Each says *nothing is on
#: record here*, and each is explicitly not the negative claim a reader might
#: infer: empty pricing is not "free", empty availability is not "unavailable"
#: (NOT_AVAILABLE is a positive fact needing evidence, §11), no recorded
#: deployment is not "never deployed", and no display-eligible image is not "no
#: image record exists" — only that none passed the MEDIA-01 gate.
NO_CURRENT_PRICING_OFFER = "no_current_pricing_offer"
NO_CURRENT_AVAILABILITY_OFFER = "no_current_availability_offer"
NO_RECORDED_DEPLOYMENT = "no_recorded_deployment"
NO_DISPLAY_ELIGIBLE_IMAGE = "no_display_eligible_image"


@dataclass(frozen=True)
class RobotResult:
    """`docs/20` §15 envelope for a single-entity tool.

    No `pagination`: that block appears only for paged tools.
    """

    data: AgentRobotDetail
    warnings: list[str] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION


def _keyring(keyring: EvidenceRefKeyring | None) -> EvidenceRefKeyring:
    """The evidence-reference keyring, or a closed door (`docs/20` §7.1, §17).

    Resolved **eagerly**, before the robot is even looked up, and uniformly for
    every robot. Deferring it until the first evidenced fact would make the call
    succeed or fail depending on whether *this* robot has evidence, which turns a
    misconfiguration into a weak oracle about catalogue contents; it would also
    let a broken deployment quietly serve detail with the provenance stripped
    out, which is precisely the outcome §7.1 exists to prevent.

    The failure is `INTERNAL` with generic public text. The underlying exception
    names the environment variable and the reason, so it is chained for the
    server's own logs and never for the caller: an agent must not be able to read
    key state, key ids, or configuration detail out of an error message (§20).
    """
    if keyring is not None:
        return keyring
    try:
        return EvidenceRefKeyring.from_settings(get_settings())
    except EvidenceRefKeyUnavailable as exc:
        raise AgentToolError("robot detail is temporarily unavailable") from exc


def get_robot(
    session: Session,
    slug: str,
    *,
    keyring: EvidenceRefKeyring | None = None,
) -> RobotResult:
    """Full governed detail for one published canonical robot.

    `slug` is the only contract input (§6): there is no UUID, no evidence id, no
    publication flag, no `include_unpublished`, and no alias form. Matching is
    exact and case-sensitive.

    `keyring` is a service dependency, not a contract input — the same kind of
    injection as `session`. It exists so a caller can supply a keyring rather
    than the process settings; it cannot widen what the tool returns.
    """
    if not isinstance(slug, str):
        # Not InvalidArgument: §6 admits exactly one addressing form, so a
        # non-slug is simply not an address of anything.
        raise NotFound("robot not found")

    ring = _keyring(keyring)

    robot = reads.load_detail(session, slug)
    if robot is None:
        # One message for "does not exist" and for "exists but unpublished".
        # A distinguishable answer would let publication state be probed one
        # slug at a time (AGENT-01.7, §6).
        raise NotFound("robot not found")

    # One canonical selection, reused by both consumers below.
    evidence_rows = reads.load_evidence_rows(session, reads.detail_subject_ids(robot))
    detail = reads.serialize_detail(session, robot, evidence_rows=evidence_rows)

    def issue_ref(row: EvidenceSource) -> str:
        return issue_evidence_ref(row, ring)

    data = project_detail(detail, robot, evidence_rows, issue_ref)

    # Derived from the GOVERNED serialization, never from raw table contents:
    # `no_display_eligible_image` must mean "nothing passed MEDIA-01", which is a
    # statement about `detail.images` and not about whether a `robot_image` row
    # exists. Reading the tables directly here would quietly redefine all four.
    warnings = [
        code
        for code, empty in (
            (NO_CURRENT_PRICING_OFFER, not detail.pricing_offers),
            (NO_CURRENT_AVAILABILITY_OFFER, not detail.availability_offers),
            (NO_RECORDED_DEPLOYMENT, not detail.deployments),
            (NO_DISPLAY_ELIGIBLE_IMAGE, not detail.images),
        )
        if empty
    ]

    return RobotResult(
        data=data,
        # Sorted and deduplicated (§15): a caller diffing two responses should
        # see a change in meaning, never a change in ordering.
        warnings=sorted(set(warnings)),
    )
