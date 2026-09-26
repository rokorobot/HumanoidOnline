"""Live source adapters — docs/16 §12 / §12.1 (Slice B).

An adapter is reviewed CODE, one versioned module per source under
`app/services/discovery/sources/`. It carries everything that decides crawler
behaviour for that source — seed URLs, URL patterns, extraction rules, version,
expected source class and the canonical manufacturer identity. The database
holds only runtime approval and state (`discovery_source`: ToS decision,
robots status, enablement, approved host/path prefixes). Nothing read from the
database can widen what an adapter fetches.

Everything in this module is PURE: bytes in, dataclasses out. No network, no
database, no clock. That is what makes fixture replay byte-identical (§15,
Gate I) and an extraction change reviewable as a diff.

Two jobs:

1. `enumerate_targets` — the one bounded enumeration step (§12.1): links (or a
   reviewed sitemap's `<loc>` entries) from the fixed seed pages, kept only when
   same host, inside an approved path prefix, matching the adapter's product or
   announcement pattern, and allowed by robots.txt. Unseen URLs first; over the
   cap they are DEFERRED and recorded, never silently dropped.

2. `extract_product` / `extract_announcement` — deterministic extraction.
   schema.org JSON-LD first, then narrowly declared HTML fallbacks. Every claim
   and signal carries the exact supporting excerpt (<= 1000 characters) and a
   locator; a value without one is rejected, not stored. A missing value stays
   missing — nothing here defaults a commercial fact.
"""
from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from app.models.acquisition import EVIDENCE_EXCERPT_MAX_CHARS
from app.services.discovery.identity import normalize
from app.services.discovery.robots import RobotsRules
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

PRODUCT = "PRODUCT"
ANNOUNCEMENT = "ANNOUNCEMENT"

#: Classes whose own pages may lead to an official-URL lead on a candidate.
OFFICIAL_CLASSES = frozenset({"MANUFACTURER", "AUTHORIZED_DISTRIBUTOR", "OFFICIAL_STORE"})

#: schema.org ItemAvailability -> availability_status. Only values that state
#: obtainability explicitly are mapped. OutOfStock / SoldOut / BackOrder say a
#: listing is not orderable right now, not that the robot is unavailable, so
#: they produce NO signal (UNKNOWN stays UNKNOWN, docs/16 §6).
SCHEMA_AVAILABILITY = {
    "instock": "AVAILABLE",
    "onlineonly": "AVAILABLE",
    "instoreonly": "AVAILABLE",
    "preorder": "PREORDER",
    "presale": "PREORDER",
    "limitedavailability": "LIMITED",
    "discontinued": "DISCONTINUED",
}

_WS = re.compile(r"\s+")
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
_XML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


# ------------------------------------------------------------------- config --


@dataclass(frozen=True)
class SourceAdapterConfig:
    """One source's reviewed crawler behaviour. Instances live in code only."""

    key: str
    version: str
    #: The `discovery_source.key` this adapter may run against.
    source_key: str
    #: The class the source must be registered with; a mismatch refuses the run.
    source_class: str
    host: str
    #: Canonical manufacturer identity, as reviewed configuration (never inferred
    #: from pages, never an alias): every candidate from this source carries it.
    manufacturer: str
    allowed_path_prefixes: tuple[str, ...]
    #: Fixed, reviewed seed pages (HTML listing pages or an explicit sitemap).
    seed_urls: tuple[str, ...]
    #: Full-match patterns on the normalized URL PATH.
    product_path_pattern: re.Pattern
    announcement_path_pattern: re.Pattern | None = None
    #: JSON-LD `additionalProperty` name (case-folded) -> (field_key, required unit
    #: or None). Unmapped properties are counted as unsupported, never guessed.
    property_map: Mapping[str, tuple[str, str | None]] = field(default_factory=dict)
    #: Exact visible-text phrases (case-insensitive) that state price-on-request.
    quote_phrases: tuple[str, ...] = ()
    #: Reference to the recorded structural check (docs/16 §12.1). None means the
    #: source's pages have not been confirmed server-rendered / JSON-LD-bearing,
    #: and the runner refuses a live run.
    structural_review: str | None = None
    #: docs/16 §12.1: at most this many target pages per source and run.
    target_cap: int = 50
    #: May the page's first <h1> name a product when there is no JSON-LD Product?
    #: False for sources whose <h1> is known not to be a product name.
    heading_identity: bool = True
    #: Set when the structural review found the source NOT safe to run with the
    #: current extraction rules. The runner refuses while it is set, whatever
    #: the source's approval state.
    blocked_reason: str | None = None

    def kind_of(self, url: str) -> str | None:
        path = urlsplit(url).path or "/"
        if self.product_path_pattern.fullmatch(path):
            return PRODUCT
        if self.announcement_path_pattern and self.announcement_path_pattern.fullmatch(path):
            return ANNOUNCEMENT
        return None


