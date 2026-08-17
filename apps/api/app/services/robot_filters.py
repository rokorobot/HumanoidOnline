"""Governed catalogue filter predicates — one implementation, two consumers.

Moved verbatim out of `routers/robots.py` so the AGENT-02 tool layer reuses the
same predicates instead of writing a second interpretation of "which robots
match".

**Geography is now single-sourced (AGENT-02.1b).** This layer accepts only
`region_ids` — an already-resolved applicability set from the canonical
`services/regions.py::applicable_region_ids`. The old `region=<bare code>`
parameter and its exact-code `WHERE region.code = :code` branch are gone: they
were the `docs/20` §12 implementation drift, under which `/api/robots?region=DE`
answered 0 while the agent answered 8 for the same catalogue. Removing the
parameter rather than leaving it unused is deliberate — a dormant exact-code
path is an invitation to reintroduce the divergence.

**Price is single-sourced too (AGENT-02.1d).** This module no longer accepts
`price_max` at all. It once applied `Robot.lowest_purchase_price <= price_max`,
a cache whose derivation takes a cross-currency minimum across `PUBLIC`/`FROM`
only — neither currency-safe nor complete (`docs/20` §10.3.1). The hard price
constraint now lives entirely in `services/pricing.py` and is applied by the
caller via `apply_price_ceiling`, so there is no second price interpretation for
a future caller to reach for.

The cache keeps its one legitimate role: `SORT_COLUMNS["price"]`, the sort/badge
use `docs/01` §7 and `db/schema.sql` sanction. Under an active
`price_max` + `price_currency` pair even ordering switches to the comparable
amount (`docs/20` §10.5, `resolve_sort`).

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

from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.models import enums as pg_enums
from app.models.commercial import AvailabilityOffer
from app.models.enums import AUTONOMY_ORDER
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.models.use_case import UseCase, UseCaseFit
from app.services.pricing import comparable_price_order_column
from app.services.regions import applicable_region_ids


class InvalidFilterValue(ValueError):
    """A catalogue filter input outside its governed vocabulary.

    Transport-independent by design: this layer is shared by the public HTTP
    router and the AGENT-02 tool, so it raises a service-layer error and lets
    each binding map it to its own taxonomy (HTTP 422 / `INVALID_ENUM` /
    `INVALID_ARGUMENT`). It must not depend on FastAPI.
    """

    def __init__(
        self, field: str, value: object, allowed: Collection[str] = ()
    ) -> None:
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


class InvalidRegion(InvalidFilterValue):
    """Requested region code resolves to no governed region."""


def resolve_region_filter(session: Session, code: str) -> set[uuid.UUID]:
    """Applicable region ids for a requested region code (`docs/20` §12).

    The one place the catalogue turns a caller-supplied region code into
    geography, for both `/api/robots` and AGENT-02 `search_robots`, so the two
    cannot answer `region=DE` differently. The walk itself is not reimplemented
    here — it is the canonical `services/regions.py::applicable_region_ids`.

    An unrecognised code raises `InvalidRegion` rather than returning an empty
    set for the caller to interpret. That is the safety-critical half: a typo
    must fail, never widen. See `apply_catalogue_filters` for why an empty set
    could otherwise become "region-agnostic offers only".
    """
    ids = applicable_region_ids(session, code=code)
    if not ids:
        raise InvalidRegion("region", code)
    return ids


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


def resolve_sort(sort: str, *, price_currency: str | None = None):
    """Ordering expression for a v0.1 sort key, `-` prefix for descending.

    Raises `InvalidSortKey` rather than falling back to `name`: a silent
    fallback hands the caller a different ordering than the one requested while
    reporting success, which is undetectable downstream (`docs/20` §16 —
    "no client-controlled sort key outside the four enumerated values").

    `price_currency` selects the *mode* of `sort=price` (`docs/20` §10.5) and is
    passed only when the query carries an active `price_max` + `price_currency`
    pair. This function chooses between modes; it does not define either —
    the constrained figure comes from `services/pricing.py`, the same module
    that defines qualification, so the two cannot drift apart.
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
    if key == "price" and price_currency:
        # Constrained: order by the comparable amount that qualified the robot.
        column = comparable_price_order_column(price_currency)
    return column.desc().nullslast() if descending else column.asc().nullslast()


