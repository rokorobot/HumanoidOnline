"""Catalogue authoring — stub generation and hand entry of specifications.

The catalogue is hand-authored JSON, and this tool writes it. The risk is
therefore not a crashed import but a *plausible wrong file*: a duplicated
manufacturer, a slug that silently shadows an existing robot, or a specification
that arrives with no record of where it came from. These tests are written
against those, not against the happy path.

No database: this operates purely on repository files.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "catalogue_entries", REPO_ROOT / "db" / "catalogue_entries.py"
)
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)


# --- slugs -------------------------------------------------------------------

@pytest.mark.parametrize(
    "manufacturer,robot,expected",
    [
        # matches the catalogue's own existing slugs
        ("Unitree Robotics", "G1", "unitree-g1"),
        ("Agility Robotics", "Digit", "agility-digit"),
        ("Engineered Arts", "Ameca", "engineered-arts-ameca"),
        ("1X Technologies", "NEO", "1x-neo"),
        # the brand is not repeated when the model already carries it
        ("Figure AI", "Figure 01", "figure-01"),
        ("Figure AI", "Figure 03", "figure-03"),
        # `dynamics` is part of the brand, not a corporate suffix
        ("Boston Dynamics", "Atlas", "boston-dynamics-atlas"),
        ("LimX Dynamics", "CL-1", "limx-dynamics-cl-1"),
    ],
)
def test_slugs_follow_the_catalogues_own_convention(manufacturer, robot, expected):
    assert ce.robot_slug(manufacturer, robot) == expected


def test_brand_token_keeps_dynamics_but_drops_corporate_words():
    assert ce.brand_token("boston-dynamics") == "boston-dynamics"
    assert ce.brand_token("unitree-robotics") == "unitree"
    assert ce.brand_token("1x-technologies") == "1x"


# --- planning ----------------------------------------------------------------

def test_the_plan_skips_robots_already_in_the_catalogue():
    plan = ce.plan_stubs("humanoid_radar_v1")
    skipped = {s["name"] for s in plan["skipped"]}
    assert {"G1", "H1", "Digit", "Apollo", "NEO", "Ameca"} <= skipped
    new = {r["slug"] for r in plan["robots"]}
    assert not (new & set(ce.existing_robots()))


def test_a_manufacturer_is_matched_by_slug_as_well_as_name():
    """The catalogue calls it "Figure" with slug `figure-ai`; the bootstrap says
    "Figure AI". Matching on name alone appends a second manufacturer whose slug
    collides with the first."""
    plan = ce.plan_stubs("humanoid_radar_v1")
    proposed = [m["slug"] for m in plan["manufacturers"]]
    existing = {m["slug"] for m in ce.load_manufacturers()["manufacturers"]}
    assert not (set(proposed) & existing)
    assert len(proposed) == len(set(proposed))  # and no duplicates among themselves


def test_planning_writes_nothing():
    before = sorted(p.name for p in ce.ROBOTS_DIR.glob("*.json"))
    ce.plan_stubs("humanoid_radar_v1")
    assert sorted(p.name for p in ce.ROBOTS_DIR.glob("*.json")) == before


def test_an_unknown_dataset_is_refused():
    with pytest.raises(ce.AuthoringError, match="no dataset"):
        ce.plan_stubs("does-not-exist")


# --- the stub itself ---------------------------------------------------------

def test_a_stub_asserts_identity_and_nothing_else():
    stub = ce.make_stub(slug="x-1", name="1", mfr_slug="x", official_url="https://x.invalid/")
    assert all(v is None for v in stub["specs"].values())
    assert stub["specs_note"] == ce.UNVERIFIED_NOTE
    # no commercial claim => nothing for G2 to demand evidence of
    assert stub["commercial_status"] == "ANNOUNCED"
    assert stub["commercial_status_evidence"] == []
    assert stub["pricing_offers"] == stub["availability_offers"] == stub["deployments"] == []
    assert stub["images"] == []


def test_a_stub_is_never_published():
    """Authoring is not publishing. A sparse profile going live is a product
    decision, never a side effect of creating the file."""
    stub = ce.make_stub(slug="x-1", name="1", mfr_slug="x", official_url=None)
    assert stub["is_published"] is False


def test_every_shipped_stub_is_unpublished_and_specless():
    """Guards the 36 files actually in the tree, not just the constructor."""
    unpublished_stubs = [
        (slug, r) for slug, r in ce.existing_robots().items()
        if r.get("specs_note") == ce.UNVERIFIED_NOTE
    ]
    assert len(unpublished_stubs) >= 36
    for slug, robot in unpublished_stubs:
        assert robot["is_published"] is False, slug
        assert all(v is None for v in robot["specs"].values()), slug
        assert robot["commercial_status_evidence"] == [], slug


def test_write_refuses_to_overwrite_an_existing_robot():
    existing = next(iter(ce.existing_robots()))
    plan = {"robots": [ce.make_stub(slug=existing, name="x", mfr_slug="y",
                                    official_url=None)],
            "manufacturers": [], "skipped": []}
    with pytest.raises(ce.AuthoringError, match="refusing to overwrite"):
        ce.write_stubs(plan)


# --- specification entry -----------------------------------------------------

def _sheet(slug: str, **over) -> dict:
    block = {"slug": slug, "source_url": "https://oem.invalid/x",
             "retrieved_on": "2026-07-30", "specs": dict.fromkeys(ce.SPEC_FIELDS)}
    block.update(over)
    return {"worksheet_version": ce.WORKSHEET_VERSION, "robots": [block]}


def _some_stub() -> str:
    return next(slug for slug, r in ce.existing_robots().items()
                if r.get("specs_note") == ce.UNVERIFIED_NOTE)


def test_an_unattributed_entry_is_refused():
    with pytest.raises(ce.AuthoringError, match="named operator"):
        ce.apply_worksheet(_sheet(_some_stub()), operator="  ")


def test_a_stale_worksheet_version_is_refused():
    sheet = _sheet(_some_stub())
    sheet["worksheet_version"] = 0
    with pytest.raises(ce.AuthoringError, match="worksheet version"):
        ce.apply_worksheet(sheet, operator="ops@h.co")


def test_a_changed_spec_without_a_source_is_refused():
    slug = _some_stub()
    sheet = _sheet(slug, source_url="", specs={**dict.fromkeys(ce.SPEC_FIELDS),
                                               "height_cm": 170})
    with pytest.raises(ce.AuthoringError, match="source_url and"):
        ce.apply_worksheet(sheet, operator="ops@h.co")


def test_a_malformed_retrieval_date_is_refused():
    slug = _some_stub()
    sheet = _sheet(slug, retrieved_on="30/07/2026",
                   specs={**dict.fromkeys(ce.SPEC_FIELDS), "height_cm": 170})
    with pytest.raises(ce.AuthoringError, match="YYYY-MM-DD"):
        ce.apply_worksheet(sheet, operator="ops@h.co")


@pytest.mark.parametrize("value", [0, -1, 0.0])
def test_a_zero_or_negative_measurement_is_refused(value):
    """Almost always a mis-keyed UNKNOWN, and a robot 0 cm tall is worse than a
    robot of unknown height."""
    slug = _some_stub()
    sheet = _sheet(slug, specs={**dict.fromkeys(ce.SPEC_FIELDS), "height_cm": value})
    with pytest.raises(ce.AuthoringError, match="not a plausible measurement"):
        ce.apply_worksheet(sheet, operator="ops@h.co")


def test_an_out_of_range_enum_is_refused():
    slug = _some_stub()
    sheet = _sheet(slug, specs={**dict.fromkeys(ce.SPEC_FIELDS), "mobility": "HOVERING"})
    with pytest.raises(ce.AuthoringError, match="is not one of"):
        ce.apply_worksheet(sheet, operator="ops@h.co")


def test_a_non_boolean_flag_is_refused():
    slug = _some_stub()
    sheet = _sheet(slug, specs={**dict.fromkeys(ce.SPEC_FIELDS), "has_sdk": "yes"})
    with pytest.raises(ce.AuthoringError, match="expected true/false/null"):
        ce.apply_worksheet(sheet, operator="ops@h.co")


def test_an_unknown_robot_is_refused():
    with pytest.raises(ce.AuthoringError, match="no such catalogue robot"):
        ce.apply_worksheet(_sheet("not-a-robot"), operator="ops@h.co")


def test_leaving_everything_null_changes_nothing_and_needs_no_source():
    """Null is UNKNOWN and is always the honest answer, so an untouched block
    must not demand provenance for a fact it never asserted."""
    result = ce.apply_worksheet(_sheet(_some_stub(), source_url="", retrieved_on=""),
                                operator="ops@h.co")
    assert result["changed"] == []


def test_a_dry_run_reports_the_change_without_writing(tmp_path):
    slug = _some_stub()
    path = ce.ROBOTS_DIR / f"{slug}.json"
    before = path.read_text(encoding="utf-8")
    sheet = _sheet(slug, specs={**dict.fromkeys(ce.SPEC_FIELDS), "height_cm": 170,
                                "mobility": "BIPEDAL"})

    result = ce.apply_worksheet(sheet, operator="ops@h.co", dry_run=True)

    assert result["dry_run"] is True
    assert result["changed"][0]["fields"] == {"height_cm": 170.0, "mobility": "BIPEDAL"}
    assert path.read_text(encoding="utf-8") == before


def test_the_export_carries_every_field_and_no_decision():
    sheet = ce.export_worksheet()
    block = sheet["robots"][0]
    assert set(block["specs"]) == set(ce.SPEC_FIELDS)
    assert block["source_url"] == "" and block["retrieved_on"] == ""


def test_the_catalogue_still_declares_one_file_per_robot():
    """A stub that shadowed an existing slug would silently replace a verified
    robot; the file set and the slug set must stay in step."""
    robots = ce.existing_robots()
    assert len(robots) == len(list(ce.ROBOTS_DIR.glob("*.json")))
    for slug, robot in robots.items():
        assert robot["slug"] == slug


def test_every_robot_names_a_manufacturer_that_exists():
    known = {m["slug"] for m in ce.load_manufacturers()["manufacturers"]}
    for slug, robot in ce.existing_robots().items():
        assert robot["manufacturer_slug"] in known, slug
