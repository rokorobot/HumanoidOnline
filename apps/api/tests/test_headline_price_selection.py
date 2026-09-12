"""The headline price is ONE offer row, chosen the same way every time.

`price_display_for` picks the price a card shows. Three ways it can lie, each
pinned here:

* **Frankenstein offers** — showing one seller's number under another seller's
  terms. The amount, currency, seller, region, basis and order status must all
  come from the row that was selected, together.
* **Cross-currency comparison** — treating 5 000 USD as cheaper than 9 000 EUR.
  There is no FX in this system, so amounts are comparable only within one
  currency, and `price` must never decide across denominations.
* **Instability** — the headline changing for no reason. Offer UUIDs are
  REGENERATED and `updated_at` is rewritten by every catalogue import, so
  neither may influence selection: re-importing unchanged data must produce the
  same headline. That is simulated here by permuting the row order, which is
  exactly what a fresh import's new ids do to the natural ordering.

No database: `price_display_for` reads attributes, so plain stand-ins suffice.
"""
from __future__ import annotations

import itertools
from types import SimpleNamespace

from app.services.reads import price_display_for
from app.services.regions import (
    MARKET_RANK_AGNOSTIC,
    MARKET_RANK_DESCENDANT,
    MARKET_RANK_EXACT,
    MARKET_RANK_GLOBAL,
)

EU_MARKET = {
    "EU": MARKET_RANK_EXACT,
    "DE": MARKET_RANK_DESCENDANT,
    "GLOBAL": MARKET_RANK_GLOBAL,
    None: MARKET_RANK_AGNOSTIC,
}


#: Stand-in manufacturer identity; the robot under test is made by MAKER.
MAKER = "maker-id"
OTHER_MAKER = "other-maker-id"


def offer(
    *,
    provider: str | None = "seller",
    provider_type: str = "DISTRIBUTOR",
    provider_manufacturer: str | None = None,
    region: str | None = "EU",
    currency: str = "EUR",
    price: float | None = 1000.0,
    edition_confirmed: bool | None = None,
    is_current: bool = True,
    price_basis: str | None = None,
    order_status_note: str | None = None,
    variant_id: str | None = None,
):
    return SimpleNamespace(
        transaction_type="PURCHASE",
        price_type="PUBLIC",
        price=price,
        price_min=None,
        price_max=None,
        currency=currency,
        billing_period="ONE_TIME",
        provider=SimpleNamespace(
            slug=provider, type=provider_type, manufacturer_id=provider_manufacturer
        ) if provider else None,
        region=SimpleNamespace(code=region) if region else None,
        price_basis=price_basis,
        order_status_note=order_status_note,
        edition_confirmed=edition_confirmed,
        is_current=is_current,
        variant_id=variant_id,
    )


def oem(**kwargs):
    """An offer sold by the robot's OWN manufacturer (the two governed columns)."""
    kwargs.setdefault("provider", "maker-store")
    return offer(provider_type="OEM", provider_manufacturer=MAKER, **kwargs)


def robot_with(*offers):
    return SimpleNamespace(pricing_offers=list(offers), manufacturer_id=MAKER)


# --- what may become a headline ----------------------------------------------

def test_a_listing_excluded_by_edition_is_never_the_headline() -> None:
    """`edition_confirmed = False` means the listing's own spec conflicts with
    this record. It stays visible on the detail page as a qualified listing, but
    it must not become the price the catalogue quotes for the robot."""
    excluded = offer(provider="reichelt", price=100.0, edition_confirmed=False)
    good = offer(provider="unitree-store", price=900.0)
    display = price_display_for(robot_with(excluded, good))
    assert display is not None
    assert display.provider == "unitree-store"
    assert display.amount == 900.0


def test_an_unassessed_edition_is_not_treated_as_excluded() -> None:
    """NULL means nobody assessed the edition match — not that it failed. It is
    also never reported as confirmed."""
    display = price_display_for(robot_with(offer(edition_confirmed=None)))
    assert display is not None
    assert display.edition_confirmed is None


def test_no_current_offers_is_unknown_not_zero() -> None:
    assert price_display_for(robot_with(offer(is_current=False))) is None
    assert price_display_for(robot_with()) is None


# --- the row travels together ------------------------------------------------

def test_the_headline_carries_its_own_seller_region_basis_and_status() -> None:
    chosen = offer(
        provider="reichelt",
        region="DE",
        currency="EUR",
        price=21000.0,
        price_basis="incl. 19% VAT",
        order_status_note="Special order",
    )
    other = offer(provider="unitree-store", region="GLOBAL", currency="USD", price=5.0)
    display = price_display_for(robot_with(chosen, other), market_rank=EU_MARKET)
    assert display is not None
    # Every field below is from the SAME row — never mixed across offers.
    assert (display.provider, display.region) == ("reichelt", "DE")
    assert (display.currency, display.amount) == ("EUR", 21000.0)
    assert display.price_basis == "incl. 19% VAT"
    assert display.order_status_note == "Special order"


# --- seller preference (manufacturer-direct) ---------------------------------

