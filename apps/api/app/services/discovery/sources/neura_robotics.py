"""NEURA Robotics — official manufacturer site. Structurally reviewed; BLOCKED.

Owner ToS decision: Robert read the terms himself and decided ALLOWED
(2026-09-26, DR-A4). That decision is recorded in the database through
`discovery source review` at registration, never here, and it does not expire.

Structural review: 2026-09-26, read-only, 7 requests with the crawler's own user
agent, 3 s apart. Full record: docs/discovery/NEURA_STRUCTURAL_REVIEW_2026-09-26.md.
Everything below is limited to what those 7 responses established; no URL
family is guessed.

IDENTITY-ONLY extractor (`extract_neura_product`). It names a model only when
the URL slug and at least one more independent deterministic locator agree:

  1. the URL family and slug (`/product/<slug>-reservation`, `/products/<slug>`);
     the page's canonical URL, when present, must point at the same page;
  2. the page-title pattern, on reservation pages only: `Reserve <name>: ...`,
     in <title> and og:title, which must agree with each other;
  3. the Yoast BreadcrumbList: `Home > Shop > "<name> Reservation"` on
     reservation pages, `Home > Products > "<name>"` on robot pages;
  4. the WooCommerce `single-product` body class, required on reservation pages.

The slug agrees when the name, lower-cased with runs of other characters turned
into "-", equals it. Any disagreement gives AMBIGUOUS; too little evidence gives
NOTHING_FOUND. <h1> and Elementor widget/element ids are never read.

No claim, signal or image is emitted. The refundable reservation fee is a
deposit; the estimated price is a future, quantity-banded estimate excluding tax
and shipping; no actual purchase price was observed. All three stay UNKNOWN. The
schema's `price_type=ESTIMATED` has no field for a quantity band, so it is not
an unambiguous home for the estimate.

The runner still refuses this module (`ADAPTER_BLOCKED`) until the owner
approves the extractor for live use.
"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import ProductExtraction, SourceAdapterConfig
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

BLOCK_CODE = "BLOCKED_PENDING_EXTRACTOR_APPROVAL"

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
    # Three different things, never interchangeable. None of them is mapped.
    "commercial_language": {
        "reservation_fee": "refundable per-unit reservation fee (a deposit), credited "
        "toward a later purchase; NOT a price",
        "estimated_price": "estimated price per unit in quantity bands, excluding taxes "
        "and shipping; NOT an actual purchase price",
        "purchase_price": "no actual purchase price was observed",
    },
}

_RESERVATION_PATH = re.compile(r"/product/(?P<slug>[a-z0-9-]+)-reservation")
_ROBOT_PATH = re.compile(r"/products/(?P<slug>[a-z0-9-]+)")
_TITLE = re.compile(r"Reserve (?P<name>[^:|]+?)\s*:.*")
_RESERVATION_CRUMB = re.compile(r"(?P<name>.+?) Reservation")
_NO_COMMERCE = "identity only: reservation fee, estimated price and purchase price not extracted"


class _Head(HTMLParser):
    """<title>, og:title, canonical, <body class> and JSON-LD text. Nothing else."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.og_title: str | None = None
        self.canonical: str | None = None
        self.body_classes: set[str] = set()
        self.jsonld: list[str] = []
        self._in_title = False
        self._in_jsonld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and a.get("property") == "og:title":
            self.og_title = a.get("content")
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href")
        elif tag == "body":
            self.body_classes = set((a.get("class") or "").split())
        elif tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in_jsonld = True
            self.jsonld.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_jsonld = False

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        elif self._in_jsonld:
            self.jsonld[-1] += data


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", html.unescape(value)).strip()
    return value or None


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _breadcrumb(blocks: list[str]) -> list[str]:
    """Names of the Yoast BreadcrumbList items, in position order."""
    for raw in blocks:
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        nodes = doc.get("@graph", [doc]) if isinstance(doc, dict) else doc
        for node in nodes if isinstance(nodes, list) else []:
            if isinstance(node, dict) and node.get("@type") == "BreadcrumbList":
                items = [i for i in node.get("itemListElement", []) if isinstance(i, dict)]
                items.sort(key=lambda i: i.get("position", 0))
                return [_clean(str(i.get("name", ""))) or "" for i in items]
    return []


def _crumb_after(crumbs: list[str], parent: str) -> str | None:
    return crumbs[-1] if len(crumbs) >= 2 and crumbs[-2] == parent else None


