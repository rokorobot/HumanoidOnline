"""Regional Research Resources (ADR-027): GET /api/research/humanoid-availability/{region}.

Publication-gated. `RESEARCH_PUBLISHED_REGIONS` (default empty) lists the public
regions; any other region answers 404 unless the caller presents the review
token (`X-Research-Preview`). The aggregation is `services/regional_research`;
this router only loads, projects and gates.
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
    published = _published(slug)
    preview = _preview_ok(x_research_preview)
    # Unknown region, or not published and no valid review token: 404 either way,
    # so an unpublished resource's existence is not disclosed.
    if code is None or not (published or preview):
        raise HTTPException(status_code=404, detail="Not found")

    snapshot_date = datetime.now(UTC).date()
    result = build_regional_availability(load_regional_snapshot(session, snapshot_date), code)
    # The publication gate result is review-only; it is never part of a public body.
    body = build_projection(result, slug, include_readiness=preview and not published)
    body["published"] = published
    response.headers["Cache-Control"] = "public, max-age=300" if published else "no-store"
    if not published:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return body
