"""G5-2: Lane B controlled fetching, document discovery, the 4NE1 Mini datasheet regression.

Offline PostgreSQL (rolled-back transactions) and httpx.MockTransport: no socket is ever opened.
Pins the owner's boundaries: a document host is fetched only inside its approved host/path, only
through the governed acquisition path, only when a reviewed extractor reads the document; nothing
is accepted, decided, claimed, written to the catalogue, published, or turned UNKNOWN.
"""
from __future__ import annotations

import hashlib
import io
import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, text
from test_claim_proposal_persistence import World
from test_discovery_stage_f_observe import dsession as dsession  # noqa: F401 (fixture)

from app.models import DiscoveryClaimProposal
from app.models.acquisition import CrawlRun, FetchedPage
from app.models.discovery import DiscoverySource
from app.services.discovery import cache as body_cache
from app.services.discovery import enrichment as en
from app.services.discovery import enrichment_fetch as ef
from app.services.discovery import enrichment_plan as ep
from app.services.discovery import g2_ingest
from app.services.discovery.fetcher import FetchLimits, HttpFetcher
from app.services.discovery.observe import CycleResult
from app.services.discovery.proposals import ingest_neura_mini_datasheet_proposals
from app.services.discovery.sources import neura_mini_datasheet_proposals as ds
from app.services.readiness import RobotRecord

pytestmark = pytest.mark.usefixtures("no_external_network")

PX = "https://neurarobotics.px.media"
MAIN = "https://maker.example"
DATASHEET = ds.DATASHEET_URL
BASE = datetime(2026, 10, 5, 6, 37, tzinfo=UTC)

# ----------------------------------------------------------------- a synthetic datasheet PDF

PAGE1 = ["Cognitive Intelligence in Compact Form", "Natural", "Language", "Interaction",
         "Computer Vision", "Reinforcement", "Learning", "Height", "{height} cm",
         "4\222 4\224", "Speed", "Max.", "4.6 km/h", "2.9 mph", "Interfaces",
         "Wi-Fi 6, Gigabit", "Ethernet, ROS2,", "C++, & Python", "SDK , NeuraSync", "Payload",
         "3 kg", "6.6 lbs", "Safety*", "Human", "detection", "Operating", "Time (h)", "24/7",
         "Voice", "Recognition", "Weight", "36 kg", "79 lbs", "DoF*",
         "* Safety human detection sensors are optional and available at an additional cost",
         "* DoF indicates the degrees of freedom of the base unit only and does not include "
         "hands or end effectors,", "which may each have up to 12 DoF independently.", "25",
         "Motion", "Endurance (h)", "2.5", "Designed and engineered in Germany",
         "All rights reserved V1 / 01.01.2026"]
PAGE2 = ["4NE1 Mini brings full cognitive capabilities within reach in a smaller form.",
         "Reserve now to be among the first to receive your 4NE1 Mini in Spring 2026.",
         "Reserve", "4NE1 Mini", "All rights reserved V1 / 01.01.2026"]


def make_pdf(pages: list[list[str]]) -> bytes:
    """A minimal valid PDF whose text layer reads line by line (Helvetica, WinAnsi)."""
    objs: list[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(b"")  # pages placeholder
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
               b"/Encoding /WinAnsiEncoding >>")
    kids = []
    for lines in pages:
        ops = ["BT", "/F1 12 Tf", "14 TL", "50 780 Td"]
        for line in lines:
            esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops += [f"({esc}) Tj", "T*"]
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        c = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>" % (font, c)))
    objs[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
              % (len(objs) + 1, xref))
    return out.getvalue()


def datasheet(height: str = "132", drop: str | None = None) -> bytes:
    p1 = [ln.replace("{height}", height) for ln in PAGE1]
    if drop:
        p1 = [ln for ln in p1 if drop not in ln]
    return make_pdf([p1, PAGE2])


# ----------------------------------------------------------------- the extractor (pure)

