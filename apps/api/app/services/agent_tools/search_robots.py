"""AGENT-02 `search_robots` — the ratified read-only tool (`docs/20` §5).

Transport-independent by construction: this is a plain callable taking a session
and typed inputs. MCP, HTTP or a test can bind to it without any of them owning
catalogue semantics (`docs/20` §19). There is no agent-specific SQL layer — the
governed predicates come from `services/robot_filters.py`, the same ones the
website's `/api/robots` uses, and serialization comes from `services/reads.py`.

Two dimensions are resolved to the ratified semantics rather than the router's
current behaviour, per the drifts `docs/20` records:

* **region** (§12) — applicability, not exact-code: the requested region, its
  ancestors, GLOBAL, and region-agnostic offers. Each offer keeps its own
  region identity; nothing is relabelled.
* **price** (§10.3) — `price_max` requires `price_currency`, is compared only
  within that currency, and never touches the cross-currency-unsafe
  `lowest_purchase_price` cache.

Read-only. Creates nothing, mutates nothing, and exposes only published
canonical robots (AGENT-01.7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.robot import Robot
from app.schemas.robot import RobotListItem
from app.services import reads
from app.services.agent_tools.errors import (
    InvalidArgument,
    InvalidEnum,
    InvalidPagination,
)
from app.services.agent_tools.pricing import evaluate_price_ceiling
from app.services.robot_filters import (
    InvalidFilterEnum,
    InvalidRegion,
    InvalidSortKey,
    apply_catalogue_filters,
    resolve_region_filter,
    resolve_sort,
    validate_filter_vocabulary,
)

#: Canonical pagination bounds, inherited from `docs/04` — not agent-specific.
DEFAULT_LIMIT = 24
MAX_LIMIT = 100

CONTRACT_VERSION = "agent-tools/0.1"


@dataclass(frozen=True)
class SearchResult:
    """`docs/20` §15 envelope, transport-independent."""

    items: list[RobotListItem]
    total: int
    limit: int
    offset: int
    warnings: list[str] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION


def search_robots(
    session: Session,
    *,
    q: str | None = None,
    manufacturer: str | None = None,
    commercial_status: list[str] | None = None,
    transaction_type: list[str] | None = None,
    availability_status: list[str] | None = None,
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
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> SearchResult:
    """Search published canonical robots under the ratified v0.1 semantics."""
    warnings: list[str] = []

    # ---- input validation (docs/20 §5, §16) --------------------------------
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise InvalidPagination("limit must be an integer")
    if not isinstance(offset, int) or isinstance(offset, bool):
        raise InvalidPagination("offset must be an integer")
    if limit < 1 or limit > MAX_LIMIT:
        # Rejected, never clamped: clamping answers a different question while
        # reporting success.
        raise InvalidPagination(
            f"limit must be between 1 and {MAX_LIMIT}; got {limit}"
        )
    if offset < 0:
        raise InvalidPagination(f"offset must be >= 0; got {offset}")

    if price_max is not None and price_currency is None:
        raise InvalidArgument(
            "price_max requires price_currency: a bare number cannot be "
            "compared to money that carries a denomination"
        )
    if price_currency is not None and price_max is None:
        raise InvalidArgument(
            "price_currency has no independent meaning in v0.1; supply it only "
            "with price_max"
        )
    if height_min is not None and height_max is not None and height_min > height_max:
        raise InvalidArgument("height_min must not exceed height_max")

    # ---- vocabulary (docs/20 §5, §17) --------------------------------------
    # Mapped onto the two distinct contract codes: an enum-backed filter carries
    # a `db/schema.sql` vocabulary and fails as INVALID_ENUM, while `sort` is a
    # contract allowlist rather than a schema enum and fails as INVALID_ARGUMENT.
    # The shared filter re-validates independently, so this mapping cannot be
    # bypassed by a future caller — it exists to name the failure correctly.
    try:
        validate_filter_vocabulary(
            commercial_status=commercial_status,
            transaction_type=transaction_type,
            availability_status=availability_status,
            mobility=mobility,
            autonomy_min=autonomy_min,
        )
    except InvalidFilterEnum as exc:
        raise InvalidEnum(str(exc)) from exc

    try:
        order = resolve_sort(sort)
    except InvalidSortKey as exc:
        raise InvalidArgument(str(exc)) from exc

    # ---- geography: ratified applicability (docs/20 §12) -------------------
    # Resolved through the shared catalogue resolver, which `/api/robots` now
    # uses too — so both surfaces answer `region=DE` identically (§21.2 parity).
    try:
        region_ids = resolve_region_filter(session, region) if region else None
    except InvalidRegion as exc:
        raise InvalidArgument(str(exc)) from exc

    filters: dict[str, Any] = dict(
        q=q,
        manufacturer=manufacturer,
        commercial_status=commercial_status,
        transaction_type=transaction_type,
        availability_status=availability_status,
        region_ids=region_ids,
        use_case=use_case,
        payload_min=payload_min,
        height_min=height_min,
        height_max=height_max,
        # `price_max` is NOT delegated: the cache behind it is cross-currency
        # unsafe. Currency-safe evaluation happens below.
        price_max=None,
        mobility=mobility,
        autonomy_min=autonomy_min,
        has_sdk=has_sdk,
        ros_support=ros_support,
        developer_edition=developer_edition,
        has_manipulation=has_manipulation,
    )

    base = apply_catalogue_filters(
        select(Robot).options(
            selectinload(Robot.pricing_offers), selectinload(Robot.images)
        ),
        **filters,
    ).order_by(order, Robot.slug)

    if price_max is None:
        total = session.execute(
            apply_catalogue_filters(select(func.count(Robot.id)), **filters)
        ).scalar_one()
        robots = list(session.execute(base.limit(limit).offset(offset)).scalars())
    else:
        # The price ceiling is evaluated per robot against pricing_offer, so it
        # cannot be pushed into the count query. Resolve the filtered set first,
        # then paginate the surviving rows — `total` stays truthful.
        candidates = list(session.execute(base).scalars())
        verdicts = evaluate_price_ceiling(
            session,
            [r.id for r in candidates],
            price_max=price_max,
            price_currency=price_currency or "",
        )
        reasons = {
            v.reason for v in verdicts.values() if v.reason is not None
        }
        warnings.extend(sorted(reasons))
        survivors = [r for r in candidates if verdicts[r.id].qualifies]
        total = len(survivors)
        robots = survivors[offset : offset + limit]

    snapshot = reads.snapshot_for(session, [r.id for r in robots])
    items = [reads.serialize_list_item(r, snapshot) for r in robots]

    return SearchResult(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        warnings=warnings,
    )
