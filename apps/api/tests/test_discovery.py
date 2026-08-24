"""DATA-D1 v0.1 acceptance gates (docs/11_DATA_D1_CONTRACT.md §27, A-K) + the
governance hardenings H1-H5.

Every test runs inside a transaction that is rolled back, so nothing touches the
shared seeded database. The service functions never commit (the caller owns the
transaction), which is exactly what lets the pipeline + promotion be exercised and
then discarded here.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import DiscoveryCandidate, DiscoverySource, PromotionAudit
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.models.robot_image import RobotImage
from app.services.discovery import DiscoveryError, PromotionError
from app.services.discovery.adapters import FixtureAdapter, ingest
from app.services.discovery.pipeline import advance, flag_recheck, record_trace
from app.services.discovery.promotion import build_proposal, promote, reject

DISCOVERY_TABLES = {
    "discovery_source", "discovery_candidate", "candidate_claim",
    "candidate_image_ref", "promotion_audit",
    # DATA-D1.LIVE Slice A (migration 0004) grew the NONCANONICAL layer. These are
    # discovery-layer tables by the ratified contract (docs/16 §16), so listing
    # them here does not weaken Gate K — the invariant it asserts is unchanged:
    # nothing OUTSIDE this set may hold a foreign key INTO it. Omitting them would
    # have made the gate fail for the right reason (the set grew) while leaving
    # the new tables unprotected by it.
    "source_eligibility_review", "crawl_run", "fetched_page", "extraction_result",
    "candidate_commercial_signal", "discovery_evidence_excerpt",
    # DATA-D1 Scheduled Freshness (migration 0010, docs/22, RATIFIED v0.1)
    # added this pair. Same precedent as the DATA-D1.LIVE tables above:
    # freshness_target's FK to discovery_source is intentional and ratified
    # (docs/22 Phase 2), so it belongs in this set for the same reason —
    # listing it here does not weaken Gate K, the invariant is unchanged.
    "freshness_target", "freshness_observation",
}


@pytest.fixture
def dsession(database_url) -> Session:
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:  # an expected IntegrityError may already have unwound it
            trans.rollback()
        conn.close()


def _uniq() -> str:
    return uuid.uuid4().hex[:8]


def _source(session: Session, *, eligible: bool = True) -> DiscoverySource:
    """An eligible source has an affirmative ToS/robots decision + attributed review
    (DATA-D1.9); an ineligible one keeps the UNKNOWN defaults."""
    kwargs = dict(key=f"fixture-{_uniq()}", name="Fixture source",
                  source_class="COMPETITOR_DIRECTORY")
    if eligible:
        kwargs.update(
            tos_status="ALLOWED", robots_status="ALLOWED",
            eligibility_reviewed_at=datetime.now(UTC), eligibility_reviewed_by="ops@h.co",
            is_enabled=True,
        )
    src = DiscoverySource(**kwargs)
    session.add(src)
    session.flush()
    return src


def _canon_robot(session: Session, mfr_name: str, robot_name: str) -> Robot:
    mfr = session.execute(
        select(Manufacturer).where(Manufacturer.name == mfr_name)
    ).scalar_one_or_none()
    if mfr is None:
        mfr = Manufacturer(slug=f"mfr-{_uniq()}", name=mfr_name)
        session.add(mfr)
        session.flush()
    robot = Robot(slug=f"rob-{_uniq()}", manufacturer_id=mfr.id, name=robot_name, is_published=True)
    session.add(robot)
    session.flush()
    return robot


def _ingest_one(session: Session, record: dict, source: DiscoverySource | None = None):
    source = source or _source(session)
    return ingest(session, source, FixtureAdapter([record]))[0]


def _confirm_trace(session: Session, cand, confirmed_fields=frozenset(),
                   source_type: str = "MANUFACTURER_SITE") -> None:
    record_trace(
        session, cand, trace_url="https://oem.invalid/x",
        trace_source_type=source_type, verified_by="ops@h.co",
        confirmed_fields=frozenset(confirmed_fields),
    )


def _count(session: Session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def _robot_count(session: Session) -> int:
    return _count(session, Robot)


# --- A: competitor discovery does not become canonical -----------------------

def test_A_discovery_alone_is_not_canonical(dsession):
    before = _robot_count(dsession)
    cand = _ingest_one(dsession, {
        "external_ref": "a-1", "name": "Nova NX", "manufacturer": "Nova",
        "claims": [{"field_key": "payload_kg", "claimed_value": "20"}],  # no trace
    })
    advance(dsession, cand)
    # No confirmed authoritative trace -> stuck at SOURCE_TRACE, not promotable.
    assert cand.status == "SOURCE_TRACE"
    assert cand.trace_state == "NOT_TRACED"
    with pytest.raises(PromotionError):
        promote(dsession, cand, approved_by="ops")
    assert _robot_count(dsession) == before


# --- B: an independently verified fact can promote (into a canonical field) ----

def test_B_verified_fact_promotes_to_canonical_field(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "b-1", "name": "Zeta ZX-1", "manufacturer": f"Zeta {_uniq()}",
        "data": {"official_url": "https://zeta.invalid/zx-1"},
        "claims": [{"field_key": "height_cm", "claimed_value": "170", "unit": "cm"}],
    })
    advance(dsession, cand)                       # -> SOURCE_TRACE (lead is not proof)
    assert cand.status == "SOURCE_TRACE"
    _confirm_trace(dsession, cand, confirmed_fields={"height_cm"})
    advance(dsession, cand)                       # -> READY_FOR_PROMOTION
    assert cand.identity_status == "NEW_ENTITY"
    assert cand.status == "READY_FOR_PROMOTION"

    robot = promote(dsession, cand, approved_by="ops@humanoid.company")
    fresh = dsession.get(Robot, robot.id)
    assert fresh.is_published is False
    # The VERIFIED fact is actually written to canonical.
    assert float(fresh.height_cm) == 170.0
    ev = dsession.execute(
        select(EvidenceSource).where(
            EvidenceSource.subject_type == "ROBOT", EvidenceSource.subject_id == robot.id
        )
    ).scalar_one()
    assert ev.source_url == "https://oem.invalid/x"
    assert ev.source_type == "MANUFACTURER_SITE"  # from the confirmed trace, not hardcoded
    assert ev.confidence == "VERIFIED"


# --- C: ambiguous identity blocks promotion ----------------------------------

def test_C_ambiguous_identity_blocks(dsession):
    mfr = f"Figure {_uniq()}"
    _canon_robot(dsession, mfr, "Figure 02")
    _canon_robot(dsession, mfr, "Figure 03")
    cand = _ingest_one(dsession, {
        "external_ref": "c-1", "name": "Figure", "manufacturer": mfr,
    })
    advance(dsession, cand)
    assert cand.identity_status == "AMBIGUOUS"
    with pytest.raises(PromotionError):
        promote(dsession, cand, approved_by="ops")


# --- D: duplicate detection -> no duplicate; still records evidence lineage ---

def test_D_dedup_links_no_duplicate_but_keeps_lineage(dsession):
    mfr = f"Zeta {_uniq()}"
    existing = _canon_robot(dsession, mfr, "ZX-1")
    before = _robot_count(dsession)
    cand = _ingest_one(dsession, {
        "external_ref": "d-1", "name": f"{mfr} ZX-1", "manufacturer": mfr,
    })
    advance(dsession, cand)
    assert cand.identity_status == "MATCHED_EXISTING"
    _confirm_trace(dsession, cand)
    advance(dsession, cand)

    promote(dsession, cand, approved_by="ops")
    assert cand.promoted_robot_id == existing.id
    assert _robot_count(dsession) == before                      # no duplicate robot
    # Gate J: existing-robot promotion still writes G2 evidence lineage.
    audit = dsession.execute(
        select(PromotionAudit).where(PromotionAudit.candidate_id == cand.id)
    ).scalar_one()
    assert audit.evidence_source_id is not None
    assert dsession.get(EvidenceSource, audit.evidence_source_id).subject_id == existing.id


# --- E: conflicting authoritative evidence -> CONFLICT, no silent overwrite ---

def test_E_conflict_preserved_not_averaged(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "e-1", "name": "Orbit O1", "manufacturer": f"Orbit {_uniq()}",
        "claims": [
            {"field_key": "payload_kg", "claimed_value": "20"},
            {"field_key": "payload_kg", "claimed_value": "30"},
        ],
    })
    advance(dsession, cand)
    _confirm_trace(dsession, cand, confirmed_fields={"payload_kg"})
    advance(dsession, cand)
    assert cand.status == "CONFLICT"
    assert all(c.claim_status == "CONFLICT" for c in cand.claims)
    with pytest.raises(PromotionError):
        promote(dsession, cand, approved_by="ops")


# --- F: unknown stays unknown; unverified never leaks to canonical -----------

def test_F_unknown_and_unverified_never_promote(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "f-1", "name": "Vega V1", "manufacturer": f"Vega {_uniq()}",
        "claims": [
            {"field_key": "payload_kg", "claimed_value": "25"},   # NOT confirmed
            {"field_key": "height_cm", "claimed_value": None},    # UNKNOWN
        ],
    })
    advance(dsession, cand)
    _confirm_trace(dsession, cand, confirmed_fields=frozenset())   # confirm existence only
    advance(dsession, cand)
    statuses = {c.field_key: c.claim_status for c in cand.claims}
    assert statuses["payload_kg"] == "NOT_VERIFIED"
    assert statuses["height_cm"] == "UNKNOWN"

    robot = promote(dsession, cand, approved_by="ops")
    fresh = dsession.get(Robot, robot.id)
    assert fresh.payload_kg is None      # unverified -> never written (not 25, not 0)
    assert fresh.height_cm is None       # unknown -> never written


# --- G: image candidate obeys MEDIA-01 (+ no binary cache, R3) ---------------

def test_G_image_candidate_not_auto_promoted(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "g-1", "name": "Iris I1", "manufacturer": f"Iris {_uniq()}",
        "images": [{"image_url": "https://competitor.invalid/iris.jpg", "credited_to": "Iris"}],
    })
    advance(dsession, cand)
    _confirm_trace(dsession, cand)
    advance(dsession, cand)
    robot = promote(dsession, cand, approved_by="ops")
    img_count = dsession.execute(
        select(func.count()).select_from(RobotImage).where(RobotImage.robot_id == robot.id)
    ).scalar_one()
    assert img_count == 0
    types = dsession.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema='humanoid' AND table_name='candidate_image_ref'"
    )).scalars().all()
    assert "bytea" not in {t.lower() for t in types}


# --- H: the pipeline (crawler) cannot write canonical ------------------------

def test_H_pipeline_never_writes_canonical(dsession):
    r_before = _robot_count(dsession)
    m_before = _count(dsession, Manufacturer)
    e_before = _count(dsession, EvidenceSource)
    cand = _ingest_one(dsession, {
        "external_ref": "h-1", "name": "Helio H1", "manufacturer": f"Helio {_uniq()}",
    })
    advance(dsession, cand)
    _confirm_trace(dsession, cand)
    advance(dsession, cand)              # full pipeline to READY, NO promote
    assert cand.status == "READY_FOR_PROMOTION"
    assert _robot_count(dsession) == r_before
    assert _count(dsession, Manufacturer) == m_before
    assert _count(dsession, EvidenceSource) == e_before


# --- I: the public API excludes discovery candidates -------------------------

def test_I_public_api_excludes_candidates():
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    leaks = [p for p in paths if "discovery" in p.lower() or "candidate" in p.lower()]
    assert leaks == [], f"public routes must not expose the discovery layer: {leaks}"


# --- J: provenance survives promotion ----------------------------------------

def test_J_provenance_lineage_reconstructable(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "j-1", "name": "Lyra L1", "manufacturer": f"Lyra {_uniq()}",
    })
    advance(dsession, cand)
    _confirm_trace(dsession, cand)
    advance(dsession, cand)
    robot = promote(dsession, cand, approved_by="ops@humanoid.company")

    audit = dsession.execute(
        select(PromotionAudit).where(PromotionAudit.candidate_id == cand.id)
    ).scalar_one()
    assert audit.action == "PROMOTED" and audit.promoted_robot_id == robot.id
    ev = dsession.get(EvidenceSource, audit.evidence_source_id)
    assert ev is not None and ev.subject_id == robot.id
    assert ev.source_url == cand.trace_url


# --- K: structural isolation (no canonical -> discovery FK) -------------------

def test_K_structural_isolation(dsession):
    existing = dsession.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='humanoid' AND table_name = ANY(:names)"
    ), {"names": list(DISCOVERY_TABLES)}).scalars().all()
    assert set(existing) == DISCOVERY_TABLES

    fks = dsession.execute(text(
        "SELECT conrelid::regclass::text AS child, confrelid::regclass::text AS parent "
        "FROM pg_constraint WHERE contype='f'"
    )).all()

    def _leaf(name: str) -> str:
        return name.split(".")[-1].strip('"')

    for child, parent in fks:
        if _leaf(parent) in DISCOVERY_TABLES:
            assert _leaf(child) in DISCOVERY_TABLES, (
                f"canonical table {child!r} has an FK to discovery table {parent!r}"
            )


# --- H1: DATA-D1.9 enforces AFFIRMATIVE eligibility, not just "reviewed" -------

def test_H1_enable_requires_affirmative_permission(dsession):
    # Reviewed, attributed, but ToS PROHIBITS automation -> may not be enabled.
    dsession.add(DiscoverySource(
        key=f"proh-{_uniq()}", name="prohibited", source_class="OTHER",
        tos_status="PROHIBITED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime.now(UTC), eligibility_reviewed_by="ops",
        is_enabled=True,
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_H1_enable_requires_review_attribution(dsession):
    # Affirmative ToS/robots but NO recorded reviewer/time -> may not be enabled.
    dsession.add(DiscoverySource(
        key=f"unattr-{_uniq()}", name="unattributed", source_class="OTHER",
        tos_status="ALLOWED", robots_status="ALLOWED", is_enabled=True,
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_H1_prohibited_source_is_not_radar_eligible(dsession):
    src = DiscoverySource(
        key=f"proh2-{_uniq()}", name="p", source_class="OTHER",
        tos_status="PROHIBITED", robots_status="ALLOWED",
        eligibility_reviewed_at=datetime.now(UTC), eligibility_reviewed_by="ops",
        is_enabled=False,
    )
    dsession.add(src)
    dsession.flush()
    assert src.radar_eligible is False
    rec = {"external_ref": "z", "name": "Z", "manufacturer": "Q"}
    with pytest.raises(DiscoveryError):
        ingest(dsession, src, FixtureAdapter([rec]))


# --- H2: an official_url lead is NOT a confirmed trace ------------------------

def test_H2_lead_is_not_proof(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "h2-1", "name": "Sol S1", "manufacturer": f"Sol {_uniq()}",
        "data": {"official_url": "https://sol.invalid/s1"},   # a lead only
    })
    advance(dsession, cand)
    # The lead did NOT confirm a trace.
    assert cand.trace_state == "NOT_TRACED"
    assert cand.status == "SOURCE_TRACE"
    with pytest.raises(PromotionError):
        promote(dsession, cand, approved_by="ops")
    # Only an explicit trace unblocks it.
    _confirm_trace(dsession, cand)
    advance(dsession, cand)
    assert cand.status == "READY_FOR_PROMOTION"


# --- H3: minimal retention + reference-only imagery are ENFORCED --------------

def test_H3_shadow_data_rejected(dsession):
    src = _source(dsession)
    bad = {"external_ref": "h3-1", "name": "X", "manufacturer": "Y",
           "data": {"competitor_description": "a long copied prose blob ..."}}
    with pytest.raises(DiscoveryError):
        ingest(dsession, src, FixtureAdapter([bad]))


def test_H3_non_http_image_rejected(dsession):
    src = _source(dsession)
    bad = {"external_ref": "h3-2", "name": "X", "manufacturer": "Y",
           "images": [{"image_url": "data:image/png;base64,AAAA"}]}
    with pytest.raises(DiscoveryError):
        ingest(dsession, src, FixtureAdapter([bad]))


# --- H5: terminal-safe state machine + durable audit + required fields -------

def test_H5_promotion_is_idempotent(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "h5-1", "name": "Ida I2", "manufacturer": f"Ida {_uniq()}",
    })
    advance(dsession, cand)
    _confirm_trace(dsession, cand)
    advance(dsession, cand)
    promote(dsession, cand, approved_by="ops")
    with pytest.raises(PromotionError):        # second promote refused
        promote(dsession, cand, approved_by="ops")
    with pytest.raises(DiscoveryError):        # terminal candidate not re-advanced
        advance(dsession, cand)


def test_H5_audit_survives_candidate_deletion(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "h5-2", "name": "Juno J1", "manufacturer": f"Juno {_uniq()}",
    })
    advance(dsession, cand)
    _confirm_trace(dsession, cand)
    advance(dsession, cand)
    promote(dsession, cand, approved_by="ops")
    dsession.delete(cand)                       # blocked by ON DELETE RESTRICT audit FK
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_H5_external_ref_is_required(dsession):
    src = _source(dsession)
    dsession.add(DiscoveryCandidate(source_id=src.id, candidate_name="No Ref", external_ref=None))
    with pytest.raises(IntegrityError):
        dsession.flush()


# --- supporting invariants ---------------------------------------------------

def test_recheck_is_autonomous_and_non_canonical(dsession):
    before = _robot_count(dsession)
    cand = _ingest_one(dsession, {
        "external_ref": "rc-1", "name": "Echo E1", "manufacturer": f"Echo {_uniq()}",
    })
    flag_recheck(dsession, cand, "official page changed")
    assert cand.status == "RECHECK_REQUIRED"
    assert _robot_count(dsession) == before


def test_reject_requires_reason(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "rj-1", "name": "Kilo K1", "manufacturer": f"Kilo {_uniq()}",
    })
    with pytest.raises(PromotionError):
        reject(dsession, cand, approved_by="ops", reason="")
    reject(dsession, cand, approved_by="ops", reason="no independent source")
    assert cand.status == "REJECTED"


def test_ineligible_source_cannot_be_crawled(dsession):
    src = _source(dsession, eligible=False)
    record = {"external_ref": "x", "name": "X", "manufacturer": "Y"}
    with pytest.raises(DiscoveryError):
        ingest(dsession, src, FixtureAdapter([record]))


def test_build_proposal_is_read_only(dsession):
    before = _robot_count(dsession)
    cand = _ingest_one(dsession, {
        "external_ref": "p-1", "name": "Pax P1", "manufacturer": f"Pax {_uniq()}",
    })
    advance(dsession, cand)
    _confirm_trace(dsession, cand)
    advance(dsession, cand)
    proposal = build_proposal(dsession, cand)
    assert proposal["name"] == "Pax P1"
    assert proposal["gates_failed"] == []
    assert _robot_count(dsession) == before