def test_extractor_reads_the_datasheet_values_label_anchored():
    r = ds.propose_neura_mini_datasheet_claims(datasheet(), DATASHEET)
    assert r.status == ds.PROPOSED and r.rejected == ()
    by = {p.kind: p for p in r.proposals}
    assert len(by) == 11
    assert by["DATASHEET_HEIGHT"].structured == (("cm", "132"),)
    assert by["DATASHEET_WEIGHT"].structured == (("kg", "36"),)
    assert by["DATASHEET_PAYLOAD"].gap and "per arm" in by["DATASHEET_PAYLOAD"].gap
    assert by["DATASHEET_DOF"].structured == (("dof_base_unit", "25"),
                                              ("hand_dof_up_to_each", "12"))
    assert by["DATASHEET_DOCUMENT_VERSION"].value == "V1 / 01.01.2026"
    assert by["DATASHEET_AVAILABILITY_STATEMENT"].value == "Spring 2026"
    for p in r.proposals:
        assert p.claim_status == "NOT_VERIFIED" and p.method == "PATTERN"
        assert p.evidence.excerpt and p.edition is None
        if p.kind != "DATASHEET_DOCUMENT_VERSION":
            assert any("edition" in q for q in p.review_required)


def test_unsupported_semantic_mappings_stay_unmapped():
    by = {p.kind: p for p in ds.propose_neura_mini_datasheet_claims(
        datasheet(), DATASHEET).proposals}
    assert by["DATASHEET_SPEED"].target.startswith("UNMAPPED")        # not walking speed
    assert by["DATASHEET_OPERATING_TIME"].target.startswith("UNMAPPED")  # not runtime
    assert by["DATASHEET_SAFETY_OPTION"].representability == ds.UNREPRESENTABLE
    blob = " ".join(p.target + p.value for p in by.values()).lower()
    assert "has_vision" not in blob and "walk_speed" not in blob.replace("walking speed", "")


def test_changed_value_is_a_new_proposal_unchanged_values_keep_their_digest():
    a = {p.kind: p.digest for p in ds.propose_neura_mini_datasheet_claims(
        datasheet(), DATASHEET).proposals}
    b = {p.kind: p.digest for p in ds.propose_neura_mini_datasheet_claims(
        datasheet("133"), DATASHEET).proposals}
    assert {k for k in a if a[k] != b[k]} == {"DATASHEET_HEIGHT"}


def test_a_label_that_is_gone_is_rejected_not_guessed():
    r = ds.propose_neura_mini_datasheet_claims(datasheet(drop="Weight"), DATASHEET)
    assert "DATASHEET_WEIGHT" not in {p.kind for p in r.proposals}
    assert [k for k, _ in r.rejected] == ["DATASHEET_WEIGHT"]


def test_extractor_fail_safes():
    assert ds.propose_neura_mini_datasheet_claims(
        b"<html>not a pdf</html>", DATASHEET).status == ds.NO_PROPOSALS
    assert ds.propose_neura_mini_datasheet_claims(
        datasheet(), PX + "/plk/other.pdf").status == ds.OUT_OF_SCOPE
    other = make_pdf([["Height", "180 cm", "4\222 4\224"], ["something else"]])
    assert ds.propose_neura_mini_datasheet_claims(other, DATASHEET).status == ds.NO_PROPOSALS


# ----------------------------------------------------------------- the world

class Net:
    """px.media + a maker site behind MockTransport; records every request."""

    def __init__(self) -> None:
        self.pages: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.redirects: dict[tuple[str, str], str] = {}
        self.robots = "User-agent: *\nAllow: /\n"
        self.requests: list[tuple[str, str]] = []
        self.t = 0.0

    def put(self, url: str, body: bytes, ctype: str) -> None:
        m = re.match(r"https://([^/]+)(/.*)", url)
        self.pages[(m.group(1), m.group(2))] = (body, ctype)

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        self.requests.append((host, path))
        if path == "/robots.txt":
            return httpx.Response(200, text=self.robots, headers={"content-type": "text/plain"})
        if (host, path) in self.redirects:
            return httpx.Response(301, headers={"location": self.redirects[(host, path)]})
        page = self.pages.get((host, path))
        if page is None:
            return httpx.Response(404)
        body, ctype = page
        etag = '"' + hashlib.sha256(body).hexdigest()[:12] + '"'
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers={"etag": etag})
        return httpx.Response(200, content=body, headers={"content-type": ctype, "etag": etag})

    def fetcher_for(self, source, urls, kill) -> HttpFetcher:
        return HttpFetcher(limits=FetchLimits(page_cap=max(1, len(urls))),
                           transport=httpx.MockTransport(self.handler),
                           monotonic=lambda: self.t, sleep=lambda s: setattr(self, "t", self.t + s),
                           kill_switch=kill)

    def fetched(self) -> list[tuple[str, str]]:
        return [r for r in self.requests if r[1] != "/robots.txt"]


