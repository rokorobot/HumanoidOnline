"""The importer owns its own rows — and only its own.

`db/import_catalogue.py` reconciles a robot's fact rows by natural key on every run
so that re-importing is idempotent and keeps row ids. `specification` is the one
table where that ownership is *shared*: `db/seed/seed.sql` and hand authoring write
rows there too, and `spec_definition` keys like `swappable_battery` are authored by
the seed with their own labels and units.

Two failures follow from that, and both are pinned here:

* a blanket reconciliation would touch somebody else's specification row while
  refreshing ours;
* leaving only our rows alone is not enough if the write that follows then goes
  over an unmanaged row occupying the same logical key — the collision has to be
  detected and REPORTED, because a silently skipped value and a silently
  overwritten one are equally invisible.

The managed-row behaviour is a property of the generated SQL, so these run with
a recording cursor and no database.
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
    """Captures SQL without a database; `fetchone` is scripted per test.

    `existing` maps a table name to the rows its reconciliation read would return
    (id, natural-key columns, then the table's ownership/protection peeks)."""

    def __init__(self, rows=None, existing=None) -> None:
        self.statements: list[str] = []
        self.params: list[tuple] = []
        self._rows = list(rows or [])
        self._existing = existing or {}
        self._last = ""

    def execute(self, sql, params=None):
        self._last = " ".join(str(sql).split())
        self.statements.append(self._last)
        self.params.append(tuple(params or ()))
        return self

    def fetchone(self):
        # The blanking guard asks whether a stored value exists: there is none.
        if "IS NOT NULL)" in self._last:
            return None
        return self._rows.pop(0) if self._rows else (1, "EUR")

    def fetchall(self):
        for table, rows in self._existing.items():
            if f"FROM {table} t" in self._last or f"FROM {table} WHERE" in self._last:
                return list(rows)
        return []

    def matching(self, prefix: str) -> list[str]:
        return [s for s in self.statements if s.startswith(prefix)]


def _import(cur, robot, authorize=None, recon=None):
    return ic.import_robot(
        cur, robot,
        region_id=lambda code: 1, manufacturer_id=lambda slug: 1,
        capability_id=lambda slug: 1, use_case_id=lambda slug: 1,
        spec_definition=lambda key: (7, "TEXT"), collisions=[], authorize=authorize,
        recon=recon,
    )


ROBOT = {"slug": "test-robot", "manufacturer_slug": "test-maker", "name": "Test Robot",
         "commercial_status": "ANNOUNCED", "is_published": False, "specs": {}}

#: The shape of an existing row as the reconciliation reads it: id, natural key, peeks.
FOREIGN_SPEC = ("spec-1", None, "swappable_battery", "seed/hand-authored")
OWN_SPEC = ("spec-2", None, "retired_key", ic.MANAGED_BY)


# --- specification reconciliation is scoped to the importer's own rows -------

def test_an_omitted_managed_specification_is_preserved_and_a_foreign_one_is_ignored():
    """D1: a row that is not in the JSON is left untouched and reported, never deleted. A
    row that is not ours is not even reported: it is outside the importer's scope."""
    cur = _RecordingCursor(existing={"specification": [FOREIGN_SPEC, OWN_SPEC]})
    recon = ic.Reconciliation()
    _import(cur, ROBOT, recon=recon)
    recon.finish()
    assert recon.preserved == [("specification", "test-robot",
                                {"variant_slug": None, "key": "retired_key"})]
    assert recon.counts["specification"]["preserved"] == 1
    assert "swappable_battery" not in recon.summary()
    assert not [s for s in cur.statements if s.startswith(("DELETE", "UPDATE specification"))]


def test_authorized_removal_deletes_only_the_named_managed_specification():
    cur = _RecordingCursor(existing={"specification": [FOREIGN_SPEC, OWN_SPEC]})
    _import(cur, ROBOT, authorize={"version": 1, "entries": [{
        "action": "remove", "table": "specification", "robot": "test-robot",
        "key": {"variant_slug": None, "key": "retired_key"}}]})
    deletes = [(s, p) for s, p in zip(cur.statements, cur.params, strict=True)
               if s.startswith("DELETE FROM specification")]
    assert deletes == [("DELETE FROM specification WHERE id = %s", ("spec-2",))]


_OFFER_KEY = {"variant_slug": None, "provider_slug": "shop", "region_code": "DE",
              "transaction_type": "PURCHASE", "condition": "NEW"}
TABLE_ROWS = {
    "pricing_offer": (("offer-1", None, "shop", "DE", "PURCHASE", "NEW"), _OFFER_KEY),
    "availability_offer": (("offer-1", None, "shop", "DE", "PURCHASE", "NEW"), _OFFER_KEY),
}


@pytest.mark.parametrize("table", sorted(TABLE_ROWS))
def test_wholly_owned_child_tables_are_removed_only_when_authorized(table):
    """The importer owns these tables outright, but a row that left the JSON is neither
    deleted nor refused: it is preserved and reported. It is removed, without any managed_by
    filter, once the operator names it."""
    row, key = TABLE_ROWS[table]
    kept = _RecordingCursor(existing={table: [row]})
    recon = ic.Reconciliation()
    _import(kept, ROBOT, recon=recon)
    recon.finish()
    assert recon.counts[table]["preserved"] == 1
    assert not [s for s in kept.statements if s.startswith("DELETE")]

    cur = _RecordingCursor(existing={table: [row]})
    _import(cur, ROBOT, authorize={"version": 1, "entries": [{
        "action": "remove", "table": table, "robot": "test-robot", "key": key}]})
    deletes = cur.matching(f"DELETE FROM {table}")
    assert deletes, f"{table} is importer-owned and an authorized removal must delete the row"
    assert "managed_by" not in deletes[0]


def test_a_stored_deployment_that_left_the_json_is_refused_by_decision_d2():
    """Deployments have no inferred identity: an omitted one cannot be matched, preserved as
    'the same row' or removed, so the import stops until an explicit deployment_key exists."""
    cur = _RecordingCursor(existing={"deployment": [("dep-1",)]})
    with pytest.raises(ic.ReconcileRefused, match="Owner decision D2"):
        _import(cur, ROBOT)
    assert not [s for s in cur.statements
                if s.startswith(("DELETE", "UPDATE", "INSERT INTO deployment"))]


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
    cur = _RecordingCursor(rows=[(1, True)])
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


def test_an_unchanged_definition_we_own_is_neither_rewritten_nor_reported():
    """The upsert only fires when a column differs, so an unchanged definition returns no
    row; that must read as 'ours and unchanged', not as a collision."""
    cur = _RecordingCursor(rows=[None, (ic.MANAGED_BY,)])
    collisions: list[str] = []
    recon = ic.Reconciliation()
    ic.import_spec_definitions(
        cur,
        {"spec_definitions": [
            {"key": "arm_joint_torque_nm", "label": "Arm joint torque", "value_type": "TEXT"},
        ]},
        collisions, recon,
    )
    assert collisions == []
    assert recon.counts["spec_definition"]["unchanged"] == 1


def test_an_unmanaged_specification_row_is_skipped_not_overwritten():
    """Anything occupying the logical key that is not ours belongs to someone else. The
    catalogue value is skipped and the preserved row is reported — never overwritten."""
    robot = {
        **ROBOT,
        "extended_specs": [
            {"key": "swappable_battery", "value": True,
             "source_label": "Maker spec sheet",
             "source_url": "https://example.invalid/spec",
             "source_kind": "MANUFACTURER", "edition_scope": "THIS_EDITION",
             "observed_at": "2026-09-11"},
        ],
    }
    cur = _RecordingCursor(existing={"specification": [FOREIGN_SPEC]})
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
    assert not cur.matching("UPDATE specification")
    assert len(collisions) == 1
    assert "swappable_battery" in collisions[0] and "preserved" in collisions[0]
    assert "seed/hand-authored" in collisions[0]


def test_extended_specs_without_a_registry_fail_loudly():
    """Dropping an attributed fact silently is worse than refusing to write it."""
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
