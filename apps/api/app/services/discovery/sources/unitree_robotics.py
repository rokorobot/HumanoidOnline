"""Unitree Robotics — official www.unitree.com product pages for the H2, R1 and G1 humanoids.

Access basis (docs/28, A4): the owner's 2026-10-18 instruction added `unitree-robotics-official`
to the discovery monitoring programme as an OWNER_AUTHORIZED source. That is an internal business
decision, NOT publisher consent: `tos_status` stays UNKNOWN, and the decision is recorded in the
database (`discovery source authorize-owner`), never here. robots.txt is re-read on every run and
no technical access control is ever bypassed.

Structural review (2026-10-18, read-only, 9 requests with the crawler's own user agent):
docs/discovery/UNITREE_STRUCTURAL_REVIEW_2026-10-18.md. Everything below is limited to what those
responses established; no URL family is guessed.

Scope. Only `www.unitree.com`, and only a FIXED, reviewed set of three product pages. The sitemap
lists only `/cn/` pages and cannot seed enumeration, and nothing is discovered by following links
(`target_cap` is the minimum). `unistore.unitree.com`, `support.`, `eai.` … are other hosts and
out of scope. The seeds are the normalized slash-less URLs. The site answers each with a same-host
302 to the trailing-slash URL that serves the page (the NEURA redirect shape).

Source-specific product extractor (`extract_unitree_product`), pure and deterministic:

- IDENTITY needs two agreeing locators: the URL slug (`H2`, `R1`, `g1`) must equal one EDITION
  NAME the page lists (case-insensitively), AND appear as a token of `<title>` (tokens split on
  every non-alphanumeric, so `G1_Humanoid` yields `G1`). The page has no `<h1>`, no canonical and
  no JSON-LD, and `og:title` is site-wide Chinese boilerplate. The candidate is the PAGE'S MODEL
  (`H2` / `R1` / `G1`) as the page writes it. Editions (`H2 EDU`, `R1 AIR`, `G1 EDU`…) are never
  resolved to catalogue robots here: their values carry the edition in the claim key, for a human.
- EDITIONS come from the `ul.versions` list (H2, R1) or the grid's `Model` row (G1). If both are
  present and disagree, the page is AMBIGUOUS.
- SPECIFICATIONS: every `div.params` grid row whose cell count is exactly 1 + editions becomes one
  verbatim TEXT claim per edition: `unitree.spec[<edition>]/<category>/<label>`, `unit=None`.
  Ranges (`26-40`), footnote markers (`【4】`) and "About" wording are kept as written. A
  misaligned row is rejected whole, never partially attributed. These keys are deliberately
  outside promotion's approved fields: nothing here can become a catalogue fact without the
  separately governed trace / review / claim chain.
- PRICES are recorded verbatim per edition (`unitree.price[<edition>]`) with the table's own
  terms header (`unitree.price_terms`, e.g. `Price（Tax and Shipping cost excluded）`). PRICE
  SIGNALS are emitted ONLY for the page model's own row and for the hero `Price from …` line,
  because a signal attaches to the page's candidate and an EDU row's "Contact Sales" must never
  read as the model's price:
    `Contact Sales` -> QUOTE_ONLY;  `Price from …` -> FROM;  a stated amount -> PUBLIC.
  Fail-closed money: a currency is set ONLY when the page states it (`US $`); a bare `$` stays
  currency UNKNOWN. An amount is parsed ONLY for an exact `US $12,345`-shaped value; a `K` suffix
  (`US $13.5K`) is never expanded. So every signal keeps its verbatim excerpt, and amount and
  currency are NULL unless both are literally stated. No VAT, region or availability is inferred:
  the global site states none, and nothing here is an EU price.
"""
from __future__ import annotations

import re
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import (
    ExtractedClaim,
    ExtractedSignal,
    ProductExtraction,
    SourceAdapterConfig,
    _evidence,
)
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

