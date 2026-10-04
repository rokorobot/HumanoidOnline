"""G5-3: the Lane B target-selection layer (enrichment target profiles + bounded, source-centric
fetch plan). Pure and read-only; pins the owner decisions of 2026-10-04.
"""
from __future__ import annotations

import inspect
import re
from datetime import timedelta
from pathlib import Path

from test_discovery_enrichment import (
    DATASHEET,
    HOST,
    NOW,
    PX,
    inp,
    neura_main,
    px_docs,
    rich,
    source,
)
from test_g4_3_readiness import sparse

from app.services import readiness as rd
from app.services.discovery import enrichment as en
from app.services.discovery import enrichment_plan as ep

MINI_PRODUCT = "https://neura-robotics.com/product/4ne1-mini-reservation"


def cadence(src, *, due: bool, hours: int = 48):
    """Give a source a cadence that is due (or not due) at NOW."""
    src.observation_interval_hours = hours
    src.last_crawled_at = NOW - timedelta(hours=hours + 1 if due else 1)
    return src


def pin(robot_inp, claim_urls=()):
    return ep.PlanInput(robot_inp, tuple(claim_urls))


def plan(inputs, sources, key, *, states=None, bound=8):
    return ep.plan_manufacturer(inputs, sources, states or {}, NOW, source_key=key, bound=bound)


def maker_sparse(slug="new-bot", **over):
    rec = sparse(slug=slug, name=slug, manufacturer_slug="maker-x", is_published=False,
                 commercial_status="UNKNOWN", official_url=HOST + f"robots/{slug}", **over)
    return pin(inp(rec, commercial_days=None, spec_days=None, year=2026, docs=False))


def maker_rich(slug="rich"):
    return pin(inp(rich(slug=slug, official_url=HOST + f"robots/{slug}")))


# ---------------------------------------------------------------------------- profile + codes


def test_a_sparse_recent_robot_gets_the_expected_reason_codes_and_high_priority():
    prof = ep.build_profile(maker_sparse(), NOW, {})
    assert prof.priority == en.HIGH and prof.robot_slug == "new-bot"
    assert {ep.COMMERCIAL_STATUS_UNKNOWN, ep.PRICE_UNKNOWN, ep.AVAILABILITY_UNKNOWN,
            ep.BUYER_FIELDS_MISSING} <= set(prof.reason_codes)
    assert prof.reason_codes == tuple(c for c in ep.REASON_CODES if c in prof.reason_codes)
    assert prof.coverage_band in ("LOW", "PARTIAL") and prof.is_published is False
    assert "payload" in prof.missing_high_value and prof.official_url.endswith("/new-bot")
    d = prof.as_dict()
    assert d["origin"] == "CATALOGUE_ENRICHMENT" and d["reason_codes"] == list(prof.reason_codes)


def test_a_stable_populated_robot_has_no_reason_code_and_low_priority():
    prof = ep.build_profile(maker_rich(), NOW, {})
    assert prof.reason_codes == () and prof.priority == en.LOW


def test_aging_commercial_evidence_is_a_reason_not_a_defect():
    old = pin(inp(rich(official_url=HOST + "robots/rich"), commercial_days=200))
    prof = ep.build_profile(old, NOW, {})
    assert ep.COMMERCIAL_EVIDENCE_AGING in prof.reason_codes
    assert prof.commercial_evidence_age_days == 200 and prof.commercial_status == "COMMERCIAL"


def test_a_changed_official_page_is_a_reason_and_raises_priority_to_high():
    url = en.normalize_url(HOST + "robots/rich") if hasattr(en, "normalize_url") else (
        ep.normalize_url(HOST + "robots/rich"))
    st = {url: ep.UrlState(NOW - timedelta(days=2), "h2", "h1")}
    prof = ep.build_profile(maker_rich(), NOW, st)
    assert ep.SOURCE_CHANGED in prof.reason_codes and prof.priority == en.HIGH
    stale = {url: ep.UrlState(NOW - timedelta(days=90), "h2", "h1")}
    assert ep.SOURCE_CHANGED not in ep.build_profile(maker_rich(), NOW, stale).reason_codes


def test_a_pending_proposal_is_a_reason_code():
    rec = rich(not_yet_reviewed=2, official_url=HOST + "robots/rich")
    assert ep.PENDING_HIGH_VALUE_PROPOSAL in ep.build_profile(pin(inp(rec)), NOW, {}).reason_codes


