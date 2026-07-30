"""Batch trace + promotion review — gates.

The whole point of the batch path is that it is a faster way to make the SAME
decisions, not a weaker one. These tests are written against that claim: every
DATA-D1 gate the one-at-a-time CLI enforces must still refuse here.

Each test runs in a transaction that is rolled back, so nothing touches the
shared seeded database.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import DiscoveryCandidate, DiscoverySource, PromotionAudit
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import DiscoveryError
from app.services.discovery.adapters import FixtureAdapter, ingest
from app.services.discovery.batch_review import (
    WORKSHEET_VERSION,
    ApplyResult,
    apply_worksheet,
    candidate_snapshot,
    export_worksheet,
    read_worksheet,
    snapshot_hash,
    validate_worksheet,
    write_worksheet,
)

REVIEWER = "robert@humanoid.company"


@pytest.fixture
def dsession(database_url) -> Session:
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        conn.close()


def _uniq() -> str:
    return uuid.uuid4().hex[:8]


def _source(session: Session) -> DiscoverySource:
    src = DiscoverySource(
        key=f"batch-{_uniq()}", name="Batch fixture", source_class="COMPETITOR_DIRECTORY",
        tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime.now(UTC), eligibility_reviewed_by="ops@h.co",
        is_enabled=True,
    )
    session.add(src)
    session.flush()
    return src


def _candidate(session: Session, name: str, manufacturer: str, *, lead: str | None = None,
               claims: list[dict] | None = None,
               exact_manufacturer: bool = False) -> DiscoveryCandidate:
    """A fixture candidate.

    The manufacturer is made unique by default. Identity resolution matches on
    manufacturer AND model, so a fixture named after a real robot would collide
    with whatever candidates the database happens to hold — the 43 bootstrap
    entries, say — and the test would then pass or fail depending on data it
    never created. `exact_manufacturer=True` opts out where a test is
    deliberately arranging a collision.
    """
    if not exact_manufacturer:
        manufacturer = f"{manufacturer} Fixture {_uniq()}"
    record: dict = {
        "external_ref": f"ref-{_uniq()}", "name": name, "manufacturer": manufacturer,
    }
    if lead:
        record["data"] = {"official_url": lead}
    if claims:
        record["claims"] = claims
    return ingest(session, _source(session), FixtureAdapter([record]))[0]


def _sheet(rows: list[dict]) -> dict:
    return {"worksheet_version": WORKSHEET_VERSION, "rows": rows}


def _row(cand: DiscoveryCandidate, **over) -> dict:
    base = {
        "candidate_id": str(cand.id),
        "snapshot_hash": snapshot_hash(candidate_snapshot(cand)),
        "decision": "", "trace_url": "",
        "trace_source_type": "MANUFACTURER_SITE", "reject_reason": "",
        "_name": cand.candidate_name, "_manufacturer": cand.candidate_manufacturer,
    }
    base.update(over)
    return base


def _robots(session: Session) -> int:
    return session.execute(select(func.count()).select_from(Robot)).scalar_one()


# --- export ------------------------------------------------------------------

def test_export_is_read_only_and_carries_the_lead(dsession):
    cand = _candidate(dsession, "T1", "Booster Robotics", lead="https://oem.invalid/t1")
    before = _robots(dsession)

    sheet = export_worksheet(dsession)

    row = next(r for r in sheet["rows"] if r["candidate_id"] == str(cand.id))
    assert row["_official_url_lead"] == "https://oem.invalid/t1"
    assert row["trace_url"] == "https://oem.invalid/t1"  # prefilled to save typing
    assert row["decision"] == ""  # ...but NOT decided
    assert _robots(dsession) == before


def test_export_excludes_terminal_candidates(dsession):
    cand = _candidate(dsession, "Gone", "Maker")
    cand.status = "REJECTED"
    dsession.flush()
    ids = {r["candidate_id"] for r in export_worksheet(dsession)["rows"]}
    assert str(cand.id) not in ids


def test_worksheet_roundtrips_through_disk(dsession, tmp_path):
    _candidate(dsession, "Ameca", "Engineered Arts", lead="https://oem.invalid/a")
    path = write_worksheet(tmp_path / "w.json", export_worksheet(dsession))
    assert read_worksheet(path)["worksheet_version"] == WORKSHEET_VERSION


def test_a_stale_worksheet_version_is_refused(tmp_path):
    p = tmp_path / "old.json"
    p.write_text('{"worksheet_version": 0, "rows": []}', encoding="utf-8")
    with pytest.raises(DiscoveryError, match="worksheet version"):
        read_worksheet(p)


def test_a_version_one_worksheet_is_refused(tmp_path):
    """v1 rows carry decisions that were never bound to what was reviewed, so
    they are refused outright rather than upgraded."""
    p = tmp_path / "v1.json"
    p.write_text('{"worksheet_version": 1, "rows": []}', encoding="utf-8")
    with pytest.raises(DiscoveryError, match="worksheet version"):
        read_worksheet(p)


# --- the decision is bound to the candidate as reviewed ----------------------

CHANGED = "candidate changed since worksheet export"


def _apply_one(session, row) -> dict | None:
    result = apply_worksheet(session, _sheet([row]), reviewed_by=REVIEWER, dry_run=False)
    return result.blocked[0] if result.blocked else None


def test_export_binds_a_snapshot_hash_to_every_row(dsession):
    cand = _candidate(dsession, "H1", "Unitree", lead="https://oem.invalid/h1")
    row = next(
        r for r in export_worksheet(dsession)["rows"] if r["candidate_id"] == str(cand.id)
    )
    assert row["snapshot_hash"] == snapshot_hash(candidate_snapshot(cand))


def test_a_decision_without_a_snapshot_hash_is_refused(dsession):
    cand = _candidate(dsession, "X", "Maker")
    with pytest.raises(DiscoveryError, match="snapshot_hash is missing"):
        validate_worksheet(_sheet([
            _row(cand, decision="confirm", trace_url="https://o.invalid/x", snapshot_hash="")
        ]))


def test_retargeting_a_row_to_another_candidate_is_refused(dsession):
    """The attack this closes: edit candidate_id so a confirmation made about one
    robot lands on a different one."""
    reviewed = _candidate(dsession, "T1", "Booster Robotics")
    other = _candidate(dsession, "Atlas", "Boston Dynamics")
    row = _row(reviewed, decision="confirm", trace_url="https://oem.invalid/t1")
    row["candidate_id"] = str(other.id)  # hash still describes `reviewed`

    blocked = _apply_one(dsession, row)

    assert blocked and CHANGED in blocked["why"]
    dsession.refresh(other)
    assert other.trace_state == "NOT_TRACED"


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda c: setattr(c, "candidate_name", "Renamed"), id="name"),
        pytest.param(lambda c: setattr(c, "candidate_manufacturer", "Other Co"), id="manufacturer"),
        pytest.param(lambda c: setattr(c, "identity_status", "AMBIGUOUS"), id="identity_status"),
        pytest.param(lambda c: setattr(c, "status", "RECHECK_REQUIRED"), id="status"),
        pytest.param(lambda c: setattr(c, "trace_state", "TRACE_FAILED"), id="trace_state"),
        pytest.param(
            lambda c: setattr(c, "candidate_data", {"official_url": "https://moved.invalid/"}),
            id="official_url_lead",
        ),
    ],
)
def test_a_material_change_since_export_is_detected(dsession, mutate):
    cand = _candidate(dsession, "G1", "Unitree", lead="https://oem.invalid/g1")
    row = _row(cand, decision="confirm", trace_url="https://oem.invalid/g1")

    mutate(cand)          # the candidate moves on after the human reviewed it
    dsession.flush()

    blocked = _apply_one(dsession, row)

    assert blocked and CHANGED in blocked["why"]
    dsession.refresh(cand)
    assert cand.trace_verified_by is None  # the stale decision was NOT applied


def test_an_unchanged_candidate_applies_normally(dsession):
    cand = _candidate(dsession, "Ameca", "Engineered Arts", lead="https://oem.invalid/a")
    row = _row(cand, decision="confirm", trace_url="https://oem.invalid/a")

    result = apply_worksheet(dsession, _sheet([row]), reviewed_by=REVIEWER, dry_run=False)

    assert result.blocked == [] and result.confirmed == [str(cand.id)]


def test_a_terminal_candidate_stays_idempotent_despite_a_stale_hash(dsession):
    """Promoting necessarily changes the candidate, so its hash necessarily goes
    stale. Re-running must still report 'already done', not 'go review again'."""
    cand = _candidate(dsession, "Twice", "Maker")
    row = _row(cand, decision="confirm", trace_url="https://oem.invalid/t")
    apply_worksheet(
        dsession, _sheet([row]), reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False
    )

    again = apply_worksheet(
        dsession, _sheet([row]), reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False
    )

    assert again.blocked == []
    assert any("already PROMOTED" in s["why"] for s in again.skipped)


# --- the prefilled lead is not a confirmation (H2) ---------------------------

def test_an_unreviewed_row_does_nothing_even_with_a_prefilled_url(dsession):
    """The core H2 guarantee: a lead is not proof. A row whose trace_url is
    prefilled but whose decision is empty must not confirm anything."""
    cand = _candidate(dsession, "H1", "Unitree", lead="https://oem.invalid/h1")
    sheet = _sheet([_row(cand, trace_url="https://oem.invalid/h1")])  # decision left ""

    result = apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=False)

    assert result.confirmed == [] and len(result.skipped) == 1
    dsession.refresh(cand)
    assert cand.trace_state == "NOT_TRACED"
    assert cand.trace_verified_by is None


def test_confirm_without_a_trace_url_is_refused_before_any_write(dsession):
    cand = _candidate(dsession, "X", "Maker")
    sheet = _sheet([_row(cand, decision="confirm", trace_url="")])
    with pytest.raises(DiscoveryError, match="requires a trace_url"):
        validate_worksheet(sheet)


def test_reject_without_a_reason_is_refused(dsession):
    cand = _candidate(dsession, "X", "Maker")
    with pytest.raises(DiscoveryError, match="reject_reason"):
        validate_worksheet(_sheet([_row(cand, decision="reject")]))


def test_an_unknown_decision_word_is_refused(dsession):
    cand = _candidate(dsession, "X", "Maker")
    with pytest.raises(DiscoveryError, match="is not one of"):
        validate_worksheet(_sheet([_row(cand, decision="yes")]))


def test_a_duplicate_candidate_row_is_refused(dsession):
    cand = _candidate(dsession, "X", "Maker")
    with pytest.raises(DiscoveryError, match="duplicate"):
        validate_worksheet(_sheet([_row(cand), _row(cand)]))


# --- attribution (H2 / P8 / DATA-D1.9) ---------------------------------------

@pytest.mark.parametrize("who", ["", "   "])
def test_an_unattributed_batch_is_refused(dsession, who):
    cand = _candidate(dsession, "X", "Maker")
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/x")])
    with pytest.raises(DiscoveryError, match="attributed human"):
        apply_worksheet(dsession, sheet, reviewed_by=who, dry_run=False)


def test_the_reviewer_is_recorded_as_the_trace_verifier(dsession):
    cand = _candidate(dsession, "G1", "Unitree")
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/g1")])
    apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=False)
    dsession.refresh(cand)
    assert cand.trace_verified_by == REVIEWER
    assert cand.trace_state == "TRACE_CONFIRMED"


# --- dry run -----------------------------------------------------------------

def test_dry_run_reports_without_writing(dsession):
    cand = _candidate(dsession, "Digit", "Agility Robotics")
    cid = cand.id
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/d")])

    result = apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=True)

    assert result.confirmed == [str(cid)]
    # the transaction was rolled back, so the candidate is gone with the fixture
    assert dsession.get(DiscoveryCandidate, cid) is None


# --- promotion: the whole point ----------------------------------------------

def test_a_confirmed_candidate_promotes_with_every_spec_unknown(dsession):
    """The result Robert asked for: identity + trace confirmed, specs UNKNOWN,
    robot listed. Not a lowered bar — P1/P2/P4/P6/P8 all still passed."""
    before = _robots(dsession)
    cand = _candidate(dsession, "Kepler K2", "Kepler Robotics")
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/k2")])

    result = apply_worksheet(
        dsession, sheet, reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False
    )

    assert len(result.promoted) == 1
    robot = dsession.get(Robot, uuid.UUID(result.promoted[0]["robot_id"]))
    assert robot.name == "Kepler K2"
    assert robot.height_cm is None and robot.weight_kg is None and robot.payload_kg is None
    assert robot.is_published is False  # publishing is a separate workflow
    assert _robots(dsession) == before + 1


def test_promotion_records_the_p8_approver_in_the_audit(dsession):
    cand = _candidate(dsession, "Apollo 2", "Apptronik")
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/a2")])
    apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False)

    audit = dsession.execute(
        select(PromotionAudit).where(PromotionAudit.candidate_id == cand.id)
    ).scalar_one()
    assert audit.approved_by == REVIEWER and audit.action == "PROMOTED"


def test_confirming_does_not_promote_unless_asked(dsession):
    before = _robots(dsession)
    cand = _candidate(dsession, "Walker S2", "UBTECH")
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/w")])

    apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, promote_confirmed=False, dry_run=False)

    assert _robots(dsession) == before
    dsession.refresh(cand)
    assert cand.status == "READY_FOR_PROMOTION"


def test_a_trace_never_verifies_a_specification_claim(dsession):
    """Confirming a trace establishes the ENTITY exists. It must not silently
    turn an unverified height into a canonical one."""
    cand = _candidate(
        dsession, "S1", "Astribot",
        claims=[{"field_key": "height_cm", "claimed_value": "170",
                 "unit": "cm", "evidence_url": "https://aggregator.invalid/s1"}],
    )
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/s1")])

    apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False)

    dsession.refresh(cand)
    assert all(c.claim_status != "VERIFIED" for c in cand.claims)
    robot = dsession.get(Robot, cand.promoted_robot_id)
    assert robot.height_cm is None  # the aggregator's 170 cm did NOT become canonical


# --- gates still refuse ------------------------------------------------------

def test_an_ambiguous_identity_still_blocks_promotion(dsession):
    """P1 is not weakened by batching. Two canonical robots of one manufacturer
    plus an underspecified candidate name = AMBIGUOUS, and ambiguity blocks."""
    mfr = Manufacturer(slug=f"m-{_uniq()}", name="Ambig Robotics")
    dsession.add(mfr)
    dsession.flush()
    for n in ("Ambig Robotics A", "Ambig Robotics B"):
        dsession.add(Robot(slug=f"r-{_uniq()}", manufacturer_id=mfr.id, name=n))
    dsession.flush()

    cand = _candidate(dsession, "Ambig Robotics", "Ambig Robotics", exact_manufacturer=True)
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/z")])

    result = apply_worksheet(
        dsession, sheet, reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False
    )

    assert result.promoted == []
    assert result.blocked and "P1" in result.blocked[0]["why"]


def test_a_conflicting_claim_still_blocks_promotion(dsession):
    """P4 is not weakened by batching."""
    cand = _candidate(
        dsession, "Conflicted", "Maker",
        claims=[
            {"field_key": "payload_kg", "claimed_value": "30", "unit": "kg",
             "evidence_url": "https://a.invalid/1"},
            {"field_key": "payload_kg", "claimed_value": "35", "unit": "kg",
             "evidence_url": "https://b.invalid/1"},
        ],
    )
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/c")])

    result = apply_worksheet(
        dsession, sheet, reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False
    )

    assert result.promoted == []
    dsession.refresh(cand)
    assert cand.status == "CONFLICT"
    # both values survive, neither averaged (DATA-D1.8)
    assert {c.claimed_value for c in cand.claims} == {"30", "35"}


# --- rejection + idempotency -------------------------------------------------

def test_reject_records_an_attributed_reason(dsession):
    cand = _candidate(dsession, "Not a humanoid", "Maker")
    sheet = _sheet([_row(cand, decision="reject", reject_reason="wheeled cart, not a humanoid")])

    result = apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=False)

    assert result.rejected == [str(cand.id)]
    dsession.refresh(cand)
    assert cand.status == "REJECTED"


def test_reapplying_a_worksheet_is_safe(dsession):
    cand = _candidate(dsession, "Twice", "Maker")
    sheet = _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/t")])
    apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False)
    before = _robots(dsession)

    again = apply_worksheet(
        dsession, sheet, reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False
    )

    assert again.promoted == []
    assert any("already PROMOTED" in s["why"] for s in again.skipped)
    assert _robots(dsession) == before  # no duplicate robot


def test_a_missing_candidate_is_reported_not_raised(dsession):
    sheet = _sheet([{
        "candidate_id": str(uuid.uuid4()), "snapshot_hash": "deadbeef", "decision": "confirm",
        "trace_url": "https://oem.invalid/x", "trace_source_type": "MANUFACTURER_SITE",
        "reject_reason": "",
    }])
    result = apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=False)
    assert result.blocked and "not found" in result.blocked[0]["why"]


def test_one_blocked_row_does_not_abort_the_batch(dsession):
    good = _candidate(dsession, "Good", "Maker")
    sheet = _sheet([
        {"candidate_id": str(uuid.uuid4()), "snapshot_hash": "deadbeef", "decision": "confirm",
         "trace_url": "https://oem.invalid/missing", "trace_source_type": "MANUFACTURER_SITE",
         "reject_reason": ""},
        _row(good, decision="confirm", trace_url="https://oem.invalid/good"),
    ])

    result = apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=False)

    assert len(result.blocked) == 1
    assert result.confirmed == [str(good.id)]


# --- transaction semantics ---------------------------------------------------

def test_an_expected_database_refusal_does_not_poison_the_session(dsession, monkeypatch):
    """A row-level DB refusal rolls back its savepoint only. The session must
    stay usable, and a later valid row must still succeed."""
    from sqlalchemy.exc import IntegrityError

    import app.services.discovery.batch_review as br

    bad = _candidate(dsession, "Bad", "Maker")
    good = _candidate(dsession, "Good", "Maker")
    real_record_trace = br.record_trace

    def flaky(session, candidate, **kw):
        if candidate.id == bad.id:
            raise IntegrityError("INSERT ...", {}, Exception("simulated constraint violation"))
        return real_record_trace(session, candidate, **kw)

    monkeypatch.setattr(br, "record_trace", flaky)

    result = apply_worksheet(
        dsession,
        _sheet([
            _row(bad, decision="confirm", trace_url="https://oem.invalid/b"),
            _row(good, decision="confirm", trace_url="https://oem.invalid/g"),
        ]),
        reviewed_by=REVIEWER,
        dry_run=False,
    )

    assert len(result.blocked) == 1 and result.blocked[0]["candidate_id"] == str(bad.id)
    assert result.confirmed == [str(good.id)]  # the session survived
    dsession.refresh(good)
    assert good.trace_state == "TRACE_CONFIRMED"
    dsession.refresh(bad)
    assert bad.trace_state == "NOT_TRACED"


def test_an_unexpected_exception_aborts_the_whole_batch(dsession, monkeypatch):
    """A bug or an infrastructure failure must NOT be downgraded into a blocked
    row: that would report a clean run that never happened."""
    import app.services.discovery.batch_review as br

    cand = _candidate(dsession, "Boom", "Maker")

    def explode(*a, **kw):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(br, "record_trace", explode)

    with pytest.raises(RuntimeError, match="connection reset"):
        apply_worksheet(
            dsession,
            _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/x")]),
            reviewed_by=REVIEWER,
            dry_run=False,
        )


def test_a_valid_trace_survives_a_blocked_promotion(dsession):
    """Tracing and promoting are two decisions. A trace confirmed by a human is
    real work and must not be discarded because a gate refused the promotion."""
    cand = _candidate(
        dsession, "Conflicted2", "Maker",
        claims=[
            {"field_key": "payload_kg", "claimed_value": "30", "unit": "kg",
             "evidence_url": "https://a.invalid/1"},
            {"field_key": "payload_kg", "claimed_value": "35", "unit": "kg",
             "evidence_url": "https://b.invalid/1"},
        ],
    )

    result = apply_worksheet(
        dsession,
        _sheet([_row(cand, decision="confirm", trace_url="https://oem.invalid/c")]),
        reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False,
    )

    assert result.confirmed == [str(cand.id)]  # the trace stood
    assert result.promoted == [] and len(result.blocked) == 1
    dsession.refresh(cand)
    assert cand.trace_state == "TRACE_CONFIRMED"
    assert cand.trace_verified_by == REVIEWER


def test_dry_run_leaves_every_row_unchanged(dsession):
    a = _candidate(dsession, "A", "Maker")
    b = _candidate(dsession, "B", "Maker")
    before = _robots(dsession)

    apply_worksheet(
        dsession,
        _sheet([
            _row(a, decision="confirm", trace_url="https://oem.invalid/a"),
            _row(b, decision="reject", reject_reason="not a humanoid"),
        ]),
        reviewed_by=REVIEWER, promote_confirmed=True, dry_run=True,
    )

    # the outer transaction was rolled back entirely
    assert dsession.get(DiscoveryCandidate, a.id) is None
    assert dsession.get(DiscoveryCandidate, b.id) is None
    assert _robots(dsession) == before


def test_a_write_run_keeps_successful_rows_and_leaves_blocked_rows_alone(dsession):
    good = _candidate(dsession, "Keeper", "Maker")
    missing_id = str(uuid.uuid4())

    result = apply_worksheet(
        dsession,
        _sheet([
            {"candidate_id": missing_id, "snapshot_hash": "deadbeef", "decision": "confirm",
             "trace_url": "https://oem.invalid/x", "trace_source_type": "MANUFACTURER_SITE",
             "reject_reason": ""},
            _row(good, decision="confirm", trace_url="https://oem.invalid/k"),
        ]),
        reviewed_by=REVIEWER, promote_confirmed=True, dry_run=False,
    )

    assert len(result.blocked) == 1 and len(result.promoted) == 1
    dsession.refresh(good)
    assert good.status == "PROMOTED"


def test_apply_result_counts_only_real_actions(dsession):
    cand = _candidate(dsession, "Skipped", "Maker")
    sheet = _sheet([_row(cand, decision="skip")])
    result = apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=False)
    assert isinstance(result, ApplyResult) and result.acted == 0
