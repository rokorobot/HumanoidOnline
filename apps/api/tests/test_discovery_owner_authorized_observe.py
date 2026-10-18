"""docs/28 (A4) — OWNER_AUTHORIZED sources in the Stage F observation cycle.

Offline against PostgreSQL, through the Stage F harness (synthetic sites served
by httpx.MockTransport; any real socket fails the test). Pins that the owner's
access basis changes WHICH sources may be observed, never HOW: robots.txt on
every run, the reviewed adapter, the owner's path ceiling, halts on blocks,
revocation, isolation between sources, and zero canonical writes.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from test_discovery_stage_f_observe import Harness, Site, canonical, dsession, h  # noqa: F401

from app.models.discovery import DiscoverySource
from app.services.discovery import source_registry as registry

pytestmark = pytest.mark.usefixtures("no_external_network")


def _owner_authorize(harness: Harness, site: Site, paths=("/products",)) -> DiscoverySource:
    """The owner's A4 decision on a source whose terms were never read (UNKNOWN)."""
    source = harness._src(site)
    source.tos_status = "UNKNOWN"
    source.access_basis = "OWNER_AUTHORIZED"
    source.owner_authorized_by = "Robert Konecny (product owner)"
    source.owner_authorized_at = datetime(2026, 10, 18, tzinfo=UTC)
    source.owner_authorization_reason = "A4 owner instruction 2026-10-18"
    source.owner_authorized_path_prefixes = list(paths)
    harness.session.flush()
    return source


def test_an_owner_authorized_source_is_observed_with_every_gate_and_tos_stays_unknown(h):  # noqa: F811
    site = h.source("a")
    source = _owner_authorize(h, site)
    before = canonical(h.session)
    _, by_key, _ = h.cycle()
    assert by_key[site.key].status == "COMPLETED"
    assert site.requests[0][0] == "/robots.txt"              # robots on every run
    assert all(p.startswith("/products") for p in site.paths())
    assert canonical(h.session) == before                    # observation is not publication
    assert source.tos_status == "UNKNOWN" and source.access_basis == "OWNER_AUTHORIZED"


def test_an_owner_scope_narrower_than_the_adapter_refuses_the_run_before_any_request(h):  # noqa: F811
    site = h.source("a")
    _owner_authorize(h, site, paths=("/products/a",))         # the adapter needs /products
    _, by_key, _ = h.cycle()
    assert by_key[site.key].status == "INELIGIBLE"
    assert "PATH_PREFIX_NOT_APPROVED" in by_key[site.key].detail
    assert site.requests == []


def test_an_owner_authorized_source_without_a_reviewed_adapter_is_never_contacted(h):  # noqa: F811
    site = h.source("a", adapter=False)
    _owner_authorize(h, site)
    result, by_key, _ = h.cycle()
    assert by_key[site.key].status == "NO_ADAPTER" and site.requests == []
    assert result.needs_attention


def test_robots_disallow_still_halts_and_disables_an_owner_authorized_source(h):  # noqa: F811
    site = h.source("a")
    _owner_authorize(h, site)
    site.robots = "User-agent: *\nDisallow: /products\n"
    _, first, _ = h.cycle()
    assert first[site.key].status == "HALTED" and "robots_disallow" in first[site.key].detail
    h.advance(48)
    seen = len(site.requests)
    _, second, _ = h.cycle()
    assert second[site.key].status == "DISABLED" and len(site.requests) == seen


@pytest.mark.parametrize("status", [403, 429])
def test_a_block_is_a_finding_not_retried_under_owner_authorization(h, status):  # noqa: F811
    site = h.source("a")
    _owner_authorize(h, site)
    site.status["/products"] = status
    _, first, _ = h.cycle()
    assert first[site.key].status == "HALTED"
    h.advance(48)
    seen = len(site.requests)
    _, second, _ = h.cycle()
    assert second[site.key].status == "NEEDS_HUMAN" and len(site.requests) == seen


def test_revocation_stops_the_next_cycle_and_other_sources_keep_running(h):  # noqa: F811
    owner_site = h.source("a")
    other = h.source("b")
    _owner_authorize(h, owner_site)
    _, first, _ = h.cycle()
    assert first[owner_site.key].status == first[other.key].status == "COMPLETED"
    registry.revoke_owner(h.session, owner_site.key, by="Robert Konecny", reason="stop")
    h.advance(48)
    seen = len(owner_site.requests)
    _, second, _ = h.cycle()
    assert second[owner_site.key].status == "DISABLED"
    assert len(owner_site.requests) == seen                  # not contacted after revocation
    assert second[other.key].status == "COMPLETED"           # isolation between sources


def test_a4_sources_without_a_reviewed_adapter_are_not_runnable(h):  # noqa: F811
    """Registered (as in production) and even if wrongly enabled and scheduled, a source
    without a reviewed adapter is never contacted. Unitree has one since 2026-10-18; the
    other five do not. (The harness only runs adapters it is given, so all six report
    NO_ADAPTER here and no real host is contacted.)"""
    from app.services.discovery.source_manifest import sync_sources
    from app.services.discovery.sources import ADAPTERS

    sync_sources(h.session, apply=True, by="test")
    keys = ("unitree-robotics-official", "booster-robotics-official", "agibot-official",
            "agility-robotics-official", "figure-ai-official", "alza-cz")
    for key in keys:
        source = h.session.scalar(select(DiscoverySource).where(DiscoverySource.key == key))
        assert source.is_enabled is False and source.tos_status == "UNKNOWN"
        registry.review_source(h.session, key, reviewed_by="test", tos_decision="UNKNOWN",
                               robots_decision="ALLOWED", path_prefixes=["/"])
        registry.authorize_owner(h.session, key, by="test", reason="fixture", path_prefixes=["/"])
        registry.enable_source(h.session, key, by="test")
        registry.set_cadence(h.session, key, every="24h", by="test")
    h.session.commit()
    result = h.cycle()[0]
    status = {s.key: s.status for s in result.sources}
    assert {status[k] for k in keys} == {"NO_ADAPTER"}
    assert set(keys) & set(ADAPTERS) == {
        "unitree-robotics-official", "booster-robotics-official", "agibot-official",
        "agility-robotics-official", "figure-ai-official"}
