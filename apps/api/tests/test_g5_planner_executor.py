"""G5-4: the G5-3 planner is the single selection authority for Lane B; the G5-2 executor consumes
its output and re-checks every target at execution time. Owner decisions of 2026-10-04.
"""
from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from test_discovery_enrichment_fetch import (
    DATASHEET,
    MAIN,
    PX,
    Lane,
    datasheet,
    state,
)
from test_discovery_enrichment_fetch import dsession as dsession  # noqa: F401 (fixture)

from app.models.discovery import DiscoveryCandidate, DiscoverySource
from app.services.discovery import enrichment as en
from app.services.discovery import enrichment_fetch as ef
from app.services.discovery import enrichment_plan as ep
from app.services.discovery import observe as ob

pytestmark = pytest.mark.usefixtures("no_external_network")


@pytest.fixture
def lane(dsession, tmp_path) -> Lane:  # noqa: F811
    return Lane(dsession, tmp_path)


def doc_target(lane: Lane, url: str = DATASHEET, **over) -> ep.Target:
    t = lane.plans()[lane.docs.key].planned[0]
    return dataclasses.replace(t, url=url, **over)


def plan_with(lane: Lane, *targets: ep.Target) -> dict[str, ep.SourcePlan]:
    plans = lane.plans()
    base = plans[lane.docs.key]
    plans[lane.docs.key] = dataclasses.replace(base, planned=tuple(targets))
    return plans


# ------------------------------------------------------------- one selection policy


def test_the_executor_has_no_selection_policy_of_its_own():
    src = inspect.getsource(ef.run_lane_b)
    for old in ("row.targets", "QueueRow", "t.due", "priority(", "gap_profile(", "build_queue("):
        assert old not in src
    assert "plans" in inspect.signature(ef.run_lane_b).parameters
    assert "rows" not in inspect.signature(ef.run_lane_b).parameters


def test_what_the_planner_plans_is_exactly_what_the_executor_fetches(lane):
    plans = lane.plans()
    planned = {u for pl in plans.values() for u in (t.url for t in pl.planned)}
    res = lane.run(plans=plans)
    fetched_urls = {u for r in res.runs if r.status == ef.FETCHED for u in r.urls}
    assert fetched_urls == {DATASHEET} <= planned
    assert res.targets_planned == 2 and res.targets_fetched == 1       # product page is Lane A's
    assert res.deferred_radar == [MAIN + "/product/4ne1-mini"]
    assert [h for h, _ in lane.net.fetched()] == ["neurarobotics.px.media"]


def test_the_contract_carries_everything_needed_to_prove_the_target(lane):
    t = lane.plans()[lane.docs.key].planned[0]
    d = t.as_dict()
    assert d["source"] == lane.docs.key and d["robot"] == lane.w.slug
    assert d["origin"] == "CATALOGUE_ENRICHMENT" and d["target"] == DATASHEET
    assert d["target_type"] == "DOCUMENT" and d["priority"] == en.HIGH and d["reasons"]
    assert d["eligibility"] == "ALLOWED" and d["source_due"] is True
    assert "previous_observation" in d and "next_due" in d and "last_observed" in d
    assert ep.contract_problems(t) == []


# ------------------------------------------------------------- execution-time re-check


@pytest.mark.parametrize("change,needle", [
    (dict(origin="NEW_MODEL"), "origin"),
    (dict(decision=ep.NOT_DUE), "decision"),
    (dict(eligibility="NEEDS_SOURCE_APPROVAL"), "eligibility"),
    (dict(reason_codes=()), "reason code"),
    (dict(priority="URGENT"), "priority"),
    (dict(target_type="PDF"), "target type"),
    (dict(robot=""), "robot"),
])
def test_a_malformed_or_fabricated_target_is_refused_and_nothing_is_requested(lane, change,
                                                                              needle):
    res = lane.run(plans=plan_with(lane, doc_target(lane, **change)))
    assert lane.net.requests == [] and lane.runs() == []
    assert res.refused_targets and any(needle in p for p in res.refused_targets[0]["problems"])
    assert next(r for r in res.runs if r.key == lane.docs.key).status == ef.REFUSED
    assert res.attention is True                         # a refused target needs a human


