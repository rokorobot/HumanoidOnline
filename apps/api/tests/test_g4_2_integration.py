"""G4-2: the G4 resolver is the single interpretation layer for every consumer (DR-G4).

Database-backed. Each test builds small, self-contained robots (a 4NE1-Mini-shaped one with the
real spec keys and tokens, plus product-value, unknown and conflict cases) inside the test
database and removes them afterwards, so nothing depends on which real robots the catalogue holds.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import event, text

from app.db.session import SessionLocal, engine
from app.services import fact_resolution as fr
from app.services.agent_tools import get_robot, search_robots
from app.services.evidence_refs import EvidenceRefKeyring
from app.services.matching.inputs import RequirementInput
from app.services.matching.repository import load_candidates
from app.services.resolved_facts import load_resolutions

REPO = Path(__file__).resolve().parents[3]
KEYRING = EvidenceRefKeyring(active_id="1", keys={"1": bytes([1]) * 64})

SPECS = {
    "common_interfaces": ("Common interfaces", "SOFTWARE"),
    "additional_interfaces": ("Additional interfaces", "SOFTWARE"),
    "dexterous_hand_option": ("Dexterous hand option", "MANIPULATION"),
}


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


class Maker:
    """Creates published test robots; removes them (and their variants/specs) on teardown."""

    def __init__(self):
        self.ids: list = []
        self.mfr = _exec("SELECT id FROM manufacturer LIMIT 1").scalar_one()
        for key, (label, category) in SPECS.items():
            _exec(
                "INSERT INTO spec_definition (key, label, category, value_type, sort_order) "
                "VALUES (:k, :l, CAST(:c AS capability_category), 'TEXT', 90) "
                "ON CONFLICT (key) DO NOTHING", k=key, l=label, c=category)

    def robot(self, tag: str, *, variants=(), specs=(), **cols) -> str:
        slug = f"g42-{tag}-{uuid.uuid4().hex[:8]}"
        rid = _exec(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
            "VALUES (:s, :m, :n, TRUE) RETURNING id", s=slug, m=self.mfr, n=slug.upper(),
        ).scalar_one()
        self.ids.append(rid)
        for col, value in cols.items():
            _exec(f"UPDATE robot SET {col} = :v WHERE id = :i", v=value, i=rid)
        vids = {}
        for vslug, vname in variants:
            vids[vslug] = _exec(
                "INSERT INTO robot_variant (robot_id, slug, name) VALUES (:r, :s, :n) RETURNING id",
                r=rid, s=vslug, n=vname).scalar_one()
        for vslug, key, value in specs:
            _exec(
                "INSERT INTO specification (robot_id, variant_id, definition_id, value_text) "
                "SELECT :r, :v, d.id, :t FROM spec_definition d WHERE d.key = :k",
                r=rid, v=vids.get(vslug), t=value, k=key)
        return slug

    def cleanup(self):
        for rid in self.ids:
            _exec("DELETE FROM robot WHERE id = :i", i=rid)


@pytest.fixture
def maker(database_url):
    m = Maker()
    yield m
    m.cleanup()


MINI_VARIANTS = (("standard", "Standard"), ("pro", "Pro"))
MINI_SPECS = (
    ("standard", "dexterous_hand_option", "Not included"),
    ("pro", "dexterous_hand_option", "12 DoF dexterous hands"),
    ("standard", "common_interfaces", "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync"),
    ("pro", "common_interfaces", "Wi-Fi 6, Ethernet, Python SDK, ROS 2 interface, NEURA Sync"),
    ("pro", "additional_interfaces",
     "C++ SDK, digital twin access, teleoperation, ready for Neura Gym training"),
)


@pytest.fixture
def world(maker):
    return {
        "mini": maker.robot("mini", variants=MINI_VARIANTS, specs=MINI_SPECS),
        "proonly": maker.robot(
            "proonly", variants=MINI_VARIANTS,
            specs=(("pro", "additional_interfaces", "C++ SDK"),
                   ("standard", "common_interfaces", "Wi-Fi 6"))),
        "unknown": maker.robot("unknown", variants=MINI_VARIANTS,
                               specs=(("pro", "common_interfaces", "Wi-Fi 6"),)),
        "novariant": maker.robot("novariant"),
        "prodtrue": maker.robot("prodtrue", has_sdk=True, ros_support=True, has_manipulation=True),
        "prodfalse": maker.robot("prodfalse", has_sdk=False, has_manipulation=False),
        "conflict": maker.robot(
            "conflict", variants=MINI_VARIANTS, has_sdk=False,
            specs=(("pro", "common_interfaces", "Python SDK"),)),
    }


def detail(client, slug):
    r = client.get(f"/api/robots/{slug}")
    assert r.status_code == 200
    return r.json()


def facts(body):
    return {f["property"]: f for f in body["resolved_facts"]}


def vals(fact):
    return {v["slug"]: v["value"] for v in fact["variants"]}


def core(slug):
    return _exec(
        "SELECT has_sdk, ros_support, has_teleoperation, has_manipulation, hand_dof "
        "FROM robot WHERE slug = :s", s=slug).one()


# ------------------------------------------------------------------------------ API detail ---


def test_the_mini_shaped_robot_resolves_to_the_g4_golden_states(client, world):
    body = detail(client, world["mini"])
    f = facts(body)
    assert sorted(f) == ["has_manipulation", "has_sdk", "has_teleoperation", "ros_support"]
    assert (f["has_sdk"]["state"], f["has_sdk"]["value"]) == ("UNIFORM_VARIANTS", True)
    assert vals(f["has_sdk"]) == {"pro": True, "standard": True}
    assert (f["ros_support"]["state"], f["ros_support"]["value"]) == ("UNIFORM_VARIANTS", True)
    for prop in ("has_teleoperation", "has_manipulation"):
        assert (f[prop]["state"], f[prop]["value"]) == ("PARTIAL_VARIANTS", None)
        assert vals(f[prop]) == {"pro": True, "standard": None}      # Standard stays UNKNOWN
    assert all(x["registry_version"] == fr.REGISTRY_VERSION for x in f.values())
    assert all(x["product_value"] is None and x["product_source"] is None for x in f.values())


def test_projection_evidence_and_the_verbatim_fact_travel_with_the_variant(client, world):
    f = facts(detail(client, world["mini"]))
    pro = next(v for v in f["has_sdk"]["variants"] if v["slug"] == "pro")
    assert {(e["spec_key"], e["token"]) for e in pro["evidence"]} == {
        ("common_interfaces", "Python SDK"), ("additional_interfaces", "C++ SDK")}
    manip = {v["slug"]: v for v in f["has_manipulation"]["variants"]}
    # "Not included" stays visible and is NOT turned into false
    assert manip["standard"]["value"] is None
    assert [(s["label"], s["value"]) for s in manip["standard"]["source_facts"]] == [
        ("Dexterous hand option", "Not included")]
    assert [s["value"] for s in manip["pro"]["source_facts"]] == ["12 DoF dexterous hands"]
    assert manip["pro"]["evidence"] == [
        {"spec_key": "dexterous_hand_option", "token": "12 DoF dexterous hands"}]


def test_the_robot_level_columns_are_never_written_back(client, world):
    detail(client, world["mini"])                              # reads resolve; they must not write
    client.get("/api/robots", params={"has_sdk": "true", "limit": 100})
    assert tuple(core(world["mini"])) == (None, None, None, None, None)
    body = detail(client, world["mini"])
    assert body["specs"]["has_sdk"] is None and body["specs"]["has_manipulation"] is None
    assert body["specs"]["hand_dof"] is None                   # "12 DoF" never populates hand_dof


def test_existing_specs_fields_are_unchanged_and_the_addition_is_additive(client, world):
    body = detail(client, world["mini"])
    for key in ("specs", "spec_caveats", "extended_specs", "variants", "images", "capabilities"):
        assert key in body
    assert {"has_sdk", "ros_support", "has_teleoperation", "has_manipulation", "hand_dof",
            "degrees_of_freedom"} <= set(body["specs"])


def test_a_robot_without_variants_resolves_from_product_scope_only(client, world):
    f = facts(detail(client, world["novariant"]))
    assert all(x["state"] == "UNKNOWN" and x["variants"] == [] for x in f.values())
    p = facts(detail(client, world["prodtrue"]))
    assert (p["has_sdk"]["state"], p["has_sdk"]["value"], p["has_sdk"]["product_source"]) == (
        "PRODUCT_VALUE", True, "core")
    assert p["has_teleoperation"]["state"] == "UNKNOWN"
    q = facts(detail(client, world["prodfalse"]))
    assert (q["has_sdk"]["state"], q["has_sdk"]["value"]) == ("PRODUCT_VALUE", False)


def test_conflict_is_exposed_and_never_resolved_silently(client, world):
    f = facts(detail(client, world["conflict"]))["has_sdk"]
    assert f["state"] == "CONFLICT" and f["value"] is None and "contradicts" in f["detail"]
    assert f["product_value"] is False                          # the product value did not win


# ------------------------------------------------------------------------------ list filters ---


def listed(client, **params):
    r = client.get("/api/robots", params={"limit": 100, **params})
    assert r.status_code == 200
    return {i["slug"]: i for i in r.json()["items"]}


def test_has_sdk_filter_is_any_variant(client, world):
    got = listed(client, has_sdk="true")
    assert {world[k] for k in ("mini", "proonly", "prodtrue")} <= set(got)
    for k in ("unknown", "novariant", "prodfalse", "conflict"):
        assert world[k] not in got, k
    assert got[world["mini"]]["scope_notes"] == []             # product-wide on all configurations
    assert got[world["prodtrue"]]["scope_notes"] == []
    note = got[world["proonly"]]["scope_notes"]
    assert [(n["property"], n["label"], n["configurations"]) for n in note] == [
        ("has_sdk", "Available on some configurations", ["pro"])]


def test_manipulation_and_ros_filters(client, world):
    m = listed(client, has_manipulation="true")
    assert world["mini"] in m and world["prodtrue"] in m
    assert world["prodfalse"] not in m and world["unknown"] not in m
    assert m[world["mini"]]["scope_notes"][0]["configurations"] == ["pro"]
    r = listed(client, ros_support="true")
    assert world["mini"] in r and world["prodtrue"] in r and world["proonly"] not in r


def test_a_false_filter_matches_only_known_absence(client, world):
    got = listed(client, has_sdk="false")
    assert world["prodfalse"] in got
    for k in ("mini", "proonly", "unknown", "conflict", "novariant", "prodtrue"):
        assert world[k] not in got, k


def test_filters_never_write_resolved_values_back(client, world):
    listed(client, has_sdk="true", ros_support="true", has_manipulation="true")
    assert tuple(core(world["proonly"])) == (None, None, None, None, None)


# ------------------------------------------------------------------------------ matching ---


def req(**kw):
    base = dict(use_case=None, country=None, payload_min_kg=None, operating_hours_day=None,
                manipulation_required=None, autonomy_required=None, budget_currency=None,
                budget_min=None, budget_max=None, required_by=None, preferred_transaction="UNKNOWN")
    return RequirementInput(**{**base, **kw})


def test_matching_inputs_are_conservative(world, database_url):
    with SessionLocal() as s:
        by = {c.slug: c for c in load_candidates(s, req())}
    mini, proonly = by[world["mini"]], by[world["proonly"]]
    assert (mini.has_sdk, mini.ros_support) == (True, True)       # UNIFORM_VARIANTS true
    assert mini.has_manipulation is None                           # PARTIAL: not a robot-wide true
    assert proonly.has_sdk is None                                 # PARTIAL: not satisfied
    assert by[world["prodtrue"]].has_sdk is True                   # PRODUCT_VALUE true
    assert by[world["prodfalse"]].has_sdk is False                 # known product-wide absence
    assert by[world["conflict"]].has_sdk is None                   # CONFLICT never satisfies
    assert by[world["unknown"]].has_sdk is None and by[world["novariant"]].has_sdk is None


def test_the_engine_does_not_treat_a_partial_robot_as_satisfying_a_hard_requirement(
        world, database_url):
    from app.services.matching.engine import match

    with SessionLocal() as s:
        cands = [c for c in load_candidates(s, req(manipulation_required=True))
                 if c.slug in {world["mini"], world["prodtrue"], world["prodfalse"]}]
    out = match(req(manipulation_required=True), cands)
    ranked = {m.slug for m in out.matches}
    assert world["prodfalse"] not in ranked                        # known absence excludes
    assert world["prodtrue"] in ranked                             # satisfies
    mini = [m for m in out.matches if m.slug == world["mini"]]
    if mini:                                                       # unknown, never a clean satisfy
        assert any("manipulation" in w.lower() or "unknown" in w.lower() for w in mini[0].warnings)


# ------------------------------------------------------------------------------ compare ---


def test_compare_exposes_the_scoped_state_not_a_collapsed_unknown(client, world):
    r = client.get("/api/robots/compare", params={"ids": f"{world['mini']},{world['prodtrue']}"})
    assert r.status_code == 200
    rows = {row["key"]: row for row in r.json()["rows"]}
    tele = rows["has_teleoperation"]
    assert tele["values"][world["mini"]] is None                  # no plain true/false invented
    assert tele["resolved"][world["mini"]]["state"] == "PARTIAL_VARIANTS"
    assert vals(tele["resolved"][world["mini"]]) == {"pro": True, "standard": None}
    sdk = rows["has_sdk"]
    assert sdk["values"][world["mini"]] is True
    assert sdk["resolved"][world["mini"]]["state"] == "UNIFORM_VARIANTS"
    assert sdk["resolved"][world["prodtrue"]]["state"] == "PRODUCT_VALUE"
    assert rows["height_cm"]["resolved"] is None                  # non-resolver rows unchanged
    ids = f"{world['mini']},{world['prodtrue']}"
    again = client.get("/api/robots/compare", params={"ids": ids})
    assert again.headers["x-app-cache"] == "HIT" and again.json() == r.json()  # survives the cache


# ------------------------------------------------------------------------------ agent tools ---


def test_the_agent_get_robot_carries_the_same_resolved_facts(world, database_url):
    with SessionLocal() as s:
        data = get_robot(s, world["mini"], keyring=KEYRING).data
    f = {x.property: x for x in data.resolved_facts}
    assert f["has_sdk"].state == "UNIFORM_VARIANTS" and f["has_sdk"].value is True
    assert f["has_teleoperation"].state == "PARTIAL_VARIANTS"
    assert {v.slug: v.value for v in f["has_manipulation"].variants} == {
        "pro": True, "standard": None}
    assert data.specs.has_sdk is None                              # the raw field is still NULL


def test_the_agent_search_uses_any_variant_and_discloses_partial_scope(world, database_url):
    with SessionLocal() as s:
        res = search_robots(s, limit=100, has_sdk=True)
    slugs = {i.slug for i in res.items}
    assert world["mini"] in slugs and world["proonly"] in slugs        # Mini SDK is discoverable
    assert world["unknown"] not in slugs and world["conflict"] not in slugs
    assert world["mini"] not in res.scope_notes                       # all configurations
    assert [n.label for n in res.scope_notes[world["proonly"]]] == [
        "Available on some configurations"]
    with SessionLocal() as s:
        both = search_robots(s, limit=100, has_manipulation=True)
    assert world["mini"] in {i.slug for i in both.items}
    assert both.scope_notes[world["mini"]][0].configurations == ["pro"]


# ------------------------------------------------------------------------------ performance ---


def test_resolution_is_three_queries_regardless_of_robot_and_property_count(world, database_url):
    statements: list[str] = []

    def count(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    with SessionLocal() as s:
        event.listen(s.get_bind(), "before_cursor_execute", count)
        try:
            out = load_resolutions(s)
        finally:
            event.remove(s.get_bind(), "before_cursor_execute", count)
    assert len(out) >= 7 and len(statements) == 3, statements


# ------------------------------------------------------------------------------ one resolver ---


def test_no_consumer_carries_its_own_projection_logic():
    """The registered tokens live in exactly one place. A second substring search in an API route,
    SQL, agent code or the web layer would be a second resolver."""
    # a registered token appearing as a QUOTED literal is a hard-coded match; property names such
    # as `has_teleoperation` are not tokens
    tokens = [r.token for r in fr.PROJECTION_REGISTRY]
    quoted = [re.compile(r"""["'`]""" + re.escape(t) + r"""["'`]""") for t in tokens]
    roots = [REPO / "apps" / "api" / "app", REPO / "apps" / "web" / "app",
             REPO / "apps" / "web" / "components", REPO / "apps" / "web" / "lib"]
    offenders = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or "discovery" in path.parts:
                continue
            if path.name == "fact_resolution.py":
                continue
            body = path.read_text(encoding="utf-8", errors="ignore")
            offenders += [f"{path.relative_to(REPO)}: {t}"
                          for t, rx in zip(tokens, quoted, strict=True) if rx.search(body)]
    assert offenders == [], offenders
