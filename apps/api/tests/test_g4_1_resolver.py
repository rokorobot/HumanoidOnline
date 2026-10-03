"""G4-1: the pure resolver and projection registry (DR-G4).

No database. Pins the owner's rulings of 2026-10-03: exact registered projections only, the six
resolution states, CONFLICT as an integrity failure, absence never false, the conservative matching
and ANY-VARIANT filter helpers, and the 4NE1 Mini golden resolution on the REAL catalogue record.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from app.services import fact_resolution as fr
from app.services.fact_resolution import (
    PROJECTION_REGISTRY,
    REGISTRY_VERSION,
    ProjectionRule,
    ResolutionError,
    ScopedSpec,
    State,
    any_variant_match,
    project,
    resolve_property,
    resolve_robot,
    satisfies_hard_requirement,
    tokens_of,
)

REPO = Path(__file__).resolve().parents[3]
FIX = Path(__file__).parent / "fixtures" / "g4"
VARIANTS = [("standard", "Standard"), ("pro", "Pro")]


def spec(variant, key, value):
    return ScopedSpec(variant, key, value)


# A synthetic registry with a NEGATIVE rule, to exercise states the initial (positive-only)
# registry cannot reach. Never used for real data.
NEG = (*PROJECTION_REGISTRY,
       ProjectionRule("common_interfaces", "No SDK support", "has_sdk", False))


# ------------------------------------------------------------------ the registry ---


def test_the_code_registry_equals_the_ratified_fixture():
    fx = json.loads((FIX / "initial_registry.json").read_text(encoding="utf-8"))
    assert REGISTRY_VERSION == fx["registry_version"]
    assert {(r.spec_key, r.token, r.property, r.value) for r in PROJECTION_REGISTRY} == {
        (e["spec_key"], e["token"], e["property"], e["value"]) for e in fx["entries"]}
    assert len(PROJECTION_REGISTRY) == len(fx["entries"]) == 5
    assert all(r.value is True for r in PROJECTION_REGISTRY)        # absence never projects false


def test_the_explicit_non_mappings_never_project():
    fx = json.loads((FIX / "initial_registry.json").read_text(encoding="utf-8"))
    for n in fx["explicitly_not_mapped"]:
        got = project(spec("pro", n["spec_key"], n["token"]))
        if n["never_projects"] == "hand_dof":
            # "12 DoF dexterous hands" projects has_manipulation only, never hand_dof
            assert [p for p, _, _ in got] == ["has_manipulation"]
        else:
            assert got == (), n


def test_projection_is_exact_never_fuzzy():
    for key, wrong in [
        ("common_interfaces", "python sdk"),                # case differs
        ("common_interfaces", "Python SDK 2"),              # superstring
        ("common_interfaces", "Python"),                    # substring
        ("common_interfaces", "PythonSDK"),
        ("common_interfaces", "ROS2 interface"),
        ("common_interfaces", "ROS 2"),
        ("additional_interfaces", "Teleoperation"),         # case differs
        ("additional_interfaces", "teleoperation support"),
        ("dexterous_hand_option", "12 DoF dexterous hand"),
        ("dexterous_hand_option", "12-DoF dexterous hands"),
        ("dexterous_hand_option", "Not included"),
        ("common_interfaces", "C++ SDK"),                   # right token, wrong key
        ("additional_interfaces", "Python SDK"),            # right token, wrong key
    ]:
        assert project(spec("pro", key, wrong)) == (), (key, wrong)


def test_tokens_are_whitespace_normalized_only():
    assert tokens_of("common_interfaces", "  Wi-Fi 6 ,Ethernet,   Python   SDK ,") == (
        "Wi-Fi 6", "Ethernet", "Python SDK")
    assert project(spec("pro", "common_interfaces", "Wi-Fi 6,  Python   SDK")) == (
        ("has_sdk", True, "Python SDK"),)
    assert tokens_of("dexterous_hand_option", " 12 DoF dexterous hands ") == (
        "12 DoF dexterous hands",)
    assert tokens_of("common_interfaces", None) == ()


def test_either_sdk_token_establishes_sdk_and_ros_does_not_imply_api():
    only_cpp = [spec("pro", "additional_interfaces", "C++ SDK")]
    only_py = [spec("pro", "common_interfaces", "Python SDK")]
    assert resolve_property("has_sdk", None, [("pro", "Pro")], only_cpp).value is True
    assert resolve_property("has_sdk", None, [("pro", "Pro")], only_py).value is True
    ros = [spec("pro", "common_interfaces", "ROS 2 interface")]
    got = resolve_robot({}, [("pro", "Pro")], ros)
    assert got["ros_support"].value is True
    assert "has_api" not in got and got["has_sdk"].state is State.UNKNOWN   # no ROS -> SDK/API


# ------------------------------------------------------------------ the six states ---


def test_unknown_when_no_evidence_at_any_scope():
    for variants in ([], VARIANTS):
        f = resolve_property("has_sdk", None, variants, [])
        assert (f.state, f.value, f.product_value) == (State.UNKNOWN, None, None)


def test_unrelated_scoped_facts_do_not_unknown_hide_or_invent():
    s = [spec("pro", "common_interfaces", "Wi-Fi 6, Ethernet")]       # known, but no SDK token
    f = resolve_property("has_sdk", None, VARIANTS, s)
    assert f.state is State.UNKNOWN                                    # nothing about SDK is known


def test_product_value_from_the_core_column():
    for v in (True, False):
        f = resolve_property("has_sdk", v, VARIANTS, [])
        assert (f.state, f.value, f.product_source) == (State.PRODUCT_VALUE, v, "core")


def test_product_value_from_a_product_level_projection():
    f = resolve_property("has_sdk", None, [], [spec(None, "common_interfaces", "Python SDK")])
    assert (f.state, f.value, f.product_source) == (State.PRODUCT_VALUE, True, "projection")


def test_uniform_variants():
    s = [spec("standard", "common_interfaces", "Python SDK"),
         spec("pro", "common_interfaces", "Python SDK")]
    f = resolve_property("has_sdk", None, VARIANTS, s)
    assert (f.state, f.value) == (State.UNIFORM_VARIANTS, True)


def test_partial_variants_keeps_the_unknown_configuration_unknown():
    s = [spec("pro", "additional_interfaces", "teleoperation")]
    f = resolve_property("has_teleoperation", None, VARIANTS, s)
    assert f.state is State.PARTIAL_VARIANTS and f.value is None
    assert [(v.slug, v.value) for v in f.variants] == [("standard", None), ("pro", True)]


def test_varies_by_variant_needs_all_known_and_two_different():
    s = [spec("standard", "common_interfaces", "No SDK support"),
         spec("pro", "common_interfaces", "Python SDK")]
    f = resolve_property("has_sdk", None, VARIANTS, s, registry=NEG)
    assert f.state is State.VARIES_BY_VARIANT and f.value is None
    assert [(v.slug, v.value) for v in f.variants] == [("standard", False), ("pro", True)]


def test_conflict_when_a_variant_contradicts_the_product_value():
    s = [spec("pro", "common_interfaces", "Python SDK")]
    f = resolve_property("has_sdk", False, VARIANTS, s)
    assert f.state is State.CONFLICT and f.value is None and "contradicts" in f.detail
    assert f.product_value is False                       # the product value did NOT silently win


def test_conflict_when_one_scope_states_both_true_and_false():
    s = [spec("pro", "common_interfaces", "Python SDK, No SDK support")]
    f = resolve_property("has_sdk", None, VARIANTS, s, registry=NEG)
    assert f.state is State.CONFLICT
    p = [spec(None, "common_interfaces", "Python SDK, No SDK support")]
    assert resolve_property("has_sdk", None, [], p, registry=NEG).state is State.CONFLICT


def test_conflict_when_a_product_projection_disagrees_with_the_core_column():
    p = [spec(None, "common_interfaces", "Python SDK")]
    f = resolve_property("has_sdk", False, [], p)
    assert f.state is State.CONFLICT


def test_agreeing_variant_and_product_value_is_a_product_value():
    s = [spec("pro", "common_interfaces", "Python SDK")]
    f = resolve_property("has_sdk", True, VARIANTS, s)
    assert (f.state, f.value) == (State.PRODUCT_VALUE, True)


def test_a_scoped_fact_for_an_undocumented_variant_is_an_input_error():
    with pytest.raises(ResolutionError, match="not one of the robot's documented variants"):
        resolve_property("has_sdk", None, VARIANTS,
                         [spec("ghost", "common_interfaces", "Python SDK")])


# ------------------------------------------------------------------ determinism ---


def test_the_resolver_is_deterministic_and_order_independent_and_pure():
    s = [spec("standard", "common_interfaces", "Wi-Fi 6, Python SDK, ROS 2 interface"),
         spec("pro", "common_interfaces", "Wi-Fi 6, Python SDK, ROS 2 interface"),
         spec("pro", "additional_interfaces", "C++ SDK, teleoperation"),
         spec("pro", "dexterous_hand_option", "12 DoF dexterous hands"),
         spec("standard", "dexterous_hand_option", "Not included")]
    base = resolve_robot({}, VARIANTS, s)
    for seed in range(20):
        shuffled = list(s)
        random.Random(seed).shuffle(shuffled)
        assert resolve_robot({}, VARIANTS, shuffled) == base
    before = list(s)
    resolve_robot({}, VARIANTS, s)
    assert s == before                                                    # inputs untouched
    assert list(base) == sorted(base)


# ------------------------------------------------------------------ consumer helpers ---


@pytest.mark.parametrize("state,value,expected", [
    (State.PRODUCT_VALUE, True, True), (State.UNIFORM_VARIANTS, True, True),
    (State.PRODUCT_VALUE, False, False), (State.UNIFORM_VARIANTS, False, False),
    (State.VARIES_BY_VARIANT, None, False), (State.PARTIAL_VARIANTS, None, False),
    (State.UNKNOWN, None, False), (State.CONFLICT, None, False)])
def test_conservative_matching_only_product_or_uniform_true_satisfies(state, value, expected):
    f = fr.ResolvedFact("has_sdk", state, value, None, None, ())
    assert satisfies_hard_requirement(f) is expected


def test_any_variant_filter_labels_partial_matches_and_never_universalizes():
    pro_only = resolve_property(
        "has_sdk", None, VARIANTS, [spec("pro", "additional_interfaces", "C++ SDK")])
    m = any_variant_match(pro_only)
    assert (m.matches, m.product_wide, m.configurations) == (True, False, ("pro",))
    assert m.label == "Available on some configurations"
    both = resolve_property("has_sdk", None, VARIANTS, [
        spec("standard", "common_interfaces", "Python SDK"),
        spec("pro", "common_interfaces", "Python SDK")])
    m = any_variant_match(both)
    assert (m.matches, m.product_wide) == (True, True) and m.label is None
    assert any_variant_match(resolve_property("has_sdk", True, VARIANTS, [])).product_wide
    none = any_variant_match(resolve_property("has_sdk", None, VARIANTS, []))
    assert (none.matches, none.label) == (False, None)
    conflict = resolve_property(
        "has_sdk", False, VARIANTS, [spec("pro", "common_interfaces", "Python SDK")])
    assert any_variant_match(conflict).matches is False


# ------------------------------------------------------------------ the REAL records ---


def robot_inputs(doc):
    variants = [(v["slug"], v["name"]) for v in doc.get("variants", [])]
    specs = [ScopedSpec(e.get("variant_slug"), e["key"], e.get("value")
                        if isinstance(e.get("value"), str) else None)
             for e in doc.get("extended_specs", [])]
    return doc.get("specs") or {}, variants, specs


def test_the_4ne1_mini_golden_resolution_on_the_real_record():
    doc = json.loads((REPO / "db" / "catalogue" / "robots" / "4ne1-mini.json")
                     .read_text(encoding="utf-8"))
    golden = json.loads((FIX / "mini_expected_resolution.json").read_text(encoding="utf-8"))
    product, variants, specs = robot_inputs(doc)
    got = resolve_robot(product, variants, specs)
    assert golden["registry_version"] == REGISTRY_VERSION
    assert set(got) == set(golden["resolution"])
    for prop, want in golden["resolution"].items():
        f = got[prop]
        assert f.state.value == want["state"], prop
        assert f.value == want["value"], prop
        assert {v.slug: v.value for v in f.variants} == want["variants"], prop
    # no fabricated false anywhere, and the robot-level core booleans stay NULL (not written back)
    assert all(v.value is not False for f in got.values() for v in f.variants)
    assert all(product.get(p) is None for p in got)
    # the Standard configuration's richer fact is untouched by the projection
    std = {e["value"] for e in doc["extended_specs"]
           if e.get("variant_slug") == "standard" and e["key"] == "dexterous_hand_option"}
    assert std == {"Not included"}


def test_the_whole_catalogue_resolves_without_conflict_or_error():
    """A read-only preview of G4-4: every real record resolves; nothing is in CONFLICT; and a
    robot without scoped facts never gains a value the catalogue did not already state."""
    n = 0
    for path in sorted((REPO / "db" / "catalogue" / "robots").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        product, variants, specs = robot_inputs(doc)
        got = resolve_robot(product, variants, specs)
        n += 1
        for prop, f in got.items():
            assert f.state is not State.CONFLICT, (path.name, prop, f.detail)
            if not any(s.variant_slug or s.spec_key in {r.spec_key for r in PROJECTION_REGISTRY}
                       for s in specs):
                want = product.get(prop)
                assert (f.state is State.UNKNOWN and want is None) or (
                    f.state is State.PRODUCT_VALUE and f.value == want), (path.name, prop)
    assert n >= 57
