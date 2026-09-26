"""NEURA Robotics — official manufacturer site. Structurally reviewed; BLOCKED.

Owner ToS decision: Robert read the terms himself and decided ALLOWED
(2026-09-26, DR-A4). That decision is recorded in the database through
`discovery source review` at registration, never here, and it does not expire.

Structural review: 2026-09-26, read-only, 7 requests with the crawler's own user
agent, 3 s apart. Full record and the future-extractor design note:
docs/discovery/NEURA_STRUCTURAL_REVIEW_2026-09-26.md. Everything below is limited
to what those 7 responses established; no URL family is guessed.

The runner refuses this module (`ADAPTER_BLOCKED`) until a NEURA-specific
deterministic extractor is approved. Commercial facts (the reservation fee,
estimated prices) stay UNKNOWN and unextracted until then.
"""
from __future__ import annotations

import re

from app.services.discovery.live_adapter import SourceAdapterConfig

BLOCK_CODE = "BLOCKED_NEEDS_SOURCE_SPECIFIC_EXTRACTOR"

#: What the inspection established, as data (asserted by the tests).
STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-09-26T09:30Z/09:33Z",
    "requests": (
        ("https://neura-robotics.com/robots.txt", 200),
        ("https://neura-robotics.com/sitemap_index.xml", 200),
        ("https://neura-robotics.com/product-sitemap.xml", 200),
        ("https://neura-robotics.com/shop/", 301),
        ("https://neura-robotics.com/product/4ne1-reservation/", 200),
        ("https://neura-robotics.com/products/4ne1/", 200),
        ("https://neura-robotics.com/news/", 200),
    ),
    # `User-agent: *` / `Allow: /` applies; no group names our token.
    "robots_status": "ALLOWED",
    "crawl_delay_seconds": 3,
    "sitemaps_observed": (
        "https://neura-robotics.com/sitemap_index.xml",
        "https://neura-robotics.com/post-sitemap.xml",
        "https://neura-robotics.com/page-sitemap.xml",
        "https://neura-robotics.com/product-sitemap.xml",
        "https://neura-robotics.com/product_cat-sitemap.xml",
    ),
    "url_families": {
        "/products/<slug>/": "official robot pages (4ne1, mipa, maira, lara, mav)",
        "/product/<slug>-reservation/": "reservation pages (4ne1, 4ne1-mini, mipa, quadruped)",
    },
    "rejected_seeds": {
        "https://neura-robotics.com/shop/": "301 to the homepage; not a catalogue index",
    },
    # The product sitemap is useful but NOT complete.
    "sitemap_omissions": ("https://neura-robotics.com/product/4ne1-mini-reservation/",),
    "newsroom": "https://neura-robotics.com/news/ exists; articles use root-level slugs, "
    "so no deterministic announcement URL pattern was established",
    "identity_issues": (
        "catalogue robot is named '4NE-1' (slug neura-4ne-1); the site writes '4NE1'. "
        "They do not normalize to each other and NO alias was added; human review "
        "needed before any NEURA candidate is resolved",
    ),
    # Three different things, never interchangeable. None of them is mapped yet.
    "commercial_language": {
        "reservation_fee": "refundable per-unit reservation fee (a deposit), credited "
        "toward a later purchase; NOT a price",
        "estimated_price": "estimated price per unit in quantity bands, excluding taxes "
        "and shipping; NOT an actual purchase price",
        "purchase_price": "no actual purchase price was observed",
    },
}

CONFIG = SourceAdapterConfig(
    key="neura-robotics-official",
    version="0.2.0",
    source_key="neura-robotics-official",
    source_class="MANUFACTURER",
    host="neura-robotics.com",
    # Canonical catalogue manufacturer name, verbatim. No aliases.
    manufacturer="Neura Robotics",
    allowed_path_prefixes=("/products/", "/product/", "/product-sitemap.xml", "/news/"),
    # Normalized (docs/16 §11) seeds, both observed 200:
    # - the product sitemap: the reservation pages (it omits 4ne1-mini);
    # - the newsroom index: its site-wide nav links every /products/ page.
    # NOT /shop/ (301 to the homepage).
    seed_urls=(
        "https://neura-robotics.com/product-sitemap.xml",
        "https://neura-robotics.com/news",
    ),
    # Full match on the NORMALIZED path (no trailing slash).
    product_path_pattern=re.compile(r"/products/[a-z0-9-]+|/product/[a-z0-9-]+-reservation"),
    # No deterministic article URL shape was observed.
    announcement_path_pattern=None,
    # No JSON-LD properties exist to map.
    property_map={},
    # No price-on-request phrase observed, and reservation/estimate wording must
    # never be read as a quote or a price.
    quote_phrases=(),
    # The /products/ <h1> is a marketing tagline, never a product name.
    heading_identity=False,
    structural_review="2026-09-26 read-only inspection (7 requests); "
    "docs/discovery/NEURA_STRUCTURAL_REVIEW_2026-09-26.md",
    blocked_reason=(
        f"{BLOCK_CODE}: pages are HTTP/server-rendered and robots-compatible, but the "
        "generic extractor cannot identify NEURA products reliably: product and "
        "reservation pages expose no usable Product JSON-LD, <h1> is not a safe identity "
        "source, and reservation pages distinguish a refundable reservation fee (deposit) "
        "from an estimated robot price, neither of which is a purchase price; running the "
        "generic adapter could create incorrect candidates or commercial facts"
    ),
)
