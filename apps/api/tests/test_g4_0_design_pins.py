"""G4-0 design pins (DR-G4): the ratified architecture and semantic decisions, pinned before code.

These tests need no database. They fail if the ratification record, the roadmap/DR-A5 amendments,
the initial projection registry fixture or the 4NE1 Mini golden resolution drift from the owner's
rulings of 2026-10-03. G4-1's code registry must equal `fixtures/g4/initial_registry.json`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FIX = Path(__file__).parent / "fixtures" / "g4"
DR = REPO / "docs" / "decisions" / "DR-G4_CANONICAL_SCOPED_FACT_RESOLUTION.md"
DR_A5 = REPO / "docs" / "decisions" / (
    "DR-A5_GOVERNED_CLAIM_PROPOSAL_REVIEW_AND_PROMOTION_BOUNDARY.md")
ROADMAP = REPO / "docs" / "08_DEVELOPMENT_ROADMAP.md"

STATES = ["PRODUCT_VALUE", "UNIFORM_VARIANTS", "VARIES_BY_VARIANT", "PARTIAL_VARIANTS", "UNKNOWN",
          "CONFLICT"]
CLASSES = ["CANONICAL_DIRECT", "CANONICAL_PROJECTED", "DETAIL_ONLY", "NO_CATALOGUE_HOME"]


def text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def flat(p: Path) -> str:
    """The document with line wrapping collapsed, so a phrase may wrap in the source."""
    return " ".join(text(p).split())


def registry() -> dict:
    return json.loads(text(FIX / "initial_registry.json"))


def tokens_of(entry: dict) -> list[str]:
    value = entry["value"]
    if entry["key"] == "dexterous_hand_option":
        return [value]
    return [p.strip() for p in value.split(",")]


# ------------------------------------------------------------------ identifiers ---


def test_g4_phases_are_defined_and_g2_6_is_preserved():
    dr = text(DR)
    for ident in ("G4-0", "G4-1", "G4-2", "G4-3", "G4-4"):
        assert ident in dr and ident in text(ROADMAP)
    a5 = text(DR_A5)
    row = next(line for line in a5.splitlines() if line.startswith("| **G2-6**"))
    # the original milestone text is intact; only an amendment was appended
    original = ("A second manufacturer: separate source and ToS approval, a separate adapter and "
                "extractor. This is Stage G3.")
    assert original in row
    assert "Satisfied in substance" in row and "Stage G4" in row
    assert "G2-7" not in a5 and "G2-7" not in text(ROADMAP)
    assert "G2-7" not in text(DR).replace("No `G2-7` or later exists", "")
    assert "| **G4** |" in text(ROADMAP)


def test_the_dr_names_every_state_and_accounting_class():
    dr = text(DR)
    for name in STATES + CLASSES:
        assert f"`{name}`" in dr, name
    assert "integrity failure" in dr
    for name in ("UNMAPPED_KNOWLEDGE", "UNACCOUNTED_LOSS", "NOT_YET_REVIEWED"):
        assert f"`{name}`" in dr, name
    # the retired design made accounting completeness a publication blocker
    assert "unaccounted = 0" not in dr


# ------------------------------------------------------------------ storage ---


def test_storage_rulings_are_recorded():
    dr = text(DR)
    assert "`robot_variant.spec_overrides` is not used" in dr
    assert "No derived database table" in dr
    assert "never written" in dr or "never stored" in dr
    assert ("resolved_fact = f(product core value, scoped canonical facts, "
            "projection registry version)") in dr


# ------------------------------------------------------------------ registry ---


def test_the_initial_registry_is_exactly_the_ratified_five_mappings():
    reg = registry()
    assert reg["registry_version"] == "0.1.0-g4-initial"
    got = {(e["spec_key"], e["token"], e["property"], e["value"]) for e in reg["entries"]}
    assert got == {
        ("common_interfaces", "Python SDK", "has_sdk", True),
        ("additional_interfaces", "C++ SDK", "has_sdk", True),
        ("common_interfaces", "ROS 2 interface", "ros_support", True),
        ("additional_interfaces", "teleoperation", "has_teleoperation", True),
        ("dexterous_hand_option", "12 DoF dexterous hands", "has_manipulation", True),
    }
    assert len(reg["entries"]) == 5


def test_no_registered_projection_is_ever_negative_or_fuzzy():
    reg = registry()
    assert all(e["value"] is True for e in reg["entries"])           # absence never projects false
    assert "no fuzzy" in reg["matching"]
    for e in reg["entries"]:                                         # exact tokens, no wildcards
        assert e["token"] == e["token"].strip() and not any(c in e["token"] for c in "*?%|")


def test_the_explicit_non_mappings_are_pinned():
    reg = registry()
    by = {(n["spec_key"], n["token"], n["never_projects"]) for n in reg["explicitly_not_mapped"]}
    assert ("dexterous_hand_option", "Not included", "has_manipulation = false") in by
    assert ("dexterous_hand_option", "12 DoF dexterous hands", "hand_dof") in by
    registered = {(e["spec_key"], e["token"]) for e in reg["entries"]}
    # "Not included" and every DETAIL_ONLY token are absent from the registry
    for n in reg["explicitly_not_mapped"]:
        if n["never_projects"] != "hand_dof":
            assert (n["spec_key"], n["token"]) not in registered
    props = {e["property"] for e in reg["entries"]}
    assert "hand_dof" not in props and "has_api" not in props   # no ROS->API, no 12 DoF->hand_dof


# ------------------------------------------------------------------ Mini golden ---


def test_the_mini_golden_resolution_follows_the_rulings():
    g = json.loads(text(FIX / "mini_expected_resolution.json"))
    res = g["resolution"]
    assert res["has_sdk"] == {"state": "UNIFORM_VARIANTS", "value": True,
                              "variants": {"standard": True, "pro": True}}
    assert res["ros_support"]["state"] == "UNIFORM_VARIANTS" and res["ros_support"]["value"] is True
    for prop in ("has_teleoperation", "has_manipulation"):
        assert res[prop]["state"] == "PARTIAL_VARIANTS" and res[prop]["value"] is None
        assert res[prop]["variants"] == {"standard": None, "pro": True}   # Standard stays UNKNOWN
    assert all(v is not False for r in res.values() for v in r["variants"].values())
    assert "has_manipulation=false" in g["never_fabricated"]
    assert "hand_dof=12" in g["never_fabricated"]
    assert "Not included" in g["detail_facts_retained"]["standard"]


def test_the_mini_golden_matches_the_real_catalogue_facts():
    """Design fixtures must describe reality: the tokens exist verbatim on the real Mini record."""
    doc = json.loads(text(REPO / "db" / "catalogue" / "robots" / "4ne1-mini.json"))
    g = json.loads(text(FIX / "mini_expected_resolution.json"))
    seen: dict[str, set[str]] = {"standard": set(), "pro": set()}
    scoped = [e for e in doc["extended_specs"] if e.get("variant_slug")]
    for e in scoped:
        seen[e["variant_slug"]].update(tokens_of(e))
    for variant, expected in g["detail_facts_retained"].items():
        assert set(expected) == seen[variant], variant
    reg = {(e["spec_key"], e["token"]) for e in registry()["entries"]}
    present = {(e["key"], t) for e in scoped for t in tokens_of(e)}
    assert reg <= present                                           # every registered token occurs


# ------------------------------------------------------------------ consumers ---


@pytest.mark.parametrize("needle", [
    "ANY-VARIANT",
    "Available on some configurations",
    "CONSERVATIVE",
    "`PRODUCT_VALUE = true` and `UNIFORM_VARIANTS = true`",
    "never mutates",
    "Absence of an option is not absence of a capability",
    "projection candidate / owner mapping required",
    "read-only",
    "does **not** project `has_manipulation = false`",
])
def test_consumer_and_governance_semantics_are_recorded(needle):
    assert needle in flat(DR)


# ------------------------------------------------------------------ G4-3: integrity vs coverage ---


def test_g4_3_is_an_integrity_gate_not_a_completeness_gate():
    """Owner correction 2026-10-03: incomplete is publishable, misleading is not."""
    dr = flat(DR)
    assert "Incomplete is publishable. Misleading is not." in dr
    assert "Fresh + truthful + incomplete is preferable to complete-but-late" in dr
    # two separate concepts; only integrity blocks
    assert "INTEGRITY / TRUTHFULNESS" in dr and "COVERAGE / COMPLETENESS" in dr
    assert "never blocks" in dr
    assert "no public label and no schema field is introduced" in dr


def test_the_hard_blockers_are_exactly_the_integrity_conditions():
    dr = flat(DR)
    for blocker in ("Identity unresolved", "Canonical `CONFLICT`",
                    "Public value contradicts canonical evidence",
                    "Fabricated precision or unsupported inference", "Required provenance missing",
                    "Publication mechanics or invariants broken"):
        assert blocker in dr, blocker


@pytest.mark.parametrize("never_a_blocker", [
    "UNKNOWN physical specifications", "a missing price, availability",
    "`DETAIL_ONLY` information", "`NO_CATALOGUE_HOME` facts",
    "a manufacturer statement that has not yet gained a semantic projection",
    "a missing optional projection mapping", "incomplete use-case classification",
    "incomplete historical chronology",
    "safely preserved verbatim but not yet normalized into a first-class field",
])
def test_completeness_conditions_never_block_publication(never_a_blocker):
    dr = flat(DR)
    section = dr[dr.index("### 7.2 Never blockers"):dr.index("### 7.3")]
    assert never_a_blocker in section


def test_unaccounted_is_split_and_only_loss_is_an_integrity_defect():
    dr = flat(DR)
    assert "`UNMAPPED_KNOWLEDGE`" in dr and "Not a blocker" in dr
    assert "`UNACCOUNTED_LOSS`" in dr and "integrity defect" in dr
    assert "`NOT_YET_REVIEWED`" in dr and "is **not canonical knowledge**" in dr
    assert "lost = 0 for the facts required by the intended public representation" in dr
    assert "conflicts = 0 for current public assertions" in dr


def test_the_fresh_announcement_path_and_the_existing_robot_guarantee_are_recorded():
    dr = flat(DR)
    assert "A newly announced humanoid is **publication-ready**" in dr
    assert "80 body DoF" in dr and "are never awaited" in dr
    assert "never unpublishes" in dr and "Low coverage never unpublishes a robot" in dr
    assert "informational, non-blocking unless the owner explicitly upgrades it" in dr
    assert "not** a mass requirement to normalize every fact" in dr


def test_explicit_negatives_use_the_governed_chain_never_spec_caveats():
    """Owner ruling 2026-10-03."""
    dr = flat(DR)
    assert "### 4.3 Explicit negative facts" in dr
    assert "`spec_caveats` is explanatory metadata only" in dr
    assert "It never establishes `false`" in dr
    assert "source statement -> proposal -> ACCEPT -> accepted claim" in dr
    assert "registered negative projection -> resolved boolean false" in dr
    assert "The initial registry contains **no** negative mapping" in dr
    assert "prefer `NULL`/UNKNOWN" in dr and "do not invent source wording" in dr.lower()
    assert "EXPLICIT_NEGATIVE" not in dr          # the retired spec_caveats convention
    reg = registry()
    assert all(e["value"] is True for e in reg["entries"])  # no negative mapping ratified yet
