"""Stage E — governed trace recording (`discovery review trace`), offline.

The command is a thin, validated path onto the EXISTING `pipeline.record_trace`
(the same call the batch review makes): the source must exist, be an official
class and approve the URL's host/path. An identical re-record is a no-op, a
different trace is refused, recording never promotes and never writes the
catalogue, and every promotion gate still applies on its own.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import discovery as cli
from app.db import session as db_session
from app.db.session import engine
from app.models.discovery import CandidateClaim, DiscoveryCandidate, DiscoverySource, PromotionAudit
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import DiscoveryError, PromotionError, review
from app.services.discovery.pipeline import advance
from app.services.discovery.promotion import check_gates, promote

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
    def __init__(self, session: Session) -> None:
        tag = uuid.uuid4().hex[:6]
        self.session = session
        self.maker = f"Neura{tag} Robotics"
        self.host = f"neura-{tag}.example"
        session.add(Manufacturer(slug=f"neura-{tag}", name=self.maker))
        self.official = DiscoverySource(
            key=f"neura-official-{tag}", name="NEURA (test)", source_class="MANUFACTURER",
            homepage_url=f"https://{self.host}/", allowed_path_prefixes=["/products/", "/product/"],
            is_enabled=True, tos_status="ALLOWED", robots_status="ALLOWED",
            eligibility_reviewed_at=datetime(2026, 9, 26, tzinfo=UTC),
            eligibility_reviewed_by="fixture-reviewer",
        )
        self.aggregator = DiscoverySource(
            key=f"aggregator-{tag}", name="Aggregator (test)", source_class="AGGREGATOR",
            homepage_url=f"https://{self.host}/")
        session.add_all([self.official, self.aggregator])
        session.flush()

    def candidate(self, path: str, name: str) -> DiscoveryCandidate:
        cand = DiscoveryCandidate(
            source_id=self.official.id, entity_type="ROBOT", candidate_name=name,
            candidate_manufacturer=self.maker, external_ref=f"https://{self.host}{path}")
        self.session.add(cand)
        self.session.flush()
        advance(self.session, cand)
        return cand

    def url(self, path: str) -> str:
        return f"https://{self.host}{path}"


def canonical(session) -> tuple[int, int]:
    return (session.scalar(select(func.count()).select_from(Robot)),
            session.scalar(select(func.count()).select_from(Manufacturer)))


def test_valid_official_trace_is_recorded_audited_and_does_not_promote(dsession):
    w = World(dsession)
    cand = w.candidate("/product/4ne1-reservation", "4NE1")
    assert cand.status == "SOURCE_TRACE"
    before = canonical(dsession)
    traced, recorded = review.record_source_trace(
        dsession, cand.id, source=w.official.key,
        url=w.url("/product/4ne1-reservation/?utm_source=x"), by="robert")
    assert recorded
    assert (traced.trace_state, traced.trace_url, traced.trace_source_type) == (
        "TRACE_CONFIRMED", w.url("/product/4ne1-reservation"), "MANUFACTURER_SITE")
    assert traced.trace_verified_by == "robert" and traced.trace_verified_at is not None
    assert traced.status == "READY_FOR_PROMOTION"          # the pipeline advanced it
    assert traced.promoted_robot_id is None                # ...and nothing more
    assert canonical(dsession) == before
    audit = dsession.scalars(select(PromotionAudit).where(
        PromotionAudit.candidate_id == cand.id)).one()
    assert audit.action == "TRACE_CONFIRMED" and audit.detail["source_key"] == w.official.key
    assert any("TRACE_CONFIRMED" in line for line in review.history(dsession, cand.id))
    shown = "\n".join(review.show(dsession, cand.id))
    assert "trace: " + w.url("/product/4ne1-reservation") in shown
    listed = [i for i in review.review_queue(dsession) if cand.id in i.candidate_ids]
    assert [i.kind for i in listed] == ["READY_FOR_PROMOTION"]
    assert "traced: " in listed[0].summary


def test_replay_is_idempotent_and_a_different_trace_is_refused(dsession):
    w = World(dsession)
    cand = w.candidate("/products/mipa", "MiPA")
    url = w.url("/products/mipa")
    review.record_source_trace(dsession, cand.id, source=w.official.key, url=url, by="robert")
    stamp = cand.trace_verified_at
    _, recorded = review.record_source_trace(dsession, cand.id, source=str(w.official.id),
                                             url=url + "/", by="someone-else")
    assert recorded is False and cand.trace_verified_at == stamp
    assert cand.trace_verified_by == "robert"
    with pytest.raises(DiscoveryError, match="refused rather than replacing"):
        review.record_source_trace(dsession, cand.id, source=w.official.key,
                                   url=w.url("/product/mipa-reservation"), by="robert")
    assert cand.trace_url == url
    assert dsession.scalar(select(func.count()).select_from(PromotionAudit).where(
        PromotionAudit.candidate_id == cand.id)) == 1


@pytest.mark.parametrize(("url", "match"), [
    ("https://other.example/products/mipa", "approved host"),
    ("https://{host}/shop/mipa", "outside"),
    ("https://{host}/", "outside"),
    ("ftp://{host}/products/mipa", "absolute http"),
    ("/products/mipa", "absolute http"),
])
def test_off_host_or_off_path_traces_are_refused(dsession, url, match):
    w = World(dsession)
    cand = w.candidate("/products/mipa", "MiPA")
    with pytest.raises(DiscoveryError, match=match):
        review.record_source_trace(dsession, cand.id, source=w.official.key,
                                   url=url.format(host=w.host), by="robert")
    assert cand.trace_state == "NOT_TRACED"


def test_unknown_or_non_official_source_and_missing_attribution_are_refused(dsession):
    w = World(dsession)
    cand = w.candidate("/products/mipa", "MiPA")
    with pytest.raises(DiscoveryError, match="no discovery source"):
        review.record_source_trace(dsession, cand.id, source="no-such-source",
                                   url=w.url("/products/mipa"), by="robert")
    with pytest.raises(DiscoveryError, match="authoritative trace needs"):
        review.record_source_trace(dsession, cand.id, source=w.aggregator.key,
                                   url=w.url("/products/mipa"), by="robert")
    with pytest.raises(DiscoveryError, match="--by"):
        review.record_source_trace(dsession, cand.id, source=w.official.key,
                                   url=w.url("/products/mipa"), by="  ")
    with pytest.raises(DiscoveryError, match="no discovery candidate"):
        review.record_source_trace(dsession, uuid.uuid4(), source=w.official.key,
                                   url=w.url("/products/mipa"), by="robert")
    assert cand.trace_state == "NOT_TRACED"


def test_rejected_candidate_cannot_be_traced(dsession):
    w = World(dsession)
    cand = w.candidate("/products/lara", "LARA")
    review.reject_candidate(dsession, cand.id, by="robert", reason="cobot",
                            reason_code="OUT_OF_SCOPE")
    with pytest.raises(DiscoveryError, match="terminal"):
        review.record_source_trace(dsession, cand.id, source=w.official.key,
                                   url=w.url("/products/lara"), by="robert")


def test_promotion_still_requires_its_other_gates(dsession):
    w = World(dsession)
    # P1: a traced POSSIBLE_DUPLICATE is not promotable.
    w.candidate("/product/x1-reservation", "X1")
    dup = w.candidate("/products/x1", "X1")
    review.record_source_trace(dsession, dup.id, source=w.official.key,
                               url=w.url("/products/x1"), by="robert")
    assert dup.status == "POSSIBLE_DUPLICATE"
    assert any(g.startswith("P1") for g in check_gates(dsession, dup))
    # P4: conflicting claims block even a traced candidate.
    conflicted = w.candidate("/products/y1", "Y1")
    for value in ("20", "25"):
        conflicted.claims.append(CandidateClaim(field_key="payload_kg", claimed_value=value,
                                                discovery_source_id=w.official.id))
    dsession.flush()
    review.record_source_trace(dsession, conflicted.id, source=w.official.key,
                               url=w.url("/products/y1"), by="robert")
    assert conflicted.status == "CONFLICT"
    assert any(g.startswith("P4") for g in check_gates(dsession, conflicted))
    # P8: a READY candidate still needs an attributed human to promote it.
    first = w.candidate("/products/z1", "Z1")
    review.record_source_trace(dsession, first.id, source=w.official.key,
                               url=w.url("/products/z1"), by="robert")
    assert first.status == "READY_FOR_PROMOTION" and check_gates(dsession, first) == []
    before = canonical(dsession)
    with pytest.raises(PromotionError):
        promote(dsession, first, approved_by="")
    assert canonical(dsession) == before and first.promoted_robot_id is None


@contextmanager
def _shared(session):
    yield session


def test_cli_trace(dsession, monkeypatch, capsys):
    dsession.commit = dsession.flush
    monkeypatch.setattr(db_session, "SessionLocal", lambda: _shared(dsession))
    w = World(dsession)
    cand = w.candidate("/products/mipa", "MiPA")
    argv = ["review", "trace", str(cand.id), "--source", w.official.key,
            "--url", w.url("/products/mipa"), "--by", "robert"]
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "TRACE RECORDED" in out and "not promoted" in out
    assert cli.main(argv) == 0
    assert "TRACE ALREADY RECORDED" in capsys.readouterr().out
    assert cli.main(["review", "trace", str(cand.id), "--source", w.official.key,
                     "--url", "https://other.example/products/mipa", "--by", "robert"]) == 1
    with pytest.raises(SystemExit):
        cli.main(["review", "trace", str(cand.id), "--source", w.official.key, "--by", "r"])
