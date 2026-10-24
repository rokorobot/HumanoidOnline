"""Catalogue promotion manifest (PR B): propose, classify, edit, derive, verify.

SYNTHETIC data only: a throwaway database with one fake discovery claim (see
promotion_support.py), and the repository's catalogue JSON copied to a temp dir.
"""
from __future__ import annotations

import difflib
import json
from datetime import timedelta

import pytest
from promotion_support import KEY, ROBOT, TODAY, VALUE, template_db, world  # noqa: F401

from app.cli import promotion as cli
from app.services.discovery import promotion_manifest as pm

# --------------------------------------------------------------------------- propose ------


def test_routine_addition_builds_a_complete_manifest(world):  # noqa: F811
    m = world.propose()
    item = m["items"][0]
    assert item["classification"] == pm.ROUTINE and item["reasons"] == []
    assert item["existing_value"] is None and item["conflict"] == "NONE"
    assert item["proposed_value"] == VALUE and item["definition"] == KEY
    assert item["source_url"] == "https://synthetic.example/g1"
    assert item["observed_at"] == "2026-10-18" and len(item["content_hash"]) == 64
    assert item["evidence_class"] == "MANUFACTURER" and item["edition_scope"] == "THIS_EDITION"
    assert item["expected_change"] == {"table": "specification", "kind": "ADDED",
                                       "match": {"robot": ROBOT, "definition": KEY}}
    assert set(m["base"]["robot_fingerprints"]) == {ROBOT}
    assert m["restricted_impact"] == dict.fromkeys(pm.RESTRICTED_IMPACT_KEYS, 0)
    assert m["digest"] == pm.compute_digest(m)
    assert pm.derive_preflight_manifest(m)["expected"] == [{**item["expected_change"], "count": 1}]
    review = pm.render_review(m)
    assert VALUE in review and "ROUTINE" in review and item["claim_id"] in review
    assert "no changes to price, availability, publication, images or unrelated robots" in review
    assert "APPROVE (merge) / REJECT / DEFER (close PR with label)" in review


def test_digest_covers_everything_but_itself(world):  # noqa: F811
    m = world.propose()
    assert pm.compute_digest({**m, "digest": "ignored"}) == m["digest"]
    tampered = json.loads(json.dumps(m))
    tampered["items"][0]["proposed_value"] = "something else"
    assert pm.compute_digest(tampered) != m["digest"]
    reordered = dict(reversed(list(m.items())))
    assert pm.compute_digest(reordered) == m["digest"]      # canonical: key order is irrelevant


def test_fingerprint_is_stable_and_tracks_the_robot(world):  # noqa: F811
    before = world.fingerprints()
    assert world.fingerprints() == before
    world.sql("UPDATE robot SET summary = 'changed' WHERE slug = %s", (ROBOT,))
    assert world.fingerprints() != before


@pytest.mark.parametrize("raw", ["/", "-", "", "   ", "N/A", "unknown", "—", None])
def test_unknown_values_are_refused_never_defaulted(world, raw):  # noqa: F811
    with pytest.raises(pm.ProposalRefused, match="UNKNOWN"):
        world.propose([world.item(proposed_value=raw)])


# ------------------------------------------------------- REVIEW_REQUIRED / RESTRICTED ------


def _reasons(manifest):
    item = manifest["items"][0]
    return item["classification"], " | ".join(item["reasons"])


def test_existing_differing_value_is_a_change_not_an_addition(world):  # noqa: F811
    path = world.base / "robots" / f"{ROBOT}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["extended_specs"].append({"key": KEY, "value": "older text", "source_label": "x",
                                   "source_url": "https://x", "source_kind": "MANUFACTURER",
                                   "edition_scope": "THIS_EDITION", "observed_at": "2026-01-01"})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    kind, why = _reasons(world.propose())
    assert kind == pm.REVIEW_REQUIRED and "different value" in why