def test_manufacturer_direct_is_preferred_over_a_reseller() -> None:
    """The canonical headline is the maker's own listing for its own robot —
    even when a reseller's number is lower, and even when the reseller sorts
    earlier alphabetically. This is the defect the correction targets: seller
    order must never be the business preference."""
    reseller = offer(provider="a-reseller", price=100.0)
    direct = oem(provider="z-maker-store", price=13500.0)
    display = price_display_for(robot_with(reseller, direct))
    assert display is not None
    assert display.provider == "z-maker-store"
    assert display.amount == 13500.0


def test_oem_type_without_a_manufacturer_link_is_not_treated_as_direct() -> None:
    """`type = 'OEM'` alone says the seller is somebody's factory outlet, not
    that it is THIS robot's. Unproven must not outrank proven."""
    unlinked = offer(provider="a-oem-store", provider_type="OEM", provider_manufacturer=None)
    other = offer(provider="b-reseller")
    from app.services.reads import _seller_rank
    r = robot_with(unlinked, other)
    assert _seller_rank(unlinked, r) == _seller_rank(other, r)


def test_an_oem_for_a_different_manufacturer_is_not_direct() -> None:
    """A factory outlet is direct only for its own maker's robots."""
    foreign = offer(provider="a-other-oem", provider_type="OEM",
                    provider_manufacturer=OTHER_MAKER, price=10.0)
    direct = oem(provider="z-maker-store", price=9000.0)
    display = price_display_for(robot_with(foreign, direct))
    assert display is not None
    assert display.provider == "z-maker-store"


def test_market_rank_outranks_seller_preference() -> None:
    """A buyer who names a market is asking what is sold THERE. A local
    reseller's in-market offer therefore legitimately beats a worldwide OEM one
    — market applicability sits above the seller preference by design."""
    oem_global = oem(provider="maker-store", region="GLOBAL", price=13500.0)
    reseller_local = offer(provider="local-reseller", region="DE", price=17900.0)
    display = price_display_for(
        robot_with(oem_global, reseller_local), market_rank=EU_MARKET
    )
    assert display is not None
    assert (display.provider, display.region) == ("local-reseller", "DE")
    # Unfiltered, the same pair resolves to the manufacturer-direct offer.
    unfiltered = price_display_for(robot_with(oem_global, reseller_local))
    assert unfiltered is not None
    assert (unfiltered.provider, unfiltered.amount) == ("maker-store", 13500.0)


# --- configuration / edition comparability -----------------------------------

def test_a_variant_scoped_offer_never_represents_the_robot_record() -> None:
    """`variant_id` NULL is variant-AGNOSTIC, and `db/schema.sql` freezes the
    rule that a variant-specific price never attaches to a robot-level offer.
    So it is excluded, not merely ranked last — ranking would let it win
    whenever nothing else survived."""
    variant_only = oem(provider="maker-store", price=10.0, variant_id="variant-1")
    assert price_display_for(robot_with(variant_only)) is None


def test_a_confirmed_edition_outranks_an_unassessed_one_even_for_an_oem() -> None:
    """Confirmation precedence, which is NOT a statement about configuration.

    NULL means nobody assessed the edition match — not that the listing is for
    something else. So this pins the ranking rule only: a listing checked
    against the manufacturer's specification for this record is preferred over
    one never checked, and that precedence is settled before seller preference,
    so manufacturer-direct does not override it.
    """
    oem_unassessed = oem(provider="maker-store", price=100.0, edition_confirmed=None)
    reseller_confirmed = offer(
        provider="z-reseller", price=30000.0, edition_confirmed=True
    )
    display = price_display_for(robot_with(oem_unassessed, reseller_confirmed))
    assert display is not None
    assert display.provider == "z-reseller"
    assert display.edition_confirmed is True


def test_an_oem_offer_for_a_known_different_edition_is_excluded() -> None:
    """A KNOWN mismatch, which NULL above is not: `edition_confirmed` FALSE means
    the listing's own specification conflicts with this record. It is excluded
    outright, so being manufacturer-direct cannot rescue it — and the eligible
    reseller offer becomes the headline even though it costs far more."""
    oem_wrong_edition = oem(
        provider="maker-store", price=100.0, edition_confirmed=False
    )
    reseller_eligible = offer(provider="z-reseller", price=30000.0)
    display = price_display_for(robot_with(oem_wrong_edition, reseller_eligible))
    assert display is not None
    assert display.provider == "z-reseller"
    assert display.amount == 30000.0


def test_a_robot_whose_only_offer_is_a_known_different_edition_has_no_headline() -> None:
    """Excluded means excluded: UNKNOWN is the honest answer, not the mismatched
    listing's amount."""
    assert price_display_for(robot_with(oem(edition_confirmed=False))) is None


def test_a_variant_scoped_oem_offer_loses_to_a_record_level_reseller_offer() -> None:
    """The same point at the eligibility stage rather than the ranking stage."""
    oem_variant = oem(provider="maker-store", price=100.0, variant_id="variant-1")
    reseller_record = offer(provider="z-reseller", price=30000.0)
    display = price_display_for(robot_with(oem_variant, reseller_record))
    assert display is not None
    assert display.provider == "z-reseller"


