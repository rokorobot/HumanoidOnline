"""NEURA 4NE1 Mini — PROPOSAL-ONLY structured claim extraction (milestone 1).

`propose_neura_mini_claims(body, url)` reads ONE official page (the 4NE1 Mini
reservation page) and returns structured, evidence-bearing *proposals*: what the
page says, where it says it, and which catalogue field a human could map it to.
It is a pure function: bytes in, dataclasses out. It imports no session, ORM
model or database module of its own, performs no I/O and writes nothing. It is
deliberately NOT wired into `neura_robotics.CONFIG` (its `product_extractor`
and `version` are untouched), so scheduled observation behaves exactly as
before and no proposal can reach `candidate_claim` or the catalogue from here.

A proposal is not a claim: there is no VERIFIED value, and every proposal is
`NOT_VERIFIED` and `review_required` until a later, separately governed
claim-review / promotion stage exists.

Identity. There is exactly one robot, "4NE1 Mini". The existing identity-only
extractor must independently name it from the same bytes, otherwise nothing is
proposed. Standard and Pro are the two column headers of the page's feature grid
and are only ever carried as `edition` on a proposal, never as robots.

What is read (nothing else): the three-column feature grid (`feature-grid-cs-3`,
header exactly Feature / Standard / Pro, rows of exactly three cells), its
datasheet link, and three sentences of body text (reservation terms,
availability year, design-refinement caveat). Navigation, footer, marketing
copy, FAQ boilerplate, other-product cards and the checkout buttons are never
read as product data, so changes to them cannot change a proposal.

Fail-safe rules (each is tested): a missing or reordered header, a row whose
cells do not line up, a value that is a known row label, an unknown row label,
a placeholder ("/"), a price or fee that is not exactly `<n> €` / `<n,nnn> €
(excluding taxes and shipping)`, or a sentence that differs from the expected
wording produces NO proposal for that item and a reason in `rejected`. Nothing
is inferred: "/" is not "none", "Not included" is carried verbatim and is not
turned into a boolean, "12 DoF dexterous hands" is not turned into `hand_dof`,
and a manufacturer's *estimated* price is not given a `price_type`.

Representability (against db/schema.sql, no schema change proposed here):
CLEAN, PARTIAL (a home exists but needs a human decision, listed in `gap` and
`review_required`) or UNREPRESENTABLE (no home; kept verbatim for the reviewer).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import Evidence, _evidence
from app.services.discovery.sources.neura_robotics import CONFIG, extract_neura_product
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

EXTRACTOR_KEY = "neura-mini-proposals"
EXTRACTOR_VERSION = "0.1.0"
MINI_URL = "https://neura-robotics.com/product/4ne1-mini-reservation"
ROBOT_NAME = "4NE1 Mini"
EDITIONS = ("Standard", "Pro")
CLAIM_STATUS = "NOT_VERIFIED"  # the existing claim_status vocabulary; never VERIFIED here

CLEAN, PARTIAL, UNREPRESENTABLE = "CLEAN", "PARTIAL", "UNREPRESENTABLE"

# Statuses of a whole result.
PROPOSED, NO_PROPOSALS, AMBIGUOUS, OUT_OF_SCOPE = (
    "PROPOSED", "NO_PROPOSALS", "AMBIGUOUS", "OUT_OF_SCOPE")

#: Page content seen and deliberately not read as product data.
IGNORED_BY_DESIGN = (
    ("site navigation and header menu", "not product data; changes must not affect proposals"),
    ("footer, legal and company address", "not product data"),
    ("marketing tagline and introduction", "descriptive copy; no verifiable field"),
    ("FAQ answers other than the design-refinement caveat",
     "boilerplate; some are placeholder text"),
    ("other-product reservation cards", "other candidates; out of this increment's scope"),
    ("stair-navigation FAQ ('under development')", "a roadmap statement, not a specification"),
)

_FEATURE_GRID = "feature-grid-cs-3"
_HEADER = ("Feature", "Standard", "Pro")
_KNOWN_LABELS = (
    "Use cases", "Manipulation", "Neuraverse integration", "Common interfaces",
    "Additional interfaces", "Estimated price", "Reservation fee",
)
_PRICE = re.compile(r"(?P<n>\d{1,3}(?:,\d{3})*) € \((?P<basis>excluding taxes and shipping)\)")
_FEE = re.compile(r"(?P<n>\d{1,3}(?:,\d{3})*) ?€")
_QUEUE = re.compile(r"A reservation fee secures your place in the delivery queue\.")
_REFUND = re.compile(
    r"This fee is fully refundable and will be applied toward your final purchase price\.")
_AVAIL = re.compile(
    r"Both 4NE1 Mini Standard and 4NE1 Mini Pro are expected to be available in "
    r"(?P<year>20\d\d)\.")
_CAVEAT = re.compile(
    r"4NE1 will retain NEURA.s signature design philosophy and core technical "
    r"specifications\. As we approach a 2026 release, we may introduce refinements to the "
    r"hardware and aesthetics[^.]*\.")


# ------------------------------------------------------------------ result --


@dataclass(frozen=True)
class ObservationRef:
    """Where the bytes came from, supplied by the caller (never read from a database)."""

    fetched_page_id: str | None = None
    crawl_run_id: str | None = None
    retrieved_at: str | None = None
    content_hash: str | None = None

    def as_dict(self) -> dict:
        return {"fetched_page_id": self.fetched_page_id, "crawl_run_id": self.crawl_run_id,
                "retrieved_at": self.retrieved_at, "content_hash": self.content_hash}


@dataclass(frozen=True)
class Proposal:
    kind: str
    edition: str | None          # "Standard" | "Pro" | None (whole product)
    target: str                  # catalogue home, or UNMAPPED / none
    representability: str        # CLEAN | PARTIAL | UNREPRESENTABLE
    value: str                   # verbatim source value, whitespace-collapsed
    structured: tuple[tuple[str, str], ...]   # parsed parts, only what the text states
    evidence: Evidence           # bounded verbatim excerpt + logical locator
    confidence: str              # parser confidence only (HIGH | MEDIUM), never verification
    gap: str | None = None
    review_required: tuple[str, ...] = ()
    source_url: str = MINI_URL
    method: str = "SELECTOR"
    claim_status: str = CLAIM_STATUS
    observation: ObservationRef | None = None

    @property
    def digest(self) -> str:
        """Stable identity of the proposal's content (not of the observation)."""
        payload = json.dumps(
            [EXTRACTOR_KEY, EXTRACTOR_VERSION, self.source_url, self.kind, self.edition,
             self.target, self.value, self.structured], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict:
        return {
            "digest": self.digest, "kind": self.kind, "edition": self.edition,
            "target": self.target, "representability": self.representability,
            "value": self.value, "structured": dict(self.structured),
            "evidence": {"excerpt": self.evidence.excerpt, "locator": self.evidence.locator},
            "source_url": self.source_url, "method": self.method,
            "confidence": self.confidence, "claim_status": self.claim_status,
            "gap": self.gap, "review_required": list(self.review_required),
            "observation": self.observation.as_dict() if self.observation else None,
        }


@dataclass(frozen=True)
class MiniProposalSet:
    status: str
    source_url: str
    robot_name: str | None = None
    editions: tuple[str, ...] = ()
    proposals: tuple[Proposal, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()   # (item, why it produced no proposal)
    ignored: tuple[tuple[str, str], ...] = ()    # (what, why it is not read)
    notes: tuple[str, ...] = ()
    observation: ObservationRef | None = None
    extractor: str = f"{EXTRACTOR_KEY}@{EXTRACTOR_VERSION}"

    #: Structural guarantee, asserted by tests: this result describes no write.
    writes_catalogue = False
    writes_candidate_claims = False

    @property
    def digest(self) -> str:
        payload = json.dumps([self.status, self.robot_name, self.editions,
                              sorted(p.digest for p in self.proposals)])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def of_kind(self, kind: str) -> tuple[Proposal, ...]:
        return tuple(p for p in self.proposals if p.kind == kind)

    def as_dict(self) -> dict:
        return {
            "extractor": self.extractor, "status": self.status, "digest": self.digest,
            "source_url": self.source_url, "robot": self.robot_name,
            "editions": list(self.editions), "observation": (
                self.observation.as_dict() if self.observation else None),
            "writes_catalogue": False, "writes_candidate_claims": False,
            "proposals": [p.as_dict() for p in self.proposals],
            "rejected": [list(r) for r in self.rejected],
            "ignored": [list(i) for i in self.ignored], "notes": list(self.notes),
        }


# -------------------------------------------------------------------- tree --

_VOID = frozenset({"br", "img", "meta", "link", "input", "hr", "source", "wbr", "area", "col"})
_SKIP = frozenset({"script", "style", "noscript", "template"})


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict, parent: _Node | None) -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[_Node | str] = []

    @property
    def classes(self) -> frozenset[str]:
        return frozenset((self.attrs.get("class") or "").split())


class _Tree(HTMLParser):
    """A tolerant element tree. Script/style content is dropped, <br> reads as a space."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {}, None)
        self._cur = self.root
        self._skip: str | None = None

    def handle_starttag(self, tag, attrs):
        if self._skip:
            return
        node = _Node(tag, {k: (v or "") for k, v in attrs}, self._cur)
        self._cur.children.append(node)
        if tag in _SKIP:
            self._skip = tag
        elif tag not in _VOID:
            self._cur = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and tag not in _SKIP:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self._skip:
            if tag == self._skip:
                self._skip = None
            return
        node = self._cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self._cur = node.parent

    def handle_data(self, data):
        if not self._skip:
            self._cur.children.append(data)


def _parse(body: bytes) -> _Node:
    tree = _Tree()
    tree.feed(body.decode("utf-8", errors="replace"))
    tree.close()
    return tree.root


def _walk(node: _Node) -> Iterator[_Node]:
    for child in node.children:
        if isinstance(child, _Node):
            yield child
            yield from _walk(child)


def _text(node: _Node) -> str:
    parts: list[str] = []

    def visit(n: _Node) -> None:
        for child in n.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag == "br":
                parts.append(" ")
            elif child.tag not in _SKIP:
                visit(child)

    visit(node)
    return re.sub(r"\s+", " ", "".join(parts)).strip()  # \s covers non-breaking spaces


def _widget_items(grid: _Node) -> list[tuple[str, str, str | None]]:
    """(kind, text, href) for every text/button widget under the grid, in page order."""
    items: list[tuple[str, str, str | None]] = []

    def visit(n: _Node) -> None:
        for child in n.children:
            if not isinstance(child, _Node):
                continue
            if "elementor-widget-text-editor" in child.classes:
                items.append(("text", _text(child), None))
            elif "elementor-widget-button" in child.classes:
                link = next((x for x in _walk(child) if x.tag == "a"), None)
                items.append(("button", _text(child), link.attrs.get("href") if link else None))
            else:
                visit(child)

    visit(grid)
    return items


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# --------------------------------------------------------------- extraction --


def _amount(digits: str) -> str:
    return f"{Decimal(digits.replace(',', '')):.2f}"


def _proposal(kind, edition, target, rep, value, locator, *, structured=(), gap=None,
              review=(), confidence="HIGH", excerpt=None, obs=None) -> Proposal | None:
    evidence = _evidence(excerpt if excerpt is not None else value, locator)
    if evidence is None:      # no bounded excerpt, no proposal
        return None
    return Proposal(kind=kind, edition=edition, target=target, representability=rep,
                    value=value, structured=tuple(structured), evidence=evidence,
                    confidence=confidence, gap=gap, review_required=tuple(review),
                    observation=obs)


def propose_neura_mini_claims(body: bytes, url: str | None,
                              observation: ObservationRef | None = None) -> MiniProposalSet:
    """Proposals for the official 4NE1 Mini page. Pure and deterministic."""
    try:
        page_url = normalize_url(url or "")
    except UnsupportedUrl:
        return MiniProposalSet(OUT_OF_SCOPE, url or "", notes=("no usable page URL",))
    if page_url != MINI_URL:
        return MiniProposalSet(OUT_OF_SCOPE, page_url, notes=(
            "this increment proposes claims for the 4NE1 Mini reservation page only",))

    identity = extract_neura_product(CONFIG, body, page_url)
    if identity.status != "EXTRACTED" or identity.name != ROBOT_NAME:
        return MiniProposalSet(
            AMBIGUOUS if identity.status == "AMBIGUOUS" else NO_PROPOSALS, page_url,
            notes=(f"identity not confirmed as {ROBOT_NAME!r}: {identity.status} "
                   f"{identity.name!r}", *identity.notes), observation=observation)

    root = _parse(body)
    rejected: list[tuple[str, str]] = []
    ignored = list(IGNORED_BY_DESIGN)
    proposals: list[Proposal] = []
    notes: list[str] = []

    grids = [g for g in _walk(root) if _FEATURE_GRID in g.classes]
    candidates = []
    for grid in grids:
        items = _widget_items(grid)
        if len(items) >= 3 and all(i[0] == "text" for i in items[:3]):
            candidates.append((grid, items))
    if not candidates:
        return MiniProposalSet(NO_PROPOSALS, page_url, robot_name=ROBOT_NAME, notes=(
            "no feature grid found",), ignored=tuple(ignored), observation=observation)
    if len(candidates) > 1:
        return MiniProposalSet(AMBIGUOUS, page_url, robot_name=ROBOT_NAME, notes=(
            f"{len(candidates)} feature grids found; refusing to choose",),
            ignored=tuple(ignored), observation=observation)
    _grid, items = candidates[0]
    header = tuple(i[1] for i in items[:3])
    if header != _HEADER:
        return MiniProposalSet(AMBIGUOUS, page_url, robot_name=ROBOT_NAME, notes=(
            f"feature grid header {header} is not {_HEADER}; column meaning not assumed",),
            ignored=tuple(ignored), observation=observation)

    editions = header[1:]
    # --- one VARIANT per column header; never a robot ---------------------------
    for column, edition in enumerate(editions, start=2):
        p = _proposal(
            "VARIANT", edition, "robot_variant", CLEAN, edition,
            f"feature-grid/header[col={column}]",
            structured=(("slug", _slug(edition)), ("header", edition)),
            review=("robot_variant.name wording and is_developer are not stated; neither is set",),
            obs=observation)
        if p:
            proposals.append(p)

    # --- rows: exactly three cells each; stop at the first row that does not line up
    rows: list[tuple[str, str, str]] = []
    cursor = 3
    while cursor + 2 < len(items) and all(i[0] == "text" for i in items[cursor:cursor + 3]):
        label, standard, pro = (i[1] for i in items[cursor:cursor + 3])
        label_set = set(_KNOWN_LABELS) | set(_HEADER)
        if label not in _KNOWN_LABELS:
            rejected.append((f"row {label!r} and every row after it",
                             "unknown row label: grid alignment is no longer trusted"))
            cursor = len(items)
            break
        if standard in label_set or pro in label_set:
            rejected.append((f"row {label!r} and every row after it",
                             "a value cell equals a row label: cells are misaligned"))
            cursor = len(items)
            break
        rows.append((label, standard, pro))
        cursor += 3
    rest = items[cursor:]

    for label, standard, pro in rows:
        for edition, cell in zip(editions, (standard, pro), strict=True):
            proposals.extend(_row_proposals(label, edition, cell, rejected, observation))

    # --- datasheet link (reference only) and checkout buttons (ignored) ----------
    buttons = [i for i in rest if i[0] == "button"]
    for _kind, text, href in buttons:
        if text == "Datasheet":
            if href and href.startswith("https://"):
                host = urlsplit(href).hostname or ""
                p = _proposal(
                    "DATASHEET_REFERENCE", None,
                    "evidence_source (source_type MANUFACTURER_DOC), reference only", PARTIAL,
                    href, "feature-grid/button[Datasheet]",
                    structured=(("url", href), ("host", host)), excerpt="Datasheet",
                    gap=("the PDF is not fetched or parsed (docs/16 §20), and its host is not "
                         "the approved NEURA host: any retrieval needs its own source "
                         "eligibility review"),
                    review=("the grid places the link in the Pro column's cell; the page does "
                            "not say which edition(s) the datasheet covers",),
                    obs=observation)
                if p:
                    proposals.append(p)
            else:
                rejected.append(("datasheet link", "href is missing or not an https URL"))
        elif text == "Reserve":
            if not any(item.startswith("reservation checkout") for item, _ in ignored):
                ignored.append(("reservation checkout buttons", "a transaction surface; "
                                "their cart links are never read"))
        else:
            rejected.append((f"button {text!r}", "unrecognized button"))
    if rest and not (rest[0][0] == "text" and rest[0][1] == "Reservation"):
        rejected.append(("trailing grid content", "unexpected structure after the last row"))

    # --- three sentences of body text -------------------------------------------
    blocks = [_text(n) for n in _walk(root)
              if n.classes & {"elementor-widget-text-editor", "elementor-tab-content"}]
    proposals.extend(_text_proposals(blocks, editions, rejected, observation))

    proposals.sort(key=_order)
    status = PROPOSED if proposals else NO_PROPOSALS
    return MiniProposalSet(
        status, page_url, robot_name=ROBOT_NAME, editions=editions, proposals=tuple(proposals),
        rejected=tuple(rejected), ignored=tuple(ignored), notes=tuple(notes),
        observation=observation)


_KIND_ORDER = ("VARIANT", "SPECIFICATION", "PRICE_ESTIMATE", "RESERVATION_FEE",
               "AVAILABILITY", "RESERVATION_TERMS", "DESIGN_CAVEAT", "DATASHEET_REFERENCE",
               "USE_CASES", "INTERFACES", "INTEGRATION")


def _order(p: Proposal) -> tuple:
    edition = EDITIONS.index(p.edition) if p.edition in EDITIONS else -1
    return (_KIND_ORDER.index(p.kind), edition)   # stable sort: page order within a group


def _row_proposals(label: str, edition: str, cell: str, rejected: list,
                   obs: ObservationRef | None) -> list[Proposal]:
    where = f"feature-grid/row[{label}]/col[{edition}]"
    made: list[Proposal | None] = []
    if cell in ("/", "-", "–", ""):
        rejected.append((f"{label} / {edition}", f"placeholder {cell!r} is not a value; it is "
                         "not read as 'none' or 'not applicable'"))
        return []
    if label == "Use cases":
        made.append(_proposal(
            "USE_CASES", edition, "use_case_fit (relational, controlled vocabulary)",
            UNREPRESENTABLE, cell, where,
            gap="use_case_fit links to the use_case table; free text cannot be mapped to it "
                "without inference", obs=obs))
    elif label == "Manipulation":
        review = ["confirm specification[dexterous_hand_option] is the home for this row"]
        if re.search(r"\bDoF\b", cell):
            review.append("'DoF' is stated without per hand or in total: hand_dof is not set")
        made.append(_proposal(
            "SPECIFICATION", edition, "specification[dexterous_hand_option]", PARTIAL, cell,
            where, structured=(("edition_scope", "THIS_EDITION"),),
            gap="verbatim text only: no boolean has_manipulation or numeric hand_dof is "
                "inferred from it", review=review, obs=obs))
    elif label == "Neuraverse integration":
        made.append(_proposal(
            "INTEGRATION", edition, "none", UNREPRESENTABLE, cell, where,
            gap="no spec_definition or robot column exists for this", obs=obs))
    elif label in ("Common interfaces", "Additional interfaces"):
        made.append(_proposal(
            "INTERFACES", edition, "UNMAPPED (nearest: specification[connectivity] or "
            "specification[sdk_software])", PARTIAL, cell, where,
            structured=(("row", label), ("edition_scope", "THIS_EDITION")),
            gap="the cell mixes connectivity and software items; splitting it would be "
                "inference, so no single key is chosen",
            review=("a human chooses the key(s) or a split rule",), obs=obs))
    elif label == "Estimated price":
        m = _PRICE.fullmatch(cell)
        if not m:
            rejected.append((f"{label} / {edition}", f"{cell!r} is not '<n,nnn> € "
                             "(excluding taxes and shipping)'"))
            return []
        made.append(_proposal(
            "PRICE_ESTIMATE", edition, "pricing_offer[variant]", PARTIAL, cell, where,
            structured=(("amount", _amount(m.group("n"))), ("currency", "EUR"),
                        ("basis", m.group("basis")), ("stated_as", "estimated price")),
            gap="the manufacturer states an ESTIMATED price. price_type ESTIMATED means a "
                "HumanoidOnline estimate; PUBLIC or FROM would overstate it: no price_type "
                "is assigned",
            review=("price_type decision", "transaction_type is not stated on this row",
                    "region is not stated"), obs=obs))
    elif label == "Reservation fee":
        m = _FEE.fullmatch(cell)
        if not m:
            rejected.append((f"{label} / {edition}", f"{cell!r} is not '<n> €'"))
            return []
        made.append(_proposal(
            "RESERVATION_FEE", edition, "none (no deposit field; pricing_offer.note at most)",
            UNREPRESENTABLE, cell, where,
            structured=(("amount", _amount(m.group("n"))), ("currency", "EUR")),
            gap="a refundable reservation deposit is not a price and has no catalogue field",
            obs=obs))
    return [p for p in made if p]


def _text_proposals(blocks: list[str], editions: tuple[str, ...], rejected: list,
                    obs: ObservationRef | None) -> list[Proposal]:
    out: list[Proposal | None] = []
    joined = " ".join(blocks)

    queue, refund = _QUEUE.search(joined), _REFUND.search(joined)
    if queue and refund:
        out.append(_proposal(
            "RESERVATION_TERMS", None, "none (no deposit terms field)", UNREPRESENTABLE,
            f"{queue.group(0)} {refund.group(0)}", "text-block[reservation-terms]",
            gap="deposit terms have no catalogue field; kept verbatim for the reviewer",
            obs=obs))
    else:
        rejected.append(("reservation terms", "expected sentences not found verbatim"))

    avail = _AVAIL.search(joined)
    if avail:
        for edition in editions:
            out.append(_proposal(
                "AVAILABILITY", edition, "availability_offer.available_from (year only)",
                PARTIAL, avail.group(0), "text-block[availability-year]",
                structured=(("expected_year", avail.group("year")),),
                gap="availability_status (WAITLIST vs PREORDER) is not stated and is not "
                    "assigned; the date is year-level only",
                review=("availability_status decision", "transaction_type is not stated"),
                obs=obs))
    else:
        rejected.append(("availability year", "expected sentence not found verbatim"))

    caveat = _CAVEAT.search(joined)
    if caveat:
        out.append(_proposal(
            "DESIGN_CAVEAT", None, "none (provenance note for the reviewer)", UNREPRESENTABLE,
            caveat.group(0), "text-block[design-refinement]",
            gap="not a claim: the manufacturer says hardware may be refined before release",
            obs=obs))
    return [p for p in out if p]


# ------------------------------------------------------------------- report --


def render(result: MiniProposalSet) -> str:
    """A deterministic plain-text report for a human reviewer."""
    lines = [
        f"{result.extractor}  status={result.status}  robot={result.robot_name}  "
        f"editions={list(result.editions)}",
        f"source {result.source_url}",
        "PROPOSALS ONLY: nothing here is verified or written to the catalogue.",
    ]
    for p in result.proposals:
        scope = p.edition or "product"
        lines.append(f"[{p.representability}] {p.kind} / {scope}: {p.value!r}")
        lines.append(f"    -> {p.target}")
        if p.structured:
            lines.append(f"    parsed {dict(p.structured)}")
        lines.append(f"    evidence {p.evidence.locator}: {p.evidence.excerpt!r}")
        if p.gap:
            lines.append(f"    gap: {p.gap}")
        for question in p.review_required:
            lines.append(f"    review: {question}")
    lines += [f"REJECTED {item}: {why}" for item, why in result.rejected]
    lines += [f"IGNORED {item}: {why}" for item, why in result.ignored]
    lines += [f"NOTE {note}" for note in result.notes]
    return "\n".join(lines)


__all__ = ["EXTRACTOR_KEY", "EXTRACTOR_VERSION", "MINI_URL", "MiniProposalSet", "ObservationRef",
           "Proposal", "propose_neura_mini_claims", "render"]
