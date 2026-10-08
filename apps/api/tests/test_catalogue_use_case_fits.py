"""Use-case fits in the catalogue files: shape, provenance and coverage.

File-level (no database). A `use_case_fit` row has no `evidence_source` linkage in
the schema, so the only place a fit can be held to its evidence is here, against
the robot file it lives in:

* a fit names a use case that exists, a score the DDL accepts (or NULL = not
  rated), and a readiness that is a `commercial_status` label (or NULL);
* a fit never claims more maturity than the robot itself records;
* a fit agrees with the robot's own recorded deployments;
* any source a fit note cites is a source already recorded in that robot's file;
* published, commercially accessible robots with no use case are REPORTED and
  kept on a reviewed register below. Incomplete coverage never fails the run
  (owner decision D5, 2026-10-08); only an inaccurate register does. A gap is
  closed by finding evidence, never by inventing a fit (AGENTS.md rule 6).

A fit on an unpublished robot is allowed when its file supports it; the public
API filters by publication (tests/test_use_case_fit_safeguards.py).

See docs/audit/USE_CASE_ENRICHMENT_REVIEW_2026-10-08.md.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE = REPO_ROOT / "db" / "catalogue"
SCHEMA = REPO_ROOT / "db" / "schema.sql"

ROBOTS = {
    p.stem: json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((CATALOGUE / "robots").glob("*.json"))
}
RAW = {p.stem: p.read_text(encoding="utf-8") for p in sorted((CATALOGUE / "robots").glob("*.json"))}
USE_CASES = {
    u["slug"]
    for u in json.loads((CATALOGUE / "use_cases.json").read_text(encoding="utf-8"))["use_cases"]
}

#: Published, commercially accessible robots with no use case (reviewed 2026-10-08).
#: Remove a slug when a sourced use case is recorded for it; add one only with an
#: entry in the review document.
KNOWN_COVERAGE_GAPS = {
    # Use cases for this robot are a governed claim kind with NO_CATALOGUE_HOME
    # (DR-A5 section 18.5; field_policy.NO_HOME_KINDS): accepted with provenance,
    # never materialized, and its interface rows derive no capability. A fit here
    # needs a change to that boundary, which is a separate owner decision.
    "4ne1-mini",
}

NON_ACCESSIBLE = {"NOT_AVAILABLE", "DISCONTINUED"}


def _commercial_status_labels() -> set[str]:
    sql = re.sub(r"--[^\n]*", "", SCHEMA.read_text(encoding="utf-8"))
    body = re.search(r"CREATE TYPE commercial_status AS ENUM \((.*?)\);", sql, flags=re.S)
    assert body, "commercial_status enum not found in db/schema.sql"
    return set(re.findall(r"'([^']+)'", body.group(1)))


def commercially_accessible(robot: dict) -> bool:
    """The canonical predicate (db/schema.sql `robot_commercial_snapshot.is_obtainable`):
    a current NEW availability offer whose status is not NOT_AVAILABLE/DISCONTINUED."""
    return any(
        o.get("is_current", True)
        and o.get("condition", "NEW") == "NEW"
        and o["availability_status"] not in NON_ACCESSIBLE
        for o in robot.get("availability_offers") or []
    )


def coverage_gaps(robots: dict[str, dict]) -> set[str]:
    """Published + commercially accessible robots with no use case at all."""
    return {
        slug
        for slug, r in robots.items()
        if r.get("is_published") and commercially_accessible(r) and not r.get("use_case_fits")
    }


def _fits():
    for slug, robot in ROBOTS.items():
        for fit in robot.get("use_case_fits") or []:
            yield slug, robot, fit


def test_there_are_fits_to_check():
    assert sum(1 for _ in _fits()) >= 9


def test_fit_shape_matches_the_schema():
    statuses = _commercial_status_labels()
    for slug, _, fit in _fits():
        where = f"{slug}/{fit.get('use_case_slug')}"
        assert fit["use_case_slug"] in USE_CASES, where
        score = fit.get("fit_score")
        assert score is None or (isinstance(score, (int, float)) and 0 <= score <= 1), where
        readiness = fit.get("commercial_readiness")
        assert readiness is None or readiness in statuses, where
        assert (fit.get("notes") or "").strip(), f"{where}: a fit states its basis"
        assert (fit.get("limitations") or "").strip(), f"{where}: a fit states its limits"
    for slug, robot in ROBOTS.items():
        slugs = [f["use_case_slug"] for f in robot.get("use_case_fits") or []]
        assert len(slugs) == len(set(slugs)), f"{slug}: one row per use case (PK robot+use_case)"
        primaries = [f for f in robot.get("use_case_fits") or [] if f.get("is_primary")]
        assert len(primaries) <= 1, f"{slug}: at most one primary use case"


def test_healthcare_fits_never_read_as_a_clinical_claim():
    """Healthcare & Rehabilitation rows are research or positioning. Each one says in
    its public limitation that no clinical validation or approval is recorded."""
    rows = [(s, f) for s, _, f in _fits() if f["use_case_slug"] == "healthcare-rehabilitation"]
    assert rows
    for slug, fit in rows:
        assert "No clinical validation or regulatory approval" in fit["limitations"], slug
        assert not fit.get("is_primary"), slug


def test_governed_records_gain_no_fit_from_the_new_categories():
    for slug in ("4ne1-mini", "xpeng-iron"):
        assert ROBOTS[slug]["use_case_fits"] == [], slug


def test_fit_readiness_never_exceeds_the_robots_own_status():
    """Suitability is not readiness: a fit may leave readiness unknown (NULL), but
    when it states one it is the robot's recorded commercial status, never a
    stronger claim made up for the use case."""
    for slug, robot, fit in _fits():
        readiness = fit.get("commercial_readiness")
        if readiness is not None:
            assert readiness == robot["commercial_status"], (
                f"{slug}/{fit['use_case_slug']}: readiness {readiness} "
                f"!= commercial_status {robot['commercial_status']}"
            )


def test_unknown_maturity_never_becomes_a_readiness_claim():
    for slug, robot, fit in _fits():
        if robot["commercial_status"] == "UNKNOWN":
            assert fit.get("commercial_readiness") is None, slug


def test_recorded_deployments_have_a_matching_fit():
    for slug, robot in ROBOTS.items():
        fit_slugs = {f["use_case_slug"] for f in robot.get("use_case_fits") or []}
        for d in robot.get("deployments") or []:
            uc = d.get("use_case_slug")
            if uc is not None:
                assert uc in fit_slugs, f"{slug}: deployment in {uc} without a {uc} fit"


def test_a_source_cited_in_a_fit_note_is_recorded_in_that_robots_file():
    """A fit has no evidence_source row of its own, so a URL it cites must already
    be a recorded source of the same robot — no new, unreviewed source enters the
    catalogue through a fit note."""
    url = re.compile(r"https?://[^\s)\"']+")
    for slug, _, fit in _fits():
        text = f"{fit.get('notes') or ''} {fit.get('limitations') or ''}"
        for cited in url.findall(text):
            cited = cited.rstrip(".,;")
            without_fits = RAW[slug]
            for field in ("notes", "limitations"):
                without_fits = without_fits.replace(json.dumps(fit[field], ensure_ascii=False), "")
            assert cited in without_fits, f"{slug}: {cited} is not a recorded source of this robot"


def test_the_reviewed_gap_register_is_accurate():
    """Integrity of the register itself (blocking): every listed slug is a real,
    published, commercially accessible robot that still has no use case. A stale
    entry would hide a robot that has since been covered or withdrawn."""
    gaps = coverage_gaps(ROBOTS)
    assert KNOWN_COVERAGE_GAPS <= set(ROBOTS), sorted(KNOWN_COVERAGE_GAPS - set(ROBOTS))
    assert KNOWN_COVERAGE_GAPS <= gaps, (
        f"listed as a gap but no longer one: {sorted(KNOWN_COVERAGE_GAPS - gaps)}"
    )


def test_unreviewed_coverage_gaps_are_reported_not_blocking():
    """Owner decision D5 (2026-10-08): incomplete use-case coverage is REPORTED,
    never a blocking condition. An accessible robot with no use case that is not
    yet on the reviewed register raises a warning in the test output; it does not
    fail the run. A gap is closed by evidence, never by a deadline."""
    unreviewed = coverage_gaps(ROBOTS) - KNOWN_COVERAGE_GAPS
    if unreviewed:
        warnings.warn(
            "use-case coverage: commercially accessible robot(s) with no use case and "
            f"no entry in the reviewed gap register: {sorted(unreviewed)}",
            stacklevel=1,
        )


# ---- the check itself, on synthetic data ---------------------------------

def _robot(*, published=True, offers=(), fits=()):
    return {
        "is_published": published,
        "availability_offers": [dict(o) for o in offers],
        "use_case_fits": [dict(f) for f in fits],
    }


AVAILABLE = {"availability_status": "AVAILABLE"}
FIT = {"use_case_slug": "home", "fit_score": None}


def test_coverage_check_flags_only_accessible_published_robots_without_a_fit():
    robots = {
        "gap": _robot(offers=[AVAILABLE]),
        "covered": _robot(offers=[AVAILABLE], fits=[FIT]),
        "unrated-still-covers": _robot(offers=[{"availability_status": "ON_REQUEST"}], fits=[FIT]),
        "unpublished": _robot(published=False, offers=[AVAILABLE]),
        "no-offer": _robot(),
    }
    assert coverage_gaps(robots) == {"gap"}


def test_coverage_check_uses_the_canonical_accessibility_predicate():
    robots = {
        "waitlist-counts": _robot(offers=[{"availability_status": "WAITLIST"}]),
        "not-available": _robot(offers=[{"availability_status": "NOT_AVAILABLE"}]),
        "discontinued": _robot(offers=[{"availability_status": "DISCONTINUED"}]),
        "retired-offer": _robot(offers=[{**AVAILABLE, "is_current": False}]),
        "used-only": _robot(offers=[{**AVAILABLE, "condition": "USED"}]),
        "one-live-offer-is-enough": _robot(
            offers=[{**AVAILABLE, "is_current": False}, AVAILABLE]
        ),
    }
    assert coverage_gaps(robots) == {"waitlist-counts", "one-live-offer-is-enough"}


# ---- owner decisions of 2026-10-08, pinned ---------------------------------

def test_g1_basic_is_associated_but_not_rated_for_research_education():
    """D1: the base G1 has no secondary development, so its Research & Education
    association carries no score, and the note no longer claims SDK support."""
    robot = ROBOTS["unitree-g1"]
    [fit] = [f for f in robot["use_case_fits"] if f["use_case_slug"] == "research-education"]
    assert fit["fit_score"] is None
    assert "SDK/ROS support make" not in fit["notes"]
    assert "does not offer secondary development" in fit["notes"]
    assert "No secondary development" in fit["limitations"]
    assert robot["commercial_status"] == "COMMERCIAL"      # maturity untouched
    assert robot["specs"]["has_sdk"] is not True            # the record never claimed an SDK


def test_4ne1_mini_carries_no_use_case_row_while_its_use_cases_have_no_catalogue_home():
    """D2 was conditional on compatibility with the claim-governance boundary. It is
    not compatible: DR-A5 registers this robot's use cases as NO_CATALOGUE_HOME."""
    policy = (REPO_ROOT / "apps/api/app/services/discovery/field_policy.py").read_text(
        encoding="utf-8")
    block = policy[policy.index("NO_HOME_KINDS = {"):]
    assert '"USE_CASES": "use_cases"' in block[: block.index("}")]
    assert ROBOTS["4ne1-mini"]["use_case_fits"] == []
    assert "4ne1-mini" in KNOWN_COVERAGE_GAPS
