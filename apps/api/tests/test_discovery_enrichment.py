"""G5-1: the Lane B (catalogue enrichment) planner. Pure, read-only, fetches nothing.

Pins the owner decisions of 2026-10-04: D1 (known-URL scope), D2 (exact 7/21/60-day cadence,
90-day commercial and 365-day spec freshness) and the PUBLICATION FIREWALL: coverage, priority
and freshness are never publication gates.
"""
from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta

import pytest
from test_g4_3_readiness import sparse

from app.models.discovery import DiscoverySource
from app.services import readiness as rd
from app.services.discovery import enrichment as en
from app.services.discovery.observe import CycleResult
from app.services.readiness import AvailabilityRow, ImageRow, PricingRow, RobotRecord

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
HOST = "https://maker-x.example/"


def source(*, enabled=True, prefixes=("/robots",), tos="ALLOWED") -> DiscoverySource:
    return DiscoverySource(
        key="maker-x-official", name="Maker X", source_class="MANUFACTURER", homepage_url=HOST,
        tos_status=tos, robots_status="ALLOWED", is_enabled=enabled,
        eligibility_reviewed_at=NOW, eligibility_reviewed_by="owner",
        allowed_path_prefixes=list(prefixes))


def rich(**over) -> RobotRecord:
    """Mature, well-covered, commercial, with fresh evidence."""
    core = dict(height_cm=170, weight_kg=60, payload_kg=5, runtime_minutes=120, battery_wh=900,
                mobility="biped", degrees_of_freedom=40, autonomy="L2", has_manipulation=True,
                has_sdk=True, has_api=True, ros_support=True, has_teleoperation=True,
                has_vision=True, has_language_ui=True, announced_year=2022)
    base = dict(
        slug="rich", name="Rich", manufacturer_slug="maker-x", is_published=True,
        summary="A mature, well documented humanoid robot sold commercially.",
        commercial_status="COMMERCIAL", official_url=HOST + "robots/rich", core=core,
        variants=(("std", "Std"),), pricing=(PricingRow(None, "LIST", 1.0, True),),
        availability=(AvailabilityRow(None, "AVAILABLE", None, None, None, True),),
        deployments=(True,), images=(ImageRow(
            "https://maker-x.example/i.png", HOST + "robots/rich", "Maker X", "VERIFIED",
            "OK", "OFFICIAL_MANUFACTURER_MEDIA", None),),
        status_evidence=1, source_count=5)
    base.update(over)
    return RobotRecord(**base)


def inp(rec, *, commercial_days=10, spec_days=10, urls=(), docs=True, year=2022):
    return en.RobotInput(
        rec, tuple(urls),
        NOW - timedelta(days=commercial_days) if commercial_days is not None else None,
        NOW - timedelta(days=spec_days) if spec_days is not None else None, docs, year)


def plan(i, src=None, last=None):
    return en.plan_robot(i, src, last, NOW)


# ------------------------------------------------------------------ gap profile

def test_gap_profile_lists_unknown_areas_in_buyer_priority_order():
    g = en.gap_profile(inp(sparse(), year=2026), NOW)
    assert g.areas["height"] == en.UNKNOWN_STATE and g.areas["dof"] != en.UNKNOWN_STATE
    assert g.unknown.index("availability") < g.unknown.index("payload") < g.unknown.index("sdk")
    assert "dof" not in g.unknown and "availability" in g.high_value_unknown
    assert g.band == "LOW"
    assert json.dumps(g.as_dict())  # machine-readable


def test_complete_robot_has_no_gaps():
    g = en.gap_profile(inp(rich()), NOW)
    assert g.unknown == () and g.old == ()


def test_unknown_is_not_an_error_and_not_a_value():
    rec = sparse()
    assert rec.core.get("height_cm") is None
    en.gap_profile(inp(rec), NOW)
    assert rec.core.get("height_cm") is None   # planning never fills a value


# ------------------------------------------------------------------ priority

def test_high_priority_triggers():
    assert plan(inp(sparse(), year=2026)).priority == en.HIGH                       # recent
    assert plan(inp(sparse(is_published=True))).priority == en.HIGH                 # published LOW
    assert plan(inp(rich(commercial_status="UNKNOWN"))).priority == en.HIGH
    assert plan(inp(rich(not_yet_reviewed=2))).priority == en.HIGH                  # pending
    assert plan(inp(rich(), commercial_days=120)).priority == en.HIGH               # stale status


def test_medium_priority_triggers():
    assert plan(inp(rich(pricing=()))).priority == en.MEDIUM          # price UNKNOWN
    assert plan(inp(rich(), spec_days=400)).priority == en.MEDIUM     # stale specs only
    assert plan(inp(rich(core={**rich().core, "has_sdk": None}))).priority == en.MEDIUM


def test_low_priority_for_stable_and_historical():
    assert plan(inp(rich())).priority == en.LOW
    hist = plan(inp(rich(commercial_status="DISCONTINUED"), commercial_days=500))
    assert hist.priority == en.LOW