def test_conflicting_claim_is_never_routine(world):  # noqa: F811
    world.sql(
        "INSERT INTO candidate_claim (candidate_id, field_key, claimed_value, claim_status,"
        " discovery_source_id) SELECT candidate_id, field_key, 'a rival value', 'NOT_VERIFIED',"
        " discovery_source_id FROM candidate_claim")
    m = world.propose()
    kind, why = _reasons(m)
    assert kind == pm.REVIEW_REQUIRED and "disagrees" in why and m["items"][0]["conflict"] != "NONE"


def test_missing_definition_is_new_semantics(world):  # noqa: F811
    kind, why = _reasons(world.propose([world.item(definition="not_a_defined_key")]))
    assert kind == pm.REVIEW_REQUIRED and "no spec definition" in why


@pytest.mark.parametrize("edition_map,edition,fragment", [
    ({}, "G1", "no explicit edition mapping"),
    ({ROBOT: "G1 EDU"}, "G1", "edition mapping says"),
    ({ROBOT: "G1 EDU"}, "G1 EDU", "claim is for edition"),
])
def test_ambiguous_edition_needs_review(world, edition_map, edition, fragment):  # noqa: F811
    m = world.propose([world.item(edition=edition)], edition_map=edition_map)
    kind, why = _reasons(m)
    assert kind == pm.REVIEW_REQUIRED and fragment in why


def test_claim_without_an_edition_in_its_field_key_needs_review(world):  # noqa: F811
    world.sql("UPDATE candidate_claim SET field_key = 'synthetic.spec/Computing Power'")
    assert "names no edition" in _reasons(world.propose())[1]


def test_unmatched_candidate_needs_review(world):  # noqa: F811
    world.sql("ALTER TABLE discovery_candidate DISABLE TRIGGER USER")
    world.sql("UPDATE discovery_candidate SET identity_status = 'POSSIBLE_DUPLICATE'")
    assert "not MATCHED_EXISTING" in _reasons(world.propose())[1]


def test_disabled_source_needs_review(world):  # noqa: F811
    world.sql("UPDATE discovery_source SET is_enabled = false")
    assert "source not eligible" in _reasons(world.propose())[1]


def test_stale_observation_needs_review(world):  # noqa: F811
    kind, why = _reasons(world.propose(today=TODAY + timedelta(days=60)))
    assert kind == pm.REVIEW_REQUIRED and "days old" in why


def test_claim_without_a_fetched_page_needs_review(world):  # noqa: F811
    world.sql("UPDATE candidate_claim SET fetched_page_id = NULL")
    assert "no fetched page" in _reasons(world.propose())[1]


def test_value_differing_from_the_claim_needs_an_interpretation(world):  # noqa: F811
    item = world.item(proposed_value="a normalised value")
    assert "no interpretation" in _reasons(world.propose([item]))[1]
    ok = world.propose([{**item, "interpretation": "normalised from the verbatim text"}])
    assert ok["items"][0]["classification"] == pm.ROUTINE


@pytest.mark.parametrize("definition,field", [
    ("price_usd", None), ("is_published", None), (KEY, "pricing_offer.price"),
    (KEY, "robot.is_published"),
])
def test_restricted_targets_are_restricted_and_verify_refuses(world, definition, field):  # noqa: F811
    item = world.item(definition=definition)
    if field:
        item["field"] = field
    m = world.propose([item])
    assert m["items"][0]["classification"] == pm.RESTRICTED
    assert sum(m["restricted_impact"].values()) == 1
    result = pm.verify(m, base_catalogue_dir=world.base, head_catalogue_dir=world.base)
    assert not result.ok and any("RESTRICTED" in r or "restricted" in r for r in result.reasons)


# ------------------------------------------------------------------- catalogue edit ------


