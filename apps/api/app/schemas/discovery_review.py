"""Operator review projection of the discovery queue — DATA-D1 §22 / Gate I.

**This is not a catalogue schema.** It exists so a human can look at what
acquisition has found and decide what to trace, and every field choice is made
against one risk: that a NONCANONICAL candidate gets mistaken for a verified
robot somewhere downstream.

So the projection deliberately omits everything that could be read as a product
fact — no specifications, no price, no availability, no maturity, no imagery, no
claims. What is left is identity, provenance and queue position: who says this
exists, where they say it, and how far through the pipeline it has got. A field
that cannot be shown without implying verification is not in this model.

`docs/11` §22 keeps discovery data off the public API and `docs/16` §17 keeps
review on operator surfaces. The router that serves this is mounted only in
relaxed environments (see `app/routers/discovery_review.py`), so this schema has
no production surface at all.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class DiscoveryCandidateReview(BaseModel):
    """One row of the review queue.

    Every optional field is `None` when absent — never `""` or a placeholder
    (AGENTS.md rule 6). A candidate with no official-URL lead is a candidate with
    nothing to trace yet, and saying so plainly is the point.
    """

    #: Opaque identifier, for the operator to hand to the promotion CLI. Accepted
    #: from the client for NOTHING: this API has no write path (§ security).
    id: uuid.UUID

    # --- identity, as CLAIMED by the source (never as fact) ------------------
    candidate_name: str | None = None
    candidate_manufacturer: str | None = None
    external_ref: str

    # --- where it came from --------------------------------------------------
    discovery_url: str | None = None
    #: The `official_url` LEAD from `candidate_data` (DATA-D1.10 allowlist). A
    #: lead is not a trace: it is where to look, not proof of anything (H2).
    official_url: str | None = None
    source_name: str
    source_class: str

    # --- queue position ------------------------------------------------------
    #: DISCOVERED / IDENTITY_REVIEW / ... — never a commercial status.
    status: str
    identity_status: str
    #: NOT_TRACED until a human records an authoritative trace (gate P2).
    trace_state: str

    discovered_at: datetime
    last_seen_at: datetime
