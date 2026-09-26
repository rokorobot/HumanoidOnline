"""Stage E — exception-only human review, built from the first real NEURA crawl
(production run 2c64d1f3, 2026-09-26). Offline, PostgreSQL, rollback-isolated.

The cases are the ones that run actually produced: two same-source pairs (4NE1
reservation + robot page; MiPA reservation + robot page), three candidates that
are not humanoids (LARA, MAiRA, MAV), a variant (4NE1 Mini), and a catalogue
record spelled '4NE-1' that the site writes '4NE1'. Each test uses a unique
manufacturer name so it never collides with other rows in the shared database.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager

import pytest
import sqlalchemy.exc
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.cli import discovery as cli
from app.db import session as db_session
from app.db.session import engine
from app.models.discovery import (
    CandidateClaim,
    CandidateIdentityDecision,
    DiscoveryCandidate,
    DiscoverySource,
    IdentityDecisionImmutableError,
    PromotionAudit,
)
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import DiscoveryError, PromotionError, review
from app.services.discovery.identity import ALIASES_PATH, resolve_identity
from app.services.discovery.pipeline import advance
from app.services.discovery.promotion import build_proposal

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


class Neura:
    """A test-local copy of the first crawl's situation."""

    def __init__(self, session: Session) -> None:
        self.session = session
        tag = uuid.uuid4().hex[:6]
        self.maker = f"Neura{tag} Robotics"
        self.host = f"https://neura-{tag}.example"
        mfr = Manufacturer(slug=f"neura-{tag}", name=self.maker)
        session.add(mfr)
        session.flush()
        self.catalogue_4ne1 = Robot(slug=f"neura-4ne-1-{tag}", manufacturer_id=mfr.id,
                                    name="4NE-1", is_published=False)
        self.source = DiscoverySource(key=f"neura-{tag}", name="NEURA (test)",
                                      source_class="MANUFACTURER")
        session.add_all([self.catalogue_4ne1, self.source])
        session.flush()

    def candidate(self, path: str, name: str) -> DiscoveryCandidate:
        cand = DiscoveryCandidate(
            source_id=self.source.id, entity_type="ROBOT", candidate_name=name,
            candidate_manufacturer=self.maker, external_ref=f"{self.host}{path}",
            discovery_url=f"{self.host}{path}",
        )
        self.session.add(cand)
        self.session.flush()
        advance(self.session, cand)   # the pipeline, exactly as the crawl ran it
        return cand

    def ids(self) -> set[uuid.UUID]:
        return set(self.session.scalars(select(DiscoveryCandidate.id).where(
            DiscoveryCandidate.source_id == self.source.id)))

    def queue(self) -> list[review.QueueItem]:
        mine = self.ids()
        return [i for i in review.review_queue(self.session)
                if set(i.candidate_ids) <= mine]


def kinds(items) -> list[tuple[str, frozenset]]:
    return sorted((i.kind, frozenset(i.candidate_ids)) for i in items)


def decisions(session) -> int:
    return session.scalar(select(func.count()).select_from(CandidateIdentityDecision))


# ------------------------------------------------------------ real NEURA cases --


def test_4ne1_pair_same_entity_ends_repeated_duplicate_review(dsession):
    w = Neura(dsession)
    reservation = w.candidate("/product/4ne1-reservation", "4NE1")
    page = w.candidate("/products/4ne1", "4NE1")
    assert (reservation.identity_status, page.identity_status) == ("NEW_ENTITY",
                                                                   "POSSIBLE_DUPLICATE")
    for c in (reservation, page):
        c.claims.append(CandidateClaim(field_key="height_m", claimed_value="1.8",
                                       discovery_source_id=w.source.id))
    dsession.flush()
    assert ("DUPLICATE_PAIR", frozenset({reservation.id, page.id})) in kinds(w.queue())

    row, created = review.decide_pair(dsession, page.id, reservation.id, review.SAME_ENTITY,
                                      decided_by="robert", reason="same robot, two pages")
    assert created and row.decision == "SAME_ENTITY"
    assert (row.candidate_a_id, row.candidate_b_id) == tuple(
        sorted((page.id, reservation.id), key=str))
    assert page.identity_status == "NEW_ENTITY" and page.status == "SOURCE_TRACE"
    assert not [i for i in w.queue() if i.kind == "DUPLICATE_PAIR"]
    # Nothing merged: both rows, and their evidence, are intact.
    assert w.ids() == {reservation.id, page.id}
    assert len(reservation.claims) == 1 and len(page.claims) == 1
    # Exposed to the promoting human.
    assert build_proposal(dsession, page)["same_entity_candidates"] == [str(reservation.id)]
    # A future run re-resolves both: still no duplicate review.
    advance(dsession, reservation)
    advance(dsession, page)
    assert {reservation.identity_status, page.identity_status} == {"NEW_ENTITY"}


