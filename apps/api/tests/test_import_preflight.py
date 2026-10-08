"""`--only` is robot-scoped reconciliation, and the preflight gate makes that visible.

`import_catalogue.py --only <robot>` reconciles the COMPLETE canonical JSON representation of the
selected robots (and what they reference). It is not "apply only the claims that motivated this
import": if production lags `main` for a selected robot, evidence that is unrelated to the newest
materialization is synchronized too (the three reichelt evidence rows of the 2026-10-05 Alza
import). These tests pin that behaviour explicitly — they do not change it — and prove that
`db/import_preflight.py` turns it into a stop instead of a surprise.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import shutil
import sys

import psycopg
import pytest
from test_identity_decision_migration import scratch_db  # noqa: F401

REPO = pathlib.Path(__file__).resolve().parents[3]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod            # dataclasses resolve their own module while decorating
    spec.loader.exec_module(mod)
    return mod


ic = _load("import_catalogue", "db/import_catalogue.py")
pf = _load("import_preflight", "db/import_preflight.py")


# ------------------------------------------------------------------- pure -----


def snap(**tables):
    return {t: list(rows) for t, rows in tables.items()}


def offer(robot="r1", provider="alza-cz", **kw):
    return {"robot": robot, "provider": provider, "condition": "NEW", "price": 1.0, **kw}


def test_an_explained_addition_passes_and_an_unexplained_one_stops():
    before = snap(pricing_offer=[], evidence_source=[])
    after = snap(pricing_offer=[offer()], evidence_source=[{"subject": "x", "source_url": "u"}])
    changes = pf.diff(before, after)
    manifest = {"expected": [{"table": "pricing_offer", "kind": "ADDED",
                              "match": {"robot": "r1", "provider": "alza-cz"}}]}
    report = pf.classify(changes, manifest)
    assert not report["ok"]                                     # the evidence row is unexplained
    assert [u["table"] for u in report["unexplained"]] == ["evidence_source"]
    manifest["expected"].append({"table": "evidence_source", "kind": "ADDED"})
    assert pf.classify(changes, manifest)["ok"]


def test_equal_row_counts_do_not_hide_a_swapped_row():
    """One row removed and a DIFFERENT one added: the totals are identical, the gate is not."""
    before = snap(pricing_offer=[offer(price=1.0)])
    after = snap(pricing_offer=[offer(price=2.0)])
    assert len(before["pricing_offer"]) == len(after["pricing_offer"])
    report = pf.classify(pf.diff(before, after), {"expected": []})
    kinds = sorted((u["kind"], u["category"]) for u in report["unexplained"])
    assert kinds == [("ADDED", "pricing_offer"), ("REMOVED", "removal")]


def test_changed_publication_and_removals_get_their_own_categories():
    before = snap(robot=[{"slug": "a", "is_published": False, "name": "A"},
                         {"slug": "b", "is_published": True, "name": "B"}])
    after = snap(robot=[{"slug": "a", "is_published": True, "name": "A"},
                        {"slug": "c", "is_published": True, "name": "C"}])
    changes = {(c.kind, c.fields["slug"]): c for c in pf.diff(before, after)}
    assert changes[("CHANGED", "a")].category == "publication"
    assert changes[("CHANGED", "a")].detail == {"is_published": [False, True]}
    assert changes[("ADDED", "c")].category == "publication"      # a new robot published at once
    assert changes[("REMOVED", "b")].category == "removal"


def test_added_append_only_history_is_reported_separately_and_never_gated():
    before = snap(accepted_claim=[], fetched_page=[])
    after = snap(accepted_claim=[{"x": 1}, {"x": 2}], fetched_page=[{"y": 1}])
    report = pf.classify(pf.diff(before, after), {"expected": []})
    assert report["ok"] and report["business_changes"] == 0
    assert report["audit_history_added"] == {"accepted_claim": 2, "fetched_page": 1}


def test_history_that_loses_or_alters_a_row_is_gated():
    """Append-only history may grow without a manifest entry; it may never shrink or change."""
    before = snap(accepted_claim=[{"digest": "a"}], fetched_page=[{"url": "u", "hash": "1"}])
    after = snap(accepted_claim=[], fetched_page=[{"url": "u", "hash": "2"}])   # lost / altered
    report = pf.classify(pf.diff(before, after), {"expected": []})
    assert not report["ok"]
    assert {(u["table"], u["kind"], u["category"]) for u in report["unexplained"]} == {
        ("accepted_claim", "REMOVED", "audit_removal"), ("fetched_page", "REMOVED",
                                                         "audit_removal")}


# ---- catalogue_write_audit.target_row_id: a forensic row id, not an identity (DR-A5 18.3) ----

def audit_row(seq=38, target="unitree-h2-edu|alza-cz|CZ|-|NEW|PURCHASE|PUBLIC", **kw):
    return {"audit_seq": seq, "claim": "c0ffee00-0000-4000-8000-000000000001",
            "robot_slug": "unitree-h2-edu", "method": "IMPORTER_M2",
            "change_ref": "chg-alza-reference-offers-pr149", "target_table": "pricing_offer",
            "target_row": target, "after_hash": "a" * 64, "applied_by": "tester", **kw}


GONE = "7d0f8f0e-3a52-4d0b-9d0c-2f6f2c1f9f11"       # the offer id the importer replaced


def test_a_dangling_audit_target_is_reported_distinctly_and_does_not_stop_the_import():
    """The 2026-10-08 false stop: the audit row is unchanged, only its target's id is gone."""
    changes = pf.diff(snap(catalogue_write_audit=[audit_row(), audit_row(seq=39)]),
                      snap(catalogue_write_audit=[audit_row(target=GONE), audit_row(seq=39)]))
    assert [(c.kind, c.category, c.gated) for c in changes] == [
        ("CHANGED", "audit_target_dangling", False)]
    report = pf.classify(changes, {"expected": []})
    assert report["ok"] and report["business_changes"] == 0 and not report["unexplained"]
    assert report["audit_history_added"] == {}                  # not "8 removed + 8 added"
    [d] = report["audit_targets_dangling"]
    assert (d["audit_seq"], d["target_table"], d["target_row_id"]) == (38, "pricing_offer", GONE)
    out = pf.render(report)
    assert "AUDIT TARGET DANGLING" in out and "audit_seq=38" in out and "PASS" in out


