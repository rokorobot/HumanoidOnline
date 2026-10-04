"""G5 — COMMERCIAL_MATURITY proposal extraction (owner ruling 2026-10-04).

`propose_maturity_clues(body, url, robot_name=..., page_scope=...)` reads ONE already-retrieved
first-party page and returns evidence-bearing *proposals*: sentences that state something relevant
to a robot's commercial maturity, with the explicit factual CLUES the sentence contains.

Automation discovers and preserves the evidence; a human decides which frozen HumanoidOnline
maturity state, if any, the evidence establishes. So this module:

- is a pure function (bytes in, dataclasses out); no I/O, no database, no randomness;
- records CLUES ("delivery stated", "pilot stated", "future launch stated", ...), which are
  observations about the wording and are NOT statuses. No clue maps to a status here: delivery is
  not COMMERCIAL, production is not COMMERCIAL, a pilot is not PILOT without scope review, a
  customer deployment is not RAAS_DEPLOYMENT, a sale is not COMMERCIAL, a future launch is not
  ANNOUNCED. There is no suggested or default status anywhere in the proposal;
- preserves the sentence verbatim (whitespace-collapsed) as the bounded evidence excerpt;
- keeps a sentence only if it names the robot (or the caller declared the whole page to be that
  robot's own page), so another product's wording is never attached to this robot.

Unchanged wording yields the same digest, so re-observing it creates no new proposal.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from app.services.discovery.live_adapter import Evidence, _evidence

EXTRACTOR_KEY = "maturity-clues"
EXTRACTOR_VERSION = "0.1.0"
KIND = "COMMERCIAL_MATURITY"
TARGET = "commercial_status"
LOCATOR_PREFIX = "text[maturity]/"
CLAIM_STATUS = "NOT_VERIFIED"

PROPOSED, NO_PROPOSALS = "PROPOSED", "NO_PROPOSALS"
ROBOT_PAGE, SHARED_PAGE = "ROBOT_PAGE", "SHARED_PAGE"

#: A bounded number of proposals per page, in page order (deterministic).
MAX_PROPOSALS_PER_PAGE = 8

REVIEW_QUESTION = (
    "Is this wording a CURRENT statement about exactly this robot (not another model, edition, "
    "earlier generation or a plan), and which frozen maturity status, if any, does it establish?")

#: Observation vocabulary. Each clue is something the sentence EXPLICITLY states; none is a status.
_CLUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("CUSTOMER_DELIVERY_STATED", re.compile(r"\bdeliver(?:ed|ing|ies|y)\b")),
    ("SHIPPING_STATED", re.compile(r"\bshipp(?:ing|ed)\b|\bships\b")),
    ("PILOT_STATED", re.compile(r"\bpilots?\b")),
    ("PURCHASE_OR_SALE_STATED", re.compile(
        r"\bbuy now\b|\bpurchas(?:e|ed|ing)\b|\border(?:s|ed|ing)?\b|\bpre-?order\b"
        r"|\bfor sale\b|\badd to cart\b|\bsold\b")),
    ("SELECTED_PARTNER_DEPLOYMENT_STATED", re.compile(
        r"\b(?:selected|select|early|launch)\s+(?:partners?|customers?)\b")),
    ("DEPLOYMENT_STATED", re.compile(r"\bdeploy(?:ed|ment|ments|ing)\b")),
    ("INTERNAL_DEPLOYMENT_STATED", re.compile(r"\binternal(?:ly)?\b|\bin-house\b")),
    ("SERVICE_CONTRACT_STATED", re.compile(
        r"\braas\b|\brobot[- ]as[- ]a[- ]service\b|\bsubscription\b|\brent(?:al|ed|ing)?\b"
        r"|\blease(?:d)?\b|\bleasing\b")),
    ("PRODUCTION_STATED", re.compile(r"\bmass[- ]production\b|\bin production\b|\bproduction\b")),
    ("FUTURE_LAUNCH_STATED", re.compile(
        r"\bwill (?:launch|be (?:available|released|launched)|ship|begin)\b|\bplanned for\b"
        r"|\bexpected (?:in|to|by)\b|\bcoming (?:in|soon)\b|\bscheduled for\b")),
    ("DISCONTINUATION_STATED", re.compile(
        r"\bdiscontinued\b|\bend of life\b|\bno longer (?:available|sold|offered)\b")),
)

_MONTHS = ("january february march april may june july august september october november "
           "december").split()
_DATE_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_DATE_US = re.compile(r"\b(\d\d)/(\d\d)/(20\d\d)\b")
_DATE_LONG = re.compile(r"\b(" + "|".join(m.capitalize() for m in _MONTHS)
                        + r")\s+(\d{1,2}),\s+(20\d\d)\b")

_BLOCK = frozenset({"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div", "section", "article",
                    "td", "th", "tr", "ul", "ol", "br", "header", "footer", "main", "figcaption",
                    "blockquote", "a", "button", "span", "time"})
_SKIP = frozenset({"script", "style", "noscript", "template", "nav"})
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“])")


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
    method: str = "PATTERN"
    claim_status: str = CLAIM_STATUS

    @property
    def digest(self) -> str:
        payload = json.dumps(
            [EXTRACTOR_KEY, EXTRACTOR_VERSION, self.source_url, self.robot_name, self.kind,
             self.edition,
             self.target, self.value, self.structured], ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MaturityProposalSet:
    status: str
    source_url: str
    proposals: tuple[Proposal, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()

    #: Structural guarantee, asserted by tests: this result describes no write and no status.
    writes_catalogue = False
    suggests_status = False


class _Blocks(HTMLParser):
    """Visible text split into blocks at block-level boundaries; script/style/nav dropped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._cur: list[str] = []
        self._skip: str | None = None

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._cur)).strip()
        if text:
            self.blocks.append(text)
        self._cur = []

    def handle_starttag(self, tag, attrs):
        if self._skip:
            return
        if tag in _SKIP:
            self._skip = tag
        elif tag in _BLOCK and tag not in ("a", "span", "time"):
            self._flush()

    def handle_endtag(self, tag):
        if self._skip:
            if tag == self._skip:
                self._skip = None
            return
        if tag in _BLOCK and tag not in ("a", "span", "time"):
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._cur.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def _context_dates(sentence: str) -> list[str]:
    found: list[str] = []
    for y, m, d in _DATE_ISO.findall(sentence):
        found.append(f"{y}-{m}-{d}")
    for m, d, y in _DATE_US.findall(sentence):
        found.append(f"{y}-{m}-{d}")
    for mon, d, y in _DATE_LONG.findall(sentence):
        found.append(f"{y}-{_MONTHS.index(mon.lower()) + 1:02d}-{int(d):02d}")
    return sorted(set(found))