# ------------------------------------------------------------------ parsing --


class _Page(HTMLParser):
    """Visible text, title, first <h1>, anchor hrefs and raw JSON-LD blocks."""

    _SKIP = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.links: list[str] = []
        self.jsonld: list[str] = []
        self.title = ""
        self.h1 = ""
        self._skip = 0
        self._in_jsonld = False
        self._buf: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._h1_done = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])
        if tag in self._SKIP:
            if tag == "script" and (attributes.get("type") or "").strip().lower() == \
                    "application/ld+json":
                self._in_jsonld, self._buf = True, []
            else:
                self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "h1" and not self._h1_done:
            self._in_h1 = True

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self.jsonld.append("".join(self._buf))
            self._in_jsonld = False
        elif tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "h1" and self._in_h1:
            self._in_h1, self._h1_done = False, True

    def handle_data(self, data):
        if self._in_jsonld:
            self._buf.append(data)
            return
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._in_h1:
            self.h1 += data
        self.text.append(data)


@dataclass(frozen=True)
class ParsedPage:
    text: str
    title: str
    h1: str
    links: tuple[str, ...]
    jsonld: tuple[object, ...]  # parsed blocks; an unparseable block is None


def _collapse(value: str) -> str:
    return _WS.sub(" ", value).strip()


def parse_page(body: bytes) -> ParsedPage:
    parser = _Page()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    blocks: list[object] = []
    for raw in parser.jsonld:
        try:
            blocks.append(json.loads(raw))
        except ValueError:
            blocks.append(None)
    return ParsedPage(
        text=_collapse(" ".join(parser.text)), title=_collapse(parser.title),
        h1=_collapse(parser.h1), links=tuple(parser.links), jsonld=tuple(blocks),
    )


def _is_sitemap(body: bytes) -> bool:
    head = body.lstrip()[:400].lower()
    return head.startswith(b"<?xml") and (b"<urlset" in head or b"<sitemapindex" in head) \
        or head.startswith(b"<urlset") or head.startswith(b"<sitemapindex")


def seed_links(body: bytes) -> list[str]:
    """Raw link targets on a seed page: `<loc>` entries of a sitemap, or anchors."""
    if _is_sitemap(body):
        text = _XML_COMMENT.sub("", body.decode("utf-8", errors="replace"))
        return [html.unescape(m) for m in _LOC.findall(text)]
    return list(parse_page(body).links)


# -------------------------------------------------------------- enumeration --


@dataclass
class Enumeration:
    selected: list[str] = field(default_factory=list)
    #: Over the cap: recorded as not fetched this run (docs/16 §12.1).
    deferred: list[str] = field(default_factory=list)
    #: (url, reason) for links that were not targets. Reasons are policy, not noise:
    #: OFF_HOST, OUTSIDE_PATHS, NO_PATTERN, ROBOTS_DISALLOW, UNSUPPORTED_URL.
    excluded: list[tuple[str, str]] = field(default_factory=list)


