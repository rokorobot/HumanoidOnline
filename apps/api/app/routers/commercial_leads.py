"""Commercial-lead write API (API contract §5) — WS7.

`POST /api/commercial-leads` is the first commercial conversion loop and the
point where WS5 anonymity ends (`contact_email` required). The endpoint is a thin
edge: the schema forbids server-owned fields (`extra="forbid"`), and all capture
semantics — requirement locking, persisted-shortlist validation, atomic
create-or-extend, identity-conflict 409, snapshot freeze and PENDING-only
provider routing — live in `app.services.leads`.

There is deliberately NO public GET/PATCH for a lead: the record carries PII and
its `lead_status` lifecycle is admin-only (contract §15, §18).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.commercial_lead import CommercialLeadCreate, CommercialLeadCreated
from app.services.leads import capture_lead

router = APIRouter(prefix="/api/commercial-leads", tags=["commercial-lead"])


@router.post("", response_model=CommercialLeadCreated)
def create_commercial_lead(
    payload: CommercialLeadCreate,
    session: Annotated[Session, Depends(get_session)],
    response: Response,
) -> CommercialLeadCreated:
    """Create a lead (`201`) or extend the requirement's existing lead (`200`).
    The public path always creates/keeps `lead_status='NEW'`."""
    lead, created = capture_lead(session, payload)
    response.status_code = 201 if created else 200
    return CommercialLeadCreated(id=str(lead.id), lead_status=lead.lead_status)
