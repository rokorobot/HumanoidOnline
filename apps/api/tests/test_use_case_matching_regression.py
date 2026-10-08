"""Use-case fits against the matching engine, straight from the catalogue files.

No database: the engine is pure, and `scripts/use_case_matching_regression.py`
builds its inputs from `db/catalogue/`. These pin what the 2026-10-08 use-case
review relies on (docs/audit/USE_CASE_ENRICHMENT_REVIEW_2026-10-08.md):

* G1 Basic (decision D1) is associated with Research & Education but not rated,
  so matching treats it exactly as a robot with no row: neutral, with a warning,
  and no fit reason.
* 4NE1 Mini (decision D2, not applied) has no row and is treated the same way.
* A scored fit reaches the engine as the score in the file, and moves the result.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from app.services.matching.engine import BASE_WEIGHTS, match

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "use_case_matching_regression", REPO_ROOT / "scripts" / "use_case_matching_regression.py"
)
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

RE = "research-education"
REGIONS = json.loads((REPO_ROOT / "db/catalogue/regions.json").read_text(encoding="utf-8"))
ROBOTS = {
    p.stem: json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((REPO_ROOT / "db/catalogue/robots").glob("*.json"))
}
REQ = harness._req(use_case=RE)
UNVERIFIED = f"use-case fit for {RE} is unverified"


def _only(robot: dict, req=REQ):
    """The single scored match for one robot, forced published so an unpublished
    file can be scored too (matching itself only ever sees published robots)."""
    [m] = match(req, harness.candidates(REGIONS, [{**robot, "is_published": True}], req)).matches
    return m


def _neutral_points(req=REQ) -> float:
    """Points the use-case criterion yields at the neutral 0.5 sub-score, for a
    requirement that states a use case and nothing else."""
    active = BASE_WEIGHTS["use_case_fit"] + BASE_WEIGHTS["commercial_availability"] \
        + BASE_WEIGHTS["deployment_readiness"]
    return round(0.5 * BASE_WEIGHTS["use_case_fit"] * 100.0 / active, 2)


def _without_fits(robot: dict) -> dict:
    clone = copy.deepcopy(robot)
    clone["use_case_fits"] = []
    return clone


@pytest.mark.parametrize("slug", ["unitree-g1", "4ne1-mini"])
def test_an_unrated_or_absent_fit_is_neutral_with_a_warning_and_no_fit_reason(slug):
    m = _only(ROBOTS[slug])
    assert m.breakdown["use_case_fit"] == _neutral_points()
    assert UNVERIFIED in m.warnings
    assert not any(r.startswith("use-case fit ") for r in m.reasons)


def test_g1_basic_scores_exactly_as_if_it_had_no_row():
    """D1: NULL is "associated, not rated". The association shows on the use-case
    page; matching cannot tell it from no row at all."""
    assert _only(ROBOTS["unitree-g1"]) == _only(_without_fits(ROBOTS["unitree-g1"]))


def test_g1_basic_no_longer_outranks_on_a_research_score_it_did_not_earn():
    basic, edu = _only(ROBOTS["unitree-g1"]), _only(ROBOTS["unitree-g1-edu-plus-u2"])
    assert edu.breakdown["use_case_fit"] > basic.breakdown["use_case_fit"]
    assert "use-case fit 0.85 for research-education" in edu.reasons


def test_g1_basic_is_unchanged_for_every_other_use_case():
    for use_case in ("home", "manufacturing", "warehouse-logistics", "events-entertainment"):
        req = harness._req(use_case=use_case)
        assert _only(ROBOTS["unitree-g1"], req) == _only(_without_fits(ROBOTS["unitree-g1"]), req)


def _scored_fits():
    for slug, robot in ROBOTS.items():
        for fit in robot.get("use_case_fits") or []:
            if fit.get("fit_score") is not None:
                yield slug, fit


def test_every_scored_fit_reaches_the_engine_as_the_score_in_the_file():
    seen = 0
    for slug, fit in _scored_fits():
        req = harness._req(use_case=fit["use_case_slug"])
        [candidate] = harness.candidates(REGIONS, [{**ROBOTS[slug], "is_published": True}], req)
        assert candidate.use_case_fit == fit["fit_score"], slug
        seen += 1
    assert seen >= 19


def test_a_scored_fit_moves_the_use_case_criterion_and_nothing_else():
    for slug, fit in _scored_fits():
        if ROBOTS[slug]["commercial_status"] == "DISCONTINUED":
            continue  # hard-excluded from matching before any scoring
        req = harness._req(use_case=fit["use_case_slug"])
        with_fit, without = _only(ROBOTS[slug], req), _only(_without_fits(ROBOTS[slug]), req)
        for key in BASE_WEIGHTS:
            if key == "use_case_fit":
                raised = with_fit.breakdown[key] > without.breakdown[key]
                assert raised == (fit["fit_score"] > 0.5), slug
            else:
                assert with_fit.breakdown[key] == without.breakdown[key], (slug, key)