def _within(path: str, prefix: str) -> bool:
    if prefix.endswith("/"):
        return path.startswith(prefix) or path == prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def enumerate_targets(
    config: SourceAdapterConfig,
    seeds: Iterable[tuple[str, bytes]],
    robots: RobotsRules,
    last_seen: Mapping[str, datetime],
) -> Enumeration:
    """One level of target URLs from the seed bodies. Pure and deterministic.

    `seeds` are (page URL, body). `last_seen` maps a target URL to its latest
    observation for this source: unseen URLs come first (sorted), then the
    least recently seen. The first `target_cap` are selected; the rest deferred.
    """
    result = Enumeration()
    found: set[str] = set()
    excluded: dict[str, str] = {}
    seed_set = {normalize_url(u) for u in config.seed_urls}
    for page_url, body in seeds:
        for href in seed_links(body):
            absolute = urljoin(page_url, href.strip())
            try:
                url = normalize_url(absolute)
            except UnsupportedUrl:
                if absolute.lower().startswith(("http:", "https:")):
                    excluded.setdefault(absolute, "UNSUPPORTED_URL")
                continue  # mailto:, tel:, javascript: are not links to pages
            if url in seed_set or url in found:
                continue
            parts = urlsplit(url)
            path = parts.path or "/"
            if parts.hostname != config.host:
                reason = "OFF_HOST"
            elif not any(_within(path, p) for p in config.allowed_path_prefixes):
                reason = "OUTSIDE_PATHS"
            elif config.kind_of(url) is None:
                reason = "NO_PATTERN"
            elif not robots.allows(url):
                reason = "ROBOTS_DISALLOW"
            else:
                found.add(url)
                continue
            excluded.setdefault(url, reason)
    ordered = sorted(found, key=lambda u: (u in last_seen, last_seen.get(u) or datetime.min, u))
    result.selected = ordered[: config.target_cap]
    result.deferred = ordered[config.target_cap:]
    result.excluded = sorted(excluded.items())
    return result


# --------------------------------------------------------------- extraction --


@dataclass(frozen=True)
class Evidence:
    excerpt: str
    locator: str


@dataclass(frozen=True)
class ExtractedClaim:
    field_key: str
    claimed_value: str
    unit: str | None
    method: str
    confidence: str
    evidence: Evidence


@dataclass(frozen=True)
class ExtractedSignal:
    axis: str  # MATURITY | OBTAINABILITY | PRICE
    method: str
    confidence: str
    evidence: Evidence
    availability_value: str | None = None
    maturity_value: str | None = None
    price_type: str | None = None
    price_amount: Decimal | None = None
    price_currency: str | None = None
    region_code: str | None = None


@dataclass(frozen=True)
class ExtractedImage:
    image_url: str
    alt_text: str | None
    locator: str


@dataclass(frozen=True)
class ProductExtraction:
    status: str  # EXTRACTED | NOTHING_FOUND | AMBIGUOUS
    name: str | None = None
    name_method: str | None = None
    claims: tuple[ExtractedClaim, ...] = ()
    signals: tuple[ExtractedSignal, ...] = ()
    images: tuple[ExtractedImage, ...] = ()
    #: What was seen but not stored, and why (unmapped property, no evidence...).
    rejected: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnnouncementExtraction:
    headline: str | None
    evidence: Evidence | None
    #: Set only when the page's structured data explicitly names ONE product of
    #: this source's manufacturer. Otherwise the URL waits for a human.
    product_name: str | None = None
    notes: tuple[str, ...] = ()


