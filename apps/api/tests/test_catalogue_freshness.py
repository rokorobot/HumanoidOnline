"""Automatic catalogue freshness (migration 0026): the CATALOGUE UPDATED date.

`catalogue_freshness` is maintained only by the `record_catalogue_change()` trigger, inside the
transaction that writes the catalogue. What is pinned here:

* a genuine change advances it: a publication, a specification, an offer, an image, a
  governed promotion (the executor's importer opt-ins), any other SQL client (the admin);
* nothing else does: a no-op re-import, a discovery observation, a new evidence observation,
  a refused / rolled-back import, an explicit ROLLBACK, an UPDATE that rewrites equal values;
* the date is the COMMIT time (not the transaction start), never moves backwards, and
  concurrent writers queue only at commit (no lock held for the whole transaction);
* an unpublished-only change is recorded as `latest_update_at` but never moves the public date;
* the row cannot be written, deleted or truncated directly;
* migration 0026 converges onto db/schema.sql, is idempotent, and seeds from stored data;
* /api/market-snapshot exposes the public date as `latest_catalogue_updated_at`.

Real catalogue files on a scratch database.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import threading
import time
from datetime import timedelta

import psycopg
import pytest
from test_identity_decision_migration import _shape, scratch_db  # noqa: F401

REPO = pathlib.Path(__file__).resolve().parents[3]
SCHEMA = (REPO / "db" / "schema.sql").read_text(encoding="utf-8")
MIGRATION = (REPO / "db" / "migrations" / "0026_catalogue_freshness.sql").read_text(
    encoding="utf-8")
PUBLISHED = "unitree-h2-edu"          # published in the catalogue JSON
ROBOTS = {PUBLISHED, "agility-digit"}


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ic = _load("import_catalogue", "db/import_catalogue.py")


@pytest.fixture(autouse=True, params=["importer", "promotion_opt_in"])
def importer_mode(request, monkeypatch):
    """Every importer test runs twice: as a manually authorized import (the defaults) and with
    the governed promotion executor's opt-ins (catalogue-write lock + unchanged-row probe),
    which is exactly how promotion_execute applies an approved manifest."""
    real = ic.run
    if request.param == "promotion_opt_in":
        def lock(cur):
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('catalogue-write'))")

        def run(url, **kw):
            return real(url, before_write=lock, probe_unchanged=True, **kw)

        monkeypatch.setattr(ic, "run", run)
    return request.param


@pytest.fixture
def world(scratch_db, tmp_path, monkeypatch):  # noqa: F811
    cat = tmp_path / "catalogue"
    shutil.copytree(REPO / "db" / "catalogue", cat)
    monkeypatch.setattr(ic, "CATALOGUE_DIR", cat)
    monkeypatch.setattr(ic, "ROBOTS_DIR", cat / "robots")
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA)
        assert _fresh(scratch_db) == (None, None)     # a fresh database is UNKNOWN
    ic.run(scratch_db, only=ROBOTS)
    return scratch_db, cat


def _fresh(url) -> tuple:
    """(latest_public_update_at, latest_update_at)."""
    with psycopg.connect(url) as conn:
        return conn.execute(
            "SELECT latest_public_update_at, latest_update_at "
            "FROM humanoid.catalogue_freshness WHERE id = 1").fetchone()


def _exec(url, sql, params=None):
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SET search_path TO humanoid, public")
        conn.execute(sql, params or ())


def _scalar(url, sql, params=None):
    with psycopg.connect(url) as conn:
        conn.execute("SET search_path TO humanoid, public")
        return conn.execute(sql, params or ()).fetchone()[0]


def _edit(cat, slug, change):
    path = cat / "robots" / f"{slug}.json"
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    change(doc)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _advanced(before, after) -> tuple[bool, bool]:
    return after[0] is not None and (before[0] is None or after[0] > before[0]), \
        after[1] is not None and (before[1] is None or after[1] > before[1])


# ------------------------------------------------------------------- genuine changes --

def test_the_first_import_sets_both_dates(world):
    url, _ = world
    public, everything = _fresh(url)
    assert public is not None and everything is not None and public <= everything
    assert public.tzinfo is not None          # TIMESTAMPTZ: an absolute (UTC) instant


def test_publishing_a_robot_advances_the_date(world):
    url, cat = world
    _exec(url, "UPDATE robot SET is_published = FALSE WHERE slug = %s", (PUBLISHED,))
    before = _fresh(url)
    ic.run(url, only=ROBOTS, apply_publication_state=True)     # the deliberate publication
    assert _advanced(before, _fresh(url)) == (True, True)


def test_unpublishing_a_robot_is_a_public_change(world):
    url, _ = world
    before = _fresh(url)
    _exec(url, "UPDATE robot SET is_published = FALSE WHERE slug = %s", (PUBLISHED,))
    assert _advanced(before, _fresh(url)) == (True, True)


def test_a_specification_change_advances_the_date(world):
    url, cat = world
    before = _fresh(url)
    _edit(cat, PUBLISHED, lambda d: d["extended_specs"][0].update(value="edited for the test"))
    ic.run(url, only=ROBOTS)
    assert _advanced(before, _fresh(url)) == (True, True)


def test_an_offer_change_advances_the_date(world):
    url, cat = world
    before = _fresh(url)
    _edit(cat, PUBLISHED,
          lambda d: d["availability_offers"][0].update(seller_wording="edited for the test"))
    ic.run(url, only=ROBOTS)
    assert _advanced(before, _fresh(url)) == (True, True)


def test_an_image_change_advances_the_date(world):
    url, cat = world
    before = _fresh(url)
    _edit(cat, PUBLISHED, lambda d: d["images"][0].update(attribution="edited for the test"))
    ic.run(url, only=ROBOTS)
    assert _advanced(before, _fresh(url)) == (True, True)


def test_an_admin_edit_outside_the_importer_advances_the_date(world):
    """The internal admin (SQLAdmin) writes through its own SQL session, not the importer;
    the trigger covers it exactly like any other client."""
    url, _ = world
    before = _fresh(url)
    _exec(url, "UPDATE robot SET summary = 'admin edit' WHERE slug = %s", (PUBLISHED,))
    assert _advanced(before, _fresh(url)) == (True, True)


def test_an_unpublished_only_change_is_recorded_but_not_public(world):
    url, _ = world
    _exec(url, "UPDATE robot SET is_published = FALSE WHERE slug = %s", (PUBLISHED,))
    before = _fresh(url)
    _exec(url, "UPDATE robot SET summary = 'draft edit' WHERE slug = %s", (PUBLISHED,))
    _exec(url, "UPDATE specification SET source_label = 'draft' WHERE robot_id = "
               "(SELECT id FROM robot WHERE slug = %s)", (PUBLISHED,))
    after = _fresh(url)
    assert after[0] == before[0]                         # the homepage date did not move
    assert _advanced(before, after)[1] is True           # ... the internal record did


def test_a_shared_record_counts_only_when_a_published_robot_uses_it(world):
    url, _ = world
    before = _fresh(url)
    _exec(url, "INSERT INTO capability (slug, name, category) "
               "SELECT 'unused-cap', 'Unused', category FROM capability LIMIT 1")
    assert _fresh(url)[0] == before[0]
    _exec(url, "UPDATE manufacturer SET description = 'edited' WHERE id = "
               "(SELECT manufacturer_id FROM robot WHERE slug = %s)", (PUBLISHED,))
    assert _advanced(before, _fresh(url))[0] is True


# ---------------------------------------------------------------------- not changes --

def test_a_no_op_reimport_does_not_advance_the_date(world):
    url, _ = world
    before = _fresh(url)
    recon = ic.run(url, only=ROBOTS)
    assert all(c["inserted"] == c["updated"] == c["removed"] == 0
               for c in recon.counts.values())
    assert _fresh(url) == before


def test_an_update_that_rewrites_equal_values_does_not_advance_the_date(world):
    url, _ = world
    before = _fresh(url)
    _exec(url, "UPDATE robot SET name = name, summary = summary WHERE slug = %s", (PUBLISHED,))
    _exec(url, "UPDATE pricing_offer SET price = price")
    assert _fresh(url) == before            # updated_at moved; content did not


def test_a_discovery_observation_does_not_advance_the_date(world):
    url, _ = world
    before = _fresh(url)
    _exec(url, """
        INSERT INTO discovery_source (key, name, source_class)
            VALUES ('fresh-src', 'Fresh source', 'MANUFACTURER');
        INSERT INTO discovery_candidate (source_id, external_ref, candidate_name,
                                         candidate_manufacturer)
            SELECT id, 'ref-1', 'Candidate', 'Maker' FROM discovery_source
            WHERE key = 'fresh-src';
    """)
    assert _fresh(url) == before


def test_a_new_evidence_observation_does_not_advance_the_date(world):
    """Evidence observation is `latest_observed_at`, a distinct metric."""
    url, _ = world
    before = _fresh(url)
    _exec(url, "INSERT INTO evidence_source (subject_type, subject_id, source_type, source_url, "
               "observed_at, confidence) SELECT 'COMMERCIAL_STATUS', id, 'MANUFACTURER_SITE', "
               "'https://example.com/x', now(), 'MEDIUM' FROM robot WHERE slug = %s",
          (PUBLISHED,))
    assert _fresh(url) == before


def test_a_refused_import_rolls_back_the_date(world, tmp_path):
    """The import writes the edit, then refuses in recon.finish(): nothing commits."""
    url, cat = world
    before = _fresh(url)
    _edit(cat, PUBLISHED, lambda d: d["extended_specs"][0].update(value="never committed"))
    stale = {"action": "remove", "table": "pricing_offer", "robot": PUBLISHED,
             "key": {"variant_slug": None, "provider_slug": "nowhere", "region_code": "DE",
                     "transaction_type": "PURCHASE", "condition": "NEW"}}
    path = tmp_path / "authorize.json"
    path.write_text(json.dumps({"version": 1, "entries": [stale]}), encoding="utf-8")
    with pytest.raises(ic.ReconcileRefused, match="matched nothing"):
        ic.run(url, only=ROBOTS, authorize=path)
    assert _fresh(url) == before


def test_a_rolled_back_transaction_does_not_advance_the_date(world):
    url, _ = world
    before = _fresh(url)
    with psycopg.connect(url) as conn:
        conn.execute("SET search_path TO humanoid, public")
        conn.execute("UPDATE robot SET summary = 'rolled back' WHERE slug = %s", (PUBLISHED,))
        assert conn.execute("SELECT latest_public_update_at, latest_update_at "
                            "FROM catalogue_freshness").fetchone() == before   # deferred
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")      # force the write mid-transaction
        assert _advanced(before, conn.execute(
            "SELECT latest_public_update_at, latest_update_at FROM catalogue_freshness"
        ).fetchone()) == (True, True)       # visible inside the transaction only
        conn.rollback()
    assert _fresh(url) == before


# ---------------------------------------------------------- commit-time semantics --

def test_the_date_is_the_commit_time_not_the_transaction_start(world):
    """now() is the transaction START: an import begun at 23:59 UTC and committed at 00:01
    would show the previous day. The recorded time is taken while the transaction commits."""
    url, _ = world
    with psycopg.connect(url) as conn:
        conn.execute("SET search_path TO humanoid, public")
        started = conn.execute("SELECT now()").fetchone()[0]
        conn.execute("UPDATE robot SET summary = 'slow import' WHERE slug = %s", (PUBLISHED,))
        conn.execute("SELECT pg_sleep(1.5)")                # the long tail of a big import
        conn.commit()
    public, everything = _fresh(url)
    assert public - started >= timedelta(seconds=1.5)
    assert everything == public


# ------------------------------------------------------------------- concurrency --

def _conn(url):
    conn = psycopg.connect(url)
    conn.execute("SET search_path TO humanoid, public")
    conn.execute("SET lock_timeout = '10s'")    # a regression fails the test, never hangs it
    return conn


def test_a_transaction_that_commits_last_sets_the_date_even_if_it_started_first(world):
    url, _ = world
    a, b = _conn(url), _conn(url)
    try:
        a.execute("UPDATE robot SET summary = 'A' WHERE slug = %s", (PUBLISHED,))
        b.execute("UPDATE robot SET summary = 'B' WHERE slug = 'agility-digit'")
        b.commit()                                  # B started later, commits first
        after_b = _fresh(url)[0]
        a.execute("SELECT pg_sleep(0.2)")
        a.commit()
        after_a = _fresh(url)[0]
    finally:
        a.close(), b.close()
    assert after_a > after_b                        # A's commit is the newest change
    assert _scalar(url, "SELECT summary FROM robot WHERE slug = %s", (PUBLISHED,)) == "A"
    assert _scalar(url, "SELECT summary FROM robot WHERE slug = 'agility-digit'") == "B"


def test_concurrent_writers_queue_at_commit_and_both_land(world):
    """A holds the freshness row (forced mid-transaction); B, on another robot, waits only for
    the freshness row at its commit, then lands after A with a later date."""
    url, _ = world
    a = _conn(url)
    result = {}

    def writer_b():
        with _conn(url) as b:
            b.execute("UPDATE robot SET summary = 'B' WHERE slug = 'agility-digit'")
            b.commit()
            result["done_at"] = time.monotonic()

    try:
        a.execute("UPDATE robot SET summary = 'A' WHERE slug = %s", (PUBLISHED,))
        a.execute("SET CONSTRAINTS ALL IMMEDIATE")          # A now holds the freshness row
        held = a.execute("SELECT latest_public_update_at FROM catalogue_freshness").fetchone()[0]
        thread = threading.Thread(target=writer_b)
        thread.start()
        time.sleep(1.0)
        assert thread.is_alive()                            # B is queued behind A ...
        assert _scalar(url, "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = "
                            "'Lock' AND query LIKE 'COMMIT%%'") == 1   # ... at its COMMIT
        a.commit()
        committed_a = time.monotonic()
        thread.join(10)
    finally:
        a.close()
    assert not thread.is_alive() and result["done_at"] >= committed_a
    assert _fresh(url)[0] > held                            # B's later commit, never backwards
    assert _scalar(url, "SELECT summary FROM robot WHERE slug = %s", (PUBLISHED,)) == "A"
    assert _scalar(url, "SELECT summary FROM robot WHERE slug = 'agility-digit'") == "B"


def test_crossing_writers_do_not_deadlock_on_the_freshness_row(world):
    """A writes X; B writes Y and commits; A then writes Y. With an immediate trigger, A would
    hold the freshness row from its first write, B would wait for it at commit while holding Y,
    and A's write to Y would deadlock. Deferred to commit, B passes and A follows."""
    url, _ = world
    before = _fresh(url)
    a, b = _conn(url), _conn(url)
    try:
        a.execute("UPDATE robot SET summary = 'A1' WHERE slug = %s", (PUBLISHED,))
        b.execute("UPDATE robot SET summary = 'B' WHERE slug = 'agility-digit'")
        b.commit()                                          # not blocked by A
        a.execute("UPDATE robot SET summary = 'A2' WHERE slug = 'agility-digit'")
        a.commit()
    finally:
        a.close(), b.close()
    assert _advanced(before, _fresh(url)) == (True, True)
    assert _scalar(url, "SELECT summary FROM robot WHERE slug = 'agility-digit'") == "A2"


