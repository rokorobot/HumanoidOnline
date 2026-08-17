"""AGENT-02.1c — shared comparable-purchase-price semantics, evaluated in SQL.

`services/pricing.py` now owns the rule `docs/20` §10.3 ratifies: a robot
satisfies `price_max = X` in `price_currency = C` only when a *comparable*
purchase price denominated in `C` exists and is confirmed <= X. `PUBLIC`, `FROM`
and `ESTIMATED` contribute their point price, `RANGE` its upper bound,
`QUOTE_ONLY` nothing at all — and there is no FX anywhere, so a price in another
currency is incomparable rather than large.

Two things are pinned beyond the rule itself:

* **boundedness** (`docs/20` §16) — the ceiling is a SQL predicate, so `COUNT`
  and `LIMIT`/`OFFSET` happen server-side. The structural test at the bottom
  fails if a robot-row query is ever emitted without a `LIMIT`, which is what
  materialising the candidate set would look like.
* **warning scope** — the two exclusion reasons describe the whole filtered
  query, never the visible page, and are derived from one aggregate row rather
  than by inspecting candidates.
"""
from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import event, func, select, text

from app.db.session import SessionLocal, engine
from app.models.robot import Robot
from app.services.agent_tools import search_robots
from app.services.agent_tools.pricing import (
    EXCLUDED_ABOVE_LIMIT,
    EXCLUDED_UNPROVABLE,
)
from app.services.pricing import (
    apply_price_ceiling,
    ceiling_exclusions,
    robots_under_ceiling,
    robots_with_comparable_price,
)

EUR, USD, GBP = "EUR", "USD", "GBP"


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


@pytest.fixture
def priced_robot():
    """Published robots carrying arbitrary purchase pricing rows.

    Offers are given as `(price_type, currency, price, price_min, price_max)`
    and must satisfy `chk_price_type_shape` — which is the point: the shapes the
    comparable-price rule relies on are the ones the database already enforces.
    """
    created: list = []

    def make(*offers) -> str:
        mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
        slug = f"price-probe-{uuid.uuid4().hex[:10]}"
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


def _slugs(**kw) -> set[str]:
    with SessionLocal() as s:
        return {i.slug for i in search_robots(s, limit=100, **kw).items}


def _result(**kw):
    with SessionLocal() as s:
        return search_robots(s, limit=100, **kw)


def _qualifies(slug: str, *, ceiling: float, currency: str) -> bool:
    with SessionLocal() as s:
        stmt = apply_price_ceiling(
            select(Robot.slug).where(Robot.slug == slug),
            price_max=ceiling, price_currency=currency,
        )
        return s.execute(stmt).scalar_one_or_none() is not None


# --------------------------------------------------------------------------
# COMPARABLE PRICE — one case per price_type (docs/20 §10.3)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("price_type", ["PUBLIC", "FROM", "ESTIMATED"])
def test_point_price_below_ceiling_qualifies(priced_robot, database_url, price_type):
    slug = priced_robot(point(price_type, EUR, 20000))
    assert _qualifies(slug, ceiling=30000, currency=EUR)
    assert slug in _slugs(price_max=30000, price_currency=EUR)


@pytest.mark.parametrize("price_type", ["PUBLIC", "FROM", "ESTIMATED"])
def test_point_price_above_ceiling_excludes(priced_robot, database_url, price_type):
    slug = priced_robot(point(price_type, EUR, 40000))
    assert not _qualifies(slug, ceiling=30000, currency=EUR)
    res = _result(price_max=30000, price_currency=EUR)
    assert slug not in {i.slug for i in res.items}
    assert EXCLUDED_ABOVE_LIMIT in res.warnings


def test_price_exactly_at_the_ceiling_qualifies(priced_robot, database_url):
    """`<=`, not `<` — the boundary is inclusive."""
    slug = priced_robot(point("PUBLIC", EUR, 30000))
    assert _qualifies(slug, ceiling=30000, currency=EUR)


def test_range_qualifies_on_its_upper_bound(priced_robot, database_url):
    """A range satisfies a hard ceiling only when its whole span is under it."""
    inside = priced_robot(price_range(EUR, 10000, 25000))
    straddling = priced_robot(price_range(EUR, 10000, 45000))
    assert _qualifies(inside, ceiling=30000, currency=EUR)
    assert not _qualifies(straddling, ceiling=30000, currency=EUR)


