"""Company-evidence ownership against real Postgres.

An unmarked MANUFACTURER evidence row (``managed_by IS NULL``) is either a row an
import wrote before migration 0013 introduced the marker, or a row someone
maintains by hand. Sharing a catalogue source's URL, type and observed date does
not tell them apart: an editor may have corrected that very row. So the importer
adopts an unmarked row ONLY when stronger provenance says it is an untouched
pre-marker import — every column the importer writes equals the catalogue source
and it carries no ``claim_fields`` (which only post-0013 writers set). Anything
else is preserved and reported as an ambiguous collision.

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

#: What an import that predates migration 0013 wrote for a catalogue source.
LEGACY_SOURCE = {
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
CATALOGUE_SOURCE = {**LEGACY_SOURCE, "claim_fields": ["legal_name"]}

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
    row = {**LEGACY_SOURCE, **overrides}
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


def _rows_for(cur, mid):
    return cur.execute(
        "SELECT source_url, managed_by, claim_fields FROM evidence_source "
        "WHERE subject_type='MANUFACTURER' AND subject_id=%s ORDER BY managed_by NULLS FIRST",
        (mid,),
    ).fetchall()


def test_untouched_pre_marker_import_row_is_adopted_not_duplicated(cur) -> None:
    slug, mid = _manufacturer(cur)
    _unmarked_row(cur, mid)

    first = _import(cur, slug, [CATALOGUE_SOURCE])
    second = _import(cur, slug, [CATALOGUE_SOURCE])

    assert first["adopted"] == 1 and first["collisions"] == []
    assert second["adopted"] == 0 and second["removed"] == 1 and second["collisions"] == []
    assert _rows_for(cur, mid) == [(LEGACY_SOURCE["source_url"], ic.MANAGED_BY, ["legal_name"])]


@pytest.mark.parametrize(
    "edit",
    [
        {"note": "Editor correction: identity confirmed by phone with the company."},
        {"source_title": "Example Robotics — corrected page title"},
        {"confidence": "LOW"},
        {"verified_at": None},
    ],
    ids=["note", "title", "confidence", "verified_at"],
)
def test_manually_edited_row_sharing_url_type_and_date_survives_repeated_imports(
    cur, edit
) -> None:
    slug, mid = _manufacturer(cur)
    manual_id = _unmarked_row(cur, mid, **edit)
    before = _row(cur, manual_id)

    runs = [_import(cur, slug, [CATALOGUE_SOURCE]) for _ in range(3)]

    # Content, ownership (still unmarked) and relationship (same subject) intact.
    assert _row(cur, manual_id) == before
    for run in runs:
        assert run["adopted"] == 0
        assert len(run["collisions"]) == 1
        assert LEGACY_SOURCE["source_url"] in run["collisions"][0]
        assert slug in run["collisions"][0]
    # The catalogue's own copy exists exactly once beside it — never duplicated.
    marked = [r for r in _rows_for(cur, mid) if r[1] == ic.MANAGED_BY]
    assert len(marked) == 1


def test_unmarked_row_carrying_claim_fields_is_never_treated_as_legacy(cur) -> None:
    """Identical content, but `claim_fields` only exist since 0013: someone
    attributed this row by hand, so it is not a pre-marker import."""
    slug, mid = _manufacturer(cur)
    manual_id = _unmarked_row(cur, mid, claim_fields=["legal_name"])
    before = _row(cur, manual_id)

    result = _import(cur, slug, [CATALOGUE_SOURCE])

    assert _row(cur, manual_id) == before
    assert result["adopted"] == 0
    assert len(result["collisions"]) == 1


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
