"""G2-5 scheduled proposal ingestion (DR-A5): observation -> proposal/sighting -> review queue.

Offline PostgreSQL; every test runs in a rolled-back transaction. Proves the step ingests
exactly what a retained observation supports, is idempotent and self-healing, surfaces
every failure, wires into the SAME observation path the scheduler / manual dispatch /
run-now use, runs under the observer role, and has no decision, claim, audit or catalogue
effect.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from test_claim_proposal_persistence import (
    BODY,
    NEW_PRICE,
    OLD_PRICE,
    PAGE,
    World,
    replace_cell,
)
from test_claim_proposal_persistence import dsession as dsession  # noqa: F401 (fixture)
from test_claim_proposal_roles import _denied, _role
from test_discovery_stage_f_observe import Harness
from test_discovery_stage_f_observe import dsession as obs_dsession  # noqa: F401 (fixture)
from test_neura_mini_proposals import drop_cell

from app.models import DiscoveryClaimProposal, DiscoveryProposalObservation
from app.services.discovery import cache as body_cache
from app.services.discovery import g2_ingest, observe
from app.services.discovery import proposal_review as pr
from app.services.discovery.fingerprint import fingerprint
from app.services.discovery.g2_ingest import G2Ingest
from app.services.discovery.proposals import IngestReport
from app.services.discovery.sources import neura_mini_proposals as mini

pytestmark = pytest.mark.usefixtures("no_external_network")
OPERATOR = "stage-f scheduler (cadence set by Robert Konecny)"
PROPOSALS = len(mini.propose_neura_mini_claims(BODY, mini.MINI_URL).proposals)


class Site:
    """A World plus a retained-body cache, driven like one scheduler cycle."""

    def __init__(self, session, tmp_path):
        self.w = World(session)
        self.session = session
        self.cache = tmp_path / "cache"
        self.registry = {self.w.source.key: G2Ingest(page_url=mini.MINI_URL,
                                                     robot_slug=self.w.slug)}
        self.n = 0

    def observe(self, body: bytes = BODY, *, retain: bool = True, **page_kw):
        self.n += 1
        page_kw.setdefault("retrieved_at", datetime(2026, 9, 26, tzinfo=UTC)
                           + timedelta(days=self.n))
        page = self.w.page(body, **page_kw)
        if retain:
            digest = body_cache.store_body(self.cache, body)
            body_cache.record_observation(self.cache, str(page.id), {"raw_sha256": digest})
        return page

    def run(self, **kw):
        return g2_ingest.ingest_for_source(
            self.session, self.w.source, cache_dir=self.cache, operator=OPERATOR,
            registry=self.registry, **kw)

    def proposals(self):
        return list(self.session.scalars(select(DiscoveryClaimProposal).where(
            DiscoveryClaimProposal.robot_slug == self.w.slug)))

    def states(self):
        return pr.derive_states(self.session, self.proposals())

    def sightings(self):
        return self.session.scalar(select(func.count()).select_from(
            DiscoveryProposalObservation))


@pytest.fixture
def site(dsession, tmp_path):  # noqa: F811
    return Site(dsession, tmp_path)


def other_state_snapshot(session):
    tables = ("robot", "manufacturer", "evidence_source", "specification", "robot_variant",
              "pricing_offer", "availability_offer", "candidate_claim", "promotion_audit",
              "candidate_identity_decision", "discovery_proposal_decision", "accepted_claim",
              "claim_retraction", "catalogue_write_audit")
    return {t: session.execute(text(
        f"SELECT count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) "
        f"FROM {t} x")).one() for t in tables}


# ------------------------------------------------------------- ingest cases --


def test_first_observation_creates_the_proposals_and_sightings_for_review(site):
    page = site.observe()
    before = other_state_snapshot(site.session)
    r = site.run()
    assert (r.status, r.proposals_created, r.sightings_created) == (
        g2_ingest.INGESTED, PROPOSALS, PROPOSALS)
    assert r.fetched_page_id == str(page.id) and r.attention      # new proposals: review
    assert all(s.state == pr.CURRENT for s in site.states())
    assert other_state_snapshot(site.session) == before          # nothing else moved


def test_unchanged_page_adds_one_sighting_per_new_observation_and_no_duplicates(site):
    site.observe()
    site.run()
    assert site.run().status == g2_ingest.UP_TO_DATE              # same observation: no-op
    site.observe()                                                # re-fetched, same content
    r = site.run()
    assert (r.proposals_created, r.sightings_created) == (0, PROPOSALS)
    assert not r.attention                                        # nothing for a human
    assert len(site.proposals()) == PROPOSALS
    assert all(s.state == pr.CURRENT for s in site.states())
    assert site.sightings() == 2 * PROPOSALS


def test_a_not_modified_answer_adds_nothing_and_keeps_proposals_current(site):
    site.observe()
    site.run()
    site.observe(BODY, retain=False, outcome="NOT_MODIFIED", http_status=304,
                 content_hash=None)
    assert site.run().status == g2_ingest.UP_TO_DATE
    assert site.sightings() == PROPOSALS
    assert all(s.state == pr.CURRENT for s in site.states())


def test_a_cosmetic_change_creates_no_proposal_and_proposals_stay_current(site):
    site.observe()
    site.run()
    cosmetic = PAGE.replace("<footer>", "<footer>New footer banner text 2026 ").encode("utf-8")
    assert fingerprint(cosmetic, "text/html") != fingerprint(BODY, "text/html")
    site.observe(cosmetic)
    assert all(s.stale for s in site.states())                    # changed, not yet re-extracted
    r = site.run()
    assert (r.proposals_created, r.sightings_created) == (0, PROPOSALS) and not r.attention
    assert all(s.state == pr.CURRENT for s in site.states())


def test_a_substantive_value_change_supersedes_and_needs_human_re_review(site):
    site.observe()
    site.run()
    old = next(p for p in site.proposals() if p.kind == "PRICE_ESTIMATE"
               and p.edition == "Standard")
    changed = replace_cell(PAGE, OLD_PRICE, NEW_PRICE).encode("utf-8")
    site.observe(changed)
    r = site.run()
    assert r.proposals_created == 1 and r.attention
    assert pr.derive_states(site.session, [old])[0].state == pr.SUPERSEDED
    new = next(p for p in site.proposals() if p.value.startswith("21,999"))
    assert pr.derive_states(site.session, [new])[0].state == pr.CURRENT
    assert site.session.scalar(text("SELECT count(*) FROM discovery_proposal_decision")) == 0


def test_a_newly_supported_slot_is_inserted_for_review_with_no_acceptance(site):
    partial = drop_cell(PAGE, OLD_PRICE).encode("utf-8")
    site.observe(partial)
    first = site.run()
    site.observe(BODY)
    second = site.run()
    assert second.proposals_created >= 1 and second.attention
    assert second.proposals_created == len(site.proposals()) - first.proposals_created
    assert site.session.scalar(text("SELECT count(*) FROM discovery_proposal_decision")) == 0
    assert site.session.scalar(text("SELECT count(*) FROM accepted_claim")) == 0


# ---------------------------------------------------------------- failures --


def test_malformed_extractor_input_is_surfaced_and_writes_nothing(site):
    junk = b"<html><body><p>not the product page</p></body></html>"
    site.observe(junk)
    r = site.run()
    assert r.status == g2_ingest.FAILED and r.attention
    assert "no proposals" in r.detail and site.proposals() == []


def test_an_identity_failure_is_surfaced_and_writes_nothing(site):
    site.observe()
    site.session.execute(text("UPDATE robot SET name = 'Another Robot' WHERE slug = :s"),
                         {"s": site.w.slug})
    site.session.expire_all()
    r = site.run()
    assert r.status == g2_ingest.FAILED and "not the catalogue" in r.detail
    assert site.proposals() == []


def test_a_missing_retained_body_fails_visibly_then_heals_when_it_is_available(site):
    page = site.observe(retain=False)
    r = site.run()
    assert r.status == g2_ingest.FAILED and "not retained" in r.detail and r.attention
    assert site.proposals() == []
    digest = body_cache.store_body(site.cache, BODY)             # the body becomes available
    body_cache.record_observation(site.cache, str(page.id), {"raw_sha256": digest})
    assert site.run().status == g2_ingest.INGESTED


def test_a_body_that_does_not_match_the_recorded_hash_is_refused(site):
    page = site.observe()
    tampered = BODY + b"<p>tampered</p>"
    digest = body_cache.store_body(site.cache, tampered)
    (site.cache / "observations" / f"{page.id}.json").write_text(
        f'{{"raw_sha256": "{digest}"}}', encoding="utf-8")
    r = site.run()
    assert r.status == g2_ingest.FAILED and "content_hash" in r.detail
    assert site.proposals() == []


def test_no_content_yet_is_not_a_failure(site):
    assert site.run().status == g2_ingest.NO_OBSERVATION and not site.run().attention


def test_a_failing_ingest_leaves_no_partial_rows(site):
    site.observe()

    def explode(session, **kw):
        real = mini.propose_neura_mini_claims(BODY, mini.MINI_URL)
        from app.services.discovery.proposals import ingest_neura_mini_proposals
        ingest_neura_mini_proposals(session, **kw)         # writes rows ...
        assert real
        raise RuntimeError("boom after writing")           # ... then fails
    site.registry = {site.w.source.key: G2Ingest(mini.MINI_URL, site.w.slug, explode)}
    r = site.run()
    assert r.status == g2_ingest.FAILED and "boom" in r.detail
    assert site.proposals() == [] and site.sightings() == 0


def test_only_the_registered_source_is_ingested(site, dsession):  # noqa: F811
    other = World(dsession)
    assert g2_ingest.ingest_for_source(
        dsession, other.source, cache_dir=site.cache, operator=OPERATOR,
        registry=site.registry) is None
    assert set(g2_ingest.G2_INGESTS) == {"neura-robotics-official", "xpeng-official"}
    assert g2_ingest.G2_INGESTS["neura-robotics-official"].robot_slug == "4ne1-mini"


def test_scheduled_ingest_cannot_decide_claim_or_touch_the_catalogue(site):
    site.observe()
    before = other_state_snapshot(site.session)
    site.run()
    site.observe(replace_cell(PAGE, OLD_PRICE, NEW_PRICE).encode("utf-8"))
    site.run()
    assert other_state_snapshot(site.session) == before
    assert site.session.scalar(text(
        "SELECT is_published FROM robot WHERE slug = :s"), {"s": site.w.slug}) is False
    r = g2_ingest.G2Result(g2_ingest.INGESTED, proposals_created=1).as_dict()
    assert (r["writes_decisions"], r["writes_claims"], r["writes_catalogue"]) == (
        False, False, False)


# --------------------------------------------------------------- role --------


def test_the_observer_role_can_run_the_ingest_and_nothing_more(site):
    site.observe()
    role = _role(site.session, "discovery_observer.sql", "discovery_observer")
    site.session.execute(text(f"SET LOCAL ROLE {role}"))
    r = site.run()
    assert r.status == g2_ingest.INGESTED and r.proposals_created == PROPOSALS
    assert site.run().status == g2_ingest.UP_TO_DATE
    site.session.execute(text("RESET ROLE"))
    for sql in (
        "INSERT INTO discovery_proposal_decision (proposal_id, decision, decided_by, rationale)"
        " SELECT id, 'DEFER', 'x', 'x' FROM discovery_claim_proposal LIMIT 1",
        "DELETE FROM discovery_proposal_decision", "DELETE FROM accepted_claim",
        "DELETE FROM claim_retraction",   # G5-1: readable (planner), never writable
        "SELECT count(*) FROM catalogue_write_audit",
        "UPDATE discovery_claim_proposal SET gap = 'x'", "DELETE FROM discovery_claim_proposal",
        "UPDATE discovery_proposal_observation SET observed_by = 'x'",
        "UPDATE robot SET is_published = true", "UPDATE robot SET name = name",
        "INSERT INTO robot_variant (robot_id, slug, name) SELECT id, 'x', 'x' FROM robot LIMIT 1",
        "UPDATE specification SET value_text = 'x'",
        "UPDATE evidence_source SET source_title = 'x'",
    ):
        _denied(site.session, role, sql)


# ------------------------------------------------- the scheduler's own path ----


class FakeIngest:
    def __init__(self, created=0, fail=False):
        self.calls = []
        self.created, self.fail = created, fail

    def __call__(self, session, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("extractor exploded")
        # like the real ingest: record a sighting of the observation (and one proposal)
        from app.models.acquisition import FetchedPage
        from app.models.discovery import DiscoverySource
        src = session.scalar(select(DiscoverySource).where(DiscoverySource.key == kw["source_key"]))
        page = session.get(FetchedPage, kw["fetched_page_id"])
        prop = session.scalar(select(DiscoveryClaimProposal).where(
            DiscoveryClaimProposal.source_id == src.id))
        if prop is None:
            prop = DiscoveryClaimProposal(
                digest="f" * 64, slot_key="e" * 64, source_id=src.id, source_url=page.url,
                robot_slug="r", kind="VARIANT", target="robot_variant",
                representability="CLEAN", value="v", evidence_excerpt="v", evidence_locator="l",
                extraction_method="SELECTOR", extraction_confidence="HIGH",
                extractor_key="fake", extractor_version="0", origin_fetched_page_id=page.id,
                origin_crawl_run_id=page.crawl_run_id, origin_content_hash=page.content_hash,
                origin_retrieved_at=page.retrieved_at, ingested_by="fake")
            session.add(prop)
            session.flush()
        session.add(DiscoveryProposalObservation(
            proposal_id=prop.id, fetched_page_id=page.id, crawl_run_id=page.crawl_run_id,
            content_hash=page.content_hash, retrieved_at=page.retrieved_at, observed_by="fake"))
        session.flush()
        return IngestReport("PROPOSED", str(kw["fetched_page_id"]), proposals_seen=20,
                            proposals_created=self.created, observations_created=20)


@pytest.fixture
def wired(obs_dsession, tmp_path, monkeypatch):  # noqa: F811
    h = Harness(obs_dsession, tmp_path)
    s = h.source("g2")
    registry = {s.key: None}

    def install(fake):
        registry[s.key] = G2Ingest(page_url=f"https://{s.host}/products", robot_slug="r",
                                   ingest=fake)
    monkeypatch.setattr(observe, "g2_registry", lambda: registry)
    return h, s, install


def test_an_unexpected_fail_safe_rejection_needs_a_human_but_the_standing_placeholder_does_not(
        site):
    r = g2_ingest.G2Result(g2_ingest.INGESTED, rejected=[
        ["Additional interfaces / Standard", "placeholder '/' is not a value; ..."]])
    assert not r.attention                                    # the page's known, benign "/"
    r2 = g2_ingest.G2Result(g2_ingest.INGESTED, rejected=[
        ["Estimated price / Pro", "'x' is not '<n,nnn> € (excluding taxes and shipping)'"]])
    assert r2.attention and "UNEXPECTED" in r2.summary()
    site.observe(replace_cell(PAGE, OLD_PRICE, "ask us").encode("utf-8"))
    real = site.run()
    assert real.attention and real.unexpected_rejections        # a price cell changed shape


def test_the_scheduled_cycle_runs_the_ingest_after_observation_and_reports_it(wired):
    h, s, install = wired
    fake = FakeIngest(created=0)
    install(fake)
    result, by_key, _ = h.cycle()
    obs = by_key[s.key]
    assert obs.status == "COMPLETED" and len(fake.calls) == 1
    call = fake.calls[0]
    assert call["source_key"] == s.key and call["body"] and call["ingested_by"].startswith(
        "stage-f scheduler")
    assert obs.counts["g2_ingest"]["status"] == "INGESTED"
    assert "G2 proposals ingested" in obs.detail
    # an unchanged second cycle is conditional: no new content, nothing re-ingested
    h.advance(48)
    _, by_key2, _ = h.cycle()
    assert len(fake.calls) == 1 and by_key2[s.key].counts["g2_ingest"]["status"] == "UP_TO_DATE"


def test_new_proposals_make_the_cycle_need_a_human_but_unchanged_ones_do_not(wired):
    h, s, install = wired
    install(FakeIngest(created=3))
    _, by_key, _ = h.cycle()
    assert by_key[s.key].counts["g2_attention"] is True and by_key[s.key].attention


def test_an_ingest_failure_is_surfaced_and_the_observation_is_preserved(wired):
    h, s, install = wired
    install(FakeIngest(fail=True))
    result, by_key, _ = h.cycle()
    obs = by_key[s.key]
    assert obs.status == "COMPLETED"                           # the observation stands
    assert obs.counts["g2_ingest"]["status"] == "FAILED" and obs.counts["g2_attention"]
    assert "G2 INGEST FAILED" in obs.detail and "RuntimeError" in obs.detail
    assert obs.attention and result.exit_code == observe.EXIT_ATTENTION
    assert any("G2 INGEST FAILED" in line for line in result.lines())
    from app.models.acquisition import FetchedPage
    assert h.session.scalar(select(func.count()).select_from(FetchedPage).where(
        FetchedPage.source_id == h._src(s).id)) >= 1       # pages preserved


def test_plan_mode_never_ingests_and_run_now_uses_the_same_path(wired):
    h, s, install = wired
    fake = FakeIngest()
    install(fake)
    h.cycle(plan_only=True)
    assert fake.calls == []                                    # no request, no write
    h.cycle()                                                  # scheduled
    assert len(fake.calls) == 1
    h.advance(1)                                               # NOT_DUE for the schedule
    _, skipped, _ = h.cycle()
    assert skipped[s.key].status == "NOT_DUE" and len(fake.calls) == 1
    h.session.execute(text("UPDATE crawl_run SET status = status WHERE false"))
    # run-now skips only the cadence wait; the observation (and so the ingest check) runs
    _, now_run, _ = h.cycle(only=s.key, run_now=True)
    assert now_run[s.key].status == "COMPLETED"
    assert now_run[s.key].counts["g2_ingest"]["status"] in ("UP_TO_DATE", "INGESTED")


def test_an_unregistered_source_gets_no_g2_step_at_all(obs_dsession, tmp_path):  # noqa: F811
    h = Harness(obs_dsession, tmp_path)
    s = h.source("plain")
    _, by_key, _ = h.cycle()
    assert "g2_ingest" not in by_key[s.key].counts and "G2" not in by_key[s.key].detail


def test_the_schedule_and_cadence_are_unchanged():
    import pathlib
    wf = (pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows"
          / "discovery-observe.yml").read_text(encoding="utf-8")
    assert 'cron: "37 6 * * 1,4"' in wf                       # Monday and Thursday 06:37 UTC
    # a scheduled event observes every enabled+scheduled source (each cadence decides)
    assert "ONLY: ${{ github.event_name == 'schedule' && '' || inputs.source }}" in wf
    assert "RUN_NOW: ${{ github.event_name == 'schedule' && 'false'" in wf
