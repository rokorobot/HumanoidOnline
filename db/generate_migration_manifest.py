#!/usr/bin/env python
"""Generate the bundled migration manifest shipped inside apps/api.

**Not a migration runner.** This never opens a database connection and never
applies anything — `db/bootstrap.py` remains the one bootstrap truth (R10).
It only reads the canonical `db/schema.sql` + `db/migrations/*.sql` and writes
a small, checked-in Python module (`apps/api/app/db/migration_manifest.py`)
that mirrors `app/db/migration_state.expected_migrations()`.

Why this exists: some deployments (e.g. Vercel with Root Directory=apps/api)
bundle only the `apps/api` tree at runtime, so the canonical repo-root
`db/schema.sql` and `db/migrations/` are not reachable to verify migration
state against. `app/db/migration_state.py` falls back to this bundled
manifest in that case. The manifest is never an independent source of truth —
`test_migration_manifest.py::test_bundled_manifest_matches_canonical_migrations`
recomputes the canonical set on every CI run and fails on any drift, so a
migration change that forgets to regenerate this file is caught, not silently
served stale.

Usage:
    uv run db/generate_migration_manifest.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
OUTPUT_FILE = (
    REPO_ROOT / "apps" / "api" / "app" / "db" / "migration_manifest.py"
)

BASELINE_VERSION = "0000_schema"

HEADER = '''"""GENERATED FILE — do not hand-edit.

Regenerate with:
    uv run db/generate_migration_manifest.py

Bundled fallback for deployments where the canonical repo-root
`db/schema.sql` and `db/migrations/` are not reachable at runtime (e.g.
Vercel with Root Directory=apps/api, which ships only this tree). Mirrors
`app.db.migration_state.expected_migrations()` exactly — same version set,
same sha256 of each forward migration's file content, baseline presence-only.

This is never an independent source of truth: `db/schema.sql` and
`db/migrations/*.sql` remain canonical. Drift between the two is a CI
failure, not a runtime decision — see
`apps/api/tests/test_migration_manifest.py::test_bundled_manifest_matches_canonical_migrations`.
"""
from __future__ import annotations

#: Mirrors app.db.migration_state.BASELINE_VERSION — presence-only, never
#: checksum-compared (db/schema.sql is canonical and is edited in place).
BASELINE_VERSION = "{baseline}"

#: version -> sha256 of the forward migration file's exact text, in the same
#: order db/bootstrap.py applies them. Does NOT include the baseline.
MIGRATIONS: dict[str, str] = {{
{entries}}}
'''


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate() -> str:
    entries = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        checksum = _sha256(path.read_text(encoding="utf-8"))
        # One key per line, value on its own line: every `NNNN_...` version is
        # long enough that `"key": "checksum",` alone can clear ruff's 100-col
        # limit (E501), and a generated file must lint clean like any other.
        entries.append(f'    "{path.stem}": (\n        "{checksum}"\n    ),\n')
    return HEADER.format(baseline=BASELINE_VERSION, entries="".join(entries))


def main() -> None:
    content = generate()
    OUTPUT_FILE.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
