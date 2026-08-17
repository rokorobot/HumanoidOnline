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

**Vocabulary validation (AGENT-02.1a).** Enum-backed inputs are validated here,
before any SQL is built, so *both* consumers inherit the check rather than each
guarding its own door. This closes a defect where an unrecognised `autonomy_min`
applied no constraint at all and reported success — an explicit hard filter must
never silently degrade to "no filter". Invalid members of the PostgreSQL-enum
filters previously reached the driver and surfaced as a raw `DataError`.
"""
from __future__ import annotations

import uuid
from collections.abc import Collection

from sqlalchemy import func, select

from app.models import enums as pg_enums
from app.models.commercial import AvailabilityOffer
from app.models.enums import AUTONOMY_ORDER
from app.models.manufacturer import Manufacturer
from app.models.region import Region
from app.models.robot import Robot
from app.models.use_case import UseCase, UseCaseFit


class InvalidFilterValue(ValueError):
    """A catalogue filter input outside its governed vocabulary.

    Transport-independent by design: this layer is shared by the public HTTP
    router and the AGENT-02 tool, so it raises a service-layer error and lets
    each binding map it to its own taxonomy (HTTP 422 / `INVALID_ENUM` /
    `INVALID_ARGUMENT`). It must not depend on FastAPI.
    """

    def __init__(self, field: str, value: object, allowed: Collection[str]) -> None:
        self.field = field
        self.value = value
        #: The governed vocabulary, exposed so a binding can help a caller
        #: self-correct without re-deriving it.
        self.allowed = tuple(allowed)
        super().__init__(f"unknown {field}: {value!r}")


class InvalidFilterEnum(InvalidFilterValue):
    """Value is not a member of the `db/schema.sql` enum backing this filter."""


class InvalidSortKey(InvalidFilterValue):
    """Sort key outside the v0.1 contract allowlist (`docs/20` §5, §16)."""


#: Enum-backed filters mapped to their vocabulary, read straight off the ORM
#: enum declarations in `models/enums.py` (which mirror `db/schema.sql`). Derived,
#: never a second hand-maintained list: a schema enum gaining a member widens
#: these filters automatically, and cannot drift out of step.
_ENUM_VOCABULARY: dict[str, tuple[str, ...]] = {
    "commercial_status": tuple(pg_enums.commercial_status.enums),
    "transaction_type": tuple(pg_enums.transaction_type.enums),
    "availability_status": tuple(pg_enums.availability_status.enums),
    "mobility": tuple(pg_enums.mobility_type.enums),
    "autonomy_min": tuple(pg_enums.autonomy_level.enums),
}

#: The four v0.1 sort keys (`docs/20` §5), each mapped to its ordering column.
#: `price` intentionally uses the `lowest_purchase_price` sort/badge cache, which
#: `docs/20` §10.3.1 permits for ordering while forbidding it as the basis of the
#: `price_max` constraint. AGENT-02.1a changes no sort *semantics*.
SORT_COLUMNS = {
    "name": Robot.name,
    "price": Robot.lowest_purchase_price,
    "payload": Robot.payload_kg,
    "newest": Robot.created_at,
}


def _check_enum(field: str, value: str) -> None:
    if value not in _ENUM_VOCABULARY[field]:
        raise InvalidFilterEnum(field, value, _ENUM_VOCABULARY[field])


def validate_filter_vocabulary(
    *,
    commercial_status=None,
    transaction_type=None,
    availability_status=None,
    mobility=None,
    autonomy_min=None,
) -> None:
    """Reject any enum-backed input outside its `db/schema.sql` vocabulary.

    List-valued filters are all-or-nothing: one invalid member rejects the whole
    call. Silently dropping it would answer a narrower question than the one
    asked, and partially accepting it would answer a wider one — both while
    reporting success.

    Empty/None inputs mean "no filter" and are left alone, preserving the
    existing truthiness behaviour of every currently-valid query.
    """
    for field, values in (
        ("commercial_status", commercial_status),
        ("transaction_type", transaction_type),
        ("availability_status", availability_status),
    ):
        for member in values or ():
            _check_enum(field, member)

    for field, value in (("mobility", mobility), ("autonomy_min", autonomy_min)):
        if value:
            _check_enum(field, value)


def resolve_sort(sort: str):
    """Ordering expression for a v0.1 sort key, `-` prefix for descending.

    Raises `InvalidSortKey` rather than falling back to `name`: a silent
    fallback hands the caller a different ordering than the one requested while
    reporting success, which is undetectable downstream (`docs/20` §16 —
    "no client-controlled sort key outside the four enumerated values").
    """
    if not isinstance(sort, str):
        raise InvalidSortKey("sort", sort, tuple(SORT_COLUMNS))
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    column = SORT_COLUMNS.get(key)
    if column is None:
        # Covers the bare "-" and the empty string, both of which previously
        # resolved to `name`.
        raise InvalidSortKey("sort", sort, tuple(SORT_COLUMNS))
    return column.desc().nullslast() if descending else column.asc().nullslast()


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

    Raises `InvalidFilterEnum` before touching SQL when an enum-backed input is
    outside its governed vocabulary.
    """
    # Validate BEFORE any predicate is built, so no invalid value can reach the
    # driver and no caller can obtain a partially-applied filter set.
    validate_filter_vocabulary(
        commercial_status=commercial_status,
        transaction_type=transaction_type,
        availability_status=availability_status,
        mobility=mobility,
        autonomy_min=autonomy_min,
    )

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
        # No membership guard here any more. It used to read `if autonomy_min in
        # AUTONOMY_ORDER:` with no else, so an unrecognised value applied NO
        # constraint and returned the unfiltered catalogue as a success.
        # `validate_filter_vocabulary` above now guarantees membership.
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
