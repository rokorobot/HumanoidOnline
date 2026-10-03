"""XPENG IRON onboarding (owner source approval 2026-10-03): adapter, identity, proposals, G2.

Fixtures under tests/fixtures/xpeng are byte-exact, script/style-stripped copies of the four
official xpeng.com pages the owner approved. Pure tests need no database; the persistence
tests run in rolled-back transactions.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models import AcceptedClaim, DiscoveryClaimProposal, DiscoveryProposalObservation
from app.models.acquisition import CrawlRun, FetchedPage
from app.models.discovery import DiscoverySource
from app.models.manufacturer import Manufacturer
from app.models.robot import Robot
from app.services.discovery import DiscoveryError, claims, g2_ingest
from app.services.discovery import cache as body_cache
from app.services.discovery import proposal_review as pr
from app.services.discovery.fingerprint import fingerprint
from app.services.discovery.proposals import ingest_xpeng_iron_proposals
from app.services.discovery.sources import ADAPTERS, adapter_for, xpeng_robotics
from app.services.discovery.sources import xpeng_iron_proposals as x

pytestmark = pytest.mark.usefixtures("no_external_network")
FX = Path(__file__).parent / "fixtures" / "xpeng"
REPO = Path(__file__).resolve().parents[3]
NEWS_2026 = "https://www.xpeng.com/news/01a080371029a057bc8e8a02a2c6012b"
NEWS_2025 = "https://www.xpeng.com/au/news/019e71be4f9e9dd703de8a0282290455"
NEWS_2024 = "https://www.xpeng.com/news/019301d2135392fa562d8a0282200016"
PAGES = {x.PRODUCT_PAGE_URL: "product_page.html", NEWS_2026: "news_2026_09_08.html",
         NEWS_2025: "news_2025_11_05.html", NEWS_2024: "news_2024_11_06.html"}
EXPECTED_COUNTS = {x.PRODUCT_PAGE_URL: 16, NEWS_2026: 9, NEWS_2025: 11, NEWS_2024: 2}


def body_of(url: str) -> bytes:
    return (FX / PAGES[url]).read_bytes()


def run(url: str, body: bytes | None = None):
    return x.propose_xpeng_iron_claims(body if body is not None else body_of(url), url)


def struct(p) -> dict:
    return dict(p.structured)


# --------------------------------------------------------------- extractor ---


@pytest.mark.parametrize("url,count", EXPECTED_COUNTS.items())
def test_every_reviewed_page_yields_its_proposals_and_no_rejections(url, count):
    r = run(url)
    assert r.status == x.PROPOSED and len(r.proposals) == count and r.rejected == ()
    assert r.writes_catalogue is False and r.writes_candidate_claims is False
    assert all(p.claim_status == "NOT_VERIFIED" and p.confidence == "HIGH" for p in r.proposals)
    assert all(p.source_url == url for p in r.proposals)
    assert len({p.digest for p in r.proposals}) == len(r.proposals)        # unique, stable ids


def test_the_extraction_is_deterministic():
    for url in PAGES:
        assert [p.digest for p in run(url).proposals] == [p.digest for p in run(url).proposals]


def by_kind(url, kind):
    return [p for p in run(url).proposals if p.kind == kind]


def test_the_2026_production_configuration_values_are_exactly_as_stated():
    [body] = by_kind(NEWS_2026, "BODY_DOF")
    [hand] = by_kind(NEWS_2026, "HAND_DOF")
    [compute] = by_kind(NEWS_2026, "COMPUTE")
    assert struct(body)["body_dof"] == "76" and struct(body)["scope"] == "across the body"
    assert struct(hand)["hand_dof_each"] == "21" and struct(hand)["scope"] == "in each hand"
    assert (struct(compute)["chips"], struct(compute)["tops_up_to"]) == ("3", "2250")
    assert body.representability == hand.representability == compute.representability == "PARTIAL"
    assert "76 degrees of freedom (DOF) across the body and 21 in each hand" in body.value


def test_the_2025_next_gen_values_stay_independent_of_the_2026_values():
    [body] = by_kind(NEWS_2025, "BODY_DOF")
    [hand] = by_kind(NEWS_2025, "HAND_DOF")
    [compute] = by_kind(NEWS_2025, "COMPUTE")
    assert struct(body)["body_dof"] == "82" and struct(hand)["hand_dof_each"] == "22"
    assert struct(compute)["tops"] == "3000" and "tops_up_to" not in struct(compute)
    # nothing averages, ranks, merges or flattens the figures across pages or generations
    every = [p for u in PAGES for p in run(u).proposals]
    for p in every:
        values = {v for k, v in p.structured if k in ("body_dof", "hand_dof_each", "tops",
                                                     "tops_up_to")}
        assert len(values) <= 2 or p.kind == "COMPUTE"
    assert not any("total" in json.dumps(dict(p.structured)).lower() for p in every)
    assert {struct(p)["configuration"] for p in (body, hand, compute)} == {"2025 Next-Gen IRON"}


def test_the_product_page_figures_are_kept_as_its_own_statements():
    hands = by_kind(x.PRODUCT_PAGE_URL, "HAND_DOF")
    assert {struct(p)["hand_dof_each"] for p in hands} == {"22"}
    assert len(hands) == 2 and all(p.representability == "PARTIAL" for p in hands)
    [chips] = by_kind(x.PRODUCT_PAGE_URL, "COMPUTE")
    assert struct(chips) == {"source_page": "product-page", "chips": "3"}   # no TOPS invented
    assert not by_kind(x.PRODUCT_PAGE_URL, "BODY_DOF")


def test_the_2024_unveiling_is_not_mapped_to_current_body_dof():
    [legacy] = by_kind(NEWS_2024, "SYSTEM_DOF_2024")
    assert struct(legacy)["joints"] == "more than 60"
    assert struct(legacy)["degrees_of_freedom"] == "200"
    assert legacy.representability == "UNREPRESENTABLE" and legacy.target == "UNMAPPED"
    assert "robot.degrees_of_freedom" not in legacy.target
    [internal] = by_kind(NEWS_2024, "DEPLOYMENT_STATE")
    assert "internal applications" in internal.value
    assert not any(p.kind in ("BODY_DOF", "HAND_DOF") for p in run(NEWS_2024).proposals)


def test_plans_stay_year_level_and_are_not_availability_or_dates():
    [launch] = by_kind(NEWS_2026, "LAUNCH_PLAN")
    assert struct(launch)["planned_year"] == "2027" and struct(launch)["precision"] == "year-level"
    assert launch.value.endswith("are planned for 2027.")
    assert "date" not in {k for k, _ in launch.structured}
    [mass] = by_kind(NEWS_2026, "MASS_PRODUCTION_PLAN")
    assert struct(mass)["stated_timing"] == "by the end of this year"
    [internal] = by_kind(NEWS_2026, "DEPLOYMENT_PLAN")
    assert "own stores and campuses" in struct(internal)["where"] or "XPENG's own" in struct(
        internal)["where"]
    every = [p for u in PAGES for p in run(u).proposals]
    plan_facts = " ".join(
        json.dumps({k: v for k, v in p.structured if k not in ("source_page", "stated_on")})
        for p in every if p.kind.endswith("PLAN"))
    assert not re.search(r"20\d\d-\d\d-\d\d", plan_facts)     # no exact date is ever invented
    for p in every:                       # no commercial semantics are ever proposed
        assert p.kind not in ("PRICE", "PRICE_ESTIMATE", "AVAILABILITY", "COMMERCIAL_STATUS")
        assert "price" not in p.target.lower() and "availability_offer (" not in p.target[:0]


def test_manufacturing_progress_is_not_a_commercial_maturity():
    [state] = by_kind(NEWS_2026, "MANUFACTURING_STATE")
    assert "NOT a commercial maturity" in state.gap
    for p in (state, *by_kind(NEWS_2026, "DEPLOYMENT_PLAN"), *by_kind(NEWS_2026,
                                                                         "MASS_PRODUCTION_PLAN")):
        assert p.representability == "UNREPRESENTABLE" and p.target == "UNMAPPED"


def test_the_generation_chronology_is_preserved_verbatim():
    kinds = by_kind(NEWS_2025, "GENERATION_HISTORY")
    values = " | ".join(p.value for p in kinds)
    assert "first-generation IRON" in values and "Next-Gen IRON made a stunning debut" in values
    assert "comprehensive upgrades" in values


def test_marketing_language_is_not_turned_into_booleans_or_capabilities():
    every = [p for u in PAGES for p in run(u).proposals]
    blob = json.dumps([[p.kind, p.target, dict(p.structured)] for p in every]).lower()
    for banned in ("has_sdk", "has_vision", "has_manipulation", "has_teleoperation",
                   "autonomy", "capability_slug", "ros_support"):
        assert banned not in blob, banned
    [sdk] = by_kind(NEWS_2025, "SDK_PLAN")
    assert sdk.representability == "UNREPRESENTABLE" and "will open" in sdk.value
    sensing = by_kind(x.PRODUCT_PAGE_URL, "SENSING")
    assert sensing and sensing[0].representability == "UNREPRESENTABLE"


def test_only_the_four_reviewed_pages_are_read():
    for bad in ("https://www.xpeng.com/", "https://www.xpeng.com/news/other",
                "https://www.xpeng.com/models/g9", "https://example.com/technology/ai_robot_iron"):
        r = x.propose_xpeng_iron_claims(body_of(x.PRODUCT_PAGE_URL), bad)
        assert r.status == x.OUT_OF_SCOPE and r.proposals == ()
    assert x.propose_xpeng_iron_claims(b"", None).status == x.OUT_OF_SCOPE


def test_a_page_that_is_not_what_was_reviewed_produces_nothing():
    body = body_of(NEWS_2026)
    wrong_date = body.replace(b"2026-09-08", b"2026-10-09")
    assert run(NEWS_2026, wrong_date).status == x.NO_PROPOSALS
    other_canonical = body.replace(b'rel="canonical" href="https://www.xpeng.com/news/01a0',
                                   b'rel="canonical" href="https://www.xpeng.com/news/zzzz', 1)
    if other_canonical != body:
        assert run(NEWS_2026, other_canonical).status == x.AMBIGUOUS
    assert run(NEWS_2026, b"<html><body>nothing</body></html>").status == x.NO_PROPOSALS
    product = body_of(x.PRODUCT_PAGE_URL).replace(
        b"XPENG Next-Gen IRON: The Most", b"XPENG Cars: The Most")
    assert run(x.PRODUCT_PAGE_URL, product).status == x.NO_PROPOSALS


def test_a_changed_statement_is_rejected_and_the_rest_are_still_proposed():
    body = body_of(NEWS_2026).replace(b"76 degrees of freedom (DOF) across the body",
                                      b"seventy-six degrees of freedom across the body")
    r = run(NEWS_2026, body)
    assert r.status == x.PROPOSED
    rejected = {item for item, _ in r.rejected}
    assert rejected == {"news-2026-09-08/body-dof", "news-2026-09-08/hand-dof"}
    assert len(r.proposals) == EXPECTED_COUNTS[NEWS_2026] - 2


def test_a_changed_number_is_a_new_proposal_in_the_same_slot_not_a_silent_overwrite():
    old = run(NEWS_2026)
    new = run(NEWS_2026, body_of(NEWS_2026).replace(b"21 in each hand", b"20 in each hand"))
    o = next(p for p in old.proposals if p.kind == "HAND_DOF")
    n = next(p for p in new.proposals if p.kind == "HAND_DOF")
    assert o.evidence.locator == n.evidence.locator and o.digest != n.digest
    assert struct(n)["hand_dof_each"] == "20"


def test_cosmetic_navigation_and_footer_changes_do_not_change_any_proposal():
    body = body_of(NEWS_2026)
    changed = body.replace(b"Charging", b"Charging network", 3).replace(
        b"COPYRIGHT@XPENG INC.", b"COPYRIGHT@XPENG INC. All rights reserved.")
    assert changed != body
    assert [p.digest for p in run(NEWS_2026, changed).proposals] == [
        p.digest for p in run(NEWS_2026).proposals]


def test_excerpts_are_bounded_verbatim_and_located():
    for url in PAGES:
        text_blocks = " ".join(x._blocks(_tree(body_of(url)).root))
        for p in run(url).proposals:
            assert 0 < len(p.evidence.excerpt) <= 1000 and p.evidence.locator.startswith(
                x.PAGES[url][0] + "/text-block[")
            assert p.evidence.excerpt in text_blocks


def _tree(body: bytes):
    t = x._Tree()
    t.feed(body.decode("utf-8"))
    t.close()
    return t


# ------------------------------------------------------------ source module ---


def test_the_adapter_is_a_fixed_reviewed_set_of_four_pages():
    cfg = xpeng_robotics.CONFIG
    assert adapter_for("xpeng-official") is cfg and "xpeng-official" in ADAPTERS
    assert (cfg.host, cfg.manufacturer, cfg.source_class) == (
        "www.xpeng.com", "XPeng Robotics", "MANUFACTURER")
    assert set(cfg.seed_urls) == set(PAGES) and cfg.target_cap == 1
    assert cfg.announcement_path_pattern is None and cfg.blocked_reason is None
    assert cfg.kind_of(x.PRODUCT_PAGE_URL) == "PRODUCT"
    for other in (NEWS_2026, NEWS_2025, NEWS_2024, "https://www.xpeng.com/models/g9",
                  "https://www.xpeng.com/technology/ai_car"):
        assert cfg.kind_of(other) is None            # nothing else is ever a target
    for url in cfg.seed_urls:
        assert any(url.split("xpeng.com", 1)[1].startswith(p) for p in cfg.allowed_path_prefixes)
    assert "OWNER-APPROVED" in xpeng_robotics.OWNER_SOURCE_DECISION


def test_identity_is_read_from_the_visible_title_not_the_boilerplate_title():
    cfg = xpeng_robotics.CONFIG
    r = xpeng_robotics.extract_xpeng_product(cfg, body_of(x.PRODUCT_PAGE_URL), x.PRODUCT_PAGE_URL)
    assert (r.status, r.name) == ("EXTRACTED", "IRON") and r.claims == () and r.signals == ()
    # a news page, or another path, is never a product page
    assert xpeng_robotics.extract_xpeng_product(cfg, body_of(NEWS_2026), NEWS_2026).status == (
        "NOTHING_FOUND")
    # no visible title block: the generic <title> alone is not identity
    plain = body_of(x.PRODUCT_PAGE_URL).replace(
        b"XPENG Next-Gen IRON: The Most", b"XPENG Cars: The Most")
    assert xpeng_robotics.extract_xpeng_product(cfg, plain, x.PRODUCT_PAGE_URL).status == (
        "NOTHING_FOUND")
    # a canonical that points elsewhere is ambiguous
    moved = body_of(x.PRODUCT_PAGE_URL).replace(
        b'rel="canonical" href="https://www.xpeng.com/technology/ai_robot_iron"',
        b'rel="canonical" href="https://www.xpeng.com/technology/ai_car"')
    assert xpeng_robotics.extract_xpeng_product(cfg, moved, x.PRODUCT_PAGE_URL).status == (
        "AMBIGUOUS")


def test_the_manufacturer_identity_is_not_duplicated():
    doc = json.loads((REPO / "db" / "catalogue" / "manufacturers.json").read_text(
        encoding="utf-8"))["manufacturers"]
    xp = [m for m in doc if "xpeng" in (m["slug"] + m["name"] + (m.get("legal_name") or "")
                                        + (m.get("parent_company") or "")).lower()
          and "robotics" in m["slug"]]
    assert [m["slug"] for m in xp] == ["xpeng-robotics"]
    robots = [p.stem for p in (REPO / "db" / "catalogue" / "robots").glob("*xpeng*.json")]
    assert robots == ["xpeng-iron"]                   # one canonical robot, not one per generation


def test_the_catalogue_entry_is_identity_and_reference_only():
    d = json.loads((REPO / "db" / "catalogue" / "robots" / "xpeng-iron.json").read_text(
        encoding="utf-8"))
    assert (d["slug"], d["name"], d["manufacturer_slug"]) == ("xpeng-iron", "IRON",
                                                              "xpeng-robotics")
    assert d["commercial_status"] == "UNKNOWN" and d["is_published"] is False
    assert d["official_url"] == "https://www.xpeng.com/technology/ai_robot_iron"
    assert d["summary"] is None and d["announced_year"] is None
    assert all(v is None for v in d["specs"].values())
    for coll in ("variants", "pricing_offers", "availability_offers", "capabilities",
                 "use_case_fits", "images", "deployments", "commercial_status_evidence"):
        assert d[coll] == [], coll


# ------------------------------------------------------------- persistence ---


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


class Site:
    def __init__(self, session: Session, tmp_path):
        tag = uuid.uuid4().hex[:8]
        self.session = session
        self.cache = tmp_path / "cache"
        self.maker = Manufacturer(slug=f"xp-{tag}", name=f"XPeng Robotics {tag}")
        session.add(self.maker)
        session.flush()
        self.slug = f"xpeng-iron-{tag}"
        self.robot = Robot(slug=self.slug, manufacturer_id=self.maker.id, name="IRON",
                           is_published=False)
        self.source = DiscoverySource(key=f"xpeng-official-{tag}", name="XPENG",
                                      source_class="MANUFACTURER")
        session.add_all([self.robot, self.source])
        session.flush()
        self.run = CrawlRun(source_id=self.source.id, adapter_key="manual", adapter_version="1",
                            operator="fixture", status="COMPLETED",
                            started_at=datetime(2026, 10, 3, tzinfo=UTC),
                            finished_at=datetime(2026, 10, 3, tzinfo=UTC))
        session.add(self.run)
        session.flush()
        self.n = 0

    def observe(self, url: str, body: bytes | None = None, *, retain: bool = True):
        body = body if body is not None else body_of(url)
        self.n += 1
        page = FetchedPage(
            crawl_run_id=self.run.id, source_id=self.source.id, url=url, http_status=200,
            content_type="text/html", content_hash=fingerprint(body, "text/html"),
            outcome="FETCHED",
            retrieved_at=datetime(2026, 10, 3, tzinfo=UTC) + timedelta(hours=self.n))
        self.session.add(page)
        self.session.flush()
        if retain:
            digest = body_cache.store_body(self.cache, body)
            body_cache.record_observation(self.cache, str(page.id), {"raw_sha256": digest})
        return page

    def ingest(self, page: FetchedPage, body: bytes):
        return ingest_xpeng_iron_proposals(
            self.session, source_key=self.source.key, robot_slug=self.slug,
            fetched_page_id=page.id, body=body, ingested_by="test")

    def registry(self):
        reg = g2_ingest.G2_INGESTS["xpeng-official"]
        return {self.source.key: g2_ingest.G2Ingest(
            page_url=reg.page_url, robot_slug=self.slug, ingest=reg.ingest,
            more_page_urls=reg.more_page_urls)}

    def cycle(self):
        return g2_ingest.ingest_for_source(
            self.session, self.source, cache_dir=self.cache, operator="test",
            registry=self.registry())

    def all_proposals(self):
        return list(self.session.scalars(select(DiscoveryClaimProposal).where(
            DiscoveryClaimProposal.robot_slug == self.slug)))


@pytest.fixture
def site(dsession, tmp_path):
    return Site(dsession, tmp_path)


def test_the_g2_registry_lists_exactly_the_four_reviewed_pages():
    reg = g2_ingest.G2_INGESTS["xpeng-official"]
    assert reg.robot_slug == "xpeng-iron" and set(reg.page_urls) == set(PAGES)
    assert set(g2_ingest.G2_INGESTS) == {"neura-robotics-official", "xpeng-official"}
    assert ("xpeng-iron-proposals", x.EXTRACTOR_VERSION) in pr.LIVE_EXTRACTORS


def test_ingest_persists_every_page_with_provenance_and_nothing_else(site):
    before = {t: site.session.scalar(text(f"SELECT count(*) FROM {t}")) for t in (
        "robot", "manufacturer", "evidence_source", "specification", "pricing_offer",
        "availability_offer", "candidate_claim", "discovery_proposal_decision", "accepted_claim")}
    for url in PAGES:
        page = site.observe(url)
        r = site.ingest(page, body_of(url))
        assert (r.status, r.proposals_created, r.observations_created) == (
            "PROPOSED", EXPECTED_COUNTS[url], EXPECTED_COUNTS[url])
        # the same observation again: idempotent
        again = site.ingest(page, body_of(url))
        assert (again.proposals_created, again.observations_created) == (0, 0)
    rows = site.all_proposals()
    assert len(rows) == sum(EXPECTED_COUNTS.values()) == 38
    assert {r.claim_status for r in rows} == {"NOT_VERIFIED"}
    assert {r.extractor_key for r in rows} == {"xpeng-iron-proposals"}
    assert {r.robot_slug for r in rows} == {site.slug}
    assert {r.source_url for r in rows} == set(PAGES)
    after = {t: site.session.scalar(text(f"SELECT count(*) FROM {t}")) for t in before}
    assert after == before
    assert all(s.state == pr.CURRENT for s in pr.derive_states(site.session, rows))


def test_ingest_refuses_wrong_pages_wrong_robots_and_unproven_bodies(site):
    page = site.observe(NEWS_2026)
    with pytest.raises(DiscoveryError, match="content_hash"):
        site.ingest(page, body_of(NEWS_2026) + b"<p>tampered</p>")
    other = site.observe("https://www.xpeng.com/models/g9", b"<html>car</html>")
    with pytest.raises(DiscoveryError, match="reads"):
        site.ingest(other, b"<html>car</html>")
    site.session.execute(text("UPDATE robot SET name = 'Another' WHERE slug = :s"),
                         {"s": site.slug})
    site.session.expire_all()
    with pytest.raises(DiscoveryError, match="not the catalogue"):
        site.ingest(page, body_of(NEWS_2026))


def test_the_scheduled_step_ingests_all_four_pages_then_is_idempotent(site):
    for url in PAGES:
        site.observe(url)
    first = site.cycle()
    assert first.status == g2_ingest.INGESTED and first.proposals_created == 38
    assert first.attention                                  # new proposals need a human
    assert site.cycle().status == g2_ingest.UP_TO_DATE
    for url in PAGES:                                       # the same content seen again
        site.observe(url)
    second = site.cycle()
    assert (second.proposals_created, second.sightings_created) == (0, 38)
    assert not second.attention and len(site.all_proposals()) == 38


def test_a_failing_page_is_surfaced_without_blocking_the_others(site):
    for url in PAGES:
        site.observe(url, retain=url != NEWS_2025)         # one body is not retained
    r = site.cycle()
    assert r.status == g2_ingest.FAILED and "not retained" in r.detail and r.attention
    assert NEWS_2025 in r.detail
    assert len(site.all_proposals()) == 38 - EXPECTED_COUNTS[NEWS_2025]


def test_a_changed_value_supersedes_and_the_old_proposal_stays_history(site):
    for url in PAGES:
        site.observe(url)
    site.cycle()
    changed = body_of(NEWS_2026).replace(b"21 in each hand", b"20 in each hand")
    site.observe(NEWS_2026, changed)
    # the retained cache copy is for the NEW observation (observe stored `changed`)
    r = site.cycle()
    assert r.status == g2_ingest.INGESTED and r.attention
    states = {(s.proposal.kind, s.proposal.value[:40], struct(s.proposal).get("hand_dof_each")):
              s for s in pr.derive_states(site.session, site.all_proposals())
              if s.proposal.source_url == NEWS_2026 and s.proposal.kind == "HAND_DOF"}
    assert {k[2]: v.state for k, v in states.items()} == {"21": pr.SUPERSEDED, "20": pr.CURRENT}


def test_only_the_current_configuration_proposals_have_a_claim_policy(site):
    for url in PAGES:
        site.ingest(site.observe(url), body_of(url))
    # only the two 2026 current-configuration proposals have a policy (owner decision 2026-10-03)
    registered = {(p.source_url, p.kind) for p in site.all_proposals() if claims.claim_policy_for(
        p.kind, p.target, p.evidence_locator, p.structured)}
    assert registered == {(NEWS_2026, "BODY_DOF"), (NEWS_2026, "COMPUTE")}
    one = next(p for p in site.all_proposals()
               if p.kind == "BODY_DOF" and p.source_url == NEWS_2025)
    answers = {pr.question_key(i): "answered" for i in range(1, len(one.review_questions) + 1)}
    pr.decide(site.session, str(one.id), pr.ACCEPT, decided_by="test", rationale="x",
              choices={**answers, pr.HOME_KEY: pr.NO_CATALOGUE_HOME})
    with pytest.raises(DiscoveryError, match="no registered field policy"):
        claims.create_claim(site.session, str(one.id), created_by="test")
    assert site.session.scalar(select(func.count()).select_from(AcceptedClaim)) == 0


def test_ingest_never_writes_a_decision_claim_or_publication(site):
    for url in PAGES:
        site.ingest(site.observe(url), body_of(url))
    assert site.session.scalar(text("SELECT count(*) FROM discovery_proposal_decision")) == 0
    assert site.session.scalar(select(func.count()).select_from(DiscoveryProposalObservation)) == 38
    assert site.session.scalar(text("SELECT is_published FROM robot WHERE slug = :s"),
                               {"s": site.slug}) is False