def test_a_known_unprocessed_document_link_is_new_document_possible_and_high():
    rec = rich(official_url=HOST + "robots/rich")
    doc = pin(inp(rec, urls=[("specification", HOST + "robots/rich/datasheet.pdf")]))
    prof = ep.build_profile(doc, NOW, {})
    assert ep.NEW_DOCUMENT_POSSIBLE in prof.reason_codes and prof.priority == en.HIGH
    seen = {ep.normalize_url(HOST + "robots/rich/datasheet.pdf"): ep.UrlState(NOW, "h", None)}
    assert ep.NEW_DOCUMENT_POSSIBLE not in ep.build_profile(doc, NOW, seen).reason_codes


# ---------------------------------------------------------------------------- URL derivation


def test_urls_come_from_official_evidence_and_accepted_claims_deduplicated():
    rec = rich(official_url=HOST + "robots/rich")
    robot = inp(rec, urls=[("commercial_status", HOST + "robots/rich/"),
                           ("specification", HOST + "robots/rich#specs")])
    p = ep.plan_manufacturer([pin(robot, [HOST + "robots/rich?utm=1", HOST + "robots/other"])],
                             [cadence(source(), due=True)], {}, NOW, source_key="maker-x-official")
    urls = [t.url for t in (*p.planned, *p.skipped)]
    assert len(urls) == len(set(urls))                    # deduplicated after normalization
    assert any(u.endswith("/robots/other") for u in urls)  # the accepted-claim URL is included


def test_a_url_outside_the_approved_boundary_is_reported_never_planned():
    rec = sparse(slug="a", manufacturer_slug="maker-x", official_url=HOST + "robots/a",
                 commercial_status="UNKNOWN")
    robot = inp(rec, urls=[("specification", HOST + "private/area"),
                           ("specification", "https://other-host.example/x")], commercial_days=None)
    p = plan([pin(robot)], [cadence(source(), due=True)], "maker-x-official")
    review = {t.url: t for t in p.skipped if t.decision == ep.SOURCE_REVIEW_REQUIRED}
    assert set(review) == {HOST + "private/area", "https://other-host.example/x"}
    assert all(t.eligibility == en.NEEDS_SOURCE_APPROVAL for t in review.values())
    assert [t.url for t in p.planned] == [HOST + "robots/a"]


def test_target_types_are_classified():
    assert ep._type_of("https://x.example/files/sheet.pdf", (),
                       document_source=False) == ep.DOCUMENT
    assert ep._type_of("https://x.example/news/launch", ("official_url",),
                       document_source=False) == ep.NEWS
    assert ep._type_of("https://x.example/robots/a", ("official_url",),
                       document_source=False) == ep.PRODUCT_PAGE
    assert ep._type_of("https://x.example/robots/a", (), document_source=False) == ep.OTHER
    assert ep._type_of("https://x.example/plk/a", (), document_source=True) == ep.DOCUMENT


# ---------------------------------------------------------------------------- the plan


def test_a_due_source_plans_a_sparse_robot_with_the_documented_output_shape():
    p = plan([maker_sparse()], [cadence(source(), due=True)], "maker-x-official")
    [t] = p.planned
    assert (t.source, t.robot, t.origin, t.priority) == (
        "maker-x-official", "new-bot", "CATALOGUE_ENRICHMENT", en.HIGH)
    assert t.target_type == ep.PRODUCT_PAGE and t.eligibility == "ALLOWED"
    assert t.decision == ep.PLANNED and t.last_observed is None and t.next_due is None
    text = "\n".join(ep.plan_lines(p))
    for needle in ("source: maker-x-official", "robot: new-bot", "origin: CATALOGUE_ENRICHMENT",
                   "priority: HIGH", "- COMMERCIAL_STATUS_UNKNOWN", "target_type: PRODUCT_PAGE",
                   "eligibility: ALLOWED", "last_observed: never", "next_due: now"):
        assert needle in text, needle


def test_a_source_that_is_not_due_plans_nothing_and_says_why():
    p = plan([maker_sparse()], [cadence(source(), due=False)], "maker-x-official")
    assert p.planned == () and [t.decision for t in p.skipped] == [ep.NOT_DUE]
    assert "next due" in p.skipped[0].detail and not p.source_due


