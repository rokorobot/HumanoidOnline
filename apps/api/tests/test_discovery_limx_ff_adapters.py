"""LimX Dynamics and Faraday Future adapters (identity only), offline.

Fixtures are 2026-11-05 structural-review bodies, trimmed (tests/fixtures/<maker>/README.md).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.discovery.live_adapter import extract_product
from app.services.discovery.robots import parse
from app.services.discovery.sources import ADAPTERS

pytestmark = pytest.mark.usefixtures("no_external_network")

FIX = Path(__file__).parent / "fixtures"
_LIMX, _FF = "limx-dynamics-official", "faraday-future-official"
_LX, _FX = "https://www.limxdynamics.com/en/products/", "https://robotics.ff.com/us/"
PAGES = [
    (_LIMX, _LX + "oli", "limx/oli.html", "LimX Oli"),
    (_LIMX, _LX + "luna", "limx/luna.html", "LimX Luna"),
    (_FF, _FX + "ff-futurist/", "faraday/ff-futurist.html", "FF Futurist"),
    (_FF, _FX + "futurist/", "faraday/futurist.html", "FF All-New Futurist"),
]


def raw(fixture: str) -> bytes:
    return (FIX / fixture).read_bytes()


@pytest.mark.parametrize("key, url, fixture, name", PAGES)
def test_each_reviewed_page_names_its_model_and_states_nothing_else(key, url, fixture, name):
    result = extract_product(ADAPTERS[key], raw(fixture), url)
    assert (result.status, result.name) == ("EXTRACTED", name)
    assert result.signals == () and result.claims == () and result.rejected == ()
    assert extract_product(ADAPTERS[key], raw(fixture), url) == result      # deterministic


def test_ff_ignores_the_conflicting_json_ld_price_and_the_foreign_canonical():
    body = raw("faraday/ff-futurist.html")
    assert b"34990" in body and b"https://www.ff.com/us/robotics/ff-futurist/" in body
    result = extract_product(ADAPTERS["faraday-future-official"], body,
                             "https://robotics.ff.com/us/ff-futurist/")
    assert result.signals == () and result.name == "FF Futurist"


def test_ff_title_must_match_the_reviewed_pattern_for_that_path():
    body = raw("faraday/futurist.html")
    # the All-New title served under the older path is not the reviewed identity
    result = extract_product(ADAPTERS["faraday-future-official"], body,
                             "https://robotics.ff.com/us/ff-futurist/")
    assert result.status == "NOTHING_FOUND"
    other = extract_product(ADAPTERS["faraday-future-official"], body,
                            "https://robotics.ff.com/us/ff-master/")
    assert other.status == "NOTHING_FOUND"


def test_limx_without_a_json_ld_product_names_nothing():
    body = raw("limx/oli.html").replace(b'"Product"', b'"Thing"')
    result = extract_product(ADAPTERS["limx-dynamics-official"], body,
                             "https://www.limxdynamics.com/en/products/oli")
    assert result.status != "EXTRACTED"


def test_scope_is_humanoid_pages_only_and_robots_allow_it():
    limx = ADAPTERS["limx-dynamics-official"]
    ff = ADAPTERS["faraday-future-official"]
    assert limx.host == "www.limxdynamics.com" and ff.host == "robotics.ff.com"
    assert limx.allowed_path_prefixes == ("/en/products/oli", "/en/products/luna")
    assert ff.allowed_path_prefixes == ("/us/ff-futurist", "/us/futurist")
    assert limx.target_cap == ff.target_cap == 2 and limx.structural_review and ff.structural_review
    rules = parse(raw("limx/robots.txt").decode("utf-8"))
    assert rules.allows("https://www.limxdynamics.com/en/products/oli")
    assert not rules.allows("https://www.limxdynamics.com/api/x")
    assert not rules.allows("https://www.limxdynamics.com/admin/")
    ff_rules = parse(raw("faraday/robots.txt").decode("utf-8"))
    assert ff_rules.allows("https://robotics.ff.com/us/futurist/")