def test_mipa_pair_same_entity(dsession):
    w = Neura(dsession)
    reservation = w.candidate("/product/mipa-reservation", "MiPA")
    page = w.candidate("/products/mipa", "MiPA")
    assert page.identity_status == "POSSIBLE_DUPLICATE"
    review.decide_pair(dsession, reservation.id, page.id, review.SAME_ENTITY,
                       decided_by="robert", reason="reservation page of the same robot")
    assert page.identity_status == "NEW_ENTITY"
    assert not [i for i in w.queue() if i.kind == "DUPLICATE_PAIR"]


def test_out_of_scope_rejection_is_terminal_and_stops_duplicate_noise(dsession):
    w = Neura(dsession)
    lara = w.candidate("/products/lara", "LARA")
    mav = w.candidate("/products/mav", "MAV")
    for cand, why in ((lara, "collaborative robot arm"), (mav, "mobile transport robot")):
        review.reject_candidate(dsession, cand.id, by="robert", reason=why,
                                reason_code="OUT_OF_SCOPE")
    assert (lara.status, mav.status) == ("REJECTED", "REJECTED")
    audit = dsession.scalars(select(PromotionAudit).where(
        PromotionAudit.candidate_id == lara.id)).one()
    assert (audit.action, audit.detail) == (
        "REJECTED", {"reason": "collaborative robot arm", "reason_code": "OUT_OF_SCOPE"})
    assert not w.queue()                                   # nothing left to review
    with pytest.raises(DiscoveryError):
        advance(dsession, lara)                            # terminal
    with pytest.raises(PromotionError):
        review.reject_candidate(dsession, lara.id, by="robert", reason="again",
                                reason_code="OUT_OF_SCOPE")
    # The next observation of 'LARA' (a new URL) is not duplicate noise.
    again = w.candidate("/products/lara-2", "LARA")
    assert again.identity_status == "NEW_ENTITY"
    assert w.ids() >= {lara.id, mav.id}                    # rows kept as history


def test_rejected_candidate_no_longer_makes_others_possible_duplicate(dsession):
    w = Neura(dsession)
    page = w.candidate("/products/maira", "MAiRA")
    other = w.candidate("/products/maira-2", "MAiRA")
    assert other.identity_status == "POSSIBLE_DUPLICATE"
    review.reject_candidate(dsession, page.id, by="robert", reason="not a humanoid",
                            reason_code="OUT_OF_SCOPE")
    assert other.identity_status == "NEW_ENTITY"           # re-resolved by the decision
    assert resolve_identity(dsession, other, aliases={}) == "NEW_ENTITY"


def test_not_same_entity_suppresses_exactly_that_pair(dsession):
    w = Neura(dsession)
    a = w.candidate("/product/a", "Q1")
    b = w.candidate("/product/b", "Q1")
    c = w.candidate("/product/c", "Q1")
    assert len([i for i in w.queue() if i.kind == "DUPLICATE_PAIR"]) == 3
    review.decide_pair(dsession, a.id, b.id, review.NOT_SAME_ENTITY,
                       decided_by="robert", reason="different generations")
    pairs = {i.candidate_ids for i in w.queue() if i.kind == "DUPLICATE_PAIR"}
    assert {frozenset(p) for p in pairs} == {frozenset({a.id, c.id}), frozenset({b.id, c.id})}