def test_an_unscheduled_or_disabled_source_is_not_due():
    s = source()                       # no cadence at all
    assert plan([maker_sparse()], [s], "maker-x-official").planned == ()
    assert plan([maker_sparse()], [cadence(source(enabled=False), due=True)],
                "maker-x-official").planned == ()


def test_an_unchanged_url_inside_its_cadence_is_not_refetched_just_because_data_is_missing():
    url = ep.normalize_url(HOST + "robots/new-bot")
    seen = {url: ep.UrlState(NOW - timedelta(days=2), "h", "h")}        # unchanged
    p = plan([maker_sparse()], [cadence(source(), due=True)], "maker-x-official", states=seen)
    assert p.planned == () and [t.decision for t in p.skipped] == [ep.UNCHANGED_RECENTLY]
    assert p.skipped[0].next_due == NOW - timedelta(days=2) + en.BAND_INTERVAL[en.HIGH]
    old = {url: ep.UrlState(NOW - timedelta(days=30), "h", "h")}        # past its interval
    assert len(plan([maker_sparse()], [cadence(source(), due=True)], "maker-x-official",
                    states=old).planned) == 1


def test_a_changed_url_is_planned_even_inside_its_interval():
    url = ep.normalize_url(HOST + "robots/new-bot")
    changed = {url: ep.UrlState(NOW - timedelta(days=1), "h2", "h1")}
    p = plan([maker_sparse()], [cadence(source(), due=True)], "maker-x-official", states=changed)
    assert len(p.planned) == 1 and ep.SOURCE_CHANGED in p.planned[0].reason_codes


def test_a_robot_with_no_meaningful_gap_is_skipped_and_ranks_below_a_recent_sparse_robot():
    src = [cadence(source(), due=True)]
    p = plan([maker_rich("old-stable"), maker_sparse("new-bot")], src, "maker-x-official")
    assert [t.robot for t in p.planned] == ["new-bot"]
    assert {(t.robot, t.decision) for t in p.skipped} == {("old-stable", ep.NO_MEANINGFUL_GAP)}
    both = ep.build_profile(maker_rich(), NOW, {}), ep.build_profile(maker_sparse(), NOW, {})
    assert ep._PRIORITY_ORDER[both[1].priority] < ep._PRIORITY_ORDER[both[0].priority]


def test_the_plan_is_bounded_and_deferred_targets_are_reported():
    robots = [maker_sparse(f"bot-{i:02d}") for i in range(12)]
    p = plan(robots, [cadence(source(), due=True)], "maker-x-official", bound=3)
    assert len(p.planned) == 3
    assert sum(1 for t in p.skipped if t.decision == ep.DEFERRED_BY_BOUND) == 9
    assert [t.robot for t in p.planned] == ["bot-00", "bot-01", "bot-02"]     # deterministic


def test_the_plan_is_deterministic():
    robots = [maker_sparse(f"bot-{i}") for i in (3, 1, 2)]
    a = plan(robots, [cadence(source(), due=True)], "maker-x-official")
    b = plan(list(reversed(robots)), [cadence(source(), due=True)], "maker-x-official")
    assert a.as_dict() == b.as_dict()


# ---------------------------------------------------------------------------- NEURA / px.media


def _mini(**over):
    rec = rich(manufacturer_slug="neura-robotics", slug="4ne1-mini", official_url=MINI_PRODUCT,
               commercial_status="UNKNOWN", images=(), **over)
    robot = inp(rec, urls=[("specification", DATASHEET)], commercial_days=None, year=2026)
    return pin(robot)


def test_4ne1_mini_exposes_its_product_page_and_datasheet_under_separate_sources():
    web = cadence(neura_main(), due=True)
    docs = cadence(px_docs(), due=True)
    p_web = plan([_mini()], [web, docs], web.key)
    p_doc = plan([_mini()], [web, docs], docs.key)
    assert [(t.url, t.target_type, t.source) for t in p_web.planned] == [
        (MINI_PRODUCT, ep.PRODUCT_PAGE, "neura-robotics-official")]
    assert [(t.url, t.target_type, t.source) for t in p_doc.planned] == [
        (DATASHEET, ep.DOCUMENT, "neura-documents-official")]
    assert ep.COMMERCIAL_STATUS_UNKNOWN in p_web.planned[0].reason_codes
    assert ep.NEW_DOCUMENT_POSSIBLE in p_doc.planned[0].reason_codes


