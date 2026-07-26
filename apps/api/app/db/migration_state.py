"""WS8.2 / R9 — the migration-before-app-start contract, at application level.

Two separate problems, both real:

1. **Silent drift.** `db/bootstrap.py` records a `sha256` for every applied
   migration but never compared it, so editing an already-applied migration was
   a no-op: the file changed, the database did not, and nothing said so.
2. **Serving an unmigrated schema.** Nothing stopped the API from starting
   against a database missing a migration it depends on.

This module defines the *contract*: the application refuses to serve a database
whose migration state does not match the governed migration set. The *mechanism*
that guarantees migrations have actually run before the process starts (a release
phase, an init container, a deploy step) is bound in WS8.7 — deliberately not
invented here.

Scope discipline (L7): read-only verification. No migration is applied, nothing
is repaired, and no down-migration is invented.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import get_settings

logger = logging.getLogger(__name__)

#: `db/bootstrap.py` records the canonical schema under this version.
BASELINE_VERSION = "0000_schema"

#: apps/api/app/db/migration_state.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]


class MigrationStateError(RuntimeError):
    """Raised when the database's migration state is not what the app requires."""


@dataclass(frozen=True)
class MigrationState:
    """A comparison between the governed files and what the database records.

    `expected` maps version -> sha256, except the baseline, which maps to
    ``None`` meaning *presence-only*. See `expected_migrations` for why.
    """

    expected: dict[str, str | None]
    applied: dict[str, str]

    @property
    def missing(self) -> list[str]:
        """Governed migrations the database has never applied."""
        return sorted(set(self.expected) - set(self.applied))

    @property
    def drifted(self) -> list[str]:
        """Applied migrations whose file content has changed since.

        Versions whose expected checksum is ``None`` (the baseline) are exempt:
        their content is *meant* to evolve.
        """
        return sorted(
            version
            for version, checksum in self.expected.items()
            if checksum is not None
            and version in self.applied
            and self.applied[version] != checksum
        )

    @property
    def ahead(self) -> list[str]:
        """Applied migrations with no corresponding file in *this* build.

        The database is **ahead** of the running code — the normal state during
        an application rollback: version B applied `0004`, B turned out to be
        defective, and the operator rolled the code back to A.

        This is reported loudly but is **not** fatal, because WS8-L7 requires
        that *application rollback remains possible against the migrated
        schema*. Refusing to start here would be the single thing that prevents
        the rollback L7 exists to guarantee — the doctrine's own safety valve,
        wired shut. L7's additive/backward-compatible rule is what makes the
        older build able to run against the newer schema; destructive changes
        are prohibited precisely so this holds.
        """
        return sorted(set(self.applied) - set(self.expected))

    @property
    def is_clean(self) -> bool:
        """Blocking conditions only.

        `ahead` is deliberately excluded: a newer database is a rollback, not a
        fault. Missing and drifted migrations mean the code needs something the
        database does not have, which genuinely cannot be served.
        """
        return not (self.missing or self.drifted)