def clues_in(sentence: str) -> list[str]:
    low = sentence.lower()
    return [name for name, rx in _CLUES if rx.search(low)]


def _names_robot(sentence: str, robot_name: str) -> bool:
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(robot_name) + r"(?![A-Za-z0-9])", sentence,
                     flags=re.IGNORECASE) is not None


def propose_maturity_clues(body: bytes, url: str, *, robot_name: str,
                           page_scope: str = SHARED_PAGE) -> MaturityProposalSet:
    """Maturity-relevant sentences on one first-party page, as proposals (never a status)."""
    if page_scope not in (ROBOT_PAGE, SHARED_PAGE):
        raise ValueError(f"unknown page scope {page_scope!r}")
    if not robot_name.strip():
        raise ValueError("a robot name is required: wording is attached to one robot only")
    parser = _Blocks()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()

    proposals: list[Proposal] = []
    rejected: list[tuple[str, str]] = []
    seen: set[str] = set()
    for block in parser.blocks:
        for sentence in _SENTENCE_END.split(block):
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue
            clues = clues_in(sentence)
            if not clues:
                continue
            names = _names_robot(sentence, robot_name)
            if not names and page_scope != ROBOT_PAGE:
                rejected.append((sentence[:80], "does not name the robot on a shared page"))
                continue
            if sentence in seen:
                continue
            locator = LOCATOR_PREFIX + hashlib.sha256(sentence.encode("utf-8")).hexdigest()[:12]
            evidence = _evidence(sentence, locator)
            if evidence is None:
                rejected.append((sentence[:80], "no bounded excerpt"))
                continue
            seen.add(sentence)
            dates = _context_dates(sentence)
            structured: list[tuple[str, object]] = [
                ("clues", clues), ("names_robot", names), ("page_scope", page_scope)]
            if len(dates) == 1:
                structured.append(("context_date", dates[0]))
            proposals.append(Proposal(
                kind=KIND, edition=None, target=TARGET, representability="PARTIAL",
                value=sentence, structured=tuple(structured), evidence=evidence,
                confidence="MEDIUM",
                gap="the wording alone does not establish a frozen maturity status; the "
                    "reviewer chooses one explicitly, or rejects/defers",
                review_required=(REVIEW_QUESTION,), source_url=url, robot_name=robot_name))
    proposals = proposals[:MAX_PROPOSALS_PER_PAGE]
    return MaturityProposalSet(
        status=PROPOSED if proposals else NO_PROPOSALS, source_url=url,
        proposals=tuple(proposals), rejected=tuple(rejected))
