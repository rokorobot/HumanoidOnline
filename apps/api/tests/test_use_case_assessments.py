"""New-robot use-case evaluation (HO-UC-01, owner rule 2026-10-24). File-level, no database.

Every robot record carries a completed use-case assessment in
`db/catalogue/use_case_assessments/<slug>.json`, except the records that predate the rule and
are frozen in `legacy_baseline.json`. An assessment rates the robot against EVERY category in
`use_cases.json` and says, per category, which of three things is true:

* ``FIT`` — a defensible fit. The robot file has a `use_case_fits` row for that category, and
  the assessment names at least one source already recorded in that same robot file.
* ``UNSUPPORTED_POSSIBILITY`` — plausible, but not defensible on the recorded evidence. No fit
  row; the reason is written down.
* ``NO_BASIS`` — nothing recorded links the robot to the category. No fit row. This is
  "suitability unknown", never a claim that the robot is unsuitable (AGENTS.md rule 6).

A robot with no FIT at all is a valid, documented outcome. The live rows the importer writes
stay the robot file's `use_case_fits`; the assessment is the review record that explains them.
Adding a category re-opens every assessment on purpose: each one must then rate it too.
See db/catalogue/README.md section 7.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE = REPO_ROOT / "db" / "catalogue"
ASSESSMENTS_DIR = CATALOGUE / "use_case_assessments"
BASELINE_FILE = ASSESSMENTS_DIR / "legacy_baseline.json"
SCHEMA = REPO_ROOT / "db" / "schema.sql"

ROBOTS = {
    p.stem: json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((CATALOGUE / "robots").glob("*.json"))
}
RAW = {p.stem: p.read_text(encoding="utf-8") for p in sorted((CATALOGUE / "robots").glob("*.json"))}
USE_CASES = [
    u["slug"]
    for u in json.loads((CATALOGUE / "use_cases.json").read_text(encoding="utf-8"))["use_cases"]
]
ASSESSMENTS = {
    p.stem: json.loads(p.read_text(encoding="utf-8"))
    for p in sorted(ASSESSMENTS_DIR.glob("*.json"))
    if p != BASELINE_FILE
}
BASELINE = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))["robots"]

#: Size of the baseline when it was frozen. It may shrink, never grow: a new robot is
#: assessed, not grandfathered. Lower this number when slugs leave the baseline.
BASELINE_FROZEN_SIZE = 62

STATUSES = {"FIT", "UNSUPPORTED_POSSIBILITY", "NO_BASIS"}


def _commercial_status_labels() -> set[str]:
    sql = re.sub(r"--[^\n]*", "", SCHEMA.read_text(encoding="utf-8"))
    body = re.search(r"CREATE TYPE commercial_status AS ENUM \((.*?)\);", sql, flags=re.S)
    assert body, "commercial_status enum not found in db/schema.sql"
    return set(re.findall(r"'([^']+)'", body.group(1)))


COMMERCIAL_STATUSES = _commercial_status_labels()


def assessment_problems(
    slug: str, robot: dict, raw: str, assessment: dict | None, use_cases: list[str]
) -> list[str]:
    """Everything wrong with one robot's assessment; an empty list means complete."""
    if assessment is None:
        return [f"{slug}: no use-case assessment (use_case_assessments/{slug}.json)"]
    problems = []
    if assessment.get("robot_slug") != slug:
        problems.append(f"{slug}: assessment names robot {assessment.get('robot_slug')!r}")
    for key in ("assessed_on", "method"):
        if not str(assessment.get(key) or "").strip():
            problems.append(f"{slug}: assessment has no {key}")

    categories = assessment.get("categories") or {}
    missing = [u for u in use_cases if u not in categories]
    unknown = sorted(set(categories) - set(use_cases))
    if missing:
        problems.append(f"{slug}: categories not assessed: {missing}")
    if unknown:
        problems.append(f"{slug}: unknown categories: {unknown}")

    fits = {f["use_case_slug"]: f for f in robot.get("use_case_fits") or []}
    for use_case in use_cases:
        entry = categories.get(use_case)
        if entry is None:
            continue
        where = f"{slug}/{use_case}"
        status = entry.get("status")
        if status not in STATUSES:
            problems.append(f"{where}: status {status!r} not in {sorted(STATUSES)}")
            continue
        if not (entry.get("basis") or "").strip():
            problems.append(f"{where}: no basis stated")
        if status == "FIT":
            if use_case not in fits:
                problems.append(f"{where}: assessed FIT but the robot file has no fit row")
            sources = entry.get("sources") or []
            if not sources:
                problems.append(f"{where}: a FIT names its sources")
            for url in sources:
                if url not in raw:
                    problems.append(f"{where}: {url} is not a recorded source of this robot")
        elif use_case in fits:
            problems.append(f"{where}: fit row present but assessed {status}")

    # Rule 3: a fit records its limitations and, when the robot's maturity is known, its
    # readiness. The score may stay NULL: unknown suitability stays unknown.
    for use_case, fit in fits.items():
        where = f"{slug}/{use_case}"
        if not (fit.get("limitations") or "").strip():
            problems.append(f"{where}: a fit states its limitations")
        if robot.get("commercial_status") not in (None, "UNKNOWN"):
            if fit.get("commercial_readiness") not in COMMERCIAL_STATUSES:
                problems.append(f"{where}: a fit records commercial readiness")
    return problems


