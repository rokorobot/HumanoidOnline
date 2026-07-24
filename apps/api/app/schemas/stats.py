"""Market-snapshot read schema (WS3 homepage index)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MarketSnapshot(BaseModel):
    """Aggregate counts derived entirely from canonical facts/views.

    No new predicate is defined here: obtainability comes from
    `robot_commercial_snapshot` (which uses `commercially_accessible()`), and
    `latest_observed_at` reflects catalogue freshness from `evidence_source`.
    """

    total_tracked: int
    commercially_accessible: int
    in_deployment_or_pilot: int
    manufacturers: int
    rental_offers_present: bool
    latest_observed_at: datetime | None = None
