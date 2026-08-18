"""AGENT-02 `get_evidence` — redeem an opaque reference for provenance (`docs/20` §7).

The closing half of the provenance loop. `get_robot` hands out an `evidence_ref`
beside every fact that has evidence; this tool is the only thing that accepts one
back. Together they let an agent check a claim's source without ever seeing a
database identifier.

**The reference is the sole public locator** (§7.1). There is no evidence id, no
`subject_id`, no robot id or slug, no offer or deployment id, no source URL — not
as a fallback, not as an alternative addressing form. Anything else would
reintroduce the raw selector the reference exists to replace.

**A reference is a revocable capability, not a pointer to a row.** Reachability
is re-evaluated on every call against the governed read model (§7.2): the ref
proves it was issued, never that its subject is still eligible. Unpublish the
robot, or supersede the offer, and the same reference stops disclosing anything.

**Two outcomes, split structurally rather than semantically** (§7.3): a token
that is not a reference of this format at all is `INVALID_ARGUMENT`; everything
else — unauthentic, retired key, unknown row, unsupported class, unreachable
subject — is one indistinguishable `NOT_FOUND`. Telling those apart would build a
publication and key-state oracle out of error messages.

No selection happens here. The reference already names one row, and this tool
performs a bounded lookup of exactly that row: `docs/20` §7.1 is explicit that a
reference must not follow "best evidence" and re-point at newer provenance later.
The single canonical selection rule stays in `reads.load_evidence_rows`, where
`get_robot` invoked it when the reference was issued.

Read-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.evidence import EvidenceSource
from app.services.agent_tools.errors import (
    AgentToolError,
    InvalidArgument,
    NotFound,
)
from app.services.agent_tools.projections import (
    CONTRACT_VERSION,
    AgentEvidence,
    build_agent_evidence,
)
from app.services.evidence_refs import (
    EvidenceRefKeyring,
    EvidenceRefKeyUnavailable,
    ResolutionFailure,
    issue_evidence_ref,
    resolve_evidence_ref,
)

#: One public message for every unresolved cause. Held as a constant so the
#: indistinguishability §7.3 requires is a property of the code and not of a
#: programmer remembering to phrase two `raise` statements identically.
NOT_FOUND_MESSAGE = "evidence not found"


@dataclass(frozen=True)
class EvidenceResult:
    """`docs/20` §15 envelope for a single-entity tool.

    `warnings` is present and empty rather than absent: the envelope has one
    shape across the tool surface, and a caller should not have to special-case
    which tools carry the field.
    """

    data: AgentEvidence
    warnings: list[str] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION


def _keyring(keyring: EvidenceRefKeyring | None) -> EvidenceRefKeyring:
    """The evidence-reference keyring, or a closed door (§7.1, §17, §20).

    `INTERNAL`, never `NOT_FOUND`. A misconfigured key means this service cannot
    answer the question; saying "not found" would assert something false about
    the catalogue, and an agent acting on that would conclude a real citation was
    fabricated. The underlying exception names the environment variable and the
    reason, so it is chained for the server's logs and never for the caller.
    """
    if keyring is not None:
        return keyring
    try:
        return EvidenceRefKeyring.from_settings(get_settings())
    except EvidenceRefKeyUnavailable as exc:
        raise AgentToolError("evidence lookup is temporarily unavailable") from exc


def get_evidence(
    session: Session,
    evidence_ref: str,
    *,
    keyring: EvidenceRefKeyring | None = None,
) -> EvidenceResult:
    """Governed provenance for one opaque reference.

    `evidence_ref` is the only contract input (§7). `keyring` is a service
    dependency in the same sense as `session` — it cannot widen what the tool
    discloses, only supply the key with which references are authenticated.
    """
    ring = _keyring(keyring)

    resolved = resolve_evidence_ref(session, evidence_ref, ring)
    if resolved is ResolutionFailure.MALFORMED:
        # Structural, not semantic: this token is not a reference of this format,
        # which says nothing about whether any evidence exists (§7.3).
        raise InvalidArgument("evidence_ref is malformed")
    if resolved is ResolutionFailure.UNRESOLVED:
        raise NotFound(NOT_FOUND_MESSAGE)

    def issue_ref(row: EvidenceSource) -> str:
        # Re-issued rather than echoed back. Issuance is deterministic for a row
        # under a key, so the caller receives the identical string — but it is
        # derived from the resolved row, so a response can never carry a
        # reference that does not address the evidence beside it.
        return issue_evidence_ref(row, ring)

    return EvidenceResult(data=build_agent_evidence(resolved, issue_ref))
