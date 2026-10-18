"""Figure AI — official www.figure.ai product page (`/figure`, currently Figure 03).

Access basis (docs/28, A4): owner instruction 2026-10-18, OWNER_AUTHORIZED, which is not publisher
consent: `tos_status` stays UNKNOWN. robots.txt disallows only `/index-privacy-policy` and `/info`,
neither of which is in scope. It is re-read on every run.

Structural review: docs/discovery/FIGURE_STRUCTURAL_REVIEW_2026-10-18.md (6 requests).

Scope: ONE fixed product page, `/figure`. `/news` articles are not seeds in v0.1.

IDENTITY-ONLY, source-specific extractor (`extract_figure_product`). There is no canonical and
no JSON-LD, and the URL names no model. Identity needs `<title>` `<name> | Figure` to equal the
first `<h1>` (case-insensitively: `Figure 03` / `FIGURE 03`). The candidate takes the title's
spelling. When the page moves to a new generation the name changes with it, and Stage E reports
that as an identity change for a human. Generation naming (Figure 03 / F.03) and aliases stay
human decisions. No claim, signal or image is emitted.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import ProductExtraction, SourceAdapterConfig
from app.services.discovery.sources import xpeng_iron_proposals as html
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-10-18",
    "robots_status": "ALLOWED",
    "robots_disallow": ("/index-privacy-policy", "/info"),
    "identity": "<title> 'Figure 03 | Figure' == first <h1> 'FIGURE 03' (case-insensitive)",
    "commercial_language": "none",
}

_PRODUCT_PATH = "/figure"
_TITLE = re.compile(r"(?P<name>.+?) \| Figure")


def _first(tree, tag: str) -> str | None:
    node = next((n for n in html._walk(tree.root) if n.tag == tag), None)
    return " ".join(html._text(node).split()) if node is not None else None


def extract_figure_product(config: SourceAdapterConfig, body: bytes,
                           url: str | None) -> ProductExtraction:
    """Identity only: `<title>` name == first `<h1>` (case-insensitive). Pure."""
    try:
        path = urlsplit(normalize_url(url or "")).path
    except UnsupportedUrl:
        return ProductExtraction("NOTHING_FOUND", notes=("no page URL",))
    if path != _PRODUCT_PATH:
        return ProductExtraction("NOTHING_FOUND", notes=("URL is not the reviewed product page",))
    tree = html._Tree()
    tree.feed(body.decode("utf-8", errors="replace"))
    tree.close()
    title, h1 = _first(tree, "title"), _first(tree, "h1")
    match = _TITLE.fullmatch(title or "")
    if match is None or not h1:
        return ProductExtraction("NOTHING_FOUND", notes=(f"<title> {title!r}, <h1> {h1!r}",))
    name = match.group("name").strip()
    if name.casefold() != h1.casefold():
        return ProductExtraction("AMBIGUOUS", notes=(
            f"<title> name {name!r} and first <h1> {h1!r} disagree",))
    return ProductExtraction(
        "EXTRACTED", name=name, name_method="SELECTOR",
        notes=("agreeing locators: ['title', 'h1']", "identity only: no specification read"))


CONFIG = SourceAdapterConfig(
    key="figure-ai-official",
    version="0.1.0",
    source_key="figure-ai-official",
    source_class="MANUFACTURER",
    host="www.figure.ai",
    manufacturer="Figure",
    allowed_path_prefixes=("/figure",),
    seed_urls=("https://www.figure.ai/figure",),
    product_path_pattern=re.compile(r"/figure"),
    announcement_path_pattern=None,
    heading_identity=False,
    product_extractor=extract_figure_product,
    target_cap=1,
    structural_review="2026-10-18 read-only inspection (6 requests); "
    "docs/discovery/FIGURE_STRUCTURAL_REVIEW_2026-10-18.md",
)
