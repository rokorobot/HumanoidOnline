"""AGENT-02.1a — governed vocabulary validation in the SHARED catalogue filter.

The defect this pins: `apply_catalogue_filters` used to guard `autonomy_min` with
`if autonomy_min in AUTONOMY_ORDER:` and no `else`, so an unrecognised value
applied **no constraint at all** and returned the unfiltered catalogue as a
success. The other enum-backed filters had the opposite failure — the value
reached PostgreSQL and came back as a raw `DataError` (HTTP 500).

Both are corrected in `services/robot_filters.py` rather than in either caller,
so `/api/robots` and AGENT-02 `search_robots` inherit one rule. The invariant:

    an explicit invalid hard-filter input must NEVER silently become "no filter"

Sort is validated by the same path: `docs/20` §16 allows no client-controlled
sort key outside the four enumerated values, and a silent fallback to `name`
answers a different question while reporting success.
"""
from __future__ import annotations

import pytest

from app.models import enums as pg_enums
from app.services.robot_filters import (
    AUTONOMY_ORDER,
    SORT_COLUMNS,
    InvalidFilterEnum,
    InvalidSortKey,
    resolve_sort,
    validate_filter_vocabulary,
)

# Members that are real `db/schema.sql` enum values, used to prove every valid
# query still works. Read off the ORM declarations, never re-typed here.
COMMERCIAL_STATUS = tuple(pg_enums.commercial_status.enums)
TRANSACTION_TYPE = tuple(pg_enums.transaction_type.enums)
AVAILABILITY_STATUS = tuple(pg_enums.availability_status.enums)
MOBILITY = tuple(pg_enums.mobility_type.enums)
AUTONOMY = tuple(pg_enums.autonomy_level.enums)


def _get(client, url, **params):
    return client.get(url, params=params)


# --------------------------------------------------------------------------
# THE REGRESSION: an invalid hard filter must not widen the result set
# --------------------------------------------------------------------------


def test_invalid_autonomy_min_no_longer_widens_to_the_whole_catalogue(
    client, database_url
) -> None:
    """The core defect. `autonomy_min=NOT_AN_AUTONOMY` used to return HTTP 200
    with the FULL unfiltered catalogue — a hard constraint silently becoming no
    constraint, undetectable by the caller."""
    unfiltered = _get(client, "/api/robots", limit=100)
    assert unfiltered.status_code == 200
    total = unfiltered.json()["total"]
    assert total > 0, "seed required for this test to mean anything"

    resp = _get(client, "/api/robots", autonomy_min="NOT_AN_AUTONOMY", limit=100)
    assert resp.status_code == 422, "invalid autonomy_min must be rejected"
    assert "items" not in resp.json(), "a rejected filter must return no result set"


def test_valid_autonomy_min_still_constrains(client, database_url) -> None:
    """The repair must not cost the working behaviour: a valid value still
    filters, inclusively upward through the ladder."""
    everything = _get(client, "/api/robots", limit=100).json()["total"]
    floor = _get(client, "/api/robots", autonomy_min="TELEOPERATED", limit=100).json()
    strictest = _get(
        client, "/api/robots", autonomy_min="HIGHLY_AUTONOMOUS", limit=100
    ).json()

    # The floor admits every robot with a known autonomy and excludes only the
    # UNKNOWN (null) ones; the ceiling admits a subset of the floor.
    assert floor["total"] <= everything
    assert strictest["total"] <= floor["total"]
    assert all(it["commercial_status"] is not None for it in floor["items"])


# --------------------------------------------------------------------------
# NO RAW DATABASE ERROR MAY ESCAPE
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["commercial_status", "transaction_type", "availability_status", "mobility"],
)
def test_invalid_enum_never_reaches_postgres_as_a_dataerror(
    client, database_url, field
) -> None:
    resp = _get(client, "/api/robots", **{field: "NOT_A_MEMBER"}, limit=100)
    assert resp.status_code == 422, (field, resp.status_code, resp.text)


