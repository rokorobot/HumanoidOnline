"""Shared acquisition eligibility (owner decision DR-A4).

Pure unit tests on in-memory model instances: no database, no network.

The owner reads each source's terms personally and records `tos_status`; that
recorded decision gates (through `radar_eligible`). ToS *currency* — expiry,
review age, page-hash change — never gates. The DR-A4 tests below pin that so a
refactor cannot quietly reintroduce the former expiry/hash gate.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.discovery import DiscoverySource
from app.services.discovery.eligibility import (
    NO_APPROVED_HOST,
    NO_APPROVED_PATHS,
    NOT_RADAR_ELIGIBLE,
    SOURCE_DISABLED,
    URL_OUTSIDE_APPROVED_HOST,
    URL_OUTSIDE_APPROVED_PATHS,
    source_acquisition_eligible,
    source_ineligibility,
    url_ineligibility,
)

NOW = datetime(2026, 9, 26, tzinfo=UTC)


def _source(**overrides) -> DiscoverySource:
    fields = dict(
        key="fixture", name="Fixture", source_class="MANUFACTURER",
        homepage_url="https://maker.example/", allowed_path_prefixes=["/products/"],
        is_enabled=True, tos_status="ALLOWED", robots_status="ALLOWED",
        eligibility_reviewed_at=NOW - timedelta(days=1), eligibility_reviewed_by="owner",
        tos_expires_at=NOW + timedelta(days=60),
    )
    fields.update(overrides)
    return DiscoverySource(**fields)


def test_fully_approved_source_and_url_are_eligible():
    source = _source()
    assert source_acquisition_eligible(source)
    assert url_ineligibility(source, "https://maker.example/products/h1") is None
    assert url_ineligibility(source, "https://MAKER.example/products/") is None


@pytest.mark.parametrize(("overrides", "reason"), [
    ({"is_enabled": False}, SOURCE_DISABLED),
    ({"tos_status": "UNKNOWN"}, NOT_RADAR_ELIGIBLE),  # owner has not recorded ALLOWED
    ({"tos_status": "PROHIBITED"}, NOT_RADAR_ELIGIBLE),
    ({"robots_status": "DISALLOWED"}, NOT_RADAR_ELIGIBLE),
    ({"robots_status": "UNKNOWN"}, NOT_RADAR_ELIGIBLE),
    ({"eligibility_reviewed_by": None}, NOT_RADAR_ELIGIBLE),
    ({"homepage_url": None}, NO_APPROVED_HOST),
    ({"homepage_url": "ftp://maker.example/"}, NO_APPROVED_HOST),
    ({"homepage_url": "maker.example"}, NO_APPROVED_HOST),
    ({"allowed_path_prefixes": None}, NO_APPROVED_PATHS),
    ({"allowed_path_prefixes": []}, NO_APPROVED_PATHS),
    ({"allowed_path_prefixes": ["products/"]}, NO_APPROVED_PATHS),
])
def test_source_policy_fails_closed(overrides, reason):
    source = _source(**overrides)
    assert source_ineligibility(source) == reason
    assert url_ineligibility(source, "https://maker.example/products/h1") == reason


def test_missing_source_fails_closed():
    assert source_ineligibility(None) == SOURCE_DISABLED
    assert url_ineligibility(None, "https://maker.example/products/h1") == SOURCE_DISABLED


@pytest.mark.parametrize("url", [
    "https://other.example/products/h1",
    "https://shop.maker.example/products/h1",
    "https://maker.example.evil/products/h1",
    "https://user:pw@maker.example/products/h1",
    "https://maker.example:8443/products/h1",
    "file:///products/h1",
    "javascript:alert(1)",
])
def test_url_outside_approved_host(url):
    assert url_ineligibility(_source(), url) == URL_OUTSIDE_APPROVED_HOST


@pytest.mark.parametrize("url", [
    "https://maker.example/",
    "https://maker.example/about",
    "https://maker.example/productsX/h1",
    "https://maker.example/products/../admin",
    "https://maker.example/products/%2E%2E/admin",
])
def test_url_outside_approved_paths(url):
    assert url_ineligibility(_source(), url) == URL_OUTSIDE_APPROVED_PATHS


def test_prefix_without_trailing_slash_is_segment_aware():
    source = _source(allowed_path_prefixes=["/robots"])
    assert url_ineligibility(source, "https://maker.example/robots") is None
    assert url_ineligibility(source, "https://maker.example/robots/h1") is None
    assert url_ineligibility(source, "https://maker.example/robotshop") == (
        URL_OUTSIDE_APPROVED_PATHS
    )


# ---- DR-A4: ToS currency never gates ---------------------------------------


@pytest.mark.parametrize("overrides", [
    {"tos_expires_at": None},
    {"tos_expires_at": NOW - timedelta(days=365)},
    {"tos_reviewed_at": None},
    {"tos_reviewed_at": NOW - timedelta(days=3650)},
    {"tos_page_hash": "0" * 64},
    {"tos_page_hash": None},
])
def test_tos_currency_does_not_block_acquisition(overrides):
    source = _source(**overrides)
    assert source_acquisition_eligible(source)
    assert url_ineligibility(source, "https://maker.example/products/h1") is None


def test_eligibility_module_never_reads_tos_currency_fields():
    import inspect

    from app.services.discovery import eligibility

    code = inspect.getsource(eligibility).split('"""', 2)[2]  # skip the docstring
    for field in ("tos_expires_at", "tos_reviewed_at", "tos_page_hash"):
        assert field not in code