def test_reversal_appends_and_latest_wins_history_is_immutable(dsession):
    w = Neura(dsession)
    a = w.candidate("/product/x", "X1")
    b = w.candidate("/products/x", "X1")
    first, _ = review.decide_pair(dsession, a.id, b.id, review.SAME_ENTITY,
                                  decided_by="robert", reason="looked the same")
    snapshot = (first.id, first.decision, first.decided_by, first.reason, first.created_at)
    second, created = review.decide_pair(dsession, b.id, a.id, review.NOT_SAME_ENTITY,
                                         decided_by="robert", reason="on reflection, no")
    assert created and second.decision_seq > first.decision_seq
    assert review.effective_decisions(dsession, a.id) == {b.id: "NOT_SAME_ENTITY"}
    dsession.refresh(first)
    assert (first.id, first.decision, first.decided_by, first.reason,
            first.created_at) == snapshot
    assert [line.split()[1] for line in review.history(dsession, a.id)] == [
        "SAME_ENTITY", "NOT_SAME_ENTITY"]
    first.reason = "rewritten"
    with pytest.raises(IdentityDecisionImmutableError):
        dsession.flush()
    dsession.rollback()


def test_database_refuses_update_delete_and_bad_pairs(dsession):
    w = Neura(dsession)
    a = w.candidate("/product/y", "Y1")
    b = w.candidate("/products/y", "Y1")
    review.decide_pair(dsession, a.id, b.id, review.SAME_ENTITY, decided_by="r", reason="r")
    first, second = sorted((a.id, b.id), key=str)
    for sql in ("UPDATE candidate_identity_decision SET reason = 'x'",
                "DELETE FROM candidate_identity_decision"):
        with pytest.raises(sqlalchemy.exc.DBAPIError), dsession.begin_nested():
            dsession.execute(text(sql))
    for a_id, b_id in ((second, first), (first, first)):   # unordered / self pair
        with pytest.raises(sqlalchemy.exc.IntegrityError), dsession.begin_nested():
            dsession.execute(text(
                "INSERT INTO candidate_identity_decision "
                "(candidate_a_id, candidate_b_id, decision, decided_by, reason) "
                "VALUES (:a, :b, 'SAME_ENTITY', 'r', 'r')"), {"a": a_id, "b": b_id})
    with pytest.raises(DiscoveryError):
        review.decide_pair(dsession, a.id, a.id, review.SAME_ENTITY, decided_by="r", reason="r")
    with pytest.raises(DiscoveryError):
        review.decide_pair(dsession, a.id, uuid.uuid4(), review.SAME_ENTITY,
                           decided_by="r", reason="r")
    for by, why in (("", "r"), ("r", " ")):
        with pytest.raises(DiscoveryError):
            review.decide_pair(dsession, a.id, b.id, review.NOT_SAME_ENTITY,
                               decided_by=by, reason=why)


def test_4ne1_mini_stays_separate(dsession):
    w = Neura(dsession)
    base = w.candidate("/product/4ne1-reservation", "4NE1")
    mini = w.candidate("/product/4ne1-mini-reservation", "4NE1 Mini")
    assert (base.identity_status, mini.identity_status) == ("NEW_ENTITY", "NEW_ENTITY")
    assert not [i for i in w.queue() if mini.id in i.candidate_ids
                and i.kind == "DUPLICATE_PAIR"]
    assert review.effective_decisions(dsession, mini.id) == {}


def test_no_catalogue_match_without_a_confirmed_alias(dsession, tmp_path):
    w = Neura(dsession)
    reservation = w.candidate("/product/4ne1-reservation", "4NE1")
    assert reservation.identity_status == "NEW_ENTITY" and reservation.possible_robot_id is None
    shown = "\n".join(review.show(dsession, reservation.id))
    assert f"{w.catalogue_4ne1.slug}" in shown and "different key" in shown
    assert "EXACT KEY MATCH" not in shown

    before = hashlib.sha256(ALIASES_PATH.read_bytes()).hexdigest()
    entry = review.propose_alias(dsession, reservation.id, w.catalogue_4ne1.slug)
    assert entry["alias"] == "4NE1" and entry["confirmed_by"] is None
    assert hashlib.sha256(ALIASES_PATH.read_bytes()).hexdigest() == before  # nothing written

    # A pending proposal is surfaced for a human; it does not change resolution.
    register = tmp_path / "aliases.json"
    register.write_text(json.dumps({"aliases": [{**entry, "proposed_at": "2026-09-26"}]}))
    pending = [i for i in review.review_queue(dsession, aliases_path=register)
               if i.kind == "ALIAS_PROPOSAL_PENDING" and reservation.id in i.candidate_ids]
    assert len(pending) == 1
    assert resolve_identity(dsession, reservation, aliases={}) == "NEW_ENTITY"
    # Only a CONFIRMED alias (the existing mechanism) would ever match it.
    confirmed = {w.catalogue_4ne1.slug: ("4NE1",)}
    assert resolve_identity(dsession, reservation, aliases=confirmed) == "MATCHED_EXISTING"


