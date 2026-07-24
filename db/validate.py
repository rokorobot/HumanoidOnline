#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Post-bootstrap validation: prove the canonical schema installed and is usable.

Confirms the expected object counts, exercises the canonical access predicate and
the three-dimension snapshot view, and thereby proves a plain client can connect.
Run after `db/bootstrap.py` (and, in CI, after the seed load).

Connection: $DATABASE_URL ("+psycopg" driver token tolerated).
"""
from __future__ import annotations

import os
import sys

import psycopg

EXPECTED_TABLES = 22  # db/schema.sql: validated 22 tables
EXPECTED_VIEWS = 5    # commercial_offer, rental_offer, purchase_offer, lease_offer, snapshot


def normalize_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")

    with psycopg.connect(normalize_url(url)) as conn:
        conn.execute("SET search_path TO humanoid, public")

        tables = conn.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'humanoid' AND table_type = 'BASE TABLE'"
        ).fetchone()[0]
        views = conn.execute(
            "SELECT count(*) FROM information_schema.views "
            "WHERE table_schema = 'humanoid'"
        ).fetchone()[0]
        accessible = conn.execute(
            "SELECT commercially_accessible('AVAILABLE')"
        ).fetchone()[0]
        snapshot_rows = conn.execute(
            "SELECT count(*) FROM robot_commercial_snapshot"
        ).fetchone()[0]

    print(
        f"tables={tables} views={views} "
        f"commercially_accessible('AVAILABLE')={accessible} "
        f"snapshot_rows={snapshot_rows}"
    )

    assert tables >= EXPECTED_TABLES, f"expected >= {EXPECTED_TABLES} tables, got {tables}"
    assert views >= EXPECTED_VIEWS, f"expected >= {EXPECTED_VIEWS} views, got {views}"
    assert accessible is True, "commercially_accessible('AVAILABLE') must be true"
    print("DB validation OK.")


if __name__ == "__main__":
    main()
