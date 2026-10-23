"""The NORTH_AMERICA region grouping (HO-RESEARCH-NA-01).

Membership lives in the catalogue's region hierarchy, never in the page layer
(ADR-027 §4). NORTH_AMERICA is a commercial research grouping following UN M49
North America (003) = Northern America (021) + Central America (013) + Caribbean
(029). Unlike EUROPE v0.1 (sovereign states only), it deliberately INCLUDES the
M49 territories that have an ISO 3166-1 row (PR, VI, GL, BM, ...), as the
HO-RESEARCH-NA-01 brief asks. ADR-027 §4 names only US, CA, MX: which reading
stands is owner decision D1 in
docs/audit/HO-RESEARCH-NA-01_NORTH_AMERICA_2026-10-23.md. Every member is a
direct child, so reparenting changes only `region.parent_id`. These tests pin
the hierarchy shape, not the page.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE = REPO_ROOT / "db" / "catalogue"
REGIONS = json.loads((CATALOGUE / "regions.json").read_text(encoding="utf-8"))["regions"]
BY_CODE = {r["code"]: r for r in REGIONS}

NORTHERN_AMERICA = {"BM", "CA", "GL", "PM", "US"}
CENTRAL_AMERICA = {"BZ", "CR", "GT", "HN", "MX", "NI", "PA", "SV"}
CARIBBEAN = {
    "AG", "AI", "AW", "BB", "BL", "BQ", "BS", "CU", "CW", "DM", "DO", "GD", "GP", "HT",
    "JM", "KN", "KY", "LC", "MF", "MQ", "MS", "PR", "SX", "TC", "TT", "VC", "VG", "VI",
}
M49_003 = NORTHERN_AMERICA | CENTRAL_AMERICA | CARIBBEAN


def _ancestors(code: str) -> list[str]:
    out, parent = [], BY_CODE[code].get("parent_code")
    while parent:
        out.append(parent)
        parent = BY_CODE[parent].get("parent_code")
    return out


def _members(root: str) -> set[str]:
    return {r["code"] for r in REGIONS if root in _ancestors(r["code"])}


def test_north_america_is_a_top_level_continent():
    assert BY_CODE["NORTH_AMERICA"]["type"] == "CONTINENT"
    assert BY_CODE["NORTH_AMERICA"]["parent_code"] is None
    assert BY_CODE["NORTH_AMERICA"]["name"] == "North America"


def test_members_are_exactly_un_m49_003():
    assert len(M49_003) == 41
    assert _members("NORTH_AMERICA") == M49_003


def test_us_canada_mexico_and_territories_are_direct_children():
    for code in ("US", "CA", "MX", "PR", "VI", "GL"):
        assert _ancestors(code) == ["NORTH_AMERICA"], code


def test_south_america_global_and_other_continents_are_not_members():
    assert not {"GLOBAL", "BR", "AR", "CO", "VE", "GY", "SR", "CN", "JP", "DE", "UK",
                "UM", "FK"} & _members("NORTH_AMERICA")


def test_north_america_and_europe_do_not_overlap():
    assert not _members("NORTH_AMERICA") & _members("EUROPE")


def test_parents_precede_children_for_the_single_pass_importer():
    seen: set[str] = set()
    for r in REGIONS:
        parent = r.get("parent_code")
        assert parent is None or parent in seen, f"{r['code']} before parent {parent}"
        seen.add(r["code"])


def test_no_catalogue_record_references_the_new_grouping_directly():
    """Reparenting is behaviour-neutral only while nothing is attached to
    NORTH_AMERICA itself: the ancestor walks in matching, lead routing and the
    commercial_offer view would otherwise start applying it to US/CA/MX buyers."""
    hits = [
        p.name for p in sorted((CATALOGUE / "robots").glob("*.json"))
        if '"NORTH_AMERICA"' in p.read_text(encoding="utf-8")
    ]
    hits += [
        p.name for p in (CATALOGUE / "providers.json", CATALOGUE / "manufacturers.json")
        if '"NORTH_AMERICA"' in p.read_text(encoding="utf-8")
    ]
    assert hits == []
