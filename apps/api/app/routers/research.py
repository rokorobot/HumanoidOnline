"""Regional Research Resources (ADR-027): GET /api/research/humanoid-availability/{region}.

Publication-gated. A region is public only when `RESEARCH_PUBLISHED_REGIONS`
(default empty) lists it AND the live data passes the ADR-027 §12 readiness
gate (5 robots / 3 manufacturers, groups reconcile); otherwise it answers 404
unless the caller presents the review token (`X-Research-Preview`). The aggregation is
`services/regional_research`; this router only loads, projects and gates.
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
    result = build_regional_availability(load_regional_snapshot(session, snapshot_date), code)
    # ADR-027 §12: publication needs the owner's flag AND data readiness. A flagged
    # region whose live data no longer passes the gate is not public (it falls back
    # to review-only), rather than silently publishing a thin or inconsistent page.
    ready = result.gate.passes and result.reconciles
    public = flagged and ready
    if not (public or preview):
        raise HTTPException(status_code=404, detail="Not found")

    # The publication gate result is review-only; it is never part of a public body.
    body = build_projection(result, slug, include_readiness=not public)
    body["published"] = public
    response.headers["Cache-Control"] = "public, max-age=300" if public else "no-store"
    if not public:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return body