def _compact(node: object) -> str:
    return json.dumps(node, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _types(node: Mapping) -> set[str]:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return {str(k).split("/")[-1].lower() for k in kinds if k}


def _walk(node: object, pointer: str):
    """Yield (pointer, dict node) for every object in a JSON-LD block."""
    if isinstance(node, Mapping):
        yield pointer, node
        for key in sorted(node):
            yield from _walk(node[key], f"{pointer}/{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, f"{pointer}/{i}")


def _nodes_of(page: ParsedPage, *kinds: str) -> list[tuple[str, Mapping]]:
    wanted = {k.lower() for k in kinds}
    out: list[tuple[str, Mapping]] = []
    for index, block in enumerate(page.jsonld):
        if block is None:
            continue
        for pointer, node in _walk(block, f"jsonld[{index}]"):
            if _types(node) & wanted:
                out.append((pointer, node))
    return out


def _as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value: object) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("name")
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        cleaned = _collapse(str(value))
        return cleaned or None
    return None


def _evidence(excerpt: str, locator: str) -> Evidence | None:
    excerpt = excerpt.strip()
    if not excerpt or len(excerpt) > EVIDENCE_EXCERPT_MAX_CHARS:
        return None
    return Evidence(excerpt, locator)


def _brand_matches(node: Mapping, manufacturer: str) -> bool | None:
    """True/False when a brand/manufacturer is stated; None when it is not."""
    stated = [_text(v) for v in (*_as_list(node.get("brand")), *_as_list(node.get("manufacturer")))]
    stated = [s for s in stated if s]
    if not stated:
        return None
    return any(normalize(s) == normalize(manufacturer) for s in stated)


def _price(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount > 0 else None


def _region(offer: Mapping) -> str | None:
    for key in ("eligibleRegion", "areaServed"):
        for value in _as_list(offer.get(key)):
            code = _text(value)
            if code and re.fullmatch(r"[A-Za-z]{2}", code):
                return code.upper()
    return None


def _offer_signals(pointer: str, offer: Mapping, rejected: list[str]) -> list[ExtractedSignal]:
    evidence = _evidence(_compact(offer), pointer)
    if evidence is None:
        rejected.append(
            f"{pointer}: offer excerpt missing or over {EVIDENCE_EXCERPT_MAX_CHARS} chars")
        return []
    region = _region(offer)
    signals: list[ExtractedSignal] = []
    amount = _price(offer.get("price"))
    currency = _text(offer.get("priceCurrency"))
    if offer.get("price") is not None:
        if amount is not None and currency and re.fullmatch(r"[A-Za-z]{3}", currency):
            signals.append(ExtractedSignal(
                "PRICE", "JSONLD", "HIGH", evidence, price_type="PUBLIC",
                price_amount=amount, price_currency=currency.upper(), region_code=region,
            ))
        else:
            rejected.append(f"{pointer}: price without a valid amount and ISO currency")
    availability = _text(offer.get("availability"))
    if availability:
        mapped = SCHEMA_AVAILABILITY.get(availability.rstrip("/").split("/")[-1].lower())
        if mapped:
            signals.append(ExtractedSignal(
                "OBTAINABILITY", "JSONLD", "HIGH", evidence,
                availability_value=mapped, region_code=region,
            ))
        else:
            rejected.append(f"{pointer}: availability {availability!r} states no obtainability")
    return signals


def _quote_signals(config: SourceAdapterConfig, page: ParsedPage) -> list[ExtractedSignal]:
    lowered = page.text.lower()
    for phrase in config.quote_phrases:
        start = lowered.find(phrase.lower())
        if start < 0:
            continue
        lo, hi = max(0, start - 120), min(len(page.text), start + len(phrase) + 120)
        evidence = _evidence(page.text[lo:hi], f"offset:{lo}-{hi}")
        if evidence is None:
            continue
        return [
            ExtractedSignal("PRICE", "PATTERN", "MEDIUM", evidence, price_type="QUOTE_ONLY"),
            ExtractedSignal("OBTAINABILITY", "PATTERN", "MEDIUM", evidence,
                            availability_value="ON_REQUEST"),
        ]
    return []


def _property_claims(config, pointer, product, rejected) -> list[ExtractedClaim]:
    claims: list[ExtractedClaim] = []
    for i, prop in enumerate(_as_list(product.get("additionalProperty"))):
        if not isinstance(prop, Mapping):
            continue
        where = f"{pointer}/additionalProperty/{i}"
        name = _text(prop.get("name"))
        value = _text(prop.get("value"))
        if not name or value is None:
            rejected.append(f"{where}: property without a name and value")
            continue
        mapped = config.property_map.get(name.casefold())
        if mapped is None:
            rejected.append(f"{where}: unsupported property {name!r}")
            continue
        field_key, required_unit = mapped
        unit = _text(prop.get("unitText")) or _text(prop.get("unitCode"))
        if required_unit is not None and (unit or "").lower() != required_unit.lower():
            rejected.append(f"{where}: {name!r} unit {unit!r} is not {required_unit!r}")
            continue
        evidence = _evidence(_compact(prop), where)
        if evidence is None:
            rejected.append(f"{where}: excerpt missing or over {EVIDENCE_EXCERPT_MAX_CHARS} chars")
            continue
        claims.append(ExtractedClaim(field_key, value, unit, "JSONLD", "HIGH", evidence))
    return claims


def _images(pointer: str, product: Mapping) -> list[ExtractedImage]:
    out: list[ExtractedImage] = []
    for i, image in enumerate(_as_list(product.get("image"))):
        url = image if isinstance(image, str) else (
            (image.get("contentUrl") or image.get("url")) if isinstance(image, Mapping) else None)
        alt = (_text(image.get("caption") or image.get("name"))
               if isinstance(image, Mapping) else None)
        if isinstance(url, str) and url.strip().lower().startswith(("http://", "https://")):
            out.append(ExtractedImage(url.strip(), alt, f"{pointer}/image/{i}"))
    return out


def extract_product(config: SourceAdapterConfig, body: bytes) -> ProductExtraction:
    """Deterministic product-page extraction. Pure: the same bytes always give
    the same result."""
    page = parse_page(body)
    products = _nodes_of(page, "Product", "ProductModel", "IndividualProduct")
    named = [(p, n) for p, n in products if _text(n.get("name"))]
    names = sorted({_text(n.get("name")) for _, n in named})
    if len(names) > 1:
        return ProductExtraction("AMBIGUOUS", notes=(
            f"page describes {len(names)} distinct products: {names}",))
    rejected: list[str] = []
    if named:
        pointer, product = named[0]
        name = _text(product.get("name"))
        brand = _brand_matches(product, config.manufacturer)
        if brand is False:
            return ProductExtraction("AMBIGUOUS", notes=(
                f"product {name!r} is branded for another manufacturer",))
        claims = _property_claims(config, pointer, product, rejected)
        signals: list[ExtractedSignal] = []
        for i, offer in enumerate(_as_list(product.get("offers"))):
            if isinstance(offer, Mapping):
                where = pointer + "/offers" + (f"/{i}" if isinstance(product.get("offers"), list)
                                               else "")
                signals += _offer_signals(where, offer, rejected)
        if not any(s.axis == "PRICE" for s in signals):
            signals += _quote_signals(config, page)
        return ProductExtraction(
            "EXTRACTED", name=name, name_method="JSONLD", claims=tuple(claims),
            signals=tuple(signals), images=tuple(_images(pointer, product)),
            rejected=tuple(rejected),
        )
    if page.h1 and config.heading_identity:
        # No structured data: identity from the page heading only. No specs and no
        # commercial facts are read from free text beyond the declared phrases.
        return ProductExtraction(
            "EXTRACTED", name=page.h1, name_method="SELECTOR",
            signals=tuple(_quote_signals(config, page)),
            notes=("no JSON-LD Product; name from <h1>",),
        )
    if page.h1:
        return ProductExtraction("NOTHING_FOUND", notes=(
            "no JSON-LD Product; <h1> is not an identity source for this adapter",))
    return ProductExtraction("NOTHING_FOUND", notes=("no JSON-LD Product and no <h1>",))


def extract_announcement(config: SourceAdapterConfig, body: bytes) -> AnnouncementExtraction:
    """Headline + one bounded excerpt. A product identity only when structured
    data explicitly names exactly one product of this source's manufacturer."""
    page = parse_page(body)
    articles = _nodes_of(page, "NewsArticle", "Article", "BlogPosting", "PressRelease")
    headline = evidence = None
    notes: list[str] = []
    if articles:
        pointer, article = articles[0]
        headline = _text(article.get("headline")) or _text(article.get("name"))
        description = _text(article.get("description"))
        if description:
            evidence = _evidence(description, f"{pointer}/description")
    headline = headline or page.h1 or page.title or None
    if evidence is None and page.text:
        start = page.text.find(page.h1) if page.h1 else 0
        start = max(start, 0)
        end = min(len(page.text), start + 500)
        evidence = _evidence(page.text[start:end], f"offset:{start}-{end}")
    products: set[str] = set()
    for _pointer, article in articles:
        for key in ("about", "mentions"):
            for node in _as_list(article.get(key)):
                named = isinstance(node, Mapping) and "product" in _types(node)
                if named and _text(node.get("name")):
                    if _brand_matches(node, config.manufacturer):
                        products.add(_text(node.get("name")))
                    else:
                        notes.append(f"product {_text(node.get('name'))!r} lacks explicit "
                                     f"{config.manufacturer!r} brand")
    if len(products) > 1:
        notes.append(f"names {len(products)} products: {sorted(products)}")
    return AnnouncementExtraction(
        headline=headline, evidence=evidence,
        product_name=next(iter(products)) if len(products) == 1 else None,
        notes=tuple(notes),
    )


def extraction_digest(extraction: ProductExtraction | AnnouncementExtraction) -> str:
    """Canonical serialization of an extraction, for byte-identical replay (§15)."""
    def default(value):
        if isinstance(value, Decimal):
            return str(value)
        return value.__dict__
    return json.dumps(extraction, default=default, sort_keys=True, ensure_ascii=False)
