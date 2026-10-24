"""HO-DATA Fast Lane FL-1: research evidence -> version-2 promotion manifest (core columns).

SYNTHETIC evidence only (synthetic.example URLs, made-up figures), applied to a temp copy of the
repository's catalogue. The DB-backed tests reuse promotion_support's throwaway database.
"""
from __future__ import annotations

import io
import json
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import psycopg
import pytest
from promotion_support import (  # noqa: F401
    PEER,
    REAL_CATALOGUE,
    ROBOT,
    TODAY,
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

DIGIT = PEER                                # agility-digit: degrees_of_freedom is null
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
    target = tmp_path / "catalogue"
    shutil.copytree(REAL_CATALOGUE, target)
    return target


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
    ({"field": "arm_span_cm"}, "not one of the Fast Lane core columns"),
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