@pytest.mark.parametrize("after", [
    audit_row(target=GONE, after_hash="b" * 64),               # content altered as well
    audit_row(target="unitree-h2-edu|other|CZ|-|NEW|PURCHASE|PUBLIC"),   # points elsewhere
    audit_row(change_ref="rewritten")])
def test_any_other_difference_in_an_audit_row_is_still_history_altered(after):
    report = pf.classify(pf.diff(snap(catalogue_write_audit=[audit_row()]),
                                 snap(catalogue_write_audit=[after])), {"expected": []})
    assert not report["ok"] and report["audit_targets_dangling"] == []
    assert [(u["kind"], u["category"]) for u in report["unexplained"]] == [
        ("CHANGED", "audit_removal")]


def test_a_removed_audit_row_is_still_gated():
    report = pf.classify(pf.diff(snap(catalogue_write_audit=[audit_row()]),
                                 snap(catalogue_write_audit=[])), {"expected": []})
    assert [(u["kind"], u["category"]) for u in report["unexplained"]] == [
        ("REMOVED", "audit_removal")]


# ---- discovery_source: acquisition policy is configuration, not history --------------------

def source(key="alza-cz", **kw):
    row = {"key": key, "name": "Alza.cz", "source_class": "DISTRIBUTOR", "is_enabled": False,
           "tos_status": "UNKNOWN", "robots_status": "UNKNOWN", "observation_interval_hours": None,
           "observation_cadence_set_by": None, "allowed_path_prefixes": None}
    row.update(kw)
    return row


def test_an_unexpected_new_discovery_source_stops_unless_listed():
    changes = pf.diff(snap(discovery_source=[]), snap(discovery_source=[source()]))
    report = pf.classify(changes, {"expected": []})
    assert not report["ok"]
    assert (report["unexplained"][0]["table"], report["unexplained"][0]["category"]) == (
        "discovery_source", "source")
    assert "PREFLIGHT STOP" in pf.render(report)
    listed = {"expected": [{"table": "discovery_source", "kind": "ADDED",
                            "match": {"key": "alza-cz", "is_enabled": False}}]}
    assert pf.classify(changes, listed)["ok"]
    wrongly_enabled = pf.diff(snap(discovery_source=[]),
                              snap(discovery_source=[source(is_enabled=True)]))
    assert not pf.classify(wrongly_enabled, listed)["ok"]     # "added disabled" != "added enabled"


