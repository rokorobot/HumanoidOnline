"""HO-DATA Fast Lane FL-1: research evidence -> version-2 promotion manifest (core columns).

SYNTHETIC evidence only (synthetic.example URLs, made-up figures), applied to a temp copy of the
repository's catalogue. The DB-backed tests reuse promotion_support's throwaway database.
"""
from __future__ import annotations

import io
import json
import re
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import psycopg
import pytest
from promotion_support import (  # noqa: F401
    PEER,
    ROBOT,
    TODAY,
    copy_catalogue,
    plain,
    run_import,
    template_db,
    world,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.cli import promotion as cli
from app.services.discovery import promotion_manifest as pm
from app.services.discovery import promotion_research as research

DIGIT = PEER                                # agility-digit; copy_catalogue clears its DoF
EDITIONS = {DIGIT: "Digit", ROBOT: "G1"}
FINGERPRINTS = {DIGIT: "synthetic-fp-digit", ROBOT: "synthetic-fp-g1",
                "4ne1-mini": "synthetic-fp-mini"}
FIXTURE_PAGE_HASH = "abc123def4567890abc123def4567890abc123def4567890abc123def4567890"


def record(**over) -> dict:
    rec = {
        "robot": DIGIT, "edition": "Digit", "edition_scope": "ALL_EDITIONS",
        "field": "degrees_of_freedom", "stated_value": "28", "stated_unit": None,
        "verbatim": "Degrees of freedom: 28",
        "excerpt": "SYNTHETIC datasheet. Degrees of freedom: 28. Not a real figure.",
        "qualifiers": [], "source_url": "https://synthetic.example/digit/datasheet.pdf",
        "source_title": "Synthetic Maker datasheet", "source_class": "MANUFACTURER",
        "content_sha256": "ab" * 32, "retrieved_at": "2026-10-18T09:00:00Z",
        "retrieval_actor": "Claude (test)", "retrieval_tool": "fixture",
        "initiated_by": "Test Owner", "work_order": "HO-DATA-SR-01",
        "scope": "synthetic test batch", "locator": "page 1, specification table",
    }
    rec.update(over)
    return rec


def g1_speed(**over) -> dict:
    fields = dict(robot=ROBOT, edition="G1", field="walk_speed_ms", stated_value="7.2",
                  stated_unit="km/h", verbatim="Max walking speed 7.2 km/h",
                  excerpt="SYNTHETIC page. Max walking speed 7.2 km/h.",
                  source_url="https://synthetic.example/g1", content_sha256="cd" * 32,
                  measurement_condition=research.NOT_STATED)
    return record(**{**fields, **over})


@pytest.fixture
def catalogue(tmp_path) -> Path:
    return copy_catalogue(tmp_path / "catalogue")


def propose(records, catalogue, **kw) -> dict:
    kw.setdefault("edition_map", EDITIONS)
    if "fingerprints" not in kw:
        kw["fingerprints"] = {s: FINGERPRINTS[s] for s in {r["robot"] for r in records}}
    return research.propose_research(None, records, catalogue_dir=catalogue,
                                     base_commit="synthetic-base", promotion_id="research-test",
                                     today=TODAY, **kw)


def only(manifest: dict) -> dict:
    (item,) = manifest["items"]
    return item


def robot_json(catalogue: Path, slug: str) -> dict:
    return json.loads(pm.robot_path(catalogue, slug).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ routine additions ------
def test_core_null_to_value_is_routine_and_edits_only_its_lines(catalogue, tmp_path):
    base = tmp_path / "base"
    shutil.copytree(catalogue, base)
    before = {s: robot_json(catalogue, s) for s in (DIGIT, ROBOT)}
    manifest = propose([record(), g1_speed()], catalogue)

    assert manifest["manifest_version"] == 2 and pm.manifest_problems(manifest) == []
    assert manifest["scope"] == {"robots": [DIGIT, ROBOT], "allowed_tables": ["robot"],
                                 "edition_map": EDITIONS}
    dof, speed = manifest["items"]
    assert [i["classification"] for i in manifest["items"]] == [pm.ROUTINE, pm.ROUTINE]
    assert (dof["proposed_value"], dof["existing_value"], dof["conversion"]) == (28, None, "none")
    assert speed["proposed_value"] == 2.0 and speed["conversion"] == "7.2 km/h = 2.0 m/s"
    for item in manifest["items"]:
        assert item["evidence_class"] == "AGENT_ASSISTED_RESEARCH"
        assert item["verification"] == "NOT_HUMAN_VERIFIED"
        assert item["observation"] == {"kind": "EVIDENCE_PACKAGE", "fetched_page_id": None}
        assert item["retrieval"]["work_order"] == "HO-DATA-SR-01"
    assert "no measurement condition is stated" in speed["caveat"]
    assert "7.2 km/h" in speed["caveat"] and "unit conversion" in speed["caveat"]
    # both robots' notes say the field was left NULL / unconfirmed: reported, not rewritten
    assert {n.split(":")[0] for n in manifest["review_notes"]} == {DIGIT, ROBOT}

    assert pm.apply_to_catalogue(manifest, catalogue) == [DIGIT, ROBOT]
    for slug, field, value in ((DIGIT, "degrees_of_freedom", 28),
                               (ROBOT, "walk_speed_ms", 2.0)):
        after = robot_json(catalogue, slug)
        assert after["specs"] == {**before[slug]["specs"], field: value}
        assert after["spec_caveats"] == (before[slug].get("spec_caveats") or []) + [
            {"field": field, "text": next(i["caveat"] for i in manifest["items"]
                                          if i["robot"] == slug)}]
        assert after["specs_note"].startswith(before[slug]["specs_note"])
        assert ("RETRIEVAL: AGENT_ASSISTED_RESEARCH (docs/26)" in after["specs_note"]
                and after["specs_note"].endswith("Not human-verified."))
        untouched = {k for k in before[slug] if k not in ("specs", "spec_caveats", "specs_note")}
        assert {k: after[k] for k in untouched} == {k: before[slug][k] for k in untouched}
    changed = [p.relative_to(catalogue).as_posix() for p in catalogue.rglob("*")
               if p.is_file() and p.read_bytes() != (base / p.relative_to(catalogue)).read_bytes()]
    assert sorted(changed) == [f"robots/{DIGIT}.json", f"robots/{ROBOT}.json"]
    assert pm.verify(manifest, base_catalogue_dir=base, head_catalogue_dir=catalogue).ok
    assert pm.derive_preflight_manifest(manifest)["expected"] == [
        {"table": "robot", "kind": "CHANGED", "match": {"slug": s}, "count": 1}
        for s in (DIGIT, ROBOT)]
    assert pm.expected_added_keys(manifest) == set()


def test_exact_conversions_and_approximately(catalogue):
    item = only(propose([record(stated_value="1.75", stated_unit="m", field="height_cm",
                                verbatim="Height 1.75 m", excerpt="Height 1.75 m",
                                robot=ROBOT, edition="G1")], catalogue))
    # unitree-g1 already holds 132 cm: a change, never routine
    assert item["classification"] == pm.REVIEW_REQUIRED
    item = only(propose([record(field="runtime_minutes", stated_value="2", stated_unit="h",
                                verbatim="about 2 h", excerpt="Battery: about 2 h walking",
                                qualifiers=["approximately"],
                                measurement_condition="walking")], catalogue))
    assert item["classification"] == pm.ROUTINE, item["reasons"]
    assert item["proposed_value"] == 120 and item["conversion"] == "2 h = 120 min"
    assert "approximate" in item["caveat"] and "walking" in item["caveat"]


def test_stale_note_is_replaced_with_the_owner_approved_wording(catalogue):
    path = pm.robot_path(catalogue, DIGIT)
    doc = robot_json(catalogue, DIGIT)
    path.write_text(path.read_text(encoding="utf-8").replace(
        json.dumps(doc["specs_note"], ensure_ascii=False),
        json.dumps("Physical figures pending. " + research.STALE_NOTE)), encoding="utf-8")
    manifest = propose([record()], catalogue)
    pm.apply_to_catalogue(manifest, catalogue)
    note = robot_json(catalogue, DIGIT)["specs_note"]
    assert research.STALE_NOTE not in note
    assert note.startswith("Physical figures pending. Selected specifications retrieved from "
                           "first-party manufacturer documentation on 2026-10-18 under "
                           "HO-DATA-SR-01. Evidence status: AGENT_ASSISTED_RESEARCH; "
                           "not human-verified.")


def test_regeneration_is_deterministic_and_the_edit_idempotent(catalogue):
    records = [g1_speed(), record()]
    first, second = propose(records, catalogue), propose(list(reversed(records)), catalogue)
    assert first == second and first["digest"] == pm.compute_digest(first)
    assert pm.render_review(first) == pm.render_review(second)
    assert pm.apply_to_catalogue(first, catalogue) == [DIGIT, ROBOT]
    snapshot = {s: pm.robot_path(catalogue, s).read_bytes() for s in (DIGIT, ROBOT)}
    assert pm.apply_to_catalogue(first, catalogue) == []
    assert {s: pm.robot_path(catalogue, s).read_bytes() for s in (DIGIT, ROBOT)} == snapshot


# ------------------------------------------------------------------------ rejections ------
def test_conflicting_statements_are_never_routine(catalogue):
    manifest = propose([g1_speed(), g1_speed(stated_value="2.5", stated_unit="m/s",
                                             verbatim="speed 2.5 m/s",
                                             excerpt="speed 2.5 m/s")], catalogue)
    assert {(i["classification"], i["conflict"]) for i in manifest["items"]} == {
        (pm.REVIEW_REQUIRED, "DISPUTED")}
    assert pm.manifest_problems(manifest)
    with pytest.raises(pm.CatalogueEditRefused):
        pm.apply_to_catalogue(manifest, catalogue)
    item = only(propose([record(conflicting_statements=["press release: 30 DoF"])], catalogue))
    assert item["conflict"] == "DISPUTED" and item["classification"] == pm.REVIEW_REQUIRED
    with pytest.raises(pm.ProposalRefused, match="two records"):
        propose([record(), record(locator="page 2")], catalogue)


@pytest.mark.parametrize("over, fragment", [
    ({"edition": "Digit V4"}, "edition mapping says 'Digit'"),
    ({"edition_scope": "SOME_EDITIONS"}, "edition_scope"),
])
def test_mismatched_edition_needs_review(catalogue, over, fragment):
    item = only(propose([record(**over)], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED
    assert any(fragment in r for r in item["reasons"]), item["reasons"]


def test_edition_scoped_value_on_a_multi_edition_robot_needs_review(catalogue):
    mini = robot_json(catalogue, "4ne1-mini")
    field = next(f for f in research.CORE_FIELDS if mini["specs"].get(f) is None)
    rec = record(robot="4ne1-mini", edition="4NE1 Mini", edition_scope="THIS_EDITION",
                 field=field, stated_value="7",
                 stated_unit=next(iter(research.CORE_FIELDS[field].conversions)),
                 verbatim="value 7", excerpt="value 7", measurement_condition="NOT_STATED")
    item = only(propose([rec], catalogue, edition_map={"4ne1-mini": "4NE1 Mini"}))
    assert any("product-level" in r for r in item["reasons"]), item["reasons"]


def test_unknown_robot_and_missing_mapping(catalogue):
    with pytest.raises(pm.ProposalRefused, match="never creates a robot"):
        propose([record(robot="not-a-robot")], catalogue, fingerprints={})
    item = only(propose([record()], catalogue, edition_map={}))
    assert any("no explicit edition mapping" in r for r in item["reasons"])


def test_known_values_are_never_overwritten(catalogue):
    height = dict(robot=ROBOT, edition="G1", field="height_cm", stated_unit="cm",
                  verbatim="Height 140 cm", excerpt="Height 140 cm")
    item = only(propose([record(stated_value="140", **height)], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED and item["existing_value"] == 132
    assert any("change, not an addition" in r for r in item["reasons"])
    with pytest.raises(pm.ProposalRefused, match="already has exactly this value"):
        propose([record(stated_value="132", **{**height, "verbatim": "Height 132 cm",
                                               "excerpt": "Height 132 cm"})], catalogue)
    # an existing caveat for the field is known state too
    path = pm.robot_path(catalogue, DIGIT)
    doc = robot_json(catalogue, DIGIT)
    doc["spec_caveats"] = [{"field": "degrees_of_freedom", "text": "not stated by Agility"}]
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    item = only(propose([record()], catalogue))
    assert any("existing spec caveat" in r for r in item["reasons"])


@pytest.mark.parametrize("over, fragment", [
    ({"stated_value": "28-30", "verbatim": "DoF 28-30", "excerpt": "DoF 28-30"},
     "not a plain number"),
    ({"field": "weight_kg", "stated_value": "150", "stated_unit": "lb",
      "verbatim": "150 lb", "excerpt": "150 lb"}, "no exact conversion"),
    ({"field": "walk_speed_ms", "stated_value": "5", "stated_unit": "km/h",
      "verbatim": "5 km/h", "excerpt": "5 km/h", "measurement_condition": "flat floor"},
     "not exact at the column's precision"),
    ({"field": "payload_kg", "stated_value": "5", "stated_unit": "kg", "qualifiers": ["per arm"],
      "verbatim": "5 kg per arm", "excerpt": "5 kg per arm"}, "per arm"),
    ({"field": "runtime_minutes", "stated_value": "90", "stated_unit": "min",
      "verbatim": "90 min", "excerpt": "90 min"}, "measurement condition"),
    ({"verbatim": "Degrees of freedom: 30"}, "not part of the excerpt"),
    ({"verbatim": "Degrees of freedom", "excerpt": "Degrees of freedom: 28"},
     "stated value is not part"),
    ({"content_sha256": None}, "missing evidence: content_sha256"),
    ({"source_class": "DISTRIBUTOR"}, "not MANUFACTURER"),
    ({"retrieved_at": "2026-08-01"}, "days old"),
    ({"field": "mobility"}, "not one of the Fast Lane core columns"),
    ({"field": "hand_type"}, "not one of the Fast Lane core columns"),
    ({"field": "autonomy"}, "not one of the Fast Lane core columns"),
])
def test_unsupported_derivations_and_missing_evidence_need_review(catalogue, over, fragment):
    item = only(propose([record(**over)], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED
    assert any(fragment in r for r in item["reasons"]), item["reasons"]


def test_restricted_fields_and_unknown_values(catalogue):
    item = only(propose([record(field="price_usd")], catalogue))
    assert item["classification"] == pm.RESTRICTED
    assert pm.manifest_problems(propose([record(field="price_usd")], catalogue))
    for token in ("—", "n/a", None):
        with pytest.raises(pm.ProposalRefused, match="UNKNOWN values are never promoted"):
            propose([record(stated_value=token)], catalogue)


def test_verify_rejects_extra_edits_and_tampering(catalogue, tmp_path):
    base = tmp_path / "base"
    shutil.copytree(catalogue, base)
    manifest = propose([record()], catalogue)
    pm.apply_to_catalogue(manifest, catalogue)
    path = pm.robot_path(catalogue, DIGIT)
    path.write_text(path.read_text(encoding="utf-8").replace(
        '"runtime_minutes": null', '"runtime_minutes": 60'), encoding="utf-8")
    result = pm.verify(manifest, base_catalogue_dir=base, head_catalogue_dir=catalogue)
    assert not result.ok and any(DIGIT in r for r in result.reasons)
    tampered = {**manifest, "items": [{**manifest["items"][0], "proposed_value": 29}]}
    assert any("digest" in r for r in pm.manifest_problems(tampered))
    human = pm.seal({**manifest, "items": [{**manifest["items"][0],
                                            "verification": "VERIFIED"}]})
    assert any("not human-verified" in r for r in pm.manifest_problems(human))


# ------------------------------------------------------------------ database-backed ------
def _session_propose(w, records, **kw) -> dict:
    engine = create_engine(w.owner_url.replace("postgresql://", "postgresql+psycopg://", 1),
                           connect_args={"options": "-csearch_path=humanoid,public"})
    try:
        with Session(engine) as session:
            return research.propose_research(
                session, records, catalogue_dir=w.base, base_commit="synthetic-base",
                promotion_id="research-test", today=TODAY, edition_map=EDITIONS, **kw)
    finally:
        engine.dispose()


def _snapshot(url: str) -> dict:
    pf = pm.load_db_tool("import_preflight")
    with psycopg.connect(plain(url)) as conn:
        conn.read_only = True
        return pf.snapshot(conn, pm.excluded_tables())


def test_import_changes_only_the_two_robot_rows(world):  # noqa: F811
    pf = pm.load_db_tool("import_preflight")
    manifest = _session_propose(world, [record(), g1_speed(content_sha256=FIXTURE_PAGE_HASH)])
    assert manifest["base"]["robot_fingerprints"] == pm.fingerprints_from_url(
        world.owner_url, [DIGIT, ROBOT])
    assert manifest["items"][1]["observation"]["kind"] == "FETCHED_PAGE"
    assert _session_propose(world, [g1_speed(content_sha256=FIXTURE_PAGE_HASH), record()]
                            ) == manifest

    pm.apply_to_catalogue(manifest, world.head)
    before = _snapshot(world.owner_url)
    run_import(world.owner_url, world.head, robots=(ROBOT, DIGIT))
    after = _snapshot(world.owner_url)
    report = pf.classify(pf.diff(before, after), pm.derive_preflight_manifest(manifest))
    assert report["ok"], report
    assert report["business_changes"] == 2, report
    changes = [c for c in pf.diff(before, after) if c.gated]
    assert {(c.table, c.kind, c.fields["slug"]) for c in changes} == {
        ("robot", "CHANGED", DIGIT), ("robot", "CHANGED", ROBOT)}
    assert {c.fields["slug"]: set(c.detail) for c in changes} == {
        DIGIT: {"degrees_of_freedom", "spec_caveats"}, ROBOT: {"walk_speed_ms", "spec_caveats"}}
    run_import(world.owner_url, world.head, robots=(ROBOT, DIGIT))
    assert [c for c in pf.diff(after, _snapshot(world.owner_url)) if c.gated] == []


def test_existing_extended_spec_path_is_unchanged(world):  # noqa: F811
    manifest = world.propose()
    assert manifest["manifest_version"] == 1
    assert only(manifest)["classification"] == pm.ROUTINE
    assert world.propose() == manifest


def test_executor_refuses_a_version_2_manifest(world):  # noqa: F811
    manifest = _session_propose(world, [record()])
    pm.apply_to_catalogue(manifest, world.head)
    before = pm.fingerprints_from_url(world.owner_url, [DIGIT])
    receipt = world.execute(manifest)
    assert receipt["outcome"] == "REFUSED:manifest", receipt
    assert "only version-1" in receipt["reason"]
    assert pm.fingerprints_from_url(world.owner_url, [DIGIT]) == before
    assert world.branch_dbs() == []


def test_cli_propose_research_dry_run_and_preflight(world, tmp_path, monkeypatch):  # noqa: F811
    package = tmp_path / "evidence.json"
    package.write_text(json.dumps({"records": [record()]}), encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setenv("DATABASE_URL", world.owner_url)
    code = cli.main(["propose", "--research", str(package), "--catalogue-dir", str(world.base),
                     "--edition-map", f"{DIGIT}=Digit", "--base-commit", "synthetic-base",
                     "--promotion-id", "research-cli", "--today", TODAY.isoformat(),
                     "--dry-run-output", str(out)])
    assert code == 0
    manifest = json.loads((out / "research-cli.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 2
    assert (out / "research-cli.md").read_text(encoding="utf-8") == pm.render_review(manifest)
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert cli.main(["render", "--manifest", str(out / "research-cli.json"),
                         "--preflight"]) == 0
    assert json.loads(buf.getvalue())["expected"] == [
        {"table": "robot", "kind": "CHANGED", "match": {"slug": DIGIT}, "count": 1}]
    assert cli.main(["propose", "--research", str(package), "--items", "x.json"]) == 2


# ----------------------------------------- FL-1 extension: more numerics and boolean flags ----
def numeric(field, stated, unit, verbatim, **over) -> dict:
    return record(field=field, stated_value=stated, stated_unit=unit, verbatim=verbatim,
                  excerpt=f"SYNTHETIC page. {verbatim}.", **over)


def flag(field="ros_support", verbatim="ROS support: Yes", **over) -> dict:
    fields = dict(field=field, stated_value="Yes", stated_unit=None, verbatim=verbatim,
                  excerpt=f"SYNTHETIC page. {verbatim}.", asserts=True)
    return record(**{**fields, **over})


def set_spec(catalogue: Path, slug: str, field: str, value) -> None:
    path = pm.robot_path(catalogue, slug)
    doc = robot_json(catalogue, slug)
    doc["specs"][field] = value
    if value is None:
        doc["spec_caveats"] = [c for c in doc.get("spec_caveats") or [] if c["field"] != field]
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def test_battery_wh_routine_with_exact_kwh_conversion(catalogue):
    item = only(propose([numeric("battery_wh", "842", "Wh", "Battery capacity: 842 Wh")],
                        catalogue))
    assert item["classification"] == pm.ROUTINE, item["reasons"]
    assert (item["proposed_value"], item["unit"], item["conversion"]) == (842.0, "Wh", "none")
    assert item["display"] == "Robot detail: 'Battery capacity: 842.0 Wh', with caveat"
    item = only(propose([numeric("battery_wh", "0.8421", "kWh", "Battery 0.8421 kWh")],
                        catalogue))
    assert item["classification"] == pm.ROUTINE, item["reasons"]
    assert item["proposed_value"] == 842.1 and item["conversion"] == "0.8421 kWh = 842.1 Wh"
    assert "unit conversion" in item["caveat"]
    # a figure that is not exact at NUMERIC(8,1) is rounding: review
    item = only(propose([numeric("battery_wh", "0.84215", "kWh", "Battery 0.84215 kWh")],
                        catalogue))
    assert any("not exact at the column's precision" in r for r in item["reasons"])


@pytest.mark.parametrize("unit, verbatim", [("Ah", "Battery 20 Ah"), ("V", "Battery 48 V"),
                                            (None, "Battery 842")])
def test_battery_not_in_wh_or_kwh_has_no_exact_conversion(catalogue, unit, verbatim):
    item = only(propose([numeric("battery_wh", verbatim.split()[1], unit, verbatim)],
                        catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED and item["proposed_value"] is None
    assert any("DEC-09" in r for r in item["reasons"]), item["reasons"]


@pytest.mark.parametrize("field, verbatim", [
    # the owner closed literal "Arm Span" / "Arm Reach" labels (HO-DATA-30 close-out: Unitree
    # "Arm Span | About 0.45M", GR-2 "Arm Reach 1520 mm"), so no label is ever routine
    ("arm_span_cm", "Arm span: 180 cm"),
    ("arm_span_cm", "Wingspan 180 cm"),
    ("arm_span_cm", "Width 180 cm"),
    ("reach_cm", "Arm reach: 180 cm"),
    ("reach_cm", "Workspace reach 180 cm"),
    ("reach_cm", "Arm length 180 cm"),
])
def test_dec_10_span_and_reach_are_always_review(catalogue, field, verbatim):
    item = only(propose([numeric(field, "180", "cm", verbatim)], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED
    assert any("DEC-10" in r for r in item["reasons"]), item["reasons"]
    assert item["proposed_value"] == 180.0 and item["unit"] == "cm"
    item = only(propose([numeric(field, "1.8", "m", verbatim.replace("180 cm", "1.8 m"))],
                        catalogue))
    assert (item["proposed_value"], item["conversion"]) == (180.0, "1.8 m = 180.0 cm")
    assert item["classification"] == pm.REVIEW_REQUIRED


def test_dec_07_hand_dof_needs_a_standard_end_effector(catalogue):
    rec = numeric("hand_dof", "6", None, "Hand degrees of freedom: 6")
    item = only(propose([rec], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED
    assert any("DEC-07" in r for r in item["reasons"]), item["reasons"]
    for other in ("DEXTEROUS", None, ""):
        item = only(propose([{**rec, "end_effector": other}], catalogue))
        assert any("DEC-07" in r for r in item["reasons"])
    item = only(propose([{**rec, "end_effector": "STANDARD"}], catalogue))
    assert item["classification"] == pm.ROUTINE, item["reasons"]
    assert item["proposed_value"] == 6 and item["unit"] is None
    assert item["display"] == "Robot detail: 'Hand degrees of freedom: 6', with caveat"


def test_boolean_flag_routine_true_edits_only_its_lines(catalogue, tmp_path):
    base = tmp_path / "base"
    shutil.copytree(catalogue, base)
    manifest = propose([flag(), numeric("battery_wh", "842", "Wh", "Battery capacity: 842 Wh")],
                       catalogue)
    battery, ros = manifest["items"]
    assert (ros["definition"], ros["classification"]) == ("ros_support", pm.ROUTINE), ros
    assert ros["proposed_value"] is True and ros["existing_value"] is None
    assert ros["unit"] is None and ros["conversion"] == "none"
    assert ros["display"] == "Robot detail: 'ROS support: yes', with caveat"
    assert ros["caveat"] == ("Synthetic Maker datasheet states 'ROS support: Yes'; evidence "
                             "AGENT_ASSISTED_RESEARCH, not human-verified.")
    assert pm.manifest_problems(manifest) == []
    review = pm.render_review(manifest)
    assert "`ros_support` (Digit, ALL_EDITIONS): UNKNOWN -> yes" in review
    assert "`battery_wh` (Digit, ALL_EDITIONS): UNKNOWN -> 842.0 Wh" in review

    assert pm.apply_to_catalogue(manifest, catalogue) == [DIGIT]
    text = pm.robot_path(catalogue, DIGIT).read_text(encoding="utf-8")
    assert re.search(r'^    "ros_support": true,?$', text, re.MULTILINE)
    assert '"battery_wh": 842.0' in text
    after, before = robot_json(catalogue, DIGIT), robot_json(base, DIGIT)
    assert after["specs"] == {**before["specs"], "ros_support": True, "battery_wh": 842.0}
    assert "battery capacity, ROS support from Synthetic Maker datasheet" in after["specs_note"]
    changed = [p.relative_to(catalogue).as_posix() for p in catalogue.rglob("*")
               if p.is_file() and p.read_bytes() != (base / p.relative_to(catalogue)).read_bytes()]
    assert changed == [f"robots/{DIGIT}.json"]
    assert pm.verify(manifest, base_catalogue_dir=base, head_catalogue_dir=catalogue).ok
    snapshot = pm.robot_path(catalogue, DIGIT).read_bytes()
    assert pm.apply_to_catalogue(manifest, catalogue) == []
    assert pm.robot_path(catalogue, DIGIT).read_bytes() == snapshot


@pytest.mark.parametrize("over", [
    {"asserts": False},
    {"asserts": False, "stated_value": "Yes"},
    {"stated_value": "No", "verbatim": "ROS support: No", "excerpt": "ROS support: No"},
    {"stated_value": "Not supported", "verbatim": "ROS support: Not supported",
     "excerpt": "ROS support: Not supported"},
])
def test_explicit_negatives_are_never_written(catalogue, over):
    manifest = propose([flag(**over)], catalogue)
    item = only(manifest)
    assert item["classification"] == pm.REVIEW_REQUIRED and item["proposed_value"] is None
    assert item["caveat"] is None and item["display"] == ""
    assert research.NEGATIVE_CHAIN in item["reasons"]
    assert "UNKNOWN -> (no value proposed)" in pm.render_review(manifest)
    assert pm.manifest_problems(manifest)
    with pytest.raises(pm.CatalogueEditRefused):
        pm.apply_to_catalogue(manifest, catalogue)


def test_a_flag_without_asserts_true_or_with_a_qualifier_needs_review(catalogue):
    rec = flag()
    del rec["asserts"]
    item = only(propose([rec], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED and item["proposed_value"] is True
    assert any('"asserts": true' in r for r in item["reasons"]), item["reasons"]
    item = only(propose([flag(asserts="yes")], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED
    item = only(propose([flag(qualifiers=["approximately"])], catalogue))
    assert any("'approximately' qualifier on a flag" in r for r in item["reasons"])
    assert item["classification"] == pm.REVIEW_REQUIRED


def test_existing_true_is_refused_and_existing_false_is_a_change(catalogue):
    set_spec(catalogue, DIGIT, "has_api", True)
    with pytest.raises(pm.ProposalRefused, match="already has exactly this value"):
        propose([flag("has_api", "API available: Yes")], catalogue)
    set_spec(catalogue, DIGIT, "has_sdk", False)
    before = pm.robot_path(catalogue, DIGIT).read_bytes()
    manifest = propose([flag("has_sdk", "SDK available: Yes")], catalogue)
    item = only(manifest)
    assert item["classification"] == pm.REVIEW_REQUIRED and item["existing_value"] is False
    assert any("change, not an addition" in r for r in item["reasons"]), item["reasons"]
    with pytest.raises(pm.CatalogueEditRefused):
        pm.apply_to_catalogue(manifest, catalogue)
    assert pm.robot_path(catalogue, DIGIT).read_bytes() == before
    # a negative against an existing true is a change for review too, never a refusal
    item = only(propose([flag("has_api", "API available: No", asserts=False)], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED and item["existing_value"] is True
    # and the edit itself never overwrites a known flag, even from a hand-built item
    forged = [{**item, "proposed_value": True, "caveat": "x", "definition": "has_sdk"}]
    with pytest.raises(pm.CatalogueEditRefused, match="already holds"):
        research.edit_robot_core(pm.robot_path(catalogue, DIGIT).read_text(encoding="utf-8"),
                                 forged)


def test_developer_edition_is_always_review(catalogue):
    item = only(propose([flag("developer_edition", "Developer edition: Yes")], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED and item["proposed_value"] is True
    assert any("DEC-02" in r for r in item["reasons"]), item["reasons"]


def test_dec_08_language_ui_needs_spoken_conversation(catalogue):
    verbatim = "Voice conversation: Yes"
    item = only(propose([flag("has_language_ui", verbatim)], catalogue))
    assert item["classification"] == pm.REVIEW_REQUIRED
    assert any("DEC-08" in r for r in item["reasons"]), item["reasons"]
    item = only(propose([flag("has_language_ui", verbatim, spoken_conversation=False)],
                        catalogue))
    assert any("DEC-08" in r for r in item["reasons"])
    item = only(propose([flag("has_language_ui", verbatim, spoken_conversation=True)],
                        catalogue))
    assert item["classification"] == pm.ROUTINE, item["reasons"]
    assert item["display"] == "Robot detail: 'Language UI: yes', with caveat"


@pytest.mark.parametrize("field", ["has_vision", "has_sdk", "has_api", "ros_support",
                                   "has_manipulation", "has_teleoperation",
                                   "simulation_support"])
def test_every_plain_flag_is_routine_when_asserted(catalogue, field):
    if field in ("has_manipulation", "has_teleoperation", "simulation_support"):
        set_spec(catalogue, DIGIT, field, None)
    item = only(propose([flag(field, f"{field}: Yes")], catalogue))
    assert item["classification"] == pm.ROUTINE, item["reasons"]
    assert item["proposed_value"] is True


def test_import_of_a_flag_and_battery_changes_only_robot_rows(world):  # noqa: F811
    pf = pm.load_db_tool("import_preflight")
    manifest = _session_propose(world, [
        flag("has_vision", "Vision: Yes"),
        numeric("battery_wh", "842", "Wh", "Battery capacity: 842 Wh", robot=ROBOT,
                edition="G1", content_sha256="cd" * 32)])
    assert [i["classification"] for i in manifest["items"]] == [pm.ROUTINE, pm.ROUTINE]
    pm.apply_to_catalogue(manifest, world.head)
    before = _snapshot(world.owner_url)
    run_import(world.owner_url, world.head, robots=(ROBOT, DIGIT))
    after = _snapshot(world.owner_url)
    report = pf.classify(pf.diff(before, after), pm.derive_preflight_manifest(manifest))
    assert report["ok"], report
    assert report["business_changes"] == 2, report
    changes = [c for c in pf.diff(before, after) if c.gated]
    assert {(c.table, c.kind, c.fields["slug"]) for c in changes} == {
        ("robot", "CHANGED", DIGIT), ("robot", "CHANGED", ROBOT)}
    assert {c.fields["slug"]: set(c.detail) for c in changes} == {
        DIGIT: {"has_vision", "spec_caveats"}, ROBOT: {"battery_wh", "spec_caveats"}}
    run_import(world.owner_url, world.head, robots=(ROBOT, DIGIT))
    assert [c for c in pf.diff(after, _snapshot(world.owner_url)) if c.gated] == []