@pytest.mark.parametrize("statement", [
    "UPDATE catalogue_freshness SET latest_public_update_at = now() + interval '1 day'",
    "DELETE FROM catalogue_freshness",
    "TRUNCATE catalogue_freshness",
])
def test_the_date_cannot_be_written_directly(world, statement):
    url, _ = world
    before = _fresh(url)
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="maintained only"):
        _exec(url, statement)
    assert _fresh(url) == before


# ------------------------------------------------------------------------ migration --

def _populate(conn) -> None:
    conn.execute("""
        SET search_path TO humanoid, public;
        -- stored timestamps given at INSERT (set_updated_at only fires on UPDATE)
        INSERT INTO manufacturer (slug, name, updated_at)
            VALUES ('m-0026', 'Maker 0026', '2026-10-01T00:00:00Z');
        INSERT INTO robot (slug, manufacturer_id, name, is_published, updated_at)
            SELECT 'pub-0026', id, 'Published', true, '2026-10-19T12:00:00Z'
            FROM manufacturer WHERE slug = 'm-0026';
        INSERT INTO robot (slug, manufacturer_id, name, is_published, updated_at)
            SELECT 'draft-0026', id, 'Draft', false, '2026-10-20T08:00:00Z'
            FROM manufacturer WHERE slug = 'm-0026';
    """)