def test_edit_is_text_level_and_idempotent(world):  # noqa: F811
    m = world.manifest                                   # also applied it to world.head
    path = "robots/" + ROBOT + ".json"
    original = (world.base / path).read_text(encoding="utf-8")
    edited = (world.head / path).read_text(encoding="utf-8")
    parsed = json.loads(edited)
    assert parsed["extended_specs"][-1]["key"] == KEY
    assert parsed["extended_specs"][-1]["value"] == VALUE
    assert parsed["extended_specs"][-1]["source_kind"] == "MANUFACTURER"
    assert parsed["extended_specs"][-1]["observed_at"] == "2026-10-18"
    # nothing but the inserted block changed: the previous last entry gains a comma, every
    # other original line is untouched and in order
    removed = [ln for ln in difflib.unified_diff(original.splitlines(), edited.splitlines(),
                                                 lineterm="", n=0) if ln.startswith("-")
               and not ln.startswith("---")]
    assert removed in ([], ["-    }"]), removed
    assert edited.encode("utf-8").startswith(original[:original.index('"extended_specs"')]
                                             .encode("utf-8"))
    again = pm.apply_to_catalogue(m, world.head)
    assert again == []                                   # second application is a no-op
    assert (world.head / path).read_text(encoding="utf-8") == edited
    assert [e["key"] for e in json.loads(edited)["extended_specs"]].count(KEY) == 1


def test_edit_with_different_existing_entry_is_refused(world):  # noqa: F811
    m = world.manifest
    path = world.head / "robots" / f"{ROBOT}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["extended_specs"][-1]["value"] = "tampered"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(pm.CatalogueEditRefused, match="different content"):
        pm.apply_to_catalogue(m, world.head)


@pytest.mark.parametrize("text_,fragment", [
    ('{\n  "slug": "x",\n  "extended_specs": []\n}\n', '"extended_specs": [\n    {'),
    ('{\n  "slug": "x"\n}\n', '"extended_specs": [\n    {'),
    ('{\r\n  "slug": "x",\r\n  "extended_specs": [\r\n    {"key": "a"}\r\n  ]\r\n}\r\n',
     '{"key": "a"},\r\n    {'),
])
def test_edit_handles_empty_missing_and_crlf_arrays(text_, fragment):
    out = pm.edit_robot_text(text_, [{"key": "k", "value": "v"}])
    assert fragment in out
    assert json.loads(out)["extended_specs"][-1] == {"key": "k", "value": "v"}


# ------------------------------------------------------------------------- verify ------


def test_verify_accepts_exactly_base_plus_manifest(world):  # noqa: F811
    result = pm.verify(world.manifest, base_catalogue_dir=world.base,
                       head_catalogue_dir=world.head)
    assert result.ok, result.reasons


def test_verify_rejects_an_extra_catalogue_edit(world):  # noqa: F811
    m = world.manifest
    path = world.head / "robots" / f"{ROBOT}.json"
    text_ = path.read_text(encoding="utf-8")
    assert '"announced_year": 2024' in text_
    path.write_text(text_.replace('"announced_year": 2024', '"announced_year": 2023'),
                    encoding="utf-8")
    result = pm.verify(m, base_catalogue_dir=world.base, head_catalogue_dir=world.head)
    assert not result.ok and any(ROBOT in r for r in result.reasons)