def test_range_never_invents_a_point_value(priced_robot, database_url):
    """The lower bound must not be used to squeak under a ceiling."""
    slug = priced_robot(price_range(EUR, 1000, 999999))
    assert not _qualifies(slug, ceiling=30000, currency=EUR)


def test_quote_only_never_qualifies(priced_robot, database_url):
    slug = priced_robot(quote_only(EUR))
    assert not _qualifies(slug, ceiling=10**9, currency=EUR)
    res = _result(price_max=30000, price_currency=EUR)
    assert slug not in {i.slug for i in res.items}
    assert EXCLUDED_UNPROVABLE in res.warnings


def test_no_pricing_rows_never_qualifies(priced_robot, database_url):
    slug = priced_robot()
    assert not _qualifies(slug, ceiling=10**9, currency=EUR)
    res = _result(price_max=30000, price_currency=EUR)
    assert slug not in {i.slug for i in res.items}
    assert EXCLUDED_UNPROVABLE in res.warnings


# --------------------------------------------------------------------------
# CURRENCY — no FX, ever
# --------------------------------------------------------------------------


def test_other_currency_only_is_unprovable_never_above_limit(
    priced_robot, database_url
):
    """A EUR-1 robot under a USD ceiling failed on comparability, not price."""
    slug = priced_robot(point("PUBLIC", EUR, 1))
    assert not _qualifies(slug, ceiling=30000, currency=USD)
    with SessionLocal() as s:
        excl = ceiling_exclusions(
            s, select(Robot.id).where(Robot.slug == slug),
            price_max=30000, price_currency=USD,
        )
    assert excl.unprovable is True
    assert excl.above_limit is False, "reported as expensive, but never compared"


def test_a_cheap_foreign_price_never_satisfies_a_ceiling(priced_robot, database_url):
    """USD 1 must not satisfy a EUR ceiling: the numbers are not commensurable."""
    slug = priced_robot(point("PUBLIC", USD, 1))
    assert not _qualifies(slug, ceiling=30000, currency=EUR)


def test_mixed_currency_robot_is_judged_only_in_the_requested_currency(
    priced_robot, database_url
):
    """The `lowest_purchase_price` regression: the cache would take the
    cross-currency minimum (USD 10,000) and wrongly qualify this under a EUR
    30,000 ceiling."""
    slug = priced_robot(point("PUBLIC", EUR, 90000), point("PUBLIC", USD, 10000))
    assert not _qualifies(slug, ceiling=30000, currency=EUR)
    assert _qualifies(slug, ceiling=30000, currency=USD)
    with SessionLocal() as s:
        excl = ceiling_exclusions(
            s, select(Robot.id).where(Robot.slug == slug),
            price_max=30000, price_currency=EUR,
        )
    assert excl.above_limit is True and excl.unprovable is False


def test_three_currencies_stay_independent(priced_robot, database_url):
    slug = priced_robot(
        point("PUBLIC", EUR, 50000), point("PUBLIC", USD, 20000), quote_only(GBP)
    )
    assert not _qualifies(slug, ceiling=30000, currency=EUR)
    assert _qualifies(slug, ceiling=30000, currency=USD)
    assert not _qualifies(slug, ceiling=10**9, currency=GBP)


