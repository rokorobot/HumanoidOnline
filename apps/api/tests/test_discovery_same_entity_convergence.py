"""Stage E — SAME_ENTITY promotion convergence (docs/16 §17.1), offline PostgreSQL.

Invariant: human-confirmed SAME_ENTITY candidates can never create more than one
canonical robot. `promote` locks the candidate's SAME_ENTITY group and
re-resolves identity at canonical-write time, so a stale NEW_ENTITY status (the
real 4NE1 reservation + product page case) converges onto the robot a
counterpart already created instead of creating a second one.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.discovery import DiscoveryCandidate, DiscoverySource, PromotionAudit
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import PromotionError, review
from app.services.discovery.identity_decisions import (
    NOT_SAME_ENTITY,
    SAME_ENTITY,
    record_identity_decision,
    same_entity_group,
)
from app.services.discovery.pipeline import advance
from app.services.discovery.promotion import promote

pytestmark = pytest.mark.usefixtures("no_external_network")


@pytest.fixture
def dsession(database_url):
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


class World:
    """One manufacturer with an official source, like production NEURA."""

    def __init__(self, session: Session) -> None:
        self.tag = uuid.uuid4().hex[:6]
        self.session = session
        self.maker = f"Neura{self.tag} Robotics"
        self.host = f"neura-{self.tag}.example"
        self.official = DiscoverySource(
            key=f"neura-official-{self.tag}", name="NEURA (test)", source_class="MANUFACTURER",
            homepage_url=f"https://{self.host}/", allowed_path_prefixes=["/products/", "/product/"],
            is_enabled=True, tos_status="ALLOWED", robots_status="ALLOWED",
            eligibility_reviewed_at=datetime(2026, 9, 26, tzinfo=UTC),
            eligibility_reviewed_by="fixture-reviewer",
        )
        session.add(self.official)
        session.flush()

    def candidate(self, path: str, name: str) -> DiscoveryCandidate:
        cand = DiscoveryCandidate(
            source_id=self.official.id, entity_type="ROBOT", candidate_name=name,
            candidate_manufacturer=self.maker, external_ref=f"https://{self.host}{path}")
        self.session.add(cand)
        self.session.flush()
        advance(self.session, cand)
        return cand

    def trace(self, cand: DiscoveryCandidate) -> DiscoveryCandidate:
        review.record_source_trace(self.session, cand.id, source=self.official.key,
                                   url=cand.external_ref, by="robert")
        return cand

    def decide(self, a, b, decision=SAME_ENTITY) -> None:
        record_identity_decision(self.session, a.id, b.id, decision, decided_by="robert",
                                 reason="fixture decision")

    def robots(self) -> list[Robot]:
        return list(self.session.scalars(
            select(Robot).join(Manufacturer, Manufacturer.id == Robot.manufacturer_id)
            .where(Manufacturer.name == self.maker)).all())


def robot_count(session) -> int:
    return session.scalar(select(func.count()).select_from(Robot))


def pair(w: World, name_a="4NE1", name_b="4NE1"):
    """The real case: a reservation page and a product page, decided SAME_ENTITY."""
    a = w.candidate("/product/4ne1-reservation", name_a)
    b = w.candidate("/products/4ne1", name_b)
    w.decide(a, b)
    for cand in (a, b):
        advance(w.session, cand)
        w.trace(cand)
    assert (a.status, b.status) == ("READY_FOR_PROMOTION", "READY_FOR_PROMOTION")
    assert (a.identity_status, b.identity_status) == ("NEW_ENTITY", "NEW_ENTITY")
    return a, b


def test_promoting_one_member_creates_exactly_one_robot(dsession):
    w = World(dsession)
    a, _b = pair(w)
    before = robot_count(dsession)
    robot = promote(dsession, a, approved_by="robert")
    assert robot_count(dsession) == before + 1
    assert w.robots() == [robot] and robot.is_published is False


def test_second_member_converges_onto_the_first_robot(dsession):
    w = World(dsession)
    a, b = pair(w)
    first = promote(dsession, a, approved_by="robert")
    before = robot_count(dsession)
    second = promote(dsession, b, approved_by="robert")
    assert second.id == first.id and robot_count(dsession) == before
    assert w.robots() == [first]
    # Both candidates and their own provenance remain; nothing merged or deleted.
    for cand in (a, b):
        dsession.refresh(cand)
        assert cand.status == "PROMOTED" and cand.promoted_robot_id == first.id
    assert b.identity_status == "MATCHED_EXISTING" and b.possible_robot_id == first.id
    assert (a.external_ref, b.external_ref) == (
        f"https://{w.host}/product/4ne1-reservation", f"https://{w.host}/products/4ne1")


def test_each_promotion_keeps_its_own_audit_and_evidence_lineage(dsession):
    w = World(dsession)
    a, b = pair(w)
    robot = promote(dsession, a, approved_by="robert")
    promote(dsession, b, approved_by="second-approver")
    audits = {row.candidate_id: row for row in dsession.scalars(
        select(PromotionAudit).where(PromotionAudit.candidate_id.in_([a.id, b.id]),
                                     PromotionAudit.action == "PROMOTED"))}
    assert set(audits) == {a.id, b.id}
    assert {row.promoted_robot_id for row in audits.values()} == {robot.id}
    assert (audits[a.id].approved_by, audits[b.id].approved_by) == ("robert", "second-approver")
    assert audits[a.id].detail["identity_revalidation"]["converged_on_robot_id"] is None
    converged = audits[b.id].detail["identity_revalidation"]
    assert converged["converged_on_robot_id"] == str(robot.id)
    assert converged["converged_via_candidates"] == [str(a.id)]
    evidence = {e.id: e for e in dsession.scalars(
        select(EvidenceSource).where(EvidenceSource.subject_id == robot.id))}
    assert {audits[a.id].evidence_source_id, audits[b.id].evidence_source_id} == set(evidence)
    assert sorted(e.source_url for e in evidence.values()) == sorted(
        [a.trace_url, b.trace_url])


def test_transitive_group_produces_one_robot(dsession):
    w = World(dsession)
    a = w.candidate("/product/q1-reservation", "Q1")
    b = w.candidate("/products/q1", "Q1 Standard")
    c = w.candidate("/products/q1-edition", "Q1 Edition")
    w.decide(a, b)
    w.decide(b, c)
    assert same_entity_group(dsession, c.id) == {a.id, b.id, c.id}
    for cand in (a, b, c):
        w.trace(cand)
        assert cand.identity_status == "NEW_ENTITY"
    before = robot_count(dsession)
    robots = {promote(dsession, cand, approved_by="robert").id for cand in (c, a, b)}
    assert len(robots) == 1 and robot_count(dsession) == before + 1


def test_not_same_entity_and_reversed_decisions_do_not_converge(dsession):
    w = World(dsession)
    a = w.candidate("/products/q1", "Q1")
    b = w.candidate("/products/q7", "Q7")
    c = w.candidate("/products/q9", "Q9")
    w.decide(a, b, NOT_SAME_ENTITY)
    w.decide(a, c, SAME_ENTITY)
    w.decide(a, c, NOT_SAME_ENTITY)          # reversal: the newest row is effective
    assert same_entity_group(dsession, a.id) == {a.id}
    for cand in (a, b, c):
        w.trace(cand)
    robots = {promote(dsession, cand, approved_by="robert").id for cand in (a, b, c)}
    assert len(robots) == 3


def test_not_same_entity_is_not_overridden_by_a_name_match(dsession):
    # Same name, but a human decided they are different: once one is promoted the
    # other would name-match its robot. That is refused, not silently linked.
    w = World(dsession)
    a = w.candidate("/products/q1", "Q1")
    b = w.candidate("/product/q1-other", "Q1")
    w.decide(a, b, NOT_SAME_ENTITY)
    for cand in (a, b):
        advance(dsession, cand)
        w.trace(cand)
    promote(dsession, a, approved_by="robert")
    before = robot_count(dsession)
    with pytest.raises(PromotionError, match="NOT_SAME_ENTITY"):
        promote(dsession, b, approved_by="robert")
    assert robot_count(dsession) == before and b.promoted_robot_id is None


def test_rejected_member_cannot_be_promoted_and_is_never_a_target(dsession):
    w = World(dsession)
    a, b = pair(w)
    review.reject_candidate(dsession, b.id, by="robert", reason="out of scope",
                            reason_code="OUT_OF_SCOPE")
    before = robot_count(dsession)
    with pytest.raises(PromotionError, match="READY_FOR_PROMOTION"):
        promote(dsession, b, approved_by="robert")
    assert robot_count(dsession) == before and b.promoted_robot_id is None
    robot = promote(dsession, a, approved_by="robert")
    assert robot_count(dsession) == before + 1 and w.robots() == [robot]
    assert b.status == "REJECTED" and b.promoted_robot_id is None


def test_stale_new_entity_status_cannot_create_a_duplicate(dsession):
    # Different names, so only the human SAME_ENTITY decision links them: the
    # resolver alone would call B a new entity. B is not re-advanced after A's
    # promotion; its stored NEW_ENTITY status is stale.
    w = World(dsession)
    a, b = pair(w, name_a="4NE1", name_b="4NE1 Reservation Edition")
    robot = promote(dsession, a, approved_by="robert")
    assert b.identity_status == "NEW_ENTITY" and b.status == "READY_FOR_PROMOTION"
    before = robot_count(dsession)
    assert promote(dsession, b, approved_by="robert").id == robot.id
    assert robot_count(dsession) == before and w.robots() == [robot]


def test_group_pointing_at_two_robots_is_refused_without_canonical_mutation(dsession):
    w = World(dsession)
    a = w.candidate("/products/q1", "Q1")
    b = w.candidate("/products/q1-pro", "Q1 Pro")
    c = w.candidate("/products/q2", "Q2")
    for cand in (a, b, c):
        w.trace(cand)
    r1 = promote(dsession, a, approved_by="robert")
    r2 = promote(dsession, c, approved_by="robert")
    w.decide(a, b)
    w.decide(b, c)                           # the group now spans two robots
    before = (robot_count(dsession), w.robots(),
              dsession.scalar(select(func.count()).select_from(EvidenceSource)))
    with pytest.raises(PromotionError, match="governance conflict") as exc:
        promote(dsession, b, approved_by="robert")
    for ident in (r1.id, r2.id, a.id, c.id):
        assert str(ident) in str(exc.value)
    assert (robot_count(dsession), w.robots(),
            dsession.scalar(select(func.count()).select_from(EvidenceSource))) == before
    assert b.promoted_robot_id is None and b.status == "READY_FOR_PROMOTION"


def test_already_promoted_candidate_is_still_refused(dsession):
    w = World(dsession)
    a, b = pair(w)
    promote(dsession, a, approved_by="robert")
    promote(dsession, b, approved_by="robert")
    before = robot_count(dsession)
    for cand in (a, b):
        with pytest.raises(PromotionError, match="already promoted"):
            promote(dsession, cand, approved_by="robert")
    assert robot_count(dsession) == before


def test_no_alias_is_inferred_for_a_differently_spelled_catalogue_robot(dsession):
    # Catalogue writes 4NE-1; the source writes 4NE1. Without a confirmed alias or
    # human decision, convergence must not reach the catalogue robot.
    w = World(dsession)
    maker = Manufacturer(slug=f"neura-{w.tag}", name=w.maker)
    dsession.add(maker)
    dsession.flush()
    catalogued = Robot(slug=f"4ne-1-{w.tag}", manufacturer_id=maker.id, name="4NE-1",
                       is_published=False)
    dsession.add(catalogued)
    dsession.flush()
    a, b = pair(w)
    robots = {promote(dsession, cand, approved_by="robert").id for cand in (a, b)}
    assert len(robots) == 1 and catalogued.id not in robots
    assert {r.name for r in w.robots()} == {"4NE-1", "4NE1"}


def _cleanup(ids: dict) -> None:
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))  # append-only trigger
        conn.execute(text("DELETE FROM candidate_identity_decision WHERE candidate_a_id = ANY(:c)"
                          " OR candidate_b_id = ANY(:c)"), {"c": ids["candidates"]})
        conn.execute(text("SET LOCAL session_replication_role = origin"))
        conn.execute(text("DELETE FROM promotion_audit WHERE candidate_id = ANY(:c)"),
                     {"c": ids["candidates"]})
        conn.execute(text("DELETE FROM evidence_source WHERE subject_id IN "
                          "(SELECT r.id FROM robot r JOIN manufacturer m"
                          " ON m.id = r.manufacturer_id WHERE m.name = :m)"),
                     {"m": ids["maker"]})
        conn.execute(text("DELETE FROM discovery_candidate WHERE id = ANY(:c)"),
                     {"c": ids["candidates"]})
        conn.execute(text("DELETE FROM robot WHERE manufacturer_id IN "
                          "(SELECT id FROM manufacturer WHERE name = :m)"), {"m": ids["maker"]})
        conn.execute(text("DELETE FROM manufacturer WHERE name = :m"), {"m": ids["maker"]})
        conn.execute(text("DELETE FROM discovery_source WHERE key = :k"), {"k": ids["source"]})


def test_concurrent_promotions_of_one_group_serialize(database_url):
    """Two sessions promoting both halves of a pair at once cannot both see "no
    promoted counterpart": the second blocks on the group lock, and after the
    first commits it converges instead of creating a second robot."""
    with Session(engine, expire_on_commit=False) as setup:
        w = World(setup)
        a, b = pair(w)
        setup.commit()
    ids = {"candidates": [a.id, b.id], "maker": w.maker, "source": w.official.key}
    try:
        with Session(engine) as first, Session(engine) as second:
            robot = promote(first, first.get(DiscoveryCandidate, a.id), approved_by="robert")
            robot_id = robot.id
            # `first` holds the group lock (uncommitted). `second` must wait, not
            # proceed on the stale view where nothing in the group is promoted.
            second.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(OperationalError, match="lock"):
                promote(second, second.get(DiscoveryCandidate, b.id), approved_by="robert")
            second.rollback()
            first.commit()
            converged = promote(second, second.get(DiscoveryCandidate, b.id),
                                approved_by="robert")
            second.commit()
            assert converged.id == robot_id
        with Session(engine) as check:
            assert check.scalar(
                select(func.count()).select_from(Robot)
                .join(Manufacturer, Manufacturer.id == Robot.manufacturer_id)
                .where(Manufacturer.name == w.maker)) == 1
    finally:
        _cleanup(ids)
