#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""SQL-first database bootstrap for HumanoidOnline (WS1).

`db/schema.sql` is the canonical baseline (AGENTS.md rule 2). This runner NEVER
generates DDL from ORM models and never edits the canonical files. It applies,
in lexicographic order:

  1. db/schema.sql              as baseline migration `0000_schema`
  2. db/migrations/NNNN_*.sql   forward migrations

Every applied file is recorded in `public.schema_migrations` (version + sha256),
so re-running against an existing database is a no-op. **WS8.2 / R9:** that
sha256 is now actually compared before a file is treated as already applied, so
editing an applied migration fails loudly instead of being silently skipped.
Optionally loads the seed
(`db/seed/seed.sql`), whose embedded G2 self-check aborts the load if any
published commercial fact lacks evidence.

Usage:
    uv run db/bootstrap.py                 # schema + forward migrations
    uv run db/bootstrap.py --seed          # ...then load db/seed/seed.sql
    uv run db/bootstrap.py --seed-only     # load seed only (schema assumed present)

Connection: --database-url or $DATABASE_URL
    e.g. postgresql://user:pass@host:5432/dbname
    (a SQLAlchemy-style "+psycopg" driver token is tolerated and stripped).
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = REPO_ROOT / "db" / "schema.sql"
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
SEED_FILE = REPO_ROOT / "db" / "seed" / "seed.sql"

BASELINE_VERSION = "0000_schema"


def normalize_url(url: str) -> str:
    """psycopg needs a libpq URL; tolerate the SQLAlchemy '+psycopg' driver token."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ensure_tracking_table(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS public.schema_migrations (
            version    TEXT PRIMARY KEY,
            checksum   TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


class MigrationDriftError(RuntimeError):
    """An already-applied migration file has changed since it was applied."""


def _applied(conn: psycopg.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT version, checksum FROM public.schema_migrations"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _governed_files() -> list[tuple[str, Path]]:
    """The canonical baseline plus every forward migration, in apply order."""
    files = [(BASELINE_VERSION, SCHEMA_FILE)]
    files += [(path.stem, path) for path in sorted(MIGRATIONS_DIR.glob("*.sql"))]
    return files


def verify_no_drift(applied: dict[str, str]) -> None:
    """WS8.2 / R9 — actually compare the recorded sha256 before skipping a file.

    The checksum was recorded from the first release but never read back, so an
    edit to an already-applied migration was silently ignored: the file said one
    thing, the database another, and `bootstrap.py` reported "up to date". Drift
    must be loud — it is the difference between a schema you can reason about
    and one you are guessing at.

    This never rewrites history and never invents a down-migration (L7): it
    reports and refuses.

    **The baseline is deliberately excluded.** By this repo's convention
    (db/migrations/README.md) `db/schema.sql` is canonical and is *edited* every
    time the model changes — "schema wins", then a forward migration lets
    existing databases converge. So the `0000_schema` checksum legitimately
    differs from what any older database recorded, and comparing it would flag
    every pre-existing environment as corrupt and refuse to apply the very
    migrations meant to bring it up to date. Forward migrations are the
    immutable history; those are what this verifies.
    """
    drifted: list[str] = []
    for version, path in _governed_files():
        if version == BASELINE_VERSION:
            continue
        recorded = applied.get(version)
        if recorded is None:
            continue  # not applied yet; it is simply pending
        current = _sha256(path.read_text(encoding="utf-8"))
        if current != recorded:
            drifted.append(f"{version} ({path.name})")

    if drifted:
        raise MigrationDriftError(
            "migration checksum drift detected — these files changed after they "
            "were applied:\n  - "
            + "\n  - ".join(drifted)
            + "\n\nAn applied migration is immutable history. Revert the edit, or "
            "add a NEW forward migration expressing the change (db/schema.sql "
            "stays canonical). Nothing has been applied."
        )


def _pending(conn: psycopg.Connection) -> list[tuple[str, Path]]:
    applied = _applied(conn)
    verify_no_drift(applied)
    return [(version, path) for version, path in _governed_files() if version not in applied]


def _apply(conn: psycopg.Connection, version: str, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    print(f"  applying {version} ({path.name}) ...", flush=True)
    # No parameters -> psycopg uses the simple-query protocol, so the whole
    # multi-statement file (including dollar-quoted DO$$ blocks) runs in one shot.
    conn.execute(sql)
    conn.execute(
        "INSERT INTO public.schema_migrations (version, checksum) VALUES (%s, %s)",
        (version, _sha256(sql)),
    )


def run_migrations(url: str) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.transaction():
            _ensure_tracking_table(conn)
        pending = _pending(conn)
        if not pending:
            print("Database up to date; nothing to apply.")
            return
        for version, path in pending:
            with conn.transaction():
                _apply(conn, version, path)
        print(f"Applied {len(pending)} migration(s).")


def load_seed(url: str, seed_path: Path = SEED_FILE) -> None:
    sql = seed_path.read_text(encoding="utf-8")
    print(f"Loading seed {seed_path.name} ...", flush=True)
    # The seed file governs its own BEGIN/COMMIT and runs the G2 self-check;
    # autocommit lets that transaction control stand. A G2 failure RAISEs and
    # propagates here as a non-zero exit.
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql)
    print("Seed loaded; G2 self-check passed.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="HumanoidOnline SQL-first DB bootstrap")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--seed", action="store_true", help="also load db/seed/seed.sql")
    ap.add_argument("--seed-only", action="store_true", help="load the seed only")
    args = ap.parse_args(argv)

    if not args.database_url:
        ap.error("no database URL: pass --database-url or set DATABASE_URL")
    url = normalize_url(args.database_url)

    if args.seed_only:
        load_seed(url)
        return
    try:
        run_migrations(url)
    except MigrationDriftError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    if args.seed:
        load_seed(url)


if __name__ == "__main__":
    main()
