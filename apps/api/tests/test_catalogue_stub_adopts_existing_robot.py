"""The 4NE1 Mini identity-only stub adopts the existing database robot (DR-A5 / M2).

`4ne1-mini` was created by a governed promotion, so it existed ONLY in the database.
DR-A5 makes `db/catalogue/` the catalogue of record, so the robot needs a catalogue
file. The invariant these tests pin:

    existing DB robot + catalogue stub  ->  the SAME DB robot   (never a second one)

The importer binds a JSON file to a database robot by slug. These prove that, on a
scratch database holding the production-shaped state, importing the stub (twice):
keeps the robot's UUID, adds no robot or manufacturer, leaves it unpublished, leaves
the promotion's evidence row byte-identical, and creates (since G2-3) only the two
materialized variants and their two variant-scoped specs: no offers, capabilities,
use-case rows, images or deployments. Only `updated_at` (a trigger
column) moves, and it moves by design on any importer upsert.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import psycopg
from test_identity_decision_migration import scratch_db  # noqa: F401  (pytest fixture)

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "db"
STUB = DB_DIR / "catalogue" / "robots" / "4ne1-mini.json"
SCHEMA_SQL = DB_DIR / "schema.sql"
SLUG, NAME, MAKER = "4ne1-mini", "4NE1 Mini", "neura-robotics"

_spec = importlib.util.spec_from_file_location("import_catalogue", DB_DIR / "import_catalogue.py")
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)
sys.path.insert(0, str(DB_DIR))
import catalogue_entries as ce  # noqa: E402

CHILD_TABLES = ("specification", "robot_variant", "pricing_offer", "availability_offer",
                "robot_capability", "use_case_fit", "robot_image", "deployment")


# ------------------------------------------------------------- the file itself --


#: The only keys G2-3 materialization (DR-A5 M2) may add to the adopted identity stub.
MATERIALIZED_KEYS = ("variants", "extended_specs")


def test_the_file_is_the_canonical_stub_plus_only_the_materialized_delta():
    doc = json.loads(STUB.read_text(encoding="utf-8"))
    stub = ce.make_stub(slug=SLUG, name=NAME, mfr_slug=MAKER, official_url=None)
    assert {k: v for k, v in doc.items() if k not in MATERIALIZED_KEYS} == {
        k: v for k, v in stub.items() if k not in MATERIALIZED_KEYS}
    assert doc["slug"] == SLUG == STUB.stem
    # the delta: exactly the two owner-approved variants and their variant-scoped specs
    assert doc["variants"] == [{"slug": "pro", "name": "Pro"},
                               {"slug": "standard", "name": "Standard"}]
    assert {(x["key"], x["variant_slug"], x["value"], x["edition_scope"])
            for x in doc["extended_specs"]} == {
        ("dexterous_hand_option", "pro", "12 DoF dexterous hands", "THIS_EDITION"),
        ("dexterous_hand_option", "standard", "Not included", "THIS_EDITION")}


def test_the_file_still_asserts_identity_and_no_commercial_or_derived_fact():
    doc = json.loads(STUB.read_text(encoding="utf-8"))
    assert (doc["slug"], doc["name"], doc["manufacturer_slug"]) == (SLUG, NAME, MAKER)
    assert doc["is_published"] is False
    assert doc["commercial_status"] == "UNKNOWN"           # asserts no maturity
    assert set(doc["specs"]) == set(ce.SPEC_FIELDS)         # the full field set, all UNKNOWN
    assert all(v is None for v in doc["specs"].values())   # hand_dof etc. stay UNKNOWN
    for scalar in ("model_code", "summary", "announced_year", "official_url"):
        assert doc[scalar] is None, scalar
    for collection in ("commercial_status_evidence", "pricing_offers", "availability_offers",
                       "deployments", "capabilities", "use_case_fits", "images"):
        assert doc[collection] == [], collection            # no price, availability, ...
    assert all("spec_overrides" not in v for v in doc["variants"])


class _Recording:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql, params=None):
        self.statements.append(" ".join(str(sql).split()))
        return self

    def fetchone(self):
        return (1, "EUR")


def test_the_importer_matches_by_slug_and_never_rewrites_publication():
    cur = _Recording()
    ic.import_robot(cur, json.loads(STUB.read_text(encoding="utf-8")),
                    region_id=lambda c: 1, manufacturer_id=lambda s: 1,
                    capability_id=lambda s: 1, use_case_id=lambda s: 1,
                    spec_definition=lambda k: (7, "TEXT"), collisions=[])
    [upsert] = [s for s in cur.statements if s.startswith("INSERT INTO robot (")]
    assert "ON CONFLICT (slug) DO UPDATE SET" in upsert      # an existing slug is UPDATED
    assert "RETURNING id" in upsert                          # ...and its id is what is used
    assert "is_published" not in upsert.split("DO UPDATE SET", 1)[1]


# --------------------------------------------------- the database-backed invariant --


def _state(conn, robot_id, maker_id):
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    return {
        "robots": q("SELECT count(*) FROM robot"),
        "manufacturers": q("SELECT count(*) FROM manufacturer"),
        "same_name_or_slug": q("SELECT count(*) FROM robot WHERE name = %s OR slug = %s",
                               NAME, SLUG),
        "robot": q("SELECT md5((to_jsonb(r) - 'updated_at')::text) FROM robot r WHERE id = %s",
                   robot_id),
        "manufacturer": q("SELECT md5((to_jsonb(m) - 'updated_at')::text) "
                          "FROM manufacturer m WHERE id = %s", maker_id),
        "is_published": q("SELECT is_published FROM robot WHERE id = %s", robot_id),
        "evidence": conn.execute(
            "SELECT id, md5(e::text) FROM evidence_source e "
            "WHERE subject_type = 'ROBOT' AND subject_id = %s ORDER BY id", (robot_id,)
        ).fetchall(),
        "children": {t: q(f"SELECT count(*) FROM {t} WHERE robot_id = %s", robot_id)
                     for t in CHILD_TABLES},
    }


def test_the_stub_adopts_the_existing_database_robot(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    # Production-shaped state: the NEURA manufacturer is established by the importer
    # (as in production), then a governed promotion creates 4ne1-mini in the database
    # ONLY: a robot row (unpublished, commercial_status defaulting to UNKNOWN) and the
    # promotion's ROBOT-subject evidence row.
    ic.run(scratch_db, only={"neura-4ne-1"})
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute("SET search_path TO humanoid, public")
        maker_id = conn.execute("SELECT id FROM manufacturer WHERE slug = %s",
                                (MAKER,)).fetchone()[0]
        robot_id = conn.execute(
            "INSERT INTO robot (slug, manufacturer_id, name, is_published) "
            "VALUES (%s, %s, %s, false) RETURNING id", (SLUG, maker_id, NAME)).fetchone()[0]
        conn.execute(
            "INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type, "
            "source_title, confidence, verified_at, note) VALUES ('ROBOT', %s, "
            "'https://neura-robotics.com/product/4ne1-mini-reservation', 'MANUFACTURER_SITE', "
            "'4NE1 Mini confirmed authoritative source', 'VERIFIED', now(), 'governed promotion')",
            (robot_id,))
        neighbour = conn.execute(
            "SELECT md5(r::text) FROM robot r WHERE slug = 'neura-4ne-1'").fetchone()[0]
        before = _state(conn, robot_id, maker_id)
    assert (before["robots"], before["same_name_or_slug"]) == (2, 1)

    states = []
    for _run in (1, 2):
        ic.run(scratch_db, only={SLUG})
        with psycopg.connect(scratch_db, autocommit=True) as conn:
            conn.execute("SET search_path TO humanoid, public")
            states.append(_state(conn, robot_id, maker_id))
            same = conn.execute("SELECT id FROM robot WHERE slug = %s", (SLUG,)).fetchone()[0]
            assert same == robot_id                                   # the SAME robot
            assert conn.execute("SELECT md5(r::text) FROM robot r WHERE slug = 'neura-4ne-1'"
                                ).fetchone()[0] == neighbour          # neura-4ne-1 untouched

    for after in states:
        assert after["robots"] == before["robots"]                    # no second robot
        assert after["manufacturers"] == before["manufacturers"]
        assert after["same_name_or_slug"] == 1                        # no duplicate identity
        assert after["robot"] == before["robot"]                      # identical but updated_at
        assert after["manufacturer"] == before["manufacturer"]
        assert after["is_published"] is False and before["is_published"] is False
        assert after["evidence"] == before["evidence"]                # id AND content intact
        assert after["children"] == {**dict.fromkeys(CHILD_TABLES, 0),   # only the delta appeared
                                     "robot_variant": 2, "specification": 2}
    assert states[0] == states[1]                                     # the 2nd run changes nothing
