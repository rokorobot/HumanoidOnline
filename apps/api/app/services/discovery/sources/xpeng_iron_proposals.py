"""XPENG IRON — PROPOSAL-ONLY structured claim extraction.

`propose_xpeng_iron_claims(body, url)` reads ONE of four officially approved xpeng.com
pages about the XPENG humanoid robot IRON and returns evidence-bearing *proposals*: what the
page says, where it says it, and which catalogue home (if any) a human could map it to. It is a
pure function (bytes in, dataclasses out): no I/O, no session, no model import, no database.

A proposal is not a claim: every one is `NOT_VERIFIED` and review-required until the separately
governed review / claim / materialization chain (DR-A5) accepts it. Nothing here writes the
catalogue, and nothing is inferred.

The four pages are four DIFFERENT TIMES in IRON's history and are deliberately kept apart. A
proposal records which page said it (`source_url`, `structured.source_page`, the locator), never
"IRON's" value as a timeless fact:

    news-2024-11-06   original ("first-generation") IRON unveiling
    news-2025-11-05   Next-Gen IRON unveiling (also an Australian regional copy of the release)
    news-2026-09-08   production-line announcement (the current configuration)
    product-page      the undated product page, which names the "Next-Gen" configuration

Values that differ between pages (82 / 76 body DoF; 22 / 21 DoF per hand; 3000 / 2,250 TOPS)
are independent statements about differing configurations or times. They are never averaged,
ranked, merged or called errors, and nothing flattens a per-hand figure into a total.

Fail-safe rules (each tested): a page whose date line, canonical URL or expected statements
differ produces NO proposal for that item and a reason in `rejected`; a sentence must match its
exact reviewed pattern; a year-level plan stays year-level ("2027", "the end of this year"); no
boolean or number is derived from marketing wording.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.services.discovery.live_adapter import Evidence, _evidence
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

EXTRACTOR_KEY = "xpeng-iron-proposals"
EXTRACTOR_VERSION = "0.1.0"
ROBOT_NAME = "IRON"
CLAIM_STATUS = "NOT_VERIFIED"

CLEAN, PARTIAL, UNREPRESENTABLE = "CLEAN", "PARTIAL", "UNREPRESENTABLE"
PROPOSED, NO_PROPOSALS, AMBIGUOUS, OUT_OF_SCOPE = (
    "PROPOSED", "NO_PROPOSALS", "AMBIGUOUS", "OUT_OF_SCOPE")

# The four reviewed pages: normalized URL -> (page key, the date line the page must show).
PAGES: dict[str, tuple[str, str | None]] = {
    "https://www.xpeng.com/technology/ai_robot_iron": ("product-page", None),
    "https://www.xpeng.com/news/01a080371029a057bc8e8a02a2c6012b": ("news-2026-09-08",
                                                                    "2026-09-08"),
    "https://www.xpeng.com/au/news/019e71be4f9e9dd703de8a0282290455": ("news-2025-11-05",
                                                                       "2025-11-05"),
    "https://www.xpeng.com/news/019301d2135392fa562d8a0282200016": ("news-2024-11-06",
                                                                    "2024-11-06"),
}
PRODUCT_PAGE_URL = "https://www.xpeng.com/technology/ai_robot_iron"
PAGE_URLS = tuple(PAGES)

#: Page content seen and deliberately not read as IRON data.
IGNORED_BY_DESIGN = (
    ("site navigation, model lists and footer", "not product data"),
    ("XPENG cars, Robotaxi, flying cars, VLA 2.0 and the Turing chip as a car product",
     "other products; out of this scope"),
    ("investor, funding and valuation statements", "corporate, not product facts"),
    ("the Kunpeng electric system and other 2024 AI Day products", "other products"),
)


# ------------------------------------------------------------------ result --


@dataclass(frozen=True)
class Proposal:
    kind: str
    target: str                  # catalogue home hint, or UNMAPPED / none
    representability: str        # CLEAN | PARTIAL | UNREPRESENTABLE
    value: str                   # verbatim source wording (sentence or label)
    structured: tuple[tuple[str, str], ...]
    evidence: Evidence           # bounded verbatim excerpt + logical locator
    source_url: str
    edition: str | None = None   # IRON has no sold editions; chronology lives in `structured`
    confidence: str = "HIGH"     # parser confidence only, never verification
    gap: str | None = None
    review_required: tuple[str, ...] = ()
    method: str = "SELECTOR"
    claim_status: str = CLAIM_STATUS

    @property
    def digest(self) -> str:
        """Stable identity of the proposal's content (not of the observation)."""
        payload = json.dumps(
            [EXTRACTOR_KEY, EXTRACTOR_VERSION, self.source_url, self.kind, self.edition,
             self.target, self.value, self.structured], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProposalSet:
    status: str
    source_url: str
    robot_name: str | None = None
    proposals: tuple[Proposal, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()
    ignored: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()
    extractor: str = f"{EXTRACTOR_KEY}@{EXTRACTOR_VERSION}"

    writes_catalogue = False
    writes_candidate_claims = False

    def of_kind(self, kind: str) -> tuple[Proposal, ...]:
        return tuple(p for p in self.proposals if p.kind == kind)


# -------------------------------------------------------------------- tree --

_VOID = frozenset({"br", "img", "meta", "link", "input", "hr", "source", "wbr", "area", "col"})
_SKIP = frozenset({"script", "style", "noscript", "template", "svg", "video"})


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict, parent: _Node | None) -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[_Node | str] = []


class _Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {}, None)
        self._cur = self.root
        self._skip: str | None = None
        self.head: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "link" and a.get("rel", "").lower() == "canonical":
            self.head["canonical"] = a.get("href", "")
        if tag == "meta" and a.get("property") == "og:url":
            self.head["og:url"] = a.get("content", "")
        if self._skip:
            return
        node = _Node(tag, a, self._cur)
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
    return re.sub(r"\s+", " ", "".join(parts)).strip()


