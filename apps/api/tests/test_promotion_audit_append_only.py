"""promotion_audit is append-only at the DATABASE (migration 0017, DR-A5 section 19.3).

The ORM listeners already refused ORM-level changes. These tests prove the database
refuses RAW SQL too, which is the bypass the listeners could not close, while every
governed path that only INSERTs keeps working, and deleting a robot still works (the
`ON DELETE SET NULL` referential action is the one allowed internal update).

Each forbidden statement runs inside a SAVEPOINT so the failure is observed without
poisoning the surrounding test transaction, which is rolled back at the end.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_discovery_same_entity_convergence import World

from app.db.session import engine
from app.models.discovery import PromotionAudit
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import review
from app.services.discovery.promotion import promote

pytestmark = pytest.mark.usefixtures("no_external_network")

RESTRICT_VIOLATION = "23001"


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


@contextmanager
def refused(session: Session, *, op: str):
    """The statement must fail in the database with restrict_violation."""
    savepoint = session.begin_nested()
    try:
        with pytest.raises(DBAPIError) as exc:
            yield
        assert getattr(exc.value.orig, "sqlstate", None) == RESTRICT_VIOLATION
        assert "append-only" in str(exc.value.orig) and f"{op} refused" in str(exc.value.orig)
    finally:
        savepoint.rollback()


def audit_snapshot(session: Session, candidate_id) -> list[tuple]:
    return list(session.execute(text(
        "SELECT id, action, approved_by, promoted_robot_id, md5(a::text) "
        "FROM promotion_audit a WHERE candidate_id = :c ORDER BY created_at, id"),
        {"c": candidate_id}).all())


def seeded_audit_row(session: Session) -> tuple[World, PromotionAudit]:
    w = World(session)
    cand = w.candidate("/products/q1", "Q1")
    w.trace(cand)
    promote(session, cand, approved_by="robert")
    row = session.scalars(select(PromotionAudit).where(
        PromotionAudit.candidate_id == cand.id, PromotionAudit.action == "PROMOTED")).one()
    return w, row


# --------------------------------------------------------------- INSERT still works --


def test_every_governed_path_still_inserts(dsession):
    w = World(dsession)
    promoted = w.candidate("/products/p1", "P1")
    w.trace(promoted)                                        # TRACE_CONFIRMED
    promote(dsession, promoted, approved_by="robert")        # PROMOTED
    rejected = w.candidate("/products/r1", "R1")
    review.reject_candidate(dsession, rejected.id, by="robert", reason="not humanoid",
                            reason_code="OUT_OF_SCOPE")      # REJECTED
    actions = {c.id: [a[1] for a in audit_snapshot(dsession, c.id)] for c in (promoted, rejected)}
    # created_at ties inside one transaction, so compare as a set, not an order.
    assert sorted(actions[promoted.id]) == ["PROMOTED", "TRACE_CONFIRMED"]
    assert actions[rejected.id] == ["REJECTED"]


def test_a_raw_insert_is_allowed(dsession):
    w = World(dsession)
    cand = w.candidate("/products/i1", "I1")
    dsession.execute(text(
        "INSERT INTO promotion_audit (candidate_id, action, approved_by, detail) "
        "VALUES (:c, 'NOTE', 'robert', '{\"k\": 1}'::jsonb)"), {"c": cand.id})
    assert [a[1] for a in audit_snapshot(dsession, cand.id)] == ["NOTE"]


# ----------------------------------------------- UPDATE and DELETE are refused in SQL --


@pytest.mark.parametrize("assignment", [
    "approved_by = 'someone else'",
    "action = 'REJECTED'",
    "detail = '{}'::jsonb",
    "created_at = now() - interval '1 year'",
    "evidence_source_id = gen_random_uuid()",
    "promoted_entity_type = NULL",
    "approved_by = approved_by",                  # even a no-op rewrite is refused
    "promoted_robot_id = NULL",                   # a DIRECT unlink is refused too
])
def test_raw_update_is_refused_and_changes_nothing(dsession, assignment):
    w, row = seeded_audit_row(dsession)
    assert row.promoted_robot_id is not None      # so the unlink case is a real change
    before = audit_snapshot(dsession, row.candidate_id)
    with refused(dsession, op="UPDATE"):
        dsession.execute(text(f"UPDATE promotion_audit SET {assignment} WHERE id = :i"),
                         {"i": row.id})
    assert audit_snapshot(dsession, row.candidate_id) == before


def test_a_bulk_update_of_every_row_is_refused(dsession):
    seeded_audit_row(dsession)
    with refused(dsession, op="UPDATE"):
        dsession.execute(text("UPDATE promotion_audit SET approved_by = 'x'"))


@pytest.mark.parametrize("where", ["id = :i", "true", "candidate_id = :c", "false"])
def test_raw_delete_is_refused_and_removes_nothing(dsession, where):
    w, row = seeded_audit_row(dsession)
    before = audit_snapshot(dsession, row.candidate_id)
    with refused(dsession, op="DELETE"):                       # even a zero-row DELETE
        dsession.execute(text(f"DELETE FROM promotion_audit WHERE {where}"),
                         {"i": row.id, "c": row.candidate_id})
    assert audit_snapshot(dsession, row.candidate_id) == before


def test_the_orm_listeners_still_refuse_first(dsession):
    from app.models.discovery import PromotionAuditImmutableError
    w, row = seeded_audit_row(dsession)
    row.approved_by = "tampered"
    with pytest.raises(PromotionAuditImmutableError):
        dsession.flush()


# ---------------------------------- the one allowed internal update: robot deletion --


def test_deleting_a_robot_still_works_and_only_nulls_the_audit_link(dsession):
    w, row = seeded_audit_row(dsession)
    robot_id = row.promoted_robot_id
    before = dsession.execute(text(
        "SELECT to_jsonb(a) - 'promoted_robot_id' FROM promotion_audit a WHERE id = :i"),
        {"i": row.id}).scalar_one()
    dsession.execute(text("DELETE FROM robot WHERE id = :r"), {"r": robot_id})   # raw SQL
    after = dsession.execute(text(
        "SELECT to_jsonb(a) - 'promoted_robot_id', promoted_robot_id FROM promotion_audit a "
        "WHERE id = :i"), {"i": row.id}).one()
    assert after[1] is None                       # the link was nulled by the FK action
    assert after[0] == before                     # and nothing else about the audit row moved


def test_deleting_a_robot_with_no_audit_rows_is_unaffected(dsession):
    maker = Manufacturer(slug=f"m-{uuid.uuid4().hex[:8]}", name=f"M{uuid.uuid4().hex[:8]}")
    dsession.add(maker)
    dsession.flush()
    robot = Robot(slug=f"r-{uuid.uuid4().hex[:8]}", manufacturer_id=maker.id, name="R",
                  is_published=False)
    dsession.add(robot)
    dsession.flush()
    dsession.execute(text("DELETE FROM robot WHERE id = :r"), {"r": robot.id})
    assert dsession.execute(text("SELECT count(*) FROM robot WHERE id = :r"),
                            {"r": robot.id}).scalar_one() == 0


def test_a_rolled_back_attempt_leaves_the_table_exactly_as_it_was(dsession):
    w, row = seeded_audit_row(dsession)
    count = dsession.execute(text("SELECT count(*) FROM promotion_audit")).scalar_one()
    with refused(dsession, op="DELETE"):
        dsession.execute(text("DELETE FROM promotion_audit"))
    assert dsession.execute(text("SELECT count(*) FROM promotion_audit")).scalar_one() == count
