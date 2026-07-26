"""DATA-D1 v0.1 discovery pipeline (docs/11_DATA_D1_CONTRACT.md, RATIFIED v0.1).

The governed path: radar (source adapters) -> candidate -> identity -> trace ->
verify -> promotion proposal -> HUMAN promotion gate -> canonical. Automation runs
autonomously up to a structured proposal; only `promotion.promote` writes canonical
truth, and it is human-invoked (the CLI / admin), never called by the pipeline (§8,
§18, Gate H). v0.1 ships NO live network crawler (DATA-D1.9): sources become
crawler-eligible only after a ToS/robots review, so discovery runs from fixtures.
"""
from __future__ import annotations


class DiscoveryError(Exception):
    """A governance/pipeline violation (e.g. crawling an ineligible source)."""


class PromotionError(Exception):
    """An implemented promotion gate blocked the candidate. No canonical write occurred."""