def test_a_target_outside_the_source_boundary_is_refused_even_if_the_plan_says_allowed(lane):
    for url in (PX + "/private/x.pdf", "https://evil.px.media/plk/x.pdf",
                "https://elsewhere.example/plk/x.pdf"):
        res = lane.run(plans=plan_with(lane, doc_target(lane, url=url)))
        assert res.refused_targets and "boundary" in " ".join(res.refused_targets[0]["problems"])
    assert lane.net.requests == []


def test_a_target_for_an_unknown_robot_is_refused_lane_b_never_creates_identities(lane):
    res = lane.run(plans=plan_with(lane, doc_target(lane, robot="no-such-robot")))
    assert any("not a catalogue robot" in p for p in res.refused_targets[0]["problems"])
    assert lane.net.requests == []


def test_a_target_attributed_to_the_wrong_source_is_refused(lane):
    res = lane.run(plans=plan_with(lane, doc_target(lane, source="neura-robotics-official")))
    assert any("belongs to source" in p for p in res.refused_targets[0]["problems"])
    assert lane.net.requests == []


def test_a_source_disabled_after_planning_refuses_its_targets(lane):
    plans = lane.plans()
    lane.docs.is_enabled = False
    res = lane.run(plans=plans)
    assert lane.net.requests == [] and any(
        "no longer eligible" in " ".join(r["problems"]) for r in res.refused_targets)


# ------------------------------------------------------------- bound and cadence


def test_the_bound_is_eight_and_deferred_targets_are_replanned_on_a_later_due_cycle(lane):
    assert ep.DEFAULT_BOUND == 8 and ef.MAX_TARGETS_PER_SOURCE == 8
    extra = [PX + f"/plk/Jj/extra-{i}.pdf" for i in range(3)]
    for u in extra:
        lane.net.put(u, datasheet(), "application/pdf")
    urls = [("specification", u) for u in extra]
    plans = lane.plans(extra_urls=urls, bound=2)
    plan = plans[lane.docs.key]
    assert len(plan.planned) == 2
    deferred = [t.url for t in plan.skipped if t.decision == ep.DEFERRED_BY_BOUND]
    assert len(deferred) == 2
    res = lane.run(plans=plans)
    assert res.targets_fetched == 2 and sorted(res.deferred_by_bound) == sorted(deferred)
    lane.advance(8)                                      # the source is due again
    again = lane.plans(extra_urls=urls, bound=2)[lane.docs.key]
    assert {t.url for t in again.planned} & set(deferred), "deferred targets must come back"


def test_the_document_source_cadence_is_seven_days_and_authoritative(lane):
    assert lane.docs.observation_interval_hours == 168
    lane.run()
    first = len(lane.net.requests)
    for days, due in ((3, False), (3, False), (2, True)):         # 3d, 6d, 8d since the run
        lane.advance(days)
        plan = lane.plans()[lane.docs.key]
        assert plan.source_due is due and bool(plan.planned) is due
    assert len(lane.net.requests) == first                        # planning fetched nothing


def test_the_executor_does_not_hard_code_any_cadence():
    src = inspect.getsource(ef)
    assert "168" not in src and "hours=" not in src


# ------------------------------------------------------------- quiet when nothing changed


def test_an_unchanged_pdf_becomes_silent_after_the_first_check(lane):
    first = lane.run()
    assert first.proposals_created == 11 and first.attention
    props = len(lane.proposals())
    lane.advance(8)
    second = lane.run()
    assert second.proposals_created == 0 and second.pages["unchanged"] == 1
    assert second.attention is False and len(lane.proposals()) == props
    lane.advance(8)
    third = lane.run()
    assert third.proposals_created == 0 and third.attention is False


