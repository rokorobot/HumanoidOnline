"""NEURA Robotics — official manufacturer site. PROVISIONAL first source (D1).

Status: NOT RUNNABLE. This module is the reviewed home for NEURA's crawler
behaviour, but two owner-side prerequisites are still open, and the runner
refuses a live run until both are recorded:

1. Robert's personal Terms of Service read and `tos_status` decision, recorded
   through `discovery source review` (DR-A4). Held in the database, not here.
2. An authorized structural check (docs/16 §12.1) confirming that the catalogue
   and product pages are server-rendered enough for HTTP-only acquisition, and
   whether they carry useful JSON-LD. Until then `structural_review` is None,
   and `SEED_URLS` is deliberately empty: no product or listing URL of this site
   has been looked at, so none is written down here as if it had been.

If NEURA fails either check, the next MANUFACTURER / OFFICIAL_STORE source is
proposed instead. The HTTP-only rule is never relaxed to fit a site.

What IS known (docs/16 §23.1): host `neura-robotics.com`; robots.txt allowed all
agents with `Crawl-delay: 3`, which the fetcher honours over its 2 s floor. The
manufacturer identity is the canonical catalogue record's name, verbatim.
"""
from __future__ import annotations

import re

from app.services.discovery.live_adapter import SourceAdapterConfig

CONFIG = SourceAdapterConfig(
    key="neura-robotics-official",
    version="0.1.0",
    source_key="neura-robotics-official",
    source_class="MANUFACTURER",
    host="neura-robotics.com",
    manufacturer="Neura Robotics",
    # Filled from the structural check, then reviewed; empty approves nothing.
    allowed_path_prefixes=(),
    seed_urls=(),
    # Placeholders that match nothing until the structural check supplies the
    # site's real product and newsroom URL shapes.
    product_path_pattern=re.compile(r"(?!)"),
    announcement_path_pattern=re.compile(r"(?!)"),
    property_map={},
    quote_phrases=("price on request", "request a quote"),
    structural_review=None,
)
