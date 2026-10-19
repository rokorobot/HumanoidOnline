"""Importer Hardening Phase 1 acceptance tests: stable-ID reconciliation.

Design: docs/discovery/STABLE_ID_RECONCILIATION_DESIGN_2026-10-19.md.

Re-importing a catalogue file must keep every row id, rewrite nothing it did not need to
change, and never delete or blank anything unless the operator authorized exactly that:

* idempotency: re-importing unchanged files changes no business content, no row id, no
  `updated_at` and issues no write (the whole row state, not just ids, is compared);
* one edit changes one row: the edited row keeps its id, everything else is byte-identical;
* additions are inserted exactly once;
* non-destructive (owner decision D1): a row that is not in the JSON is preserved and reported,
  removed only under an explicit `--authorize` entry; no stored value is ever turned into NULL
  without a `clear` entry;
* fail closed: ambiguity (duplicate keys in the JSON or in the database) aborts, evidence is
  immutable unless authorized, deployments have no inferred identity (D2), a changed excerpt is
  a new evidence version (D3);
* `is_published` stays editorial.

Real catalogue files on a scratch database.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys

import psycopg
import pytest
from test_identity_decision_migration import scratch_db  # noqa: F401

REPO = pathlib.Path(__file__).resolve().parents[3]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ic = _load("import_catalogue", "db/import_catalogue.py")
pf = _load("import_preflight", "db/import_preflight.py")
SCHEMA = (REPO / "db" / "schema.sql").read_text(encoding="utf-8")

# Between them: variants, variant-scoped specs, manufacturer-estimate and retail offers,
# availability, a deployment, images, use-case fits, capabilities and their evidence.
ROBOTS = {"4ne1-mini", "unitree-h2-edu", "agility-digit"}

_R = "JOIN robot r ON r.id = t.robot_id WHERE r.slug = ANY(%(s)s)"
_VAR = "LEFT JOIN robot_variant v ON v.id = t.variant_id"
_OFFER_KEY = ("r.slug||'|'||coalesce(v.slug,'-')||'|'"
              "||coalesce((SELECT slug FROM provider WHERE id = t.provider_id),'-')||'|'"
              "||coalesce((SELECT code FROM region WHERE id = t.region_id),'-')||'|'"
              "||t.transaction_type||'|'||t.condition")
# table -> SELECT <logical key>, <id>, <whole row as text> for the rows of ROBOTS. The key is
# written here independently of the importer, so a mapping that survives is a real statement
# about which row kept which id.
KEYED = {
    "robot": "SELECT t.slug, t.id, to_jsonb(t)::text FROM robot t WHERE t.slug = ANY(%(s)s)",
    "robot_variant": f"SELECT r.slug||'|'||t.slug, t.id, to_jsonb(t)::text "
                     f"FROM robot_variant t {_R}",
    "specification": f"SELECT r.slug||'|'||coalesce(v.slug,'-')||'|'||d.key, t.id, "
                     f"to_jsonb(t)::text FROM specification t {_VAR} "
                     f"JOIN spec_definition d ON d.id = t.definition_id {_R}",
    "pricing_offer": f"SELECT {_OFFER_KEY}, t.id, to_jsonb(t)::text "
                     f"FROM pricing_offer t {_VAR} {_R}",
    "availability_offer": f"SELECT {_OFFER_KEY}, t.id, to_jsonb(t)::text "
                          f"FROM availability_offer t {_VAR} {_R}",
    "deployment": f"SELECT r.slug||'|'||coalesce(t.customer_name,'-')||'|'||"
                  f"coalesce((SELECT code FROM region WHERE id = t.region_id),'-')||'|'||"
                  f"coalesce(t.started_on::text,'-'), t.id, to_jsonb(t)::text "
                  f"FROM deployment t {_R}",
    "robot_image": f"SELECT r.slug||'|'||t.image_url, t.id, to_jsonb(t)::text "
                   f"FROM robot_image t {_R}",
    # evidence whose subject is a ROBOT's commercial status or one of its offers/deployments
    "evidence_source": "SELECT t.subject_type||'|'||t.subject_id||'|'||coalesce(t.source_url,'-')"
                       "||'|'||t.source_type||'|'||md5(coalesce(t.excerpt,''))||'|'||"
                       "t.observed_at::date, t.id, to_jsonb(t)::text FROM evidence_source t "
                       "WHERE t.subject_id IN (SELECT r.id FROM robot r WHERE r.slug = ANY(%(s)s)"
                       + "".join(f" UNION SELECT t2.id FROM {tb} t2 JOIN robot r ON "
                                 "r.id = t2.robot_id WHERE r.slug = ANY(%(s)s)"
                                 for tb in ("pricing_offer", "availability_offer", "deployment"))
                       + ")",
}
# Shared entities: whole rows (updated_at included) must not move on an unchanged re-import.
SHARED = ("manufacturer", "provider", "region", "capability", "use_case", "spec_definition")


@pytest.fixture
def world(scratch_db, tmp_path, monkeypatch):  # noqa: F811
    cat = tmp_path / "catalogue"
    shutil.copytree(REPO / "db" / "catalogue", cat)
    monkeypatch.setattr(ic, "CATALOGUE_DIR", cat)
    monkeypatch.setattr(ic, "ROBOTS_DIR", cat / "robots")
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA)
    ic.run(scratch_db, only=ROBOTS)
    return scratch_db, cat


def _state(url) -> dict[str, dict[str, tuple]]:
    """{table: {logical key: (id, whole row)}} for the fixture robots."""
    with psycopg.connect(url) as conn:
        conn.read_only = True
        conn.execute("SET search_path TO humanoid, public")
        return {t: {k: (i, row) for k, i, row in conn.execute(q, {"s": sorted(ROBOTS)})}
                for t, q in KEYED.items()}


def _ids(url) -> dict[str, dict[str, object]]:
    return {t: {k: v[0] for k, v in rows.items()} for t, rows in _state(url).items()}


def _shared(url) -> dict[str, list]:
    with psycopg.connect(url) as conn:
        conn.read_only = True
        conn.execute("SET search_path TO humanoid, public")
        return {t: conn.execute(f"SELECT to_jsonb(t)::text FROM {t} t ORDER BY 1").fetchall()
                for t in SHARED}


def _content(url):
    with psycopg.connect(url) as conn:
        conn.read_only = True
        return pf.snapshot(conn)


def _exec(url, sql, params=None):
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SET search_path TO humanoid, public")
        return conn.execute(sql, params or ())


def _scalar(url, sql, params=None):
    with psycopg.connect(url) as conn:
        conn.execute("SET search_path TO humanoid, public")
        return conn.execute(sql, params or ()).fetchone()[0]


def _edit(cat, slug, change):
    path = cat / "robots" / f"{slug}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _changed(before, after):
    """{(table, key)} whose id or row content differs, plus inserted/removed keys."""
    out = set()
    for table in before:
        for key in before[table].keys() | after[table].keys():
            if before[table].get(key) != after[table].get(key):
                out.add((table, key))
    return out


def _authorization_in(error: BaseException) -> dict:
    """The pasteable `--authorize` document at the end of a refusal."""
    message = str(error)
    return json.loads(message[message.index('{\n  "version"'):])


def _authorize_file(tmp_path, entries) -> pathlib.Path:
    path = tmp_path / "authorize.json"
    path.write_text(json.dumps({"version": 1, "entries": entries}), encoding="utf-8")
    return path


# ---------------------------------------------------------------------- idempotency --

def test_the_fixture_exercises_every_id_table(world):
    url, _ = world
    assert all(_ids(url).values()), {t: len(v) for t, v in _ids(url).items()}


def test_reimporting_unchanged_files_changes_no_business_content(world):
    url, _ = world
    before = _content(url)
    ic.run(url, only=ROBOTS)
    assert pf.diff(before, _content(url)) == []      # the preflight's id-stripped comparison


@pytest.mark.parametrize("table", sorted(KEYED))
def test_reimporting_unchanged_files_keeps_every_logical_key_on_its_id(world, table):
    url, _ = world
    before = _ids(url)[table]
    ic.run(url, only=ROBOTS)
    assert _ids(url)[table] == before          # same key -> same id, nothing added or lost


def test_reimporting_unchanged_files_writes_nothing_at_all(world):
    """Not just ids: whole rows, `updated_at` included, and the run reports zero changes."""
    url, _ = world
    before, shared = _state(url), _shared(url)
    recon = ic.run(url, only=ROBOTS)
    assert _state(url) == before
    assert _shared(url) == shared              # robot's manufacturer, providers, regions, ...
    for table, counts in recon.counts.items():
        assert counts["inserted"] == counts["updated"] == counts["removed"] == 0, table


def test_a_full_second_run_reports_zero_changes_for_every_table(world):
    url, _ = world
    recon = ic.run(url)                        # the first full run settles the other robots
    again = ic.run(url)
    assert recon.counts and again.counts
    for table, counts in again.counts.items():
        assert counts["inserted"] == counts["updated"] == counts["removed"] == 0, table


# ------------------------------------------------------------------ one edit, one row --

def test_a_one_value_edit_keeps_every_other_id(world):
    url, cat = world
    before = _ids(url)
    _edit(cat, "unitree-h2-edu",
          lambda d: d["availability_offers"][0].update(seller_wording="edited for the test"))
    ic.run(url, only=ROBOTS)
    assert _ids(url) == before                 # the edited offer is updated in place


def test_one_changed_spec_value_changes_only_that_row(world):
    url, cat = world
    before = _state(url)
    _edit(cat, "unitree-h2-edu", lambda d: d["extended_specs"][0].update(value="edited value"))
    recon = ic.run(url, only=ROBOTS)
    after = _state(url)
    ((table, key),) = _changed(before, after)           # exactly one row differs ...
    assert table == "specification"
    assert before[table][key][0] == after[table][key][0]  # ... and it kept its id
    assert json.loads(after[table][key][1])["value_text"] == "edited value"
    assert recon.counts["specification"]["updated"] == 1
    assert recon.counts["pricing_offer"]["updated"] == 0


def test_a_corrected_offer_price_keeps_its_id(world):
    url, cat = world
    before = _state(url)
    _edit(cat, "unitree-h2-edu", lambda d: d["pricing_offers"][0].update(price=61111.0))
    ic.run(url, only=ROBOTS)
    after = _state(url)
    key = "unitree-h2-edu|-|reichelt|DE|PURCHASE|NEW"
    assert after["pricing_offer"][key][0] == before["pricing_offer"][key][0]
    assert json.loads(after["pricing_offer"][key][1])["price"] == 61111.0
    assert {t for t, _ in _changed(before, after)} <= {"pricing_offer", "robot"}   # robot: cache
    assert _scalar(url, "SELECT lowest_purchase_price FROM robot WHERE slug='unitree-h2-edu'") \
        is not None


def test_retiring_an_offer_is_an_update_in_place(world):
    url, cat = world
    before = _ids(url)
    _edit(cat, "unitree-h2-edu", lambda d: d["availability_offers"][1].update(is_current=False))
    ic.run(url, only=ROBOTS)
    assert _ids(url) == before
    assert _scalar(url, "SELECT count(*) FROM availability_offer WHERE NOT is_current") == 1


def test_a_new_spec_and_a_new_offer_are_inserted_exactly_once(world):
    url, cat = world
    before = _ids(url)

    def add(doc):
        doc["extended_specs"].append(dict(doc["extended_specs"][0], key="max_speed",
                                          value="9 km/h"))
        offer = dict(doc["pricing_offers"][0], provider_slug="alza-cz", region_code="CZ",
                     transaction_type="RENTAL", price_type="QUOTE_ONLY", price=None)
        doc["pricing_offers"].append({k: v for k, v in offer.items() if k != "evidence"}
                                     | {"evidence": doc["pricing_offers"][0]["evidence"]})

    _edit(cat, "unitree-h2-edu", add)
    first = ic.run(url, only=ROBOTS)
    mid = _ids(url)
    assert first.counts["specification"]["inserted"] == 1
    assert first.counts["pricing_offer"]["inserted"] == 1
    for table in before:                       # every old row kept its id
        assert before[table].items() <= mid[table].items(), table
    assert len(mid["pricing_offer"]) == len(before["pricing_offer"]) + 1
    second = ic.run(url, only=ROBOTS)
    assert all(c["inserted"] == c["updated"] == c["removed"] == 0
               for c in second.counts.values())
    assert _ids(url) == mid


def test_new_evidence_is_inserted_once(world):
    url, cat = world

    def add(doc):
        doc["availability_offers"][0]["evidence"].append(
            {"source_url": "https://example.test/new", "source_type": "MANUFACTURER_SITE",
             "observed_at": "2026-10-01", "confidence": "HIGH"})

    _edit(cat, "unitree-h2-edu", add)
    assert ic.run(url, only=ROBOTS).counts["evidence_source"]["inserted"] == 1
    assert ic.run(url, only=ROBOTS).counts["evidence_source"]["inserted"] == 0


def test_an_image_primary_swap_never_trips_the_unique_index(world):
    url, cat = world
    before = _ids(url)

    def swap(doc):
        first = doc["images"][0]
        second = dict(first, image_url="/robots/second.png", is_primary=True)
        first["is_primary"] = False
        doc["images"].append(second)

    _edit(cat, "agility-digit", swap)
    ic.run(url, only=ROBOTS)
    after = _ids(url)
    assert before["robot_image"].items() <= after["robot_image"].items()
    assert _scalar(url, "SELECT image_url FROM robot_image i JOIN robot r ON r.id = i.robot_id "
                        "WHERE r.slug='agility-digit' AND i.is_primary") == "/robots/second.png"


# ----------------------------------------------------------------- ownership / editorial --

def test_unmanaged_specification_rows_are_preserved(world, capsys):
    url, _ = world
    with psycopg.connect(url) as conn:
        conn.execute("SET search_path TO humanoid, public")
        robot = conn.execute("SELECT id FROM robot WHERE slug='unitree-h2-edu'").fetchone()[0]
        # (1) an unmanaged row on a key the catalogue never writes
        free = conn.execute("INSERT INTO spec_definition (key, label, category, value_type) "
                            "VALUES ('hand_made_key','Hand made','OTHER','TEXT') RETURNING id"
                            ).fetchone()[0]
        conn.execute("INSERT INTO specification (robot_id, definition_id, value_text) "
                     "VALUES (%s,%s,'by hand')", (robot, free))
        # (2) an unmanaged row sitting on a key the catalogue DOES write
        taken = conn.execute(
            "SELECT s.id, s.definition_id FROM specification s JOIN spec_definition d "
            "ON d.id = s.definition_id WHERE s.robot_id=%s AND d.key='battery_pack'", (robot,)
        ).fetchone()
        conn.execute("DELETE FROM specification WHERE id=%s", (taken[0],))
        conn.execute("INSERT INTO specification (robot_id, definition_id, value_text) "
                     "VALUES (%s,%s,'seed value')", (robot, taken[1]))
        conn.commit()
    ic.run(url, only=ROBOTS)
    out = capsys.readouterr().out
    assert "PRESERVED (not overwritten)" in out and "battery_pack" in out
    rows = dict(_exec(url, "SELECT d.key, s.value_text FROM specification s JOIN spec_definition "
                           "d ON d.id = s.definition_id WHERE d.key IN ('hand_made_key',"
                           "'battery_pack')").fetchall())
    assert rows == {"hand_made_key": "by hand", "battery_pack": "seed value"}


@pytest.mark.parametrize("apply_state", [False, True])
def test_is_published_is_editorial(world, apply_state):
    url, cat = world
    _exec(url, "UPDATE robot SET is_published = FALSE WHERE slug = 'unitree-h2-edu'")
    _edit(cat, "unitree-h2-edu", lambda d: (d.update(is_published=True),
                                            d["extended_specs"][0].update(value="edit")))
    ic.run(url, only=ROBOTS, apply_publication_state=apply_state)
    expected = apply_state                    # only the deliberate publishing operation moves it
    assert _scalar(url, "SELECT is_published FROM robot WHERE slug='unitree-h2-edu'") is expected


def test_a_published_robot_stays_published_through_reimport_and_spec_edits(world):
    url, cat = world
    _exec(url, "UPDATE robot SET is_published = TRUE WHERE slug = 'unitree-h2-edu'")
    _edit(cat, "unitree-h2-edu", lambda d: (d.update(is_published=False),
                                            d["extended_specs"][0].update(value="edit")))
    ic.run(url, only=ROBOTS)
    ic.run(url, only=ROBOTS)
    assert _scalar(url, "SELECT is_published FROM robot WHERE slug='unitree-h2-edu'") is True


# ------------------------------------------------------------------------ fail closed --

def test_a_duplicate_key_in_the_json_aborts_with_nothing_written(world):
    url, cat = world
    before, shared = _state(url), _shared(url)

    def twice(doc):
        doc["name"] = "a change that must not be applied"
        doc["availability_offers"].append(dict(doc["availability_offers"][0]))

    _edit(cat, "unitree-h2-edu", twice)
    with pytest.raises(ic.ReconcileRefused, match="duplicate availability offer"):
        ic.run(url, only=ROBOTS)
    assert _state(url) == before and _shared(url) == shared


def test_two_database_rows_on_one_key_abort_and_nothing_is_picked(world):
    url, _ = world
    _exec(url, "INSERT INTO pricing_offer (robot_id, variant_id, provider_id, region_id, "
               "transaction_type, price_type, currency, price, condition) "
               "SELECT robot_id, variant_id, provider_id, region_id, transaction_type, "
               "price_type, currency, price + 1, condition FROM pricing_offer LIMIT 1")
    before = _state(url)
    with pytest.raises(ic.ReconcileRefused, match="ambiguous: 2 existing rows share one natural"):
        ic.run(url, only=ROBOTS)
    assert _state(url) == before


def test_an_omitted_offer_is_preserved_and_reported_and_removed_only_when_authorized(
        world, tmp_path, capsys):
    url, cat = world
    before = _state(url)
    _edit(cat, "unitree-h2-edu", lambda d: d["pricing_offers"].pop(0))
    recon = ic.run(url, only=ROBOTS)                  # D1: nothing is deleted or refused
    assert recon.counts["pricing_offer"]["preserved"] == 1
    assert recon.counts["evidence_source"]["preserved"] == 0
    out = capsys.readouterr().out
    assert "PRESERVED (not in JSON, left untouched)" in out
    assert "pricing_offer of unitree-h2-edu" in out and "reichelt" in out
    assert _state(url) == before                      # not one row or byte changed

    path = _authorize_file(tmp_path, [{
        "action": "remove", "table": "pricing_offer", "robot": "unitree-h2-edu",
        "key": {"variant_slug": None, "provider_slug": "reichelt", "region_code": "DE",
                "transaction_type": "PURCHASE", "condition": "NEW"}}])
    recon = ic.run(url, only=ROBOTS, authorize=path)
    assert recon.counts["pricing_offer"]["removed"] == 1
    assert recon.counts["evidence_source"]["removed"] == 2    # the offer's own evidence goes
    after = _state(url)
    gone = _changed(before, after)
    assert ("pricing_offer", "unitree-h2-edu|-|reichelt|DE|PURCHASE|NEW") in gone
    assert {t for t, _ in gone} <= {"pricing_offer", "evidence_source", "robot"}
    for table in before:                       # every surviving row kept its id
        assert {k: v[0] for k, v in after[table].items()} == \
            {k: v[0] for k, v in before[table].items() if k in after[table]}


def test_the_cli_takes_an_authorize_file(world, tmp_path, capsys):
    url, cat = world
    _edit(cat, "unitree-h2-edu", lambda d: d["pricing_offers"].pop(0))
    argv = ["--database-url", url, "--only", ",".join(sorted(ROBOTS))]
    ic.main(argv)                                     # preserved, reported, nothing removed
    assert "PRESERVED (not in JSON, left untouched)" in capsys.readouterr().out
    entry = {"action": "remove", "table": "pricing_offer", "robot": "unitree-h2-edu",
             "key": {"variant_slug": None, "provider_slug": "reichelt", "region_code": "DE",
                     "transaction_type": "PURCHASE", "condition": "NEW"}}
    ic.main([*argv, "--authorize", str(_authorize_file(tmp_path, [entry]))])
    assert "pricing_offer" in capsys.readouterr().out
    assert _scalar(url, "SELECT count(*) FROM pricing_offer p JOIN robot r ON r.id=p.robot_id "
                        "WHERE r.slug='unitree-h2-edu'") == 2


def test_an_authorization_that_matches_nothing_aborts(world, tmp_path):
    url, _ = world
    before = _state(url)
    stale = {"action": "remove", "table": "pricing_offer", "robot": "unitree-h2-edu",
             "key": {"variant_slug": None, "provider_slug": "nowhere", "region_code": "DE",
                     "transaction_type": "PURCHASE", "condition": "NEW"}}
    with pytest.raises(ic.ReconcileRefused, match="matched nothing"):
        ic.run(url, only=ROBOTS, authorize=_authorize_file(tmp_path, [stale]))
    assert _state(url) == before


def test_removing_a_variant_with_a_dependent_that_is_not_removed_aborts(world, tmp_path):
    url, cat = world
    before = _state(url)
    with psycopg.connect(url) as conn:         # someone else's specification on the variant
        conn.execute("SET search_path TO humanoid, public")
        conn.execute(
            "INSERT INTO specification (robot_id, variant_id, definition_id, value_text) "
            "SELECT v.robot_id, v.id, (SELECT id FROM spec_definition WHERE key='battery_pack'),"
            " 'hand written' FROM robot_variant v JOIN robot r ON r.id = v.robot_id "
            "WHERE r.slug='agility-digit' AND v.slug='digit-v5'")
        conn.commit()
    _edit(cat, "agility-digit", lambda d: d.update(variants=[]))
    entry = {"action": "remove", "table": "robot_variant", "robot": "agility-digit",
             "key": {"slug": "digit-v5"}}
    with pytest.raises(ic.ReconcileRefused, match="still depends on it"):
        ic.run(url, only=ROBOTS, authorize=_authorize_file(tmp_path, [entry]))
    unchanged = {t: v for t, v in _state(url).items() if t != "specification"}
    assert unchanged == {t: v for t, v in before.items() if t != "specification"}


def test_an_authorized_variant_removal_removes_its_dependents_too(world, tmp_path):
    url, cat = world
    doc = json.loads((cat / "robots" / "unitree-h2-edu.json").read_text(encoding="utf-8"))
    on_u2 = [x for x in doc["extended_specs"] if x.get("variant_slug") == "u2"]
    offer_key = {"variant_slug": "u2", "provider_slug": "alza-cz", "region_code": "CZ",
                 "transaction_type": "PURCHASE", "condition": "NEW"}
    entries = [{"action": "remove", "table": t, "robot": "unitree-h2-edu", "key": k}
               for t, k in [("robot_variant", {"slug": "u2"}),
                            ("pricing_offer", offer_key), ("availability_offer", offer_key)]
               + [("specification", {"variant_slug": "u2", "key": x["key"]}) for x in on_u2]]
    _edit(cat, "unitree-h2-edu",
          lambda d: d.update(variants=[], availability_offers=d["availability_offers"][:1],
                             pricing_offers=d["pricing_offers"][:2],
                             extended_specs=[x for x in d["extended_specs"]
                                             if x.get("variant_slug") is None]))
    recon = ic.run(url, only=ROBOTS, authorize=_authorize_file(tmp_path, entries))
    assert recon.counts["robot_variant"]["removed"] == 1
    assert _scalar(url, "SELECT count(*) FROM robot_variant v JOIN robot r ON r.id = v.robot_id "
                        "WHERE r.slug='unitree-h2-edu'") == 0


# ----------------------------------------------------------------- evidence immutability --

def test_evidence_with_a_changed_note_aborts_unless_update_evidence_is_authorized(
        world, tmp_path):
    url, cat = world
    before = _state(url)
    _edit(cat, "unitree-h2-edu",
          lambda d: d["availability_offers"][0]["evidence"][0].update(note="a rewritten note"))
    with pytest.raises(ic.ReconcileRefused) as refused:
        ic.run(url, only=ROBOTS)
    entries = _authorization_in(refused.value)["entries"]
    assert [e["action"] for e in entries] == ["update_evidence"]
    assert entries[0]["table"] == "evidence_source" and entries[0]["robot"] == "unitree-h2-edu"
    assert entries[0]["key"]["subject_type"] == "AVAILABILITY_OFFER"
    assert _state(url) == before

    ic.run(url, only=ROBOTS, authorize=_authorize_file(tmp_path, entries))
    after = _state(url)
    changed = _changed(before, after)
    assert [t for t, _ in changed] == ["evidence_source"]       # same id, note rewritten
    (key,) = [k for _, k in changed]
    assert before["evidence_source"][key][0] == after["evidence_source"][key][0]
    assert json.loads(after["evidence_source"][key][1])["note"] == "a rewritten note"


# ---------------------------------------------------------------------- protected clears --

PROTECTED = [
    ("4ne1-mini", "robot_image", "attribution",
     lambda d: d["images"][0].update(attribution=None)),
    ("unitree-h2-edu", "robot_image", "display_approved_by",
     lambda d: d["images"][0].update(display_approved_by=None)),
    ("unitree-h2-edu", "specification", "source_url",
     lambda d: d["extended_specs"][0].update(source_url=None)),
]


@pytest.mark.parametrize(("slug", "table", "column", "change"), PROTECTED,
                         ids=[f"{t}.{c}" for _, t, c, _ in PROTECTED])
def test_blanking_provenance_needs_a_clear_entry(
        world, tmp_path, slug, table, column, change):
    url, cat = world
    before = _state(url)
    _edit(cat, slug, change)
    with pytest.raises(ic.ReconcileRefused, match=f"erase the stored value of {column}") as refused:
        ic.run(url, only=ROBOTS)
    entries = _authorization_in(refused.value)["entries"]
    assert len(entries) == 1 and entries[0]["action"] == "clear"
    assert entries[0]["column"] == column and entries[0]["table"] == table
    assert _state(url) == before

    ic.run(url, only=ROBOTS, authorize=_authorize_file(tmp_path, entries))
    after = _state(url)
    ((_, key),) = _changed(before, after)
    assert before[table][key][0] == after[table][key][0]
    assert json.loads(after[table][key][1])[column] is None


# --------------------------------------------- D1: no value is erased implicitly (any column) --

BLANKING = [
    ("robot", "summary", lambda d: d.pop("summary"),
     {"table": "robot", "robot": "unitree-h2-edu", "key": {}}),
    ("pricing_offer", "price_basis", lambda d: d["pricing_offers"][0].pop("price_basis"),
     {"table": "pricing_offer", "robot": "unitree-h2-edu",
      "key": {"variant_slug": None, "provider_slug": "reichelt", "region_code": "DE",
              "transaction_type": "PURCHASE", "condition": "NEW"}}),
    ("specification", "source_label",
     lambda d: d["extended_specs"][0].pop("source_label"),
     {"table": "specification", "robot": "unitree-h2-edu",
      "key": {"variant_slug": None, "key": "standing_dimensions_mm"}}),
]


@pytest.mark.parametrize(("change", "entry"), [b[2:] for b in BLANKING],
                         ids=[b[0] for b in BLANKING])
def test_an_absent_field_over_a_stored_value_needs_a_clear_entry(world, tmp_path, change,
                                                                 entry):
    url, cat = world
    before = _state(url)
    _edit(cat, "unitree-h2-edu", change)
    with pytest.raises(ic.ReconcileRefused, match="erase the stored value") as refused:
        ic.run(url, only=ROBOTS)
    (needed,) = _authorization_in(refused.value)["entries"]
    assert needed["action"] == "clear" and needed["table"] == entry["table"]
    assert needed["robot"] == "unitree-h2-edu" and needed["key"] == entry["key"]
    assert _state(url) == before                       # refused: nothing changed

    ic.run(url, only=ROBOTS, authorize=_authorize_file(tmp_path, [needed]))
    after = _state(url)
    assert _changed(before, after)                     # the cleared value, same row id
    for table in before:
        assert {k: v[0] for k, v in before[table].items()} == \
            {k: v[0] for k, v in after[table].items()}


def test_an_explicit_null_is_the_same_as_an_absent_field(world):
    url, cat = world
    _edit(cat, "unitree-h2-edu", lambda d: d.update(summary=None))
    with pytest.raises(ic.ReconcileRefused, match="erase the stored value of summary"):
        ic.run(url, only=ROBOTS)


def test_a_changed_non_null_value_is_a_normal_update(world):
    url, cat = world
    _edit(cat, "unitree-h2-edu", lambda d: d.update(summary="A reworded summary."))
    recon = ic.run(url, only=ROBOTS)
    assert recon.counts["robot"]["updated"] == 1


# ---------------------------------------------------------------- D2: deployments frozen --

def _digit_deployments(url):
    return _exec(url, "SELECT id, status FROM deployment d JOIN robot r ON r.id = d.robot_id "
                      "WHERE r.slug = 'agility-digit'").fetchall()


def test_unchanged_deployments_are_not_written_and_keep_their_ids(world):
    url, _ = world
    before = _state(url)["deployment"]
    assert before
    recon = ic.run(url, only=ROBOTS)
    assert recon.counts["deployment"]["unchanged"] == len(before)
    assert recon.counts["deployment"]["inserted"] == 0
    assert _state(url)["deployment"] == before


@pytest.mark.parametrize("change", [
    lambda d: d["deployments"][0].update(status="an edited status"),
    lambda d: d["deployments"].append(dict(d["deployments"][0], customer_name="Another")),
    lambda d: d.update(deployments=[]),
], ids=["edited", "added", "removed"])
def test_any_other_deployment_situation_is_refused_by_decision_d2(world, change):
    url, cat = world
    before = _state(url)
    _edit(cat, "agility-digit", change)
    with pytest.raises(ic.ReconcileRefused, match="Owner decision D2"):
        ic.run(url, only=ROBOTS)
    assert _state(url) == before


def test_a_remove_authorization_for_a_deployment_is_refused_for_now(world, tmp_path):
    url, _ = world
    entry = {"action": "remove", "table": "deployment", "robot": "agility-digit", "key": {}}
    with pytest.raises(ic.ReconcileRefused, match="not supported"):
        ic.run(url, only=ROBOTS, authorize=_authorize_file(tmp_path, [entry]))


# ------------------------------------------------------------ D3: evidence is versioned --

def test_a_changed_excerpt_is_a_new_evidence_row_and_the_old_one_is_preserved(world, capsys):
    url, cat = world
    before = _state(url)["evidence_source"]

    def reword(doc):
        doc["availability_offers"][0]["evidence"][0]["excerpt"] = "A materially new excerpt."

    _edit(cat, "unitree-h2-edu", reword)
    recon = ic.run(url, only=ROBOTS)
    after = _state(url)["evidence_source"]
    assert recon.counts["evidence_source"]["inserted"] == 1
    assert recon.counts["evidence_source"]["preserved"] == 1
    assert before.items() <= after.items()             # the old row: same id, same content
    assert len(after) == len(before) + 1
    assert "PRESERVED (not in JSON, left untouched)" in capsys.readouterr().out
