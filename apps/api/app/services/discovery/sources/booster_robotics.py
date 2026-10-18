"""Booster Robotics — official www.booster.tech product pages for the T2 and K1 humanoids.

Access basis (docs/28, A4): owner instruction 2026-10-18, OWNER_AUTHORIZED. That is an internal
business decision, NOT publisher consent: `tos_status` stays UNKNOWN, and the decision is recorded
in the database, never here. robots.txt (`User-agent: *` / `Allow: /`) is re-read on every run.

Structural review: docs/discovery/BOOSTER_STRUCTURAL_REVIEW_2026-10-18.md (9 requests), plus two
probes on 2026-10-18 for this adapter: the slash-less seed form `/booster-t2?target=en` answers 200
with the same bytes as `/booster-t2/?target=en`, and `/booster-k1/?target=en` answers 200.

Scope: a FIXED set of two English product pages (`?target=en` is the site's own language
switch and is part of the reviewed URL). Nothing is discovered by following links. `/store`,
the `/cn/` copies and `agentstore.`, `docs.`, `studio.` and `support.` are out of scope. The
site has no T1 page.

Identity is the GENERIC rule: each page carries a schema.org `Product` (`Booster T2`,
`Booster K1`, brand `Booster Robotics`) that agrees with `canonical` and the `<h1>`. There is no
`offers` block, so no price or availability is stated, and none is inferred. v0.2.0 also records
the `#specifications` section: a reviewed edition label (`EDITIONS`) heads `h4` categories of
"Label: Value" lines, kept verbatim as `booster.spec[<model> <edition>]/<category>/<label>`. The
block repeats for responsive layouts: identical repeats collapse, and differing values are
dropped. "Buy now" links and the homepage's funding-round "$" amounts are never read.
"""
from __future__ import annotations

import dataclasses
import re
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import (
    ProductExtraction,
    SourceAdapterConfig,
    extract_product,
)
from app.services.discovery.sources import xpeng_iron_proposals as html
from app.services.discovery.sources.spec_claims import SpecClaims, children, find, text
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

STRUCTURAL_FINDINGS = {
    "inspected_at": "2026-10-18",
    "robots_status": "ALLOWED",
    "identity": "JSON-LD Product name + canonical + <h1> agree on both pages",
    "commercial_language": "'Buy now' -> /store (not reviewed); no offers in JSON-LD; no price",
    "absent": "no T1 page on www.booster.tech",
}

#: The edition labels each reviewed page's "Specifications" section uses, as reviewed
#: (2026-10-18), each an <h3>. An unknown <h3> label is not guessed: the lines under it are
#: attributed to no edition at all.
EDITIONS = {"/booster-t2": ("Education", "Professional"),
            "/booster-k1": ("Geek Edition", "Education", "Professional")}
_LINE = re.compile(r"(?P<label>[^:\uff1a]{1,80})[:\uff1a]\s*(?P<value>.+)")


def extract_booster_product(config: SourceAdapterConfig, body: bytes,
                            url: str | None) -> ProductExtraction:
    """Identity by the GENERIC JSON-LD rule, plus the page's per-edition specification lines."""
    base = extract_product(dataclasses.replace(config, product_extractor=None), body, url)
    if base.status != "EXTRACTED":
        return base
    try:
        path = urlsplit(normalize_url(url or "")).path
    except UnsupportedUrl:
        return base
    editions, model = EDITIONS.get(path, ()), (base.name or "").removeprefix("Booster ").strip()
    tree = html._Tree()
    tree.feed(body.decode("utf-8", errors="replace"))
    tree.close()
    sections = [n for n in find(tree.root, "section") if n.attrs.get("id") == "specifications"]
    specs = SpecClaims("booster")
    edition = category = None
    for node in (html._walk(sections[0]) if len(sections) == 1 and editions else ()):
        if children(node):
            continue                # only leaf elements carry a label, heading or line
        line = text(node)
        if node.tag == "h3":        # an edition label: only a reviewed one is attributed
            edition, category = (line if line in editions else None), None
        elif node.tag == "h4":
            category = line
        elif node.tag == "p" and edition and category and (m := _LINE.fullmatch(line)):
            specs.add(f"{model} {edition}", f"{category}/{m['label']}", m["value"],
                      f"specifications/{edition}/{category}/{m['label']}")
    if not sections:
        specs.rejected.append("no #specifications section")
    return dataclasses.replace(base, claims=base.claims + specs.claims,
                               rejected=base.rejected + tuple(specs.rejected),
                               notes=base.notes + (
                                   "specifications: '#specifications' lines per reviewed edition, "
                                   "verbatim; editions are not resolved to catalogue robots",))


CONFIG = SourceAdapterConfig(
    key="booster-robotics-official",
    version="0.2.0",
    source_key="booster-robotics-official",
    source_class="MANUFACTURER",
    host="www.booster.tech",
    manufacturer="Booster Robotics",
    allowed_path_prefixes=("/booster-t2", "/booster-k1"),
    seed_urls=("https://www.booster.tech/booster-t2?target=en",
               "https://www.booster.tech/booster-k1?target=en"),
    product_path_pattern=re.compile(r"/booster-(?:t2|k1)"),
    announcement_path_pattern=None,
    product_extractor=extract_booster_product,
    target_cap=1,
    structural_review="2026-10-18 read-only inspection (9 + 2 requests); "
    "docs/discovery/BOOSTER_STRUCTURAL_REVIEW_2026-10-18.md",
)