def test_priority_does_not_change_maturity_or_publication():
    rec = rich(commercial_status="UNKNOWN", is_published=False)
    before = (rec.commercial_status, rec.is_published)
    row = plan(inp(rec))
    assert row.priority == en.HIGH
    assert (rec.commercial_status, rec.is_published) == before
    assert row.commercial_status == "UNKNOWN" and row.is_published is False


# ------------------------------------------------------------------ cadence (D2: exact)

@pytest.mark.parametrize("band,days", [(en.HIGH, 7), (en.MEDIUM, 21), (en.LOW, 60)])
def test_exact_band_intervals(band, days):
    last = NOW - timedelta(days=3)
    assert en.BAND_INTERVAL[band] == timedelta(days=days)
    assert en.next_eligible_at(band, last) == last + timedelta(days=days)
    assert en.next_eligible_at(band, None) is None


def test_due_now_only_at_exact_interval_boundary():
    src = source()   # HIGH priority below
    rec2 = sparse(is_published=True, official_url=HOST + "robots/x")
    i = inp(rec2)
    assert plan(i, src, NOW - timedelta(days=7)).due == en.DUE_NOW
    assert plan(i, src, NOW - timedelta(days=7) + timedelta(seconds=1)).due == en.NOT_DUE
    assert plan(i, src, None).due == en.DUE_NOW


# ------------------------------------------------------------------ freshness (D2)

def test_commercial_fields_old_after_90_days():
    for days, state in ((90, en.KNOWN_CURRENT), (91, en.KNOWN_BUT_OLD)):
        g = en.gap_profile(inp(rich(), commercial_days=days), NOW)
        assert g.areas["price"] == state == g.areas["availability"] == g.areas["commercial_status"]


def test_spec_facts_old_after_365_days_and_commercial_unaffected():
    g = en.gap_profile(inp(rich(), spec_days=366), NOW)
    assert g.areas["payload"] == en.KNOWN_BUT_OLD and g.areas["price"] == en.KNOWN_CURRENT
    assert en.gap_profile(inp(rich(), spec_days=365), NOW).areas["payload"] == en.KNOWN_CURRENT


def test_staleness_never_unknowns_or_proposes():
    rec = rich()
    g = en.gap_profile(inp(rec, commercial_days=999, spec_days=999), NOW)
    assert en.REVIEW_REQUIRED not in g.areas.values()      # needs observed evidence: G5-2
    assert g.areas["payload"] == en.KNOWN_BUT_OLD != en.UNKNOWN_STATE
    assert rec.core["payload_kg"] == 5 and rec.pricing and rec.availability


# ------------------------------------------------------------------ known URLs (D1)

def test_known_url_aggregation_and_normalization():
    rec = rich(official_url="HTTPS://Maker-X.example/robots/rich/?utm_source=x#frag")
    i = inp(rec, urls=[("specification", HOST + "robots/rich"),
                       ("pricing_offer", HOST + "robots/rich/"),
                       ("commercial_status", HOST + "news/launch")])
    known = en.collect_known_urls(i)
    assert list(known) == sorted(known)                               # deterministic
    assert known[HOST + "robots/rich"] == ("image", "official_url", "pricing_offer",
                                           "specification")
    assert HOST + "news/launch" in known and len(known) == 2


def test_unusable_url_reported_not_dropped():
    i = inp(rich(official_url=None), urls=[("specification", "mailto:x@y.z")])
    row = plan(i, source())
    assert [v.reason for v in row.excluded_urls] == [en.UNUSABLE_URL]


def test_host_and_prefix_eligibility():
    src = source(prefixes=("/robots",))
    rec = rich(official_url=HOST + "robots/rich")
    i = inp(rec, urls=[("specification", HOST + "docs/rich.pdf"),          # outside prefix
                       ("deployment", "https://other.example/robots/rich"),  # other host
                       ("pricing_offer", "https://shop.maker-x.example/robots/r")])  # subdomain
    row = plan(i, src)
    assert HOST + "robots/rich" in row.eligible_urls
    reasons = {v.url: v.reason for v in row.excluded_urls}
    assert set(reasons.values()) == {en.NEEDS_SOURCE_APPROVAL}
    assert len(reasons) == 3
    # a sibling path of an approved prefix is not inside it
    assert plan(inp(rich(official_url=HOST + "robotsX/rich", images=())), src).eligible_urls == ()


def test_dot_segment_escape_needs_approval():
    i = inp(rich(official_url=HOST + "robots/../admin", images=()))
    row = plan(i, source())
    assert row.eligible_urls == () and row.excluded_urls[0].reason == en.NEEDS_SOURCE_APPROVAL


def test_no_approved_source_never_schedules_a_fetch():
    for src in (None, source(enabled=False), source(tos="UNKNOWN"), source(prefixes=())):
        row = plan(inp(sparse(is_published=True, official_url=HOST + "robots/x")), src)
        assert row.due == en.NO_APPROVED_SOURCE
        assert row.eligible_urls == () and row.fetch_planned is False
        assert row.source_status == en.NO_APPROVED_SOURCE
        assert row.excluded_urls and all(v.reason for v in row.excluded_urls)


