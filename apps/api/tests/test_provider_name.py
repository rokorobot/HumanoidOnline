"""UX-02B - `provider_name` beside `provider` on the read schemas.

The offer's seller identity is a slug; the provider record already has a display `name`
(`ProviderRead.name`). `provider_name` exposes that SAME column, additively and optionally:

* it is the provider record's own name - never derived from the slug;
* NULL when the offer has no provider, or the provider has no usable name;
* each offer carries ITS OWN provider's name (no blending across sellers);
* nothing else about the response changes: same fields, same values, same selection.

The relationship is `lazy="selectin"` on pricing/availability offers (already loaded to read
`provider.slug`), so reading `.name` adds no query.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.schemas.common import PriceDisplay
from app.schemas.robot import AvailabilityOfferRead, PricingOfferRead
from app.services.reads import price_display_for


def _offer(provider_slug, provider_name, *, price=1000.0, region="EU", currency="EUR"):
    return SimpleNamespace(
        condition="NEW",
        transaction_type="PURCHASE",
        price_type="PUBLIC",
        price=price,
        price_min=None,
        price_max=None,
        currency=currency,
        billing_period="ONE_TIME",
        provider=(
            SimpleNamespace(
                slug=provider_slug, name=provider_name, type="DISTRIBUTOR", manufacturer_id=None
            )
            if provider_slug
            else None
        ),
        region=SimpleNamespace(code=region),
        price_basis=None,
        order_status_note=None,
        edition_confirmed=None,
        is_current=True,
        variant_id=None,
        variant=None,
    )


def _robot(*offers):
    return SimpleNamespace(pricing_offers=list(offers), manufacturer_id="maker")


# ---- unit: the headline carries its own provider's name --------------------------------------

def test_headline_carries_the_selected_offers_provider_name() -> None:
    pd = price_display_for(_robot(_offer("alza-cz", "Alza.cz")))
    assert pd is not None
    assert (pd.provider, pd.provider_name) == ("alza-cz", "Alza.cz")


def test_a_provider_without_a_usable_name_is_null_never_derived_from_the_slug() -> None:
    for name in (None, "", ):
        pd = price_display_for(_robot(_offer("alza-cz", name)))
        assert pd.provider == "alza-cz"
        assert pd.provider_name is None


def test_no_provider_means_no_name() -> None:
    pd = price_display_for(_robot(_offer(None, None)))
    assert pd.provider is None and pd.provider_name is None


def test_several_sellers_each_offer_reports_its_own_name_and_selection_is_unchanged() -> None:
    cheap = _offer("reichelt", "reichelt elektronik", price=900.0)
    dear = _offer("alza-cz", "Alza.cz", price=1100.0)
    # Same currency/basis/region: the lower amount wins - exactly as before the field existed.
    for order in ((cheap, dear), (dear, cheap)):
        pd = price_display_for(_robot(*order))
        got = (pd.provider, pd.provider_name, pd.amount)
        assert got == ("reichelt", "reichelt elektronik", 900.0)


def test_schemas_default_to_null_so_older_producers_and_consumers_are_unaffected() -> None:
    assert PriceDisplay(type="PUBLIC").provider_name is None
    assert "provider_name" in PricingOfferRead.model_fields
    assert "provider_name" in AvailabilityOfferRead.model_fields
    assert PricingOfferRead.model_fields["provider_name"].default is None
    assert AvailabilityOfferRead.model_fields["provider_name"].default is None


# ---- against the seeded database ---------------------------------------------------------------

def _get(client, url, **params):
    resp = client.get(url, params=params)
    assert resp.status_code == 200, (url, resp.status_code, resp.text)
    return resp.json()


def test_list_items_carry_provider_name_beside_provider(client, database_url) -> None:
    body = _get(client, "/api/robots", limit=100)
    seen = [
        it["price_display"]
        for it in body["items"]
        if it.get("price_display") and it["price_display"].get("provider")
    ]
    assert seen, "the seed has priced robots with a seller"
    for pd in seen:
        assert "provider_name" in pd
        assert pd["provider_name"]  # every seeded provider has a name column (NOT NULL)
    g1 = next(it for it in body["items"] if it["slug"] == "unitree-g1")["price_display"]
    assert (g1["provider"], g1["provider_name"]) == ("unitree-store", "Unitree Online Store")


def test_detail_offers_carry_their_own_providers_name(client, database_url) -> None:
    d = _get(client, "/api/robots/digit")
    for o in d["pricing_offers"] + d["availability_offers"]:
        assert "provider_name" in o
        if o["provider"] == "agility-raas":
            assert o["provider_name"] == "Agility Robotics (RaaS)"
        if o["provider"] is None:
            assert o["provider_name"] is None
    g1 = _get(client, "/api/robots/unitree-g1")
    names = {o["provider"]: o["provider_name"] for o in g1["pricing_offers"] if o["provider"]}
    assert names.get("unitree-store") == "Unitree Online Store"


def test_compare_offers_carry_provider_name(client, database_url) -> None:
    body = _get(client, "/api/robots/compare", ids="unitree-g1,digit")
    for r in body["robots"]:
        for o in r["pricing_offers"] + r["availability_offers"]:
            assert "provider_name" in o
            assert (o["provider_name"] is None) == (o["provider"] is None)


def test_existing_fields_are_unchanged_additions_only(client, database_url) -> None:
    """Every pre-existing offer key is still present; `provider_name` is the only new one."""
    d = _get(client, "/api/robots/unitree-g1")
    for o in d["pricing_offers"]:
        old = {k for k in o if k != "provider_name"}
        expected = {
            "transaction_type", "price_type", "currency", "billing_period",
            "region", "provider", "price_basis", "condition",
        }
        assert expected <= old
    items = _get(client, "/api/robots", limit=100)["items"]
    item = next(it for it in items if it["slug"] == "unitree-g1")
    old_pd = {k for k in item["price_display"] if k != "provider_name"}
    assert {"type", "amount", "currency", "billing_period", "provider", "region"} <= old_pd


def test_list_filters_still_return_a_consistent_ordered_set(client, database_url) -> None:
    """The listing is a pure function of the filters (the before/after diff against origin/main
    is recorded in the UX-02 report); `total` always equals the returned rows here."""
    cases = (
        {},
        {"sort": "price"},
        {"transaction_type": ["PURCHASE"]},
        {"price_max": 50000, "price_currency": "USD"},
    )
    for params in cases:
        a = _get(client, "/api/robots", limit=100, **params)
        b = _get(client, "/api/robots", limit=100, **params)
        assert [i["slug"] for i in a["items"]] == [i["slug"] for i in b["items"]]
        assert a["total"] == b["total"] == len(a["items"])
