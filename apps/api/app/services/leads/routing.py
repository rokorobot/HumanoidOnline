"""Deterministic provider routing for a commercial lead (WS7 §13).

WS7 activates the routing *mechanism*, not fulfilment: a candidate route is
written with status='PENDING' and contacted_at=NULL. A PENDING route means an
eligible provider exists — it never means HumanoidOnline contacted anyone. No
email, webhook, CRM push or provider notification happens here.

A route (provider × selected-robot) is eligible only when ALL hold:
  - provider.is_active AND provider.accepts_leads
  - the provider owns an availability_offer for that robot that is
    `is_current AND commercially_accessible(availability_status)` — the CANONICAL
    DB predicate (schema.sql), never an ad-hoc status list. WAITLIST / PREORDER /
    LIMITED / ON_REQUEST / AVAILABLE all count; NOT_AVAILABLE / DISCONTINUED do not.
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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.commercial import AvailabilityOffer
from app.models.commercial_lead import CommercialLead, CommercialLeadProvider
from app.models.manufacturer import Provider
from app.models.region import Region

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


def _eligible_routes(session: Session, lead: CommercialLead) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """The set of (provider_id, robot_id) pairs eligible for a PENDING route for
    the lead's SELECTED robots, applying the canonical accessibility predicate +
    transaction + geography compatibility."""
    selected_robot_ids = [r.robot_id for r in lead.robots if r.is_selected]
    if not selected_robot_ids:
        return set()

    country_known = lead.country_region_id is not None
    applicable = (
        _applicable_region_ids(session, lead.country_region_id) if country_known else set()
    )
    compatible_txn = _PREFERENCE_TO_TXN.get(lead.preferred_transaction)  # None => any

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
            # CANONICAL access predicate — never an ad-hoc status list.
            func.commercially_accessible(AvailabilityOffer.availability_status),
            AvailabilityOffer.provider_id.is_not(None),
            Provider.is_active.is_(True),
            Provider.accepts_leads.is_(True),
        )
    ).all()

    eligible: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for provider_id, robot_id, txn, region_id in rows:
        if compatible_txn is not None and txn not in compatible_txn:
            continue
        if country_known and not (region_id is None or region_id in applicable):
            continue
        eligible.add((provider_id, robot_id))
    return eligible


def reconcile_routes(session: Session, lead: CommercialLead) -> None:
    """Reconcile the lead's PENDING provider routes with the currently-eligible
    set (WS7 §13). Idempotent:
      - remove ONLY now-ineligible routes whose status is still PENDING (e.g. the
        buyer refined country/transaction so a provider no longer qualifies);
      - RETAIN non-PENDING routes (CONTACTED/ACCEPTED/DECLINED) as operational
        history, and never touch their `contacted_at`;
      - add newly-eligible routes as PENDING (contacted_at NULL).
    On first capture there is nothing to remove or retain, so this simply creates
    the eligible PENDING routes."""
    eligible = _eligible_routes(session, lead)

    # Remove now-ineligible PENDING routes only (delete-orphan cascade removes them).
    for route in list(lead.providers):
        if route.status == "PENDING" and (route.provider_id, route.robot_id) not in eligible:
            lead.providers.remove(route)

    present = {(r.provider_id, r.robot_id) for r in lead.providers}
    # Deterministic add order (stable across runs; no reliance on set iteration).
    for provider_id, robot_id in sorted(eligible, key=lambda k: (str(k[0]), str(k[1]))):
        if (provider_id, robot_id) not in present:
            lead.providers.append(
                CommercialLeadProvider(
                    provider_id=provider_id,
                    robot_id=robot_id,
                    status="PENDING",
                    contacted_at=None,
                )
            )