def test_manufacturer_direct_still_wins_among_equally_comparable_offers() -> None:
    """Seller preference must still apply once comparability has tied."""
    reseller = offer(provider="a-reseller", price=100.0, edition_confirmed=True)
    direct = oem(provider="z-maker-store", price=13500.0, edition_confirmed=True)
    display = price_display_for(robot_with(reseller, direct))
    assert display is not None
    assert display.provider == "z-maker-store"


def test_price_is_not_consulted_across_tax_bases() -> None:
    """No tax normalisation exists, so a pre-tax figure must not undercut a
    VAT-inclusive one. With the amounts incomparable, the documented arbitrary
    tie-break decides — NOT a preference for either basis."""
    incl = oem(provider="maker-store", price=21000.0, price_basis="incl. 19% VAT")
    excl = oem(provider="maker-store", price=19000.0, price_basis="excl. VAT")
    display = price_display_for(robot_with(incl, excl))
    assert display is not None
    # The cheaper raw number did not simply win by being smaller.
    chosen = (display.price_basis, display.amount)
    assert chosen in {("incl. 19% VAT", 21000.0), ("excl. VAT", 19000.0)}
    # Whichever row won, it reports its own basis with its own amount.
    assert (display.price_basis == "excl. VAT") == (display.amount == 19000.0)


def test_the_amount_decides_only_within_one_currency_and_basis() -> None:
    """Inside a single comparable group the lower amount wins outright."""
    dearer = oem(provider="maker-store", price=23000.0, price_basis="incl. VAT")
    cheaper = oem(provider="maker-store", price=21000.0, price_basis="incl. VAT")
    display = price_display_for(robot_with(dearer, cheaper))
    assert display is not None
    assert display.amount == 21000.0


def test_price_never_decides_across_currencies() -> None:
    """A smaller number in another denomination is not a lower price. With no FX
    in the system, the amount is reached only after currency has already tied."""
    eur = offer(currency="EUR", price=9000.0)
    usd = offer(currency="USD", price=5000.0)
    display = price_display_for(robot_with(usd, eur))
    assert display is not None
    assert display.currency == "EUR"  # ordered by currency, not by 5000 < 9000
    assert display.amount == 9000.0


# --- market scope -------------------------------------------------------------

def test_an_offer_outside_the_market_is_dropped_not_ranked() -> None:
    """An offer in an unrelated market is not a worse answer — it is not an
    answer. With a US-only listing and an EU market, the price is UNKNOWN."""
    assert price_display_for(robot_with(offer(region="US")), market_rank=EU_MARKET) is None


def test_market_prefers_the_exact_region_over_a_member_country() -> None:
    de = offer(provider="a-seller", region="DE", price=10.0)
    eu = offer(provider="z-seller", region="EU", price=99999.0)
    display = price_display_for(robot_with(de, eu), market_rank=EU_MARKET)
    assert display is not None
    # Rank beats both provider order and amount: EU is the exact market scope.
    assert display.region == "EU"


def test_a_member_country_offer_is_reported_as_its_own_region() -> None:
    """Surfacing a DE offer in the EU market must not relabel it as EU-wide
    (`docs/20` §12.1)."""
    display = price_display_for(
        robot_with(offer(provider="reichelt", region="DE")), market_rank=EU_MARKET
    )
    assert display is not None
    assert display.region == "DE"


def test_without_a_market_geography_orders_nothing_and_hides_nothing() -> None:
    display = price_display_for(robot_with(offer(region="US", provider="us-seller")))
    assert display is not None
    assert display.region == "US"


# --- stability across re-imports ---------------------------------------------

def test_the_headline_is_identical_for_every_row_order() -> None:
    """Re-importing the catalogue regenerates offer UUIDs and rewrites
    `updated_at`, which reorders rows arbitrarily. The chosen headline must not
    move: selection uses durable attributes only.
    """
    offers = [
        offer(provider="reichelt", region="DE", currency="EUR", price=21000.0),
        oem(provider="unitree-store", region="GLOBAL", currency="USD", price=5900.0),
        offer(provider="reichelt", region="DE", currency="EUR", price=23000.0),
        offer(provider="a-distributor", region="EU", currency="EUR", price=30000.0),
    ]
    expected = price_display_for(robot_with(*offers), market_rank=EU_MARKET)
    assert expected is not None
    for permutation in itertools.permutations(offers):
        again = price_display_for(robot_with(*permutation), market_rank=EU_MARKET)
        assert again is not None
        assert (again.provider, again.region, again.currency, again.amount) == (
            expected.provider,
            expected.region,
            expected.currency,
            expected.amount,
        )


def test_ties_are_broken_by_amount_only_within_one_seller_region_and_currency() -> None:
    """Two rows identical in every durable attribute except the number: the
    lower price wins, because here the comparison is genuinely like-for-like."""
    display = price_display_for(
        robot_with(
            offer(provider="reichelt", region="DE", currency="EUR", price=23000.0),
            offer(provider="reichelt", region="DE", currency="EUR", price=21000.0),
        ),
        market_rank=EU_MARKET,
    )
    assert display is not None
    assert display.amount == 21000.0
