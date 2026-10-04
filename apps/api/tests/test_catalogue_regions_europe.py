"""The reviewed EUROPE region grouping (Europe Readiness Enrichment 01).

Membership lives in the catalogue's region hierarchy, never in the page layer
(ADR-027 §4). EUROPE is a commercial research grouping: EU membership is
inherited transitively through the nested EU zone, and non-EU membership
follows the UN M49 Europe classification for sovereign ISO states (AM, AZ, GE,
TR are Western Asia and KZ is Central Asia, so they are excluded; territories
and non-ISO Kosovo are deliberately not added in v0.1). These tests pin the
hierarchy shape, not the page.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REGIONS = json.loads(
    (REPO_ROOT / "db" / "catalogue" / "regions.json").read_text(encoding="utf-8")
)["regions"]
BY_CODE = {r["code"]: r for r in REGIONS}


def _ancestors(code: str) -> list[str]:
    out, parent = [], BY_CODE[code].get("parent_code")
    while parent:
        out.append(parent)
        parent = BY_CODE[parent].get("parent_code")
    return out


def _members() -> set[str]:
    return {r["code"] for r in REGIONS if "EUROPE" in _ancestors(r["code"])}


def test_europe_is_a_top_level_continent():
    assert BY_CODE["EUROPE"]["type"] == "CONTINENT"
    assert BY_CODE["EUROPE"]["parent_code"] is None


def test_eu27_is_transitively_in_europe():
    eu = {r["code"] for r in REGIONS if r["parent_code"] == "EU"}
    assert len(eu) == 27
    assert eu <= _members()
    assert _ancestors("DE") == ["EU", "EUROPE"]


def test_named_non_eu_europeans_are_members():
    assert {"UK", "NO", "CH", "IS", "LI"} <= _members()


def test_global_and_non_european_regions_are_not_members():
    assert not {"GLOBAL", "US", "CN", "JP", "TR"} & _members()


def test_parents_precede_children_for_the_single_pass_importer():
    seen: set[str] = set()
    for r in REGIONS:
        parent = r.get("parent_code")
        assert parent is None or parent in seen, f"{r['code']} before parent {parent}"
        seen.add(r["code"])


def test_transcontinental_and_non_sovereign_candidates_are_excluded():
    assert not {"AM", "AZ", "GE", "KZ", "TR", "AX", "FO", "GG", "GI", "IM", "JE", "SJ"} & _members()
    assert "XK" not in BY_CODE


def test_belarus_and_russia_follow_m49_europe():
    assert {"BY", "RU"} <= _members()
