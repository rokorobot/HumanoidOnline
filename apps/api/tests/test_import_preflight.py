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


def test_audit_history_is_reported_separately_and_never_gated():
    before = snap(accepted_claim=[], crawl_run=[])
    after = snap(accepted_claim=[{"x": 1}, {"x": 2}], crawl_run=[{"y": 1}])
    report = pf.classify(pf.diff(before, after), {"expected": []})
    assert report["ok"] and report["business_changes"] == 0
    assert report["audit_history"] == {"accepted_claim": 2, "crawl_run": 1}


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


def test_a_reimport_of_an_unchanged_robot_changes_no_business_data(scoped_world):
    url, _ = scoped_world
    before = _snap(url)
    ic.run(url, only={H2})
    assert [c for c in pf.diff(before, _snap(url)) if not c.audit] == []


def test_only_synchronizes_preexisting_canonical_evidence_of_the_selected_robot(scoped_world):
    """The documented semantic: `--only H2` reconciles H2's WHOLE canonical JSON — an evidence
    row unrelated to any new claim comes along — and touches nothing of the unselected robot."""
    url, cat = scoped_world
    _add_old_evidence(cat, H2)
    _add_old_evidence(cat, R1)                  # also lagging, but NOT selected
    before = _snap(url)
    ic.run(url, only={H2})
    changes = [c for c in pf.diff(before, _snap(url)) if not c.audit]
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