_INLINE = frozenset({"a", "span", "b", "strong", "em", "i", "font", "u", "sup", "sub", "small",
                     "abbr", "code", "mark"})


def _blocks(root: _Node) -> list[str]:
    """Visible text lines in page order. Any non-inline element, <br> and <img> ends a line, so
    one line is one paragraph, list item, heading or label however the CMS marked it up
    (the news bodies are <font> runs separated by <br>). Navigation chrome is included here and
    simply never matched."""
    lines: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        text = re.sub(r"\s+", " ", "".join(buf)).strip()
        if text:
            lines.append(text)
        buf.clear()

    def visit(n: _Node) -> None:
        for child in n.children:
            if isinstance(child, str):
                buf.append(child)
            elif child.tag in _SKIP:
                continue
            elif child.tag in _INLINE:
                visit(child)
            else:
                flush()
                visit(child)
                flush()

    visit(root)
    flush()
    return lines


def _sentences(block: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(])", block)
    return [p.strip() for p in parts if p.strip()]


# ------------------------------------------------------------------- facts --
# Each reviewed fact: (fact id, kind, regex that must FULL-MATCH one sentence/block,
#                      target hint, representability, structured builder, gap, review questions)
# The regexes were written from the four reviewed pages and tested against fixtures of them.

_WS = r"\s*"
_DEF_BODY = ("the same page set states different body DoF for different configurations or times "
             "(Next-Gen 2025: 82; production 2026: 76); one timeless robot.degrees_of_freedom "
             "would flatten them, and 'whole-body' is not 'whole-system' articulation")
_DEF_HAND = ("stated per hand; no combined two-hand total is stated and none is inferred; the "
             "configurations differ (2025: 22; 2026: 21 in each hand)")

Fact = tuple  # documentation alias