def extract_neura_product(config: SourceAdapterConfig, body: bytes,
                          url: str | None) -> ProductExtraction:
    """Identity-only NEURA product-page extraction. Pure and deterministic."""
    try:
        page_url = normalize_url(url or "")
    except UnsupportedUrl:
        return ProductExtraction("NOTHING_FOUND", notes=("no page URL",))
    path = urlsplit(page_url).path
    reservation = _RESERVATION_PATH.fullmatch(path)
    robot = _ROBOT_PATH.fullmatch(path)
    if not (reservation or robot):
        return ProductExtraction("NOTHING_FOUND", notes=("URL outside the NEURA product families",))
    slug = (reservation or robot).group("slug")

    head = _Head()
    head.feed(body.decode("utf-8", errors="replace"))
    head.close()
    if head.canonical:
        try:
            canonical = normalize_url(head.canonical)
        except UnsupportedUrl:
            canonical = None
        if canonical != page_url:
            return ProductExtraction("AMBIGUOUS", notes=(
                f"canonical {head.canonical!r} is not this page",))

    crumbs = _breadcrumb(head.jsonld)
    names: dict[str, str | None] = {}
    if reservation:
        if "single-product" not in head.body_classes:
            return ProductExtraction("NOTHING_FOUND", notes=(
                "reservation URL without the WooCommerce single-product marker",))
        titles = [t for t in (_clean("".join(head.title)), _clean(head.og_title)) if t]
        from_titles = [(m.group("name").strip() if (m := _TITLE.fullmatch(t)) else None)
                       for t in titles]
        if len(set(from_titles)) > 1:
            return ProductExtraction("AMBIGUOUS", notes=(f"titles disagree: {titles}",))
        names["title"] = from_titles[0] if from_titles else None
        crumb = _crumb_after(crumbs, "Shop")
        match = _RESERVATION_CRUMB.fullmatch(crumb) if crumb else None
        names["breadcrumb"] = match.group("name").strip() if match else None
    else:
        names["breadcrumb"] = _crumb_after(crumbs, "Products")

    present = {k: v for k, v in names.items() if v}
    if not present:
        return ProductExtraction("NOTHING_FOUND", notes=(
            "no title or breadcrumb identity; <h1> is never used", _NO_COMMERCE))
    if len(set(present.values())) > 1:
        return ProductExtraction("AMBIGUOUS", notes=(f"locators disagree: {present}",))
    name = next(iter(present.values()))
    if _slugify(name) != slug:
        return ProductExtraction("AMBIGUOUS", notes=(
            f"name {name!r} does not match URL slug {slug!r}",))
    return ProductExtraction(
        "EXTRACTED", name=name, name_method="SELECTOR",
        notes=(f"agreeing locators: {['url_slug', *sorted(present)]}", _NO_COMMERCE),
    )


CONFIG = SourceAdapterConfig(
    key="neura-robotics-official",
    version="0.3.0",
    source_key="neura-robotics-official",
    source_class="MANUFACTURER",
    host="neura-robotics.com",
    # Canonical catalogue manufacturer name, verbatim. No aliases.
    manufacturer="Neura Robotics",
    allowed_path_prefixes=("/products/", "/product/", "/product-sitemap.xml", "/news/"),
    # Normalized (docs/16 §11) seeds, all observed 200:
    # - the product sitemap: the reservation pages (it omits 4ne1-mini);
    # - the newsroom index: its site-wide nav links every /products/ page;
    # - the 4NE1 reservation page: it links every reservation, including
    #   4ne1-mini. It is itself a product page, so it is extracted from its seed
    #   fetch and never requested twice.
    # NOT /shop/ (301 to the homepage).
    seed_urls=(
        "https://neura-robotics.com/product-sitemap.xml",
        "https://neura-robotics.com/news",
        "https://neura-robotics.com/product/4ne1-reservation",
    ),
    # Full match on the NORMALIZED path (no trailing slash).
    product_path_pattern=re.compile(r"/products/[a-z0-9-]+|/product/[a-z0-9-]+-reservation"),
    # No deterministic article URL shape was observed.
    announcement_path_pattern=None,
    # No JSON-LD properties exist to map.
    property_map={},
    # Reservation/estimate wording must never be read as a quote or a price.
    quote_phrases=(),
    # The /products/ <h1> is a marketing tagline, never a product name.
    heading_identity=False,
    product_extractor=extract_neura_product,
    structural_review="2026-09-26 read-only inspection (7 requests); "
    "docs/discovery/NEURA_STRUCTURAL_REVIEW_2026-09-26.md",
    blocked_reason=(
        f"{BLOCK_CODE}: pages are HTTP/server-rendered and robots-compatible, and the "
        "generic extractor is unsafe for them (no usable Product JSON-LD; <h1> is not a "
        "safe identity source; the refundable reservation fee (deposit) and the estimated "
        "robot price are not a purchase price). A NEURA identity-only extractor is wired "
        "but has not been approved for live use"
    ),
)