def test_a_changed_pdf_creates_only_the_changed_enrichment_proposal(lane):
    lane.run()
    lane.advance(8)
    lane.net.put(DATASHEET, datasheet("133"), "application/pdf")
    res = lane.run()
    assert res.pages["changed"] == 1 and res.proposals_created == 1
    assert {p.origin for p in lane.proposals()} == {"CATALOGUE_ENRICHMENT"}


def test_remaining_unknown_fields_alone_never_alert(lane):
    lane.run()
    lane.advance(8)
    quiet = lane.run()
    assert quiet.attention is False and quiet.proposals_created == 0 and quiet.refused_targets == []


# ------------------------------------------------------------- identity and publication


def test_a_known_robot_never_becomes_a_candidate_and_publication_is_untouched(lane):
    before = state(lane.session)
    published = lane.session.scalar(text("SELECT count(*) FROM robot WHERE is_published"))
    cands = lane.session.scalar(select(func.count()).select_from(DiscoveryCandidate))
    lane.run()
    lane.advance(8)
    lane.net.put(DATASHEET, datasheet("133"), "application/pdf")
    lane.run()
    assert lane.session.scalar(select(func.count()).select_from(DiscoveryCandidate)) == cands
    assert lane.session.scalar(text("SELECT count(*) FROM robot WHERE is_published")) == published
    after = state(lane.session)
    assert after["robot"] == before["robot"]
    for t in ("discovery_proposal_decision", "accepted_claim", "claim_retraction",
              "catalogue_write_audit", "evidence_source", "specification"):
        assert after[t] == before[t], t                  # nothing decided, claimed or written


# ------------------------------------------------------------- Lane A is not regressed


def doc_source(**over) -> DiscoverySource:
    base = dict(key="neura-documents-official", name="docs", source_class="OFFICIAL_DOCUMENT",
                is_enabled=True, observation_interval_hours=168)
    base.update(over)
    return DiscoverySource(**base)


def test_a_cadenced_document_source_is_not_a_radar_problem():
    now = datetime(2026, 10, 5, tzinfo=UTC)
    status, detail, run = ob.assess(None, doc_source(), None, now, False)
    assert status == ob.LANE_B_OWNED and run is None and "Lane B" in detail
    assert ob.LANE_B_OWNED not in ob.ATTENTION
    assert not ob.SourceObservation("neura-documents-official", status, detail).attention
    # any other adapter-less scheduled source is still a finding for a human
    other = ob.assess(None, doc_source(key="mystery-source"), None, now, False)
    assert other[0] == ob.NO_ADAPTER and ob.NO_ADAPTER in ob.ATTENTION


def test_lane_a_report_sections_stay_separate_and_ordered():
    cycle = ob.CycleResult(started_at=datetime(2026, 10, 5, tzinfo=UTC), plan_only=False)
    out = "\n".join(cycle.lines())
    assert out.index("NEW MODEL RADAR") < out.index("CATALOGUE ENRICHMENT")


def test_the_cycle_report_lists_the_required_enrichment_counters(lane):
    res = lane.run()
    text_ = "\n".join(res.lines())
    for needle in ("robots considered=", "targets planned=", "fetched=", "deferred by bound=",
                   "source review required=", "technical proposals created=",
                   "maturity proposals created=", "datasheets/docs discovered="):
        assert needle in text_, needle
    d = res.as_dict()
    for key in ("robots_considered", "targets_planned", "targets_fetched",
                "source_review_required", "deferred_by_bound", "maturity_proposals_created",
                "documents_discovered", "refused_targets"):
        assert key in d, key
    assert d["writes_catalogue"] is False and d["writes_claims"] is False


def test_the_planner_alone_decides_the_window(lane):
    """No second algorithm: the band interval lives in the planner and nowhere in the executor."""
    assert "BAND_INTERVAL" in inspect.getsource(ep)
    window = inspect.getsource(ef.run_lane_b)
    assert "BAND_INTERVAL" not in window
    assert timedelta(days=7) == en.BAND_INTERVAL[en.HIGH]
