"""Gate D / Gate R parity: /crawler-policy states what the crawler actually does.

The web page takes its figures from apps/web/lib/crawler-policy.ts; this test
fails if they drift from the crawler's code constants.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.services.discovery.fetcher import MIN_INTERVAL_FLOOR_SECONDS, USER_AGENT
from app.services.discovery.live_adapter import SourceAdapterConfig
from app.services.discovery.robots import PRODUCT_TOKEN

WEB = Path(__file__).resolve().parents[2] / "web"
POLICY = (WEB / "lib" / "crawler-policy.ts").read_text(encoding="utf-8")


def _const(name: str) -> str:
    match = re.search(rf"export const {name} =\s*([^;]+);", POLICY)
    assert match, name
    return match.group(1).strip().strip('"')


def test_page_exists_at_the_user_agent_url() -> None:
    assert USER_AGENT.endswith("(+https://humanoidonline.com/crawler-policy)")
    assert (WEB / "app" / "crawler-policy" / "page.tsx").is_file()


def test_page_figures_match_the_crawler() -> None:
    assert _const("CRAWLER_USER_AGENT") == USER_AGENT
    assert _const("CRAWLER_PRODUCT_TOKEN").lower() == PRODUCT_TOKEN
    assert float(_const("CRAWLER_MIN_INTERVAL_SECONDS")) == MIN_INTERVAL_FLOOR_SECONDS
    default_cap = SourceAdapterConfig.__dataclass_fields__["target_cap"].default
    assert int(_const("CRAWLER_PAGES_PER_RUN")) == default_cap
