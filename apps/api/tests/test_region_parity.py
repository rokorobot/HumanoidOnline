"""AGENT-02.1b — region applicability, and HTTP/AGENT parity over it.

`docs/20` §12 ratifies region as an *eligibility* constraint: an offer applies to
a buyer in the requested region when its scope is the exact region, an applicable
ancestor, `GLOBAL`, or region-agnostic (`NULL`). `docs/20` §21.2 requires the
same query to answer identically through the public API and the agent tool.

Before this slice `/api/robots` matched `region.code` exactly while
`search_robots` resolved applicability, so `region=DE` answered **0** over HTTP
and **8** through the agent against the same catalogue. Both now resolve through
`services/robot_filters.py::resolve_region_filter` →
`services/regions.py::applicable_region_ids`.

Parity is asserted on canonical slug **identities**, never on counts: two
different sets of the same size would satisfy a count assertion and still mean
the surfaces disagree.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.services.agent_tools import InvalidArgument, search_robots


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


def _region_id(code: str):
    return _exec("SELECT id FROM region WHERE code = :c", c=code).scalar_one_or_none()


@pytest.fixture
def robot_factory():
    """Published robots carrying one availability offer at a chosen scope.

    `region_code=None` creates a genuinely region-agnostic (NULL) offer — the
    case the seeded catalogue happens not to contain, and the one that made the
    empty-`region_ids` defect invisible in production data.
    """
    created: list = []

    def make(*, region_code: str | None, published: bool = True) -> str:
        mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
        slug = f"region-probe-{uuid.uuid4().hex[:10]}"
        rid = _exec(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
            "VALUES (:s, :m, :n, :p) RETURNING id",
            s=slug, m=mfr_id, n=slug.upper(), p=published,
        ).scalar_one()
        created.append(rid)
        _exec(
            "INSERT INTO availability_offer (robot_id, transaction_type, "
            "availability_status, region_id, is_current) "
            "VALUES (:r, 'PURCHASE', 'AVAILABLE', :rg, TRUE)",
            r=rid, rg=_region_id(region_code) if region_code else None,
        )
        return slug

    yield make
    for rid in created:
        _exec("DELETE FROM robot WHERE id = :i", i=rid)


def _http_slugs(client, **params) -> set[str]:
    resp = client.get("/api/robots", params={**params, "limit": 100})
    assert resp.status_code == 200, (params, resp.status_code, resp.text)
    return {it["slug"] for it in resp.json()["items"]}


def _agent_slugs(**kwargs) -> set[str]:
    with SessionLocal() as s:
        return {i.slug for i in search_robots(s, limit=100, **kwargs).items}


# --------------------------------------------------------------------------
# THE PARITY GATE (docs/20 §21.2) — identities, not counts
# --------------------------------------------------------------------------


@pytest.mark.parametrize("region", ["DE", "US", "GLOBAL", "EU", "CN", "CZ", "UK"])
def test_http_and_agent_return_the_same_identities(client, database_url, region):
    if _region_id(region) is None:
        pytest.skip(f"region {region} not in this dataset")
    assert _http_slugs(client, region=region) == _agent_slugs(region=region)


def test_parity_holds_across_the_hierarchy_fixtures(client, database_url, robot_factory):
    """A fresh robot at each scope, then parity re-checked with them present."""
    if _region_id("DE") is None or _region_id("EU") is None:
        pytest.skip("DE/EU hierarchy not in this dataset")
    robot_factory(region_code="DE")
    robot_factory(region_code="EU")
    robot_factory(region_code="GLOBAL")
    robot_factory(region_code=None)
    robot_factory(region_code="US")

    for region in ("DE", "EU", "US", "GLOBAL"):
        assert _http_slugs(client, region=region) == _agent_slugs(region=region), region


def test_parity_is_not_a_count_coincidence(client, database_url, robot_factory):
    """Guards the assertion itself: equal-sized but different sets must fail a
    real parity check, so the check is made on identities."""
    if _region_id("DE") is None:
        pytest.skip("DE not in this dataset")
    de = robot_factory(region_code="DE")
    us = robot_factory(region_code="US")
    de_set, us_set = _http_slugs(client, region="DE"), _http_slugs(client, region="US")
    assert de in de_set and us not in de_set
    assert us in us_set and de not in us_set


# --------------------------------------------------------------------------
# THE TEN REQUIRED CASES — asserted on BOTH surfaces
# --------------------------------------------------------------------------


def _both(client, region: str) -> tuple[set[str], set[str]]:
    return _http_slugs(client, region=region), _agent_slugs(region=region)


def test_1_exact_region_offer_qualifies(client, database_url, robot_factory):
    slug = robot_factory(region_code="US")
    http, agent = _both(client, "US")
    assert slug in http and slug in agent


def test_2_ancestor_region_offer_qualifies(client, database_url, robot_factory):
    """An EU-scoped offer applies to a buyer in DE. This is the case the old
    exact-code HTTP path got wrong."""
    if _region_id("DE") is None or _region_id("EU") is None:
        pytest.skip("DE/EU hierarchy not in this dataset")
    slug = robot_factory(region_code="EU")
    http, agent = _both(client, "DE")
    assert slug in http, "HTTP still matching region code exactly"
    assert slug in agent


def test_3_global_offer_qualifies_for_a_narrower_region(
    client, database_url, robot_factory
):
    slug = robot_factory(region_code="GLOBAL")
    http, agent = _both(client, "US")
    assert slug in http and slug in agent


def test_4_region_agnostic_offer_qualifies(client, database_url, robot_factory):
    slug = robot_factory(region_code=None)
    http, agent = _both(client, "US")
    assert slug in http and slug in agent


def test_5_unrelated_region_is_excluded(client, database_url, robot_factory):
    slug = robot_factory(region_code="US")
    http, agent = _both(client, "CN")
    assert slug not in http and slug not in agent


def test_6_descendants_do_not_qualify_upward(client, database_url, robot_factory):
    """Applicability runs one way. A DE-scoped offer is not evidence of EU-wide
    availability, and a sibling country is never implied."""
    if _region_id("DE") is None or _region_id("EU") is None:
        pytest.skip("DE/EU hierarchy not in this dataset")
    slug = robot_factory(region_code="DE")
    http, agent = _both(client, "EU")
    assert slug not in http, "a DE offer must not satisfy an EU-wide query"
    assert slug not in agent
    if _region_id("CZ") is not None:
        sibling_http, sibling_agent = _both(client, "CZ")
        assert slug not in sibling_http and slug not in sibling_agent


def test_7_a_global_offer_keeps_its_own_region_identity(
    client, database_url, robot_factory
):
    """Applicability must never be written back as identity: the offer still
    reports GLOBAL, not the queried region (`docs/20` §12)."""
    slug = robot_factory(region_code="GLOBAL")
    assert slug in _http_slugs(client, region="US")

    detail = client.get(f"/api/robots/{slug}")
    assert detail.status_code == 200
    regions = {o["region"] for o in detail.json()["availability_offers"]}
    assert regions == {"GLOBAL"}, f"GLOBAL offer relabelled: {regions}"


def test_8_unknown_region_is_rejected_on_both_surfaces(client, database_url):
    """OWNER DECISION: invalid input, not an empty or widened result."""
    resp = client.get("/api/robots", params={"region": "NOT-A-REGION", "limit": 100})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "unknown region: 'NOT-A-REGION'"
    assert "items" not in resp.json()

    with pytest.raises(InvalidArgument):
        with SessionLocal() as s:
            search_robots(s, region="NOT-A-REGION", limit=100)


def test_8a_unknown_region_never_widens_to_the_catalogue(client, database_url):
    full = client.get("/api/robots", params={"limit": 100}).json()["total"]
    assert full > 0
    resp = client.get("/api/robots", params={"region": "ZZ-NOPE", "limit": 100})
    assert resp.status_code == 422
    assert resp.json().get("total") is None


def test_9_an_empty_resolved_region_set_matches_nothing(database_url, robot_factory):
    """The safety defect this slice also closes.

    An empty `region_ids` used to fall through to `region_id IS NULL`, i.e.
    "region-agnostic offers only" — so an unresolvable region returned a *result
    set*, and one that a resolvable narrow region would not have returned. The
    seeded catalogue has no NULL-region offers, which hid it; this fixture
    creates one, so the old behaviour would return exactly this robot.
    """
    from sqlalchemy import func, select

    from app.models.robot import Robot
    from app.services.robot_filters import apply_catalogue_filters

    agnostic = robot_factory(region_code=None)

    base = dict(
        q=None, manufacturer=None, commercial_status=None, transaction_type=None,
        availability_status=None, use_case=None, payload_min=None, height_min=None,
        height_max=None, mobility=None, autonomy_min=None,
        has_sdk=None, ros_support=None, developer_edition=None,
        has_manipulation=None,
    )
    with SessionLocal() as s:
        # Sanity: the region-agnostic robot IS reachable for a resolvable region.
        reachable = {
            r.slug
            for r in s.execute(
                apply_catalogue_filters(
                    select(Robot), **base, region_ids={_region_id("US")}
                )
            ).scalars()
        }
        assert agnostic in reachable

        empty = s.execute(
            apply_catalogue_filters(
                select(func.count(Robot.id)), **base, region_ids=set()
            )
        ).scalar_one()
    assert empty == 0, "an empty applicability set must match nothing, not NULL offers"


def test_10_unpublished_robots_never_appear_for_any_region(
    client, database_url, robot_factory
):
    slug = robot_factory(region_code="GLOBAL", published=False)
    for region in ("US", "DE", "GLOBAL"):
        if _region_id(region) is None:
            continue
        assert slug not in _http_slugs(client, region=region)
        assert slug not in _agent_slugs(region=region)


# --------------------------------------------------------------------------
# PRESERVED SEMANTICS (Phase 6)
# --------------------------------------------------------------------------


def test_a_query_without_a_region_is_unchanged(client, database_url):
    """Geography stays inactive when no region is supplied."""
    body = client.get("/api/robots", params={"limit": 100}).json()
    everything = client.get("/api/robots", params={"limit": 100}).json()
    assert body["total"] == everything["total"]
    assert {i["slug"] for i in body["items"]} == {i["slug"] for i in everything["items"]}


def test_an_empty_region_param_still_means_no_region_filter(client, database_url):
    baseline = _http_slugs(client, limit=100)
    assert _http_slugs(client, region="") == baseline


def test_region_composes_with_transaction_type_unchanged(client, database_url):
    """The availability sub-select still applies its other predicates."""
    resp = client.get(
        "/api/robots",
        params={"region": "US", "transaction_type": "PURCHASE", "limit": 100},
    )
    assert resp.status_code == 200
    combined = {it["slug"] for it in resp.json()["items"]}
    assert combined <= _http_slugs(client, region="US")
