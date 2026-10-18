"""Agility Robotics — official www.agilityrobotics.com product page for Digit 5.

Access basis (docs/28, A4): owner instruction 2026-10-18, OWNER_AUTHORIZED, which is not publisher
consent: `tos_status` stays UNKNOWN. robots.txt states only a Sitemap line (nothing disallowed).
It is re-read on every run.

Structural review: docs/discovery/AGILITY_STRUCTURAL_REVIEW_2026-10-18.md (6 requests).

Scope: ONE fixed product page, `/solutions/digit-5`. The spec sheet is form-gated (not in the
HTML), and `/sales` is a form; neither is read. `/content/` press articles are not seeds in v0.1.

Source-specific extractor (identity first) (`extract_agility_product`). The `<h1>` is a tagline
("Digit 5: Safety designed …"), so the generic `<h1>` rule cannot name the product. Identity
needs three things to agree: `<title>` `<name> | Agility`, the name slugified equal to the URL
slug (`digit-5`), and the `<h1>` beginning with that name. Whether "Digit 5" is the catalogue's
"Digit" is a human identity decision. v0.2.0 also records the page's stat block (Payload*,
Reach*, Run to charge ratio*, Work/Shift*) as verbatim claims `agility.spec[<model>]/<label>`.
No signal is emitted; executive biographies' "$" amounts are never read.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import ProductExtraction, SourceAdapterConfig
from app.services.discovery.sources import xpeng_iron_proposals as html
from app.services.discovery.sources.spec_claims import SpecClaims, find, text
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-10-18",
    "robots_status": "ALLOWED",
    "identity": "<title> 'Digit 5 | Agility' + URL slug + <h1> prefix",
    "commercial_language": "no price; 'Contact sales' -> /sales (a form)",
}

_PAGES = {"/solutions/digit-5": "digit-5"}
_TITLE = re.compile(r"(?P<name>.+?) \| Agility")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _first(tree, tag: str) -> str | None:
    node = next((n for n in html._walk(tree.root) if n.tag == tag), None)
    return " ".join(html._text(node).split()) if node is not None else None


def extract_agility_product(config: SourceAdapterConfig, body: bytes,
                            url: str | None) -> ProductExtraction:
    """Identity only: `<title>` name == URL slug, and the `<h1>` starts with it. Pure."""
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
    title, h1 = _first(tree, "title"), _first(tree, "h1")
    match = _TITLE.fullmatch(title or "")
    if match is None:
        return ProductExtraction("NOTHING_FOUND", notes=(f"<title> {title!r} names no product",))
    name = match.group("name").strip()
    if _slug(name) != slug or not (h1 or "").startswith(name):
        return ProductExtraction("AMBIGUOUS", notes=(
            f"<title> name {name!r}, URL slug {slug!r} and <h1> {h1!r} do not agree",))
    specs = SpecClaims("agility")
    for stat in find(tree.root, cls="_3d-model-stat"):
        labels = find(stat, cls="_3d-model-stat-label")
        numbers = find(stat, cls="_3d-model-stat-number")
        if len(labels) == 1 and len(numbers) == 1:
            label = text(labels[0])
            specs.add(name, label, text(numbers[0]), f"3d-model-stats/stat[{label}]")
        else:
            specs.rejected.append("3d-model-stats/stat: not exactly one label and one number")
    return ProductExtraction(
        "EXTRACTED", name=name, name_method="SELECTOR", claims=specs.claims,
        rejected=tuple(specs.rejected),
        notes=("agreeing locators: ['title', 'url_slug', 'h1_prefix']",
               "specifications: the 'Explore Digit' stat block, verbatim (labels keep their '*' "
               "footnote marker); no deployment, price or availability read"))


CONFIG = SourceAdapterConfig(
    key="agility-robotics-official",
    version="0.2.0",
    source_key="agility-robotics-official",
    source_class="MANUFACTURER",
    host="www.agilityrobotics.com",
    manufacturer="Agility Robotics",
    allowed_path_prefixes=("/solutions/digit-5",),
    seed_urls=("https://www.agilityrobotics.com/solutions/digit-5",),
    product_path_pattern=re.compile(r"/solutions/digit-5"),
    announcement_path_pattern=None,
    heading_identity=False,
    product_extractor=extract_agility_product,
    target_cap=1,
    structural_review="2026-10-18 read-only inspection (6 requests); "
    "docs/discovery/AGILITY_STRUCTURAL_REVIEW_2026-10-18.md",
)
