"""XPENG (XPeng Inc.) — official xpeng.com site, for the humanoid robot IRON only.

Owner source decision (2026-10-03, Robert Konecny, work order "XPENG / IRON governed manufacturer
onboarding"): XPENG official web sources on `xpeng.com` are OWNER-APPROVED / ALLOWED for governed
research and discovery of the XPENG humanoid IRON. That decision is recorded in the database
through `discovery source review` at registration, never here, and it does not expire. robots.txt
is read and recorded on every run for provenance; it does not reopen the owner's decision, and
no technical access control is ever bypassed.

Structural review (2026-10-03, read-only, one request per page with the crawler's own user agent,
3 s apart): docs/discovery/XPENG_STRUCTURAL_REVIEW_2026-10-03.md. Everything below is limited to
what those responses established; no URL family is guessed.

Scope. Only IRON is in scope: cars, Robotaxi, flying cars and generic "Physical AI" are never
read as humanoid candidates. The adapter is therefore a FIXED, reviewed set of four seed pages and
nothing else (`target_cap` is the minimum; no pattern lets the crawler follow links to other
XPENG content):

  - the IRON product / technology page (also the only page that can yield a candidate),
  - the 2026-09-08 production-line announcement,
  - the 2025-11-05 Next-Gen IRON announcement (the Australian regional copy of the release),
  - the 2024-11-06 original IRON unveiling.

IDENTITY-ONLY product extractor (`extract_xpeng_product`). The product page's <title> and
<meta> are the site-wide car-site boilerplate, so identity rests on two independent locators that
must agree: the URL slug (`/technology/ai_robot_iron`) and the page's own visible title block
(`XPENG [Next-Gen ]IRON: ...`), with the page's canonical URL and og:url pointing at the same
page. No claim, signal or image is emitted: every specification is a PROPOSAL read later by the
separately governed extractor (`xpeng_iron_proposals`).
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import ProductExtraction, SourceAdapterConfig
from app.services.discovery.sources import xpeng_iron_proposals as proposals
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

OWNER_SOURCE_DECISION = (
    "2026-10-03 robert@humanoid.company: xpeng.com official sources OWNER-APPROVED / ALLOWED for "
    "governed research of the XPENG humanoid IRON; robots.txt and terms are recorded for "
    "provenance and do not reopen this decision; no technical access control may be bypassed"
)

#: What the inspection established, as data (asserted by the tests).
STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-10-03",
    "requests": (
        ("https://www.xpeng.com/robots.txt", 200),
        ("https://www.xpeng.com/technology/ai_robot_iron", 200),
        ("https://www.xpeng.com/news/01a080371029a057bc8e8a02a2c6012b", 200),
        ("https://www.xpeng.com/au/news/019e71be4f9e9dd703de8a0282290455", 200),
        ("https://www.xpeng.com/news/019301d2135392fa562d8a0282200016", 200),
    ),
    # `User-agent: *` disallows only /api and some query-string patterns; no group names our token.
    "robots_status": "ALLOWED",
    "crawl_delay_seconds": None,
    "robots_disallow": ("/api", "*?tblci=*", "*?trk=*", "*?ref=*", "*?v=*", "*?model*",
                        "*?parentId=*", "*?categoryId=*", "*?fromNav=*", "*?ad=*", "*?os=*"),
    "server_rendered": True,
    "page_titles": {
        "/technology/ai_robot_iron": "generic site-wide boilerplate (not an identity locator)",
        "news pages": "the article headline",
    },
    "identity_issues": (
        "the IRON product page's <title>, og:title and JSON-LD name are generic XPENG car-site "
        "boilerplate; identity is read from the visible title block instead",
        "the product page, announced as 'Next-Gen IRON', states 22-DoF hands while the 2026-09-08 "
        "release states 21 DoF in each hand: independent statements, kept apart as proposals",
    ),
}

_PRODUCT_PATH = "/technology/ai_robot_iron"
_HERO = re.compile(r"XPENG (?:Next-Gen )?(?P<name>IRON): .+")


def extract_xpeng_product(config: SourceAdapterConfig, body: bytes,
                          url: str | None) -> ProductExtraction:
    """Identity-only extraction for the IRON product page. Pure and deterministic."""
    try:
        page_url = normalize_url(url or "")
    except UnsupportedUrl:
        return ProductExtraction("NOTHING_FOUND", notes=("no page URL",))
    if urlsplit(page_url).path != _PRODUCT_PATH:
        return ProductExtraction("NOTHING_FOUND", notes=("URL is not the IRON product page",))

    tree = proposals._Tree()
    tree.feed(body.decode("utf-8", errors="replace"))
    tree.close()
    for label in ("canonical", "og:url"):
        stated = tree.head.get(label)
        if stated:
            try:
                agrees = normalize_url(stated) == page_url
            except UnsupportedUrl:
                agrees = False
            if not agrees:
                return ProductExtraction(
                    "AMBIGUOUS", notes=(f"{label} {stated!r} is not this page",))

    names = {m.group("name") for b in proposals._blocks(tree.root) if (m := _HERO.fullmatch(b))}
    if not names:
        return ProductExtraction("NOTHING_FOUND", notes=(
            "no visible 'XPENG [Next-Gen] IRON: ...' title block; <title> is site boilerplate",))
    if len(names) > 1:
        return ProductExtraction("AMBIGUOUS", notes=(f"title blocks disagree: {sorted(names)}",))
    name = next(iter(names))
    slug_tail = urlsplit(page_url).path.rsplit("_", 1)[-1]
    if slug_tail != name.lower():
        return ProductExtraction("AMBIGUOUS", notes=(
            f"name {name!r} does not match the URL slug tail {slug_tail!r}",))
    return ProductExtraction(
        "EXTRACTED", name=name, name_method="SELECTOR",
        notes=("agreeing locators: ['url_slug', 'title_block', 'canonical']",
               "identity only: specifications, dates and plans are proposals, never claims"))


CONFIG = SourceAdapterConfig(
    key="xpeng-official",
    version="0.1.0",
    source_key="xpeng-official",
    source_class="MANUFACTURER",
    host="www.xpeng.com",
    # Canonical catalogue manufacturer name, verbatim. No aliases.
    manufacturer="XPeng Robotics",
    allowed_path_prefixes=("/technology/ai_robot_iron", "/news/", "/au/news/"),
    # Exactly the four reviewed pages; nothing is discovered by following links.
    seed_urls=tuple(proposals.PAGE_URLS),
    # Only the IRON product page can yield a candidate.
    product_path_pattern=re.compile(r"/technology/ai_robot_iron"),
    announcement_path_pattern=None,
    property_map={},
    quote_phrases=(),
    heading_identity=False,
    product_extractor=extract_xpeng_product,
    # No link-following target is ever wanted: the seeds are the whole set.
    target_cap=1,
    structural_review="2026-10-03 read-only inspection (5 requests); "
    "docs/discovery/XPENG_STRUCTURAL_REVIEW_2026-10-03.md",
)