def test_verify_rejects_an_edit_to_another_catalogue_file(world):  # noqa: F811
    m = world.manifest
    other = world.head / "regions.json"
    other.write_text(other.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert not pm.verify(m, base_catalogue_dir=world.base,
                         head_catalogue_dir=world.head).ok
    (world.head / "regions.json").write_bytes((world.base / "regions.json").read_bytes())
    (world.head / "robots" / "extra-robot.json").write_text("{}", encoding="utf-8")
    result = pm.verify(m, base_catalogue_dir=world.base, head_catalogue_dir=world.head)
    assert any("added outside the manifest" in r for r in result.reasons)


def test_verify_rejects_a_modified_manifest_unsupported_version_and_review_lane(world):  # noqa: F811
    m = world.manifest
    bad = json.loads(json.dumps(m))
    bad["items"][0]["proposed_value"] = "edited after approval"
    assert any("digest" in r for r in pm.verify(
        bad, base_catalogue_dir=world.base, head_catalogue_dir=world.head).reasons)
    future = pm.seal({**json.loads(json.dumps(m)), "manifest_version": 3})
    assert any("unsupported" in r for r in pm.verify(
        future, base_catalogue_dir=world.base, head_catalogue_dir=world.head).reasons)
    # version 2 is core robot columns from research: a specification manifest relabelled as 2
    # fails its scope checks
    relabelled = pm.seal({**json.loads(json.dumps(m)), "manifest_version": 2})
    assert any("allowed_tables must be exactly ['robot']" in r for r in pm.verify(
        relabelled, base_catalogue_dir=world.base, head_catalogue_dir=world.head).reasons)
    review = json.loads(json.dumps(m))
    review["items"][0]["classification"] = pm.REVIEW_REQUIRED
    assert any("only ROUTINE" in r for r in pm.verify(
        pm.seal(review), base_catalogue_dir=world.base,
        head_catalogue_dir=world.head).reasons)
    impact = json.loads(json.dumps(m))
    impact["restricted_impact"]["prices"] = 1
    assert any("restricted impact" in r for r in pm.verify(
        pm.seal(impact), base_catalogue_dir=world.base,
        head_catalogue_dir=world.head).reasons)


# ------------------------------------------------------------------------ decisions ------


def test_rejected_claims_are_not_proposed_again_unless_reconsidered(world):  # noqa: F811
    m = world.propose()
    entry = pm.record_decision(world.base, m, "REJECT", "not wanted", "Robert", TODAY)
    assert entry["claim_ids"] == [world.claim_id]
    with pytest.raises(pm.ProposalRefused, match="REJECTED"):
        world.propose()
    again = world.propose(reconsider=True)
    assert again["items"][0]["classification"] == pm.ROUTINE
    assert (world.base / "promotions" / "decisions.json").exists()


def test_deferred_claims_may_be_proposed_again(world):  # noqa: F811
    m = world.propose()
    pm.record_decision(world.base, m, "DEFER", "later", "Robert", TODAY)
    assert world.propose()["items"][0]["classification"] == pm.ROUTINE
    with pytest.raises(ValueError):
        pm.record_decision(world.base, m, "MAYBE", "x", "Robert", TODAY)
    with pytest.raises(ValueError):
        pm.record_decision(world.base, m, "REJECT", " ", "Robert", TODAY)


# ----------------------------------------------------------------------------- CLI ------


def test_cli_propose_dry_run_output_and_decide(world, tmp_path, capsys):  # noqa: F811
    out = tmp_path / "out"
    rc = cli.main(["propose", "--database-url", world.url, "--robot", ROBOT, "--claim",
                   world.claim_id, "--definition", KEY, "--value", VALUE, "--edition", "G1",
                   "--promotion-id", "cli-promo", "--base-commit", "x", "--today",
                   TODAY.isoformat(), "--catalogue-dir", str(world.base),
                   "--dry-run-output", str(out)])
    assert rc == 0, capsys.readouterr()
    manifest = json.loads((out / "cli-promo.json").read_text(encoding="utf-8"))
    assert manifest["digest"] == pm.compute_digest(manifest)
    assert (out / "cli-promo.md").read_text(encoding="utf-8") == pm.render_review(manifest)
    assert not (world.base / "promotions").exists()               # nothing written to the repo
    assert cli.main(["decide", "--manifest", str(out / "cli-promo.json"), "--reject", "--reason",
                     "no", "--by", "Robert", "--catalogue-dir", str(world.base)]) == 0
    rc = cli.main(["propose", "--database-url", world.url, "--robot", ROBOT, "--claim",
                   world.claim_id, "--definition", KEY, "--value", VALUE, "--edition", "G1",
                   "--catalogue-dir", str(world.base), "--dry-run-output", str(out)])
    assert rc == 2 and "REJECTED" in capsys.readouterr().err


def test_cli_propose_unreadable_database_prints_type_only(tmp_path, capsys):
    rc = cli.main(["propose", "--database-url",
                   "postgresql+psycopg://nosuchuser:secretpw@localhost:55441/none",
                   "--robot", ROBOT, "--claim", "00000000-0000-0000-0000-000000000000",
                   "--definition", KEY,
                   "--value", "v", "--edition", "G1", "--dry-run-output", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 4 and "secretpw" not in captured.err + captured.out
