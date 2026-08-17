"""AGENT-02.1 — `search_robots` against the ratified contract (`docs/20`).

Every fixture is created inside the test and removed afterwards, so the shared
seeded database is left exactly as found (the convention of
`test_truth_regressions.py`).

The two rules with the most ways to go quietly wrong are pinned hardest:

* **currency** — a hard ceiling must never compare across currencies, and a
  robot priced only in another currency must be reported *unprovable*, never
  *above limit*;
* **geography** — a GLOBAL offer satisfies a narrower query but keeps its own
  region identity.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.models import enums as pg_enums
from app.services.agent_tools import (
    InvalidArgument,
    InvalidEnum,
    InvalidPagination,
    search_robots,
)
from app.services.agent_tools.pricing import (
    EXCLUDED_ABOVE_LIMIT,
    EXCLUDED_UNPROVABLE,
)


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _region_id(code: str):
    return _exec("SELECT id FROM region WHERE code = :c", c=code).scalar_one_or_none()


@pytest.fixture
def robot_factory():
    """Create published robots with optional purchase pricing / availability."""
    created: list = []

    def make(
        *,
        published: bool = True,
        prices: list[tuple[str, str, float | None]] | None = None,
        avail_region_code: str | None = "__none__",
        **cols,
    ) -> str:
        mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
        slug = _uniq("agent-probe")
        extra_cols = "".join(f", {k}" for k in cols)
        extra_vals = "".join(f", :{k}" for k in cols)
        rid = _exec(
            f"INSERT INTO robot (slug, manufacturer_id, name, is_published{extra_cols}) "
            f"VALUES (:s, :m, :n, :p{extra_vals}) RETURNING id",
            s=slug, m=mfr_id, n=slug.upper(), p=published, **cols,
        ).scalar_one()
        created.append(rid)

        for price_type, currency, amount in prices or []:
            _exec(
                "INSERT INTO pricing_offer (robot_id, transaction_type, price_type, "
                "currency, price, is_current) "
                "VALUES (:r, 'PURCHASE', CAST(:pt AS price_type), :c, :a, TRUE)",
                r=rid, pt=price_type, c=currency, a=amount,
            )
        if avail_region_code != "__none__":
            _exec(
                "INSERT INTO availability_offer (robot_id, transaction_type, "
                "availability_status, region_id, is_current) "
                "VALUES (:r, 'PURCHASE', 'AVAILABLE', :rg, TRUE)",
                r=rid, rg=_region_id(avail_region_code) if avail_region_code else None,
            )
        return slug

    yield make
    for rid in created:
        _exec("DELETE FROM robot WHERE id = :i", i=rid)


def _slugs(**kw) -> set[str]:
    with SessionLocal() as s:
        return {i.slug for i in search_robots(s, **kw).items}


def _result(**kw):
    with SessionLocal() as s:
        return search_robots(s, **kw)


# --------------------------------------------------------------------------
# PUBLICATION
# --------------------------------------------------------------------------


def test_unpublished_robot_is_never_returned(robot_factory) -> None:
    slug = robot_factory(published=False)
    assert slug not in _slugs(limit=100)


def test_discovery_candidates_are_never_returned() -> None:
    """Candidates live in their own table; `search_robots` reads canonical only."""
    with SessionLocal() as s:
        items = search_robots(s, limit=100).items
    names = {i.name for i in items}
    assert not any(n.startswith("Probe ") for n in names)


# --------------------------------------------------------------------------
# REGION (docs/20 §12)
# --------------------------------------------------------------------------


def test_exact_region_offer_qualifies(robot_factory) -> None:
    slug = robot_factory(avail_region_code="US")
    assert slug in _slugs(region="US", limit=100)


def test_ancestor_region_offer_qualifies(robot_factory) -> None:
    """An EU-scoped offer applies to a buyer in DE (EU is DE's ancestor)."""
    if _region_id("DE") is None or _region_id("EU") is None:
        pytest.skip("DE/EU regions not present in this dataset")
    slug = robot_factory(avail_region_code="EU")
    assert slug in _slugs(region="DE", limit=100)


def test_global_offer_qualifies_for_a_narrower_geography(robot_factory) -> None:
    slug = robot_factory(avail_region_code="GLOBAL")
    assert slug in _slugs(region="US", limit=100)


def test_global_offer_keeps_its_own_region_identity(robot_factory) -> None:
    """Applicability must never be written back as identity."""
    slug = robot_factory(avail_region_code="GLOBAL")
    with SessionLocal() as s:
        rid = _exec("SELECT id FROM robot WHERE slug = :s", s=slug).scalar_one()
        code = _exec(
            "SELECT r.code FROM availability_offer a JOIN region r ON r.id = a.region_id "
            "WHERE a.robot_id = :i",
            i=rid,
        ).scalar_one()
        assert code == "GLOBAL", "a GLOBAL offer was relabelled as the queried region"
        assert slug in {i.slug for i in search_robots(s, region="US", limit=100).items}


def test_unrelated_region_does_not_qualify(robot_factory) -> None:
    slug = robot_factory(avail_region_code="US")
    assert slug not in _slugs(region="CN", limit=100)


def test_region_agnostic_offer_applies_everywhere(robot_factory) -> None:
    """A NULL region is region-agnostic, not unknown-and-therefore-excluded."""
    slug = robot_factory(avail_region_code=None)
    assert slug in _slugs(region="US", limit=100)


def test_unknown_region_is_rejected_not_silently_widened() -> None:
    with pytest.raises(InvalidArgument):
        _result(region="NOT-A-REGION")


# --------------------------------------------------------------------------
# PRICE / CURRENCY (docs/20 §10.3) — the core of this slice
# --------------------------------------------------------------------------


def test_price_max_without_currency_is_invalid_argument() -> None:
    with pytest.raises(InvalidArgument):
        _result(price_max=30000)


def test_price_currency_without_price_max_is_invalid_argument() -> None:
    with pytest.raises(InvalidArgument):
        _result(price_currency="EUR")


def test_same_currency_price_below_ceiling_qualifies(robot_factory) -> None:
    slug = robot_factory(prices=[("PUBLIC", "EUR", 20000)])
    assert slug in _slugs(price_max=30000, price_currency="EUR", limit=100)


def test_same_currency_price_above_ceiling_excludes_as_above_limit(
    robot_factory,
) -> None:
    slug = robot_factory(prices=[("PUBLIC", "EUR", 40000)])
    res = _result(price_max=30000, price_currency="EUR", limit=100)
    assert slug not in {i.slug for i in res.items}
    assert EXCLUDED_ABOVE_LIMIT in res.warnings


def test_eur_ceiling_never_compares_a_usd_price_numerically(robot_factory) -> None:
    """USD 20,000 must not satisfy a EUR 30,000 ceiling — no FX."""
    slug = robot_factory(prices=[("PUBLIC", "USD", 20000)])
    assert slug not in _slugs(price_max=30000, price_currency="EUR", limit=100)


def test_usd_ceiling_never_compares_a_eur_price_numerically(robot_factory) -> None:
    slug = robot_factory(prices=[("PUBLIC", "EUR", 20000)])
    assert slug not in _slugs(price_max=30000, price_currency="USD", limit=100)


def test_other_currency_only_excludes_as_unprovable_not_above_limit(
    robot_factory,
) -> None:
    """The distinction that matters: a EUR-only robot under a USD ceiling failed
    on comparability, not on price."""
    slug = robot_factory(prices=[("PUBLIC", "EUR", 1)])
    res = _result(price_max=30000, price_currency="USD", limit=100)
    assert slug not in {i.slug for i in res.items}
    assert EXCLUDED_UNPROVABLE in res.warnings


def test_quote_only_excludes_as_unprovable(robot_factory) -> None:
    slug = robot_factory(prices=[("QUOTE_ONLY", "EUR", None)])
    res = _result(price_max=30000, price_currency="EUR", limit=100)
    assert slug not in {i.slug for i in res.items}
    assert EXCLUDED_UNPROVABLE in res.warnings


def test_no_price_excludes_as_unprovable(robot_factory) -> None:
    slug = robot_factory()
    res = _result(price_max=30000, price_currency="EUR", limit=100)
    assert slug not in {i.slug for i in res.items}
    assert EXCLUDED_UNPROVABLE in res.warnings


def test_mixed_currency_robot_cannot_use_a_cross_currency_minimum(
    robot_factory,
) -> None:
    """The `lowest_purchase_price` regression, pinned.

    A robot priced EUR 90,000 and USD 10,000 caches the numerically smallest
    figure (USD 10,000) with no currency partition. Under a EUR 30,000 ceiling
    the cache would wrongly qualify it; the governed rule must not.
    """
    slug = robot_factory(
        prices=[("PUBLIC", "EUR", 90000), ("PUBLIC", "USD", 10000)]
    )
    assert slug not in _slugs(price_max=30000, price_currency="EUR", limit=100)
    # ...and it is correctly reported above-limit in EUR, not unprovable.
    res = _result(price_max=30000, price_currency="EUR", limit=100)
    assert EXCLUDED_ABOVE_LIMIT in res.warnings
    # The same robot DOES qualify under a USD ceiling that its USD price meets.
    assert slug in _slugs(price_max=30000, price_currency="USD", limit=100)


def test_no_fx_conversion_path_exists() -> None:
    """Structural: the pricing module must contain no conversion machinery."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app/services/agent_tools/pricing.py"
    body = src.read_text(encoding="utf-8").lower()
    for forbidden in ("exchange_rate", "fx_rate", "convert_currency", "base_currency"):
        assert forbidden not in body


# --------------------------------------------------------------------------
# UNKNOWN (docs/20 §9)
# --------------------------------------------------------------------------


def test_unknown_specs_stay_null_and_are_never_coerced(robot_factory) -> None:
    slug = robot_factory()
    with SessionLocal() as s:
        item = next(
            i for i in search_robots(s, limit=100).items if i.slug == slug
        )
    assert item.payload_kg is None
    assert item.height_cm is None
    assert item.payload_kg is not False and item.payload_kg != 0
    assert item.mobility is None


def test_hard_positive_flag_constraint_excludes_unknown(robot_factory) -> None:
    """UNKNOWN does not satisfy an explicitly requested positive requirement,
    and is still reported as null rather than false."""
    unknown = robot_factory()  # has_sdk NULL
    yes = robot_factory(has_sdk=True)
    found = _slugs(has_sdk=True, limit=100)
    assert yes in found
    assert unknown not in found


# --------------------------------------------------------------------------
# PAGINATION (docs/20 §16)
# --------------------------------------------------------------------------


def test_pagination_defaults_and_max_are_inherited() -> None:
    res = _result()
    assert res.limit == 24
    assert _result(limit=100).limit == 100


@pytest.mark.parametrize("limit", [0, -1, 101, 1000])
def test_out_of_range_limit_is_rejected_never_clamped(limit) -> None:
    with pytest.raises(InvalidPagination):
        _result(limit=limit)


def test_negative_offset_is_rejected() -> None:
    with pytest.raises(InvalidPagination):
        _result(offset=-1)


def test_pagination_is_deterministic_and_continuable() -> None:
    first = _result(limit=1, offset=0)
    second = _result(limit=1, offset=1)
    assert first.total == second.total
    assert first.items[0].slug != second.items[0].slug
    both = {first.items[0].slug, second.items[0].slug}
    page = _result(limit=2, offset=0)
    assert {i.slug for i in page.items} == both


# --------------------------------------------------------------------------
# CONTRACT SHAPE
# --------------------------------------------------------------------------


def test_result_carries_canonical_identity_and_contract_version() -> None:
    res = _result(limit=5)
    assert res.contract_version == "agent-tools/0.1"
    for item in res.items:
        assert item.slug and item.name
        assert item.manufacturer.slug and item.manufacturer.name


def test_warning_codes_are_not_transport_errors() -> None:
    """Exclusion reasons ride in `warnings`; the call still succeeds."""
    res = _result(price_max=1, price_currency="EUR", limit=100)
    assert res.warnings, "expected an exclusion reason"
    for w in res.warnings:
        assert w.startswith("price_max_excluded_")
        assert w not in {"INVALID_ARGUMENT", "INVALID_PAGINATION", "NOT_FOUND"}


# --------------------------------------------------------------------------
# VOCABULARY — AGENT-02.1a (docs/20 §5 enum errors, §16 sort allowlist)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"commercial_status": ["NOT_A_MEMBER"]},
        {"transaction_type": ["NOT_A_MEMBER"]},
        {"availability_status": ["NOT_A_MEMBER"]},
        {"mobility": "NOT_A_MEMBER"},
        {"autonomy_min": "NOT_A_MEMBER"},
    ],
    ids=["commercial_status", "transaction_type", "availability_status",
         "mobility", "autonomy_min"],
)
def test_unknown_enum_member_raises_invalid_enum(kwargs) -> None:
    """`docs/20` §5: "Unknown enum member → INVALID_ENUM". Not INVALID_ARGUMENT —
    the codes are distinct and §21.12 requires each to be reachable."""
    with pytest.raises(InvalidEnum) as exc:
        _result(limit=100, **kwargs)
    assert exc.value.code == "INVALID_ENUM"


def test_invalid_enum_is_genuinely_reachable() -> None:
    """Before AGENT-02.1a the class existed and was exported but was raised
    nowhere, so the contract code was unreachable."""
    with pytest.raises(InvalidEnum):
        _result(mobility="NOT_A_MEMBER", limit=100)


def test_mixed_valid_and_invalid_members_reject_the_entire_call() -> None:
    """No partial acceptance and no silent dropping: either would answer a
    different question than the caller asked, and report success."""
    with pytest.raises(InvalidEnum):
        _result(commercial_status=["COMMERCIAL", "NOT_A_MEMBER"], limit=100)
    with pytest.raises(InvalidEnum):
        _result(commercial_status=["NOT_A_MEMBER", "COMMERCIAL"], limit=100)


def test_an_invalid_hard_constraint_never_degrades_to_no_constraint() -> None:
    """The regression that motivated this slice: `autonomy_min` used to be
    silently ignored, returning the FULL catalogue as a success."""
    unfiltered = _result(limit=100).total
    assert unfiltered > 0
    with pytest.raises(InvalidEnum):
        _result(autonomy_min="NOT_AN_AUTONOMY", limit=100)


@pytest.mark.parametrize("member", tuple(pg_enums.commercial_status.enums))
def test_every_commercial_status_member_remains_accepted(member) -> None:
    assert _result(commercial_status=[member], limit=100).total >= 0


@pytest.mark.parametrize("member", tuple(pg_enums.transaction_type.enums))
def test_every_transaction_type_member_remains_accepted(member) -> None:
    assert _result(transaction_type=[member], limit=100).total >= 0


@pytest.mark.parametrize("member", tuple(pg_enums.availability_status.enums))
def test_every_availability_status_member_remains_accepted(member) -> None:
    assert _result(availability_status=[member], limit=100).total >= 0


@pytest.mark.parametrize("member", tuple(pg_enums.mobility_type.enums))
def test_every_mobility_member_remains_accepted(member) -> None:
    assert _result(mobility=member, limit=100).total >= 0


@pytest.mark.parametrize("member", tuple(pg_enums.autonomy_level.enums))
def test_every_autonomy_member_remains_accepted(member) -> None:
    assert _result(autonomy_min=member, limit=100).total >= 0


@pytest.mark.parametrize(
    "sort", ["garbage", "pric", "lowest_purchase_price", "-", "", "-garbage"]
)
def test_invalid_sort_raises_invalid_argument(sort) -> None:
    """`sort` is a contract allowlist, not a `db/schema.sql` enum, so it fails as
    INVALID_ARGUMENT (`docs/20` §17) — never a silent fallback to `name`."""
    with pytest.raises(InvalidArgument) as exc:
        _result(sort=sort, limit=100)
    assert exc.value.code == "INVALID_ARGUMENT"


def test_invalid_sort_is_not_reported_as_an_enum_error() -> None:
    """The two codes stay disjoint: sort carries no schema vocabulary."""
    with pytest.raises(InvalidArgument) as exc:
        _result(sort="garbage", limit=100)
    assert not isinstance(exc.value, InvalidEnum)


@pytest.mark.parametrize(
    "sort",
    ["name", "price", "payload", "newest", "-name", "-price", "-payload", "-newest"],
)
def test_every_valid_sort_form_still_works(sort) -> None:
    assert _result(sort=sort, limit=100).limit == 100


def test_valid_descending_sort_actually_reverses() -> None:
    asc = [i.slug for i in _result(sort="name", limit=100).items]
    desc = [i.slug for i in _result(sort="-name", limit=100).items]
    assert asc and asc == list(reversed(desc))