@pytest.mark.parametrize(
    "field",
    ["commercial_status", "transaction_type", "availability_status", "mobility",
     "autonomy_min"],
)
def test_no_internal_database_detail_leaks(client, database_url, field) -> None:
    """`docs/20` §17 — an error must not carry internal detail. The pre-fix
    behaviour leaked the PostgreSQL type name and the rejected literal through a
    psycopg `InvalidTextRepresentation`."""
    resp = _get(client, "/api/robots", **{field: "NOT_A_MEMBER"}, limit=100)
    body = resp.text.lower()
    for leaked in (
        "psycopg", "dataerror", "invalidtextrepresentation", "traceback",
        "sqlalchemy", "select ", "humanoid.",
    ):
        assert leaked not in body, f"{leaked!r} leaked in: {resp.text[:300]}"


def test_public_error_uses_the_repositorys_structured_client_error(
    client, database_url
) -> None:
    """Same shape the API already uses for unknown vocabulary elsewhere
    (`unknown country: ...`, `unknown use_case: ...`) — not a new framework."""
    resp = _get(client, "/api/robots", mobility="NOT_A_MEMBER", limit=100)
    assert resp.status_code == 422
    payload = resp.json()
    assert "detail" in payload
    assert payload["detail"] == "unknown mobility: 'NOT_A_MEMBER'"


# --------------------------------------------------------------------------
# LIST-VALUED FILTERS ARE ALL-OR-NOTHING
# --------------------------------------------------------------------------


def test_mixed_valid_and_invalid_members_reject_the_whole_call(
    client, database_url
) -> None:
    """Neither partially accepted (a wider answer) nor silently trimmed (a
    narrower one) — both would report success for a query nobody asked."""
    resp = client.get(
        "/api/robots",
        params=[("commercial_status", "COMMERCIAL"),
                ("commercial_status", "NOT_A_MEMBER"),
                ("limit", "100")],
    )
    assert resp.status_code == 422
    assert "NOT_A_MEMBER" in resp.text


# --------------------------------------------------------------------------
# EVERY VALID MEMBER STILL WORKS (no currently-valid query may change)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("member", COMMERCIAL_STATUS)
def test_every_commercial_status_member_is_accepted(client, database_url, member):
    assert _get(client, "/api/robots", commercial_status=member, limit=100).status_code == 200


@pytest.mark.parametrize("member", TRANSACTION_TYPE)
def test_every_transaction_type_member_is_accepted(client, database_url, member):
    assert _get(client, "/api/robots", transaction_type=member, limit=100).status_code == 200


@pytest.mark.parametrize("member", AVAILABILITY_STATUS)
def test_every_availability_status_member_is_accepted(client, database_url, member):
    assert _get(client, "/api/robots", availability_status=member, limit=100).status_code == 200


@pytest.mark.parametrize("member", MOBILITY)
def test_every_mobility_member_is_accepted(client, database_url, member):
    assert _get(client, "/api/robots", mobility=member, limit=100).status_code == 200


@pytest.mark.parametrize("member", AUTONOMY)
def test_every_autonomy_member_is_accepted(client, database_url, member):
    assert _get(client, "/api/robots", autonomy_min=member, limit=100).status_code == 200


def test_empty_filter_values_still_mean_no_filter(client, database_url) -> None:
    """Truthiness behaviour of the pre-existing filters is preserved: an empty
    string is "unset", not "invalid"."""
    baseline = _get(client, "/api/robots", limit=100).json()["total"]
    for field in ("mobility", "autonomy_min"):
        resp = _get(client, "/api/robots", **{field: ""}, limit=100)
        assert resp.status_code == 200, field
        assert resp.json()["total"] == baseline, field


# --------------------------------------------------------------------------
# SORT
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sort", ["name", "price", "payload", "newest",
             "-name", "-price", "-payload", "-newest"],
)
def test_every_valid_sort_form_still_works(client, database_url, sort) -> None:
    assert _get(client, "/api/robots", sort=sort, limit=100).status_code == 200


