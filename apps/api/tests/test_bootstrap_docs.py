"""WS8.2 / R10 — one bootstrap truth, enforced automatically.

The ratified contract declares R10 **[Automated]**, and WS8-L8 permits exactly
one evidence class per gate. A documentation sweep is a human act, so the sweep
alone would have quietly downgraded the gate to Attested — an implementation
slice editing the contract from below. These tests make the gate what it was
frozen as.

What "one bootstrap truth" means concretely: `db/bootstrap.py` applies the
canonical baseline *and* every forward migration *and* records them in
`schema_migrations` with a verified checksum. Any instruction telling a reader
to pipe `db/schema.sql` into `psql` produces a database that looks right, is
silently missing every migration, and cannot be verified — which is exactly the
D6 defect this closes.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Docs a developer or operator could plausibly follow to set up a database.
GOVERNED_DOCS = (
    "README.md",
    "DEVELOPMENT.md",
    "apps/api/README.md",
    "apps/web/README.md",
    "db/migrations/README.md",
    "db/catalogue/README.md",
)

#: Commands that bypass `db/bootstrap.py`. Matched against fenced-code content
#: only, so prose *warning* against them (which README now carries) is allowed.
FORBIDDEN_IN_CODE_BLOCKS = (
    re.compile(r"psql[^\n]*-f\s+db/schema\.sql"),
    re.compile(r"psql[^\n]*--file[= ]\s*db/schema\.sql"),
    re.compile(r"psql[^\n]*<\s*db/schema\.sql"),
)

CODE_BLOCK = re.compile(r"```.*?\n(.*?)```", re.DOTALL)


def _doc(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _code_blocks(text: str) -> list[str]:
    return CODE_BLOCK.findall(text)


@pytest.mark.parametrize("doc", GOVERNED_DOCS)
def test_no_governed_doc_teaches_a_bypass_bootstrap(doc: str) -> None:
    """D6: no runnable instruction may apply schema.sql directly."""
    for block in _code_blocks(_doc(doc)):
        for pattern in FORBIDDEN_IN_CODE_BLOCKS:
            assert not pattern.search(block), (
                f"{doc} contains a runnable command that bypasses "
                f"db/bootstrap.py:\n{block.strip()[:300]}"
            )


def test_readme_names_bootstrap_as_the_canonical_path() -> None:
    readme = _doc("README.md")
    assert "db/bootstrap.py" in readme
    blocks = "\n".join(_code_blocks(readme))
    assert "uv run db/bootstrap.py" in blocks
    # And it must say why the old path was wrong, not just drop it silently.
    assert "psql -f db/schema.sql" in readme, (
        "the README should warn against the removed path, so a reader who "
        "remembers it learns why it disappeared"
    )


def test_seed_is_not_taught_as_a_standalone_psql_step() -> None:
    """`--seed` runs the G2 self-check; piping seed.sql by hand skips nothing
    but does bypass the single documented entry point."""
    for doc in GOVERNED_DOCS:
        for block in _code_blocks(_doc(doc)):
            assert not re.search(r"psql[^\n]*-f\s+db/seed/seed\.sql", block), doc


def test_every_migration_on_disk_is_documented() -> None:
    """D7: `0003` was undocumented. Any future migration must be too, or this
    gate fails — the documentation cannot silently fall behind the directory."""
    readme = _doc("db/migrations/README.md")
    migrations = sorted(p.name for p in (REPO_ROOT / "db" / "migrations").glob("*.sql"))
    assert migrations, "expected forward migrations on disk"
    undocumented = [name for name in migrations if name not in readme]
    assert not undocumented, (
        "db/migrations/README.md does not document: " + ", ".join(undocumented)
    )


def test_migration_docs_state_the_checksum_and_rollback_doctrine() -> None:
    """R9's behaviour has to be discoverable by whoever hits it at 3am."""
    readme = _doc("db/migrations/README.md")
    assert "checksum" in readme.lower()
    assert "down-migration" in readme.lower()


def test_bootstrap_script_is_the_only_migration_runner() -> None:
    """No second runner has appeared (Alembic, a shell wrapper, a make target)."""
    db_dir = REPO_ROOT / "db"
    runners = {p.name for p in db_dir.glob("*.py")}
    assert "bootstrap.py" in runners
    assert not (db_dir / "alembic.ini").exists()
    assert not (REPO_ROOT / "alembic.ini").exists()