class Lane:
    def __init__(self, session, tmp_path) -> None:
        self.session = session
        self.w = World(session)
        self.cache = tmp_path / "cache"
        self.net = Net()
        self.clock = BASE
        tag = uuid.uuid4().hex[:8]
        reviewed = dict(tos_status="ALLOWED", robots_status="ALLOWED",
                        eligibility_reviewed_at=datetime(2026, 10, 4, tzinfo=UTC),
                        eligibility_reviewed_by="owner", is_enabled=True)
        main = self.w.source
        main.homepage_url, main.allowed_path_prefixes = MAIN + "/", ["/product/"]
        main.observation_interval_hours = 48
        main.observation_cadence_set_by = "robert"
        main.observation_cadence_set_at = datetime(2026, 10, 2, tzinfo=UTC)
        for k, v in reviewed.items():
            setattr(main, k, v)
        self.docs = DiscoverySource(
            key=f"docs-{tag}", name="docs (test)", source_class="OFFICIAL_DOCUMENT",
            homepage_url=PX + "/", allowed_path_prefixes=["/plk/"],
            observation_interval_hours=168, observation_cadence_set_by="Robert Konecny",
            observation_cadence_set_at=datetime(2026, 10, 4, tzinfo=UTC), **reviewed)
        session.add(self.docs)
        session.flush()
        self.registry = {self.docs.key: g2_ingest.G2Ingest(
            page_url=DATASHEET, robot_slug=self.w.slug,
            ingest=ingest_neura_mini_datasheet_proposals)}
        self.net.put(DATASHEET, datasheet(), "application/pdf")

    def now(self) -> datetime:
        return self.clock

    def advance(self, days: float) -> None:
        self.clock += timedelta(days=days)
        self.net.t += days * 86400

    def inputs(self, extra_urls=(), commercial="UNKNOWN", datasheet_known=True):
        rec = RobotRecord(
            slug=self.w.slug, name="4NE1 Mini", manufacturer_slug="maker", is_published=True,
            summary="x" * 40, commercial_status=commercial,
            official_url=MAIN + "/product/4ne1-mini")
        urls = [*([("specification", DATASHEET)] if datasheet_known else []), *extra_urls]
        return [ep.PlanInput(en.RobotInput(rec, tuple(urls), announced_year=2026))]

    def states(self) -> dict[str, ep.UrlState]:
        return {u: ep.UrlState(p.retrieved_at, p.content_hash, None, str(p.id))
                for u, p in self._last().items()}

    def plans(self, extra_urls=(), commercial="UNKNOWN", datasheet_known=True, bound=8):
        return ep.plan_all_from_inputs(
            self.inputs(extra_urls, commercial, datasheet_known),
            {"maker": [self.w.source, self.docs]}, self.states(), self.clock, bound=bound)

    def _last(self) -> dict[str, FetchedPage]:
        out: dict[str, FetchedPage] = {}
        for p in self.session.scalars(select(FetchedPage).where(
                FetchedPage.content_hash.is_not(None)).order_by(FetchedPage.retrieved_at)):
            out[p.url] = p
        return out

    def run(self, *, plan_only=False, plans=None, **kw) -> ef.LaneBResult:
        return ef.run_lane_b(
            self.session, plans if plans is not None else self.plans(),
            {"maker": [self.w.source, self.docs]}, plan_only=plan_only, cache_dir=self.cache,
            now=self.now, fetcher_for=self.net.fetcher_for,
            checkpoint=None, registry=self.registry, radar_sources={self.w.source.key}, **kw)

    def proposals(self) -> list[DiscoveryClaimProposal]:
        return list(self.session.scalars(select(DiscoveryClaimProposal).where(
            DiscoveryClaimProposal.source_id == self.docs.id)))

    def runs(self) -> list[CrawlRun]:
        return list(self.session.scalars(select(CrawlRun).where(
            CrawlRun.source_id == self.docs.id)))


@pytest.fixture
def lane(dsession, tmp_path) -> Lane:  # noqa: F811
    return Lane(dsession, tmp_path)


def state(session) -> dict:
    tables = ("robot", "manufacturer", "evidence_source", "specification", "robot_variant",
              "pricing_offer", "availability_offer", "candidate_claim", "promotion_audit",
              "discovery_proposal_decision", "accepted_claim", "claim_retraction",
              "catalogue_write_audit")
    return {t: session.execute(text(
        f"SELECT count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) "
        f"FROM {t} x")).one() for t in tables}


# ----------------------------------------------------------------- the 4NE1 Mini regression