@pytest.mark.parametrize(
    "sort", ["garbage", "pric", "lowest_purchase_price", "-", "", "-garbage"],
)
def test_invalid_sort_is_rejected_not_silently_renamed(
    client, database_url, sort
) -> None:
    resp = _get(client, "/api/robots", sort=sort, limit=100)
    assert resp.status_code == 422, (sort, resp.status_code)


def test_sort_actually_orders_and_is_unchanged_for_valid_keys(
    client, database_url
) -> None:
    """Guards against the resolver silently losing direction while validating.

    Asserted as a mirror rather than against Python's `sorted()`: ordering is
    PostgreSQL's collation, which is not codepoint order ('Ameca' precedes
    'ASIMO'). Pinning the collation here would test the database, not the sort
    resolver — and would fail on a differently-collated deployment.
    """
    def names(sort: str) -> list[str]:
        body = _get(client, "/api/robots", sort=sort, limit=100).json()
        return [it["name"] for it in body["items"]]

    asc, desc = names("name"), names("-name")
    assert asc, "seed required"
    assert asc == list(reversed(desc))


# --------------------------------------------------------------------------
# UNIT-LEVEL: the shared layer itself, with no transport present
# --------------------------------------------------------------------------


def test_vocabulary_is_derived_from_the_schema_enums_not_retyped() -> None:
    """`docs/20` §2 / WorkOrder §1 — no second manually-maintained vocabulary.
    A schema enum gaining a member must widen the filter automatically."""
    from app.services.robot_filters import _ENUM_VOCABULARY

    assert _ENUM_VOCABULARY["commercial_status"] == tuple(pg_enums.commercial_status.enums)
    assert _ENUM_VOCABULARY["transaction_type"] == tuple(pg_enums.transaction_type.enums)
    assert _ENUM_VOCABULARY["availability_status"] == tuple(pg_enums.availability_status.enums)
    assert _ENUM_VOCABULARY["mobility"] == tuple(pg_enums.mobility_type.enums)
    assert _ENUM_VOCABULARY["autonomy_min"] == tuple(pg_enums.autonomy_level.enums)
    # UNKNOWN is a real commercial_status member and must stay filterable.
    assert "UNKNOWN" in _ENUM_VOCABULARY["commercial_status"]


def test_autonomy_order_matches_the_schema_enum_exactly() -> None:
    """`autonomy_min` is validated against the schema enum but *ranked* by
    AUTONOMY_ORDER. If the two ever diverge, a validated value could fail the
    ranking lookup — so the agreement is pinned rather than assumed."""
    assert tuple(AUTONOMY_ORDER) == tuple(pg_enums.autonomy_level.enums)


def test_validate_filter_vocabulary_raises_the_shared_service_error() -> None:
    with pytest.raises(InvalidFilterEnum) as exc:
        validate_filter_vocabulary(mobility="NOT_A_MEMBER")
    assert exc.value.field == "mobility"
    assert exc.value.value == "NOT_A_MEMBER"
    assert "BIPEDAL" in exc.value.allowed


def test_validate_filter_vocabulary_accepts_unset_inputs() -> None:
    validate_filter_vocabulary()
    validate_filter_vocabulary(commercial_status=[], mobility=None, autonomy_min="")


def test_resolve_sort_covers_exactly_the_four_v01_keys() -> None:
    assert set(SORT_COLUMNS) == {"name", "price", "payload", "newest"}
    for key in SORT_COLUMNS:
        assert resolve_sort(key) is not None
        assert resolve_sort(f"-{key}") is not None
    for bad in ("garbage", "pric", "lowest_purchase_price", "-", "", "Name", "slug"):
        with pytest.raises(InvalidSortKey):
            resolve_sort(bad)


def test_resolve_sort_rejects_a_non_string() -> None:
    with pytest.raises(InvalidSortKey):
        resolve_sort(None)  # type: ignore[arg-type]
