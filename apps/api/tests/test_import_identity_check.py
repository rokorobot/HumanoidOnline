"""db/import_identity_check.py: identity (not content) comparison of two catalogue databases."""
from __future__ import annotations

import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("import_identity_check",
                                               REPO / "db" / "import_identity_check.py")
ick = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ick)


def snap(**tables):
    out = {t: {"rows": rows, "ambiguous": []} for t, rows in tables.items()}
    out["_audit_targets"] = {}
    return out


def test_same_ids_pass_and_a_reinserted_row_is_an_id_change():
    before = snap(pricing_offer={"r1:-|alza|CZ|PURCHASE|NEW": ("id-1", "t0")})
    same = snap(pricing_offer={"r1:-|alza|CZ|PURCHASE|NEW": ("id-1", "t0")})
    churn = snap(pricing_offer={"r1:-|alza|CZ|PURCHASE|NEW": ("id-2", "t1")})
    assert not any(ick.compare(before, same)[k] for k in ("ID_CHANGED", "TOUCHED"))
    assert ick.compare(before, churn)["ID_CHANGED"] == ["pricing_offer r1:-|alza|CZ|PURCHASE|NEW"]


def test_rewrites_additions_removals_and_lost_audit_targets_are_reported():
    before = snap(robot={"r1:r1": ("a", "t0"), "r2:r2": ("b", "t0")})
    after = snap(robot={"r1:r1": ("a", "t1"), "r3:r3": ("c", "t0")})
    before["_audit_targets"], after["_audit_targets"] = {"7": True}, {"7": False}
    report = ick.compare(before, after)
    assert report["TOUCHED"] == ["robot r1:r1"]
    assert report["REMOVED"] == ["robot r2:r2"] and report["ADDED"] == ["robot r3:r3"]
    assert report["AUDIT_TARGET_LOST"] == ["audit_seq 7"]


def test_robot_scope_limits_robot_tables():
    before = snap(robot={"r1:r1": ("a", None), "r2:r2": ("b", None)})
    after = snap(robot={"r1:r1": ("a", None), "r2:r2": ("x", None)})
    assert ick.compare(before, after, {"r1"})["ID_CHANGED"] == []
    assert ick.compare(before, after)["ID_CHANGED"] == ["robot r2:r2"]
