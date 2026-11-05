"""Faraday Future robotics — official robotics.ff.com humanoid product pages (Futurist).

Access basis (docs/28, A4): owner approval 2026-11-05 to build the adapter; the source's
OWNER_AUTHORIZED basis is a separate owner act and `tos_status` stays UNKNOWN. robots.txt
is `Allow: /`; it is re-read on every run. `www.ff.com` is a different host with different
rules and is not covered.

Structural review: docs/discovery/FARADAY_FUTURE_STRUCTURAL_REVIEW_2026-11-05.md (5 requests).

Scope: two fixed pages, `/us/ff-futurist/` and `/us/futurist/`. Other FF products (Master, Aegis,
Nova, Faber, Navi) are not described as humanoid and are not seeds.

Source-specific extractor (`extract_ff_product`). There is no `<h1>`, the canonical points to
another host, and the embedded JSON-LD and menu data carry conflicting prices, so none of those
is used. Identity is the reviewed URL path plus the page's own `<title>`, which must match the
pattern reviewed for that path. No price, availability, status or specification is emitted.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import ProductExtraction, SourceAdapterConfig
from app.services.discovery.sources import xpeng_iron_proposals as html
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-11-05",
    "robots_status": "ALLOWED",
    "robots_disallow": (),
    "identity": "URL path + <title>; no <h1>; canonical points to www.ff.com (ignored)",
    "commercial_language": "'Order Now', 'Preorder / Inquire'; prices conflict in page data",
}

#: reviewed path -> <title> pattern whose `name` group is the model name
_TITLES = {
    "/us/ff-futurist": re.compile(r"(?P<name>FF Futurist) - FF EAI Robotics"),
    "/us/futurist": re.compile(r"(?P<name>FF All-New Futurist): Full-Size Humanoid Robot"
                                r" \| Faraday Future"),
}


def extract_ff_product(config: SourceAdapterConfig, body: bytes,
                       url: str | None) -> ProductExtraction:
    """Identity only: reviewed path + matching `<title>`. Pure."""
    try:
        path = urlsplit(normalize_url(url or "")).path
    except UnsupportedUrl:
        return ProductExtraction("NOTHING_FOUND", notes=("no page URL",))
    pattern = _TITLES.get(path)
    if pattern is None:
        return ProductExtraction("NOTHING_FOUND", notes=("URL is not a reviewed product page",))
    tree = html._Tree()
    tree.feed(body.decode("utf-8", errors="replace"))
    tree.close()
    node = next((n for n in html._walk(tree.root) if n.tag == "title"), None)
    title = " ".join(html._text(node).split()) if node is not None else None
    match = pattern.fullmatch(title or "")
    if match is None:
        return ProductExtraction("NOTHING_FOUND", notes=(f"<title> {title!r} not as reviewed",))
    return ProductExtraction(
        "EXTRACTED", name=match.group("name"), name_method="SELECTOR",
        notes=("agreeing locators: ['path', 'title']",
               "identity only: no price, availability, status or specification"))


CONFIG = SourceAdapterConfig(
    key="faraday-future-official",
    version="0.1.0",
    source_key="faraday-future-official",
    source_class="MANUFACTURER",
    host="robotics.ff.com",
    manufacturer="Faraday Future",
    allowed_path_prefixes=("/us/ff-futurist", "/us/futurist"),
    seed_urls=("https://robotics.ff.com/us/ff-futurist/", "https://robotics.ff.com/us/futurist/"),
    product_path_pattern=re.compile(r"/us/(ff-)?futurist"),
    announcement_path_pattern=None,
    heading_identity=False,
    product_extractor=extract_ff_product,
    target_cap=2,
    structural_review="2026-11-05 read-only inspection (5 requests); "
    "docs/discovery/FARADAY_FUTURE_STRUCTURAL_REVIEW_2026-11-05.md",
)
