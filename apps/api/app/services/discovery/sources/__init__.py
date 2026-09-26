"""Registry of reviewed source adapters — one versioned module per source (D3).

Adding a source is a code change reviewed in a PR: its seeds, URL patterns and
extraction rules are never read from the database.
"""
from __future__ import annotations

from app.services.discovery.live_adapter import SourceAdapterConfig
from app.services.discovery.sources import neura_robotics

ADAPTERS: dict[str, SourceAdapterConfig] = {
    config.source_key: config for config in (neura_robotics.CONFIG,)
}


def adapter_for(source_key: str) -> SourceAdapterConfig | None:
    return ADAPTERS.get(source_key)