#: What the inspection established, as data (asserted by the tests).
STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-10-18T18:47Z/18:50Z",
    "requests": (
        ("https://www.unitree.com/robots.txt", 200),
        ("https://www.unitree.com/", 200),
        ("https://www.unitree.com/sitemap.xml", 200),
        ("https://www.unitree.com/H2", 302),
        ("https://www.unitree.com/R1", 302),
        ("https://www.unitree.com/g1", 302),
        ("https://www.unitree.com/H2/", 200),
        ("https://www.unitree.com/R1/", 200),
        ("https://www.unitree.com/g1/", 200),
    ),
    # `User-agent:*` / `Disallow:` (empty) behind a UTF-8 BOM; no group names our token.
    "robots_status": "ALLOWED",
    "crawl_delay_seconds": None,
    "server_rendered": True,
    "sitemap": "59 URLs, all under /cn/; none of the English product pages",
    "identity_issues": (
        "no <h1>, no canonical, no JSON-LD; og:title is site-wide Chinese boilerplate",
        "the G1 <title> is an SEO string ('Humanoid robot G1_Humanoid Robot Functions_...')",
        "each page lists several editions (H2/H2 EDU; R1 AIR/R1/R1 EDU; G1/G1 EDU); mapping an "
        "edition to a catalogue robot is a human identity decision",
    ),
    "commercial_language": {
        "table": "Price（Tax and Shipping cost excluded）: per-edition amount or 'Contact Sales'",
        "hero": "'Price from $…' (the cheapest edition), separate from the table",
        "currency": "'$' (H2, R1) or 'US $' (G1); only the latter states a currency",
        "store": "https://unistore.unitree.com: a separate, unregistered host; out of scope",
    },
}

SEED_URLS = ("https://www.unitree.com/H2", "https://www.unitree.com/R1",
             "https://www.unitree.com/g1")
_PRODUCT_PATHS = {urlsplit(u).path: urlsplit(u).path.strip("/") for u in SEED_URLS}

_CONTACT = re.compile(r"contact\s+sales", re.IGNORECASE)
_AMOUNT = re.compile(r"(?P<us>US\s+)?\$\s?(?P<num>\d{1,3}(?:,\d{3})+|\d{1,3})(?P<k>[Kk])?")
_EXACT_USD = re.compile(r"US\s+\$\s?(?P<num>\d{1,3}(?:,\d{3})+)")
_FROM = re.compile(r"Price from \S+")
_TERMS = re.compile(r"Price\s*[（(].*?[）)]")
_TOKENS = re.compile(r"[^A-Za-z0-9]+")
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS.sub(" ", text).strip()