def test_robot_with_no_source_and_no_urls_still_in_queue():
    i = inp(sparse(official_url=None))
    rows = en.build_queue([i], {}, {}, NOW)
    assert len(rows) == 1 and rows[0].due == en.NO_APPROVED_SOURCE


def test_sources_by_manufacturer_needs_a_reviewed_adapter():
    from app.services.discovery.sources import ADAPTERS
    neura = DiscoverySource(key="neura-robotics-official", name="n", source_class="MANUFACTURER")
    orphan = DiscoverySource(key="no-adapter", name="o", source_class="MANUFACTURER")
    out = en.sources_by_manufacturer([neura, orphan], ADAPTERS)
    assert out == {"neura-robotics": neura}


# ------------------------------------------------------------------ queue & quietness

def test_queue_covers_every_robot_and_is_deterministic():
    a, b = inp(sparse(slug="b-robot"), year=2026), inp(rich(slug="a-robot"))
    rows1 = en.build_queue([a, b], {}, {}, NOW)
    rows2 = en.build_queue([b, a], {}, {}, NOW)
    assert [r.robot_slug for r in rows1] == [r.robot_slug for r in rows2]
    assert {r.robot_slug for r in rows1} == {"a-robot", "b-robot"}
    assert rows1[0].priority == en.HIGH


def test_unchanged_and_unknown_stay_quiet():
    """Planning twice over identical state is identical; nothing is created or implied."""
    i = inp(rich(core={**rich().core, "has_sdk": None}))
    r1, r2 = plan(i, source()), plan(i, source())
    assert r1.as_dict() == r2.as_dict()
    s = en.summarize([r1])
    assert s["fetches_made"] == 0 and s["canonical_rows_written"] == 0
    # the planner exposes no write/propose surface at all
    assert not [n for n in dir(en) if n.startswith(("write_", "propose", "accept", "ingest"))]
    src = inspect.getsource(en)
    for banned in ("session.add", "session.commit", ".flush(", "INSERT", "UPDATE ", "DELETE",
                   "HttpFetcher", "requests."):
        assert banned not in src


def test_last_observation_drives_next_eligible_from_normalized_urls():
    rec = rich(official_url=HOST + "robots/rich")
    i = inp(rec)
    seen = NOW - timedelta(days=10)
    rows = en.build_queue([i], {"maker-x": source()}, {HOST + "robots/rich": seen}, NOW)
    assert rows[0].last_observation == seen
    assert rows[0].next_eligible == seen + en.BAND_INTERVAL[rows[0].priority]


def test_summary_counts_and_report_lines():
    rows = en.build_queue([inp(sparse(is_published=True)), inp(rich())], {}, {}, NOW)
    s = en.summarize(rows)
    assert (s["catalogue_robots"], s["no_approved_source"]) == (2, 2)
    assert s["high"] + s["medium"] + s["low"] == 2
    text = "\n".join(en.summary_lines(s))
    assert "CATALOGUE ENRICHMENT" in text and "no approved source=2" in text


def test_cycle_report_separates_the_two_lanes():
    res = CycleResult(started_at=NOW, plan_only=True)
    assert "unavailable" in "\n".join(res.lane_lines())
    res.enrichment = en.summarize(en.build_queue([inp(rich())], {}, {}, NOW))
    out = "\n".join(res.lines())
    assert out.index("NEW MODEL RADAR") < out.index("CATALOGUE ENRICHMENT")
    d = res.as_dict()
    assert set(d["lanes"]) == {"NEW_MODEL", "CATALOGUE_ENRICHMENT"}
    assert d["exit_code"] == 0   # informational: never changes the exit code


# ------------------------------------------------------------------ lanes

def test_lane_derivation():
    assert en.lane_for_proposal() == en.CATALOGUE_ENRICHMENT
    assert en.lane_for_candidate() == en.NEW_MODEL
    assert plan(inp(rich())).lane == en.CATALOGUE_ENRICHMENT
    assert plan(inp(rich())).as_dict()["lane"] == "CATALOGUE_ENRICHMENT"


# ------------------------------------------------------------------ PUBLICATION FIREWALL

def test_low_coverage_robot_remains_publication_eligible():
    rec = sparse()
    cov = rd.coverage_audit(rec)
    row = plan(inp(rec, year=2026))
    assert cov.band == "LOW" and row.priority == en.HIGH and row.coverage_band == "LOW"
    assert rd.publication_check(rec) == []
    assert rd.fresh_announcement_ready(rec) is True


def test_priority_and_freshness_are_not_inputs_to_readiness():
    rec = rich()
    base = rd.publication_check(rec)
    plan(inp(rec, commercial_days=999, spec_days=999))
    assert rd.publication_check(rec) == base == []
    assert "discovery.enrichment" not in inspect.getsource(rd)   # readiness cannot see it