@pytest.mark.parametrize("change", [
    {"is_enabled": True, "tos_status": "ALLOWED", "robots_status": "ALLOWED"},
    {"observation_interval_hours": 24, "observation_cadence_set_by": "someone"},
    {"allowed_path_prefixes": ["/unitree/"]},
    {"source_class": "MANUFACTURER"},
])
def test_a_change_to_a_sources_automation_state_is_detected_by_its_key_and_gated(change):
    before = snap(discovery_source=[source(), source("other")])
    after = snap(discovery_source=[source(**change), source("other")])
    [c] = pf.diff(before, after)
    assert (c.table, c.kind, c.category, c.fields["key"]) == (
        "discovery_source", "CHANGED", "source", "alza-cz")
    assert set(c.detail) == set(change)                       # exactly the columns that moved
    report = pf.classify([c], {"expected": []})
    assert not report["ok"] and "PREFLIGHT STOP" in pf.render(report)
    assert pf.classify([c], {"expected": [{"table": "discovery_source", "kind": "CHANGED",
                                           "match": {"key": "alza-cz"}}]})["ok"]


def test_alza_cannot_be_enabled_inside_the_audit_count_bucket():
    """The 2026-10-05 invariant: alza-cz exists for provenance and stays disabled. Every audit
    row the manual-capture chain legitimately adds is free, yet flipping the source to enabled
    or giving it a cadence in the same rehearsal is NOT hidden by them."""
    audit_rows = dict(crawl_run_unused=[], accepted_claim=[{"d": i} for i in range(14)],
                      fetched_page=[{"u": i} for i in range(7)],
                      discovery_proposal_decision=[{"p": i} for i in range(14)])
    before = snap(discovery_source=[source()], **{k: [] for k in audit_rows})
    clean_after = snap(discovery_source=[source()], **audit_rows)
    assert pf.classify(pf.diff(before, clean_after), {"expected": []})["ok"]   # audit-only: free
    sneaky = snap(discovery_source=[source(is_enabled=True, observation_interval_hours=24,
                                           observation_cadence_set_by="x")], **audit_rows)
    report = pf.classify(pf.diff(before, sneaky), {"expected": []})
    assert not report["ok"]
    assert [u["table"] for u in report["unexplained"]] == ["discovery_source"]
    assert report["audit_history_added"]["accepted_claim"] == 14   # the bucket stays a count


@pytest.mark.parametrize("table,category", [
    ("freshness_target", "freshness_config"), ("crawl_run", "acquisition_run"),
    ("discovery_candidate", "discovery_candidate"), ("candidate_claim", "discovery_candidate"),
    ("candidate_commercial_signal", "discovery_candidate"),
    ("candidate_image_ref", "discovery_candidate"),
])
def test_mutable_operational_state_is_gated(table, category):
    [c] = pf.diff(snap(**{table: []}), snap(**{table: [{"k": 1}]}))
    assert (c.category, c.gated) == (category, True)
    assert not pf.classify([c], {"expected": []})["ok"]


def test_freshness_target_and_candidate_changes_pair_by_their_composite_keys():
    before = snap(freshness_target=[{"robot": "r", "url": "u", "active": True}],
                  discovery_candidate=[{"source": "s", "external_ref": "e", "status": "NEW"}])
    after = snap(freshness_target=[{"robot": "r", "url": "u", "active": False}],
                 discovery_candidate=[{"source": "s", "external_ref": "e", "status": "REJECTED"}])
    got = {c.table: (c.kind, c.detail) for c in pf.diff(before, after)}
    assert got == {"freshness_target": ("CHANGED", {"active": [True, False]}),
                   "discovery_candidate": ("CHANGED", {"status": ["NEW", "REJECTED"]})}


def test_lead_and_requirement_rows_are_gated_but_never_printed():
    """User-submitted business records: any change must be listed, and no contact detail may
    reach the report (only a content hash is compared)."""
    secret = "buyer@example.com"
    import hashlib
    import json as _json
    row = {"contact_email": secret, "lead_status": "NEW"}
    redacted = {"redacted_content_sha": hashlib.sha256(
        _json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]}
    changes = pf.diff(snap(commercial_lead=[]), snap(commercial_lead=[redacted]))
    report = pf.classify(changes, {"expected": []})
    assert not report["ok"] and report["unexplained"][0]["category"] == "runtime_user_data"
    assert secret not in pf.render(report) and secret not in _json.dumps(report)
    assert pf.classify(changes, {"expected": [{"table": "commercial_lead",
                                               "kind": "ADDED"}]})["ok"]