class _Page(HTMLParser):
    """<title>, the `ul.versions` rows, the `div.params` grid and visible text blocks."""

    _SKIP = frozenset({"script", "style", "noscript", "template", "svg"})
    _VOID = frozenset({"br", "img", "meta", "link", "input", "hr", "source", "wbr", "area", "col"})
    _BLOCK = frozenset({"p", "div", "li", "h1", "h2", "h3", "h4", "span", "a", "ul", "section"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.versions: list[list[str]] = []           # each row: [cell, cell]
        self.grid: list[tuple[str, list[str]]] = []   # (category, [label, value, value…])
        self.blocks: list[str] = []
        self._stack: list[tuple[str, frozenset[str]]] = []
        self._skip = 0
        self._title: list[str] | None = None
        self._category: list[str] | None = None
        self._last_category = ""
        self._vrow: list[str] | None = None
        self._vcell: list[str] | None = None
        self._grow: list[str] | None = None
        self._gcell: list[str] | None = None
        self._block: list[str] = []

    def _inside(self, cls: str) -> bool:
        return any(cls in c for _, c in self._stack)

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
            return
        if tag in self._VOID:
            return
        classes = frozenset((dict(attrs).get("class") or "").split())
        if tag in self._BLOCK:
            self._flush()
        if tag == "title":
            self._title = []
        if tag == "li" and self._inside("versions"):
            self._vrow = []
        if tag == "p" and self._vrow is not None:
            self._vcell = []
        if tag == "div" and "category" in classes and self._inside("params"):
            self._category = []
        if tag == "li" and self._inside("params") and self._inside("value"):
            self._grow = []
        if tag == "div" and "valPart" in classes and self._grow is not None:
            self._gcell = []
        self._stack.append((tag, classes))

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip = max(0, self._skip - 1)
            return
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] != tag:
                continue
            _, classes = self._stack[i]
            del self._stack[i:]
            if tag == "title" and self._title is not None:
                self.title, self._title = _clean("".join(self._title)), None
            elif tag == "p" and self._vcell is not None and self._vrow is not None:
                self._vrow.append(_clean("".join(self._vcell)))
                self._vcell = None
            elif tag == "li" and self._vrow is not None and self._vcell is None:
                # A `ul.versions` row holds only <p>/<span>: closing its <li> ends the row.
                self.versions.append(self._vrow)
                self._vrow = None
            if tag == "div" and "category" in classes and self._category is not None:
                self._last_category, self._category = _clean("".join(self._category)), None
            elif tag == "div" and "valPart" in classes and self._gcell is not None:
                if self._grow is not None:
                    self._grow.append(_clean("".join(self._gcell)))
                self._gcell = None
            elif tag == "li" and self._grow is not None and self._gcell is None:
                self.grid.append((self._last_category, self._grow))
                self._grow = None
            break
        if tag in self._BLOCK:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        for buf in (self._title, self._category, self._vcell, self._gcell):
            if buf is not None:
                buf.append(data)
        self._block.append(data)

    def _flush(self) -> None:
        text = _clean("".join(self._block))
        if text:
            self.blocks.append(text)
        self._block = []

    def close(self) -> None:
        super().close()
        self._flush()


def _price_signal(cell: str, excerpt: str, locator: str, price_type_if_amount: str
                  ) -> tuple[ExtractedSignal | None, str | None]:
    """A PRICE signal from one verbatim price statement, or a rejection reason."""
    evidence = _evidence(excerpt, locator)
    if evidence is None:
        return None, f"{locator}: excerpt missing or too long"
    if _CONTACT.fullmatch(cell.strip()):
        return ExtractedSignal("PRICE", "SELECTOR", "HIGH", evidence, price_type="QUOTE_ONLY"), None
    match = _AMOUNT.search(cell)
    if match is None:
        return None, f"{locator}: no price statement in {cell!r}"
    exact = _EXACT_USD.fullmatch(cell.strip()) if not match.group("k") else None
    return ExtractedSignal(
        "PRICE", "SELECTOR" if price_type_if_amount == "PUBLIC" else "PATTERN", "HIGH",
        evidence, price_type=price_type_if_amount,
        # Currency only when stated ("US $"); amount only for an exact US $12,345 value.
        price_currency="USD" if match.group("us") else None,
        price_amount=Decimal(exact.group("num").replace(",", "")) if exact else None,
    ), None


def extract_unitree_product(config: SourceAdapterConfig, body: bytes,
                            url: str | None) -> ProductExtraction:
    """Identity, verbatim specifications and literal price statements. Pure and deterministic."""
    try:
        page_url = normalize_url(url or "")
    except UnsupportedUrl:
        return ProductExtraction("NOTHING_FOUND", notes=("no page URL",))
    path = urlsplit(page_url).path
    if urlsplit(page_url).hostname != config.host or path not in _PRODUCT_PATHS:
        return ProductExtraction("NOTHING_FOUND", notes=("URL is not a reviewed product page",))
    slug = _PRODUCT_PATHS[path]

    page = _Page()
    page.feed(body.decode("utf-8", errors="replace"))
    page.close()

    header = page.versions[0] if page.versions else []
    listed = [row[0] for row in page.versions[1:] if row]
    model_rows = [cells[1:] for _, cells in page.grid if cells and cells[0] == "Model"]
    grid_editions = model_rows[0] if model_rows else []
    if listed and grid_editions and listed != grid_editions:
        return ProductExtraction("AMBIGUOUS", notes=(
            f"edition list {listed} and grid Model row {grid_editions} disagree",))
    editions = listed or grid_editions
    if not editions:
        return ProductExtraction("NOTHING_FOUND", notes=("no edition list on the page",))

    named = [e for e in editions if e.lower() == slug.lower()]
    title_tokens = {t.lower() for t in _TOKENS.split(page.title) if t}
    if not named:
        return ProductExtraction("NOTHING_FOUND", notes=(
            f"no listed edition equals the URL slug {slug!r}: {editions}",))
    if slug.lower() not in title_tokens:
        return ProductExtraction("AMBIGUOUS", notes=(
            f"<title> {page.title!r} does not name {slug!r}",))
    name = named[0]

    claims: list[ExtractedClaim] = []
    rejected: list[str] = []
    seen: dict[str, str] = {}
    conflicted: set[str] = set()

    def claim(key: str, value: str, excerpt: str, locator: str, method: str = "SELECTOR") -> None:
        if key in conflicted:
            return
        if key in seen:
            if seen[key] != value:   # the same key stated twice, differently: keep neither
                conflicted.add(key)
                rejected.append(f"{key}: stated twice with different values")
            return
        evidence = _evidence(excerpt, locator)
        if evidence is None:
            rejected.append(f"{locator}: excerpt missing or too long")
            return
        seen[key] = value
        claims.append(ExtractedClaim(key, value, None, method, "HIGH", evidence))

    claim("unitree.editions", "; ".join(editions), " | ".join(editions),
          "versions/editions" if listed else "params/row[Model]")

    # The price table: the `ul.versions` rows, or the grid's own Price row (G1).
    price_rows: list[tuple[str, str]] = []
    terms = header[1] if len(header) == 2 and _TERMS.fullmatch(header[1]) else None
    if listed:
        if terms is None:
            rejected.append(f"versions/header: unexpected header {header!r}")
        else:
            for row in page.versions[1:]:
                if len(row) == 2:
                    price_rows.append((row[0], row[1]))
                else:
                    rejected.append(f"versions/row: misaligned {row!r}")
    else:
        for _, cells in page.grid:
            if cells and _TERMS.fullmatch(cells[0]):
                if len(cells) == len(editions) + 1:
                    terms = cells[0]
                    price_rows = list(zip(editions, cells[1:], strict=True))
                else:
                    rejected.append(f"params/row[{cells[0]}]: misaligned price row")
                break
    signals: list[ExtractedSignal] = []
    if terms is not None:
        claim("unitree.price_terms", terms, terms, "price-table/header")
        for edition, cell in price_rows:
            excerpt = f"{terms} | {edition} | {cell}"
            locator = f"price-table/row[{edition}]"
            claim(f"unitree.price[{edition}]", cell, excerpt, locator)
            if edition == name:
                signal, why = _price_signal(cell, excerpt, locator, "PUBLIC")
                if signal is not None:
                    signals.append(signal)
                else:
                    rejected.append(why)

    for block in page.blocks:
        match = _FROM.search(block)
        if match and not block.startswith(terms or "\0"):
            statement = block if len(block) <= 200 else match.group(0)
            signal, why = _price_signal(match.group(0), statement, "hero/price-from", "FROM")
            if signal is not None:
                signals.append(signal)
                claim("unitree.price_from", match.group(0), statement, "hero/price-from",
                      method="PATTERN")
            else:
                rejected.append(why)
            break

    for category, cells in page.grid:
        if not cells or cells[0] == "Model" or _TERMS.fullmatch(cells[0]):
            continue
        if len(cells) != len(editions) + 1:
            rejected.append(f"params/{category}/row[{cells[0]}]: {len(cells) - 1} values for "
                            f"{len(editions)} editions (row rejected, never partially attributed)")
            continue
        label = cells[0]
        for edition, value in zip(editions, cells[1:], strict=True):
            if not value:
                continue    # an empty cell states nothing
            claim(f"unitree.spec[{edition}]/{category}/{label}", value,
                  f"{category} | {label} | {edition} | {value}",
                  f"params/{category}/row[{label}]/col[{edition}]")

    return ProductExtraction(
        "EXTRACTED", name=name, name_method="SELECTOR", claims=tuple(claims),
        signals=tuple(signals), rejected=tuple(rejected),
        notes=(f"agreeing locators: ['url_slug', 'edition_list', 'title_token'] -> {name!r}",
               f"editions on the page (not resolved to catalogue robots): {editions}",
               "prices verbatim; currency only when stated; no VAT, region or availability"))


CONFIG = SourceAdapterConfig(
    key="unitree-robotics-official",
    version="0.1.0",
    source_key="unitree-robotics-official",
    source_class="MANUFACTURER",
    host="www.unitree.com",
    # Canonical catalogue manufacturer name, verbatim. No aliases.
    manufacturer="Unitree Robotics",
    allowed_path_prefixes=("/H2", "/R1", "/g1"),
    # Exactly the three reviewed pages; nothing is discovered by following links.
    seed_urls=SEED_URLS,
    product_path_pattern=re.compile(r"/(?:H2|R1|g1)"),
    announcement_path_pattern=None,
    property_map={},
    quote_phrases=(),
    heading_identity=False,
    product_extractor=extract_unitree_product,
    target_cap=1,
    structural_review="2026-10-18 read-only inspection (9 requests); "
    "docs/discovery/UNITREE_STRUCTURAL_REVIEW_2026-10-18.md",
)
