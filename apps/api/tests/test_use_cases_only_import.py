"""`--use-cases-only` (DR-C2): imports use_cases.json and nothing else. DB-backed.

A throwaway database holds the whole repository catalogue (as production would after a full
import), then the use-case file is imported on its own. The point of the mode is that main may
hold merged-but-unimported catalogue changes a full run would also apply, so the test proves
a pending robot change is NOT applied and every table other than `use_case` and the importer's
USE_CASE evidence is untouched.
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import make_url

from app.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]

EV = {
    "source_url": "https://example.test/uco/deployment",
    "source_type": "PRESS_RELEASE",
    "source_title": "Example announcement",
    "excerpt": "Example Robotics and Acme signed a multi-year agreement.",
    "observed_at": "2026-11-02",
    "confidence": "HIGH",
    "claim_fields": ["description"],
}


def _importer():
    spec = importlib.util.spec_from_file_location(
        "import_catalogue", REPO_ROOT / "db" / "import_catalogue.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["import_catalogue"] = mod
    spec.loader.exec_module(mod)
    return mod


def _libpq(url) -> str:
    return url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://", 1)


def _sql(dsn, query, params=()):
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET search_path TO humanoid, public")
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else None


@pytest.fixture()
def scratch(database_url):
    """(dsn, importer) for a scratch DB holding the full repository catalogue."""
    url = make_url(get_settings().resolved_database_url)
    admin = _libpq(url.set(database="postgres"))
    name = f"ho_dr_c2_uco_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    dsn = _libpq(url.set(database=name))
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute((REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        ic = _importer()
        with contextlib.redirect_stdout(io.StringIO()):
            ic.run(dsn)
        # Production before DR-C2 holds no USE_CASE evidence, whatever the repository file
        # carries (the file gains rows when the HO-CONTENT-01 sources move into it).
        _sql(dsn, "DELETE FROM evidence_source WHERE subject_type = 'USE_CASE'")
        yield dsn, ic
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                         " WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _fingerprint(dsn) -> dict[str, str]:
    """A content hash per table, ignoring use_case, USE_CASE evidence and the freshness row
    the write triggers maintain."""
    out = {}
    tables = [r[0] for r in _sql(
        dsn, "SELECT tablename FROM pg_tables WHERE schemaname = 'humanoid' ORDER BY 1")]
    for t in tables:
        if t in ("use_case", "catalogue_freshness"):
            continue
        where = " WHERE subject_type <> 'USE_CASE'" if t == "evidence_source" else ""
        out[t] = _sql(
            dsn, f"SELECT count(*), md5(coalesce(string_agg(x::text, ',' ORDER BY x::text), '')) "
                 f"FROM (SELECT * FROM {t}{where}) x")[0]
    return out


def _use_cases_file(tmp_path, *, evidence=True, mutate=None) -> Path:
    data = json.loads((REPO_ROOT / "db" / "catalogue" / "use_cases.json").read_text("utf-8"))
    for u in data["use_cases"]:
        u.pop("evidence", None)
    if evidence:
        data["use_cases"][0]["evidence"] = [EV]
    if mutate:
        mutate(data)
    path = tmp_path / "use_cases.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _first_slug() -> str:
    """The use case `_use_cases_file` attaches its evidence to."""
    data = json.loads((REPO_ROOT / "db/catalogue/use_cases.json").read_text("utf-8"))
    return data["use_cases"][0]["slug"]


def _uc_evidence(dsn):
    return _sql(dsn, "SELECT u.slug, e.source_url, e.managed_by, e.claim_fields "
                     "FROM evidence_source e JOIN use_case u ON u.id = e.subject_id "
                     "WHERE e.subject_type = 'USE_CASE' ORDER BY 1, 2")


def test_use_cases_only_writes_use_cases_and_their_evidence_and_nothing_else(scratch, tmp_path):
    dsn, ic = scratch
    # A catalogue change pending in the repository but not yet in the database: a full run would
    # apply it; the scoped run must not.
    _sql(dsn, "UPDATE robot SET name = name || ' (pending)' WHERE slug = "
              "(SELECT slug FROM robot ORDER BY slug LIMIT 1)")
    # ... and a use case whose stored text lags the file.
    first_slug = _first_slug()
    _sql(dsn, "UPDATE use_case SET description = 'stale' WHERE slug = %s", (first_slug,))
    before = _fingerprint(dsn)
    path = _use_cases_file(tmp_path)

    with contextlib.redirect_stdout(io.StringIO()):
        recon = ic.run_use_cases_only(dsn, use_cases_path=path)

    assert _fingerprint(dsn) == before            # no other table changed, the robot included
    assert recon.counts["use_case"]["updated"] == 1
    assert recon.counts["evidence_source"]["inserted"] == 1
    assert set(recon.counts) == {"use_case", "evidence_source"}
    assert _uc_evidence(dsn) == [(first_slug, EV["source_url"], ic.MANAGED_BY, ["description"])]
    (desc,) = _sql(dsn, "SELECT description FROM use_case WHERE slug = %s", (first_slug,))[0]
    assert desc != "stale"


def test_use_cases_only_second_run_is_a_noop(scratch, tmp_path):
    dsn, ic = scratch
    path = _use_cases_file(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        ic.run_use_cases_only(dsn, use_cases_path=path)
        mid_fp, mid_ev = _fingerprint(dsn), _uc_evidence(dsn)
        recon = ic.run_use_cases_only(dsn, use_cases_path=path)
    assert (_fingerprint(dsn), _uc_evidence(dsn)) == (mid_fp, mid_ev)
    for table in ("use_case", "evidence_source"):
        c = recon.counts[table]
        assert c["inserted"] == c["updated"] == c["removed"] == 0


def test_use_cases_only_preserves_unmarked_use_case_evidence(scratch, tmp_path):
    dsn, ic = scratch
    slug = _sql(dsn, "SELECT slug FROM use_case ORDER BY slug LIMIT 1")[0][0]
    _sql(dsn, "INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type, "
              "observed_at, confidence, claim_fields) SELECT 'USE_CASE', id, "
              "'https://example.test/uco/manual', 'OTHER', '2026-10-01', 'LOW', "
              "ARRAY['description'] FROM use_case WHERE slug = %s", (slug,))
    with contextlib.redirect_stdout(io.StringIO()):
        ic.run_use_cases_only(dsn, use_cases_path=_use_cases_file(tmp_path, evidence=False))
    rows = _uc_evidence(dsn)
    assert [(r[1], r[2]) for r in rows] == [("https://example.test/uco/manual", None)]


def test_use_cases_only_refuses_bad_data_without_writing(scratch, tmp_path):
    dsn, ic = scratch
    before = (_fingerprint(dsn), _uc_evidence(dsn),
              _sql(dsn, "SELECT md5(string_agg(u::text, ',' ORDER BY slug)) FROM use_case u"))

    def bad_field(d):
        d["use_cases"][0]["evidence"] = [{**EV, "claim_fields": ["name"]}]

    def duplicate(d):
        d["use_cases"][0]["evidence"] = [EV, {**EV, "source_title": "again"}]

    def duplicate_slug(d):
        d["use_cases"].append(copy.deepcopy(d["use_cases"][0]))

    def no_name(d):
        d["use_cases"][0]["name"] = ""

    for mutate, message in [(bad_field, "claim_fields"), (duplicate, "duplicate evidence key"),
                            (duplicate_slug, "duplicate slug"), (no_name, "missing name")]:
        path = _use_cases_file(tmp_path, evidence=False, mutate=mutate)
        with pytest.raises(ic.UseCasesImportAborted, match=message):
            ic.run_use_cases_only(dsn, use_cases_path=path)
    after = (_fingerprint(dsn), _uc_evidence(dsn),
             _sql(dsn, "SELECT md5(string_agg(u::text, ',' ORDER BY slug)) FROM use_case u"))
    assert after == before


def test_a_managed_source_that_left_the_file_is_removed_only_when_authorized(scratch, tmp_path):
    dsn, ic = scratch
    slug = _first_slug()
    with contextlib.redirect_stdout(io.StringIO()):
        ic.run_use_cases_only(dsn, use_cases_path=_use_cases_file(tmp_path))
        ic.run_use_cases_only(dsn, use_cases_path=_use_cases_file(tmp_path, evidence=False))
    assert len(_uc_evidence(dsn)) == 1                     # left untouched without `remove`
    auth = {"version": 1, "entries": [{
        "action": "remove", "table": "evidence_source", "robot": slug,
        "key": {"subject_type": "USE_CASE", "source_url": EV["source_url"],
                "source_type": EV["source_type"], "excerpt": EV["excerpt"],
                "observed_at": EV["observed_at"]}}]}
    with contextlib.redirect_stdout(io.StringIO()):
        ic.run_use_cases_only(dsn, use_cases_path=_use_cases_file(tmp_path, evidence=False),
                              authorize=auth)
    assert _uc_evidence(dsn) == []


@pytest.mark.parametrize("other", ["--only=x", "--manufacturers-only", "--product-lines-only",
                                   "--apply-publication-state"])
def test_the_flag_cannot_be_combined_with_other_modes(other, capsys, monkeypatch):
    ic = _importer()
    monkeypatch.setattr(ic, "run_use_cases_only", lambda *a, **k: pytest.fail("ran"))
    with pytest.raises(SystemExit) as exc:
        ic.main(["--database-url", "postgresql://u@h/d", "--use-cases-only", other])
    assert exc.value.code == 2
    assert "--use-cases-only cannot be combined with" in capsys.readouterr().err


def test_the_flag_dispatches_to_the_scoped_run(monkeypatch):
    ic = _importer()
    seen = {}
    monkeypatch.setattr(ic, "run_use_cases_only", lambda url, **k: seen.update(url=url, **k))
    monkeypatch.setattr(ic, "run", lambda *a, **k: pytest.fail("full run"))
    ic.main(["--database-url", "postgresql+psycopg://u@h/d", "--use-cases-only"])
    assert seen == {"url": "postgresql://u@h/d", "authorize": None}
