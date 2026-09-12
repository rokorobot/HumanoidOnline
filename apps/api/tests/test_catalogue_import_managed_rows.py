"""The importer owns its own rows — and only its own.

`db/import_catalogue.py` replaces a robot's fact rows on every run so that
re-importing is idempotent. `specification` is the one table where that
ownership is *shared*: `db/seed/seed.sql` and hand authoring write rows there
too, and `spec_definition` keys like `swappable_battery` are authored by the
seed with their own labels and units.

Two failures follow from that, and both are pinned here:

* a blanket delete would destroy somebody else's specification row while
  refreshing ours;
* deleting only our rows is not enough if the INSERT that follows then writes
  over an unmanaged row occupying the same logical key — the collision has to be
  detected and REPORTED, because a silently skipped value and a silently
  overwritten one are equally invisible.

The managed-row behaviour is a property of the generated SQL, so these run with
a recording cursor and no database.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO_ROOT / "db" / "import_catalogue.py"
)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)


class _RecordingCursor:
    """Captures SQL without a database; `fetchone` is scripted per test."""

    def __init__(self, rows=None) -> None:
        self.statements: list[str] = []
        self._rows = list(rows or [])

    def execute(self, sql, params=None):
        self.statements.append(" ".join(str(sql).split()))
        return self

    def fetchone(self):
        return self._rows.pop(0) if self._rows else (1, "EUR")

    def matching(self, prefix: str) -> list[str]:
        return [s for s in self.statements if s.startswith(prefix)]


# --- specification retirement is scoped to the importer's own rows -----------

def test_reset_deletes_only_importer_managed_specifications():
    """The delete must carry the ownership predicate. Without it, a routine
    fact refresh silently destroys seed and hand-authored specifications."""
    cur = _RecordingCursor()
    ic._reset_robot_children(cur, robot_id=1)

    deletes = cur.matching("DELETE FROM specification")
    assert len(deletes) == 1, deletes
    assert "managed_by = %s" in deletes[0], (
        "specification rows were deleted without restricting to the importer's "
        f"own managed rows: {deletes[0]}"
    )


def test_wholly_owned_child_tables_are_still_replaced_outright():
    """The narrow specification rule must not accidentally spare the tables the
    importer does own — those must keep being replaced, or re-import stops
    being idempotent and rows accumulate."""
    cur = _RecordingCursor()
    ic._reset_robot_children(cur, robot_id=1)

    for table in ("pricing_offer", "availability_offer", "deployment"):
        deletes = cur.matching(f"DELETE FROM {table}")
        assert deletes, f"{table} is importer-owned and must be replaced on import"
        assert "managed_by" not in deletes[0], (
            f"{table} is wholly owned by the importer; it must not be filtered "
            "by managed_by"
        )


def test_the_managed_marker_is_a_named_constant():
    """The ownership marker is explicit, so widening it is a deliberate edit."""
    assert ic.MANAGED_BY == "CATALOGUE_IMPORT"


# --- logical-key collisions are preserved AND reported -----------------------

def test_an_unmanaged_spec_definition_is_preserved_and_reported():
    """The conditional UPDATE matches nothing when the row is not ours, so the
    definition keeps its own label, units and filterability — and the collision
    is reported rather than swallowed."""
    # First fetchone() -> the upsert's RETURNING id (None = nothing written,
    # because the row is not managed by us); second -> the owner lookup.
    cur = _RecordingCursor(rows=[None, ("seed/hand-authored",)])
    collisions: list[str] = []
    ic.import_spec_definitions(
        cur,
        {"spec_definitions": [
            {"key": "swappable_battery", "label": "Swappable battery",
             "value_type": "BOOL"},
        ]},
        collisions,
    )

    upserts = cur.matching("INSERT INTO spec_definition")
    assert upserts and "WHERE spec_definition.managed_by = %s" in upserts[0], (
        "the definition upsert must be conditional on ownership, or the "
        "catalogue can redefine a key the seed owns"
    )
    assert len(collisions) == 1
    assert "swappable_battery" in collisions[0]
    assert "preserved" in collisions[0]
    assert "seed/hand-authored" in collisions[0]


def test_a_definition_we_own_is_updated_without_a_collision_report():
    """The protection must not cry wolf on the importer's own keys."""
    cur = _RecordingCursor(rows=[(1,)])
    collisions: list[str] = []
    ic.import_spec_definitions(
        cur,
        {"spec_definitions": [
            {"key": "arm_joint_torque_nm", "label": "Arm joint torque",
             "value_type": "TEXT"},
        ]},
        collisions,
    )
    assert collisions == []


def test_an_unmanaged_specification_row_is_skipped_not_overwritten():
    """Our rows were already deleted, so anything still occupying the logical
    key belongs to someone else. The catalogue value is skipped and the
    preserved row is reported — never overwritten."""
    robot = {
        "slug": "test-robot",
        "manufacturer_slug": "test-maker",
        "name": "Test Robot",
        "commercial_status": "ANNOUNCED",
        "is_published": False,
        "specs": {},
        "extended_specs": [
            {"key": "swappable_battery", "value": True,
             "source_label": "Maker spec sheet",
             "source_url": "https://example.invalid/spec",
             "source_kind": "MANUFACTURER", "edition_scope": "THIS_EDITION",
             "observed_at": "2026-09-11"},
        ],
    }
    # robot upsert RETURNING id, then the occupancy probe finding a foreign row.
    cur = _RecordingCursor(rows=[(1,), ("seed/hand-authored",)])
    collisions: list[str] = []
    ic.import_robot(
        cur, robot,
        region_id=lambda code: 1,
        manufacturer_id=lambda slug: 1,
        capability_id=lambda slug: 1,
        use_case_id=lambda slug: 1,
        spec_definition=lambda key: (7, "BOOL"),
        collisions=collisions,
    )

    assert not cur.matching("INSERT INTO specification"), (
        "an unmanaged specification row was overwritten by the catalogue import"
    )
    assert len(collisions) == 1
    assert "swappable_battery" in collisions[0] and "preserved" in collisions[0]


def test_extended_specs_without_a_registry_fail_loudly():
    """Dropping an attributed fact silently is worse than refusing to write it."""
    import pytest

    robot = {
        "slug": "test-robot", "manufacturer_slug": "test-maker", "name": "Test Robot",
        "commercial_status": "ANNOUNCED", "is_published": False, "specs": {},
        "extended_specs": [{"key": "whatever", "value": 1}],
    }
    with pytest.raises(ValueError) as exc:
        ic.import_robot(
            _RecordingCursor(rows=[(1,)]), robot,
            region_id=lambda code: 1,
            manufacturer_id=lambda slug: 1,
            capability_id=lambda slug: 1,
            use_case_id=lambda slug: 1,
        )
    assert "extended_specs" in str(exc.value)