def _structured(**kw: str) -> tuple[tuple[str, str], ...]:
    return tuple(kw.items())


FACTS: dict[str, list[Fact]] = {
    "product-page": [
        ("hero-title", "GENERATION_LABEL", r"XPENG Next-Gen IRON: The Most Human-Like Robot",
         "UNMAPPED", UNREPRESENTABLE, lambda m: _structured(label="Next-Gen IRON"),
         "names the configuration this page describes; no catalogue field carries a generation "
         "label", ("how the Next-Gen / production IRON relates to the catalogue robot",)),
        ("hand-dof-demo", "HAND_DOF",
         r"XPENG Robot.s (?P<n>\d+)-degree-of-freedom bionic hands and precise, stable arms "
         r"handle complex tasks with human-like dexterity\.",
         "robot.hand_dof or a specification", PARTIAL,
         lambda m: _structured(hand_dof_each=m["n"], scope="per hand (wording: 'hands')"),
         _DEF_HAND, ("which hand-DoF figure and convention the catalogue should carry",)),
        ("hand-dof", "HAND_DOF",
         r"With the industry.s smallest harmonic joints, the dexterous hand achieves (?P<n>\d+) "
         r"degrees of freedom.*",
         "robot.hand_dof or a specification", PARTIAL,
         lambda m: _structured(hand_dof_each=m["n"], scope="the (single) dexterous hand"),
         _DEF_HAND, ("which hand-DoF figure and convention the catalogue should carry",)),
        ("shoulder-dof", "SHOULDER_DOF",
         r"With four degrees of freedom in the scapular joint, it can lift, rotate, and "
         r"reach.*",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(scapular_joint_dof="4"),
         "a per-joint figure has no catalogue home", ()),
        ("chips", "COMPUTE",
         r"Powered by three self-developed chips, the robot is equipped with a powerful brain "
         r"that delivers exceptional computing performance\..*",
         "specification[compute_ai]", PARTIAL, lambda m: _structured(chips="3"),
         "a chip count only: no TOPS figure on this page, and no number is inferred",
         ("the catalogue's compute convention (chip count and TOPS are separate statements)",)),
        ("battery", "BATTERY",
         r"Lighter\. Stronger\. Safer\. The solid-state battery redefines energy storage with "
         r"ultimate lightweighting and ultra-high energy density\..*",
         "specification[battery_pack]", PARTIAL, lambda m: _structured(chemistry="solid-state"),
         "marketing wording only: no capacity, voltage or runtime is stated",
         ("whether a chemistry-only statement belongs in battery_pack",)),
        ("architecture", "AI_ARCHITECTURE",
         r"XPENG IRON is powered by a .VLT\+VLA\+VLM. trio: VLM as the brain for perception, "
         r"VLT as the core engine for autonomous decision-making, and VLA as the cerebellum for "
         r"whole-body control\.",
         "UNMAPPED", UNREPRESENTABLE, lambda m: _structured(models="VLT+VLA+VLM"),
         "a software architecture description; no autonomy level is stated or inferred", ()),
        ("spine", "MORPHOLOGY",
         r"A bionic humanoid spine empowers the robot with remarkable flexibility.*",
         "UNMAPPED", UNREPRESENTABLE, lambda m: _structured(feature="bionic spine"),
         "morphology wording; no catalogue field", ()),
        ("muscles", "MORPHOLOGY",
         r"Soft materials meet intelligent design\. Our bionic muscles use generative 3D "
         r"lattice topology.*",
         "UNMAPPED", UNREPRESENTABLE, lambda m: _structured(feature="bionic muscles"),
         "morphology wording; no catalogue field", ()),
        ("skin", "SENSING",
         r"Soft to the touch, responsive by design\. The fully covered flexible skin provides a "
         r"gentle, skin-like feel while embedded tactile sensors enable sensitive touch "
         r"perception.*",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(feature="full-coverage flexible skin with embedded tactile "
                               "sensors"),
         "states embedded tactile sensors; no sensor specification and no capability is "
         "inferred", ()),
        ("display", "MORPHOLOGY",
         r"The bionic spherical display seamlessly integrates seeing, hearing, speaking, and "
         r"expression into a single 3D curved surface\..*",
         "UNMAPPED", UNREPRESENTABLE, lambda m: _structured(feature="head-mounted 3D curved "
                                                            "display"),
         "head/display wording; no catalogue field", ()),
        ("production-teaser", "MANUFACTURING_STATE",
         r"IRON, the First General-Purpose Humanoid Robot, Rolls Off XPENG.s New Production "
         r"Line",
         "UNMAPPED", UNREPRESENTABLE, lambda m: _structured(statement_type="headline"),
         "a headline on the product page; the dated announcement carries the detail. It is not "
         "a commercial maturity", ()),
        ("commercial-settings", "APPLICATIONS",
         r"First to Provide Services in Commercial Settings",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(scenarios="Tour Guide; Shopping Guide; Patrol Guide"),
         "application scenarios; no automatic use-case mapping, and 'first to provide services' "
         "is a marketing claim, not a deployment record", ()),
    ],
    "news-2026-09-08": [
        ("production-line", "MANUFACTURING_STATE",
         r"\W*XPENG has officially commissioned its humanoid robot production lines and completed "
         r"the production-lines manufacturing of the world.s first advanced humanoid robot, "
         r"which autonomously walked off the lines, .*",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(state="production lines commissioned; first unit walked off the "
                               "lines", article_date="2026-09-08"),
         "a manufacturing milestone; it is NOT a commercial maturity and implies no availability",
         ("whether any commercial maturity follows (the dictionary maps none from manufacturing "
          "progress)",)),
        ("automation", "MANUFACTURING_METRIC",
         r"\W*XPENG.s humanoid robot production lines features core process automation exceeding "
         r"80%, .*",
         "UNMAPPED", UNREPRESENTABLE, lambda m: _structured(core_process_automation=">80%"),
         "a factory metric, not a robot specification", ()),
        ("form", "MORPHOLOGY",
         r"XPENG IRON features an industry-leading human-like form and design, with a "
         r"proprietary fully enclosed flexible lattice structure designed to balance aesthetics "
         r"and safety\.",
         "UNMAPPED", UNREPRESENTABLE, lambda m: _structured(feature="fully enclosed flexible "
                                                            "lattice structure"),
         "morphology wording; no catalogue field", ()),
        ("body-dof", "BODY_DOF",
         r"With (?P<body>\d+) degrees of freedom \(DOF\) across the body and (?P<hand>\d+) in "
         r"each hand, IRON delivers industry-leading levels of dexterity and mobility\.",
         "robot.degrees_of_freedom", PARTIAL,
         lambda m: _structured(body_dof=m["body"], scope="across the body",
                               configuration="2026 production IRON"),
         _DEF_BODY, ("which configuration's body DoF the catalogue should carry as current",)),
        ("hand-dof", "HAND_DOF",
         r"With (?P<body>\d+) degrees of freedom \(DOF\) across the body and (?P<hand>\d+) in "
         r"each hand, IRON delivers industry-leading levels of dexterity and mobility\.",
         "robot.hand_dof or a specification", PARTIAL,
         lambda m: _structured(hand_dof_each=m["hand"], scope="in each hand",
                               configuration="2026 production IRON"),
         _DEF_HAND, ("which hand-DoF figure and convention the catalogue should carry",)),
        ("compute", "COMPUTE",
         r"On the intelligence side, XPENG IRON is powered by three Turing AI chips delivering "
         r"up to (?P<tops>[\d,]+) TOPS of effective computing power\.",
         "specification[compute_ai]", PARTIAL,
         lambda m: _structured(chips="3", tops_up_to=m["tops"].replace(",", ""),
                               configuration="2026 production IRON"),
         "'up to' effective computing power; the 2025 Next-Gen statement says 3000 TOPS",
         ("the catalogue's compute convention and which configuration is current",)),
        ("mass-production", "MASS_PRODUCTION_PLAN",
         r"Looking ahead, XPENG robots are scheduled to enter mass production by the end of "
         r"this year, with initial commercial-scenario rollouts beginning in XPENG.s own stores "
         r"and campuses\.",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(stated_timing="by the end of this year",
                               article_year="2026", precision="year-level"),
         "a manufacturing plan stated relative to the article's year; it is not an availability "
         "and carries no date", ()),
        ("internal-rollout", "DEPLOYMENT_PLAN",
         r"Looking ahead, XPENG robots are scheduled to enter mass production by the end of "
         r"this year, with initial commercial-scenario rollouts beginning in XPENG.s own stores "
         r"and campuses\.",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(where="XPENG's own stores and campuses", phase="initial "
                               "commercial-scenario rollouts"),
         "an INTERNAL rollout; it is not external availability and maps to no maturity", ()),
        ("market-launch", "LAUNCH_PLAN",
         r"Official market launch and delivery in China and overseas markets are planned for "
         r"(?P<year>20\d\d)\.",
         "availability_offer (year-level only)", PARTIAL,
         lambda m: _structured(planned_year=m["year"], geography="China and overseas markets",
                               precision="year-level"),
         "a plan for external launch and delivery; no availability status, price or date is "
         "stated and none is chosen (WAITLIST/PREORDER/AVAILABLE are not implied)",
         ("whether and how a year-level launch plan belongs in the catalogue",)),
    ],
    "news-2025-11-05": [
        ("first-generation", "GENERATION_HISTORY",
         r"In 2024, XPENG released its first-generation IRON, whose .human-like. feel left a "
         r"deep impression on the outside world\.",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(generation="first-generation IRON", year="2024"),
         "chronology evidence for the generation relationship", ()),
        ("next-gen-debut", "GENERATION_HISTORY",
         r"At the press conference, XPENG Next-Gen IRON made a stunning debut with its highly "
         r"human-like appearance and catwalk-like graceful gait\.",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(generation="Next-Gen IRON", event="debut", date="2025-11-05"),
         "chronology evidence for the generation relationship", ()),
        ("upgrades", "GENERATION_HISTORY",
         r"Compared with the first-generation IRON, the Next-Gen IRON has achieved "
         r"comprehensive upgrades in bionic structure, intelligence system, and energy "
         r"architecture, .*",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(relationship="Next-Gen IRON is an upgrade of the first-generation "
                               "IRON"),
         "states the generational relationship in XPENG's own words", ()),
        ("design", "MORPHOLOGY",
         r"It has a humanoid spine, bionic muscles, and fully covered flexible skin, and "
         r"supports customisation for different body shapes\.",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(configuration="2025 Next-Gen IRON"),
         "morphology wording; no catalogue field", ()),
        ("body-dof", "BODY_DOF",
         r"With (?P<body>\d+) degrees of freedom throughout the body, .* and the hand has "
         r"(?P<hand>\d+) degrees of freedom\.",
         "robot.degrees_of_freedom", PARTIAL,
         lambda m: _structured(body_dof=m["body"], scope="throughout the body",
                               configuration="2025 Next-Gen IRON"),
         _DEF_BODY, ("which configuration's body DoF the catalogue should carry as current",)),
        ("hand-dof", "HAND_DOF",
         r"With (?P<body>\d+) degrees of freedom throughout the body, .* and the hand has "
         r"(?P<hand>\d+) degrees of freedom\.",
         "robot.hand_dof or a specification", PARTIAL,
         lambda m: _structured(hand_dof_each=m["hand"], scope="the hand",
                               configuration="2025 Next-Gen IRON"),
         _DEF_HAND, ("which hand-DoF figure and convention the catalogue should carry",)),
        ("battery", "BATTERY",
         r"Meanwhile, the XPENG Next-Gen IRON also pioneered the application of all-solid-state "
         r"batteries in the industry, .*",
         "specification[battery_pack]", PARTIAL,
         lambda m: _structured(chemistry="all-solid-state", configuration="2025 Next-Gen IRON"),
         "marketing wording only: no capacity, voltage or runtime is stated",
         ("whether a chemistry-only statement belongs in battery_pack",)),
        ("compute", "COMPUTE",
         r"The XPENG Next-Gen IRON is equipped with 3 Turing AI chips, with an effective "
         r"computing power of (?P<tops>[\d,]+) TOPS, .*",
         "specification[compute_ai]", PARTIAL,
         lambda m: _structured(chips="3", tops=m["tops"].replace(",", ""),
                               configuration="2025 Next-Gen IRON"),
         "the 2026 production statement says up to 2,250 TOPS; both are kept",
         ("the catalogue's compute convention and which configuration is current",)),
        ("applications", "APPLICATIONS",
         r"At the monetisation plan level, XPENG Next-Gen IRON will prioritise entering "
         r"commercial scenarios to provide services such as guided tours, shopping guides, and "
         r"traffic diversion\.",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(scenarios="guided tours; shopping guides; traffic diversion"),
         "application scenarios; no automatic use-case mapping", ()),
        ("mass-production", "MASS_PRODUCTION_PLAN",
         r"He Xiaopeng said, .By the end of 2026, XPENG aims to achieve large-scale mass "
         r"production of high-level humanoid robots\..",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(stated_timing="by the end of 2026", precision="year-level",
                               stated_on="2025-11-05"),
         "a plan stated in 2025; not an availability and carries no date", ()),
        ("sdk-plan", "SDK_PLAN",
         r"He Xiaopeng said, .To accelerate the application and implementation of humanoid "
         r"robots, XPENG IRON will open its SDK and jointly build a humanoid robot application "
         r"ecosystem with global developers\. ?.",
         "UNMAPPED", UNREPRESENTABLE, lambda m: _structured(tense="future (will open)"),
         "a future statement: not a present SDK, so no has_sdk is derived", ()),
    ],
    "news-2024-11-06": [
        ("system-dof", "SYSTEM_DOF_2024",
         r"\W*XPENG AI Robot Iron: XPENG.s latest humanoid robot, developed over five years, "
         r"has more than (?P<j>\d+) "
         r"joints and (?P<d>\d+) degrees of freedom, with technology shared from XPENG.s AI "
         r"vehicles\.",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(joints=f"more than {m['j']}", degrees_of_freedom=m["d"],
                               configuration="2024 first-generation IRON",
                               scope="as worded: joints and degrees of freedom of the robot "
                                     "(not directly comparable with the body-DoF figures of "
                                     "the later configurations)"),
         "a 2024 first-generation system-level figure; it is not the body DoF of later "
         "configurations and is not mapped to robot.degrees_of_freedom", ()),
        ("internal-use", "DEPLOYMENT_STATE",
         r"The robots have already been integrated into XPENG.s daily operations and focus on "
         r"internal applications, such as factories and stores\.",
         "UNMAPPED", UNREPRESENTABLE,
         lambda m: _structured(where="XPENG's own factories and stores",
                               configuration="2024 first-generation IRON"),
         "internal use in 2024; it maps to no commercial maturity", ()),
    ],
}


