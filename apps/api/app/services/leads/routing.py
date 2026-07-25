"""Deterministic provider routing for a commercial lead (WS7 §13).

WS7 activates the routing *mechanism*, not fulfilment: a candidate route is
written with status='PENDING' and contacted_at=NULL. A PENDING route means an
eligible provider exists — it never means HumanoidOnline contacted anyone. No
email, webhook, CRM push or provider notification happens here.

A route (provider × selected-robot) is eligible only when ALL hold:
  - provider.is_active AND provider.accepts_leads
  - the provider owns a *current, accessible* availability_offer for that robot
    (the canonical accessibility law: is_current AND availability_status NOT IN
    (NOT_AVAILABLE, DISCONTINUED)) — the same predicate used everywhere else
  - the offer's transaction_type is compatible with the lead's preference
    (RENT->RENTAL, BUY->PURCHASE, LEASE->LEASE, RAAS->RAAS; FLEXIBLE/UNKNOWN ->
    any mode)
  - the offer's geography applies to the lead's country (exact / ancestor region
    / GLOBAL / region-agnostic NULL, via the canonical region hierarchy). When
    the lead states no country, geography is not a constraint.

Because the verified catalogue does not assert accepts_leads=true on any
provider, this legitimately yields zero routes in production — the mechanism is
proven with controlled fixtures, never by fabricating commercial partnerships
(WS7 §14).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial import AvailabilityOffer
from app.models.commercial_lead import CommercialLead, CommercialLeadProvider
from app.models.manufacturer import Provider
from app.models.region import Region

# availability_status values that mean "not obtainable" — excluded from routing.
_INACCESSIBLE = ("NOT_AVAILABLE", "DISCONTINUED")

# Buyer preference -> the offer transaction_type(s) it is compatible with. A
# preference absent from this map (FLEXIBLE / UNKNOWN) matches any mode.
_PREFERENCE_TO_TXN: dict[str, set[str]] = {
    "RENT": {"RENTAL"},
    "BUY": {"PURCHASE"},
    "LEASE": {"LEASE"},
    "RAAS": {"RAAS"},
}


def _applicable_region_ids(session: Session, region_id: uuid.UUID) -> set[uuid.UUID]:
    """A region + its ancestor regions (economic zone, continent, ...) + GLOBAL —
    the regions whose offers apply to a buyer located in `region_id`. Mirrors the
    matching repository's country->applicable-regions walk, keyed by id."""
    ids: set[uuid.UUID] = {region_id}
    parent = session.execute(
        select(Region.parent_id).where(Region.id == region_id)
    ).scalar_one_or_none()
    while parent is not None:
        ids.add(parent)
        parent = session.execute(
            select(Region.parent_id).where(Region.id == parent)
        ).scalar_one_or_none()
    global_id = session.execute(
        select(Region.id).where(Region.code == "GLOBAL")
    ).scalar_one_or_none()
    if global_id is not None:
        ids.add(global_id)
    return ids


def route_providers(session: Session, lead: CommercialLead) -> int:
    """Create any missing PENDING routes for the lead's SELECTED robots and
    return the number of routes newly created. Idempotent: existing (lead,
    provider, robot) routes are left untouched, so re-running on an extended lead
    never duplicates rows (the UNIQUE(lead_id, provider_id, robot_id) also
    guards this). Never mutates or auto-contacts an existing route."""
    selected_robot_ids = [r.robot_id for r in lead.robots if r.is_selected]
    if not selected_robot_ids:
        return 0

    country_known = lead.country_region_id is not None
    applicable = (
        _applicable_region_ids(session, lead.country_region_id) if country_known else set()
    )
    compatible_txn = _PREFERENCE_TO_TXN.get(lead.preferred_transaction)  # None => any

    existing = {
        (r.provider_id, r.robot_id) for r in lead.providers
    }

    # Candidate offers: current + accessible, for a selected robot, owned by an
    # active lead-accepting provider. Transaction and geography are filtered in
    # Python against the canonical hierarchy (keeps this readable and matches the
    # matcher's approach).
    rows = session.execute(
        select(
            AvailabilityOffer.provider_id,
            AvailabilityOffer.robot_id,
            AvailabilityOffer.transaction_type,
            AvailabilityOffer.region_id,
        )
        .join(Provider, Provider.id == AvailabilityOffer.provider_id)
        .where(
            AvailabilityOffer.robot_id.in_(selected_robot_ids),
            AvailabilityOffer.is_current.is_(True),
            AvailabilityOffer.availability_status.notin_(_INACCESSIBLE),
            AvailabilityOffer.provider_id.is_not(None),
            Provider.is_active.is_(True),
            Provider.accepts_leads.is_(True),
        )
    ).all()

    created = 0
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for provider_id, robot_id, txn, region_id in rows:
        if compatible_txn is not None and txn not in compatible_txn:
            continue
        geo_ok = (not country_known) or region_id is None or region_id in applicable
        if not geo_ok:
            continue
        key = (provider_id, robot_id)
        if key in existing or key in seen:
            continue
        seen.add(key)
        lead.providers.append(
            CommercialLeadProvider(
                provider_id=provider_id,
                robot_id=robot_id,
                status="PENDING",
                contacted_at=None,
            )
        )
        created += 1
    return created
