"""LimX Dynamics — official www.limxdynamics.com humanoid product pages (Oli, Luna).

Access basis (docs/28, A4): owner approval 2026-11-05 to build the adapter; the source's
OWNER_AUTHORIZED basis is a separate owner act and `tos_status` stays UNKNOWN. robots.txt
allows `*` except `/api/` and `/admin/`; it is re-read on every run.

Structural review: docs/discovery/LIMX_STRUCTURAL_REVIEW_2026-11-05.md (7 requests).

Scope: two fixed English product pages, `/en/products/oli` and `/en/products/luna`. TRON 1,
TRON 2 and FluxVLA are not described as humanoid and are not seeds; `/spec` and `/news` pages
are not seeds in v0.1.0. Both pages carry a server-rendered JSON-LD `Product` and a
self-referential canonical, so the generic JSON-LD identity rule applies unchanged: the
candidate is named by the page's own Product name, and nothing else is claimed (no price, no
availability, no specification). Specification claims need a source-specific extractor and are
a later version.
"""
from __future__ import annotations

import re

from app.services.discovery.live_adapter import SourceAdapterConfig

STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-11-05",
    "robots_status": "ALLOWED",
    "robots_disallow": ("/api/", "/admin/"),
    "identity": "JSON-LD Product name ('LimX Oli', 'LimX Luna'); canonical is self-referential",
    "commercial_language": "'Buy Now' links to /en/order (not reviewed, not a seed)",
}

CONFIG = SourceAdapterConfig(
    key="limx-dynamics-official",
    version="0.1.0",
    source_key="limx-dynamics-official",
    source_class="MANUFACTURER",
    host="www.limxdynamics.com",
    manufacturer="LimX Dynamics",
    allowed_path_prefixes=("/en/products/oli", "/en/products/luna"),
    seed_urls=("https://www.limxdynamics.com/en/products/oli",
               "https://www.limxdynamics.com/en/products/luna"),
    product_path_pattern=re.compile(r"/en/products/(oli|luna)"),
    announcement_path_pattern=None,
    heading_identity=False,
    target_cap=2,
    structural_review="2026-11-05 read-only inspection (7 requests); "
    "docs/discovery/LIMX_STRUCTURAL_REVIEW_2026-11-05.md",
)
