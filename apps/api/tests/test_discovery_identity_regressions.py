"""Regression tests for the EXISTING deterministic resolver (Stage C preflight).

These pin down current behaviour; none of them changes it. The first live
adapter reuses `resolve_identity` unchanged, so anything it relies on — or any
gap it must work around — is stated here as an executable fact:

- (source, external_ref) is idempotent, and URL spelling variants would break
  that unless the §11 normalizer is applied;
- variants ("G1" / "G1 EDU", "R1" / "R1 EDU U1..U6", "H2" / "H2 EDU") never
  match each other;
- the same normalized manufacturer + model on another candidate is
  POSSIBLE_DUPLICATE;
- a REJECTED candidate no longer takes part in duplicate detection (changed
  deliberately in Stage E; it was documented here as the earlier behaviour);
- a manufacturer spelled differently stays unmatched: there is no manufacturer
  alias mechanism, and a confirmed robot alias does not cross manufacturers.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery.adapters import FixtureAdapter, ingest
from app.services.discovery.identity import (
    _model_key,
    canonical_matches,
    load_confirmed_aliases,
    normalize,
    resolve_identity,
)
from app.services.discovery.urlref import normalize_url

CATALOGUE = Path(__file__).resolve().parents[3] / "db" / "catalogue"


# ------------------------------------------------ repository files (no DB) --


def _catalogue_rows() -> list[tuple[str, str, str, str]]:
    makers = {m["slug"]: m["name"] for m in json.loads(
        (CATALOGUE / "manufacturers.json").read_text(encoding="utf-8"))["manufacturers"]}
    rows = []
    for path in sorted((CATALOGUE / "robots").glob("*.json")):
        robot = json.loads(path.read_text(encoding="utf-8"))
        rows.append((robot["slug"], robot["slug"], robot["name"],
                     makers[robot["manufacturer_slug"]]))
    return rows


def _matches(manufacturer: str, name: str) -> list[str]:
    mfr_key = normalize(manufacturer)
    return canonical_matches(mfr_key, _model_key(name, mfr_key), _catalogue_rows(),
                             load_confirmed_aliases())


@pytest.mark.parametrize(("name", "expected"), [
    ("G1", ["unitree-g1"]),                     # confirmed alias of "G1 Basic"
    ("G1 Basic", ["unitree-g1"]),
    ("G1 EDU Plus (U2)", ["unitree-g1-edu-plus-u2"]),
    ("G1 EDU", []),                             # not "G1", not "G1 EDU Plus (U2)"
    ("R1", ["unitree-r1"]),
    ("R1 EDU", []),                             # never folds into R1 or any EDU tier
    *[(f"R1 EDU U{i}", [f"unitree-r1-edu-u{i}"]) for i in range(1, 7)],
    ("R1 EDU U7", []),
    ("H2", ["unitree-h2"]),
    ("H2 EDU", ["unitree-h2-edu"]),
    ("H1-2", []),                               # not H1
])
def test_variants_never_silently_match(name: str, expected: list[str]) -> None:
    assert _matches("Unitree Robotics", name) == expected


# ------------------------------------------------------------ PostgreSQL --


@pytest.fixture
def dsession(database_url):
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


def _source(session, **overrides) -> DiscoverySource:
    fields = dict(
        key=f"regress-{uuid.uuid4().hex[:10]}", name="Fixture source",
        source_class="MANUFACTURER", homepage_url="https://maker.example/",
        is_enabled=True, tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime(2026, 9, 1, tzinfo=UTC),
        eligibility_reviewed_by="fixture-reviewer",
    )
    fields.update(overrides)
    source = DiscoverySource(**fields)
    session.add(source)
    session.flush()
    return source


def _candidate(session, source, name, manufacturer, ref=None, **extra) -> DiscoveryCandidate:
    cand = DiscoveryCandidate(
        source_id=source.id, entity_type="ROBOT", candidate_name=name,
        candidate_manufacturer=manufacturer, external_ref=ref or uuid.uuid4().hex, **extra,
    )
    session.add(cand)
    session.flush()
    return cand


def _count(session, source) -> int:
    return session.scalar(select(func.count()).select_from(DiscoveryCandidate)
                          .where(DiscoveryCandidate.source_id == source.id))


def test_same_source_same_external_ref_is_idempotent(dsession) -> None:
    source = _source(dsession)
    record = {"external_ref": "https://maker.example/products/ex-1", "name": "EX-1",
              "manufacturer": f"Maker{uuid.uuid4().hex[:6]}"}
    first = ingest(dsession, source, FixtureAdapter(records=[record]))
    second = ingest(dsession, source, FixtureAdapter(records=[record]))
    assert len(first) == 1 and second == []
    assert _count(dsession, source) == 1


def test_unnormalized_url_variants_would_create_a_second_candidate(dsession) -> None:
    """Without §11 normalization one page becomes two candidates that then flag
    each other as POSSIBLE_DUPLICATE. The normalizer collapses the spellings."""
    maker = f"Maker{uuid.uuid4().hex[:6]}"
    raw = ["https://maker.example/products/ex-1",
           "https://maker.example/products/ex-1/?utm_source=newsletter"]
    records = [{"external_ref": r, "name": "EX-1", "manufacturer": maker} for r in raw]

    unnormalized = _source(dsession)
    created = ingest(dsession, unnormalized, FixtureAdapter(records=records))
    assert len(created) == 2
    assert resolve_identity(dsession, created[1], aliases={}) == "POSSIBLE_DUPLICATE"

    normalized = _source(dsession)
    for record in records:
        ingest(dsession, normalized, FixtureAdapter(records=[
            {**record, "external_ref": normalize_url(record["external_ref"])}]))
    assert _count(dsession, normalized) == 1


def test_other_candidate_with_same_normalized_identity_is_possible_duplicate(dsession) -> None:
    maker = f"Maker{uuid.uuid4().hex[:6]}"
    bootstrap = _source(dsession, source_class="OTHER", is_enabled=False)
    official = _source(dsession)
    _candidate(dsession, bootstrap, "EX 9", f"{maker} Robotics")
    cand = _candidate(dsession, official, "ex-9", maker)  # punctuation/case/generic tokens
    assert resolve_identity(dsession, cand, aliases={}) == "POSSIBLE_DUPLICATE"
    assert cand.possible_robot_id is None


def test_rejected_candidate_no_longer_causes_duplicate_detection(dsession) -> None:
    """CHANGED DELIBERATELY in Stage E (docs/16 §17.1). Until then a REJECTED
    candidate still made others POSSIBLE_DUPLICATE (documented in the Stage C
    preflight). A rejection is terminal, so it now stops causing duplicate
    review, while an open candidate with the same identity still does."""
    maker = f"Maker{uuid.uuid4().hex[:6]}"
    old = _candidate(dsession, _source(dsession), "EX-4", maker, status="REJECTED")
    assert old.status == "REJECTED"
    cand = _candidate(dsession, _source(dsession), "EX-4", maker)
    assert resolve_identity(dsession, cand, aliases={}) == "NEW_ENTITY"
    _candidate(dsession, _source(dsession), "EX-4", maker)   # an open one still counts
    assert resolve_identity(dsession, cand, aliases={}) == "POSSIBLE_DUPLICATE"


def test_manufacturer_spelling_difference_stays_unmatched(dsession) -> None:
    tag = uuid.uuid4().hex[:6]
    mfr = Manufacturer(slug=f"fourier-{tag}", name=f"Fourier{tag} Intelligence")
    dsession.add(mfr)
    dsession.flush()
    robot = Robot(slug=f"gr-{tag}", manufacturer_id=mfr.id, name="GR-1", is_published=True)
    dsession.add(robot)
    dsession.flush()
    source = _source(dsession)

    short = _candidate(dsession, source, "GR-1", f"Fourier{tag}")
    assert resolve_identity(dsession, short, aliases={}) == "NEW_ENTITY"
    assert short.possible_manufacturer_id is None
    # A confirmed ROBOT alias does not reach across a manufacturer mismatch.
    assert resolve_identity(dsession, short, aliases={robot.slug: ("GR-1",)}) == "NEW_ENTITY"

    # Generic corporate tokens are the only spelling difference normalization absorbs.
    generic = _candidate(dsession, source, "GR-1", f"Fourier{tag} Intelligence Robotics Inc.")
    assert resolve_identity(dsession, generic, aliases={}) == "MATCHED_EXISTING"
    assert generic.possible_robot_id == robot.id