def _nullable_fact_constraints(
    *,
    payload_min,
    height_min,
    height_max,
    mobility,
    autonomy_min,
    has_sdk,
    ros_support,
    developer_edition,
    has_manipulation,
) -> list[tuple]:
    """Active hard constraints on **nullable first-class robot facts**.

    Each is returned as `(satisfied, is_unknown)` so the two consumers cannot
    drift apart: `apply_catalogue_filters` requires `satisfied`, and
    `unknown_exclusion_query` asks whether a robot would have qualified but for
    `is_unknown`. Writing the second interpretation separately is exactly how a
    notice ends up describing a filter that behaves differently.

    Scope is deliberately these nine inputs over eight nullable columns:

    * `commercial_status` is **excluded** — it is `NOT NULL` with `UNKNOWN` as an
      explicit enum member (`docs/20` §9.1), so filtering it out is an ordinary
      enum exclusion, not the exclusion of an unrecorded fact.
    * `price_max` is **excluded** — it has its own ratified reason codes
      (`docs/20` §10.3), which distinguish *unprovable* from *above limit* more
      precisely than a generic notice could.
    * `q`, `manufacturer`, `use_case`, `transaction_type`, `availability_status`
      and `region` are relational or textual, not nullable facts on the robot.

    SQL three-valued logic is what excludes UNKNOWN in the first place: `NULL >=
    10` and `NULL IS TRUE` are both not-true, so a robot with no recorded value
    never satisfies an explicit requirement. That is the ratified rule (§9.2);
    this helper only makes the same predicate available to the detector.
    """
    constraints: list[tuple] = []
    if payload_min is not None:
        constraints.append(
            (Robot.payload_kg >= payload_min, Robot.payload_kg.is_(None))
        )
    if height_min is not None:
        constraints.append((Robot.height_cm >= height_min, Robot.height_cm.is_(None)))
    if height_max is not None:
        constraints.append((Robot.height_cm <= height_max, Robot.height_cm.is_(None)))
    if mobility:
        constraints.append((Robot.mobility == mobility, Robot.mobility.is_(None)))
    if autonomy_min:
        allowed = AUTONOMY_ORDER[AUTONOMY_ORDER.index(autonomy_min):]
        constraints.append((Robot.autonomy.in_(allowed), Robot.autonomy.is_(None)))
    for column, value in (
        (Robot.has_sdk, has_sdk),
        (Robot.ros_support, ros_support),
        (Robot.developer_edition, developer_edition),
        (Robot.has_manipulation, has_manipulation),
    ):
        if value is not None:
            constraints.append((column.is_(value), column.is_(None)))
    return constraints


#: The `apply_catalogue_filters` keywords `_nullable_fact_constraints` owns.
_NULLABLE_FACT_INPUTS = (
    "payload_min", "height_min", "height_max", "mobility", "autonomy_min",
    "has_sdk", "ros_support", "developer_edition", "has_manipulation",
)