def test_the_document_host_stays_governed_separately_from_the_main_site():
    web, docs = cadence(neura_main(), due=True), cadence(px_docs(), due=True)
    robot = pin(inp(rich(manufacturer_slug="neura-robotics", slug="4ne1-mini",
                         official_url=MINI_PRODUCT, images=()),
                    urls=[("specification", PX + "other/secret.pdf"),
                          ("specification", "https://evil.px.media/plk/x.pdf")]))
    p = plan([robot], [web, docs], docs.key)
    bad = {t.url for t in p.skipped if t.decision == ep.SOURCE_REVIEW_REQUIRED}
    assert bad == {PX + "other/secret.pdf", "https://evil.px.media/plk/x.pdf"}
    assert all(t.url not in bad for t in p.planned)
    # without an enabled document source the datasheet itself needs source review
    no_docs = plan([_mini()], [web, cadence(px_docs(enabled=False), due=True)], web.key)
    assert DATASHEET in {t.url for t in no_docs.skipped
                         if t.decision == ep.SOURCE_REVIEW_REQUIRED}


# ---------------------------------------------------------------------------- no source onboarded


def test_a_robot_without_an_approved_source_is_profiled_but_gets_no_target():
    fourier = pin(inp(sparse(slug="fourier-gr-1", manufacturer_slug="fourier-intelligence",
                             commercial_status="UNKNOWN", official_url="https://www.fftai.com/"),
                      commercial_days=None, year=2023, docs=False))
    profiles, targets = ep.plan_unsourced([fourier, maker_rich()], {"maker-x"}, {}, NOW)
    assert [p.robot_slug for p in profiles] == ["fourier-gr-1"]
    [t] = targets
    assert t.decision == ep.NO_APPROVED_TARGET and t.url == "-" and t.eligibility == (
        "NO_APPROVED_SOURCE")
    assert profiles[0].priority == en.HIGH and ep.COMMERCIAL_STATUS_UNKNOWN in (
        profiles[0].reason_codes)
    # and once a governed source is onboarded the same robot becomes a HIGH-priority target
    fftai = cadence(source(), due=True)
    fftai.key, fftai.homepage_url, fftai.allowed_path_prefixes = (
        "fourier-official", "https://www.fftai.com/", ["/"])
    p = plan([fourier], [fftai], "fourier-official")
    assert [t.robot for t in p.planned] == ["fourier-gr-1"] and p.planned[0].priority == en.HIGH


# ---------------------------------------------------------------------------- firewalls


def test_priority_and_reason_codes_never_affect_publication_eligibility():
    rec = rich(is_published=True, official_url=HOST + "robots/rich")
    base = rd.publication_check(rec)
    ep.build_profile(pin(inp(rec, commercial_days=999, spec_days=999)), NOW, {})
    assert rd.publication_check(rec) == base == []
    assert "enrichment_plan" not in inspect.getsource(rd)
    assert "discovery.enrichment" not in inspect.getsource(rd)


def test_a_low_coverage_published_robot_stays_publication_valid_and_is_high_priority():
    rec = sparse(is_published=True, manufacturer_slug="maker-x", commercial_status="UNKNOWN")
    prof = ep.build_profile(pin(inp(rec, commercial_days=None, year=2026)), NOW, {})
    assert prof.is_published and prof.priority == en.HIGH
    assert rd.publication_check(rec) == []


def test_the_planner_has_no_write_path():
    src = Path(ep.__file__).read_text(encoding="utf-8")
    forbidden_patterns = (
        r"session\.add\(", r"\.commit\(", r"\.flush\(", r"INSERT\s", r"UPDATE\s", r"DELETE\s",
        r"is_published\s*=[^=]", r"commercial_status\s*=[^=]", r"httpx", r"requests\.",
        r"urlopen", r"ingest_proposals", r"DiscoveryCandidate")
    for forbidden in forbidden_patterns:
        assert not re.search(forbidden, src), forbidden
    p = plan([maker_sparse()], [cadence(source(), due=True)], "maker-x-official")
    assert p.as_dict()["writes"] == 0 and p.as_dict()["fetches"] == 0


def test_assume_due_reports_what_a_source_would_plan_without_changing_anything():
    s = cadence(source(), due=False)
    p = ep.plan_manufacturer([maker_sparse()], [s], {}, NOW, source_key=s.key, assume_due=True)
    assert len(p.planned) == 1 and p.source_due
    assert s.last_crawled_at == NOW - timedelta(hours=1)          # the source itself is untouched