def sha256_text(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()


def migrations_root() -> Path:
    """Directory holding the governed migration files."""
    configured = get_settings().migrations_dir
    if configured:
        return Path(configured)
    return _REPO_ROOT / "db" / "migrations"


def schema_file() -> Path:
    configured = get_settings().migrations_dir
    if configured:
        # A caller pointing at a bespoke directory owns the baseline too.
        return Path(configured).parent / "schema.sql"
    return _REPO_ROOT / "db" / "schema.sql"


def expected_migrations() -> dict[str, str | None]:
    """version -> sha256 for every forward migration, plus the baseline.

    The baseline maps to ``None`` — **presence-only, never checksum-compared**.
    `db/schema.sql` is canonical and is edited whenever the model changes
    ("schema wins", then a forward migration lets existing databases converge,
    per db/migrations/README.md). Its hash therefore differs legitimately from
    whatever an older database recorded, and comparing it would declare every
    pre-existing environment corrupt. Forward migrations are the immutable
    history worth verifying.

    Mirrors `db/bootstrap.py` exactly: the same versions, hashed the same way.
    If the two ever disagree the checks here become meaningless, so
    `test_migration_integrity.py` pins them together.
    """
    root = migrations_root()
    baseline = schema_file()
    if not baseline.is_file() or not root.is_dir():
        raise MigrationStateError(
            "cannot verify migration state: expected the governed migration "
            f"files at {baseline} and {root}. Set MIGRATIONS_DIR, or run the "
            "application from a deployment that ships them."
        )

    expected: dict[str, str | None] = {BASELINE_VERSION: None}
    for path in sorted(root.glob("*.sql")):
        expected[path.stem] = sha256_text(path.read_text(encoding="utf-8"))
    return expected


def applied_migrations(connection: Connection) -> dict[str, str]:
    """version -> checksum as recorded in `public.schema_migrations`."""
    exists = connection.execute(
        text("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
    ).scalar_one()
    if not exists:
        raise MigrationStateError(
            "public.schema_migrations does not exist: this database has never "
            "been initialised by db/bootstrap.py. The application will not serve "
            "an unmigrated database."
        )
    rows = connection.execute(
        text("SELECT version, checksum FROM public.schema_migrations")
    ).all()
    return {row[0]: row[1] for row in rows}


def inspect_migration_state(connection: Connection) -> MigrationState:
    return MigrationState(
        expected=expected_migrations(), applied=applied_migrations(connection)
    )


def describe(state: MigrationState) -> str:
    parts: list[str] = []
    if state.missing:
        parts.append(f"not applied: {', '.join(state.missing)}")
    if state.drifted:
        parts.append(
            "checksum drift (file edited after it was applied): "
            + ", ".join(state.drifted)
        )
    return "; ".join(parts)


def describe_ahead(state: MigrationState) -> str:
    return (
        "database is ahead of this build (applied but not present here): "
        + ", ".join(state.ahead)
    )


def verify_migration_state(connection: Connection) -> MigrationState:
    """Raise unless the database can serve this build.

    Blocking: a migration this build expects is missing, or one it knows has
    drifted. Non-blocking: the database is *ahead* — surfaced loudly (L7
    rollback compatibility).
    """
    state = inspect_migration_state(connection)
    if not state.is_clean:
        raise MigrationStateError(
            "database migration state does not match this build — "
            f"{describe(state)}. Run `uv run db/bootstrap.py` against this "
            "database before starting the application."
        )
    if state.ahead:
        logger.warning(
            "%s. Continuing: WS8-L7 requires application rollback to remain "
            "possible against a migrated schema, and WS8 migrations are "
            "additive/backward-compatible by doctrine.",
            describe_ahead(state),
        )
    return state


def enforce_migration_state_at_startup(engine) -> MigrationState | None:
    """Startup hook implementing the migration-before-app-start contract.

    Strict environments (staging/production) **refuse to serve** on any
    mismatch. Relaxed environments log a warning instead, so a developer with a
    half-migrated scratch database still gets a usable error surface rather than
    a process that will not boot.
    """
    settings = get_settings()
    try:
        with engine.connect() as connection:
            state = verify_migration_state(connection)
    except MigrationStateError:
        if settings.is_strict:
            raise
        logger.warning(
            "Migration-state check failed, continuing because APP_ENV=%s is a "
            "relaxed environment. This would refuse to start in production.",
            settings.app_env,
            exc_info=True,
        )
        return None
    except Exception:  # pragma: no cover - connectivity, not migration state
        if settings.is_strict:
            raise
        logger.warning(
            "Could not reach the database to verify migration state (APP_ENV=%s).",
            settings.app_env,
        )
        return None

    if state.ahead:
        logger.warning(
            "Migration state OK for this build, but the database is AHEAD: %s.",
            ", ".join(state.ahead),
        )
    logger.info("Migration state verified: %d applied.", len(state.applied))
    return state
