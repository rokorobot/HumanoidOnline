"""Manufacturer profiles: every company claim is attributed; unknown stays unknown.

The manufacturer profile used to state things it had no basis for: the importer
filled `is_public_company = FALSE` for every record without a listing claim, so
"not researched" rendered as "PUBLIC CO.: NO", and a single identity row stood
behind whatever the record said. These tests pin the catalogue contract that
replaces that (migration 0013, docs/03 §8):

* every asserted company fact is named by at least one evidence row's
  `claim_fields`, so each field can be traced to a source;
* agent-assisted research rows carry the docs/26 provenance statement and are
  never marked verified;
* listing status is three-state, a ticker only accompanies a listed entity, and
  a parent's listing only accompanies a named parent;
* the importer passes NULL listing status and claim fields through unchanged.

No database: the catalogue files are the thing under test, and the importer's
statement shape is asserted with a recording cursor.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE = REPO_ROOT / "db" / "catalogue"

_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO_ROOT / "db" / "import_catalogue.py"
)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)

MANUFACTURERS = json.loads((CATALOGUE / "manufacturers.json").read_text(encoding="utf-8"))[
    "manufacturers"
]
REGION_CODES = {
    r["code"]
    for r in json.loads((CATALOGUE / "regions.json").read_text(encoding="utf-8"))["regions"]
}
ROBOT_MAKERS = {
    json.loads(p.read_text(encoding="utf-8"))["manufacturer_slug"]
    for p in (CATALOGUE / "robots").glob("*.json")
}

#: Company facts that must be attributed whenever they are asserted.
ATTRIBUTED_FIELDS = (
    "legal_name", "country_region_code", "headquarters_city", "incorporation",
    "operating_locations", "founded_year", "description", "target_markets",
    "commercial_model", "deployment_status", "deployment_note",
    "is_public_company", "ticker", "parent_company", "parent_listing",
    "parent_relationship",
)
CLAIMABLE_FIELDS = set(ATTRIBUTED_FIELDS) | {"website_url"}
COMMERCIAL_STATUSES = {
    "UNKNOWN", "ANNOUNCED", "DEVELOPMENT", "PROTOTYPE", "PILOT", "EARLY_ACCESS",
    "LIMITED_COMMERCIAL", "COMMERCIAL", "RAAS_DEPLOYMENT", "DISCONTINUED",
}
AGENT_PREFIX = "RETRIEVAL: AGENT_ASSISTED_RESEARCH (docs/26)"


def _asserted(m: dict, field: str) -> bool:
    value = m.get(field)
    if value is None or value == [] or value == "":
        return False
    # UNKNOWN is the explicit absence of a status claim (docs/03 §7).
    return not (field == "deployment_status" and value == "UNKNOWN")


def _ids(m: dict) -> str:
    return m["slug"]


def test_every_manufacturer_with_catalogue_records_has_one_profile() -> None:
    slugs = [m["slug"] for m in MANUFACTURERS]
    assert len(slugs) == len(set(slugs)), "duplicate manufacturer slug"
    assert ROBOT_MAKERS <= set(slugs), ROBOT_MAKERS - set(slugs)


@pytest.mark.parametrize("m", MANUFACTURERS, ids=_ids)
def test_every_asserted_company_fact_names_a_source(m: dict) -> None:
    claimed = {f for ev in m.get("evidence", []) for f in (ev.get("claim_fields") or [])}
    unattributed = [f for f in ATTRIBUTED_FIELDS if _asserted(m, f) and f not in claimed]
    assert not unattributed, f"{m['slug']}: no source names {unattributed}"


@pytest.mark.parametrize("m", MANUFACTURERS, ids=_ids)
def test_claim_fields_name_real_profile_fields(m: dict) -> None:
    for ev in m.get("evidence", []):
        unknown = set(ev.get("claim_fields") or []) - CLAIMABLE_FIELDS
        assert not unknown, f"{m['slug']}: unknown claim_fields {unknown}"


@pytest.mark.parametrize("m", MANUFACTURERS, ids=_ids)
def test_agent_research_rows_are_labelled_and_never_verified(m: dict) -> None:
    for ev in m.get("evidence", []):
        note = ev.get("note") or ""
        if not note.startswith(AGENT_PREFIX):
            continue
        assert ev.get("verified_at") is None, f"{m['slug']}: agent row marked verified"
        assert ev.get("confidence") != "VERIFIED"
        assert "Not a MANUAL_BOOTSTRAP reading. Not human-verified." in note
        assert ev.get("observed_at"), f"{m['slug']}: agent row without a check date"
        assert ev.get("source_url"), f"{m['slug']}: agent row without an exact URL"


@pytest.mark.parametrize("m", MANUFACTURERS, ids=_ids)
def test_listing_status_is_three_state_and_scoped_to_the_entity(m: dict) -> None:
    listed = m.get("is_public_company")
    assert listed in (True, False, None)
    if m.get("ticker"):
        assert listed is True, f"{m['slug']}: a ticker on an entity not recorded as listed"
    # A parent's listing never stands in for the entity's own status.
    if m.get("parent_listing") or m.get("parent_relationship"):
        assert m.get("parent_company"), f"{m['slug']}: parent detail without a parent"


@pytest.mark.parametrize("m", MANUFACTURERS, ids=_ids)
def test_headquarters_and_status_use_canonical_vocabularies(m: dict) -> None:
    code = m.get("country_region_code")
    assert code is None or code in REGION_CODES, f"{m['slug']}: unknown region {code}"
    status = m.get("deployment_status")
    assert status is None or status in COMMERCIAL_STATUSES
    if m.get("headquarters_city"):
        assert code, f"{m['slug']}: headquarters city without a headquarters country"


# --- importer -----------------------------------------------------------------

class _RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(str(sql).split()), tuple(params or ())))
        return self

    def fetchone(self):
        return (1,)

    def insert(self, table: str) -> tuple[list[str], tuple]:
        for sql, params in self.calls:
            match = re.match(rf"INSERT INTO {table} \((.*?)\) VALUES", sql)
            if match:
                return [c.strip() for c in match.group(1).split(",")], params
        raise AssertionError(f"no INSERT INTO {table}")


def test_importer_writes_missing_listing_status_as_null_not_false() -> None:
    cur = _RecordingCursor()
    ic.import_manufacturers(
        cur,
        {"manufacturers": [{"slug": "unlisted-unknown", "name": "Unknown Co", "evidence": []}]},
        lambda code: None,
    )
    cols, params = cur.insert("manufacturer")
    assert params[cols.index("is_public_company")] is None


def test_importer_carries_profile_fields_and_claim_fields_through() -> None:
    cur = _RecordingCursor()
    record = {
        "slug": "sourced-co",
        "name": "Sourced Co",
        "headquarters_city": "Testville",
        "incorporation": "United States (Delaware)",
        "operating_locations": ["Plant A"],
        "deployment_status": "PILOT",
        "deployment_note": "Customer trial",
        "is_public_company": False,
        "parent_company": "Group Co",
        "parent_listing": "NYSE: GRP",
        "parent_relationship": "Controlling shareholder",
        "evidence": [
            {
                "source_type": "OTHER",
                "source_url": "https://example.test/filing",
                "observed_at": "2026-09-13",
                "claim_fields": ["is_public_company", "parent_company"],
            }
        ],
    }
    ic.import_manufacturers(cur, {"manufacturers": [record]}, lambda code: None)

    cols, params = cur.insert("manufacturer")
    for field in (
        "headquarters_city", "incorporation", "operating_locations", "deployment_status",
        "deployment_note", "is_public_company", "parent_company", "parent_listing",
        "parent_relationship",
    ):
        assert params[cols.index(field)] == record[field], field

    ev_cols, ev_params = cur.insert("evidence_source")
    assert ev_params[ev_cols.index("claim_fields")] == ["is_public_company", "parent_company"]


def test_the_whole_manufacturer_catalogue_imports_through_the_upsert() -> None:
    cur = _RecordingCursor()

    def region_id(code):
        assert code is None or code in REGION_CODES
        return None

    ic.import_manufacturers(cur, {"manufacturers": MANUFACTURERS}, region_id)
    upserts = [sql for sql, _ in cur.calls if sql.startswith("INSERT INTO manufacturer")]
    assert len(upserts) == len(MANUFACTURERS)