def test_datasheet_flows_from_planner_target_to_proposals_for_review(lane):
    before = state(lane.session)
    plan = lane.plans()[lane.docs.key]
    assert [t.url for t in plan.planned] == [DATASHEET]
    assert plan.planned[0].source == lane.docs.key and plan.planned[0].origin == (
        "CATALOGUE_ENRICHMENT")
    res = lane.run()
    docs_run = next(r for r in res.runs if r.key == lane.docs.key)
    assert docs_run.status == ef.FETCHED and docs_run.urls == [DATASHEET]
    assert lane.net.fetched() == [("neurarobotics.px.media", "/plk/Jj/4NE1Minidatasheet.pdf")]
    run = lane.runs()[0]
    assert (run.trigger, run.adapter_key) == ("SCHEDULED", "g5-lane-b")
    props = lane.proposals()
    assert len(props) == 11 and {p.extractor_key for p in props} == {ds.EXTRACTOR_KEY}
    assert all(p.claim_status == "NOT_VERIFIED" for p in props)
    assert res.proposals_created == 11 and res.commercial_proposals == 1   # the availability line
    assert res.attention is True                       # new proposals need a human
    assert state(lane.session) == before                # nothing decided / claimed / written
    assert lane.session.scalar(select(func.count()).select_from(
        text("discovery_proposal_decision"))) == 0


def test_radar_cadence_source_targets_are_deferred_not_fetched(lane):
    res = lane.run()
    assert [h for h, _ in lane.net.fetched()] == ["neurarobotics.px.media"]
    assert MAIN + "/product/4ne1-mini" in res.deferred_radar
    assert next(r for r in res.runs if r.key == lane.w.source.key).status == ef.DEFERRED_RADAR


def test_plan_only_makes_no_request_and_no_write(lane):
    before = state(lane.session)
    res = lane.run(plan_only=True)
    assert lane.net.requests == [] and lane.runs() == [] and lane.proposals() == []
    assert any(r.status == ef.WOULD_FETCH for r in res.runs)
    assert state(lane.session) == before


def test_unchanged_document_is_quiet_and_not_refetched_inside_the_band(lane):
    lane.run()
    n = len(lane.net.requests)
    lane.advance(3)                                    # inside the 7-day HIGH interval
    res = lane.run()
    assert len(lane.net.requests) == n                 # not due: not even requested
    assert all(r.status == ef.DEFERRED_RADAR for r in res.runs) or not any(
        r.status == ef.FETCHED for r in res.runs)
    assert res.robots_deferred_cadence == 0 or res.proposals_created == 0
    lane.advance(5)                                    # now due: conditional GET -> 304
    res = lane.run()
    assert res.proposals_created == 0 and res.attention is False
    assert res.pages["changed"] == 0 and len(lane.proposals()) == 11
    assert lane.net.fetched()[-1] == ("neurarobotics.px.media", "/plk/Jj/4NE1Minidatasheet.pdf")


def test_changed_document_yields_only_the_changed_proposal_old_one_preserved(lane):
    lane.run()
    lane.advance(8)
    lane.net.put(DATASHEET, datasheet("133"), "application/pdf")
    res = lane.run()
    assert res.pages["changed"] == 1 and res.proposals_created == 1
    heights = [p for p in lane.proposals() if p.kind == "DATASHEET_HEIGHT"]
    assert sorted(p.value for p in heights) == ["132 cm", "133 cm"]    # history preserved
    assert len(lane.proposals()) == 12


def test_not_restated_is_reported_but_nothing_is_deleted_or_unknowned(lane):
    lane.run()
    lane.advance(8)
    lane.net.put(DATASHEET, datasheet(drop="Weight"), "application/pdf")
    before = state(lane.session)
    res = lane.run()
    kinds = {n["kind"] for n in res.not_restated}
    assert "DATASHEET_WEIGHT" in kinds
    assert len(lane.proposals()) == 11                  # no deletion, no new proposal
    assert state(lane.session) == before                # no claim / catalogue / decision change
    assert any(k == "DATASHEET_WEIGHT" for k, _ in
               ((n["kind"], n["url"]) for n in res.not_restated))


