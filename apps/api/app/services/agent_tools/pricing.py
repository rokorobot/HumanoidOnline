"""Currency-safe comparable purchase pricing for a hard numeric ceiling.

`docs/20` §10.3: given `price_max = X` and `price_currency = C`, find the
governed comparable purchase price(s) **denominated in C** and evaluate the
constraint **only within that currency**. No FX, no conversion, no base
currency, no cross-currency minimum.

`robot.lowest_purchase_price` is deliberately NOT used. Its derivation
(`db/import_catalogue.py::_refresh_lowest_price`) selects `ORDER BY price ASC
LIMIT 1` across all current PUBLIC/FROM purchase offers with **no currency
partition**, so for a robot priced in two currencies it caches whichever number
is numerically smallest — a cross-currency minimum, and meaningless as a
comparison basis (`docs/20` §10.3.1). This module reads `pricing_offer`
directly, which `db/schema.sql` names as the authoritative money.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial import PricingOffer

#: Exclusion reason codes (`docs/20` §10.3). These are query-result warnings,
#: NOT transport errors — see `errors.py`.
EXCLUDED_ABOVE_LIMIT = "price_max_excluded_above_limit"
EXCLUDED_UNPROVABLE = "price_max_excluded_unprovable"

#: Point-price types carrying a comparable number. RANGE is handled separately;
#: QUOTE_ONLY carries no number at all and can never satisfy a ceiling.
_POINT_TYPES = ("PUBLIC", "FROM", "ESTIMATED")


@dataclass(frozen=True)
class PriceVerdict:
    """Why a robot did or did not satisfy the ceiling, per robot."""

    qualifies: bool
    reason: str | None  # None when it qualifies


def evaluate_price_ceiling(
    session: Session,
    robot_ids: list[uuid.UUID],
    *,
    price_max: float,
    price_currency: str,
) -> dict[uuid.UUID, PriceVerdict]:
    """Classify each robot against `price_max` in `price_currency`.

    Outcomes (`docs/20` §10.3 A–F):

    * a comparable numeric price in C <= X            -> qualifies
    * a comparable numeric price in C  > X            -> EXCLUDED_ABOVE_LIMIT
    * has prices, none comparable in C                -> EXCLUDED_UNPROVABLE
    * QUOTE_ONLY only                                 -> EXCLUDED_UNPROVABLE
    * no pricing rows / UNKNOWN price                 -> EXCLUDED_UNPROVABLE
    * prices only in other currencies                 -> EXCLUDED_UNPROVABLE

    The last case is the one that must never be reported as *above limit*: a
    EUR-only robot under a USD ceiling failed on comparability, not on price.
    Nothing here converts an unprovable state to 0, false or "unavailable".
    """
    if not robot_ids:
        return {}

    currency = price_currency.upper()
    ceiling = Decimal(str(price_max))

    # Only PURCHASE money is comparable to a purchase ceiling, and only current
    # rows. Currency is filtered in SQL so a non-matching currency can never
    # reach a numeric comparison.
    rows = list(
        session.execute(
            select(PricingOffer).where(
                PricingOffer.robot_id.in_(robot_ids),
                PricingOffer.is_current.is_(True),
                PricingOffer.transaction_type == "PURCHASE",
                PricingOffer.currency == currency,
            )
        ).scalars()
    )

    best: dict[uuid.UUID, Decimal] = {}
    for offer in rows:
        amount: Decimal | None = None
        if offer.price_type in _POINT_TYPES and offer.price is not None:
            amount = offer.price
        elif offer.price_type == "RANGE" and offer.price_max is not None:
            # A range satisfies a hard ceiling only when its whole span is under
            # it; its upper bound is therefore the comparable figure. Never
            # invent a point value from a range.
            amount = offer.price_max
        # QUOTE_ONLY (and any row with no usable number) contributes nothing.
        if amount is None:
            continue
        current = best.get(offer.robot_id)
        if current is None or amount < current:
            best[offer.robot_id] = amount

    verdicts: dict[uuid.UUID, PriceVerdict] = {}
    for rid in robot_ids:
        comparable = best.get(rid)
        if comparable is None:
            # No comparable price in C. Covers "no prices at all", "quote-only",
            # and "priced only in another currency" — all unprovable, none of
            # them a statement that the robot is expensive.
            verdicts[rid] = PriceVerdict(False, EXCLUDED_UNPROVABLE)
        elif comparable <= ceiling:
            verdicts[rid] = PriceVerdict(True, None)
        else:
            verdicts[rid] = PriceVerdict(False, EXCLUDED_ABOVE_LIMIT)
    return verdicts