def test_no_fx_machinery_exists_in_either_price_module() -> None:
    """Structural: neither the shared service nor the adapter may convert."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app/services"
    for rel in ("pricing.py", "agent_tools/pricing.py"):
        body = (root / rel).read_text(encoding="utf-8").lower()
        for forbidden in (
            "exchange_rate", "fx_rate", "convert_currency", "base_currency",
        ):
            assert forbidden not in body, (rel, forbidden)


def test_the_cross_currency_cache_is_never_read() -> None:
    """The shared service must not touch `robot.lowest_purchase_price`.

    Asserted against the parsed syntax tree, not the file text, so the module's
    prose may explain *why* the cache is unusable without tripping the check.
    """
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app/services/pricing.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    referenced = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "lowest_purchase_price" not in referenced
    assert "lowest_price_currency" not in referenced


# --------------------------------------------------------------------------
# MULTIPLE OFFERS PER ROBOT
# --------------------------------------------------------------------------


def test_one_qualifying_offer_is_enough(priced_robot, database_url):
    """A robot with a qualifying AND an above-limit offer still qualifies —
    the cheapest comparable price governs."""
    slug = priced_robot(point("PUBLIC", EUR, 25000), point("FROM", EUR, 80000))
    assert _qualifies(slug, ceiling=30000, currency=EUR)


def test_multiple_qualifying_offers_do_not_duplicate_the_robot(
    priced_robot, database_url
):
    slug = priced_robot(
        point("PUBLIC", EUR, 10000),
        point("FROM", EUR, 12000),
        point("ESTIMATED", EUR, 15000),
    )
    items = [i.slug for i in _result(price_max=30000, price_currency=EUR).items]
    assert items.count(slug) == 1


def test_mixed_price_types_use_the_comparable_one(priced_robot, database_url):
    """QUOTE_ONLY contributes nothing, so the point price decides."""
    slug = priced_robot(quote_only(EUR), point("PUBLIC", EUR, 20000))
    assert _qualifies(slug, ceiling=30000, currency=EUR)

    unprovable = priced_robot(quote_only(EUR), price_range(EUR, 50000, 90000))
    assert not _qualifies(unprovable, ceiling=30000, currency=EUR)


def test_non_current_offers_are_ignored(priced_robot, database_url):
    slug = priced_robot(point("PUBLIC", EUR, 20000))
    _exec(
        "UPDATE pricing_offer SET is_current = FALSE WHERE robot_id = "
        "(SELECT id FROM robot WHERE slug = :s)", s=slug,
    )
    assert not _qualifies(slug, ceiling=30000, currency=EUR)


def test_non_purchase_money_is_not_comparable_to_a_purchase_ceiling(
    priced_robot, database_url
):
    slug = priced_robot()
    _exec(
        "INSERT INTO pricing_offer (robot_id, transaction_type, price_type, currency,"
        " price, is_current) VALUES ((SELECT id FROM robot WHERE slug = :s),"
        " 'RENTAL', 'PUBLIC', 'EUR', 500, TRUE)", s=slug,
    )
    assert not _qualifies(slug, ceiling=30000, currency=EUR)


# --------------------------------------------------------------------------
# SET-LEVEL HELPERS
# --------------------------------------------------------------------------


def test_comparable_and_qualifying_sets_are_distinct(priced_robot, database_url):
    expensive = priced_robot(point("PUBLIC", EUR, 90000))
    cheap = priced_robot(point("PUBLIC", EUR, 900))
    quoted = priced_robot(quote_only(EUR))

    with SessionLocal() as s:
        comparable = set(s.execute(robots_with_comparable_price(EUR)).scalars())
        under = set(s.execute(robots_under_ceiling(EUR, 30000)).scalars())
        ids = {
            slug: s.execute(
                select(Robot.id).where(Robot.slug == slug)
            ).scalar_one()
            for slug in (expensive, cheap, quoted)
        }
    assert ids[expensive] in comparable and ids[expensive] not in under
    assert ids[cheap] in comparable and ids[cheap] in under
    assert ids[quoted] not in comparable and ids[quoted] not in under


# --------------------------------------------------------------------------
# UNKNOWN IS NEVER COERCED
# --------------------------------------------------------------------------


def test_unknown_specs_survive_a_price_query(priced_robot, database_url):
    slug = priced_robot(point("PUBLIC", EUR, 20000))
    item = next(
        i for i in _result(price_max=30000, price_currency=EUR).items
        if i.slug == slug
    )
    assert item.payload_kg is None and item.height_cm is None
    assert item.payload_kg is not False and item.payload_kg != 0
    assert item.mobility is None


def test_an_excluded_robot_is_not_reported_as_priced_zero(priced_robot, database_url):
    """Failing a ceiling is not a claim about the robot."""
    slug = priced_robot(quote_only(EUR))
    item = next(i for i in _result().items if i.slug == slug)
    assert item.price_display.type == "QUOTE_ONLY"
    assert item.price_display.amount is None


# --------------------------------------------------------------------------
# PAGINATION + WARNING SCOPE
# --------------------------------------------------------------------------


def test_total_is_independent_of_page_size(priced_robot, database_url):
    for amount in (1000, 2000, 3000, 4000):
        priced_robot(point("PUBLIC", GBP, amount))
    totals = {
        limit: search_robots_total(price_max=30000, price_currency=GBP, limit=limit)
        for limit in (1, 2, 100)
    }
    assert len(set(totals.values())) == 1, totals
    assert totals[1] >= 4


def search_robots_total(**kw) -> int:
    with SessionLocal() as s:
        return search_robots(s, **kw).total


def test_pagination_after_price_filtering_is_complete_and_disjoint(
    priced_robot, database_url
):
    for amount in (1000, 2000, 3000, 4000):
        priced_robot(point("PUBLIC", GBP, amount))
    with SessionLocal() as s:
        full = [i.slug for i in search_robots(
            s, price_max=30000, price_currency=GBP, limit=100).items]
        pages = []
        for offset in range(0, len(full), 2):
            pages += [i.slug for i in search_robots(
                s, price_max=30000, price_currency=GBP, limit=2, offset=offset).items]
    assert pages == full, "paging skipped, repeated or reordered rows"


def test_warnings_describe_the_query_not_the_visible_page(
    priced_robot, database_url
):
    """A page of 1 must still report both kinds of exclusion happening
    elsewhere in the result set."""
    priced_robot(point("PUBLIC", GBP, 1000))       # qualifies
    priced_robot(point("PUBLIC", GBP, 999999))     # above limit
    priced_robot(quote_only(GBP))                  # unprovable

    narrow = _result_limit(price_max=30000, price_currency=GBP, limit=1)
    wide = _result_limit(price_max=30000, price_currency=GBP, limit=100)
    assert narrow.warnings == wide.warnings
    assert EXCLUDED_ABOVE_LIMIT in narrow.warnings
    assert EXCLUDED_UNPROVABLE in narrow.warnings
    assert len(narrow.items) == 1


def _result_limit(**kw):
    with SessionLocal() as s:
        return search_robots(s, **kw)


def test_warnings_are_absent_when_nothing_was_excluded(priced_robot, database_url):
    """No spurious reason codes: a query where every candidate qualifies
    reports none."""
    slug = priced_robot(point("PUBLIC", GBP, 1000))
    with SessionLocal() as s:
        res = search_robots(
            s, q=slug.replace("-", " "), price_max=30000, price_currency=GBP, limit=100
        )
    if res.total == 1 and res.items[0].slug == slug:
        assert res.warnings == []


# --------------------------------------------------------------------------
# BOUNDEDNESS (docs/20 §16) — the structural regression
# --------------------------------------------------------------------------


def test_price_query_never_materialises_the_catalogue(priced_robot, database_url):
    """Fails if a price-constrained search emits an unbounded robot-row query.

    Structural rather than timed: every statement that loads full robot rows
    (identified by selecting `robot.slug`) must carry a LIMIT. The old
    implementation ran `SELECT robot.* … ` with no LIMIT and filtered in Python,
    which this catches deterministically at any catalogue size.
    """
    for amount in (1000, 2000, 3000, 4000, 5000):
        priced_robot(point("PUBLIC", GBP, amount))

    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(" ".join(statement.split()).lower())

    event.listen(engine, "after_cursor_execute", record)
    try:
        with SessionLocal() as s:
            result = search_robots(
                s, price_max=30000, price_currency=GBP, limit=2, offset=0
            )
    finally:
        event.remove(engine, "after_cursor_execute", record)

    assert result.total > result.limit, "need more matches than one page"
    assert len(result.items) == 2

    row_loads = [q for q in seen if re.search(r"\brobot\.slug\b", q)]
    assert row_loads, "expected at least one robot-row query"
    unbounded = [q for q in row_loads if " limit " not in q]
    assert not unbounded, "unbounded robot-row query:\n" + "\n\n".join(unbounded)


def test_count_and_reasons_are_single_row_queries(priced_robot, database_url):
    """The count and the warning aggregate must not grow with the catalogue."""
    priced_robot(point("PUBLIC", GBP, 1000))
    priced_robot(quote_only(GBP))

    with SessionLocal() as s:
        candidates = select(Robot.id).where(Robot.is_published.is_(True))
        excl = ceiling_exclusions(
            s, candidates, price_max=30000, price_currency=GBP
        )
        total = s.execute(
            apply_price_ceiling(
                select(func.count(Robot.id)).where(Robot.is_published.is_(True)),
                price_max=30000, price_currency=GBP,
            )
        ).scalar_one()
    assert isinstance(total, int)
    assert excl.unprovable is True