def test_not_restated_is_judged_per_page_of_a_multi_page_source(lane):
    """Live finding 2026-10-04: XPENG's four pages produced 114 false NOT_RESTATED because each
    page was compared with the proposals of the OTHER pages of the same source and robot."""
    lane.run()
    first = lane.proposals()[0]
    clone = DiscoveryClaimProposal(**{
        c.name: getattr(first, c.name) for c in DiscoveryClaimProposal.__table__.columns
        if c.name not in ("id", "proposal_seq", "created_at")})
    clone.digest = "d" * 64
    clone.slot_key = "e" * 64
    clone.source_url = PX + "/plk/Jj/another-page.pdf"      # proposed from a DIFFERENT page
    lane.session.add(clone)
    lane.session.flush()
    lane.advance(8)
    res = lane.run()
    assert res.not_restated == []


def test_changed_document_without_a_registered_extractor_is_reported_only(lane):
    other = PX + "/plk/Jj/other-datasheet.pdf"
    lane.net.put(other, make_pdf([["v1"]]), "application/pdf")
    lane.run(plans=lane.plans(extra_urls=[("specification", other)]))
    lane.advance(8)
    lane.net.put(other, make_pdf([["v2"]]), "application/pdf")
    res = lane.run(plans=lane.plans(extra_urls=[("specification", other)]))
    assert other in res.changed_no_extractor
    assert not [p for p in lane.proposals() if p.source_url == other]


def test_nothing_outside_plk_is_fetched_and_a_redirect_out_is_not_followed(lane):
    outside = PX + "/private/secret.pdf"
    lane.net.put(outside, b"secret", "application/pdf")
    lane.net.redirects[("neurarobotics.px.media", "/plk/Jj/4NE1Minidatasheet.pdf")] = (
        PX + "/private/secret.pdf")
    plans = lane.plans(extra_urls=[("specification", outside)])
    assert outside in {t.url for t in plans[lane.docs.key].skipped
                       if t.decision == ep.SOURCE_REVIEW_REQUIRED}
    res = lane.run(plans=plans)
    assert ("neurarobotics.px.media", "/private/secret.pdf") not in lane.net.requests
    assert lane.proposals() == []
    page = lane.session.scalars(select(FetchedPage).where(
        FetchedPage.source_id == lane.docs.id, FetchedPage.url == DATASHEET)).one()
    assert page.outcome == "ERROR" and "redirect_outside_policy" in page.error_class
    assert res.pages["errors"] == 1


def test_robots_disallow_halts_disables_and_is_not_retried(lane):
    lane.net.robots = "User-agent: *\nDisallow: /plk/\n"
    plans_before = lane.plans()
    res = lane.run(plans=plans_before)
    assert next(r for r in res.runs if r.key == lane.docs.key).status == ef.HALTED
    assert lane.docs.is_enabled is False                # robots disallow disables the source
    n = len(lane.net.requests)
    again = lane.run()
    assert len(lane.net.requests) == n                  # a disabled source authorizes nothing
    assert [r for r in again.runs if r.key == lane.docs.key] == []   # not even planned
    stale_plan = lane.run(plans=plans_before)                          # a stale plan is refused too
    assert next(r for r in stale_plan.runs if r.key == lane.docs.key).status == ef.REFUSED
    assert len(lane.net.requests) == n


def test_kill_switch_stops_before_any_request(lane):
    res = lane.run(kill_switch_for=lambda key: (lambda: key == lane.docs.key))
    assert next(r for r in res.runs if r.key == lane.docs.key).status == ef.KILL_SWITCH
    assert lane.net.requests == []


def test_a_halted_run_is_not_retried_automatically(lane):
    lane.net.robots = "User-agent: *\nDisallow: /plk/\n"
    lane.run()
    lane.docs.is_enabled = True                         # a human re-enables after review
    lane.net.robots = "User-agent: *\nAllow: /\n"
    n = len(lane.net.requests)
    quiet = lane.run()                                  # not due (7d cadence): quiet
    assert [r for r in quiet.runs if r.key == lane.docs.key] == []
    assert len(lane.net.requests) == n
    lane.advance(8)                                     # due again: still not retried by itself
    res = lane.run()
    assert next(r for r in res.runs if r.key == lane.docs.key).status == ef.NEEDS_HUMAN
    assert len(lane.net.requests) == n


# ----------------------------------------------------------------- document discovery

def retain_product_page(lane, html: str) -> str:
    url = MAIN + "/product/4ne1-mini"
    page = FetchedPage(
        crawl_run_id=lane.w.run.id, source_id=lane.w.source.id, url=url, http_status=200,
        content_type="text/html", content_hash="h" * 64, outcome="FETCHED",
        retrieved_at=BASE - timedelta(days=1))
    lane.session.add(page)
    lane.session.flush()
    digest = body_cache.store_body(lane.cache, html.encode())
    body_cache.record_observation(lane.cache, str(page.id), {"raw_sha256": digest})
    return url


