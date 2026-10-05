"""Alza.cz reference-offer proposals — manual / evidence-backed, NEVER automated.

Owner decision (2026-10-05): Alza.cz is an approved Czech commercial provider and a *reference*
source for evidence-backed offers. It is NOT approved for automated monitoring, scheduled
fetching, recurring discovery, polling, or automated stock/price checking. So this module:

- is a pure function over bytes an operator ALREADY retained
  (`manual_capture.record_manual_capture`); it does no I/O, holds no HTTP client and is
  registered with NO scheduler, adapter table or observation cycle (asserted by tests);
- reads one category-listing page and proposes only for the explicitly reviewed items in
  `REFERENCE_ITEMS`. Anything else (accessories, quadrupeds, other brands, unreviewed SKUs) is
  reported as rejected, never proposed;
- proposes two things per item, each its own claim: `RETAIL_PRICE` and `RETAIL_AVAILABILITY`.
  It records what the page SAYS (price token, availability wording, displayed quantity, the
  new/used marker); the reviewer alone chooses the mapping into the catalogue vocabulary;
- keeps NEW and USED apart: the condition is read from two independent markers on the listing
  (the item's `data-almostnew` flag and its "Použité" availability wording). If they disagree,
  or the wording is not one of the recognised forms, nothing is proposed for the item;
- never reads a price as MSRP, a manufacturer price or an EU price, never converts currency and
  never infers VAT: `vat_stated` is always false because a category listing does not state it.

Identity is part of the reviewed configuration, not of the page: `REFERENCE_ITEMS` maps an Alza
product id to a catalogue robot with a stated confidence and basis. Items whose canonical robot
does not exist (or is genuinely uncertain) are listed in `UNRESOLVED_ITEMS` with the reason and
produce no proposal.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from html.parser import HTMLParser

from app.services.discovery.field_policy import RETAIL_ALLOWED_STATUS
from app.services.discovery.live_adapter import Evidence, _evidence

EXTRACTOR_KEY = "alza-cz-reference"
EXTRACTOR_VERSION = "0.1.0"
SOURCE_KEY = "alza-cz"
PROVIDER_SLUG = "alza-cz"
MARKET = "CZ"
CURRENCY = "CZK"
HOST = "www.alza.cz"

#: The only pages this extractor reads (normalized form): the two category listings.
UNITREE_LISTING_URL = "https://www.alza.cz/unitree/v49936.htm?evt=re&exps=humanoidni+robot"
UBTECH_LISTING_URL = "https://www.alza.cz/ubtech/v6390.htm"
PAGE_URLS = (UNITREE_LISTING_URL, UBTECH_LISTING_URL)

PRICE_KIND, AVAILABILITY_KIND = "RETAIL_PRICE", "RETAIL_AVAILABILITY"
PRICE_TARGET, AVAILABILITY_TARGET = "pricing_offer[retail]", "availability_offer[retail]"
LOCATOR_ROOT = "listing/item["
PROPOSED, NO_PROPOSALS = "PROPOSED", "NO_PROPOSALS"
CLAIM_STATUS = "NOT_VERIFIED"

#: What the page's availability wording is, as an OBSERVATION. The reviewer maps it to the
#: HumanoidOnline availability vocabulary; `ALLOWED_STATUS` is the only mapping the registry
#: accepts.
IN_STOCK, UNAVAILABLE, PREORDER = "IN_STOCK", "UNAVAILABLE", "PREORDER"
ALLOWED_STATUS = RETAIL_ALLOWED_STATUS
CONDITIONS = ("NEW", "USED")


@dataclass(frozen=True)
class ReferenceItem:
    """One reviewed Alza product -> one catalogue robot (reviewed configuration)."""

    product_id: str
    robot_slug: str
    robot_name: str
    expected_condition: str
    identity_confidence: str          # HIGH | MEDIUM
    identity_basis: str


def _item(pid, slug, name, cond, conf, basis) -> tuple[str, ReferenceItem]:
    return pid, ReferenceItem(pid, slug, name, cond, conf, basis)


#: Reviewed 2026-10-05 against the retained listing captures and the current catalogue. The
#: robot name is the catalogue's `robot.name` (the ingest identity gate checks it).
REFERENCE_ITEMS: dict[str, ReferenceItem] = dict([
    _item("13408319", "unitree-r1-edu-u2", "R1 EDU U2", "NEW", "HIGH",
          "Alza U2: 26 DoF, 100 TOPS, no active fingers = catalogue R1 EDU U2 (Smart, no hands)"),
    _item("13408321", "unitree-r1-edu-u4", "R1 EDU U4", "NEW", "HIGH",
          "Alza U4: 2x Dex3-1 with tactile sensors = catalogue R1 EDU U4"),
    _item("13408322", "unitree-r1-edu-u5", "R1 EDU U5", "NEW", "HIGH",
          "Alza U5: 2x BrainCo Revo 2 Basic = catalogue R1 EDU U5"),
    _item("13408323", "unitree-r1-edu-u6", "R1 EDU U6", "NEW", "HIGH",
          "Alza U6: 2x BrainCo Revo 2 Touch = catalogue R1 EDU U6"),
    _item("13150281", "unitree-g1-edu-plus-u2", "G1 EDU Plus (U2)", "NEW", "MEDIUM",
          "Alza 'G1 EDU U2' states 29 joint motors + Jetson Orin; catalogue 'G1 EDU Plus (U2)' is "
          "29 DoF + Orin NX. The name differs ('Plus'): reviewer must confirm"),
    _item("13215767", "unitree-h2", "H2", "NEW", "MEDIUM",
          "Alza 'H2 Basic' (31 DoF) vs the catalogue's base edition 'H2'; the 'Basic' wording is "
          "Alza's: reviewer must confirm"),
    _item("13215768", "unitree-h2-edu", "H2 EDU", "NEW", "HIGH",
          "Alza 'H2 EDU' = catalogue H2 EDU"),
    _item("13233810", "ubtech-walker-tienkung-embodied-intelligence",
          "Walker Tienkung · Embodied Intelligence", "NEW", "MEDIUM",
          "Alza 'Ubtech Walker Tienkung (embodied intelligence)'; the canonical entity rests on "
          "official UBTECH evidence, reviewer confirms the match"),
    _item("13509114", "ubtech-walker-tienkung-embodied-intelligence",
          "Walker Tienkung · Embodied Intelligence", "USED", "MEDIUM",
          "Same product as the NEW listing, Alza bazaar/used unit; reviewer confirms the match"),
])

#: Seen on the reviewed captures but deliberately NOT proposed, with the reason.
UNRESOLVED_ITEMS: dict[str, str] = {
    "13150282": "G1 EDU U4 (43 DoF, Dex3-1): no canonical robot in the catalogue yet",
    "13079624": "G1 EDU U5 (43 DoF, Inspire RH56DFQ): no canonical robot in the catalogue yet",
    "13150284": "G1 EDU U6 (41 DoF, Inspire RH56E2): no canonical robot in the catalogue yet",
    "13501544": "H2 EDU U2 (BrainCo Revo 2 hands bundle): no canonical robot; may be an H2 EDU "
                "configuration, owner decision",
    "13408317": "R1 Basic (24 DoF, no head): the catalogue 'R1' is a 26-joint mid tier; not the "
                "same configuration without owner review",
}

# ---------------------------------------------------------------- listing parse --

_PRICE = re.compile(r"^(\d{1,3}(?:[  ]\d{3})*),-$")
_STOCK = re.compile(r"^Skladem(?: (?:> )?(\d+) ks)?$")
_USED_STOCK = re.compile(r"^Použité - skladem (\d+) ks$")
_UNAVAILABLE = "Momentálně nedostupné"
_PREORDER = re.compile(r"^Předobjednávka")
_ANCHOR = "Hlídat dostupnost nebo cenu"


@dataclass(frozen=True)
class ListingItem:
    product_id: str
    code: str
    href: str
    name: str
    price: str | None            # the item's own price token, verbatim ("917 990,-")
    new_reference_price: str | None   # "Nový 2 491 790,-" on a used item: reference only
    availability_wording: str | None
    signal: str | None
    stock_quantity: str | None   # "5" or ">5" exactly as displayed
    condition: str | None
    order_code: str | None
    excerpt: str
    problems: tuple[str, ...]


class _Items(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict] = []
        self._cur: dict | None = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "div" and "browsingitem" in (a.get("class") or "").split():
            self._cur = {"id": a.get("data-id"), "code": a.get("data-code"),
                         "almostnew": a.get("data-almostnew"), "href": None, "tokens": []}
            self.items.append(self._cur)
        if (self._cur is not None and tag == "a" and a.get("href") and not self._cur["href"]
                and re.search(r"-d\d+\.htm$", a["href"])):
            self._cur["href"] = a["href"]

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._cur is not None and not self._skip and data.strip():
            self._cur["tokens"].append(re.sub(r"\s+", " ", data.replace(" ", " ")).strip())


def _price_text(token: str) -> str | None:
    match = _PRICE.match(token.replace(" ", " "))
    return match.group(0) if match else None


def _signal(token: str) -> tuple[str, str | None, str | None] | None:
    """(signal, quantity, condition-from-wording) for a recognised availability token."""
    m = _USED_STOCK.match(token)
    if m:
        return IN_STOCK, m.group(1), "USED"
    m = _STOCK.match(token)
    if m:
        qty = m.group(1)
        if qty and "> " in token:
            qty = ">" + qty
        return IN_STOCK, qty, "NEW"
    if token == _UNAVAILABLE:
        return UNAVAILABLE, None, None
    if _PREORDER.match(token):
        return PREORDER, None, None
    return None


def parse_listing(body: bytes) -> list[ListingItem]:
    """Every product box on a category listing, as observations. Fail closed per item."""
    parser = _Items()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    out: list[ListingItem] = []
    for raw in parser.items:
        tokens: list[str] = raw["tokens"]
        problems: list[str] = []
        name = None
        start = 0
        if _ANCHOR in tokens:
            k = tokens.index(_ANCHOR)
            if k + 1 < len(tokens):
                name, start = tokens[k + 1], k + 2
        if not name:
            problems.append("no product name found")
        avail_idx = next((i for i in range(start, len(tokens)) if _signal(tokens[i])), None)
        signal = wording = qty = word_condition = None
        if avail_idx is None:
            problems.append("no recognised availability wording")
        else:
            wording = tokens[avail_idx]
            signal, qty, word_condition = _signal(wording)
        end = avail_idx if avail_idx is not None else len(tokens)
        price = None
        new_ref = None
        for tok in tokens[start:end]:
            if tok.startswith("Nový ") and _price_text(tok[5:]):
                new_ref = _price_text(tok[5:])
                continue
            if "měsíčně" in tok or tok.startswith("Od ") or "%" in tok:
                continue
            candidate = _price_text(tok)
            if candidate and price is None:
                price = candidate
        if price is None:
            problems.append("no price token")
        marker = {"true": "USED", "false": "NEW"}.get(raw["almostnew"] or "")
        condition = None
        if marker is None:
            problems.append("condition markers missing")
        elif word_condition is not None and marker != word_condition:
            problems.append(f"condition markers disagree (flag {marker}, wording "
                            f"{word_condition})")
        elif marker == "USED" and word_condition != "USED" and new_ref is None:
            problems.append("used flag without a second marker (no 'Použité' wording, no "
                            "new-unit reference price)")
        else:
            # An unavailable / preorder item has no condition wording: the item's own flag
            # decides NEW. A USED flag always needs a second, independent marker.
            condition = marker
        order_code = None
        if "Objednací kód:" in tokens:
            j = tokens.index("Objednací kód:")
            order_code = tokens[j + 1] if j + 1 < len(tokens) else None
        excerpt = " | ".join(t for t in (name, price, wording,
                                         f"Objednací kód: {order_code}" if order_code else None)
                             if t)
        out.append(ListingItem(
            product_id=raw["id"] or "", code=raw["code"] or "", href=raw["href"] or "",
            name=name or "", price=price, new_reference_price=new_ref,
            availability_wording=wording, signal=signal, stock_quantity=qty,
            condition=condition, order_code=order_code, excerpt=excerpt,
            problems=tuple(problems)))
    return out


# --------------------------------------------------------------------- proposals --


@dataclass(frozen=True)
class Proposal:
    kind: str
    edition: str | None
    target: str
    representability: str
    value: str
    structured: tuple[tuple[str, object], ...]
    evidence: Evidence
    confidence: str
    gap: str | None
    review_required: tuple[str, ...]
    source_url: str
    robot_name: str = ""
    method: str = "SELECTOR"
    claim_status: str = CLAIM_STATUS

    @property
    def digest(self) -> str:
        payload = json.dumps(
            [EXTRACTOR_KEY, EXTRACTOR_VERSION, self.source_url, self.robot_name, self.kind,
             self.edition, self.target, self.value, self.structured],
            ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AlzaProposalSet:
    status: str
    source_url: str
    proposals: tuple[Proposal, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()

    #: Structural guarantee, asserted by tests: no write, no status, no fetch.
    writes_catalogue = False
    fetches = False


def price_amount(token: str) -> str:
    """'917 990,-' -> '917990' (a plain decimal string; never converted or rounded)."""
    digits = re.sub(r"[^\d]", "", token)
    return str(Decimal(digits))


def _review(item: ReferenceItem, what: str) -> tuple[str, ...]:
    return (
        f"Is this listing exactly the catalogue robot '{item.robot_name}'? Identity confidence "
        f"{item.identity_confidence}: {item.identity_basis}.",
        f"This {what} was read from an Alza category listing, not the product page, and is an "
        "evidence snapshot (not a live value). Is it acceptable as a reference offer?",
    )


def propose_alza_reference_claims(body: bytes, url: str, *, robot_slug: str) -> AlzaProposalSet:
    """Retail price + availability proposals for the reviewed items that map to `robot_slug`."""
    if not robot_slug.strip():
        raise ValueError("a robot slug is required: listings are attached to one robot only")
    proposals: list[Proposal] = []
    rejected: list[tuple[str, str]] = []
    notes: list[str] = []
    for li in parse_listing(body):
        label = f"{li.product_id} {li.name}".strip()
        ref = REFERENCE_ITEMS.get(li.product_id)
        if ref is None:
            why = UNRESOLVED_ITEMS.get(li.product_id)
            rejected.append((label, f"IDENTITY_UNRESOLVED: {why}" if why else
                             "OUT_OF_SCOPE: not on the reviewed reference list (accessory, "
                             "non-humanoid or unreviewed product)"))
            continue
        if ref.robot_slug != robot_slug:
            continue
        if li.problems:
            rejected.append((label, "FAIL_CLOSED: " + "; ".join(li.problems)))
            continue
        if li.condition != ref.expected_condition:
            rejected.append((label, f"FAIL_CLOSED: listing condition {li.condition} differs from "
                                    f"the reviewed {ref.expected_condition}"))
            continue
        product_url = f"https://{HOST}{li.href}"
        common = {
            "provider": PROVIDER_SLUG, "market": MARKET, "currency": CURRENCY,
            "condition": li.condition, "product_id": li.product_id,
            "order_code": li.order_code, "product_name": li.name, "product_url": product_url,
            "page_kind": "category-listing", "vat_stated": False,
            "identity_confidence": ref.identity_confidence,
            "identity_basis": ref.identity_basis,
            "capture_class": "AGENT_ASSISTED_RESEARCH",
        }
        price_struct = {**common, "amount": price_amount(li.price),
                        "price_token": li.price}
        if li.condition == "USED" and li.new_reference_price:
            # The listing shows the NEW price next to a used one; kept as reference text only.
            price_struct["new_unit_price_shown"] = li.new_reference_price
        avail_struct = {**common, "availability_signal": li.signal,
                        "availability_wording": li.availability_wording,
                        "stock_quantity": li.stock_quantity}
        for kind, target, suffix, value, struct, what in (
                (PRICE_KIND, PRICE_TARGET, "price", li.price, price_struct, "price"),
                (AVAILABILITY_KIND, AVAILABILITY_TARGET, "availability",
                 li.availability_wording, avail_struct, "availability")):
            locator = f"{LOCATOR_ROOT}{li.product_id}]/{suffix}"
            evidence = _evidence(li.excerpt, locator)
            if evidence is None:
                rejected.append((label, "FAIL_CLOSED: evidence excerpt empty or too long"))
                continue
            proposals.append(Proposal(
                kind=kind, edition=None, target=target, representability="CLEAN", value=value,
                structured=tuple(sorted(struct.items())), evidence=evidence,
                confidence="MEDIUM", gap=None, review_required=_review(ref, what),
                source_url=url, robot_name=ref.robot_name))
    if not proposals:
        return AlzaProposalSet(NO_PROPOSALS, url, rejected=tuple(rejected),
                               notes=tuple(notes))
    return AlzaProposalSet(PROPOSED, url, tuple(proposals), tuple(rejected), tuple(notes))
