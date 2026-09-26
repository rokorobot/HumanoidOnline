"""NEURA Robotics — official manufacturer site. First source, NOT YET RUNNABLE.

Owner ToS decision: Robert read the terms himself and decided ALLOWED
(2026-09-26, DR-A4). That decision is recorded in the database through
`discovery source review` when the source is registered, never here, and it does
not expire on its own.

Structural review — 2026-09-26, read-only, 7 requests with the crawler's own
user agent, 3 s apart. Full record:
docs/discovery/NEURA_STRUCTURAL_REVIEW_2026-09-26.md. Summary:

- robots.txt (200): `User-agent: *` / `Allow: /` / `Crawl-delay:3`. Nothing
  names our token. The fetcher uses max(3 s, 2 s floor) = 3 s.
- HTTP-only acquisition is viable. Pages are server-rendered WordPress/Elementor
  (~6-7k characters of visible text, no client-side framework).
- Two English product-page families:
    /products/<slug>/              official robot pages (4ne1, mipa, maira, lara, mav)
    /product/<slug>-reservation/   reservation pages (4ne1, 4ne1-mini, mipa, quadruped)
  German copies (/de/produkt/...) are outside the approved prefixes.
- /shop/ answers 301 -> homepage, so there is no usable catalogue index. The
  product sitemap lists the reservation pages but omits 4ne1-mini. The newsroom
  page carries the site-wide nav, which links every /products/ page.
- JSON-LD is Yoast's graph only (WebPage, BreadcrumbList, WebSite,
  Organization, ImageObject). There is NO Product or Offer and no structured
  price, currency, availability or specification. Specs, estimated price tiers
  and the reservation fee appear only as visible text.
- There is no deterministic newsroom article pattern: articles live at
  root-level slugs (/<slug>/), the same shape as ordinary pages.

Why it is BLOCKED: the generic extractor is unsafe here. With no Product
JSON-LD it falls back to <h1>. The /products/ pages' <h1> is a marketing
tagline, which would become a candidate's name, and the reservation pages have
no <h1>, so they produce nothing. Running this module needs an owner-approved,
NEURA-specific deterministic HTML extractor and the owner decisions listed in
the review.
"""
from __future__ import annotations

import re

from app.services.discovery.live_adapter import SourceAdapterConfig

CONFIG = SourceAdapterConfig(
    key="neura-robotics-official",
    version="0.2.0",
    source_key="neura-robotics-official",
    source_class="MANUFACTURER",
    host="neura-robotics.com",
    # Canonical catalogue manufacturer name, verbatim. No aliases.
    manufacturer="Neura Robotics",
    allowed_path_prefixes=("/products/", "/product/", "/product-sitemap.xml", "/news/"),
    # Normalized (docs/16 §11) seeds, both observed 200 on 2026-09-26:
    # - the product sitemap: the reservation pages (it omits 4ne1-mini);
    # - the newsroom index: its site-wide nav links every /products/ page.
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
    # Neither page uses a price-on-request phrase.
    quote_phrases=(),
    structural_review="2026-09-26 read-only inspection (7 requests); "
    "docs/discovery/NEURA_STRUCTURAL_REVIEW_2026-09-26.md",
    blocked_reason="generic extraction unsafe: no Product JSON-LD; /products/ <h1> is a "
    "tagline and reservation pages have no <h1>; needs an owner-approved NEURA HTML "
    "extractor",
)
