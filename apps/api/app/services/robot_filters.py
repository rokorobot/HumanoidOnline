"""Governed catalogue filter predicates — one implementation, two consumers.

Moved verbatim out of `routers/robots.py` so the AGENT-02 tool layer reuses the
same predicates instead of writing a second interpretation of "which robots
match". The HTTP router's behaviour is unchanged: it still passes `region` as a
bare code and `price_max` as a bare number.

Two dimensions are deliberately parameterised rather than shared, because the
router and the agent contract legitimately differ today:

* **region** — the router passes `region=<code>` (exact-code match, the
  behaviour `docs/20` §12 records as implementation drift). The agent passes
  `region_ids=<applicable set>` resolved by `services/regions.py`, which is the
  ratified applicability rule. Both funnel through the same availability
  sub-select, so nothing else diverges.
* **price_max** — the router still filters on the `lowest_purchase_price` cache.
  The agent passes `price_max=None` and applies currency-safe filtering in
  `agent_tools/search_robots.py`, because that cache is cross-currency unsafe
  (`docs/20` §10.3.1).

`Robot.is_published.is_(True)` is unconditional here and is the publication gate
(AGENT-01.7). No caller may bypass it.
"""
from __future__ import annotations

import uuid
from collections.abc import Collection

from sqlalchemy import func, select

from app.models.commercial import AvailabilityOffer
from app.models.enums import AUTONOMY_ORDER
from app.models.manufacturer import Manufacturer
from app.models.region import Region
from app.models.robot import Robot
from app.models.use_case import UseCase, UseCaseFit


def apply_catalogue_filters(
    stmt,
    *,
    q,
    manufacturer,
    commercial_status,
    transaction_type,
    availability_status,
    region,
    use_case,
    payload_min,
    height_min,
    height_max,
    price_max,
    mobility,
    autonomy_min,
    has_sdk,
    ros_support,
    developer_edition,
    has_manipulation,
    region_ids: Collection[uuid.UUID] | None = None,
):
    """Apply the governed catalogue predicates to `stmt`.

    `region_ids`, when given, replaces the `region` code lookup with an explicit
    set of applicable region ids (see module docstring). Passing an empty
    collection means "no region applies" and matches nothing, which is the
    correct answer for an unknown region rather than a silently unfiltered one.
    """
    stmt = stmt.where(Robot.is_published.is_(True))
    if q:
        stmt = stmt.where(Robot.search_vector.op("@@")(func.plainto_tsquery("english", q)))
    if manufacturer:
        stmt = stmt.where(
            Robot.manufacturer_id.in_(
                select(Manufacturer.id).where(Manufacturer.slug == manufacturer)
            )
        )
    if commercial_status:
        stmt = stmt.where(Robot.commercial_status.in_(commercial_status))
    if use_case:
        stmt = stmt.where(
            Robot.id.in_(
                select(UseCaseFit.robot_id)
                .join(UseCase, UseCase.id == UseCaseFit.use_case_id)
                .where(UseCase.slug == use_case)
            )
        )
    if payload_min is not None:
        stmt = stmt.where(Robot.payload_kg >= payload_min)
    if height_min is not None:
        stmt = stmt.where(Robot.height_cm >= height_min)
    if height_max is not None:
        stmt = stmt.where(Robot.height_cm <= height_max)
    if price_max is not None:
        stmt = stmt.where(Robot.lowest_purchase_price <= price_max)
    if mobility:
        stmt = stmt.where(Robot.mobility == mobility)
    if autonomy_min:
        if autonomy_min in AUTONOMY_ORDER:
            allowed = AUTONOMY_ORDER[AUTONOMY_ORDER.index(autonomy_min):]
            stmt = stmt.where(Robot.autonomy.in_(allowed))
    for flag, value in (
        (Robot.has_sdk, has_sdk),
        (Robot.ros_support, ros_support),
        (Robot.developer_edition, developer_edition),
        (Robot.has_manipulation, has_manipulation),
    ):
        if value is not None:
            stmt = stmt.where(flag.is_(value))

    # Availability-derived filters, all gated by is_current + canonical predicate.
    # `bool(region)`, not `region is not None`: the router historically treats an
    # empty string as "no region filter", and moving this must not change that.
    geo_active = bool(region) or region_ids is not None
    if transaction_type or availability_status or geo_active:
        avail = (
            select(AvailabilityOffer.robot_id)
            .where(AvailabilityOffer.is_current.is_(True))
            .where(func.commercially_accessible(AvailabilityOffer.availability_status))
        )
        if transaction_type:
            avail = avail.where(AvailabilityOffer.transaction_type.in_(transaction_type))
        if availability_status:
            avail = avail.where(AvailabilityOffer.availability_status.in_(availability_status))
        if region_ids is not None:
            # Ratified applicability: exact + ancestors + GLOBAL, resolved by the
            # caller. Region-agnostic (NULL) offers apply everywhere.
            ids = list(region_ids)
            if ids:
                avail = avail.where(
                    (AvailabilityOffer.region_id.in_(ids))
                    | (AvailabilityOffer.region_id.is_(None))
                )
            else:
                avail = avail.where(AvailabilityOffer.region_id.is_(None))
        elif region:
            avail = avail.where(
                AvailabilityOffer.region_id.in_(
                    select(Region.id).where(Region.code == region)
                )
            )
        stmt = stmt.where(Robot.id.in_(avail))
    return stmt
