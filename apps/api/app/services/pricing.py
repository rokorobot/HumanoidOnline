"""Governed comparable-purchase-price semantics — shared, SQL-level.

The single owner of "which money may be compared to a purchase ceiling, and in
which currency" (`docs/20` §10.3). It is deliberately a *catalogue* service, not
an agent one: AGENT-02 is its first consumer, but `/api/robots` is intended to
adopt the same predicate when its input shape converges, and two independent
price interpretations is exactly the drift this module exists to prevent.

**Everything here is expressed as SQL.** The predicate composes into the caller's
statement, so filtering, `COUNT` and `LIMIT`/`OFFSET` all happen server-side and
no candidate set is materialised to be filtered in Python (`docs/20` §16 — no
unbounded query).

**No FX, ever.** There is no conversion, no rate, no base currency and no
normalisation. `price_currency` is matched exactly in SQL, so a price in another
currency can never reach a numeric comparison — it is *incomparable*, which is a
different fact from *expensive* (`docs/20` §10.3 case F).

`robot.lowest_purchase_price` is never read. Its derivation takes a
cross-currency minimum across `PUBLIC`/`FROM` only, so it is neither
currency-safe nor complete (`docs/20` §10.3.1); `pricing_offer` is the
authoritative money per `db/schema.sql`.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.models.commercial import PricingOffer
from app.models.robot import Robot

#: Point-price types carrying a directly comparable number. `RANGE` is handled
#: separately (upper bound); `QUOTE_ONLY` carries no number by construction.
POINT_TYPES = ("PUBLIC", "FROM", "ESTIMATED")


@dataclass(frozen=True)
class CeilingExclusions:
    """Why robots are absent from a ceiling-constrained result, as presence flags.

    Semantic, not contractual: this layer states *what happened*, and the binding
    maps it to its own vocabulary. Counts are deliberately not carried — the
    contract asks callers to distinguish two kinds of absence, not to quantify
    them.
    """

    above_limit: bool
    unprovable: bool


def comparable_amount():
    """The comparable figure of a `pricing_offer` row, or NULL if there is none.

    Leans on `chk_price_type_shape` (`db/schema.sql`) rather than inventing
    states: that constraint already guarantees `PUBLIC`/`FROM`/`ESTIMATED` carry
    `price`, `RANGE` carries `price_min` + `price_max`, and `QUOTE_ONLY` carries
    none of them. So `QUOTE_ONLY` falls through to NULL and can never satisfy a
    ceiling — an exclusion by construction, not a special case.

    A `RANGE` satisfies a hard ceiling only when its whole span is under it, so
    its upper bound is the comparable figure. A point value is never invented
    from a range.
    """
    return case(
        (PricingOffer.price_type.in_(POINT_TYPES), PricingOffer.price),
        (PricingOffer.price_type == "RANGE", PricingOffer.price_max),
        else_=None,
    )


def _purchase_offers(price_currency: str) -> Select:
    """Current PURCHASE offers denominated exactly in `price_currency`."""
    return select(PricingOffer.robot_id).where(
        PricingOffer.is_current.is_(True),
        PricingOffer.transaction_type == "PURCHASE",
        PricingOffer.currency == price_currency.upper(),
    )


def robots_with_comparable_price(price_currency: str) -> Select:
    """Robot ids having *any* comparable purchase price in `price_currency`.

    The difference between "we cannot prove a price" and "the price is too high"
    (`docs/20` §10.3): a robot absent from this set failed on comparability.
    """
    return _purchase_offers(price_currency).where(comparable_amount().is_not(None))


def robots_under_ceiling(price_currency: str, price_max: float) -> Select:
    """Robot ids with at least one comparable price in `price_currency` <= ceiling.

    Equivalent to "the cheapest comparable price in C is <= X" — an existential
    over offers is the same test as a comparison against their minimum, and it
    expresses in SQL without an aggregate.
    """
    amount = comparable_amount()
    ceiling = Decimal(str(price_max))
    return _purchase_offers(price_currency).where(
        amount.is_not(None), amount <= ceiling
    )


def apply_price_ceiling(stmt, *, price_max: float, price_currency: str):
    """Restrict a robot-selecting statement to robots satisfying the ceiling.

    Composes into `SELECT robot…`, `SELECT count(robot.id)…` and the paged query
    alike, which is what keeps `total` truthful while pagination stays in SQL.
    """
    return stmt.where(Robot.id.in_(robots_under_ceiling(price_currency, price_max)))


def ceiling_exclusions(
    session: Session,
    candidate_ids: Select,
    *,
    price_max: float,
    price_currency: str,
) -> CeilingExclusions:
    """Which kinds of ceiling exclusion occurred across the WHOLE filtered query.

    `candidate_ids` selects the robot ids matching every filter *except* the
    price ceiling. One aggregate row comes back regardless of catalogue size —
    the reasons describe the entire result set, never merely the visible page,
    without loading a single robot into Python.

    `bool_or` yields NULL over an empty candidate set, which coalesces to False:
    no candidates means nothing was excluded on price.
    """
    candidates = candidate_ids.subquery()
    has_comparable = (
        robots_with_comparable_price(price_currency)
        .where(PricingOffer.robot_id == candidates.c.id)
        .exists()
    )
    qualifies = (
        robots_under_ceiling(price_currency, price_max)
        .where(PricingOffer.robot_id == candidates.c.id)
        .exists()
    )

    above_limit, unprovable = session.execute(
        select(
            func.coalesce(func.bool_or(has_comparable & ~qualifies), False),
            func.coalesce(func.bool_or(~has_comparable), False),
        ).select_from(candidates)
    ).one()
    return CeilingExclusions(above_limit=bool(above_limit), unprovable=bool(unprovable))
