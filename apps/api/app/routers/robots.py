"""Public read API for robots (API contract §1)."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db.session import get_session
from app.models.robot import Robot
from app.schemas.common import Page
from app.schemas.robot import CompareResponse, CompareRow, RobotDetail, RobotListItem
from app.services import compare_cache, reads
from app.services.pricing import (
    InvalidPriceQuery,
    apply_price_ceiling,
    validate_price_pair,
)
from app.services.robot_filters import (
    InvalidFilterValue,
    apply_catalogue_filters,
    resolve_region_filter,
    resolve_sort,
)

# No PII here (WS8-L6): only a cache disposition and integer counts, never the
# requested slugs/query string — same doctrine as app.request (observability.py).
_cache_logger = logging.getLogger("app.compare_cache")

router = APIRouter(prefix="/api/robots", tags=["robots"])


# The governed predicates now live in services/robot_filters.py so the AGENT-02
# tool layer reuses them instead of writing a second interpretation. This alias
# keeps the router's call sites and behaviour unchanged.
_apply_filters = apply_catalogue_filters


@router.get("", response_model=Page[RobotListItem])
def list_robots(
    session: Annotated[Session, Depends(get_session)],
    q: str | None = None,
    manufacturer: str | None = None,
    commercial_status: Annotated[list[str] | None, Query()] = None,
    transaction_type: Annotated[list[str] | None, Query()] = None,
    availability_status: Annotated[list[str] | None, Query()] = None,
    region: str | None = None,
    use_case: str | None = None,
    payload_min: float | None = None,
    height_min: float | None = None,
    height_max: float | None = None,
    price_max: float | None = None,
    price_currency: str | None = None,
    mobility: str | None = None,
    autonomy_min: str | None = None,
    has_sdk: bool | None = None,
    ros_support: bool | None = None,
    developer_edition: bool | None = None,
    has_manipulation: bool | None = None,
    sort: str = "name",
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page[RobotListItem]:
    # Vocabulary validation happens inside the shared governed filter, so an
    # unknown enum member or sort key becomes a structured 422 here instead of a
    # PostgreSQL DataError (500) or a silently-unfiltered result. Both statements
    # are built before either is executed, so a bad input costs no query.
    try:
        # AGENT-02.1b — `region` is resolved to the ratified applicability set
        # (exact + ancestors + GLOBAL) by the SAME canonical resolver AGENT-02
        # uses, so `?region=DE` now matches an EU-scoped or GLOBAL offer instead
        # of demanding a literal DE row. An unknown code is invalid input (422),
        # never a silently unfiltered or widened result. No ancestor walking
        # happens in this router.
        region_ids = resolve_region_filter(session, region) if region else None

        # AGENT-02.1d — `price_max` and `price_currency` are a required pair, and
        # the constraint is the shared currency-safe predicate AGENT-02 uses
        # (`services/pricing.py`), never the cross-currency `lowest_purchase_price`
        # cache. There is no default currency: a bare `price_max` is rejected.
        validate_price_pair(price_max, price_currency)
        constrained = price_max is not None

        filters = dict(
            q=q, manufacturer=manufacturer, commercial_status=commercial_status,
            transaction_type=transaction_type, availability_status=availability_status,
            region_ids=region_ids, use_case=use_case, payload_min=payload_min,
            height_min=height_min, height_max=height_max,
            mobility=mobility, autonomy_min=autonomy_min, has_sdk=has_sdk,
            ros_support=ros_support, developer_edition=developer_edition,
            has_manipulation=has_manipulation,
        )

        count_stmt = _apply_filters(select(func.count(Robot.id)), **filters)
        stmt = _apply_filters(
            select(Robot).options(
                selectinload(Robot.pricing_offers), selectinload(Robot.images)
            ),
            **filters,
        )
        if constrained:
            ceiling = dict(price_max=price_max, price_currency=price_currency)
            count_stmt = apply_price_ceiling(count_stmt, **ceiling)
            stmt = apply_price_ceiling(stmt, **ceiling)

        # `sort=price` follows the qualifying amount only while a currency
        # constraint is active (docs/20 §10.5); otherwise the sort/badge cache
        # remains the sanctioned basis.
        order = resolve_sort(
            sort, price_currency=price_currency if constrained else None
        )
        stmt = stmt.order_by(order, Robot.slug).limit(limit).offset(offset)
    except (InvalidFilterValue, InvalidPriceQuery) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    total = session.execute(count_stmt).scalar_one()
    robots = list(session.execute(stmt).scalars())

    snapshot = reads.snapshot_for(session, [r.id for r in robots])
    items = [reads.serialize_list_item(r, snapshot) for r in robots]
    return Page(items=items, total=total, limit=limit, offset=offset)


# The detail load — publication predicate and eager-load set together — now lives
# in services/reads.py so AGENT-02's `get_robot` inherits one implementation
# instead of importing a router private (`docs/20` §6). This alias keeps the
# router's call sites and behaviour unchanged.
_load_detail = reads.load_detail


def _reordered_for_request(cached: CompareResponse, order: list[str]) -> CompareResponse:
    """Reshape a cache HIT to look exactly as if it had been computed fresh for
    THIS request's slug order.

    Emergency Compare Traffic Containment (2026-08-22): the cache key is now
    order-independent (services/compare_cache.cache_key), so a HIT may have
    been stored by a request that asked for the same robot SET in a different
    order. The stored facts are identical either way — no new query, no
    changed data — only the caller-requested display order (the `robots`
    array, and each row's `values` KEY order) needs rebuilding, which is why
    this is a pure in-memory reshape rather than a cache-bypass.
    """
    by_slug = {r.slug: r for r in cached.robots}
    rows = [
        CompareRow(
            group=row.group,
            key=row.key,
            label=row.label,
            values={slug: row.values[slug] for slug in order},
        )
        for row in cached.rows
    ]
    return CompareResponse(robots=[by_slug[s] for s in order], rows=rows)


@router.get("/compare", response_model=CompareResponse)
def compare_robots(
    session: Annotated[Session, Depends(get_session)],
    response: Response,
    ids: str = Query(..., description="2–4 comma-separated robot slugs"),
) -> CompareResponse:
    slugs = [s.strip() for s in ids.split(",") if s.strip()]
    # Trimmed, de-duplicated, ORDER-PRESERVED — the response's `robots` array
    # and each row's `values` mapping are built (or reshaped, on a cache HIT —
    # see _reordered_for_request) by iterating this list in order, so ids=a,b
    # and ids=b,a remain genuinely different RESPONSES. The CACHE KEY itself is
    # order-independent (services/compare_cache.cache_key) — permutations of
    # the same set now share one computation, they just never share output order.
    unique = list(dict.fromkeys(slugs))
    settings = get_settings()
    ttl = settings.compare_cache_ttl_s
    cache_control = f"public, s-maxage={ttl}, stale-while-revalidate={ttl * 5}"

    key = compare_cache.cache_key(unique)
    cached = compare_cache.get(key)
    if cached is not None:
        response.headers["Cache-Control"] = cache_control
        # Distinguishes an in-process cache hit from Vercel's own edge cache
        # (surfaced separately as `x-vercel-cache`) — the two are different
        # layers and either can be a HIT while the other is a MISS.
        response.headers["X-App-Cache"] = "HIT"
        _cache_logger.info("compare cache HIT robots=%d", len(unique))
        return _reordered_for_request(cached, unique)

    robots = [r for r in (_load_detail(session, s) for s in unique) if r is not None]
    if not 2 <= len(robots) <= 4:
        # Never cached: an invalid request must not poison the cache for a
        # later valid, identical request (requirement: don't cache errors).
        _cache_logger.info("compare cache BYPASS reason=invalid_request robots=%d", len(robots))
        raise HTTPException(status_code=422, detail="compare requires 2–4 valid robot slugs")

    details = [reads.serialize_detail(session, r) for r in robots]
    rows: list[CompareRow] = []
    for group, attr, label in reads.COMPARE_FIELDS:
        values: dict[str, float | bool | str | None] = {}
        for r in robots:
            raw = getattr(r, attr)
            values[r.slug] = float(raw) if isinstance(raw, Decimal) else raw
        rows.append(CompareRow(group=group, key=attr, label=label, values=values))
    result = CompareResponse(robots=details, rows=rows)

    compare_cache.put(key, result, ttl_seconds=ttl)
    response.headers["Cache-Control"] = cache_control
    response.headers["X-App-Cache"] = "MISS"
    _cache_logger.info("compare cache MISS robots=%d ttl_s=%d", len(unique), ttl)
    return result


@router.get("/{slug}", response_model=RobotDetail)
def get_robot(
    slug: str, session: Annotated[Session, Depends(get_session)]
) -> RobotDetail:
    robot = _load_detail(session, slug)
    if robot is None:
        raise HTTPException(status_code=404, detail="robot not found")
    return reads.serialize_detail(session, robot)