def test_replay_is_deterministic_and_writes_nothing_twice(dsession):
    w = Neura(dsession)
    reservation = w.candidate("/product/4ne1-reservation", "4NE1")
    page = w.candidate("/products/4ne1", "4NE1")
    lara = w.candidate("/products/lara", "LARA")
    first_queue = w.queue()
    assert w.queue() == first_queue                       # listing is deterministic
    count = decisions(dsession)
    for _ in range(2):
        review.decide_pair(dsession, reservation.id, page.id, review.SAME_ENTITY,
                           decided_by="robert", reason="same")
    assert decisions(dsession) == count + 1                # repeat = no new row
    for c in (reservation, page, lara):
        advance(dsession, c)
    assert decisions(dsession) == count + 1
    assert w.queue() == w.queue()
    assert "\n".join(review.show(dsession, page.id)) == "\n".join(review.show(dsession, page.id))


# ------------------------------------------------------------------------ CLI --


@contextmanager
def _shared(session):
    yield session


@pytest.fixture
def cli_session(dsession, monkeypatch):
    dsession.commit = dsession.flush  # CLI commits must not escape the rollback
    monkeypatch.setattr(db_session, "SessionLocal", lambda: _shared(dsession))
    return dsession


def test_cli_review_workflow(cli_session, capsys):
    w = Neura(cli_session)
    reservation = w.candidate("/product/4ne1-reservation", "4NE1")
    page = w.candidate("/products/4ne1", "4NE1")
    mav = w.candidate("/products/mav", "MAV")

    assert cli.main(["review", "list"]) == 0
    listing = capsys.readouterr().out
    assert "DUPLICATE_PAIR" in listing and str(page.id) in listing
    assert cli.main(["review", "show", str(page.id)]) == 0
    assert "related candidates (same identity key)" in capsys.readouterr().out
    assert cli.main(["review", "same-as", str(page.id), str(reservation.id),
                     "--by", "robert", "--reason", "same robot"]) == 0
    assert "RECORDED SAME_ENTITY" in capsys.readouterr().out
    assert cli.main(["review", "same-as", str(page.id), str(reservation.id),
                     "--by", "robert", "--reason", "same robot"]) == 0
    assert "ALREADY IN EFFECT" in capsys.readouterr().out
    assert cli.main(["review", "reject", str(mav.id), "--reason-code", "OUT_OF_SCOPE",
                     "--by", "robert", "--reason", "mobile robot"]) == 0
    assert cli.main(["review", "history", str(page.id)]) == 0
    assert "SAME_ENTITY" in capsys.readouterr().out
    assert cli.main(["review", "propose-alias", str(reservation.id),
                     w.catalogue_4ne1.slug]) == 0
    assert "PROPOSAL ONLY" in capsys.readouterr().out
    assert cli.main(["review", "same-as", str(page.id), str(page.id), "--by", "r",
                     "--reason", "r"]) == 1


@pytest.mark.parametrize("argv", [
    ["review", "show", "not-a-uuid"],
    ["review", "same-as", "00000000-0000-0000-0000-000000000001", "x", "--by", "r",
     "--reason", "r"],
    ["review", "reject", "00000000-0000-0000-0000-000000000001", "--reason-code", "SPAM",
     "--by", "r", "--reason", "r"],
    ["review", "not-same-as", "00000000-0000-0000-0000-000000000001",
     "00000000-0000-0000-0000-000000000002", "--reason", "r"],
])
def test_cli_argument_rules(argv):
    with pytest.raises(SystemExit):
        cli.main(argv)
