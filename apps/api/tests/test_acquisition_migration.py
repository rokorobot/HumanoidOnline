"""DATA-D1.LIVE Slice A — migration `0004` convergence.

`db/schema.sql` is canonical and is *edited* when the model changes; a forward
migration then brings existing databases to the same shape
(db/migrations/README.md). The failure that convention invites is **drift**: the
baseline and the migration diverge, so a fresh database and an upgraded one end
up structurally different, and every later assumption is made against whichever
one the developer happened to test.

This module proves they converge, against a real database and without pinning a
git SHA: it takes a scratch copy of the current schema, strips it back to its
`0003` state, applies `0004`, and compares the recovered shape column-for-column
with the baseline.

Skipped when no database is configured.
"""
from __future__ import annotations

import pathlib
import uuid

import psycopg
import pytest
from sqlalchemy import make_url

from app.config import get_settings

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_SQL = ROOT / "db" / "schema.sql"
MIGRATION_0004 = ROOT / "db" / "migrations" / "0004_add_live_acquisition_layer.sql"

#: Everything `0004` introduces. Dropping exactly this set puts a database back
#: into its `0003` shape, which is what makes the round trip meaningful.
NEW_TABLES = (
    "discovery_evidence_excerpt",
    "candidate_commercial_signal",
    "extraction_result",
    "fetched_page",
    "crawl_run",
    "source_eligibility_review",
)
NEW_TYPES = (
    "crawl_run_status", "crawl_trigger", "fetch_outcome", "extraction_method",
    "extraction_confidence", "signal_axis", "eligibility_decision",
    "extraction_status", "evidence_subject_type",
)
NEW_COLUMNS = {
    "discovery_source": (
        "allowed_path_prefixes", "tos_reviewed_at", "tos_expires_at", "tos_page_hash",
        "last_robots_hash", "last_robots_checked_at", "last_crawled_at",
    ),
    "candidate_claim": (
        "extractor_key", "extractor_version", "extraction_method",
        "extraction_confidence", "crawl_run_id", "fetched_page_id",
    ),
    "candidate_image_ref": (
        "page_url", "retrieved_at", "declared_credit", "attribution_claimed",
        "alt_text", "retrieval_source_class", "crawl_run_id", "fetched_page_id",
    ),
}

INSPECT_COLUMNS = """
    SELECT table_name, column_name, data_type, udt_name, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'humanoid'
    ORDER BY table_name, column_name
"""
INSPECT_CONSTRAINTS = """
    SELECT c.conname, c.contype, rel.relname
    FROM pg_constraint c
    JOIN pg_class rel ON rel.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = rel.relnamespace
    WHERE n.nspname = 'humanoid'
    ORDER BY rel.relname, c.conname
"""


def _libpq_dsn(url) -> str:
    """A libpq DSN. `str(URL)` MASKS the password as `***`, which fails auth in a
    way that looks like a credentials problem rather than a formatting one."""
    return url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )


@pytest.fixture
def scratch_db(database_url):
    """A disposable database, created and dropped around EACH test.

    A scratch database rather than the shared one: these tests DROP tables, which
    must never happen anywhere a developer keeps data. Per-test rather than
    per-module because each one applies the baseline from scratch, and a shared
    database would make the second application fail on objects the first created.
    """
    url = make_url(get_settings().resolved_database_url)
    admin_dsn = _libpq_dsn(url.set(database="postgres"))
    name = f"slice_a_upgrade_{uuid.uuid4().hex[:12]}"

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        yield _libpq_dsn(url.set(database=name))
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                " WHERE datname = %s AND pid <> pg_backend_pid()",
                (name,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _shape(conn) -> tuple[list, list]:
    columns = conn.execute(INSPECT_COLUMNS).fetchall()
    constraints = conn.execute(INSPECT_CONSTRAINTS).fetchall()
    return columns, constraints


def test_migration_0004_converges_a_0003_database_onto_the_baseline(scratch_db) -> None:
    """Apply the baseline, wind it back to `0003`, then let `0004` rebuild it.

    Column-for-column and constraint-for-constraint equality is the assertion
    that matters: it is what guarantees an operator upgrading a live database
    ends up with the same schema a fresh install gets, including the CHECK
    constraints that carry the contract's laws.
    """
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        baseline_columns, baseline_constraints = _shape(conn)

        # --- wind back to the 0003 shape -----------------------------------
        conn.execute("SET search_path TO humanoid, public")
        for table in NEW_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS humanoid.{table} CASCADE")
        for table, columns in NEW_COLUMNS.items():
            for column in columns:
                conn.execute(f"ALTER TABLE humanoid.{table} DROP COLUMN IF EXISTS {column}")
        for type_name in NEW_TYPES:
            conn.execute(f"DROP TYPE IF EXISTS humanoid.{type_name}")

        reduced_columns, _ = _shape(conn)
        assert len(reduced_columns) < len(baseline_columns), (
            "the wind-back removed nothing, so the round trip would prove nothing"
        )

        # --- apply the forward migration -----------------------------------
        conn.execute(MIGRATION_0004.read_text(encoding="utf-8"))
        upgraded_columns, upgraded_constraints = _shape(conn)

    assert upgraded_columns == baseline_columns, (
        "migration 0004 and db/schema.sql disagree on columns:\n"
        f"only in baseline: {sorted(set(baseline_columns) - set(upgraded_columns))}\n"
        f"only in upgraded: {sorted(set(upgraded_columns) - set(baseline_columns))}"
    )
    assert set(upgraded_constraints) == set(baseline_constraints), (
        "migration 0004 and db/schema.sql disagree on constraints:\n"
        f"only in baseline: {sorted(set(baseline_constraints) - set(upgraded_constraints))}\n"
        f"only in upgraded: {sorted(set(upgraded_constraints) - set(baseline_constraints))}"
    )


def test_migration_0004_is_idempotent(scratch_db) -> None:
    """Re-applying it must be a no-op.

    The bootstrap already skips applied migrations by checksum, so this is not
    the normal path — but a migration that only works once is a trap for anyone
    recovering a half-applied upgrade, which is exactly when it will be re-run.
    """
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        sql = MIGRATION_0004.read_text(encoding="utf-8")
        conn.execute(sql)
        first_columns, first_constraints = _shape(conn)
        conn.execute(sql)   # again
        second_columns, second_constraints = _shape(conn)

    assert second_columns == first_columns
    assert second_constraints == first_constraints


def test_existing_0003_rows_survive_the_upgrade(scratch_db) -> None:
    """The additive promise, tested with data rather than asserted.

    A source row carrying a value that only existed before the widening
    (`MANUFACTURER`) must be readable and unchanged afterwards — that is what
    "no rename, no removal, no re-mapping" means for an operator with a
    populated database.
    """
    with psycopg.connect(scratch_db, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.execute("SET search_path TO humanoid, public")

        # Wind back to 0003 and insert a pre-upgrade row.
        for table in NEW_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS humanoid.{table} CASCADE")
        for table, columns in NEW_COLUMNS.items():
            for column in columns:
                conn.execute(f"ALTER TABLE humanoid.{table} DROP COLUMN IF EXISTS {column}")

        conn.execute(
            "INSERT INTO discovery_source (key, name, source_class, tos_status,"
            " robots_status) VALUES ('legacy', 'Legacy Source', 'MANUFACTURER',"
            " 'PROHIBITED', 'ALLOWED')"
        )
        source_id = conn.execute(
            "SELECT id FROM discovery_source WHERE key = 'legacy'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO discovery_candidate (source_id, external_ref, candidate_name)"
            " VALUES (%s, 'legacy-1', 'Legacy Robot')",
            (source_id,),
        )
        conn.execute(
            "INSERT INTO candidate_claim (candidate_id, field_key, claimed_value,"
            " discovery_source_id) SELECT id, 'payload_kg', '30', %s"
            " FROM discovery_candidate WHERE external_ref = 'legacy-1'",
            (source_id,),
        )

        conn.execute(MIGRATION_0004.read_text(encoding="utf-8"))

        row = conn.execute(
            "SELECT source_class::text, tos_status::text, is_enabled,"
            " allowed_path_prefixes FROM discovery_source WHERE key = 'legacy'"
        ).fetchone()
        claim = conn.execute(
            "SELECT claimed_value, claim_status::text, discovery_source_id,"
            " extraction_confidence FROM candidate_claim WHERE field_key = 'payload_kg'"
        ).fetchone()

    # The shipped enum value survived, and nothing was silently re-mapped.
    assert row[0] == "MANUFACTURER"
    assert row[1] == "PROHIBITED"
    assert row[2] is False, "the upgrade must not enable a source"
    assert row[3] is None, "new columns arrive NULL, not with an invented default"
    # The claim survived with its provenance intact and remains unverified.
    assert claim[0] == "30"
    assert claim[1] == "NOT_VERIFIED"
    assert claim[2] == source_id
    assert claim[3] is None
