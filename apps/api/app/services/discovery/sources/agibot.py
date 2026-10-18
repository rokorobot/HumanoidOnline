"""AgiBot — official www.agibot.com product pages for the A2 and X2 humanoids.

Access basis (docs/28, A4): owner instruction 2026-10-18, OWNER_AUTHORIZED, which is not publisher
consent: `tos_status` stays UNKNOWN. robots.txt answered 404 on 2026-10-18 (no restrictions under
RFC 9309). It is re-read on every run, so a future file applies immediately.

Structural review: docs/discovery/AGIBOT_STRUCTURAL_REVIEW_2026-10-18.md (6 requests).

Scope: a FIXED set of two product pages, `/products/A2` and `/products/X2`, both bipedal humanoids.
The wheeled G2, the C5/D1 quadrupeds, hands and other products are not seeds. The malformed
sitemap is never read, and `store.agibot.com` is another host.

IDENTITY-ONLY, source-specific extractor (`extract_agibot_product`). The pages have no `<h1>` and
no JSON-LD. Their `<title>` is often the generic company title, and **every product page's
canonical points to the homepage**, so canonical is deliberately NOT read. Identity needs the URL
slug (`A2`, `X2`) to equal the model in a visible `AGIBOT <model>` / `AGIBOT <model> series`
heading block. The candidate is the model token as the page writes it (`A2`, `X2`); catalogue
editions (`A2 Lite`, `A2 Ultra`) are a human identity decision. No claim, signal or image is
emitted.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import ProductExtraction, SourceAdapterConfig
from app.services.discovery.sources import xpeng_iron_proposals as html
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-10-18",
    "robots_status": "ALLOWED",       # 404 -> no restrictions (RFC 9309)
    "identity_issues": ("canonical points to the homepage on every product page",
                        "no <h1>, no JSON-LD; <title> generic on X2/G2"),
    "commercial_language": "'Contact sales' only; no price",
}

_PAGES = {"/products/A2": "A2", "/products/X2": "X2"}
_HEADING = re.compile(r"AGIBOT (?P<model>[A-Za-z0-9_]+)(?: series)?")


#: Site-wide product menus and swipers repeat "AGIBOT <model>" for every product, and a
#: contact form lists models as checkbox labels: that text is navigation, never identity.
_NAV_TAGS = frozenset({"a", "label", "nav", "header", "footer", "select", "option"})
_NAV_CLASS = re.compile(r"nav|swiper|menu|dropdown", re.IGNORECASE)


def _without_navigation(node):
    """A copy of the tree without navigation, menu and form-label subtrees."""
    copy = html._Node(node.tag, node.attrs, None)
    for child in node.children:
        if isinstance(child, str):
            copy.children.append(child)
        elif child.tag not in _NAV_TAGS and not _NAV_CLASS.search(child.attrs.get("class") or ""):
            sub = _without_navigation(child)
            sub.parent = copy
            copy.children.append(sub)
    return copy


def extract_agibot_product(config: SourceAdapterConfig, body: bytes,
                           url: str | None) -> ProductExtraction:
    """Identity only: URL slug == visible `AGIBOT <model>` heading. Pure and deterministic."""
    try:
        path = urlsplit(normalize_url(url or "")).path
    except UnsupportedUrl:
        return ProductExtraction("NOTHING_FOUND", notes=("no page URL",))
    slug = _PAGES.get(path)
    if slug is None:
        return ProductExtraction("NOTHING_FOUND", notes=("URL is not a reviewed product page",))
    tree = html._Tree()
    tree.feed(body.decode("utf-8", errors="replace"))
    tree.close()
    models = {m.group("model") for b in html._blocks(_without_navigation(tree.root))
              if (m := _HEADING.fullmatch(b))}
    if not models:
        return ProductExtraction("NOTHING_FOUND", notes=("no visible 'AGIBOT <model>' heading",))
    if models != {slug}:
        return ProductExtraction("AMBIGUOUS", notes=(
            f"headings name {sorted(models)}, the URL slug is {slug!r}",))
    return ProductExtraction(
        "EXTRACTED", name=slug, name_method="SELECTOR",
        notes=("agreeing locators: ['url_slug', 'heading_block']; canonical ignored "
               "(it points to the homepage)", "identity only: no specification or price read"))


CONFIG = SourceAdapterConfig(
    key="agibot-official",
    version="0.1.0",
    source_key="agibot-official",
    source_class="MANUFACTURER",
    host="www.agibot.com",
    manufacturer="AgiBot",
    allowed_path_prefixes=("/products/A2", "/products/X2"),
    seed_urls=("https://www.agibot.com/products/A2", "https://www.agibot.com/products/X2"),
    product_path_pattern=re.compile(r"/products/(?:A2|X2)"),
    announcement_path_pattern=None,
    heading_identity=False,
    product_extractor=extract_agibot_product,
    target_cap=1,
    structural_review="2026-10-18 read-only inspection (6 requests); "
    "docs/discovery/AGIBOT_STRUCTURAL_REVIEW_2026-10-18.md",
)
