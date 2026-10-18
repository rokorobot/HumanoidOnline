"""Booster Robotics — official www.booster.tech product pages for the T2 and K1 humanoids.

Access basis (docs/28, A4): owner instruction 2026-10-18, OWNER_AUTHORIZED. That is an internal
business decision, NOT publisher consent: `tos_status` stays UNKNOWN, and the decision is recorded
in the database, never here. robots.txt (`User-agent: *` / `Allow: /`) is re-read on every run.

Structural review: docs/discovery/BOOSTER_STRUCTURAL_REVIEW_2026-10-18.md (9 requests), plus two
probes on 2026-10-18 for this adapter: the slash-less seed form `/booster-t2?target=en` answers 200
with the same bytes as `/booster-t2/?target=en`, and `/booster-k1/?target=en` answers 200.

Scope: a FIXED set of two English product pages (`?target=en` is the site's own language
switch and is part of the reviewed URL). Nothing is discovered by following links. `/store`,
the `/cn/` copies and `agentstore.`, `docs.`, `studio.` and `support.` are out of scope. The
site has no T1 page.

Extraction is the GENERIC rule: each page carries a schema.org `Product` (`Booster T2`,
`Booster K1`, brand `Booster Robotics`) that agrees with `canonical` and the `<h1>`. There is no
`offers` block, so no price or availability is stated, and none is inferred. "Buy now" links and
the homepage's funding-round "$" amounts are never read.
"""
from __future__ import annotations

import re

from app.services.discovery.live_adapter import SourceAdapterConfig

STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-10-18",
    "robots_status": "ALLOWED",
    "identity": "JSON-LD Product name + canonical + <h1> agree on both pages",
    "commercial_language": "'Buy now' -> /store (not reviewed); no offers in JSON-LD; no price",
    "absent": "no T1 page on www.booster.tech",
}

CONFIG = SourceAdapterConfig(
    key="booster-robotics-official",
    version="0.1.0",
    source_key="booster-robotics-official",
    source_class="MANUFACTURER",
    host="www.booster.tech",
    manufacturer="Booster Robotics",
    allowed_path_prefixes=("/booster-t2", "/booster-k1"),
    seed_urls=("https://www.booster.tech/booster-t2?target=en",
               "https://www.booster.tech/booster-k1?target=en"),
    product_path_pattern=re.compile(r"/booster-(?:t2|k1)"),
    announcement_path_pattern=None,
    target_cap=1,
    structural_review="2026-10-18 read-only inspection (9 + 2 requests); "
    "docs/discovery/BOOSTER_STRUCTURAL_REVIEW_2026-10-18.md",
)
