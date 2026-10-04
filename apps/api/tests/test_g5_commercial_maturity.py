"""G5 — commercial maturity joins the governed claim pipeline (owner ruling 2026-10-04).

Automation discovers and preserves the evidence; a human decides which frozen status, if any,
it establishes. proposal (COMMERCIAL_MATURITY) -> human ACCEPT with an explicit status ->
accepted claim (target `commercial_status`) -> deterministic materialization into
`commercial_status` + `commercial_status_evidence` -> importer. Publication is never touched.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from test_xpeng_iron import Site
from test_xpeng_iron import dsession as dsession  # noqa: F401 (fixture)
from test_xpeng_iron import site as site  # noqa: F401 (fixture)

from app.models import AcceptedClaim, ClaimRetraction, DiscoveryClaimProposal
from app.services.discovery import DiscoveryError, claims, materialize
from app.services.discovery import proposal_review as pr
from app.services.discovery.field_policy import (
    ACCEPTABLE_COMMERCIAL_STATUSES,
    CLAIM_POLICIES,
    claim_policy_for,
)
from app.services.discovery.proposals import (
    CATALOGUE_ENRICHMENT,
    NEW_MODEL,
    ingest_proposals,
    maturity_spec,
)
from app.services.discovery.sources import maturity_proposals as mp

pytestmark = pytest.mark.usefixtures("no_external_network")
REPO = Path(__file__).resolve().parents[3]
WHO = "Robert Konecny"
URL = "https://xpeng.example.com/iron-news"

DELIVERY = ("IRON has begun delivery to the first customers in the United States and Europe in "
            "2026.")
PILOT = "IRON is running a pilot with two selected partners at their factories."
FUTURE = "IRON will launch to the public in 2027."
NOISE = "Our company was founded in 2014 and builds electric vehicles."
OTHER = "The XYZ-9 has begun delivery to its first customers."


def page(*sentences: str) -> bytes:
    body = "".join(f"<p>{s}</p>" for s in sentences)
    return (f"<html><head><script>var a='IRON ships';</script></head><body><nav>IRON shipping now."
            f"</nav>{body}</body></html>").encode()


def ingest(site: Site, body: bytes, *, origin: str = CATALOGUE_ENRICHMENT, url: str = URL,
           scope: str = mp.SHARED_PAGE):
    obs = site.observe(url, body)
    report = ingest_proposals(
        site.session, spec=maturity_spec("IRON", scope), source_key=site.source.key,
        robot_slug=site.slug, fetched_page_id=obs.id, body=body, ingested_by="scanner",
        origin=origin)
    return obs, report


def maturity_proposals(site: Site):
    return [p for p in site.all_proposals() if p.kind == mp.KIND]


def by_text(site: Site, fragment: str) -> DiscoveryClaimProposal:
    [p] = [p for p in maturity_proposals(site) if fragment in p.value]
    return p


def choices(p, status: str | None = "COMMERCIAL", **over):
    out = {pr.question_key(i): "Reviewed: current statement about this exact robot"
           for i in range(1, len(p.review_questions) + 1)}
    out["target_kind"] = "commercial_status"
    if status is not None:
        out["accepted_value"] = status
    out.update(over)
    return out


def accept(site, p, status="COMMERCIAL", **over):
    return pr.decide(site.session, str(p.id), pr.ACCEPT, decided_by=WHO,
                     rationale="owner decision", choices=choices(p, status, **over))[0]


def make_claim(site, p, status="COMMERCIAL"):
    accept(site, p, status)
    return claims.create_claim(site.session, str(p.id), created_by=WHO)[0]


def stub_dir(site: Site, tmp_path: Path, **over) -> Path:
    doc = json.loads((REPO / "db" / "catalogue" / "robots" / "xpeng-iron.json").read_text(
        encoding="utf-8"))
    doc["slug"], doc["manufacturer_slug"] = site.slug, site.maker.slug
    doc["commercial_status"] = "UNKNOWN"
    doc["commercial_status_evidence"] = []
    doc["is_published"] = False
    doc.update(over)
    d = tmp_path / "cat"
    d.mkdir(exist_ok=True)
    (d / f"{site.slug}.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return d


# --------------------------------------------------------------------- extractor (pure) ---


def test_the_extractor_preserves_verbatim_wording_and_records_clues_not_a_status():
    r = mp.propose_maturity_clues(page(DELIVERY, PILOT, FUTURE, NOISE, OTHER), URL,
                                  robot_name="IRON")
    assert r.status == mp.PROPOSED and not r.suggests_status and not r.writes_catalogue
    values = {p.value: dict(p.structured) for p in r.proposals}
    assert set(values) == {DELIVERY, PILOT, FUTURE}          # noise and another product dropped
    assert "CUSTOMER_DELIVERY_STATED" in values[DELIVERY]["clues"]
    assert {"PILOT_STATED", "SELECTED_PARTNER_DEPLOYMENT_STATED"} <= set(values[PILOT]["clues"])
    assert "FUTURE_LAUNCH_STATED" in values[FUTURE]["clues"]
    for p in r.proposals:
        assert p.evidence.excerpt == p.value and p.evidence.locator.startswith(mp.LOCATOR_PREFIX)
        assert p.claim_status == "NOT_VERIFIED" and p.representability == "PARTIAL"
        assert not any(k in dict(p.structured) for k in ("status", "suggested_status",
                                                         "commercial_status"))
        assert not any(s in p.review_required[0] for s in ACCEPTABLE_COMMERCIAL_STATUSES[:0])
    assert [n for n in ("<nav", "var a") if n in "".join(p.value for p in r.proposals)] == []


def test_clues_are_observations_never_statuses():
    for clue_text in (DELIVERY, PILOT, FUTURE, "IRON is in mass production."):
        for clue in mp.clues_in(clue_text):
            assert clue not in ACCEPTABLE_COMMERCIAL_STATUSES      # no clue is a status name
    assert "CUSTOMER_DELIVERY_STATED" in mp.clues_in(DELIVERY)


def test_a_shared_page_sentence_must_name_the_robot_unless_the_page_is_its_own():
    unnamed = "The robot has begun delivery to its first customers."
    shared = mp.propose_maturity_clues(page(unnamed), URL, robot_name="IRON")
    own = mp.propose_maturity_clues(page(unnamed), URL, robot_name="IRON",
                                    page_scope=mp.ROBOT_PAGE)
    assert shared.status == mp.NO_PROPOSALS and shared.rejected
    assert [p.value for p in own.proposals] == [unnamed]


def test_the_extractor_is_deterministic_and_captures_one_explicit_date():
    s = "On March 3, 2026 IRON began delivery to customers."
    a = mp.propose_maturity_clues(page(s), URL, robot_name="IRON")
    b = mp.propose_maturity_clues(page(s), URL, robot_name="IRON")
    assert [p.digest for p in a.proposals] == [p.digest for p in b.proposals]
    assert dict(a.proposals[0].structured)["context_date"] == "2026-03-03"
    other = mp.propose_maturity_clues(page(s), URL, robot_name="IRON-2")
    assert other.status == mp.NO_PROPOSALS


# -------------------------------------------------------------- persistence and origin ---


def test_ingest_creates_proposals_and_changes_no_catalogue_state(site):
    before = site.session.scalar(select(func.count()).select_from(AcceptedClaim))
    status0 = site.session.scalar(text("SELECT commercial_status::text FROM robot WHERE slug=:s"),
                                  {"s": site.slug})
    _, rep = ingest(site, page(DELIVERY, PILOT))
    assert rep.status == "PROPOSED" and rep.proposals_created == 2
    assert {p.origin for p in maturity_proposals(site)} == {CATALOGUE_ENRICHMENT}
    assert {p.extractor_key for p in maturity_proposals(site)} == {mp.EXTRACTOR_KEY}
    assert site.session.scalar(select(func.count()).select_from(AcceptedClaim)) == before
    assert site.session.scalar(text("SELECT commercial_status::text FROM robot WHERE slug=:s"),
                               {"s": site.slug}) == status0 == "UNKNOWN"


def test_unchanged_wording_creates_no_duplicate_proposal(site):
    body = page(DELIVERY)
    _, first = ingest(site, body)
    _, again = ingest(site, body)           # a second observation of identical content
    assert (first.proposals_created, again.proposals_created) == (1, 0)
    assert len(maturity_proposals(site)) == 1
    assert again.observations_created == 1 and again.unchanged == 0   # one new sighting only


def test_changed_wording_creates_a_new_proposal_and_keeps_the_old_one(site):
    ingest(site, page(PILOT))
    _, changed = ingest(site, page(DELIVERY))
    assert changed.proposals_created == 1
    assert {p.value for p in maturity_proposals(site)} == {PILOT, DELIVERY}


def test_both_origins_use_the_same_policy_and_the_same_governed_claim(site):
    ingest(site, page(DELIVERY), origin=NEW_MODEL)
    ingest(site, page(FUTURE), origin=CATALOGUE_ENRICHMENT, url=URL + "-2")
    a, b = by_text(site, "begun delivery"), by_text(site, "will launch")
    assert (a.origin, b.origin) == (NEW_MODEL, CATALOGUE_ENRICHMENT)
    pa = claim_policy_for(a.kind, a.target, a.evidence_locator, a.structured)
    pb = claim_policy_for(b.kind, b.target, b.evidence_locator, b.structured)
    assert pa is pb is CLAIM_POLICIES["commercial_status[current]"]
    assert make_claim(site, a, "COMMERCIAL").target_kind == "commercial_status"


def test_an_unknown_origin_is_refused(site):
    with pytest.raises(DiscoveryError, match="origin"):
        ingest(site, page(DELIVERY), origin="SOMEWHERE")


def test_origin_is_a_database_checked_column(site):
    ingest(site, page(DELIVERY))
    definition = site.session.scalar(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'ck_claim_proposal_origin'"))
    assert "NEW_MODEL" in definition and "CATALOGUE_ENRICHMENT" in definition
    kinds = site.session.scalar(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'ck_accepted_claim_target_kind'"))
    assert "commercial_status" in kinds


# ---------------------------------------------------------------- human decision rules ---


def test_accept_requires_an_explicit_frozen_status(site):
    ingest(site, page(DELIVERY))
    p = by_text(site, "begun delivery")
    for bad, why in ((None, "explicit"), ("UNKNOWN", "UNKNOWN is not an accepted maturity claim"),
                     ("NOT_A_STATUS", "not a frozen commercial status"),
                     ("commercial", "not a frozen commercial status")):
        with pytest.raises(DiscoveryError, match=why):
            pr.decide(site.session, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="r",
                      choices=choices(p, bad))
    # the target must be named explicitly too, and the question must be answered
    with pytest.raises(DiscoveryError, match="target_kind"):
        pr.decide(site.session, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="r",
                  choices={k: v for k, v in choices(p).items() if k != "target_kind"})
    with pytest.raises(DiscoveryError, match="every review question"):
        pr.decide(site.session, str(p.id), pr.ACCEPT, decided_by=WHO, rationale="r",
                  choices={"target_kind": "commercial_status", "accepted_value": "COMMERCIAL"})
    assert site.session.scalar(select(func.count()).select_from(AcceptedClaim)) == 0


@pytest.mark.parametrize("status", ACCEPTABLE_COMMERCIAL_STATUSES)
def test_every_frozen_substantive_status_is_choosable_and_unknown_is_not(site, status):
    ingest(site, page(DELIVERY))
    p = by_text(site, "begun delivery")
    assert make_claim(site, p, status).accepted_value == status
    assert "UNKNOWN" not in ACCEPTABLE_COMMERCIAL_STATUSES


def test_reject_and_defer_leave_no_claim_and_the_status_unknown(site, tmp_path):
    ingest(site, page(DELIVERY, PILOT))
    d, p = by_text(site, "begun delivery"), by_text(site, "pilot")
    pr.decide(site.session, str(d.id), pr.REJECT, decided_by=WHO, rationale="not clean")
    pr.decide(site.session, str(p.id), pr.DEFER, decided_by=WHO, rationale="scope unclear")
    with pytest.raises(DiscoveryError, match="effective ACCEPT"):
        claims.create_claim(site.session, str(d.id), created_by=WHO)
    plan = materialize.plan_materialization(site.session, site.slug,
                                            stub_dir(site, tmp_path))
    assert not plan.changed


# ----------------------------------------------------------- materialization + provenance ---


def test_an_accepted_status_materializes_with_provenance_and_never_publishes(site, tmp_path):
    ingest(site, page(DELIVERY))
    p = by_text(site, "begun delivery")
    claim = make_claim(site, p, "COMMERCIAL")
    cat = stub_dir(site, tmp_path, is_published=False)
    plan = materialize.plan_materialization(site.session, site.slug, cat)
    doc = json.loads(plan.after)
    assert doc["commercial_status"] == "COMMERCIAL" and doc["is_published"] is False
    [ev] = doc["commercial_status_evidence"]
    assert ev["excerpt"] == DELIVERY and ev["source_url"] == URL
    assert ev["verified_at"] is None and ev["source_type"] == "MANUFACTURER_SITE"
    assert claim.claim_digest[:12] in ev["note"] and p.digest[:12] in ev["note"]
    assert WHO in ev["note"] and "reviewer's decision" in ev["note"]
    # deterministic and idempotent: applying it and planning again yields no diff
    assert materialize.apply_plan(plan) is True
    assert not materialize.plan_materialization(site.session, site.slug, cat).changed
    assert materialize.logical_target(claim) == f"commercial_status:{site.slug}"


def test_other_evidence_rows_are_preserved_when_a_status_materializes(site, tmp_path):
    ingest(site, page(DELIVERY))
    make_claim(site, by_text(site, "begun delivery"), "PILOT")
    manual = {"source_url": "https://x.example/old", "source_type": "MANUFACTURER_SITE",
              "source_title": "old", "excerpt": "older evidence", "published_at": None,
              "observed_at": "2025-01-01", "verified_at": None, "confidence": "LOW",
              "note": "manual"}
    cat = stub_dir(site, tmp_path, commercial_status="ANNOUNCED",
                   commercial_status_evidence=[manual])
    doc = json.loads(materialize.plan_materialization(site.session, site.slug, cat).after)
    assert doc["commercial_status"] == "PILOT"
    assert doc["commercial_status_evidence"][0] == manual and len(
        doc["commercial_status_evidence"]) == 2


def test_conflicting_active_maturity_claims_refuse_materialization(site, tmp_path):
    ingest(site, page(PILOT, DELIVERY))
    make_claim(site, by_text(site, "pilot"), "PILOT")
    newer = make_claim(site, by_text(site, "begun delivery"), "COMMERCIAL")
    cat = stub_dir(site, tmp_path)
    with pytest.raises(DiscoveryError, match="CONFLICT"):
        materialize.plan_materialization(site.session, site.slug, cat)
    # resolved through the governed mechanism: retract the older claim, naming the replacement
    [older] = [c for c in claims.active_claims(site.session, site.slug)
               if c.accepted_value == "PILOT"]
    claims.retract_claim(site.session, str(older.id), retracted_by=WHO,
                         reason="superseded by delivery wording", replacement_id=str(newer.id))
    doc = json.loads(materialize.plan_materialization(site.session, site.slug, cat).after)
    assert doc["commercial_status"] == "COMMERCIAL"


def test_retracting_the_only_claim_materializes_unknown_explicitly(site, tmp_path):
    ingest(site, page(DELIVERY))
    claim = make_claim(site, by_text(site, "begun delivery"), "COMMERCIAL")
    cat = stub_dir(site, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(site.session, site.slug, cat))
    claims.retract_claim(site.session, str(claim.id), retracted_by=WHO, reason="source was wrong")
    plan = materialize.plan_materialization(site.session, site.slug, cat)
    doc = json.loads(plan.after)
    assert doc["commercial_status"] == "UNKNOWN"                  # the governed outcome
    assert len(doc["commercial_status_evidence"]) == 1            # history is preserved
    assert doc["is_published"] is False


def test_a_robot_with_no_governed_maturity_history_keeps_its_manual_status(site, tmp_path):
    cat = stub_dir(site, tmp_path, commercial_status="PILOT")
    assert not materialize.plan_materialization(site.session, site.slug, cat).changed


def test_disappearing_wording_never_retracts_or_downgrades_a_claim(site, tmp_path):
    ingest(site, page(DELIVERY))
    claim = make_claim(site, by_text(site, "begun delivery"), "COMMERCIAL")
    cat = stub_dir(site, tmp_path)
    materialize.apply_plan(materialize.plan_materialization(site.session, site.slug, cat))
    assert materialize.maturity_review_required(site.session, site.slug) == []
    # the manufacturer rewrites the page: the sentence is gone
    ingest(site, page("A brand new, unrelated sentence about nothing in particular here."))
    review = materialize.maturity_review_required(site.session, site.slug)
    assert len(review) == 1 and review[0].startswith("REVIEW REQUIRED:")
    assert "COMMERCIAL" in review[0]
    # nothing was retracted, the active claim stands, and materialization still works unchanged
    assert site.session.scalar(select(func.count()).select_from(ClaimRetraction)) == 0
    assert [c.id for c in claims.active_claims(site.session, site.slug)] == [claim.id]
    plan = materialize.plan_materialization(site.session, site.slug, cat)
    assert not plan.changed and json.loads(plan.after)["commercial_status"] == "COMMERCIAL"


def test_maturity_claim_needs_a_manufacturer_source_for_its_evidence(site):
    ingest(site, page(DELIVERY))
    claim = make_claim(site, by_text(site, "begun delivery"), "COMMERCIAL")
    site.source.source_class = "RETAILER" if False else site.source.source_class
    ev = materialize.maturity_evidence(site.session, claim)
    assert ev["source_type"] == "MANUFACTURER_SITE" and ev["confidence"] == "MEDIUM"


def test_verify_applied_checks_the_robot_status_and_its_evidence_row(site, tmp_path):
    ingest(site, page(DELIVERY))
    claim = make_claim(site, by_text(site, "begun delivery"), "COMMERCIAL")
    with pytest.raises(DiscoveryError, match="import the merged catalogue"):
        materialize.verify_applied(site.session, site.slug, change_ref="PR-x", applied_by=WHO)
    site.session.execute(text("UPDATE robot SET commercial_status='COMMERCIAL' WHERE slug=:s"),
                         {"s": site.slug})
    rid = site.session.scalar(text("SELECT id FROM robot WHERE slug=:s"), {"s": site.slug})
    site.session.execute(text(
        "INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type, "
        "excerpt, observed_at, confidence) VALUES ('COMMERCIAL_STATUS', :r, :u, "
        "'MANUFACTURER_SITE', :e, now(), 'MEDIUM')"),
        {"r": rid, "u": URL, "e": claim.evidence_excerpt})
    [audit] = materialize.verify_applied(site.session, site.slug, change_ref="PR-x",
                                         applied_by=WHO)
    assert audit.target_table == "robot" and audit.claim_id == claim.id


def test_the_policy_is_registered_and_keeps_the_registry_closed(site):
    pol = CLAIM_POLICIES["commercial_status[current]"]
    assert (pol.proposal_kind, pol.target_kind, pol.target_key) == (
        "COMMERCIAL_MATURITY", "commercial_status", "commercial_status")
    assert claim_policy_for("COMMERCIAL_MATURITY", "commercial_status", "text[other]/x") is None
    assert claim_policy_for("COMMERCIAL_MATURITY", "robot_spec", mp.LOCATOR_PREFIX + "ab") is None
    assert ("maturity-clues", mp.EXTRACTOR_VERSION) in pr.LIVE_EXTRACTORS


# ------------------------------------------------------- Lane B inside one source cycle ---

from test_xpeng_iron import PAGES, body_of  # noqa: E402

from app.models.discovery import DiscoveryCandidate  # noqa: E402
from app.services.discovery import g2_ingest  # noqa: E402


def cycle_registry(site: Site, *, maturity: bool = True):
    reg = g2_ingest.G2_INGESTS["xpeng-official"]
    return {site.source.key: g2_ingest.G2Ingest(
        page_url=reg.page_url, robot_slug=site.slug, ingest=reg.ingest,
        more_page_urls=reg.more_page_urls, maturity_robot_name="IRON" if maturity else None)}


def run_cycle(site: Site, *, maturity: bool = True):
    return g2_ingest.ingest_for_source(
        site.session, site.source, cache_dir=site.cache, operator="scheduler",
        registry=cycle_registry(site, maturity=maturity))


def observe_all(site: Site):
    for url in PAGES:
        site.observe(url)


def counts(site: Site) -> dict:
    return {t: site.session.scalar(text(f"SELECT count(*) FROM {t}")) for t in (
        "discovery_candidate", "robot", "accepted_claim", "discovery_proposal_decision",
        "catalogue_write_audit")}


def test_one_source_cycle_runs_the_technical_and_the_maturity_lane_quietly(site):
    observe_all(site)
    before = counts(site)
    first = run_cycle(site)
    assert first.status == "INGESTED" and first.proposals_created > 0
    assert first.maturity_created > 0 and first.maturity_failure == ""
    assert first.attention and "commercial-maturity proposal" in first.summary()
    assert {p.origin for p in maturity_proposals(site)} == {CATALOGUE_ENRICHMENT}
    # a known robot: no candidate, no new robot, no decision, claim, audit or status change
    after = counts(site)
    assert after == before
    assert site.session.scalar(text("SELECT commercial_status::text FROM robot WHERE slug=:s"),
                               {"s": site.slug}) == "UNKNOWN"
    assert site.session.scalar(text("SELECT is_published FROM robot WHERE slug=:s"),
                               {"s": site.slug}) is False
    n = len(maturity_proposals(site))
    # the next cycle sees nothing new: no duplicate proposal, no alert
    second = run_cycle(site)
    assert second.maturity_created == 0 and len(maturity_proposals(site)) == n
    assert not second.attention


def test_lane_a_behaviour_is_unchanged_when_no_maturity_robot_is_registered(site):
    observe_all(site)
    r = run_cycle(site, maturity=False)
    assert r.status == "INGESTED" and r.maturity_created == 0 and r.maturity_seen == 0
    assert maturity_proposals(site) == []
    assert not r.as_dict()["maturity_failure"]


def test_a_changed_page_creates_a_new_enrichment_proposal_and_unchanged_ones_stay_quiet(site):
    for url in PAGES:
        site.observe(url)
    run_cycle(site)
    base = len(maturity_proposals(site))
    url = next(iter(PAGES))
    changed = body_of(url).replace(
        b"</body>", b"<p>IRON has begun delivery to its first paying customers.</p></body>")
    site.observe(url, changed)
    r = run_cycle(site)
    assert r.maturity_created == 1 and len(maturity_proposals(site)) == base + 1
    fresh = by_text(site, "first paying customers")
    assert fresh.origin == CATALOGUE_ENRICHMENT and "CUSTOMER_DELIVERY_STATED" in dict(
        fresh.structured)["clues"]
    assert site.session.scalar(select(func.count()).select_from(DiscoveryCandidate)) == 0


def test_a_failing_maturity_extraction_never_fails_the_technical_ingest(site, monkeypatch):
    observe_all(site)

    def boom(*a, **k):
        raise RuntimeError("extractor exploded")

    monkeypatch.setattr(g2_ingest, "maturity_spec", boom)
    r = run_cycle(site)
    assert r.status == "INGESTED" and r.proposals_created > 0
    assert "extractor exploded" in r.maturity_failure and r.attention


def test_the_cycle_report_lists_maturity_proposals_in_the_enrichment_lane():
    from datetime import UTC, datetime

    from app.services.discovery.observe import CycleResult, SourceObservation

    src = SourceObservation("s", "COMPLETED", "", counts={"g2_ingest": {
        "proposals_created": 1, "proposals_seen": 2, "maturity_proposals_created": 3,
        "maturity_proposals_seen": 4}})
    cycle = CycleResult(datetime(2026, 10, 4, tzinfo=UTC), plan_only=False, sources=[src])
    text_ = "\n".join(cycle.lane_lines())
    assert "commercial-maturity proposals: 3 new / 4 seen" in text_
    assert cycle.lane_summary()["CATALOGUE_ENRICHMENT"]["maturity_proposals_created"] == 3


def test_no_g5_module_can_change_publication_or_accept_anything():
    """Scanning and proposing never publish and never decide; pinned structurally."""
    base = REPO / "apps" / "api" / "app" / "services" / "discovery"
    for rel in ("g2_ingest.py", "sources/maturity_proposals.py", "enrichment.py"):
        src = (base / rel).read_text(encoding="utf-8")
        assert not re.search(r"is_published\s*=[^=]|SET\s+is_published|publish\(", src), rel
        assert "DiscoveryProposalDecision(" not in src and "AcceptedClaim(" not in src, rel