def unknown_exclusion_query(**filters):
    """Robots excluded **only** because a constrained fact is UNKNOWN.

    `docs/20` §9.2 excludes an UNKNOWN value from satisfying an explicit positive
    requirement, and §9.4 requires the response to say so where a consumer could
    misread the absence. This builds the set that notice is about: a published
    robot that

    1. satisfies every other active constraint,
    2. holds no **known** value contradicting an active nullable-fact
       constraint, and
    3. is UNKNOWN on at least one of them.

    Point 2 is what keeps the notice honest. A robot already failing a different
    requirement on a recorded value was not excluded by uncertainty, and must not
    imply that it was — so the constraints are *relaxed* to "satisfied or
    unknown" rather than dropped.

    Returns `None` when no nullable-fact constraint is active, because then no
    robot can have been excluded for being UNKNOWN and there is nothing to
    report. Returns a `select(Robot.id)` otherwise — the caller decides how to
    ask (an `EXISTS`, never a materialised list).
    """
    constraints = _nullable_fact_constraints(
        **{k: filters[k] for k in _NULLABLE_FACT_INPUTS}
    )
    if not constraints:
        return None

    # Every OTHER active constraint, applied by the governed filter itself — so
    # publication, geography, availability and vocabulary all behave identically
    # here and in the real query.
    stmt = apply_catalogue_filters(
        select(Robot.id),
        **{**filters, **{k: None for k in _NULLABLE_FACT_INPUTS}},
    )
    for satisfied, is_unknown in constraints:
        stmt = stmt.where(or_(satisfied, is_unknown))
    return stmt.where(or_(*(is_unknown for _, is_unknown in constraints)))


def apply_catalogue_filters(
    stmt,
    *,
    q,
    manufacturer,
    commercial_status,
    transaction_type,
    availability_status,
    use_case,
    payload_min,
    height_min,
    height_max,
    mobility,
    autonomy_min,
    has_sdk,
    ros_support,
    developer_edition,
    has_manipulation,
    region_ids: Collection[uuid.UUID] | None = None,
):
    """Apply the governed catalogue predicates to `stmt`.

    Geography is expressed only as `region_ids`, resolved by the caller through
    `resolve_region_filter`. The three states are exhaustive and distinct:

    * `None`            — no region filter was requested; geography is inactive.
    * non-empty         — match offers scoped to those applicable regions, plus
                          region-agnostic (`NULL`) offers, which apply anywhere.
    * **empty**         — **match nothing.**

    The empty case is the one worth stating explicitly. It previously fell
    through to `region_id IS NULL`, i.e. "region-agnostic offers only" — so an
    unresolvable region produced a *result set* rather than no result, and could
    return robots a narrower, resolvable region would not. That is the wrong
    direction to fail in. It was masked in the seeded dataset only because no
    current availability offer has a NULL region.

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
    # Nullable first-class facts. The predicates come from the shared helper so
    # the UNKNOWN-exclusion notice describes exactly this filter and not a second
    # reading of it. `autonomy_min` no longer needs a membership guard —
    # `validate_filter_vocabulary` above guarantees it, where it once silently
    # applied no constraint at all for an unrecognised value.
    for satisfied, _is_unknown in _nullable_fact_constraints(
        payload_min=payload_min,
        height_min=height_min,
        height_max=height_max,
        mobility=mobility,
        autonomy_min=autonomy_min,
        has_sdk=has_sdk,
        ros_support=ros_support,
        developer_edition=developer_edition,
        has_manipulation=has_manipulation,
    ):
        stmt = stmt.where(satisfied)

    # Availability-derived filters, all gated by is_current + canonical predicate.
    # Geography is active only when the caller resolved a region; an absent or
    # empty `region` query param resolves to None and leaves it inactive, exactly
    # as before.
    if transaction_type or availability_status or region_ids is not None:
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
            # caller. Region-agnostic (NULL) offers apply everywhere. Each offer
            # keeps its own region identity — nothing here relabels a GLOBAL
            # offer as the queried region (`docs/20` §12).
            ids = list(region_ids)
            if ids:
                avail = avail.where(
                    (AvailabilityOffer.region_id.in_(ids))
                    | (AvailabilityOffer.region_id.is_(None))
                )
            else:
                # No region applies -> match nothing. Never fall through to
                # region-agnostic offers: an unresolvable region must not return
                # more than a resolvable one.
                avail = avail.where(false())
        stmt = stmt.where(Robot.id.in_(avail))
    return stmt
