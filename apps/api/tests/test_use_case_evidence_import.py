"""DR-C2: use-case evidence (``subject_type='USE_CASE'``) through the importer.

Mirrors ``test_catalogue_import_evidence_collisions.py`` (the manufacturer analogue).
The validation tests are pure. The reconciliation tests run the importer's real SQL
inside one transaction that is rolled back, so the shared database is left as found.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "import_catalogue", REPO_ROOT / "db" / "import_catalogue.py"
)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)

SOURCE = {
    "source_url": "https://example.test/use-case/deployment",
    "source_type": "PRESS_RELEASE",
    "source_title": "Example deployment announcement",
    "excerpt": "Example Robotics and Acme signed a multi-year agreement.",
    "observed_at": "2026-11-02",
    "confidence": "HIGH",
    "claim_fields": ["description"],
}


def _data(*evidence, slug="uc-test") -> dict:
    return {"use_cases": [{"slug": slug, "name": "Test", "evidence": list(evidence)}]}


# --------------------------------------------------------------------------- validation


def test_a_well_formed_use_case_evidence_row_is_clean() -> None:
    assert ic.validate_use_case_evidence(_data(SOURCE)) == []
    # `evidence` is optional per use case.
    assert ic.validate_use_case_evidence({"use_cases": [{"slug": "x", "name": "X"}]}) == []


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        ({"source_type": "TWEET"}, "source_type"),
        ({"source_type": None}, "source_type"),
        ({"confidence": "CERTAIN"}, "confidence"),
        ({"observed_at": None}, "observed_at"),
        ({"claim_fields": None}, "claim_fields"),
        ({"claim_fields": []}, "claim_fields"),
        ({"claim_fields": ["name"]}, "claim_fields"),          # not a claimable field
        ({"claim_fields": ["description", "legal_name"]}, "claim_fields"),  # manufacturer field
        ({"note": ic.AGENT_RETRIEVAL_PREFIX + " ...", "verified_at": "2026-11-02"},
         "marked verified"),
    ],
)
def test_invalid_use_case_evidence_is_refused(edit, message) -> None:
    errors = ic.validate_use_case_evidence(_data({**SOURCE, **edit}))
    assert len(errors) == 1 and message in errors[0] and "uc-test evidence[0]" in errors[0]


def test_every_use_case_text_field_is_claimable() -> None:
    fields = ["description", "typical_requirements", "key_limitations", "typical_tasks"]
    assert ic.validate_use_case_evidence(_data({**SOURCE, "claim_fields": fields})) == []


def test_a_duplicate_evidence_key_is_refused() -> None:
    errors = ic.validate_use_case_evidence(_data(SOURCE, {**SOURCE, "source_title": "Again"}))
    assert len(errors) == 1 and "duplicate evidence key" in errors[0]
    # A different excerpt or observed day is a different key.
    assert ic.validate_use_case_evidence(
        _data(SOURCE, {**SOURCE, "excerpt": "Another fact."},
              {**SOURCE, "observed_at": "2026-11-03"})) == []


def test_the_repository_catalogue_use_case_evidence_is_valid() -> None:
    data = ic._load(ic.CATALOGUE_DIR / "use_cases.json")
    assert ic.validate_use_case_evidence(data) == []


def test_an_invalid_file_aborts_a_run_before_a_connection_opens(monkeypatch, tmp_path) -> None:
    """run() reads the validator's problems before psycopg.connect: nothing is written."""
    bad = _data({**SOURCE, "claim_fields": ["name"]})
    real_load = ic._load
    monkeypatch.setattr(
        ic, "_load",
        lambda p: bad if Path(p).name == "use_cases.json" else real_load(p))

    def no_connection(*a, **k):
        raise AssertionError("connected despite an invalid catalogue")

    monkeypatch.setattr(ic.psycopg, "connect", no_connection)
    with pytest.raises(ic.ReconcileRefused, match=r"claim_fields"):
        ic.run("postgresql://unused")


# --------------------------------------------------------------------------- reconciliation


@pytest.fixture
def cur(database_url):
    conn = psycopg.connect(ic.normalize_url(database_url), autocommit=False)
    cursor = conn.cursor()
    cursor.execute("SET search_path TO humanoid, public")
    try:
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def _import(cur, slug, *evidence, recon=None):
    data = {"use_cases": [{"slug": slug, "name": "Test use case", "evidence": list(evidence)}]}
    own = recon is None
    recon = recon or ic.Reconciliation()
    ic.import_use_cases(cur, data, recon)
    if own:
        recon.finish()
    return recon


def _slug() -> str:
    return f"uc-evidence-{uuid.uuid4().hex[:10]}"


