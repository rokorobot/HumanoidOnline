"""`--manufacturers-only` — company profiles and company evidence, nothing else.

The production rollout of the manufacturer profile enrichment must update
manufacturer data without refreshing any robot record: a full import replaces
the child rows (offers, evidence, images, specifications) of every robot, and
`--only` still imports the robots it selects. These tests pin the mode that
does not:

* incompatible options (robot selection, publication state) are rejected before
  anything connects;
* robot files are never read, and no statement touches a robot-side table,
  providers or regions;
* only the importer's own (catalogue-managed) MANUFACTURER evidence is replaced —
  every unmarked row survives untouched, and one sharing a source's URL/type/date
  is reported as a collision without any claim about who wrote it;
* invalid data or an unknown region aborts before the first write, and a failure
  mid-import is never committed.

No database: the mutation shape is asserted with a recording connection. The
same behaviour is rehearsed against a populated throwaway Postgres before any
production use.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE = REPO_ROOT / "db" / "catalogue"
_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO_ROOT / "db" / "import_catalogue.py"
)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)

MANUFACTURERS = json.loads((CATALOGUE / "manufacturers.json").read_text(encoding="utf-8"))
REGION_CODES = [
    r["code"]
    for r in json.loads((CATALOGUE / "regions.json").read_text(encoding="utf-8"))["regions"]
]

#: Every table a manufacturer-only run may write.
WRITABLE = {"manufacturer", "evidence_source"}
WRITE = re.compile(r"^(INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)", re.IGNORECASE)


class _Cursor:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.rowcount = 0
        self._last = ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        self.conn.calls.append((text, tuple(params or ())))
        self._last = text
        if text.startswith("INSERT INTO evidence_source"):
            self.conn.evidence_inserts += 1
            if self.conn.fail_on_evidence_insert == self.conn.evidence_inserts:
                raise RuntimeError("simulated failure mid-import")
        self.rowcount = 0
        return self

    def fetchone(self):
        if self._last.startswith("SELECT count(*)"):
            return (0,)
        return (1,)

    def fetchall(self):
        if self._last.startswith("SELECT code, id FROM region"):
            return [(code, i) for i, code in enumerate(self.conn.region_codes)]
        return []


class _Connection:
    def __init__(self, region_codes=None, fail_on_evidence_insert=None) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.region_codes = list(REGION_CODES if region_codes is None else region_codes)
        self.fail_on_evidence_insert = fail_on_evidence_insert
        self.evidence_inserts = 0
        self.committed = False
        self.exited_with: type[BaseException] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # psycopg rolls the transaction back when the block exits with an exception.
        self.exited_with = exc_type
        return False

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.committed = True

    def writes(self) -> list[tuple[str, str, tuple]]:
        out = []
        for sql, params in self.calls:
            match = WRITE.match(sql)
            if match:
                out.append((match.group(2).lower(), sql, params))
        return out


@pytest.fixture
def connection(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(ic.psycopg, "connect", lambda *a, **k: conn)
    return conn


def _no_connection(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a connection was opened")
    monkeypatch.setattr(ic.psycopg, "connect", refuse)


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "manufacturers.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- CLI ------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("extra", "named"),
    [
        (["--only", "unitree-g1"], "--only"),
        (["--apply-publication-state"], "--apply-publication-state"),
        (
            ["--only", "unitree-g1", "--apply-publication-state"],
            "--only, --apply-publication-state",
        ),
    ],
)
def test_cli_rejects_manufacturers_only_with_robot_or_publication_options(
    monkeypatch, capsys, extra, named
) -> None:
    _no_connection(monkeypatch)
    monkeypatch.setattr(ic, "run", lambda *a, **k: pytest.fail("full import ran"))
    monkeypatch.setattr(
        ic, "run_manufacturers_only", lambda *a, **k: pytest.fail("manufacturer import ran")
    )
    with pytest.raises(SystemExit) as exc:
        ic.main(["--database-url", "postgresql://unused", "--manufacturers-only", *extra])
    assert exc.value.code == 2
    assert f"--manufacturers-only cannot be combined with {named}" in capsys.readouterr().err


def test_cli_dispatches_manufacturers_only_instead_of_the_catalogue_import(monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(ic, "run", lambda *a, **k: pytest.fail("full import ran"))
    monkeypatch.setattr(ic, "run_manufacturers_only", lambda url, **k: seen.append(url))
    ic.main(["--database-url", "postgresql+psycopg://u:p@h/db", "--manufacturers-only"])
    assert seen == ["postgresql://u:p@h/db"]


# --- scope ------------------------------------------------------------------------

def test_manufacturers_only_reads_no_robot_file_and_writes_only_company_rows(
    monkeypatch, connection
) -> None:
    loaded: list[Path] = []
    real_load = ic._load
    monkeypatch.setattr(ic, "_load", lambda p: loaded.append(Path(p)) or real_load(p))
    monkeypatch.setattr(
        ic, "select_robot_files", lambda *a, **k: pytest.fail("robot files selected")
    )

    ic.run_manufacturers_only("postgresql://unused")

    assert loaded == [CATALOGUE / "manufacturers.json"]
    tables = {table for table, _, _ in connection.writes()}
    assert tables <= WRITABLE, tables - WRITABLE
    for table, sql, _ in connection.writes():
        if table == "evidence_source":
            assert "subject_type='MANUFACTURER'" in sql or sql.startswith("INSERT"), sql
    for sql, params in connection.calls:
        if sql.startswith("INSERT INTO evidence_source"):
            assert params[0] == "MANUFACTURER", sql
    assert connection.committed


def test_company_evidence_refresh_deletes_only_catalogue_managed_rows(connection) -> None:
    ic.run_manufacturers_only("postgresql://unused")
    deletes = [
        (sql, p) for _, sql, p in connection.writes()
        if sql.startswith("DELETE FROM evidence_source")
    ]
    assert deletes, "no evidence refresh happened"
    for sql, params in deletes:
        # Only the importer's own marked rows — never an unmarked row, whatever
        # its content.
        assert "subject_type='MANUFACTURER'" in sql
        assert "managed_by = %s" in sql and params[-1] == ic.MANAGED_BY, sql
        assert "managed_by IS NULL" not in sql, sql
    assert not any(
        sql.startswith("UPDATE evidence_source") for _, sql, _ in connection.writes()
    )
    inserts = [
        p for _, sql, p in connection.writes()
        if sql.startswith("INSERT INTO evidence_source")
    ]
    expected = sum(len(m.get("evidence") or []) for m in MANUFACTURERS["manufacturers"])
    assert len(inserts) == expected
    assert all(p[-1] == ic.MANAGED_BY for p in inserts)


def test_full_import_manufacturer_step_uses_the_same_owned_row_refresh() -> None:
    class Recording:
        def __init__(self):
            self.sql: list[str] = []

        def execute(self, sql, params=None):
            self.sql.append(" ".join(str(sql).split()))
            return self

        def fetchone(self):
            return (1,)

    cur = Recording()
    ic.import_manufacturers(cur, MANUFACTURERS, lambda code: None)
    blanket = [
        s for s in cur.sql
        if s.startswith("DELETE FROM evidence_source") and "managed_by" not in s
    ]
    assert not blanket, blanket


# --- validation before writing -----------------------------------------------------

def test_the_catalogue_validates_clean() -> None:
    assert ic.validate_manufacturer_profiles(MANUFACTURERS) == []


def _broken(mutate) -> dict:
    data = copy.deepcopy(MANUFACTURERS)
    mutate(data["manufacturers"])
    return data


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda ms: ms[0].update(deployment_status="SHIPPING"), "is not a commercial_status"),
        (lambda ms: ms[1].update(slug=ms[0]["slug"]), "duplicate slug"),
        (lambda ms: ms[0].update(ticker="NYSE: XX", is_public_company=None), "ticker given"),
        (
            lambda ms: ms[0].update(parent_listing="NYSE: XX", parent_company=None),
            "without parent_company",
        ),
        (lambda ms: ms[0].update(founded_year=1800), "outside 1900-2100"),
        (
            lambda ms: [ev.update(claim_fields=[]) for ev in ms[0]["evidence"]],
            "asserted but no evidence row claims",
        ),
        (lambda ms: ms[0]["evidence"][0].update(source_type="BLOG"), "is not a source_type"),
        (lambda ms: ms[0]["evidence"][1].update(verified_at="2026-09-13"), "marked verified"),
    ],
)
def test_invalid_manufacturer_data_aborts_before_connecting(
    monkeypatch, tmp_path, mutate, message
) -> None:
    _no_connection(monkeypatch)
    path = _write(tmp_path, _broken(mutate))
    with pytest.raises(ic.ManufacturerImportAborted) as exc:
        ic.run_manufacturers_only("postgresql://unused", manufacturers_path=path)
    assert message in str(exc.value)


def test_unknown_region_aborts_before_the_first_write(monkeypatch) -> None:
    conn = _Connection(region_codes=[c for c in REGION_CODES if c != "HK"])
    monkeypatch.setattr(ic.psycopg, "connect", lambda *a, **k: conn)
    with pytest.raises(ic.ManufacturerImportAborted) as exc:
        ic.run_manufacturers_only("postgresql://unused")
    assert "HK" in str(exc.value)
    assert conn.writes() == []
    assert not conn.committed
    assert conn.exited_with is ic.ManufacturerImportAborted


def test_a_failure_mid_import_is_never_committed(monkeypatch) -> None:
    conn = _Connection(fail_on_evidence_insert=5)
    monkeypatch.setattr(ic.psycopg, "connect", lambda *a, **k: conn)
    with pytest.raises(RuntimeError, match="simulated failure"):
        ic.run_manufacturers_only("postgresql://unused")
    assert conn.writes(), "the failure should come after writes began"
    assert not conn.committed
    assert conn.exited_with is RuntimeError


def test_collisions_are_reported_without_asserting_ownership(monkeypatch, capsys) -> None:
    class CollidingCursor(_Cursor):
        def fetchone(self):
            # An unmarked row shares every catalogue source's URL/type/date.
            if self._last.startswith("SELECT count(*)") and "source_url" in self._last:
                return (1,)
            return super().fetchone()

    class CollidingConnection(_Connection):
        def cursor(self):
            return CollidingCursor(self)

    conn = CollidingConnection()
    monkeypatch.setattr(ic.psycopg, "connect", lambda *a, **k: conn)

    totals = ic.run_manufacturers_only("postgresql://unused")

    expected = sum(len(m.get("evidence") or []) for m in MANUFACTURERS["manufacturers"])
    assert len(totals["collisions"]) == expected
    out = capsys.readouterr().out
    assert out.count(ic.EVIDENCE_COLLISION_LABEL) == expected
    assert "adopted" not in out
    assert "pre-marker importer" not in out
