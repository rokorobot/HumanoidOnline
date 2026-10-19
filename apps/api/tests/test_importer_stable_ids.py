"""Importer Hardening Phase 1 acceptance tests.

Design: docs/discovery/STABLE_ID_RECONCILIATION_DESIGN_2026-10-19.md.

Pins the target behaviour of a re-import BEFORE the importer changes:

* idempotency: re-importing unchanged catalogue files changes no business content (passes
  today; must keep passing);
* no ID churn: re-importing unchanged files keeps every row id. This FAILS today, because the
  importer deletes and reinserts a robot's child rows. Those tests are `xfail(strict=True)`:
  when Phase 1 lands they XPASS, strict turns that into a failure, and the marker must be
  removed, so the change is visible rather than silent;
* a one-value edit changes only that row (also xfail until Phase 1);
* a row omitted from the JSON is preserved, id and evidence intact (owner decision D1: routine
  imports never delete by omission; removal is an explicit authorized operation). Also xfail:
  today the reset deletes it.

Real catalogue files on a scratch database; nothing here touches the importer.
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

# Tables with a surrogate `id` that a robot import writes, and how to scope them to ROBOTS.
ID_TABLES = {
    "robot": "SELECT id FROM robot WHERE slug = ANY(%(s)s)",
    "robot_variant": "SELECT t.id FROM robot_variant t JOIN robot r ON r.id = t.robot_id "
                     "WHERE r.slug = ANY(%(s)s)",
    "specification": "SELECT t.id FROM specification t JOIN robot r ON r.id = t.robot_id "
                     "WHERE r.slug = ANY(%(s)s)",
    "pricing_offer": "SELECT t.id FROM pricing_offer t JOIN robot r ON r.id = t.robot_id "
                     "WHERE r.slug = ANY(%(s)s)",
    "availability_offer": "SELECT t.id FROM availability_offer t JOIN robot r "
                          "ON r.id = t.robot_id WHERE r.slug = ANY(%(s)s)",
    "deployment": "SELECT t.id FROM deployment t JOIN robot r ON r.id = t.robot_id "
                  "WHERE r.slug = ANY(%(s)s)",
    "robot_image": "SELECT t.id FROM robot_image t JOIN robot r ON r.id = t.robot_id "
                   "WHERE r.slug = ANY(%(s)s)",
    # evidence whose subject is one of ROBOTS, its manufacturer, or one of its child rows
    "evidence_source": "SELECT e.id FROM evidence_source e WHERE e.subject_id IN ("
                       "SELECT r.id FROM robot r WHERE r.slug = ANY(%(s)s) "
                       "UNION SELECT r.manufacturer_id FROM robot r WHERE r.slug = ANY(%(s)s) "
                       + "".join(f"UNION SELECT t.id FROM {t} t JOIN robot r ON r.id = t.robot_id "
                                 "WHERE r.slug = ANY(%(s)s) "
                                 for t in ("robot_variant", "specification", "pricing_offer",
                                           "availability_offer", "deployment"))
                       + ")",
}
# Ids that already survive a re-import (upserted by natural key). Everything else churns.
STABLE_TODAY = {"robot"}


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


def _ids(url) -> dict[str, set]:
    with psycopg.connect(url) as conn:
        conn.read_only = True
        conn.execute("SET search_path TO humanoid, public")
        return {t: {r[0] for r in conn.execute(q, {"s": sorted(ROBOTS)})}
                for t, q in ID_TABLES.items()}


def _content(url):
    with psycopg.connect(url) as conn:
        conn.read_only = True
        return pf.snapshot(conn)


def test_the_fixture_exercises_every_id_table(world):
    url, _ = world
    assert all(_ids(url).values()), {t: len(v) for t, v in _ids(url).items()}


def test_reimporting_unchanged_files_changes_no_business_content(world):
    url, _ = world
    before = _content(url)
    ic.run(url, only=ROBOTS)
    assert pf.diff(before, _content(url)) == []      # the preflight's id-stripped comparison


@pytest.mark.parametrize("table", sorted(STABLE_TODAY))
def test_ids_that_are_already_stable_stay_stable(world, table):
    url, _ = world
    before = _ids(url)[table]
    ic.run(url, only=ROBOTS)
    assert _ids(url)[table] == before


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Phase 1 not implemented: the importer deletes and reinserts child "
                          "rows, so their ids change")
@pytest.mark.parametrize("table", sorted(set(ID_TABLES) - STABLE_TODAY))
def test_reimporting_unchanged_files_changes_no_ids(world, table):
    url, _ = world
    before = _ids(url)[table]
    ic.run(url, only=ROBOTS)
    assert _ids(url)[table] == before


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Phase 1 not implemented: one edit recreates every child row of the "
                          "robot")
def test_a_one_value_edit_keeps_every_other_id(world):
    url, cat = world
    before = _ids(url)
    path = cat / "robots" / "unitree-h2-edu.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["availability_offers"][0]["seller_wording"] = "edited for the stable-id test"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ic.run(url, only=ROBOTS)
    after = _ids(url)
    for table in set(ID_TABLES) - {"availability_offer"}:
        assert after[table] == before[table], table
    # the edited offer is updated in place, not recreated
    assert after["availability_offer"] == before["availability_offer"]


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Phase 1 not implemented: the importer deletes every child row, so an "
                          "omitted row is lost (D1 requires it to be preserved)")
def test_an_omitted_row_is_preserved(world):
    url, cat = world
    before = _ids(url)
    path = cat / "robots" / "unitree-h2-edu.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    omitted = doc["pricing_offers"].pop(0)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ic.run(url, only=ROBOTS)
    with psycopg.connect(url) as conn:
        conn.execute("SET search_path TO humanoid, public")
        kept = conn.execute(
            "SELECT count(*) FROM pricing_offer o JOIN robot r ON r.id = o.robot_id "
            "JOIN provider p ON p.id = o.provider_id "
            "WHERE r.slug = 'unitree-h2-edu' AND p.slug = %s AND o.price = %s",
            (omitted["provider_slug"], omitted["price"])).fetchone()[0]
    assert kept == 1, "the omitted pricing offer was deleted"
    # omission is not a change: every id, the omitted row's and its evidence's included, survives
    after = _ids(url)
    for table in ID_TABLES:
        assert after[table] == before[table], table