def test_the_ungated_set_is_exactly_the_append_only_history():
    assert pf.AUDIT_TABLES.isdisjoint({
        "discovery_source", "freshness_target", "crawl_run", "discovery_candidate",
        "candidate_claim", "candidate_commercial_signal", "candidate_image_ref",
        "commercial_lead", "commercial_lead_robot", "commercial_lead_provider",
        "buyer_requirement", "match_result"})
    assert {"accepted_claim", "claim_retraction", "catalogue_write_audit",
            "discovery_claim_proposal", "discovery_proposal_decision",
            "discovery_proposal_observation", "promotion_audit", "candidate_identity_decision",
            "source_eligibility_review"} <= pf.AUDIT_TABLES      # DB-enforced append-only


def test_an_expected_change_that_does_not_happen_also_stops():
    report = pf.classify([], {"expected": [{"table": "pricing_offer", "kind": "ADDED",
                                            "match": {"robot": "r1"}, "count": 2}]})
    assert not report["ok"] and report["unfulfilled"][0]["missing"] == 2


def test_substring_matching_and_counts():
    changes = pf.diff(snap(evidence_source=[]), snap(evidence_source=[
        {"subject": "pricing|r1|alza", "source_url": "https://www.alza.cz/a"},
        {"subject": "pricing|r1|alza", "source_url": "https://www.alza.cz/b"}]))
    ok = {"expected": [{"table": "evidence_source", "kind": "ADDED", "count": 2,
                        "match": {"source_url~": "alza.cz"}}]}
    assert pf.classify(changes, ok)["ok"]
    too_few = copy.deepcopy(ok)
    too_few["expected"][0]["count"] = 1
    assert not pf.classify(changes, too_few)["ok"]


def test_the_cli_refuses_to_run_without_a_manifest_unless_report_only(capsys):
    with pytest.raises(SystemExit):
        pf.main(["--before", "postgresql://x/a", "--after", "postgresql://x/b"])
    assert "manifest is required" in capsys.readouterr().err


# ------------------------------------------------------------ DB-backed -------

SCHEMA = (REPO / "db" / "schema.sql").read_text(encoding="utf-8")
H2 = "unitree-h2-edu"
R1 = "unitree-r1-edu-u4"


@pytest.fixture
def scoped_world(scratch_db, tmp_path, monkeypatch):  # noqa: F811
    cat = tmp_path / "catalogue"
    shutil.copytree(REPO / "db" / "catalogue", cat)
    monkeypatch.setattr(ic, "CATALOGUE_DIR", cat)
    monkeypatch.setattr(ic, "ROBOTS_DIR", cat / "robots")
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA)
    ic.run(scratch_db, only={H2, R1})                   # production "as last imported"
    return scratch_db, cat


def _snap(url):
    with psycopg.connect(url) as conn:
        conn.read_only = True
        return pf.snapshot(conn)


def _add_old_evidence(cat, slug):
    """A reviewed evidence row already present on `main` for this robot, absent from the DB."""
    path = cat / "robots" / f"{slug}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    ev = copy.deepcopy(doc["pricing_offers"][0]["evidence"][0])
    ev["observed_at"] = "2026-09-26"
    ev["excerpt"] = "Re-observation already reviewed on main (unrelated to the newest claim)"
    doc["pricing_offers"][0]["evidence"].append(ev)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def test_real_discovery_source_cadence_and_enablement_are_gated(scratch_db):  # noqa: F811
    """Against the actual schema: registering a source and later giving it a cadence are
    detected by the source's `key` and cannot pass without a manifest entry."""
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA)
        conn.execute("SET search_path TO humanoid, public")
        base = _snap(scratch_db)
        conn.execute("INSERT INTO discovery_source (key, name, source_class, homepage_url) "
                     "VALUES ('alza-cz', 'Alza.cz', 'DISTRIBUTOR', 'https://www.alza.cz/')")
        registered = _snap(scratch_db)
        conn.execute("UPDATE discovery_source SET observation_interval_hours = 24, "
                     "observation_cadence_set_by = 'someone', "
                     "observation_cadence_set_at = now() WHERE key = 'alza-cz'")
        scheduled = _snap(scratch_db)
    [added] = [c for c in pf.diff(base, registered) if c.gated]
    assert (added.table, added.kind, added.fields["key"], added.fields["is_enabled"]) == (
        "discovery_source", "ADDED", "alza-cz", False)
    assert not pf.classify(pf.diff(base, registered), {"expected": []})["ok"]
    [moved] = [c for c in pf.diff(registered, scheduled) if c.gated]
    assert (moved.kind, moved.category) == ("CHANGED", "source")
    assert set(moved.detail) == {"observation_interval_hours", "observation_cadence_set_by",
                                 "observation_cadence_set_at"}
    assert not pf.classify(pf.diff(registered, scheduled), {"expected": [
        {"table": "discovery_source", "kind": "ADDED"}]})["ok"]       # "added" != "scheduled"


