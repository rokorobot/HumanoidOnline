"""Regional Research Resources (ADR-027): GET /api/research/humanoid-availability/{region}.

Publication lifecycle (ADR-027 §12):

* `RESEARCH_PUBLISHED_REGIONS` (default empty) is the owner's PERSISTENT publication
  decision. A flagged region stays public unless its data is structurally invalid
  (groups do not reconcile, region structure missing, projection failure): then 404.
* The 5 robots / 3 manufacturers threshold is a launch readiness check, verified in
  the review-only preview BEFORE the flag is first set. After publication, a decline
  below it (or evidence ageing) is not a kill switch: the page stays public and
  carries a `publication_health` of LIMITED_EVIDENCE with deterministic reasons.
  Stale offers are never counted as current.
* Not flagged: 404 unless the caller presents the review token (`X-Research-Preview`),
  which returns the full, noindex readiness report.

The aggregation is `services/regional_research`; this router only loads, projects
and gates.
"""
from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_session
from app.services.regional_research.loader import load_regional_snapshot
from app.services.regional_research.projection import REGION_SLUGS, build_projection
from app.services.regional_research.readmodel import build_regional_availability

router = APIRouter(prefix="/api/research", tags=["research"])


def _published(region_slug: str) -> bool:
    configured = {
        s.strip().lower()
        for s in get_settings().research_published_regions.split(",")
        if s.strip()
    }
    return region_slug in configured


def _preview_ok(presented: str | None) -> bool:
    token = get_settings().research_preview_token
    if not token or not presented:
        return False
    return hmac.compare_digest(token.encode(), presented.encode())


@router.get("/humanoid-availability/{region}")
def regional_availability(
    region: str,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    x_research_preview: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    slug = region.lower()
    code = REGION_SLUGS.get(slug)
    flagged = _published(slug)
    preview = _preview_ok(x_research_preview)
    # Unknown region, or neither flagged for publication nor a valid review token:
    # 404, so an unpublished resource's existence is not disclosed.
    if code is None or not (flagged or preview):
        raise HTTPException(status_code=404, detail="Not found")

    snapshot_date = datetime.now(UTC).date()
    try:
        result = build_regional_availability(
            load_regional_snapshot(session, snapshot_date), code
        )
    except ValueError:
        # The region structure is missing from the catalogue: structural failure.
        raise HTTPException(status_code=404, detail="Not found") from None

    # Structural integrity, not evidence health: ordinary ageing or a thin dataset
    # must not take a published resource down (it degrades visibly instead).
    structurally_sound = result.reconciles
    public = flagged and structurally_sound
    if not (public or preview):
        raise HTTPException(status_code=404, detail="Not found")

    try:
        # The review-only gate/readiness report is never part of a public body; the
        # public body carries only the small `publication_health` summary.
        body = build_projection(result, slug, include_readiness=not public)
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Not found") from None
    body["published"] = public
    response.headers["Cache-Control"] = "public, max-age=300" if public else "no-store"
    if not public:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return body
