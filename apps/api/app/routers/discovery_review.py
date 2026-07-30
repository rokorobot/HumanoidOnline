"""Operator review surface for the discovery queue — READ-ONLY, NON-PUBLIC.

Why this router exists: MANUAL_BOOTSTRAP filled the queue with 43 humanoids and
there was no way to look at them except psql. A reviewer cannot decide what to
trace from a table dump.

Why it is not part of the public API, and must never become so:

  * DATA-D1 §22 / Gate I — the public API does not expose discovery tables, and a
    regression test reads every public surface to prove candidate data never
    appears in one.
  * AGENT-01.7 — machine surfaces expose published canonical rows only.
  * These records are NOT VERIFIED. A public endpoint serving them would let a
    consumer treat "an aggregator says this robot exists" as HumanoidOnline
    saying so, which is the exact confusion the whole contract is built against.

**Fail-closed:** `app.main` mounts this router only when `settings.is_relaxed`
(development / test). In staging and production the routes do not exist — not
hidden behind a flag that could be flipped by configuration, simply absent. That
mirrors how the admin surface fails closed (WS8.1 / R1): the safe state is "not
mounted", and it is reached by default rather than by remembering to disable
something.

**No write path.** Every handler here is a SELECT. There is no POST, PATCH,
PUT or DELETE, and no handler takes a candidate id to act on. Changing a
candidate's state — recording a trace, promoting, rejecting — stays in the
governed CLI where it is attributed to a named human (DATA-D1 §18).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.schemas.common import Page
from app.schemas.discovery_review import DiscoveryCandidateReview

router = APIRouter(prefix="/api/discovery-review", tags=["discovery-review"])

#: Hard ceiling. The review queue is bounded by an explicit maximum rather than
#: served unbounded: 43 candidates today is fine, and the first time acquisition
#: finds 40,000 this endpoint should page rather than try to serialize all of it.
MAX_LIMIT = 100
DEFAULT_LIMIT = 100


@router.get("", response_model=Page[DiscoveryCandidateReview])
def list_discovery_candidates(
    session: Annotated[Session, Depends(get_session)],
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> Page[DiscoveryCandidateReview]:
    """The discovery queue, ordered for human review.

    Sorted by manufacturer then model so the grouping a reviewer thinks in is the
    order the rows arrive in — the UI does not have to re-sort to be readable.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)

    total = session.execute(select(func.count(DiscoveryCandidate.id))).scalar_one()

    rows = session.execute(
        select(DiscoveryCandidate, DiscoverySource)
        .join(DiscoverySource, DiscoveryCandidate.source_id == DiscoverySource.id)
        .order_by(
            DiscoveryCandidate.candidate_manufacturer,
            DiscoveryCandidate.candidate_name,
            DiscoveryCandidate.external_ref,
        )
        .limit(limit)
        .offset(offset)
    ).all()

    items = [
        DiscoveryCandidateReview(
            id=candidate.id,
            candidate_name=candidate.candidate_name,
            candidate_manufacturer=candidate.candidate_manufacturer,
            external_ref=candidate.external_ref,
            discovery_url=candidate.discovery_url,
            # DATA-D1.10 allowlists exactly one free-form key, and `.get` keeps a
            # candidate with no lead as null rather than inventing a URL.
            official_url=(candidate.candidate_data or {}).get("official_url"),
            source_name=source.name,
            source_class=source.source_class,
            status=candidate.status,
            identity_status=candidate.identity_status,
            trace_state=candidate.trace_state,
            discovered_at=candidate.discovered_at,
            last_seen_at=candidate.last_seen_at,
        )
        for candidate, source in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
