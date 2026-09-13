"""Company-evidence ownership against real Postgres.

An unmarked MANUFACTURER evidence row (``managed_by IS NULL``) may have been
written by an import that predates migration 0013's marker, or by someone by
hand — and nothing in a row's content tells those apart. A row identical to a
catalogue source is not proof the importer wrote it. So the importer takes
ownership of NO unmarked row: every one is preserved exactly (content,
ownership, subject), the catalogue keeps its own marked copy separately beside
it, and an unmarked row sharing a source's URL, type and observed date is
reported as a collision that asserts no ownership.

Each test runs the importer's real SQL inside one transaction that is rolled
back, so the shared database is left exactly as found and no seed fact changes.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO_ROOT / "db" / "import_catalogue.py"
)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)

#: A company source as an import before migration 0013 would have written it.
UNMARKED_SOURCE = {
    "source_url": "https://example.test/collision/company-profile",
    "source_type": "MANUFACTURER_SITE",
    "source_title": "Example Robotics official site",
    "excerpt": None,
    "published_at": None,
    "observed_at": "2026-07-24",
    "verified_at": "2026-07-24",
    "confidence": "HIGH",
    "note": "Company identity sourced from the official manufacturer site.",
}
#: The same source as the catalogue carries it today (now field-attributed).
CATALOGUE_SOURCE = {**UNMARKED_SOURCE, "claim_fields": ["legal_name"]}

ROW_COLUMNS = (
    "id, subject_type, subject_id, source_url, source_type, source_title, excerpt, "
    "published_at, observed_at, verified_at, confidence, note, claim_fields, managed_by, "
    "created_at"
)


@pytest.fixture
def cur(database_url):
    conn = psycopg.connect(ic.normalize_url(database_url), autocommit=False)
    cursor = conn.cursor()
    cursor.execute("SET search_path TO humanoid, public")
    try:
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def _manufacturer(cur) -> tuple[str, object]:
    slug = f"collision-maker-{uuid.uuid4().hex[:10]}"
    mid = cur.execute(
        "INSERT INTO manufacturer (slug, name) VALUES (%s, %s) RETURNING id",
        (slug, f"Collision Robotics {slug[-6:]}"),
    ).fetchone()[0]
    return slug, mid


def _unmarked_row(cur, mid, **overrides) -> object:
    row = {**UNMARKED_SOURCE, **overrides}
    ic.insert_evidence(cur, "MANUFACTURER", mid, row)
    return cur.execute(
        "SELECT id FROM evidence_source WHERE subject_id=%s ORDER BY created_at DESC, id LIMIT 1",
        (mid,),
    ).fetchone()[0]


def _row(cur, evidence_id):
    return cur.execute(
        f"SELECT {ROW_COLUMNS} FROM evidence_source WHERE id=%s", (evidence_id,)
    ).fetchone()


def _import(cur, slug, sources):
    data = {"manufacturers": [{"slug": slug, "name": "Collision Robotics", "evidence": sources}]}
    return ic.import_manufacturers(cur, data, lambda code: None)


def _managed_rows(cur, mid):
    return cur.execute(
        "SELECT id, source_url, claim_fields FROM evidence_source "
        "WHERE subject_type='MANUFACTURER' AND subject_id=%s AND managed_by = %s",
        (mid, ic.MANAGED_BY),
    ).fetchall()


def _assert_preserved_and_reported(cur, slug, mid, manual_id, runs) -> None:
    before = _row(cur, manual_id)
    results = [_import(cur, slug, [CATALOGUE_SOURCE]) for _ in range(runs)]

    # Content, ownership (still unmarked) and subject are exactly as before.
    assert _row(cur, manual_id) == before
    for result in results:
        assert "adopted" not in result
        assert len(result["collisions"]) == 1
        line = result["collisions"][0]
        assert slug in line and UNMARKED_SOURCE["source_url"] in line
        assert "ownership not assumed" in line
        assert "importer" not in line  # the report claims no authorship
    # The catalogue's own copy is kept separately, exactly once, however many runs.
    managed = _managed_rows(cur, mid)
    assert len(managed) == 1
    assert managed[0][2] == ["legal_name"]


def test_exact_content_unmarked_row_is_preserved_not_adopted(cur) -> None:
    """Identical to the catalogue source in every importer-written column: still
    not evidence of importer authorship, so it is kept and reported."""
    slug, mid = _manufacturer(cur)
    manual_id = _unmarked_row(cur, mid)
    _assert_preserved_and_reported(cur, slug, mid, manual_id, runs=3)


@pytest.mark.parametrize(
    "edit",
    [
        {"note": "Editor correction: identity confirmed by phone with the company."},
        {"source_title": "Example Robotics — corrected page title"},
        {"confidence": "LOW"},
        {"verified_at": None},
        {"claim_fields": ["legal_name"]},
    ],
    ids=["note", "title", "confidence", "verified_at", "claim_fields"],
)
def test_edited_unmarked_row_sharing_url_type_and_date_survives_repeated_imports(
    cur, edit
) -> None:
    slug, mid = _manufacturer(cur)
    manual_id = _unmarked_row(cur, mid, **edit)
    _assert_preserved_and_reported(cur, slug, mid, manual_id, runs=3)


def test_repeated_imports_replace_only_catalogue_managed_rows(cur) -> None:
    """No unmarked row present: the managed copy is replaced on each run, never
    duplicated, and nothing is reported."""
    slug, mid = _manufacturer(cur)
    ids = []
    for run in range(3):
        result = _import(cur, slug, [CATALOGUE_SOURCE])
        assert result["collisions"] == []
        assert result["removed"] == (0 if run == 0 else 1)
        managed = _managed_rows(cur, mid)
        assert len(managed) == 1
        ids.append(managed[0][0])
    assert len(set(ids)) == 3  # re-inserted each run, one row at a time


def test_unrelated_manual_row_is_preserved_without_a_collision(cur) -> None:
    slug, mid = _manufacturer(cur)
    manual_id = _unmarked_row(
        cur, mid, source_url="https://example.test/collision/editor-analyst-note",
        source_type="ANALYST_REPORT", observed_at="2026-09-01",
    )
    before = _row(cur, manual_id)

    for _ in range(2):
        result = _import(cur, slug, [CATALOGUE_SOURCE])
        assert result["collisions"] == []

    assert _row(cur, manual_id) == before
    assert len(_managed_rows(cur, mid)) == 1
