"""`--only` — a scoped import touches the selected records and nothing else.

A full catalogue import replaces the child rows (offers, evidence, images,
specifications) of EVERY robot in the catalogue. That is correct when the
catalogue is the thing being synchronised, and wrong when the operator asked for
one batch: it rewrites rows belonging to robots nobody selected.

The risks this pins down:

* an unknown slug discovered *after* writes have begun — the abort must happen
  before a connection is even opened;
* the filter applied after the robot upsert, so an unselected robot is still
  mutated;
* shared entities (manufacturers, providers, capabilities, use cases, spec
  definitions) silently rewritten catalogue-wide even under `--only`;
* a region imported without its parent, breaking the applicability walk;
* the default path changing behaviour at all.

No database: selection and narrowing are pure functions over the catalogue
files, and the mutation shape is asserted with a recording cursor.
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

BATCH = {
    "unitree-r1", "unitree-h2", "unitree-h2-edu",
    "unitree-r1-edu-u1", "unitree-r1-edu-u2", "unitree-r1-edu-u3",
    "unitree-r1-edu-u4", "unitree-r1-edu-u5", "unitree-r1-edu-u6",
    "booster-t2-education", "booster-t2-professional",
}


def _catalogue_slugs() -> set[str]:
    return {p.stem for p in (REPO_ROOT / "db" / "catalogue" / "robots").glob("*.json")}


# --- selection ---------------------------------------------------------------

def test_default_selects_every_record_unchanged():
    """The default path must keep importing the whole catalogue."""
    assert {p.stem for p in ic.select_robot_files(None)} == _catalogue_slugs()


def test_only_selects_exactly_the_named_records():
    selected = {p.stem for p in ic.select_robot_files(set(BATCH))}
    assert selected == BATCH
    assert len(selected) == 11


def test_unknown_slug_aborts_before_any_write():
    """The abort is a pure-function failure: no connection, no cursor, no SQL."""
    with pytest.raises(SystemExit) as exc:
        ic.select_robot_files({"unitree-r1", "not-a-robot", "also-missing"})
    message = str(exc.value)
    assert "also-missing" in message and "not-a-robot" in message
    assert "unitree-r1" not in message.split("--only:")[1].split("(")[0].replace("not-a-robot", "")


def test_a_wholly_unknown_selection_is_refused():
    with pytest.raises(SystemExit):
        ic.select_robot_files({"nope"})


# --- shared-entity narrowing -------------------------------------------------

def _batch_deps():
    regions = ic._load(ic.CATALOGUE_DIR / "regions.json")
    robots = [ic._load(p) for p in ic.select_robot_files(set(BATCH))]
    return ic.scoped_dependencies(robots, regions), regions


def test_dependencies_are_only_what_the_selection_references():
    deps, _ = _batch_deps()
    assert deps["manufacturers"] == {"unitree", "booster-robotics"}
    assert deps["providers"] == {"unitree-store", "reichelt", "quadruped-de"}
    assert deps["capabilities"] == {"voice-interaction", "dexterous-hands"}
    assert deps["use_cases"] == set()


def test_a_referenced_region_brings_its_ancestors():
    """`DE` without `EU` would leave the applicability walk broken."""
    deps, _ = _batch_deps()
    assert "DE" in deps["regions"]
    assert "EU" in deps["regions"], "DE's parent must be imported with it"
    assert "GLOBAL" in deps["regions"]


def test_narrowing_excludes_unreferenced_shared_rows():
    """The catalogue's other manufacturers/providers must not be rewritten."""
    deps, _ = _batch_deps()
    providers = ic._load(ic.CATALOGUE_DIR / "providers.json")
    manufacturers = ic._load(ic.CATALOGUE_DIR / "manufacturers.json")
    kept_providers = ic._narrow(providers, "providers", "slug", deps["providers"])
    kept_mfrs = ic._narrow(manufacturers, "manufacturers", "slug", deps["manufacturers"])

    assert {p["slug"] for p in kept_providers["providers"]} == deps["providers"]
    assert "robotshop-us" not in {p["slug"] for p in kept_providers["providers"]}
    assert "agility-raas" not in {p["slug"] for p in kept_providers["providers"]}
    assert len(kept_mfrs["manufacturers"]) < len(manufacturers["manufacturers"])


def test_spec_definitions_are_narrowed_to_keys_the_selection_uses():
    deps, _ = _batch_deps()
    defs = ic._load(ic.CATALOGUE_DIR / "spec_definitions.json")
    kept = ic._narrow(defs, "spec_definitions", "key", deps["spec_definitions"])
    assert {d["key"] for d in kept["spec_definitions"]} <= deps["spec_definitions"]
    assert kept["spec_definitions"], "the batch does use long-tail specs"


# --- the mutation itself -----------------------------------------------------

class _RecordingCursor:
    def __init__(self, rows=None):
        self.statements: list[str] = []
        self.params: list[tuple] = []
        self._rows = list(rows or [])

    def execute(self, sql, params=None):
        self.statements.append(" ".join(str(sql).split()))
        if params:
            self.params.append(params)
        return self

    def fetchone(self):
        return self._rows.pop(0) if self._rows else (1, "EUR")


def test_an_unselected_robot_is_never_mutated():
    """The decisive property: importing the batch emits no statement carrying an
    unselected robot's slug, so its row and child rows cannot be touched."""
    selected = ic.select_robot_files(set(BATCH))
    cur = _RecordingCursor()
    for path in selected:
        ic.import_robot(
            cur, ic._load(path),
            region_id=lambda code: 1,
            manufacturer_id=lambda slug: 1,
            capability_id=lambda slug: 1,
            use_case_id=lambda slug: 1,
            spec_definition=lambda key: (7, "TEXT"),
            collisions=[],
        )
    emitted_slugs = {p for params in cur.params for p in params if isinstance(p, str)}
    unselected = _catalogue_slugs() - BATCH
    assert unselected, "sanity: the catalogue has non-batch records"
    assert not (emitted_slugs & unselected), (
        f"a scoped import referenced unselected robots: {sorted(emitted_slugs & unselected)}"
    )


def test_publication_state_is_still_preserved_under_scope():
    """`--only` changes WHICH records are refreshed, never the publication rule."""
    cur = _RecordingCursor()
    ic.import_robot(
        cur, ic._load(ic.select_robot_files({"unitree-r1"})[0]),
        region_id=lambda code: 1,
        manufacturer_id=lambda slug: 1,
        capability_id=lambda slug: 1,
        use_case_id=lambda slug: 1,
        spec_definition=lambda key: (7, "TEXT"),
        collisions=[],
    )
    upsert = [s for s in cur.statements if s.startswith("INSERT INTO robot (")]
    assert len(upsert) == 1
    assert "is_published" not in upsert[0].split("DO UPDATE SET", 1)[1]
