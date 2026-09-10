"""Confirmed identity aliases (DATA-D1.7 "known aliases"; docs/16 §11).

The radar seed names robots the way the market does ("G1", "Atlas"); the
catalogue names them the way the product owner scoped them ("G1 Basic", "Atlas
(Electric)"). Exact-name resolution alone then reports an already-catalogued,
already-published robot as NEW_ENTITY — a promotable verdict that invites a
duplicate canonical record. The fix is a human-confirmed alias register, still
matched by EXACT normalized equality. These tests hold both halves: the radar
entries resolve to the robots they are, and matching did not become fuzzy.

Repository files only, except the last test, which proves the database wiring.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery.bootstrap import load_dataset
from app.services.discovery.identity import (
    ALIASES_PATH,
    _model_key,
    canonical_matches,
    load_confirmed_aliases,
    normalize,
    resolve_identity,
)

CATALOGUE = Path(__file__).resolve().parents[3] / "db" / "catalogue"
DATASET = "humanoid_radar_v1"

#: Radar entries pinned to a slug: the two that resolve only through a confirmed
#: alias, and the one whose model name is shared with another maker.
PINNED = {
    ("Unitree Robotics", "G1"): "unitree-g1",                       # record is "G1 Basic"
    ("Boston Dynamics", "Atlas"): "boston-dynamics-atlas-electric",  # record is "Atlas (Electric)"
    ("Galbot", "G1"): "galbot-g1",                                  # must never cross makers
}


def _catalogue_rows() -> list[tuple[str, str, str, str]]:
    """`(key, slug, name, manufacturer_name)` for every catalogued robot."""
    mfr_doc = json.loads((CATALOGUE / "manufacturers.json").read_text(encoding="utf-8"))
    makers = {m["slug"]: m["name"] for m in mfr_doc["manufacturers"]}
    rows = []
    for path in sorted((CATALOGUE / "robots").glob("*.json")):
        robot = json.loads(path.read_text(encoding="utf-8"))
        rows.append((robot["slug"], robot["slug"], robot["name"],
                     makers[robot["manufacturer_slug"]]))
    return rows


def _resolve(record: dict, rows, aliases) -> list[str]:
    mfr_key = normalize(record["manufacturer"])
    return canonical_matches(mfr_key, _model_key(record["name"], mfr_key), rows, aliases)


def _register_entries() -> list[dict]:
    return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))["aliases"]


# --------------------------------------------------------------------------- #
# The shipped radar against the shipped catalogue
# --------------------------------------------------------------------------- #
def test_no_catalogued_radar_v1_entry_regresses_to_new_entity() -> None:
    """The invariant: a radar candidate for a robot that is already catalogued
    must never resolve NEW_ENTITY. The frozen v1 radar is entirely catalogued
    (the catalogue's stubs were authored from it), so for v1 that means every
    entry resolves to exactly one robot — MATCHED_EXISTING.

    Scoped to v1 on purpose. A genuinely new robot in a FUTURE radar dataset
    should resolve NEW_ENTITY; this is not a law that every radar entry matches.
    A catalogue slice that renames a robot and breaks this fails here; the fix is
    a confirmed alias, not a reverted name."""
    rows, aliases = _catalogue_rows(), load_confirmed_aliases()
    unresolved = {
        f"{r['manufacturer']} / {r['name']}": _resolve(r, rows, aliases)
        for r in load_dataset(DATASET)
        if len(_resolve(r, rows, aliases)) != 1
    }
    assert not unresolved, f"not resolving to exactly one catalogued robot: {unresolved}"


def test_the_renamed_and_shared_name_entries_resolve_to_the_right_robot() -> None:
    rows, aliases = _catalogue_rows(), load_confirmed_aliases()
    by_identity = {(r["manufacturer"], r["name"]): r for r in load_dataset(DATASET)}
    for identity, slug in PINNED.items():
        assert _resolve(by_identity[identity], rows, aliases) == [slug], identity


def test_no_two_radar_entries_resolve_to_the_same_robot() -> None:
    rows, aliases = _catalogue_rows(), load_confirmed_aliases()
    seen: dict[str, str] = {}
    for record in load_dataset(DATASET):
        for slug in _resolve(record, rows, aliases):
            assert slug not in seen, f"{record['name']!r} and {seen[slug]!r} both reach {slug}"
            seen[slug] = record["name"]


# --------------------------------------------------------------------------- #
# The register itself
# --------------------------------------------------------------------------- #
def test_the_register_is_well_formed_and_names_only_catalogued_robots() -> None:
    load_confirmed_aliases()  # raises on a malformed register
    slugs = {row[0] for row in _catalogue_rows()}
    for entry in _register_entries():
        assert entry["robot_slug"] in slugs, entry


def test_an_alias_never_shadows_a_robots_own_name() -> None:
    """An alias equal to a same-maker robot's own name would silently turn that
    robot's exact match into AMBIGUOUS — or be a redundant no-op on its own."""
    rows = _catalogue_rows()
    maker_of = {slug: mfr_name for _, slug, _, mfr_name in rows}
    for entry in _register_entries():
        mfr_key = normalize(maker_of[entry["robot_slug"]])
        key = _model_key(entry["alias"], mfr_key)
        assert key, f"alias {entry['alias']!r} is empty once normalized"
        for _, slug, name, mfr_name in rows:
            if normalize(mfr_name) == mfr_key:
                assert _model_key(name, mfr_key) != key, (entry["alias"], slug)


# --------------------------------------------------------------------------- #
# Matching stays exact (DATA-D1.6)
# --------------------------------------------------------------------------- #
_ROWS = [
    ("g1-basic", "g1-basic", "G1 Basic", "Unitree Robotics"),
    ("g1-edu", "g1-edu", "G1 EDU Plus (U2)", "Unitree Robotics"),
    ("h1-2", "h1-2", "H1-2", "Unitree Robotics"),
    ("galbot-g1", "galbot-g1", "G1", "Galbot"),
]
_G1 = {"g1-basic": ("G1",)}


def _match(manufacturer: str, name: str, aliases) -> list[str]:
    mfr_key = normalize(manufacturer)
    return canonical_matches(mfr_key, _model_key(name, mfr_key), _ROWS, aliases)


def test_without_an_alias_a_renamed_record_is_not_matched() -> None:
    assert _match("Unitree Robotics", "G1", {}) == []


def test_a_confirmed_alias_matches_its_robot() -> None:
    assert _match("Unitree Robotics", "G1", _G1) == ["g1-basic"]
    assert _match("Unitree", "Unitree G1", _G1) == ["g1-basic"]  # maker tokens still stripped


@pytest.mark.parametrize("name", ["G1 EDU", "G1 Basic Plus", "G", "H1", "G1-2"])
def test_an_alias_is_exact_equality_not_similarity(name: str) -> None:
    """A similar name is not the same robot: "H1" must not reach "H1-2"."""
    assert _match("Unitree Robotics", name, _G1) == []


def test_an_alias_never_crosses_manufacturers() -> None:
    assert _match("Galbot", "G1", _G1) == ["galbot-g1"]


def test_one_alias_on_two_robots_is_ambiguous_not_a_guess() -> None:
    """Confirming a family name on two records is how an owner says "a human
    decides which": two matches, which the resolver reports as AMBIGUOUS."""
    both = {"g1-basic": ("G1",), "g1-edu": ("G1",)}
    assert sorted(_match("Unitree Robotics", "G1", both)) == ["g1-basic", "g1-edu"]


# --------------------------------------------------------------------------- #
# Loader: proposals are inert, malformed entries are refused
# --------------------------------------------------------------------------- #
def _entry(**overrides) -> dict:
    entry = {"robot_slug": "g1-basic", "alias": "G1", "basis": "test",
             "proposed_at": "2026-09-10", "confirmed_by": "ops@h.co",
             "confirmed_at": "2026-09-10"}
    entry.update(overrides)
    return entry


def _register(tmp_path: Path, *entries: dict) -> Path:
    path = tmp_path / "identity_aliases.json"
    path.write_text(json.dumps({"aliases": list(entries)}), encoding="utf-8")
    return path


def test_a_confirmed_entry_is_loaded(tmp_path) -> None:
    assert load_confirmed_aliases(_register(tmp_path, _entry())) == {"g1-basic": ("G1",)}


def test_an_unconfirmed_alias_is_a_proposal_and_is_inert(tmp_path) -> None:
    """docs/16 §11: an alias is a proposal, not a merge, until a human confirms it."""
    path = _register(tmp_path, _entry(confirmed_by=None, confirmed_at=None))
    assert load_confirmed_aliases(path) == {}


@pytest.mark.parametrize("bad", [
    {"confirmed_at": None},              # half-confirmed
    {"confirmed_by": None},
    {"confirmed_by": " "},
    {"confirmed_at": "10/09/2026"},      # not an ISO date
    {"alias": " "},
    {"robot_slug": ""},
    {"note": "unknown field"},
])
def test_a_malformed_entry_is_refused(tmp_path, bad: dict) -> None:
    with pytest.raises(ValueError):
        load_confirmed_aliases(_register(tmp_path, _entry(**bad)))


# --------------------------------------------------------------------------- #
# Database wiring
# --------------------------------------------------------------------------- #
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


def test_resolve_identity_matches_through_a_confirmed_alias(dsession) -> None:
    tag = uuid.uuid4().hex[:8]
    mfr = Manufacturer(slug=f"mfr-{tag}", name=f"Zeta{tag} Robotics")
    dsession.add(mfr)
    dsession.flush()
    robot = Robot(slug=f"rob-{tag}", manufacturer_id=mfr.id, name="ZX-1 Basic",
                  is_published=True)
    source = DiscoverySource(key=f"fixture-{tag}", name="Fixture source",
                             source_class="COMPETITOR_DIRECTORY")
    dsession.add_all([robot, source])
    dsession.flush()
    cand = DiscoveryCandidate(source_id=source.id, entity_type="ROBOT",
                              external_ref=f"zeta/{tag}", candidate_name="ZX-1",
                              candidate_manufacturer=mfr.name)
    dsession.add(cand)
    dsession.flush()

    assert resolve_identity(dsession, cand, aliases={}) == "NEW_ENTITY"
    assert cand.possible_robot_id is None
    assert resolve_identity(dsession, cand, aliases={robot.slug: ("ZX-1",)}) == "MATCHED_EXISTING"
    assert cand.possible_robot_id == robot.id