def test_a_reimport_of_an_unchanged_robot_changes_no_business_data(scoped_world):
    url, _ = scoped_world
    before = _snap(url)
    ic.run(url, only={H2})
    assert [c for c in pf.diff(before, _snap(url)) if c.gated] == []


def test_only_synchronizes_preexisting_canonical_evidence_of_the_selected_robot(scoped_world):
    """The documented semantic: `--only H2` reconciles H2's WHOLE canonical JSON — an evidence
    row unrelated to any new claim comes along — and touches nothing of the unselected robot."""
    url, cat = scoped_world
    _add_old_evidence(cat, H2)
    _add_old_evidence(cat, R1)                  # also lagging, but NOT selected
    before = _snap(url)
    ic.run(url, only={H2})
    changes = [c for c in pf.diff(before, _snap(url)) if c.gated]
    assert [(c.table, c.kind) for c in changes] == [("evidence_source", "ADDED")]
    assert "Re-observation" in changes[0].fields["excerpt"]
    assert H2 in changes[0].fields["subject"] and R1 not in changes[0].fields["subject"]


def test_the_gate_stops_on_that_synchronization_until_it_is_listed(scoped_world):
    url, cat = scoped_world
    _add_old_evidence(cat, H2)
    before = _snap(url)
    ic.run(url, only={H2})
    changes = pf.diff(before, _snap(url))
    # a manifest written only for "the new claims" (here: none) does not cover the extra row
    report = pf.classify(changes, {"expected": []})
    assert not report["ok"]
    assert report["unexplained"][0]["table"] == "evidence_source"
    assert "STOP" in pf.render(report)
    listed = {"expected": [{"table": "evidence_source", "kind": "ADDED",
                            "match": {"subject~": H2, "excerpt~": "Re-observation"}}]}
    assert pf.classify(changes, listed)["ok"]


def test_a_reimport_orphans_the_audit_target_row_id_and_the_gate_says_exactly_that(scoped_world):
    """The mechanism end to end: the importer replaces a robot's offers (new UUIDs), so an
    untouched `catalogue_write_audit` row stops resolving. Reported as a dangling target, not
    as a removed + added audit row."""
    url, _ = scoped_world
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SET search_path TO humanoid, public")
        # Scratch database only: an accepted claim needs the whole proposal/decision chain,
        # which is irrelevant to how the preflight reads the audit row.
        conn.execute("ALTER TABLE catalogue_write_audit "
                     "DROP CONSTRAINT catalogue_write_audit_claim_id_fkey")
        offer_id = conn.execute(
            "SELECT p.id FROM pricing_offer p JOIN robot r ON r.id = p.robot_id "
            "WHERE r.slug = %s ORDER BY p.id LIMIT 1", (H2,)).fetchone()[0]
        seq, stored = conn.execute(
            "INSERT INTO catalogue_write_audit (claim_id, robot_slug, method, change_ref, "
            "target_table, target_row_id, after_hash, applied_by) VALUES (gen_random_uuid(), %s, "
            "'IMPORTER_M2', 'chg-test', 'pricing_offer', %s, repeat('a', 64), 'tester') "
            "RETURNING audit_seq, md5(catalogue_write_audit::text)", (H2, offer_id)).fetchone()
    before = _snap(url)
    ic.run(url, only={H2})
    after = _snap(url)
    with psycopg.connect(url) as conn:
        conn.execute("SET search_path TO humanoid, public")
        unchanged = conn.execute("SELECT md5(a::text) FROM catalogue_write_audit a").fetchone()[0]
        live = conn.execute("SELECT count(*) FROM pricing_offer WHERE id = %s",
                            (offer_id,)).fetchone()[0]
    assert unchanged == stored                  # the audit row is byte-identical
    assert live == 0                            # its target was recreated under a new UUID
    changes = pf.diff(before, after)
    assert [c for c in changes if c.gated] == []
    report = pf.classify(changes, {"expected": []})
    assert report["ok"] and report["audit_history_added"] == {}
    [d] = report["audit_targets_dangling"]
    assert (d["audit_seq"], d["target_row_id"]) == (seq, str(offer_id))
    assert d["was"].startswith(H2)
    # already dangling on both sides: nothing left to report on the next import
    ic.run(url, only={H2})
    assert pf.classify(pf.diff(after, _snap(url)), {"expected": []})["audit_targets_dangling"] == []
