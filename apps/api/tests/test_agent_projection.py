"""AGENT-02.1g — the public agent projection and its identifier boundary.

`docs/20` §8 makes the slug the canonical external identifier and states that
internal database UUIDs are never the public contract; §20 forbids database
selectors; §21.10 requires that no raw database identifier appear in any request
or response. §5 additionally makes `canonical_url` a mandatory list field.

`search_robots` previously returned the governed HTTP `RobotListItem`, which
carries `id=str(robot.id)` — the row's PostgreSQL UUID — and carries no
`canonical_url`. The filtering semantics were complete; the projection was not.

These tests are mostly *negative*, and deliberately recursive: checking that the
top-level `id` key is gone would pass just as happily if a UUID were nested
inside `manufacturer` or `primary_image`. The assertion that matters is that no
database identifier appears anywhere in the serialized result, at any depth.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.services.agent_tools import canonical_robot_url, search_robots

# One gate, shared with the `get_robot` tests: a second, subtly weaker copy of a
# security assertion is worse than no second copy at all.
from tests.agent_identifier_gate import UUID_PATTERN, assert_no_database_identifier


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


def dumped(**kw) -> list[dict]:
    with SessionLocal() as s:
        res = search_robots(s, limit=100, **kw)
    return [item.model_dump(mode="json") for item in res.items]


@pytest.fixture
def probe_robot():
    """A published robot whose real row id we keep, to hunt for it in the output."""
    created: list = []

    def make(**cols) -> tuple[str, uuid.UUID]:
        mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
        slug = f"projection-probe-{uuid.uuid4().hex[:10]}"
        rid = _exec(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
            "VALUES (:s, :m, :n, TRUE) RETURNING id",
            s=slug, m=mfr_id, n=slug.upper(),
        ).scalar_one()
        created.append(rid)
        return slug, rid

    yield make
    for rid in created:
        _exec("DELETE FROM robot WHERE id = :i", i=rid)


# --------------------------------------------------------------------------
# canonical_url (docs/20 §5, §8)
# --------------------------------------------------------------------------


def test_every_item_carries_a_canonical_url(database_url):
    items = dumped()
    assert items, "seed required"
    for item in items:
        assert item["canonical_url"]


def test_canonical_url_is_the_slug_address(database_url):
    for item in dumped():
        assert item["canonical_url"] == f"/robots/{item['slug']}"


def test_canonical_url_helper_derives_from_the_slug_alone(database_url):
    assert canonical_robot_url("unitree-g1") == "/robots/unitree-g1"


def test_canonical_url_never_contains_a_database_identifier(
    database_url, probe_robot
):
    slug, rid = probe_robot()
    item = next(i for i in dumped() if i["slug"] == slug)
    assert str(rid) not in item["canonical_url"]
    assert not UUID_PATTERN.search(item["canonical_url"])


# --------------------------------------------------------------------------
# IDENTIFIER SAFETY — recursive, not top-level
# --------------------------------------------------------------------------


def test_no_item_exposes_an_id_field(database_url):
    for item in dumped():
        assert "id" not in item


def test_no_database_identifier_appears_at_any_depth(database_url):
    assert_no_database_identifier(dumped())


def test_the_actual_row_uuid_never_appears_anywhere(database_url, probe_robot):
    """The strongest form: take a real `robot.id` and prove it is absent."""
    slug, rid = probe_robot()
    items = dumped()
    item = next(i for i in items if i["slug"] == slug)
    assert str(rid) not in repr(item)
    assert str(rid) not in repr(items)


def test_manufacturer_is_exposed_by_slug_and_name_only(database_url):
    for item in dumped():
        assert set(item["manufacturer"]) == {"slug", "name"}
        assert item["manufacturer"]["slug"]
        assert item["manufacturer"]["name"]


def test_nested_objects_carry_no_identifiers(database_url):
    """`price_display` and `primary_image` are value objects, and must stay so."""
    for item in dumped():
        for nested in ("price_display", "primary_image"):
            value = item.get(nested)
            if value is not None:
                assert_no_database_identifier({nested: value})


def test_identifier_safety_holds_under_every_filter_shape(database_url):
    """A projection leak could hide behind a code path a plain query misses."""
    for query in (
        {},
        {"has_sdk": True},
        {"region": "US"},
        {"price_max": 250000, "price_currency": "USD"},
        {"price_max": 250000, "price_currency": "USD", "sort": "-price"},
        {"commercial_status": ["COMMERCIAL"]},
        {"sort": "newest"},
    ):
        assert_no_database_identifier(dumped(**query))


def test_the_safety_gate_would_actually_catch_a_leak() -> None:
    """Guards the guard: the recursive assertion must fail on a planted UUID."""
    planted = str(uuid.uuid4())
    with pytest.raises(AssertionError):
        assert_no_database_identifier([{"manufacturer": {"slug": planted}}])
    with pytest.raises(AssertionError):
        assert_no_database_identifier([{"nested": {"robot_id": "x"}}])


# --------------------------------------------------------------------------
# NOTHING ELSE MOVED
# --------------------------------------------------------------------------


def test_slug_and_name_are_unchanged(database_url):
    with SessionLocal() as s:
        items = search_robots(s, limit=100).items
        rows = dict(
            s.execute(
                text("SELECT slug, name FROM humanoid.robot WHERE is_published")
            ).all()
        )
    for item in items:
        assert rows[item.slug] == item.name


def test_unknown_fields_stay_null(database_url, probe_robot):
    slug, _ = probe_robot()  # payload/height/mobility all NULL
    item = next(i for i in dumped() if i["slug"] == slug)
    for field in ("payload_kg", "height_cm", "mobility"):
        assert field in item, "UNKNOWN must be null with the key PRESENT (§9.1)"
        assert item[field] is None
        assert item[field] is not False and item[field] != 0


def test_price_display_meaning_is_preserved(database_url):
    """The three price states stay distinct through the projection."""
    items = {i["slug"]: i for i in dumped()}
    if "unitree-g1" in items:
        assert items["unitree-g1"]["price_display"]["type"] == "PUBLIC"
        assert items["unitree-g1"]["price_display"]["amount"] == 16000
    if "digit" in items:
        assert items["digit"]["price_display"]["type"] == "QUOTE_ONLY"
        assert items["digit"]["price_display"]["amount"] is None
    if "optimus" in items:
        assert items["optimus"]["price_display"] is None


def test_primary_image_still_obeys_media01(database_url):
    """Only display-eligible images cross the boundary, unchanged in shape."""
    for item in dumped():
        image = item.get("primary_image")
        if image is not None:
            assert image["image_url"]
            assert isinstance(image["is_official"], bool)
            assert set(image) == {"image_url", "source_name", "is_official"}


def test_ratified_field_set_is_exactly_section_5(database_url):
    expected = {
        "slug", "name", "commercial_status", "canonical_url", "manufacturer",
        "payload_kg", "height_cm", "mobility", "price_display",
        "available_modes", "deployment_count", "primary_image", "updated_at",
    }
    for item in dumped():
        assert set(item) == expected


def test_result_set_order_and_total_are_unchanged(database_url):
    """The projection reshapes identity; it must not touch the query."""
    with SessionLocal() as s:
        res = search_robots(s, limit=100)
        expected = s.execute(
            text(
                "SELECT slug FROM humanoid.robot WHERE is_published "
                "ORDER BY name ASC, slug"
            )
        ).scalars().all()
    assert [i.slug for i in res.items] == list(expected)
    assert res.total == len(expected)


def test_pagination_and_warnings_are_unchanged(database_url):
    with SessionLocal() as s:
        page = search_robots(s, limit=2, offset=1)
        full = search_robots(s, limit=100)
        priced = search_robots(s, price_max=1, price_currency="EUR", limit=100)
    assert page.limit == 2 and page.offset == 1
    assert page.total == full.total
    assert [i.slug for i in page.items] == [i.slug for i in full.items[1:3]]
    assert priced.warnings, "price reason codes still reported"
    assert full.contract_version == "agent-tools/0.1"


# --------------------------------------------------------------------------
# THE HTTP SURFACE IS UNTOUCHED (Phase 6)
# --------------------------------------------------------------------------


def test_http_api_still_returns_its_own_schema_with_id(client, database_url):
    """`id` remains on the public HTTP schema — removing it would be a
    compatibility change, and the agent boundary is where it must disappear."""
    body = client.get("/api/robots", params={"limit": 5}).json()
    assert body["items"]
    for item in body["items"]:
        assert "id" in item
        assert UUID_PATTERN.fullmatch(item["id"])
        assert "canonical_url" not in item


def test_http_and_agent_still_agree_on_which_robots(client, database_url):
    http = {i["slug"] for i in client.get(
        "/api/robots", params={"limit": 100}
    ).json()["items"]}
    with SessionLocal() as s:
        agent = {i.slug for i in search_robots(s, limit=100).items}
    assert http == agent