def test_every_robot_outside_the_baseline_has_a_complete_assessment():
    problems = []
    for slug, robot in ROBOTS.items():
        if slug in BASELINE:
            continue
        problems += assessment_problems(slug, robot, RAW[slug], ASSESSMENTS.get(slug), USE_CASES)
    assert not problems, "\n".join(problems)


def test_every_assessment_belongs_to_exactly_one_robot_record():
    """An assessment is linked to the exact model or edition by its file name: each edition
    file (e.g. unitree-r1-edu-u2) is its own record and needs its own assessment."""
    orphans = sorted(set(ASSESSMENTS) - set(ROBOTS))
    assert not orphans, f"assessments without a robot record: {orphans}"


def test_the_legacy_baseline_only_shrinks():
    assert len(BASELINE) == len(set(BASELINE)), "duplicate baseline entries"
    assert len(BASELINE) <= BASELINE_FROZEN_SIZE, (
        "the legacy baseline may not grow; assess the new robot instead"
    )
    assert not sorted(set(BASELINE) - set(ROBOTS)), sorted(set(BASELINE) - set(ROBOTS))
    stale = sorted(set(BASELINE) & set(ASSESSMENTS))
    assert not stale, f"assessed robots still on the legacy baseline (remove them): {stale}"


# --- the check itself detects what it must detect (synthetic records) -------------------

_SOURCE = "https://example.com/robot-x/factory-pilot"
_ROBOT = {
    "slug": "robot-x",
    "commercial_status": "PILOT",
    "use_case_fits": [{
        "use_case_slug": "manufacturing", "fit_score": None, "is_primary": True,
        "commercial_readiness": "PILOT", "notes": "Factory pilot.", "limitations": "Pilot only.",
    }],
}
_RAW = json.dumps(_ROBOT) + _SOURCE


def _assessment(**overrides) -> dict:
    categories = {u: {"status": "NO_BASIS", "basis": "Nothing recorded."} for u in USE_CASES}
    categories["manufacturing"] = {"status": "FIT", "basis": "Pilot.", "sources": [_SOURCE]}
    base = {"robot_slug": "robot-x", "assessed_on": "2026-10-24", "method": "test",
            "categories": categories}
    base.update(overrides)
    return base


def _problems(assessment, robot=_ROBOT, raw=_RAW):
    return assessment_problems("robot-x", robot, raw, assessment, USE_CASES)


def test_a_complete_assessment_passes():
    assert _problems(_assessment()) == []


def test_a_new_robot_without_an_assessment_is_detected():
    assert _problems(None) == [
        "robot-x: no use-case assessment (use_case_assessments/robot-x.json)"
    ]


def test_a_robot_with_no_fit_is_valid_when_the_reason_is_documented():
    robot = {**_ROBOT, "use_case_fits": []}
    categories = {u: {"status": "NO_BASIS", "basis": "Nothing recorded."} for u in USE_CASES}
    assert _problems(_assessment(categories=categories), robot=robot) == []


def test_every_category_must_be_rated():
    a = _assessment()
    del a["categories"]["home"]
    assert any("not assessed: ['home']" in p for p in _problems(a))


def test_a_fit_without_a_fit_row_and_a_row_without_a_fit_are_detected():
    a = _assessment()
    a["categories"]["home"] = {"status": "FIT", "basis": "x", "sources": [_SOURCE]}
    a["categories"]["manufacturing"] = {"status": "UNSUPPORTED_POSSIBILITY", "basis": "x"}
    problems = _problems(a)
    assert any("home: assessed FIT but the robot file has no fit row" in p for p in problems)
    assert any("manufacturing: fit row present but assessed UNSUPPORTED_POSSIBILITY" in p
               for p in problems)


def test_a_fit_source_must_already_be_recorded_for_that_robot():
    a = _assessment()
    a["categories"]["manufacturing"]["sources"] = ["https://example.com/unrecorded"]
    assert any("not a recorded source" in p for p in _problems(a))


def test_an_assessment_names_the_exact_robot():
    problems = _problems(_assessment(robot_slug="robot-x-pro"))
    assert any("names robot 'robot-x-pro'" in p for p in problems)


def test_a_fit_without_readiness_or_limitations_is_detected():
    fit = {**_ROBOT["use_case_fits"][0], "commercial_readiness": None, "limitations": ""}
    problems = _problems(_assessment(), robot={**_ROBOT, "use_case_fits": [fit]})
    assert any("states its limitations" in p for p in problems)
    assert any("records commercial readiness" in p for p in problems)