def _rows(cur, slug, managed=True):
    return cur.execute(
        "SELECT e.id, e.subject_type::text, e.source_url, e.claim_fields, e.managed_by, "
        "       e.excerpt, e.confidence::text "
        "FROM evidence_source e JOIN use_case u ON u.id = e.subject_id "
        "WHERE e.subject_type = 'USE_CASE' AND u.slug = %s AND "
        + ("e.managed_by = %s" if managed else "e.managed_by IS DISTINCT FROM %s")
        + " ORDER BY e.source_url", (slug, ic.MANAGED_BY)).fetchall()


def test_import_writes_managed_use_case_rows_and_a_rerun_is_a_no_op(cur) -> None:
    slug = _slug()
    second = {**SOURCE, "source_url": "https://example.test/use-case/figures",
              "claim_fields": ["description", "key_limitations"]}
    recon = _import(cur, slug, SOURCE, second)
    assert recon.counts["evidence_source"]["inserted"] == 2
    first_rows = _rows(cur, slug)
    assert [r[1] for r in first_rows] == ["USE_CASE", "USE_CASE"]
    assert {r[4] for r in first_rows} == {ic.MANAGED_BY}
    assert {tuple(r[3]) for r in first_rows} == {("description",),
                                                 ("description", "key_limitations")}

    recon = _import(cur, slug, SOURCE, second)       # same ids, no write, no duplicate
    assert recon.counts["evidence_source"]["inserted"] == 0
    assert recon.counts["evidence_source"]["unchanged"] == 2
    assert _rows(cur, slug) == first_rows


def test_unmarked_use_case_rows_are_never_touched(cur) -> None:
    slug = _slug()
    _import(cur, slug)
    uc_id = cur.execute("SELECT id FROM use_case WHERE slug=%s", (slug,)).fetchone()[0]
    ic.insert_evidence(cur, "USE_CASE", uc_id, {**SOURCE, "claim_fields": ["description"]})
    before = _rows(cur, slug, managed=False)
    assert len(before) == 1

    # Same URL, type and day as the catalogue source: preserved, never adopted or removed.
    _import(cur, slug, SOURCE)
    _import(cur, slug)                      # and the catalogue dropping every source
    assert _rows(cur, slug, managed=False) == before
    assert len(_rows(cur, slug)) == 1       # the importer's own row (removal not authorized)


def test_a_managed_source_that_left_the_json_is_removed_only_when_authorized(cur) -> None:
    slug = _slug()
    other = {**SOURCE, "source_url": "https://example.test/use-case/other"}
    _import(cur, slug, SOURCE, other)

    _import(cur, slug, other)               # SOURCE left the file ...
    assert len(_rows(cur, slug)) == 2       # ... and is left untouched

    auth = {"version": 1, "entries": [{
        "action": "remove", "table": "evidence_source", "robot": slug,
        "key": {"subject_type": "USE_CASE", "source_url": SOURCE["source_url"],
                "source_type": SOURCE["source_type"], "excerpt": SOURCE["excerpt"],
                "observed_at": SOURCE["observed_at"]}}]}
    recon = ic.Reconciliation(auth)
    _import(cur, slug, other, recon=recon)
    recon.finish()
    assert [r[2] for r in _rows(cur, slug)] == [other["source_url"]]


def test_managed_use_case_evidence_whose_content_changed_needs_update_evidence(cur) -> None:
    slug = _slug()
    _import(cur, slug, SOURCE)
    (kept,) = _rows(cur, slug)
    edited = {**SOURCE, "confidence": "LOW"}

    cur.execute("SAVEPOINT before_refusal")
    with pytest.raises(ic.ReconcileRefused, match="immutable to the importer"):
        _import(cur, slug, edited)
    cur.execute("ROLLBACK TO SAVEPOINT before_refusal")
    assert _rows(cur, slug) == [kept]

    auth = {"version": 1, "entries": [{
        "action": "update_evidence", "table": "evidence_source", "robot": slug,
        "key": {"subject_type": "USE_CASE", "source_url": SOURCE["source_url"],
                "source_type": SOURCE["source_type"], "excerpt": SOURCE["excerpt"],
                "observed_at": SOURCE["observed_at"]}}]}
    recon = ic.Reconciliation(auth)
    _import(cur, slug, edited, recon=recon)
    recon.finish()
    (updated,) = _rows(cur, slug)
    assert updated[0] == kept[0] and updated[6] == "LOW"     # same id, edited in place


def test_use_case_and_manufacturer_evidence_do_not_share_rows(cur) -> None:
    """A MANUFACTURER row with the same URL does not make a use-case import see a collision."""
    slug = _slug()
    mid = cur.execute("INSERT INTO manufacturer (slug, name) VALUES (%s, %s) RETURNING id",
                      (slug, "Isolation Robotics")).fetchone()[0]
    ic.insert_evidence(cur, "MANUFACTURER", mid, {**SOURCE, "claim_fields": ["description"]})
    _import(cur, slug, SOURCE)
    assert len(_rows(cur, slug)) == 1
    assert cur.execute("SELECT count(*) FROM evidence_source WHERE subject_id=%s", (mid,)
                       ).fetchone()[0] == 1
