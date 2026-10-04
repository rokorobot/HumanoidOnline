"""G5-4 — the HUMAN REVIEW summary of a discovery cycle: the actionable queue, counted and digested.

Actionable work is exactly (1) proposals that still need a human decision and can be decided
(current, non-stale), (2) unresolved identity-review items, and (3) planner targets that need a
source-policy decision (SOURCE_REVIEW_REQUIRED). The DB is canonical; this is a read-only summary.

The digest is a hash of the sorted, tagged identifiers of the actionable queue, so the same
unresolved queue always yields the same digest: no timestamps, run ids or counts-by-run enter it.
`new_this_cycle` separates work created by this cycle from the standing queue, so a quiet recurring
scan does not look like a discovery event just because old review work is still open.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy.orm import Session

from app.services.discovery import proposal_review as pr
from app.services.discovery.review import review_queue


def queue_digest(proposals: Iterable[str], identity: Iterable[str], source: Iterable[str]) -> str:
    lines = sorted({*(f"proposal:{p}" for p in proposals), *(f"identity:{i}" for i in identity),
                    *(f"source:{s}" for s in source)})
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def summarize(proposals: Iterable[str], identity: Iterable[str], source: Iterable[str],
              new_proposals: int = 0, new_identity: int = 0) -> dict:
    p, i, s = sorted(set(proposals)), sorted(set(identity)), sorted(set(source))
    return {
        "complete": True,
        "proposals_awaiting_decision": len(p), "identity_review_items": len(i),
        "source_review_items": len(s), "total": len(p) + len(i) + len(s),
        "new_this_cycle": {"proposals": new_proposals, "identity_items": new_identity,
                           "total": new_proposals + new_identity},
        "standing_queue": len(p) + len(i) + len(s) - new_proposals - new_identity,
        "queue_digest": queue_digest(p, i, s),
    }


def incomplete(reason: str) -> dict:
    """The queue could not be established: nothing may be inferred (an issue is never closed)."""
    return {"complete": False, "reason": reason, "queue_digest": None, "total": None}


def compute(session: Session, started_at: datetime, source_items: Iterable[str],
            new_identity: int = 0) -> dict:
    """The actionable queue from the live database. SELECT only; never raises into the cycle."""
    try:
        states = [s for s in pr.list_proposals(session) if s.acceptable]
        ids = [s.proposal.digest for s in states]
        new = sum(1 for s in states if s.proposal.created_at >= started_at)
        identity = [f"{q.kind}:{','.join(sorted(map(str, q.candidate_ids)))}"
                    for q in review_queue(session)]
        return summarize(ids, identity, source_items, new, min(new_identity, len(identity)))
    except Exception as exc:  # noqa: BLE001 - informational; an incomplete queue never closes an issue
        return incomplete(type(exc).__name__)


def lines(hr: dict | None) -> list[str]:
    if hr is None:
        return ["HUMAN REVIEW", "  unavailable this cycle (informational; not an error)"]
    if not hr.get("complete"):
        return ["HUMAN REVIEW", f"  queue could not be established ({hr.get('reason')}); "
                "nothing is inferred"]
    n = hr["new_this_cycle"]
    return ["HUMAN REVIEW",
            f"  proposals awaiting decision={hr['proposals_awaiting_decision']}  "
            f"identity review={hr['identity_review_items']}  "
            f"source review={hr['source_review_items']}",
            f"  new this cycle={n['total']} (proposals {n['proposals']}, identity "
            f"{n['identity_items']})  standing queue={hr['standing_queue']}",
            f"  queue digest={hr['queue_digest'][:16]}"]
