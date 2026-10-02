"""G2-2 governed proposal review (DR-A5 sections 5, 9, 16), offline PostgreSQL.

Every test runs in a transaction that is rolled back. Proves the review layer appends
human decisions and nothing else, and that supersession, staleness and the ACCEPT guards
hold and fail closed.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_claim_proposal_persistence import (
    BODY,
    NEW_PRICE,
    OLD_PRICE,
    PAGE,
    World,
    replace_cell,
)
from test_claim_proposal_persistence import dsession as dsession  # noqa: F401 (fixture)

from app.cli import discovery as cli
from app.models import DiscoveryClaimProposal, DiscoveryProposalDecision
from app.models.robot import Robot
from app.services.discovery import DiscoveryError
from app.services.discovery import proposal_review as pr
from app.services.discovery.fingerprint import fingerprint

pytestmark = pytest.mark.usefixtures("no_external_network")
WHO, WHY = "Robert Konecny", "owner review"


def prop(session, w, kind, edition=None):
    return session.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug, DiscoveryClaimProposal.kind == kind,
        DiscoveryClaimProposal.edition == edition)).one()


def seeded(session):
    w = World(session)
    w.ingest(w.page())
    return w


def state_of(session, p):
    [st] = pr.derive_states(session, [p])
    return st


def all_choices(p, value="a human's explicit answer"):
    return {pr.question_key(i): value for i in range(1, len(p.review_questions) + 1)}


def tables_changed(session, w, fn):
    tables = ("robot", "manufacturer", "evidence_source", "specification", "pricing_offer",
              "availability_offer", "robot_variant", "candidate_claim", "discovery_candidate",
              "promotion_audit", "candidate_identity_decision", "discovery_claim_proposal",
              "discovery_proposal_observation")

    def snap():
        return {t: session.execute(text(
            f"SELECT count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) "
            f"FROM {t} x")).one() for t in tables}
    before = snap()
    fn()
    assert snap() == before


# ------------------------------------------------------------------ states ---


def test_a_freshly_ingested_proposal_is_current_and_acceptable(dsession):
    w = seeded(dsession)
    states = pr.derive_states(dsession, list(dsession.scalars(select(DiscoveryClaimProposal))))
    mine = [s for s in states if s.proposal.robot_slug == w.slug]
    assert mine and all(s.state == pr.CURRENT and s.acceptable for s in mine)


def test_supersession_is_derived_and_the_superseded_cannot_be_accepted(dsession):
    w = seeded(dsession)
    old = prop(dsession, w, "PRICE_ESTIMATE", "Standard")
    changed = replace_cell(PAGE, OLD_PRICE, NEW_PRICE).encode("utf-8")
    w.ingest(w.page(changed, retrieved_at=datetime(2026, 9, 27, tzinfo=UTC)), changed)
    new = next(p for p in dsession.scalars(select(DiscoveryClaimProposal).where(
        DiscoveryClaimProposal.robot_slug == w.slug,
        DiscoveryClaimProposal.kind == "PRICE_ESTIMATE",
        DiscoveryClaimProposal.edition == "Standard")) if p.id != old.id)
    assert state_of(dsession, old).state == pr.SUPERSEDED
    assert state_of(dsession, new).state == pr.CURRENT
    with pytest.raises(DiscoveryError, match="SUPERSEDED"):
        pr.decide(dsession, str(old.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
                  choices=all_choices(old))
    # history stays: a decision on the superseded proposal can still be recorded and is kept
    row, created = pr.decide(dsession, str(old.id), pr.REJECT, decided_by=WHO, rationale=WHY)
    assert created and state_of(dsession, old).effective.id == row.id
    assert state_of(dsession, old).state == pr.SUPERSEDED


def _expect_stale(session, w, needle):
    p = prop(session, w, "VARIANT", "Standard")
    st = state_of(session, p)
    assert st.state == pr.STALE and not st.acceptable
    assert any(needle in r for r in st.stale_reasons), st.stale_reasons
    with pytest.raises(DiscoveryError, match="STALE"):
        pr.decide(session, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
                  choices=all_choices(p))
    return p


def test_changed_page_content_that_was_not_re_extracted_makes_it_stale(dsession):
    w = seeded(dsession)
    w.page(b"<html>different</html>", retrieved_at=datetime(2026, 9, 27, tzinfo=UTC))
    _expect_stale(dsession, w, "not content this proposal was sighted on")


def test_re_extracting_the_changed_page_restores_currentness(dsession):
    w = seeded(dsession)
    cosmetic = BODY + b"<!-- cosmetic -->"
    page = w.page(cosmetic, retrieved_at=datetime(2026, 9, 27, tzinfo=UTC),
                  content_hash="b" * 64)       # hash differs, extraction identical
    p = prop(dsession, w, "VARIANT", "Standard")
    assert state_of(dsession, p).stale
    # Provenance rules are not weakened: a body that does not match the hash is refused.
    with pytest.raises(DiscoveryError, match="content_hash"):
        w.ingest(page, cosmetic)
    ok = w.page(cosmetic, retrieved_at=datetime(2026, 9, 28, tzinfo=UTC))
    w.ingest(ok, cosmetic)
    assert state_of(dsession, p).state == pr.CURRENT


def test_a_not_modified_answer_keeps_currentness_but_adds_no_content(dsession):
    w = seeded(dsession)
    w.page(BODY, retrieved_at=datetime(2026, 9, 28, tzinfo=UTC), outcome="NOT_MODIFIED",
           http_status=304, content_hash=None)
    assert state_of(dsession, prop(dsession, w, "VARIANT", "Standard")).state == pr.CURRENT


@pytest.mark.parametrize("kw,needle", [
    ({"outcome": "ERROR", "http_status": None, "content_hash": None}, "did not retrieve"),
    ({"outcome": "BLOCKED_BY_ROBOTS", "http_status": None, "content_hash": None},
     "did not retrieve"),
    ({"outcome": "FETCHED", "http_status": 404, "content_hash": None}, "HTTP 404"),
    ({"outcome": "FETCHED", "http_status": 410, "content_hash": None}, "HTTP 410"),
])
def test_an_unretrievable_or_removed_source_page_makes_it_stale(dsession, kw, needle):
    w = seeded(dsession)
    w.page(BODY, retrieved_at=datetime(2026, 9, 27, tzinfo=UTC), **kw)
    _expect_stale(dsession, w, needle)


def test_a_retired_extractor_makes_its_proposals_stale(dsession, monkeypatch):
    w = seeded(dsession)
    monkeypatch.setattr(pr, "LIVE_EXTRACTORS", frozenset())
    _expect_stale(dsession, w, "not a live extractor")


def test_a_failed_identity_gate_makes_proposals_stale(dsession):
    w = seeded(dsession)
    dsession.execute(text("UPDATE robot SET name = 'Something Else' WHERE id = :i"),
                     {"i": w.robot.id})
    _expect_stale(dsession, w, "identity gate")


def test_missing_data_is_never_read_as_current(dsession):
    """A proposal whose source page has no observation at all is stale, not current."""
    w = seeded(dsession)
    dsession.execute(text("SET LOCAL session_replication_role = replica"))   # test-only
    dsession.execute(text(
        "UPDATE discovery_claim_proposal SET source_url = 'https://neura-robotics.com/other' "
        "WHERE robot_slug = :s"), {"s": w.slug})
    dsession.execute(text("SET LOCAL session_replication_role = origin"))
    dsession.expire_all()
    st = state_of(dsession, prop(dsession, w, "VARIANT", "Standard"))
    assert st.stale and any("no observation" in r for r in st.stale_reasons)


# ------------------------------------------------------------------ decide ---


@pytest.mark.parametrize("decision", [pr.REJECT, pr.DEFER])
def test_reject_and_defer_need_a_named_human_and_a_rationale_and_change_nothing_else(
        dsession, decision):
    w = seeded(dsession)
    p = prop(dsession, w, "PRICE_ESTIMATE", "Pro")
    for by, why in (("", WHY), ("  ", WHY), (WHO, ""), (WHO, "   ")):
        with pytest.raises(DiscoveryError):
            pr.decide(dsession, str(p.id), decision, decided_by=by, rationale=why)
    tables_changed(dsession, w, lambda: pr.decide(
        dsession, str(p.id), decision, decided_by=WHO, rationale=WHY))
    st = state_of(dsession, p)
    assert st.effective.decision == decision and st.effective.decided_by == WHO
    assert dsession.scalar(select(Robot.is_published).where(Robot.id == w.robot.id)) is False


def test_accept_needs_every_review_question_resolved(dsession):
    w = seeded(dsession)
    p = prop(dsession, w, "PRICE_ESTIMATE", "Standard")
    assert len(p.review_questions) >= 2
    partial = {pr.question_key(1): "answered"}
    with pytest.raises(DiscoveryError, match="unresolved"):
        pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY, choices=partial)
    with pytest.raises(DiscoveryError, match="unresolved"):
        pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY)
    blank = {**all_choices(p), "q1": "  "}
    with pytest.raises(DiscoveryError, match="blank"):
        pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY, choices=blank)
    with pytest.raises(DiscoveryError, match="unknown"):
        pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
                  choices={**all_choices(p), "colour": "red"})
    assert not dsession.scalars(select(DiscoveryProposalDecision)).all()
    row, created = pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
                             choices=all_choices(p))
    assert created and row.decision == pr.ACCEPT
    assert set(row.resolved_choices) == {pr.question_key(i) for i in
                                         range(1, len(p.review_questions) + 1)}


def test_no_catalogue_home_is_valid_only_when_a_human_selects_it(dsession):
    w = seeded(dsession)
    p = prop(dsession, w, "RESERVATION_FEE", "Pro")
    assert p.representability == "UNREPRESENTABLE"
    with pytest.raises(DiscoveryError, match="no catalogue home"):
        pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
                  choices=all_choices(p))
    with pytest.raises(DiscoveryError, match="may only be"):
        pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
                  choices={**all_choices(p), pr.HOME_KEY: "pricing_offer.note"})
    choices = {**all_choices(p), pr.HOME_KEY: pr.NO_CATALOGUE_HOME}
    tables_changed(dsession, w, lambda: pr.decide(
        dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY, choices=choices))
    assert state_of(dsession, p).effective.resolved_choices[pr.HOME_KEY] == pr.NO_CATALOGUE_HOME


def test_repeating_the_effective_decision_is_a_no_op_and_a_reversal_appends(dsession):
    w = seeded(dsession)
    p = prop(dsession, w, "DESIGN_CAVEAT")
    first, created = pr.decide(dsession, str(p.id), pr.DEFER, decided_by=WHO, rationale=WHY)
    again, created2 = pr.decide(dsession, str(p.id), pr.DEFER, decided_by="Someone Else",
                                rationale="a different rationale")
    assert created and not created2 and again.id == first.id
    assert len(pr.decision_history(dsession, p)) == 1
    # a different resolved choice is not "identical": it appends
    third, created3 = pr.decide(dsession, str(p.id), pr.DEFER, decided_by=WHO, rationale=WHY,
                                choices={pr.HOME_KEY: pr.NO_CATALOGUE_HOME})
    assert created3 and third.decision_seq > first.decision_seq
    # genuine reversal
    rev, created4 = pr.decide(dsession, str(p.id), pr.REJECT, decided_by=WHO, rationale="no")
    assert created4
    history = pr.decision_history(dsession, p)
    assert [h.decision for h in history] == ["DEFER", "DEFER", "REJECT"]
    assert state_of(dsession, p).effective.id == rev.id
    # the first row is untouched, and the database still refuses to change it
    assert history[0].id == first.id and history[0].rationale == WHY
    sp = dsession.begin_nested()
    with pytest.raises(DBAPIError):
        dsession.execute(text("UPDATE discovery_proposal_decision SET rationale = 'x'"))
    sp.rollback()


def test_resolved_choices_serialize_deterministically(dsession):
    a = pr.canonical_choices({"q2": " b ", "q1": "a"})
    b = pr.canonical_choices({"q1": "a", "q2": "b"})
    assert a == b and pr.serialize_choices(a) == '{"q1":"a","q2":"b"}'
    with pytest.raises(DiscoveryError):
        pr.canonical_choices({"q1": ""})
    with pytest.raises(DiscoveryError):
        pr.canonical_choices({" ": "x"})


def test_reversal_and_repeat_compare_choices(dsession):
    w = seeded(dsession)
    p = prop(dsession, w, "PRICE_ESTIMATE", "Pro")
    choices = all_choices(p)
    r1, c1 = pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
                       choices=choices)
    r2, c2 = pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
                       choices=dict(reversed(list(choices.items()))))
    assert c1 and not c2 and r1.id == r2.id
    _, c3 = pr.decide(dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
                      choices={**choices, "q1": "a different answer"})
    assert c3


def test_a_decision_alone_creates_no_accepted_claim_and_writes_only_a_decision(dsession):
    w = seeded(dsession)
    p = prop(dsession, w, "DESIGN_CAVEAT")
    tables_changed(dsession, w, lambda: pr.decide(
        dsession, str(p.id), pr.ACCEPT, decided_by=WHO, rationale=WHY,
        choices={**all_choices(p), pr.HOME_KEY: pr.NO_CATALOGUE_HOME}))
    assert dsession.scalar(text("SELECT count(*) FROM accepted_claim")) == 0
    assert dsession.scalar(text("SELECT count(*) FROM catalogue_write_audit")) == 0


# ----------------------------------------------------------- list and show ---


def test_list_defaults_to_proposals_needing_a_human_and_filters(dsession):
    w = seeded(dsession)
    listed = pr.list_proposals(dsession, robot_slug=w.slug)
    assert len(listed) == len(pr.list_proposals(dsession, robot_slug=w.slug, include_all=True))
    rejected = prop(dsession, w, "DESIGN_CAVEAT")
    deferred = prop(dsession, w, "RESERVATION_TERMS")
    pr.decide(dsession, str(rejected.id), pr.REJECT, decided_by=WHO, rationale=WHY)
    pr.decide(dsession, str(deferred.id), pr.DEFER, decided_by=WHO, rationale=WHY)
    ids = {s.proposal.id for s in pr.list_proposals(dsession, robot_slug=w.slug)}
    assert rejected.id not in ids and deferred.id in ids       # DEFER still needs a human
    assert rejected.id in {s.proposal.id for s in pr.list_proposals(
        dsession, robot_slug=w.slug, include_all=True)}
    pro = pr.list_proposals(dsession, robot_slug=w.slug, edition="Pro", include_all=True)
    assert pro and {s.proposal.edition for s in pro} == {"Pro"}
    none = pr.list_proposals(dsession, robot_slug=w.slug, edition="none", include_all=True)
    assert none and {s.proposal.edition for s in none} == {None}
    only = pr.list_proposals(dsession, robot_slug=w.slug, kind="price_estimate", include_all=True)
    assert {s.proposal.kind for s in only} == {"PRICE_ESTIMATE"}
    assert pr.list_proposals(dsession, source_key=w.source.key, include_all=True)
    assert not pr.list_proposals(dsession, source_key="no-such-source", include_all=True)


def test_show_carries_everything_a_reviewer_needs(dsession):
    w = seeded(dsession)
    p = prop(dsession, w, "PRICE_ESTIMATE", "Standard")
    pr.decide(dsession, str(p.id), pr.DEFER, decided_by=WHO, rationale="waiting on the owner",
              choices={pr.HOME_KEY: pr.NO_CATALOGUE_HOME})
    out = "\n".join(pr.render_show(dsession, p))
    for needle in (w.slug, "PRICE_ESTIMATE", "Standard", p.value, "19,999", p.source_url,
                   p.evidence_excerpt, p.evidence_locator, mini_key(), p.digest,
                   str(p.origin_fetched_page_id), p.representability, "gap", "q1:", "CURRENT",
                   "sightings (1)", "DEFER", "waiting on the owner", pr.NO_CATALOGUE_HOME):
        assert needle in out, needle


def mini_key():
    from app.services.discovery.sources import neura_mini_proposals as mini
    return f"{mini.EXTRACTOR_KEY}@{mini.EXTRACTOR_VERSION}"


def test_proposals_resolve_by_unique_prefix_only(dsession):
    w = seeded(dsession)
    p = prop(dsession, w, "VARIANT", "Pro")
    assert pr.resolve_proposal(dsession, str(p.id)).id == p.id
    assert pr.resolve_proposal(dsession, p.digest[:16]).id == p.id
    with pytest.raises(DiscoveryError):
        pr.resolve_proposal(dsession, "abc")
    with pytest.raises(DiscoveryError):
        pr.resolve_proposal(dsession, "ffffffffffffffff")


# --------------------------------------------------------------------- CLI ---


def _ns(**kw):
    base = {"choice": None, "no_catalogue_home": False}
    return argparse.Namespace(**{**base, **kw})


def test_cli_review_flow_prints_and_records(dsession, capsys):
    w = seeded(dsession)
    p = prop(dsession, w, "DESIGN_CAVEAT")
    cli._proposal_review(dsession, _ns(action="list", robot_slug=w.slug, source=None,
                                       edition=None, kind=None, all=False))
    assert "needing a human" in capsys.readouterr().out
    cli._proposal_review(dsession, _ns(action="show", proposal=str(p.id)))
    assert p.digest in capsys.readouterr().out
    cli._proposal_review(dsession, _ns(action="defer", proposal=p.digest[:12], by=WHO,
                                       reason=WHY))
    assert "RECORDED DEFER" in capsys.readouterr().out
    cli._proposal_review(dsession, _ns(action="defer", proposal=p.digest[:12], by=WHO,
                                       reason=WHY))
    assert "no-op" in capsys.readouterr().out
    cli._proposal_review(dsession, _ns(
        action="accept", proposal=str(p.id), by=WHO, reason=WHY, no_catalogue_home=True,
        choice=[f"{pr.question_key(i)}=answered" for i in range(1, len(p.review_questions) + 1)]))
    assert "no accepted claim" in capsys.readouterr().out
    with pytest.raises(DiscoveryError, match="KEY=VALUE"):
        cli._parse_choices(["nonsense"])


def test_cli_refuses_a_decision_without_attribution_or_rationale():
    for argv in (["proposals", "reject", "abcdef12", "--reason", "x"],
                 ["proposals", "reject", "abcdef12", "--by", "x"],
                 ["proposals", "accept", "abcdef12", "--by", " ", "--reason", "x"]):
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        assert exc.value.code == 2


def test_stage_a_to_f_modules_do_not_reference_review():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "discovery"
    for rel in ("observe.py", "adapter_run.py", "live_adapter.py", "promotion.py",
                "sources/neura_robotics.py", "review.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "proposal_review" not in src and "proposals import" not in src, rel
    assert fingerprint(b"x", "text/plain") and timedelta(0) == timedelta(0)
