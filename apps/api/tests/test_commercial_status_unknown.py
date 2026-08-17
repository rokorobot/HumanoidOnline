"""UNKNOWN commercial maturity: an absent claim, not a claim of immaturity.

The catalogue could say a robot's maturity was ANNOUNCED, PILOT or COMMERCIAL
but had no way to say it did not know yet, so sparse profiles were written as
ANNOUNCED. That is a factual claim ("publicly revealed, no hardware shipping",
docs/03 §2) asserted without evidence — and G2 correctly failed the moment such
a profile was published.

The fix is to stop making the claim, NOT to relax G2. These tests pin both
halves, because either alone is a regression waiting to happen:

  * UNKNOWN asserts nothing, so a published UNKNOWN robot needs no
    COMMERCIAL_STATUS evidence row; and
  * every other status keeps its full G2 obligation — a published ANNOUNCED or
    COMMERCIAL robot without evidence must still fail.

Follows the injection convention of `test_truth_regressions.py`: fixtures are
created inside the test and removed afterwards.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db.session import engine

# `db/` is a script directory, not a package — loaded by path, matching
# test_catalogue_entries.py.
REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "catalogue_entries", REPO_ROOT / "db" / "catalogue_entries.py"
)
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)

# The G2 commercial-status gate, kept in one place so a test cannot silently
# drift from db/validate_catalogue.py::GAP_QUERIES["commercial_status"].
_G2_COMMERCIAL_STATUS_GAP = """
    SELECT count(*) FROM robot r
    WHERE r.is_published
      AND r.commercial_status <> 'UNKNOWN'
      AND NOT EXISTS (SELECT 1 FROM evidence_source e
                      WHERE e.subject_type='COMMERCIAL_STATUS' AND e.subject_id=r.id)
"""


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def robot_factory():
    """Create published robots with a chosen maturity and no evidence."""
    created: list = []

    def make(status: str, *, published: bool = True) -> str:
        mfr_id = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
        slug = _uniq(f"status-{status.lower()}")
        rid = _exec(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published, "
            "commercial_status) VALUES (:s, :m, :n, :p, CAST(:c AS commercial_status)) "
            "RETURNING id",
            s=slug, m=mfr_id, n=slug.upper(), p=published, c=status,
        ).scalar_one()
        created.append(rid)
        return slug

    yield make
    for rid in created:
        _exec("DELETE FROM robot WHERE id = :i", i=rid)


def _gap_count() -> int:
    return _exec(_G2_COMMERCIAL_STATUS_GAP).scalar_one()


# --------------------------------------------------------------------------
# 1/2 — authoring default, and the owner-approved published sparse profile
# --------------------------------------------------------------------------


def test_a_newly_authored_stub_is_unknown_and_unpublished():
    stub = ce.make_stub(slug="x-1", name="1", mfr_slug="x", official_url=None)
    assert stub["commercial_status"] == "UNKNOWN"
    assert stub["is_published"] is False


def test_a_published_sparse_robot_may_carry_unknown_maturity(robot_factory):
    slug = robot_factory("UNKNOWN")
    row = _exec(
        "SELECT is_published, commercial_status FROM robot WHERE slug = :s", s=slug
    ).one()
    assert row.is_published is True
    assert row.commercial_status == "UNKNOWN"


# --------------------------------------------------------------------------
# 3/4/5 — G2 distinguishes an absent claim from an unevidenced one
# --------------------------------------------------------------------------


def test_published_unknown_status_passes_g2_without_fabricated_evidence(
    robot_factory,
) -> None:
    before = _gap_count()
    robot_factory("UNKNOWN")
    assert _gap_count() == before, (
        "a published UNKNOWN-maturity robot must not require a COMMERCIAL_STATUS "
        "evidence row — it asserts no maturity to evidence"
    )


@pytest.mark.parametrize("status", ["ANNOUNCED", "COMMERCIAL"])
def test_published_asserted_status_still_fails_g2_without_evidence(
    robot_factory, status
) -> None:
    """The other half: UNKNOWN is an exemption for the absent claim only."""
    before = _gap_count()
    robot_factory(status)
    assert _gap_count() == before + 1, (
        f"a published {status} robot without evidence must still violate G2"
    )


def test_every_asserted_status_keeps_its_g2_obligation(robot_factory) -> None:
    """Pins the whole vocabulary, so a future value cannot quietly join the
    exemption by being added to the enum."""
    asserted = [
        "ANNOUNCED", "DEVELOPMENT", "PROTOTYPE", "PILOT", "EARLY_ACCESS",
        "LIMITED_COMMERCIAL", "COMMERCIAL", "RAAS_DEPLOYMENT", "DISCONTINUED",
    ]
    before = _gap_count()
    for status in asserted:
        robot_factory(status)
    assert _gap_count() == before + len(asserted)


# --------------------------------------------------------------------------
# 6 — UNKNOWN renders as UNKNOWN, never coerced
# --------------------------------------------------------------------------


def test_unknown_status_is_served_verbatim_never_coerced(client, robot_factory) -> None:
    slug = robot_factory("UNKNOWN")
    body = client.get(f"/api/robots/{slug}")
    assert body.status_code == 200
    detail = body.json()
    assert detail["commercial_status"] == "UNKNOWN"
    for wrong in ("ANNOUNCED", "NOT_AVAILABLE", "DISCONTINUED"):
        assert detail["commercial_status"] != wrong
    # Not silently emptied or falsified either.
    assert detail["commercial_status"] not in (None, "", False, 0)


# --------------------------------------------------------------------------
# 7/8 — the surrounding gates are untouched by the new status
# --------------------------------------------------------------------------


def test_unknown_status_does_not_bypass_publication_gating(
    client, robot_factory
) -> None:
    slug = robot_factory("UNKNOWN", published=False)
    assert client.get(f"/api/robots/{slug}").status_code == 404
    listing = client.get("/api/robots", params={"limit": 100}).json()
    assert slug not in {item["slug"] for item in listing["items"]}


def test_unknown_status_robots_are_still_canonical_not_candidates(
    client, robot_factory
) -> None:
    """A robot is canonical whatever its maturity; discovery candidates live in
    their own table and are excluded regardless (test_discovery_review.py)."""
    slug = robot_factory("UNKNOWN")
    listing = client.get("/api/robots", params={"limit": 100}).json()
    assert slug in {item["slug"] for item in listing["items"]}
