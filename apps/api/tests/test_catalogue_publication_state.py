"""Catalogue invariant: an import refreshes FACTS, never editorial visibility.

HumanoidOnline keeps two distinct concepts:

* the **master catalogue** — everything we know about, cumulative, and never
  reduced because a robot is sparse, image-less, pre-production or
  discontinued;
* the **public catalogue** — the currently approved view of that master.

`db/import_catalogue.py` owns the first. It must not silently rewrite the
second. The failure this pins down actually happened: stub entries are authored
with `"is_published": false`, so a routine fact-refresh import reverted an
editorial decision to display them and 46 stored robots became 7 on screen.
Nothing was deleted, and that is precisely why it was hard to see.

These tests are written against that regression, not the happy path.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO_ROOT / "db" / "import_catalogue.py"
)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)


class _RecordingCursor:
    """Captures SQL without a database.

    The invariant lives in the shape of one generated statement, so it can be
    asserted directly — no Postgres required, which means this test runs
    everywhere and cannot be skipped into uselessness.
    """

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql, params=None):
        self.statements.append(" ".join(str(sql).split()))
        return self

    def fetchone(self):
        # Wide enough for every row this code path reads: the RETURNING id of
        # the upsert (index 0) and the price rollup's (price, currency) pair.
        return (1, "EUR")

    def upsert_sql(self) -> str:
        matches = [s for s in self.statements if s.startswith("INSERT INTO robot (")]
        assert len(matches) == 1, f"expected one robot upsert, saw {len(matches)}"
        return matches[0]


ROBOT = {
    "slug": "test-robot",
    "manufacturer_slug": "test-maker",
    "name": "Test Robot",
    "commercial_status": "ANNOUNCED",
    # Exactly how `catalogue_entries.py stubs` writes a new identity-only entry.
    "is_published": False,
    "specs": {},
}


def _run_import(**kwargs) -> str:
    cur = _RecordingCursor()
    ic.import_robot(
        cur, ROBOT,
        region_id=lambda code: 1,
        manufacturer_id=lambda slug: 1,
        capability_id=lambda slug: 1,
        use_case_id=lambda slug: 1,
        **kwargs,
    )
    return cur.upsert_sql()


def _update_clause(sql: str) -> str:
    return sql.split("DO UPDATE SET", 1)[1]


def test_routine_import_does_not_touch_publication_state():
    """The default path must leave `is_published` exactly as the editors left it."""
    update = _update_clause(_run_import())
    assert "is_published" not in update, (
        "a routine catalogue import rewrote is_published — this is the exact "
        "defect that made 46 stored robots display as 7"
    )


def test_routine_import_still_refreshes_catalogue_facts():
    """Preserving visibility must not come at the cost of the facts."""
    update = _update_clause(_run_import())
    for column in ("name", "summary", "commercial_status", "manufacturer_id"):
        assert f"{column} = EXCLUDED.{column}" in update, (
            f"{column} is a catalogue fact and must still refresh on import"
        )


def test_new_records_are_created_with_their_authored_state():
    """A brand-new row has no editorial history to protect, so INSERT writes it."""
    sql = _run_import()
    insert_columns = sql.split(")", 1)[0]
    assert "is_published" in insert_columns


def test_explicit_publishing_operation_can_change_visibility():
    """Visibility is not frozen — it is only moved deliberately."""
    update = _update_clause(_run_import(apply_publication_state=True))
    assert "is_published = EXCLUDED.is_published" in update


def test_editorial_columns_are_named_not_inferred():
    """The protected set is explicit, so widening it is a deliberate edit."""
    assert ic.EDITORIAL_COLUMNS == ("is_published",)


@pytest.mark.parametrize("authored", [True, False])
def test_preservation_is_independent_of_the_authored_value(authored):
    """Whichever way the JSON leans, a fact refresh must not act on it."""
    robot = dict(ROBOT, is_published=authored)
    cur = _RecordingCursor()
    ic.import_robot(
        cur, robot,
        region_id=lambda code: 1,
        manufacturer_id=lambda slug: 1,
        capability_id=lambda slug: 1,
        use_case_id=lambda slug: 1,
    )
    assert "is_published" not in _update_clause(cur.upsert_sql())
