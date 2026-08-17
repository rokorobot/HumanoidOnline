"""AGENT-02.1d — HTTP/AGENT price convergence and the §10.5 constrained sort.

`/api/robots` previously applied `Robot.lowest_purchase_price <= price_max`: a
cache taking the cross-currency minimum across `PUBLIC`/`FROM` only, so it was
neither currency-safe nor complete. Measured against the seeded catalogue it
returned a strict *subset* of what the agent returned for the same ceiling —
`ESTIMATED` and `RANGE` priced robots were invisible to the public filter
entirely.

Both surfaces now share `services/pricing.py`. `docs/20` §21.2 requires the same
query to answer identically through the public API and the tool, so parity here
is asserted on canonical **slug identities and their order**, never on counts:
two different sets of the same size satisfy a count assertion while meaning the
surfaces disagree.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.services.agent_tools import InvalidArgument, search_robots

EUR, USD, GBP = "EUR", "USD", "GBP"


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


@pytest.fixture
def priced_robot():
    """Published robots with arbitrary purchase pricing and an optional cache value.

    `cache` writes `robot.lowest_purchase_price` directly so the adversarial
    sort fixtures can make the cache disagree with the comparable price — which
    is the only way to prove ordering follows the qualifying amount.
    """
    created: list = []

    def make(*offers, cache: float | None = None) -> str:
        mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
        slug = f"parity-probe-{uuid.uuid4().hex[:10]}"
        rid = _exec(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
            "VALUES (:s, :m, :n, TRUE) RETURNING id",
            s=slug, m=mfr_id, n=slug.upper(),
        ).scalar_one()
        created.append(rid)
        for price_type, currency, price, pmin, pmax in offers:
            _exec(
                "INSERT INTO pricing_offer (robot_id, transaction_type, price_type,"
                " currency, price, price_min, price_max, is_current) "
                "VALUES (:r, 'PURCHASE', CAST(:pt AS price_type), :c, :p, :mn, :mx, TRUE)",
                r=rid, pt=price_type, c=currency, p=price, mn=pmin, mx=pmax,
            )
        if cache is not None:
            _exec(
                "UPDATE robot SET lowest_purchase_price = :v WHERE id = :i",
                v=cache, i=rid,
            )
        return slug

    yield make
    for rid in created:
        _exec("DELETE FROM robot WHERE id = :i", i=rid)


def point(price_type, currency, amount):
    return (price_type, currency, amount, None, None)


def price_range(currency, low, high):
    return ("RANGE", currency, None, low, high)


def quote_only(currency=EUR):
    return ("QUOTE_ONLY", currency, None, None, None)


def http(client, **params) -> list[str]:
    """Ordered slugs from the public API."""
    resp = client.get("/api/robots", params={**params, "limit": 100})
    assert resp.status_code == 200, (params, resp.status_code, resp.text)
    return [it["slug"] for it in resp.json()["items"]]


def agent(**kwargs) -> list[str]:
    """Ordered slugs from the AGENT-02 tool."""
    with SessionLocal() as s:
        return [i.slug for i in search_robots(s, limit=100, **kwargs).items]


# --------------------------------------------------------------------------
# PARITY (docs/20 §21.2) — identities, then order
# --------------------------------------------------------------------------


@pytest.mark.parametrize("ceiling", [30000, 50000, 250000])
def test_http_and_agent_return_the_same_identities(client, database_url, ceiling):
    assert set(http(client, price_max=ceiling, price_currency=USD)) == set(
        agent(price_max=ceiling, price_currency=USD)
    )


def test_parity_across_every_price_shape(client, database_url, priced_robot):
    """One fixture per shape the rule distinguishes, then both surfaces compared."""
    priced_robot(point("PUBLIC", USD, 10000))
    priced_robot(point("FROM", USD, 15000))
    priced_robot(point("ESTIMATED", USD, 20000))
    priced_robot(price_range(USD, 5000, 25000))
    priced_robot(price_range(USD, 5000, 900000))
    priced_robot(quote_only(USD))
    priced_robot()
    priced_robot(point("PUBLIC", EUR, 100))
    priced_robot(point("PUBLIC", EUR, 90000), point("PUBLIC", USD, 12000))
    priced_robot(point("PUBLIC", USD, 28000), point("FROM", USD, 40000))

    for ceiling in (30000, 50000, 250000):
        assert set(http(client, price_max=ceiling, price_currency=USD)) == set(
            agent(price_max=ceiling, price_currency=USD)
        ), ceiling


def test_parity_of_order_under_a_constrained_price_sort(
    client, database_url, priced_robot
):
    for amount in (4000, 1000, 3000, 2000):
        priced_robot(point("PUBLIC", GBP, amount))
    for direction in ("price", "-price"):
        assert http(client, price_max=30000, price_currency=GBP, sort=direction) == \
            agent(price_max=30000, price_currency=GBP, sort=direction), direction


def test_parity_composes_with_region(client, database_url):
    """Region convergence and price convergence must hold simultaneously."""
    for region in ("US", "DE", "GLOBAL"):
        if _exec("SELECT id FROM region WHERE code=:c", c=region).scalar_one_or_none():
            assert set(
                http(client, region=region, price_max=250000, price_currency=USD)
            ) == set(agent(region=region, price_max=250000, price_currency=USD)), region


# --------------------------------------------------------------------------
# HARD PRICE CASES, THROUGH THE PUBLIC API
# --------------------------------------------------------------------------


@pytest.mark.parametrize("price_type", ["PUBLIC", "FROM", "ESTIMATED"])
def test_point_price_below_and_above(client, database_url, priced_robot, price_type):
    low = priced_robot(point(price_type, GBP, 20000))
    high = priced_robot(point(price_type, GBP, 40000))
    found = http(client, price_max=30000, price_currency=GBP)
    assert low in found
    assert high not in found


def test_boundary_equality_qualifies(client, database_url, priced_robot):
    slug = priced_robot(point("PUBLIC", GBP, 30000))
    assert slug in http(client, price_max=30000, price_currency=GBP)


def test_range_qualifies_only_on_upper_bound(client, database_url, priced_robot):
    inside = priced_robot(price_range(GBP, 1000, 25000))
    straddling = priced_robot(price_range(GBP, 1000, 45000))
    found = http(client, price_max=30000, price_currency=GBP)
    assert inside in found
    assert straddling not in found


def test_quote_only_and_unpriced_never_qualify(client, database_url, priced_robot):
    quoted = priced_robot(quote_only(GBP))
    unpriced = priced_robot()
    found = http(client, price_max=10**9, price_currency=GBP)
    assert quoted not in found
    assert unpriced not in found


def test_foreign_currency_only_never_qualifies(client, database_url, priced_robot):
    slug = priced_robot(point("PUBLIC", EUR, 1))
    assert slug not in http(client, price_max=30000, price_currency=GBP)


def test_mixed_currency_never_compares_across_currencies(
    client, database_url, priced_robot
):
    """The cache would take the cross-currency minimum (GBP 10,000) and wrongly
    qualify this robot under a EUR 30,000 ceiling."""
    slug = priced_robot(point("PUBLIC", EUR, 90000), point("PUBLIC", GBP, 10000))
    assert slug not in http(client, price_max=30000, price_currency=EUR)
    assert slug in http(client, price_max=30000, price_currency=GBP)


def test_one_qualifying_offer_among_several_qualifies(
    client, database_url, priced_robot
):
    slug = priced_robot(point("PUBLIC", GBP, 25000), point("FROM", GBP, 80000))
    assert slug in http(client, price_max=30000, price_currency=GBP)


def test_multiple_offers_do_not_duplicate_a_robot(client, database_url, priced_robot):
    slug = priced_robot(
        point("PUBLIC", GBP, 10000),
        point("FROM", GBP, 12000),
        point("ESTIMATED", GBP, 15000),
    )
    assert http(client, price_max=30000, price_currency=GBP).count(slug) == 1


# --------------------------------------------------------------------------
# THE INPUT PAIR (docs/04, docs/20 §5)
# --------------------------------------------------------------------------


def test_bare_price_max_is_rejected(client, database_url):
    resp = client.get("/api/robots", params={"price_max": 30000, "limit": 100})
    assert resp.status_code == 422
    assert "price_currency" in resp.json()["detail"]
    assert "items" not in resp.json()


def test_bare_price_currency_is_rejected(client, database_url):
    resp = client.get("/api/robots", params={"price_currency": USD, "limit": 100})
    assert resp.status_code == 422
    assert "items" not in resp.json()


def test_no_server_side_default_currency(client, database_url, priced_robot):
    """A bare ceiling must never be silently interpreted as USD."""
    priced_robot(point("PUBLIC", USD, 1000))
    assert client.get(
        "/api/robots", params={"price_max": 30000, "limit": 100}
    ).status_code == 422


def test_both_surfaces_reject_the_same_broken_pairs(client, database_url):
    assert client.get(
        "/api/robots", params={"price_max": 1, "limit": 100}
    ).status_code == 422
    with pytest.raises(InvalidArgument):
        with SessionLocal() as s:
            search_robots(s, price_max=1, limit=100)

    assert client.get(
        "/api/robots", params={"price_currency": USD, "limit": 100}
    ).status_code == 422
    with pytest.raises(InvalidArgument):
        with SessionLocal() as s:
            search_robots(s, price_currency=USD, limit=100)


# --------------------------------------------------------------------------
# §10.5 CONSTRAINED SORT — fixtures built to fail under the old cache sort
# --------------------------------------------------------------------------


def test_constrained_sort_follows_the_qualifying_price_not_the_cache(
    client, database_url, priced_robot
):
    """The decisive case.

    A qualifies at EUR 20,000 but caches 90,000; B qualifies at EUR 25,000 but
    caches 10,000. Ordering by the cache would put B first. Ordering by the
    amount that actually qualified them puts A first.
    """
    a = priced_robot(point("PUBLIC", EUR, 20000), cache=90000)
    b = priced_robot(point("PUBLIC", EUR, 25000), cache=10000)

    for surface in (
        lambda **kw: http(client, **kw),
        lambda **kw: agent(**kw),
    ):
        order = [s for s in surface(
            price_max=30000, price_currency=EUR, sort="price"
        ) if s in {a, b}]
        assert order == [a, b], "ordered by the cache instead of the qualifying price"


def test_constrained_descending_reverses_the_numeric_order(
    client, database_url, priced_robot
):
    a = priced_robot(point("PUBLIC", EUR, 20000), cache=90000)
    b = priced_robot(point("PUBLIC", EUR, 25000), cache=10000)
    order = [s for s in http(
        client, price_max=30000, price_currency=EUR, sort="-price"
    ) if s in {a, b}]
    assert order == [b, a]


def test_range_upper_bound_participates_in_the_sort(
    client, database_url, priced_robot
):
    cheap = priced_robot(price_range(EUR, 100, 12000))
    dear = priced_robot(price_range(EUR, 100, 26000))
    order = [s for s in http(
        client, price_max=30000, price_currency=EUR, sort="price"
    ) if s in {cheap, dear}]
    assert order == [cheap, dear], "sorted by lower bound instead of upper"


def test_sort_uses_the_per_robot_minimum_comparable_amount(
    client, database_url, priced_robot
):
    """A robot with several comparable offers sorts on its cheapest."""
    multi = priced_robot(point("FROM", EUR, 28000), point("PUBLIC", EUR, 11000))
    single = priced_robot(point("PUBLIC", EUR, 15000))
    order = [s for s in http(
        client, price_max=30000, price_currency=EUR, sort="price"
    ) if s in {multi, single}]
    assert order == [multi, single], "did not use the per-robot minimum"


def test_slug_breaks_exact_ties_deterministically(client, database_url, priced_robot):
    a = priced_robot(point("PUBLIC", EUR, 17000))
    b = priced_robot(point("PUBLIC", EUR, 17000))
    order = [s for s in http(
        client, price_max=30000, price_currency=EUR, sort="price"
    ) if s in {a, b}]
    assert order == sorted([a, b]), "equal prices not broken by slug"


def test_paging_equal_priced_robots_never_skips_or_repeats(
    client, database_url, priced_robot
):
    slugs = {priced_robot(point("PUBLIC", EUR, 17000)) for _ in range(4)}
    full = http(client, price_max=30000, price_currency=EUR, sort="price")
    paged: list[str] = []
    for offset in range(0, len(full), 2):
        resp = client.get("/api/robots", params={
            "price_max": 30000, "price_currency": EUR, "sort": "price",
            "limit": 2, "offset": offset,
        })
        paged += [it["slug"] for it in resp.json()["items"]]
    assert paged == full
    assert slugs <= set(paged)


# --------------------------------------------------------------------------
# UNCONSTRAINED SORT KEEPS THE CACHE (Phase 6)
# --------------------------------------------------------------------------


def test_unconstrained_price_sort_still_uses_the_cache(
    client, database_url, priced_robot
):
    """Without a currency-constrained query the sort/badge cache remains the
    sanctioned basis — and `price_currency` is not required merely to sort."""
    cheap_cache = priced_robot(point("PUBLIC", EUR, 90000), cache=10)
    dear_cache = priced_robot(point("PUBLIC", EUR, 100), cache=999999)

    resp = client.get("/api/robots", params={"sort": "price", "limit": 100})
    assert resp.status_code == 200
    order = [it["slug"] for it in resp.json()["items"] if it["slug"] in
             {cheap_cache, dear_cache}]
    assert order == [cheap_cache, dear_cache], "unconstrained sort stopped using cache"


def test_sort_price_without_currency_is_not_an_error(client, database_url):
    assert client.get(
        "/api/robots", params={"sort": "price", "limit": 100}
    ).status_code == 200
    assert client.get(
        "/api/robots", params={"sort": "-price", "limit": 100}
    ).status_code == 200


# --------------------------------------------------------------------------
# NON-PRICE QUERIES UNCHANGED
# --------------------------------------------------------------------------


def test_queries_without_a_price_are_unaffected(client, database_url):
    baseline = http(client)
    assert baseline == http(client, sort="name")
    assert set(http(client, mobility="BIPEDAL")) <= set(baseline)


def test_no_fx_path_exists_anywhere_in_the_price_layer() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    for rel in (
        "services/pricing.py",
        "services/agent_tools/pricing.py",
        "services/robot_filters.py",
        "routers/robots.py",
    ):
        body = (root / rel).read_text(encoding="utf-8").lower()
        for forbidden in (
            "exchange_rate", "fx_rate", "convert_currency", "base_currency",
        ):
            assert forbidden not in body, (rel, forbidden)


def test_the_legacy_cache_hard_filter_is_gone() -> None:
    """`lowest_purchase_price` may appear only as a sort column, never as a
    filter predicate, in the shared catalogue filter."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"

    def attributes(rel: str, *, inside: str | None = None) -> set[str]:
        """Attribute names actually referenced in code — prose is ignored, so a
        comment may explain why the cache is unusable without tripping this."""
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        if inside is not None:
            tree = next(
                n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == inside
            )
        return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}

    # The shared filter must not reference the cache at all, nor still accept a
    # `price_max` parameter for a caller to reach the old predicate through.
    filters = ast.parse(
        (root / "services/robot_filters.py").read_text(encoding="utf-8")
    )
    fn = next(
        n for n in ast.walk(filters)
        if isinstance(n, ast.FunctionDef) and n.name == "apply_catalogue_filters"
    )
    assert "lowest_purchase_price" not in {
        n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)
    }
    assert "price_max" not in {a.arg for a in fn.args.kwonlyargs + fn.args.args}

    # The cache survives in exactly one place: the unconstrained sort column.
    assert "lowest_purchase_price" in attributes("services/robot_filters.py")

    # The router never touches it directly at all.
    assert "lowest_purchase_price" not in attributes("routers/robots.py")
