"""DATA-D1 v0.1 acceptance gates (docs/11_DATA_D1_CONTRACT.md §27, A-K).

Every test runs inside a transaction that is rolled back, so nothing touches the
shared seeded database. The service functions never commit (the caller owns the
transaction), which is exactly what lets the pipeline + promotion be exercised and
then discarded here.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import DiscoverySource, PromotionAudit
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.models.robot_image import RobotImage
from app.services.discovery import DiscoveryError, PromotionError
from app.services.discovery.adapters import FixtureAdapter, ingest
from app.services.discovery.pipeline import advance, flag_recheck
from app.services.discovery.promotion import build_proposal, promote

DISCOVERY_TABLES = {
    "discovery_source", "discovery_candidate", "candidate_claim",
    "candidate_image_ref", "promotion_audit",
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
    src = DiscoverySource(
        key=f"fixture-{_uniq()}",
        name="Fixture source",
        source_class="COMPETITOR_DIRECTORY",
        tos_reviewed=eligible,
        robots_allowed=eligible,
        is_enabled=eligible,
    )
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
    created = ingest(session, source, FixtureAdapter([record]))
    return created[0]


def _count(session: Session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def _robot_count(session: Session) -> int:
    return _count(session, Robot)


# --- A: competitor discovery does not become canonical -----------------------

def test_A_discovery_alone_is_not_canonical(dsession):
    before = _robot_count(dsession)
    cand = _ingest_one(dsession, {
        "external_ref": "a-1", "name": "Nova NX", "manufacturer": "Nova Robotics",
        "claims": [{"field_key": "payload_kg", "claimed_value": "20"}],  # no evidence
    })
    advance(dsession, cand)
    # No authoritative source -> not promotable, canonical untouched.
    assert cand.trace_state == "TRACE_FAILED"
    assert cand.status == "INSUFFICIENT_EVIDENCE"
    with pytest.raises(PromotionError):
        promote(dsession, cand, approved_by="ops")
    assert _robot_count(dsession) == before


# --- B: an independently verified fact can promote ---------------------------

def test_B_verified_candidate_promotes(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "b-1", "name": "Zeta ZX-1", "manufacturer": f"Zeta {_uniq()}",
        "data": {"official_url": "https://zeta.invalid/zx-1"},
        "claims": [{"field_key": "height_cm", "claimed_value": "170",
                    "evidence_url": "https://zeta.invalid/zx-1/specs"}],
    })
    advance(dsession, cand)
    assert cand.identity_status == "NEW_ENTITY"
    assert cand.status == "READY_FOR_PROMOTION"

    robot = promote(dsession, cand, approved_by="ops@humanoid.company")
    assert cand.status == "PROMOTED"
    assert cand.promoted_robot_id == robot.id
    # Canonical robot exists but UNPUBLISHED (a human publishes separately).
    assert session_get_robot(dsession, robot.id).is_published is False
    # Evidence written through the existing G2 model (R5).
    ev = dsession.execute(
        select(EvidenceSource).where(
            EvidenceSource.subject_type == "ROBOT", EvidenceSource.subject_id == robot.id
        )
    ).scalar_one()
    assert ev.source_url == "https://zeta.invalid/zx-1"
    assert ev.confidence == "VERIFIED"


def session_get_robot(session: Session, rid) -> Robot:
    return session.get(Robot, rid)


# --- C: ambiguous identity blocks promotion ----------------------------------

def test_C_ambiguous_identity_blocks(dsession):
    mfr = f"Figure {_uniq()}"
    _canon_robot(dsession, mfr, "Figure 02")
    _canon_robot(dsession, mfr, "Figure 03")
    cand = _ingest_one(dsession, {
        "external_ref": "c-1", "name": "Figure", "manufacturer": mfr,
        "data": {"official_url": "https://figure.invalid/"},
    })
    advance(dsession, cand)
    assert cand.identity_status == "AMBIGUOUS"
    with pytest.raises(PromotionError):
        promote(dsession, cand, approved_by="ops")


# --- D: duplicate detection -> no duplicate canonical robot ------------------

def test_D_dedup_links_no_duplicate(dsession):
    mfr = f"Zeta {_uniq()}"
    existing = _canon_robot(dsession, mfr, "ZX-1")
    before = _robot_count(dsession)
    cand = _ingest_one(dsession, {
        "external_ref": "d-1", "name": f"{mfr} ZX-1", "manufacturer": mfr,
        "data": {"official_url": "https://zeta.invalid/zx-1"},
    })
    advance(dsession, cand)
    assert cand.identity_status == "MATCHED_EXISTING"
    assert cand.possible_robot_id == existing.id

    promote(dsession, cand, approved_by="ops")
    # Linked to the existing robot; NO new canonical robot created.
    assert cand.promoted_robot_id == existing.id
    assert _robot_count(dsession) == before


# --- E: conflicting authoritative evidence -> CONFLICT, no silent overwrite ---

def test_E_conflict_preserved_not_averaged(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "e-1", "name": "Orbit O1", "manufacturer": f"Orbit {_uniq()}",
        "data": {"official_url": "https://orbit.invalid/o1"},
        "claims": [
            {"field_key": "payload_kg", "claimed_value": "20"},
            {"field_key": "payload_kg", "claimed_value": "30"},
        ],
    })
    advance(dsession, cand)
    assert cand.status == "CONFLICT"
    assert all(c.claim_status == "CONFLICT" for c in cand.claims)
    with pytest.raises(PromotionError):
        promote(dsession, cand, approved_by="ops")


# --- F: unknown stays unknown ------------------------------------------------

def test_F_unknown_stays_unknown(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "f-1", "name": "Vega V1", "manufacturer": f"Vega {_uniq()}",
        "data": {"official_url": "https://vega.invalid/v1"},
        "claims": [
            {"field_key": "payload_kg", "claimed_value": "25"},   # no evidence -> NOT_VERIFIED
            {"field_key": "height_cm", "claimed_value": None},    # -> UNKNOWN
        ],
    })
    advance(dsession, cand)
    statuses = {c.field_key: c.claim_status for c in cand.claims}
    assert statuses["payload_kg"] == "NOT_VERIFIED"
    assert statuses["height_cm"] == "UNKNOWN"

    robot = promote(dsession, cand, approved_by="ops")
    fresh = dsession.get(Robot, robot.id)
    # Unverified/unknown claims never leak into canonical as fabricated values.
    assert fresh.payload_kg is None
    assert fresh.height_cm is None


# --- G: image candidate obeys MEDIA-01 (+ no binary cache, R3) ---------------

def test_G_image_candidate_not_auto_promoted(dsession):
    cand = _ingest_one(dsession, {
        "external_ref": "g-1", "name": "Iris I1", "manufacturer": f"Iris {_uniq()}",
        "data": {"official_url": "https://iris.invalid/i1"},
        "images": [{"image_url": "https://competitor.invalid/iris.jpg", "credited_to": "Iris"}],
    })
    advance(dsession, cand)
    robot = promote(dsession, cand, approved_by="ops")
    # The candidate image is NOT auto-promoted to a display-eligible robot_image.
    img_count = dsession.execute(
        select(func.count()).select_from(RobotImage).where(RobotImage.robot_id == robot.id)
    ).scalar_one()
    assert img_count == 0
    # R3: the candidate image layer stores no binary.
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
        "data": {"official_url": "https://helio.invalid/h1"},
    })
    advance(dsession, cand)  # full pipeline, NO promote
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
        "data": {"official_url": "https://lyra.invalid/l1"},
    })
    advance(dsession, cand)
    robot = promote(dsession, cand, approved_by="ops@humanoid.company")

    audit = dsession.execute(
        select(PromotionAudit).where(PromotionAudit.candidate_id == cand.id)
    ).scalar_one()
    assert audit.action == "PROMOTED"
    assert audit.promoted_robot_id == robot.id
    assert audit.approved_by == "ops@humanoid.company"
    # candidate -> evidence -> canonical robot is fully reconstructable.
    ev = dsession.get(EvidenceSource, audit.evidence_source_id)
    assert ev is not None and ev.subject_id == robot.id
    assert ev.source_url == cand.trace_url


# --- K: structural isolation (no canonical -> discovery FK) -------------------

def test_K_structural_isolation(dsession):
    existing = dsession.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='humanoid' AND table_name = ANY(:names)"
    ), {"names": list(DISCOVERY_TABLES)}).scalars().all()
    assert set(existing) == DISCOVERY_TABLES  # the discovery layer exists

    fks = dsession.execute(text(
        "SELECT conrelid::regclass::text AS child, confrelid::regclass::text AS parent "
        "FROM pg_constraint WHERE contype='f'"
    )).all()

    def _leaf(name: str) -> str:
        return name.split(".")[-1].strip('"')

    for child, parent in fks:
        if _leaf(parent) in DISCOVERY_TABLES:
            # A discovery table may only be referenced by another discovery table;
            # no canonical table may point at the candidate layer (Gate K).
            assert _leaf(child) in DISCOVERY_TABLES, (
                f"canonical table {child!r} has an FK to discovery table {parent!r}"
            )


# --- supporting invariants ---------------------------------------------------

def test_recheck_is_autonomous_and_non_canonical(dsession):
    before = _robot_count(dsession)
    cand = _ingest_one(dsession, {
        "external_ref": "rc-1", "name": "Echo E1", "manufacturer": f"Echo {_uniq()}",
    })
    flag_recheck(dsession, cand, "official page changed")
    assert cand.status == "RECHECK_REQUIRED"
    assert _robot_count(dsession) == before  # metadata only, no canonical mutation


def test_ineligible_source_cannot_be_crawled(dsession):
    src = _source(dsession, eligible=False)  # not reviewed / not enabled
    record = {"external_ref": "x", "name": "X", "manufacturer": "Y"}
    with pytest.raises(DiscoveryError):
        ingest(dsession, src, FixtureAdapter([record]))


def test_source_enabled_requires_review_db_check(dsession):
    # DATA-D1.9 encoded as a DB CHECK: enabled without review must be rejected.
    dsession.add(DiscoverySource(
        key=f"bad-{_uniq()}", name="bad", source_class="OTHER",
        tos_reviewed=False, robots_allowed=False, is_enabled=True,
    ))
    with pytest.raises(IntegrityError):
        dsession.flush()


def test_build_proposal_is_read_only(dsession):
    before = _robot_count(dsession)
    cand = _ingest_one(dsession, {
        "external_ref": "p-1", "name": "Pax P1", "manufacturer": f"Pax {_uniq()}",
        "data": {"official_url": "https://pax.invalid/p1"},
    })
    advance(dsession, cand)
    proposal = build_proposal(dsession, cand)
    assert proposal["name"] == "Pax P1"
    assert proposal["gates_failed"] == []
    assert _robot_count(dsession) == before
