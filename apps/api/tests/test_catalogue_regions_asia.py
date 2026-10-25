"""The ASIA region grouping (HO-RESEARCH-ASIA-01).

Membership lives in the catalogue's region hierarchy, never in the page layer
(ADR-027 §4). ASIA is a commercial research grouping following UN M49 Asia (142)
= Central (143) + Eastern (030) + South-eastern (035) + Southern (034) + Western
Asia (145), with two disclosed exceptions (owner decisions D1/D2 in
docs/audit/HO-RESEARCH-ASIA-01_ASIA_2026-10-24.md):

* CY (Cyprus, M49 Western Asia) keeps parent EU. The hierarchy is single-parent,
  so reparenting Cyprus would silently remove an EU member state from the EU zone,
  the pricing-hierarchy view and the Europe resource. Asia v0.1 covers 49 of the
  50 M49 Asia codes.
* TW is included as a commercial-market member (an ISO 3166-1 row the catalogue
  uses as a separate destination; M49 does not list it as a separate Asia entry).

RU stays under EUROPE, APAC is not modelled, GLOBAL is never a member. Every
member is a direct child, so reparenting changes only `region.parent_id`.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE = REPO_ROOT / "db" / "catalogue"
REGIONS = json.loads((CATALOGUE / "regions.json").read_text(encoding="utf-8"))["regions"]
BY_CODE = {r["code"]: r for r in REGIONS}

CENTRAL_ASIA = {"KZ", "KG", "TJ", "TM", "UZ"}
EASTERN_ASIA = {"CN", "HK", "MO", "KP", "JP", "MN", "KR"}
SOUTH_EASTERN_ASIA = {"BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN"}
SOUTHERN_ASIA = {"AF", "BD", "BT", "IN", "IR", "MV", "NP", "PK", "LK"}
WESTERN_ASIA = {
    "AM", "AZ", "BH", "CY", "GE", "IQ", "IL", "JO", "KW", "LB", "OM", "QA", "SA", "PS", "SY",
    "TR", "AE", "YE",
}
M49_142 = CENTRAL_ASIA | EASTERN_ASIA | SOUTH_EASTERN_ASIA | SOUTHERN_ASIA | WESTERN_ASIA
ASIA_V01 = (M49_142 - {"CY"}) | {"TW"}


def _ancestors(code: str) -> list[str]:
    out, parent = [], BY_CODE[code].get("parent_code")
    while parent:
        out.append(parent)
        parent = BY_CODE[parent].get("parent_code")
    return out


def _members(root: str) -> set[str]:
    return {r["code"] for r in REGIONS if root in _ancestors(r["code"])}


def test_asia_is_a_top_level_continent():
    assert BY_CODE["ASIA"]["type"] == "CONTINENT"
    assert BY_CODE["ASIA"]["parent_code"] is None
    assert BY_CODE["ASIA"]["name"] == "Asia"


def test_m49_142_has_fifty_codes_all_present_in_the_catalogue():
    assert len(M49_142) == 50
    assert M49_142 <= set(BY_CODE)


def test_members_are_m49_142_minus_cyprus_plus_taiwan():
    assert _members("ASIA") == ASIA_V01
    assert len(ASIA_V01) == 50  # 49 of the 50 M49 codes + TW


def test_every_member_is_a_direct_child():
    for code in ASIA_V01:
        assert _ancestors(code) == ["ASIA"], code


def test_cyprus_stays_in_the_eu_and_europe_and_out_of_asia():
    assert BY_CODE["CY"]["parent_code"] == "EU"
    assert _ancestors("CY") == ["EU", "EUROPE"]
    assert "CY" in _members("EUROPE")
    assert "CY" not in _members("ASIA")


def test_taiwan_is_a_commercial_member_but_not_reparented_under_china():
    assert BY_CODE["TW"]["type"] == "COUNTRY"
    assert _ancestors("TW") == ["ASIA"]
    assert "TW" not in M49_142


def test_russia_stays_in_europe_and_apac_is_not_modelled():
    assert _ancestors("RU") == ["EUROPE"]
    assert "APAC" not in BY_CODE
    assert not {"AU", "NZ", "FJ", "PG", "GLOBAL", "RU", "EG", "US"} & _members("ASIA")


def test_existing_groupings_are_unchanged_and_disjoint():
    assert len(_members("EUROPE")) == 46  # EU zone + 27 member states + 18 non-EU states
    assert len(_members("NORTH_AMERICA")) == 41
    assert not _members("ASIA") & _members("EUROPE")
    assert not _members("ASIA") & _members("NORTH_AMERICA")


def test_parents_precede_children_for_the_single_pass_importer():
    seen: set[str] = set()
    for r in REGIONS:
        parent = r.get("parent_code")
        assert parent is None or parent in seen, f"{r['code']} before parent {parent}"
        seen.add(r["code"])


def test_no_catalogue_record_references_the_new_grouping_directly():
    """Reparenting is behaviour-neutral only while nothing is attached to ASIA
    itself: the ancestor walks in matching, lead routing and the commercial_offer
    view would otherwise start applying it to every Asian buyer."""
    hits = [
        p.name for p in sorted((CATALOGUE / "robots").glob("*.json"))
        if '"ASIA"' in p.read_text(encoding="utf-8")
    ]
    hits += [
        p.name for p in (CATALOGUE / "providers.json", CATALOGUE / "manufacturers.json")
        if '"ASIA"' in p.read_text(encoding="utf-8")
    ]
    assert hits == []
