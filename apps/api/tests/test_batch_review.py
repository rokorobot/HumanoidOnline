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
    export_worksheet,
    read_worksheet,
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
               claims: list[dict] | None = None) -> DiscoveryCandidate:
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
        "candidate_id": str(cand.id), "decision": "", "trace_url": "",
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

    cand = _candidate(dsession, "Ambig Robotics", "Ambig Robotics")
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
        "candidate_id": str(uuid.uuid4()), "decision": "confirm",
        "trace_url": "https://oem.invalid/x", "trace_source_type": "MANUFACTURER_SITE",
        "reject_reason": "",
    }])
    result = apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=False)
    assert result.blocked and "not found" in result.blocked[0]["why"]


def test_one_blocked_row_does_not_abort_the_batch(dsession):
    good = _candidate(dsession, "Good", "Maker")
    sheet = _sheet([
        {"candidate_id": str(uuid.uuid4()), "decision": "confirm",
         "trace_url": "https://oem.invalid/missing", "trace_source_type": "MANUFACTURER_SITE",
         "reject_reason": ""},
        _row(good, decision="confirm", trace_url="https://oem.invalid/good"),
    ])

    result = apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=False)

    assert len(result.blocked) == 1
    assert result.confirmed == [str(good.id)]


def test_apply_result_counts_only_real_actions(dsession):
    cand = _candidate(dsession, "Skipped", "Maker")
    sheet = _sheet([_row(cand, decision="skip")])
    result = apply_worksheet(dsession, sheet, reviewed_by=REVIEWER, dry_run=False)
    assert isinstance(result, ApplyResult) and result.acted == 0
