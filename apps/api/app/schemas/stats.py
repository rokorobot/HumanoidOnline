"""Market-snapshot read schema (WS3 homepage index)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MarketSnapshot(BaseModel):
    """Aggregate counts derived entirely from canonical facts/views.

    No new predicate is defined here: obtainability comes from
    `robot_commercial_snapshot` (which uses `commercially_accessible()`).

    Two different dates, never merged: `latest_catalogue_updated_at` is when PUBLIC
    catalogue content last changed (the `catalogue_freshness` row, maintained by
    database triggers inside each committed catalogue write; migration 0026), and
    `latest_observed_at` is the newest evidence observation in `evidence_source`.

    TRACKED vs PUBLISHED are two different facts and are reported separately.
    *Tracked* is what the intelligence catalogue knows about; *published* is the
    editorially approved subset that has a public profile. Reporting a published
    count under a "tracked" label understates what the platform knows, and — on
    a per-manufacturer card — states something false about the manufacturer.
    Obtainability and pilot/deployment counts stay PUBLISHED-scoped: they are
    claims made on public profiles, so they may only count robots that have one.
    """

    total_tracked: int
    total_published: int
    commercially_accessible: int
    in_deployment_or_pilot: int
    manufacturers_tracked: int
    manufacturers_published: int
    rental_offers_present: bool
    latest_observed_at: datetime | None = None
    latest_catalogue_updated_at: datetime | None = None