def known_plans(lane, with_datasheet: bool):
    return lane.plans(datasheet_known=with_datasheet)


def test_new_datasheet_link_on_an_approved_page_becomes_a_fetched_target(lane):
    html = (f'<html><body><a href="{DATASHEET}">Datasheet</a>'
            f'<a href="{PX}/plk/Jj/unreviewed.pdf">Other</a>'
            f'<a href="{PX}/private/x.pdf">Private</a>'
            '<a href="/product/other">page</a></body></html>')
    retain_product_page(lane, html)
    res = lane.run(plans=known_plans(lane, with_datasheet=False))
    status = {d.url: d.status for d in res.discovered}
    assert status[DATASHEET] == "TARGET"
    assert status[PX + "/plk/Jj/unreviewed.pdf"] == "ELIGIBLE_NO_EXTRACTOR"
    assert status[PX + "/private/x.pdf"] == en.NEEDS_SOURCE_APPROVAL
    assert lane.net.fetched() == [("neurarobotics.px.media", "/plk/Jj/4NE1Minidatasheet.pdf")]
    assert len(lane.proposals()) == 11 and res.proposals_created == 11


def test_discovered_document_follows_the_band_cadence_afterwards(lane):
    html = f'<html><body><a href="{DATASHEET}">Datasheet</a></body></html>'
    retain_product_page(lane, html)
    lane.run(plans=known_plans(lane, with_datasheet=False))
    n = len(lane.net.requests)
    lane.advance(2)
    res = lane.run(plans=known_plans(lane, with_datasheet=False))
    assert len(lane.net.requests) == n                  # observed once: not re-fetched
    assert res.discovered == []                         # no longer a discovery: quiet


def test_document_links_are_one_level_pdf_only_and_normalized():
    html = (b'<a href="/plk/a.pdf?utm_source=x#p2">a</a><a href="https://h.example/b.PDF">b</a>'
            b'<a href="/page">c</a><a href="mailto:x@y.z">d</a>')
    assert ef.document_links(html, "https://h.example/product/x") == [
        "https://h.example/b.PDF", "https://h.example/plk/a.pdf"]


# ----------------------------------------------------------------- firewall / reporting

def test_lane_b_has_no_write_surface_beyond_the_governed_acquisition():
    import inspect
    src = inspect.getsource(ef)
    for banned in ("ProposalDecision(", "AcceptedClaim(", "is_published", "commercial_status =",
                   "session.delete", "requests.", "httpx.get", "urlopen"):
        assert banned not in src


def test_unknown_and_stale_fields_alone_create_no_proposals(lane):
    # a robot with UNKNOWN everything and only radar-source URLs: Lane B proposes nothing
    plans = lane.plans(datasheet_known=False)
    plans[lane.docs.key] = ep.plan_manufacturer([], [lane.w.source, lane.docs], {}, lane.clock,
                                                source_key=lane.docs.key)
    res = lane.run(plans=plans)
    assert res.proposals_created == 0 and lane.proposals() == [] and lane.runs() == []


def test_cycle_report_and_exit_status_reflect_lane_b(lane):
    quiet = CycleResult(started_at=BASE, plan_only=False)
    assert quiet.exit_code == 0
    res = lane.run()
    cycle = CycleResult(started_at=BASE, plan_only=False, lane_b=res)
    assert cycle.exit_code == 4                          # new proposals need a human
    out = "\n".join(cycle.lines())
    assert out.index("NEW MODEL RADAR") < out.index("CATALOGUE ENRICHMENT") < out.index("lane B")
    d = cycle.as_dict()["lanes"]["CATALOGUE_ENRICHMENT"]["lane_b"]
    assert d["new_facts_proposed"] == 11 and d["writes_catalogue"] is False
    failed = ef.LaneBResult(plan_only=False, error="RuntimeError")
    assert CycleResult(started_at=BASE, plan_only=False, lane_b=failed).exit_code == 1
    calm = ef.LaneBResult(plan_only=False)
    assert CycleResult(started_at=BASE, plan_only=False, lane_b=calm).exit_code == 0


def test_g2_registry_wires_the_document_source():
    cfg = g2_ingest.G2_INGESTS["neura-documents-official"]
    assert cfg.page_urls == (DATASHEET,) and cfg.robot_slug == "4ne1-mini"
    assert cfg.ingest is ingest_neura_mini_datasheet_proposals
