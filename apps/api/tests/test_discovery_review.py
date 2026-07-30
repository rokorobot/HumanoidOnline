"""Operator review surface — read-only, noncanonical, non-public.

The endpoint exists so a human can look at the discovery queue. These tests hold
three lines: it returns candidates and nothing canonical, it writes nothing, and
it does not exist in production.

The failure they guard against is not a crash. It is a NONCANONICAL candidate
leaking into a place where something treats it as a verified robot — via the
public API, via the catalogue counts, or via a field that reads like a product
fact.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.schemas.discovery_review import DiscoveryCandidateReview

ROUTE = "/api/discovery-review"

#: Exactly the fields §  the review projection may carry. A new key appearing here
#: without a deliberate decision is how a spec or a price would eventually arrive.
APPROVED_FIELDS = {
    "id",
    "candidate_name",
    "candidate_manufacturer",
    "external_ref",
    "discovery_url",
    "official_url",
    "source_name",
    "source_class",
    "status",
    "identity_status",
    "trace_state",
    "discovered_at",
    "last_seen_at",
}

#: Anything that would make a candidate read as a product. None of these may ever
#: appear in the projection, however convenient it would be for the UI.
FORBIDDEN_FIELDS = {
    "height_cm", "payload_kg", "price", "price_amount", "pricing", "specs",
    "specifications", "commercial_status", "availability", "availability_status",
    "maturity", "images", "image_url", "hero_image_url", "claims", "is_published",
    "verified_at", "confidence",
}

CANONICAL_TABLES = (
    "robot", "manufacturer", "pricing_offer", "availability_offer", "deployment",
    "specification", "robot_image", "evidence_source",
)


@pytest.fixture
def dsession(database_url) -> Session:
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        conn.close()


@pytest.fixture
def seeded_candidates(database_url):
    """COMMITTED candidates, because the API runs on its own connection.

    Teardown removes the candidates before the source: `candidate_claim`
    .discovery_source_id is RESTRICT since Slice A, and the fixture must not rely
    on provenance being nullable.
    """
    tag = uuid.uuid4().hex[:8]
    with Session(engine) as s:
        source = DiscoverySource(
            key=f"review-fixture-{tag}",
            name="Review Fixture Source",
            source_class="AGGREGATOR",
            tos_status="ALLOWED",
            robots_status="NOT_APPLICABLE",
            eligibility_reviewed_by="tester",
            eligibility_reviewed_at=func.now(),
            is_enabled=True,
        )
        s.add(source)
        s.flush()
        for index, (name, maker, official) in enumerate([
            ("Probe One", "Probe Robotics", "https://probe.invalid/one"),
            ("Probe Two", "Probe Robotics", None),          # no lead: must stay null
            ("Probe Three", "Another Maker", "https://another.invalid/three"),
        ]):
            s.add(DiscoveryCandidate(
                source_id=source.id,
                external_ref=f"{tag}/robot-{index}",
                candidate_name=name,
                candidate_manufacturer=maker,
                discovery_url="https://probe.invalid/",
                candidate_data={"official_url": official} if official else None,
            ))
        s.commit()
        ids = {"source": source.id, "tag": tag}
    try:
        yield ids
    finally:
        with Session(engine) as s:
            s.execute(text(
                "DELETE FROM humanoid.discovery_candidate WHERE source_id = :sid"
            ), {"sid": ids["source"]})
            s.execute(text(
                "DELETE FROM humanoid.discovery_source WHERE id = :sid"
            ), {"sid": ids["source"]})
            s.commit()


def _counts(session: Session) -> dict[str, int]:
    return {
        table: session.execute(
            text(f"SELECT count(*) FROM humanoid.{table}")  # noqa: S608 - fixed allowlist
        ).scalar_one()
        for table in CANONICAL_TABLES
    }


# --------------------------------------------------------------------------- #
# 1 — it returns discovery candidates
# --------------------------------------------------------------------------- #
def test_the_endpoint_returns_discovery_candidates(client, seeded_candidates) -> None:
    body = client.get(ROUTE, params={"limit": 100}).json()
    refs = {item["external_ref"] for item in body["items"]}
    tag = seeded_candidates["tag"]
    assert {f"{tag}/robot-0", f"{tag}/robot-1", f"{tag}/robot-2"} <= refs
    assert body["total"] >= 3


def test_source_provenance_is_carried_on_every_row(client, seeded_candidates) -> None:
    """A candidate without its source is an anonymous assertion. The reviewer's
    first question is "who says so", so the answer travels with the row."""
    items = client.get(ROUTE, params={"limit": 100}).json()["items"]
    mine = [i for i in items if i["external_ref"].startswith(seeded_candidates["tag"])]
    assert mine
    for item in mine:
        assert item["source_name"] == "Review Fixture Source"
        assert item["source_class"] == "AGGREGATOR"


# --------------------------------------------------------------------------- #
# 2 — canonical robots are NOT served as candidates
# --------------------------------------------------------------------------- #
def test_canonical_robots_are_not_returned_as_discovery_candidates(
    client, seeded_candidates, dsession
) -> None:
    """The two populations must not be mixed. A canonical robot appearing in the
    review queue would invite a reviewer to "promote" something already published,
    and a candidate appearing in the catalogue is the failure the contract exists
    to prevent."""
    canonical_names = set(dsession.execute(select(Robot.name)).scalars().all())
    assert canonical_names, "expected a seeded catalogue to compare against"

    items = client.get(ROUTE, params={"limit": 100}).json()["items"]
    candidate_refs = {item["external_ref"] for item in items}
    canonical_ids = {str(rid) for rid in dsession.execute(select(Robot.id)).scalars().all()}

    for item in items:
        assert item["id"] not in canonical_ids, "a canonical robot id surfaced as a candidate"
    # Every returned row really is a discovery_candidate row.
    stored_refs = set(
        dsession.execute(select(DiscoveryCandidate.external_ref)).scalars().all()
    )
    assert candidate_refs <= stored_refs


# --------------------------------------------------------------------------- #
# 3 — the bootstrap batch is visible
# --------------------------------------------------------------------------- #
def test_the_bootstrap_dataset_is_visible_when_loaded(client, database_url) -> None:
    """The whole point of the surface: after MANUAL_BOOTSTRAP the queue is
    reviewable. Counted against the dataset itself so the assertion tracks the
    seed rather than a number copied into a test."""
    from app.services.discovery.bootstrap import bootstrap, load_dataset

    records = load_dataset("humanoid_radar_v1")
    with Session(engine) as s:
        source, _ = bootstrap(s, dataset="humanoid_radar_v1", operator="tester")
        s.commit()
        source_id = source.id
    try:
        body = client.get(ROUTE, params={"limit": 100}).json()
        returned = {
            item["external_ref"] for item in body["items"]
        }
        expected = {r["external_ref"] for r in records}
        assert expected <= returned, sorted(expected - returned)[:5]

        makers = {
            item["candidate_manufacturer"] for item in body["items"]
            if item["external_ref"] in expected
        }
        assert len(makers) >= 25, f"expected the full manufacturer spread, got {len(makers)}"
    finally:
        with Session(engine) as s:
            s.execute(text(
                "DELETE FROM humanoid.discovery_candidate WHERE source_id = :sid"
            ), {"sid": source_id})
            s.execute(text(
                "DELETE FROM humanoid.discovery_source WHERE id = :sid"
            ), {"sid": source_id})
            s.commit()


# --------------------------------------------------------------------------- #
# 4 — only the approved fields
# --------------------------------------------------------------------------- #
def test_the_response_exposes_only_the_approved_fields(client, seeded_candidates) -> None:
    items = client.get(ROUTE, params={"limit": 100}).json()["items"]
    assert items
    for item in items:
        assert set(item) == APPROVED_FIELDS, set(item) ^ APPROVED_FIELDS


def test_no_product_fact_field_is_exposed(client, seeded_candidates) -> None:
    """Not just "the current fields are fine" — the fields that must never appear
    are named, so adding one is a test failure rather than a judgement call."""
    body = client.get(ROUTE, params={"limit": 100}).text
    items = client.get(ROUTE, params={"limit": 100}).json()["items"]
    for item in items:
        for forbidden in FORBIDDEN_FIELDS:
            assert forbidden not in item, forbidden
    assert "hero_image_url" not in body


def test_the_schema_itself_declares_only_the_approved_fields() -> None:
    assert set(DiscoveryCandidateReview.model_fields) == APPROVED_FIELDS


def test_a_candidate_without_a_lead_reports_null_not_a_placeholder(
    client, seeded_candidates
) -> None:
    """UNKNOWN stays UNKNOWN (AGENTS.md rule 6). A candidate with nothing to trace
    yet must say so, not carry an empty string that renders as a broken link."""
    items = client.get(ROUTE, params={"limit": 100}).json()["items"]
    two = next(i for i in items if i["external_ref"].endswith("/robot-1"))
    assert two["official_url"] is None


# --------------------------------------------------------------------------- #
# 5 + 6 — it writes nothing
# --------------------------------------------------------------------------- #
def test_the_endpoint_performs_no_database_writes(
    client, seeded_candidates, dsession
) -> None:
    """Counted across the discovery layer as well as canonical: a read surface
    that quietly touched `last_seen_at` would be rewriting the audit trail of when
    a candidate was actually observed."""
    before_candidates = dsession.execute(
        select(func.count()).select_from(DiscoveryCandidate)
    ).scalar_one()
    before_seen = dict(dsession.execute(
        select(DiscoveryCandidate.external_ref, DiscoveryCandidate.last_seen_at)
    ).all())

    client.get(ROUTE, params={"limit": 100})
    client.get(ROUTE, params={"limit": 100})

    dsession.expire_all()
    after_candidates = dsession.execute(
        select(func.count()).select_from(DiscoveryCandidate)
    ).scalar_one()
    after_seen = dict(dsession.execute(
        select(DiscoveryCandidate.external_ref, DiscoveryCandidate.last_seen_at)
    ).all())

    assert after_candidates == before_candidates
    assert after_seen == before_seen, "a read must not refresh last_seen_at"


def test_calling_the_endpoint_changes_no_canonical_count(
    client, seeded_candidates, dsession
) -> None:
    before = _counts(dsession)
    client.get(ROUTE, params={"limit": 100})
    dsession.expire_all()
    assert _counts(dsession) == before


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_the_surface_has_no_write_verbs(client, method: str) -> None:
    """No mutation path exists, and none takes a candidate id. State changes stay
    in the governed CLI where they are attributed to a named human.

    Issued through `request` rather than the verb helpers because `delete()`
    accepts no body — and a DELETE with no body is exactly what must be refused.
    """
    response = client.request(method, ROUTE)
    assert response.status_code in (404, 405), response.status_code


# --------------------------------------------------------------------------- #
# 7 — status values are the queue's, not a product's
# --------------------------------------------------------------------------- #
def test_bootstrapped_candidates_report_the_untraced_queue_state(
    client, seeded_candidates
) -> None:
    items = client.get(ROUTE, params={"limit": 100}).json()["items"]
    mine = [i for i in items if i["external_ref"].startswith(seeded_candidates["tag"])]
    assert mine
    for item in mine:
        assert item["status"] == "DISCOVERED"
        assert item["identity_status"] == "UNRESOLVED"
        assert item["trace_state"] == "NOT_TRACED"


# --------------------------------------------------------------------------- #
# 8 — bounded, paginated
# --------------------------------------------------------------------------- #
def test_the_limit_is_capped_rather_than_unbounded(client, seeded_candidates) -> None:
    body = client.get(ROUTE, params={"limit": 10_000}).json()
    assert body["limit"] == 100, "an unbounded review query is a denial-of-service"


def test_pagination_walks_the_queue_without_overlap(client, seeded_candidates) -> None:
    first = client.get(ROUTE, params={"limit": 2, "offset": 0}).json()
    second = client.get(ROUTE, params={"limit": 2, "offset": 2}).json()
    assert first["limit"] == 2 and first["offset"] == 0
    assert second["offset"] == 2
    assert len(first["items"]) <= 2
    ids = {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}
    assert ids == set(), "pages must not overlap"
    assert first["total"] == second["total"]


@pytest.mark.parametrize(("limit", "expected"), [(0, 1), (-5, 1), (101, 100)])
def test_out_of_range_limits_are_clamped(client, limit: int, expected: int) -> None:
    assert client.get(ROUTE, params={"limit": limit}).json()["limit"] == expected


def test_a_negative_offset_is_clamped(client) -> None:
    assert client.get(ROUTE, params={"offset": -10}).json()["offset"] == 0


# --------------------------------------------------------------------------- #
# 9 — an empty queue is a valid response
# --------------------------------------------------------------------------- #
def test_an_empty_queue_returns_a_valid_empty_page(client, database_url) -> None:
    """The seeded database has no candidates of its own, so this is the real
    default state: a well-formed empty page, not a 404 and not an error."""
    body = client.get(ROUTE, params={"limit": 100}).json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["limit"] == 100
    assert body["offset"] == 0


# --------------------------------------------------------------------------- #
# 10 — the canonical catalogue is untouched
# --------------------------------------------------------------------------- #
def test_the_canonical_robot_api_is_unchanged(client, seeded_candidates) -> None:
    """The catalogue must not notice that the review surface exists."""
    before = client.get("/api/robots", params={"limit": 100}).json()
    client.get(ROUTE, params={"limit": 100})
    after = client.get("/api/robots", params={"limit": 100}).json()
    assert after == before

    candidate_names = {"Probe One", "Probe Two", "Probe Three"}
    listed = {item["name"] for item in after["items"]}
    assert candidate_names & listed == set(), "a candidate reached /api/robots"


def test_candidates_do_not_reach_the_market_snapshot(client, seeded_candidates) -> None:
    """Snapshot counts drive the public homepage. A candidate counted there would
    make the site advertise robots it has not verified."""
    snapshot = client.get("/api/market-snapshot").json()
    with Session(engine) as s:
        published = s.execute(
            select(func.count(Robot.id)).where(Robot.is_published.is_(True))
        ).scalar_one()
    assert snapshot["total_tracked"] == published


def test_candidate_manufacturers_do_not_reach_the_manufacturer_api(
    client, seeded_candidates, dsession
) -> None:
    listed = {m["name"] for m in client.get(
        "/api/manufacturers", params={"limit": 100}
    ).json()["items"]}
    assert "Probe Robotics" not in listed
    assert dsession.execute(
        select(func.count(Manufacturer.id)).where(Manufacturer.name == "Probe Robotics")
    ).scalar_one() == 0


# --------------------------------------------------------------------------- #
# Fail-closed: the surface does not exist in production
# --------------------------------------------------------------------------- #
def test_the_router_is_not_mounted_in_a_strict_environment(monkeypatch) -> None:
    """The important half of the design. Not "hidden behind a flag" — absent.

    Rebuilds the app with APP_ENV=production and asserts the route does not exist,
    which is what makes DATA-D1 §22 hold by construction rather than by anyone
    remembering to disable something.

    Checked through the OpenAPI schema and a live request, NOT by walking
    `app.routes`: that list mixes route objects with mounted sub-routers, and
    filtering it on `getattr(route, "path")` silently drops every router-mounted
    path — which made an earlier version of this assertion pass while proving
    nothing at all. The `/api/robots` check below exists to keep it honest: if the
    probe cannot see a route that IS mounted, it cannot be trusted about one that
    is not.
    """
    import importlib

    from fastapi.testclient import TestClient

    from app.config import get_settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://humanoid:humanoid@localhost:5432/none"
    )
    get_settings.cache_clear()
    try:
        import app.main as main_module

        strict_app = importlib.reload(main_module).app
        paths = set(strict_app.openapi()["paths"])

        assert not any(p.startswith("/api/discovery-review") for p in paths), paths
        # Non-vacuity: the probe must be able to see a route that IS mounted.
        assert "/api/robots" in paths

        # And it is genuinely unroutable, not merely undocumented. 404 arrives
        # before any database work, so the unreachable DATABASE_URL is irrelevant.
        with TestClient(strict_app) as strict_client:
            assert strict_client.get(ROUTE).status_code == 404
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        import app.main as main_module

        importlib.reload(main_module)


def test_the_surface_is_mounted_in_development(client) -> None:
    assert client.get(ROUTE).status_code == 200


def test_the_router_documents_why_it_is_not_public() -> None:
    """A reviewer reading this file must find the reason, not just the behaviour —
    the next person tempted to "just expose it publicly" is the audience."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1]
              / "app" / "routers" / "discovery_review.py").read_text(encoding="utf-8")
    assert "Gate I" in source
    assert "AGENT-01.7" in source
    assert "is_relaxed" in source


def test_the_review_route_is_separate_from_the_catalogue_route() -> None:
    from app.routers import robots as robots_router

    assert ROUTE != robots_router.router.prefix
    assert not ROUTE.startswith(robots_router.router.prefix)