def _wind_back(conn) -> None:
    conn.execute("SET search_path TO humanoid, public")
    conn.execute("DROP TABLE catalogue_freshness CASCADE")
    for t in ("robot", "robot_variant", "robot_image", "specification", "robot_capability",
              "use_case_fit", "pricing_offer", "availability_offer", "deployment",
              "manufacturer", "provider", "capability", "use_case", "spec_definition"):
        conn.execute(f"DROP TRIGGER trg_{t}_catalogue_freshness ON {t}")
    conn.execute("DROP FUNCTION record_catalogue_change(), guard_catalogue_freshness()")


@pytest.mark.parametrize("importer_mode", ["importer"], indirect=True)
def test_0026_converges_onto_the_baseline_and_seeds_from_stored_data(scratch_db):  # noqa: F811
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA)
        baseline = _shape(conn)
        _wind_back(conn)
        _populate(conn)                     # pre-0026 data: no trigger records it
        conn.execute(MIGRATION)
        assert _shape(conn) == baseline
        public, everything = conn.execute(
            "SELECT latest_public_update_at::text, latest_update_at::text "
            "FROM humanoid.catalogue_freshness").fetchone()
        # bootstrap: the published robot's newest stored change; the draft counts internally
        assert public.startswith("2026-10-19 12:00:00")
        assert everything.startswith("2026-10-20 08:00:00")
        conn.execute(MIGRATION)             # idempotent: the seeded row is kept
        assert _shape(conn) == baseline
        assert conn.execute("SELECT latest_public_update_at::text FROM "
                            "humanoid.catalogue_freshness").fetchone()[0] == public


# ------------------------------------------------------------------------------ API --

@pytest.mark.parametrize("importer_mode", ["importer"], indirect=True)
def test_market_snapshot_exposes_the_public_catalogue_date(client, database_url):
    body = client.get("/api/market-snapshot").json()
    assert "latest_catalogue_updated_at" in body and "latest_observed_at" in body
    with psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://")) as conn:
        stored = conn.execute("SELECT latest_public_update_at FROM "
                              "humanoid.catalogue_freshness WHERE id = 1").fetchone()[0]
    if stored is None:
        assert body["latest_catalogue_updated_at"] is None       # UNKNOWN, never invented
    else:
        from datetime import datetime
        assert datetime.fromisoformat(body["latest_catalogue_updated_at"]) == stored