def _find_sentence(blocks: list[str], pattern: re.Pattern) -> tuple[str, re.Match] | None:
    for block in blocks:
        if pattern.fullmatch(block):
            return block, pattern.fullmatch(block)
        for sentence in _sentences(block):
            m = pattern.fullmatch(sentence)
            if m:
                return sentence, m
    return None


def propose_xpeng_iron_claims(body: bytes, url: str | None) -> ProposalSet:
    """Proposals for one of the four reviewed XPENG IRON pages. Pure and deterministic."""
    try:
        page_url = normalize_url(url or "")
    except UnsupportedUrl:
        return ProposalSet(OUT_OF_SCOPE, url or "", notes=("no usable page URL",))
    if page_url not in PAGES:
        return ProposalSet(OUT_OF_SCOPE, page_url, notes=(
            "this extractor reads the four reviewed XPENG IRON pages only",))
    page_key, expected_date = PAGES[page_url]

    tree = _Tree()
    tree.feed(body.decode("utf-8", errors="replace"))
    tree.close()
    for label in ("canonical", "og:url"):
        stated = tree.head.get(label)
        if stated:
            try:
                same = normalize_url(stated) == page_url
            except UnsupportedUrl:
                same = False
            if not same:
                return ProposalSet(AMBIGUOUS, page_url, notes=(
                    f"{label} {stated!r} is not this page",))
    blocks = _blocks(tree.root)
    if expected_date is not None and expected_date not in blocks:
        return ProposalSet(NO_PROPOSALS, page_url, notes=(
            f"the expected date line {expected_date!r} is not on the page",))
    if page_key == "product-page" and not any(
            re.fullmatch(r"XPENG (?:Next-Gen )?IRON: .*", b) for b in blocks):
        return ProposalSet(NO_PROPOSALS, page_url, notes=(
            "the IRON title block is not on the product page",))

    made: list[Proposal] = []
    rejected: list[tuple[str, str]] = []
    for fact_id, kind, regex, target, rep, structured, gap, review in FACTS[page_key]:
        found = _find_sentence(blocks, re.compile(regex))
        if found is None:
            rejected.append((f"{page_key}/{fact_id}", "the reviewed statement is not on the "
                             "page as expected; nothing is proposed for it"))
            continue
        sentence, match = found
        evidence = _evidence(sentence, f"{page_key}/text-block[{fact_id}]")
        if evidence is None:
            rejected.append((f"{page_key}/{fact_id}", "no bounded excerpt"))
            continue
        made.append(Proposal(
            kind=kind, target=target, representability=rep, value=sentence,
            structured=(("source_page", page_key), *structured(match)), evidence=evidence,
            source_url=page_url, gap=gap, review_required=tuple(review)))

    # The three application scenarios on the product page are separate, verbatim labels.
    if page_key == "product-page":
        for label in ("Tour Guide", "Shopping Guide", "Patrol Guide"):
            if label in blocks:
                ev = _evidence(label, f"{page_key}/text-block[scenario:{label}]")
                if ev is not None:
                    made.append(Proposal(
                        kind="APPLICATIONS", target="UNMAPPED", representability=UNREPRESENTABLE,
                        value=label, structured=(("source_page", page_key),
                                                 ("context", "First to Provide Services in "
                                                  "Commercial Settings")),
                        evidence=ev, source_url=page_url,
                        gap="an application scenario label; no automatic use-case mapping"))
            else:
                rejected.append((f"{page_key}/scenario:{label}", "label not on the page"))

    status = PROPOSED if made else NO_PROPOSALS
    return ProposalSet(status, page_url, robot_name=ROBOT_NAME if made else None,
                       proposals=tuple(made), rejected=tuple(rejected),
                       ignored=IGNORED_BY_DESIGN, notes=(f"page: {page_key}",))


def page_key_for(url: str) -> str | None:
    try:
        return PAGES.get(normalize_url(url), (None, None))[0]
    except UnsupportedUrl:
        return None


__all__ = ["propose_xpeng_iron_claims", "ProposalSet", "Proposal", "PAGES", "PAGE_URLS",
           "EXTRACTOR_KEY", "EXTRACTOR_VERSION", "ROBOT_NAME", "PRODUCT_PAGE_URL",
           "page_key_for", "urlsplit"]
