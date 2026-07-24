"""Market snapshot — homepage index counts (WS3).

A read-only aggregation over existing canonical facts. Obtainability uses the
`robot_commercial_snapshot` view (canonical `commercially_accessible()`); nothing
here defines a new commercial predicate or business rule.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.stats import MarketSnapshot

router = APIRouter(prefix="/api", tags=["market"])

_SNAPSHOT_SQL = text(
    """
    SELECT
      (SELECT count(*) FROM robot WHERE is_published) AS total_tracked,
      (SELECT count(*) FROM robot_commercial_snapshot s
         JOIN robot r ON r.id = s.id AND r.is_published
         WHERE s.is_obtainable) AS commercially_accessible,
      (SELECT count(*) FROM robot r
         WHERE r.is_published
           AND (r.commercial_status IN ('PILOT', 'RAAS_DEPLOYMENT')
                OR EXISTS (SELECT 1 FROM deployment d WHERE d.robot_id = r.id))
      ) AS in_deployment_or_pilot,
      (SELECT count(DISTINCT manufacturer_id) FROM robot WHERE is_published) AS manufacturers,
      EXISTS (SELECT 1 FROM availability_offer a
              JOIN robot r ON r.id = a.robot_id
              WHERE r.is_published AND a.is_current
                AND a.transaction_type IN ('RENTAL', 'SUBSCRIPTION')
                AND commercially_accessible(a.availability_status)) AS rental_offers_present,
      (SELECT max(observed_at) FROM evidence_source) AS latest_observed_at
    """
)


@router.get("/market-snapshot", response_model=MarketSnapshot)
def market_snapshot(
    session: Annotated[Session, Depends(get_session)]
) -> MarketSnapshot:
    row = session.execute(_SNAPSHOT_SQL).one()
    return MarketSnapshot(
        total_tracked=row.total_tracked,
        commercially_accessible=row.commercially_accessible,
        in_deployment_or_pilot=row.in_deployment_or_pilot,
        manufacturers=row.manufacturers,
        rental_offers_present=row.rental_offers_present,
        latest_observed_at=row.latest_observed_at,
    )
