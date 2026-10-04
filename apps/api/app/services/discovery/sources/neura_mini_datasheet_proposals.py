"""NEURA 4NE1 Mini DATASHEET — PROPOSAL-ONLY structured claim extraction (G5-2).

`propose_neura_mini_datasheet_claims(body, url)` reads ONE first-party document, the 2-page
"4NE1 Mini datasheet" PDF linked from NEURA's approved 4NE1 Mini product page and hosted on the
owner-approved `neurarobotics.px.media` (path prefix `/plk/`), and returns evidence-bearing
*proposals*: what the sheet states, where, and which catalogue home (if any) a human could map
it to. Pure and deterministic: bytes in, dataclasses out. No session, no I/O beyond decoding the
bytes, no model import, no database.

A proposal is not a claim: every one is `NOT_VERIFIED` and review-required until the separately
governed review / claim / materialization chain (DR-A5) accepts it. Nothing here writes the
catalogue, and nothing is inferred (docs/discovery, G5 "missing fact does not authorize
inference"):

- the sheet does not name an edition, so every proposal carries `edition = None` and a review
  question; Standard/Pro are never guessed;
- "Speed Max. 4.6 km/h" is kept verbatim and NOT mapped to walking speed; "Operating Time (h)
  24/7" is kept verbatim and NOT mapped to runtime; "Motion Endurance (h) 2.5" is proposed as
  endurance with its unit conversion left to the reviewer;
- the capability icons (natural language interaction, computer vision, reinforcement learning,
  voice recognition, multi-language) are marketing labels and are ignored by design: no boolean
  such as `has_vision` is derived from them;
- the DoF figure is the base unit only (the sheet's own footnote), never a total with hands.

Each value is read by a label-anchored pattern, so a CHANGED number or wording produces a new
proposal (a new digest in the same slot, which supersedes the old one for review) while an
unchanged value produces the same digest. A label whose pattern no longer matches produces NO
proposal for it and a reason in `rejected`; the caller reports it (`NOT_RESTATED`).

The document version line ("V1 / 01.01.2026") is its own proposal, so a version bump that
repeats every value does not duplicate them.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass

from app.services.discovery.live_adapter import Evidence, _evidence
from app.services.discovery.urlref import UnsupportedUrl, normalize_url

EXTRACTOR_KEY = "neura-mini-datasheet-proposals"
EXTRACTOR_VERSION = "0.1.0"
ROBOT_NAME = "4NE1 Mini"
DATASHEET_URL = "https://neurarobotics.px.media/plk/Jj/4NE1Minidatasheet.pdf"
PAGE_URLS = (DATASHEET_URL,)
CLAIM_STATUS = "NOT_VERIFIED"

CLEAN, PARTIAL, UNREPRESENTABLE = "CLEAN", "PARTIAL", "UNREPRESENTABLE"
PROPOSED, NO_PROPOSALS, AMBIGUOUS, OUT_OF_SCOPE = (
    "PROPOSED", "NO_PROPOSALS", "AMBIGUOUS", "OUT_OF_SCOPE")

IGNORED_BY_DESIGN = (
    ("capability icons (natural language interaction, computer vision, reinforcement learning, "
     "multimodal cognitive interaction, voice recognition, multi-language)",
     "marketing labels; no capability boolean is derived from them"),
    ("tagline, copyright and 'Designed and engineered in Germany'", "not product data"),
    ("'Reserve 4NE1 Mini' call to action", "a transaction surface; never read"),
)

_EDITION_QUESTION = ("the datasheet does not say which edition(s) it covers "
                     "(Standard, Pro or both); a human must decide the scope")
_TEXT = r"[A-Za-z0-9 ,.&+/\-]{1,160}"
_NUM = r"\d+(?:\.\d+)?"

# (kind, label-anchored pattern over the whitespace-collapsed text, locator)
_PATTERNS: tuple[tuple[str, re.Pattern, str], ...] = (
    ("DATASHEET_HEIGHT", re.compile(rf"Height (?P<cm>{_NUM}) cm (?P<ft>\d+’ ?\d+”)"),
     "page 1 / Height"),
    ("DATASHEET_WEIGHT", re.compile(rf"Weight (?P<kg>{_NUM}) kg (?P<lbs>{_NUM}) lbs"),
     "page 1 / Weight"),
    ("DATASHEET_PAYLOAD", re.compile(rf"Payload (?P<kg>{_NUM}) kg (?P<lbs>{_NUM}) lbs"),
     "page 1 / Payload"),
    ("DATASHEET_SPEED", re.compile(
        rf"Speed Max\. (?P<kmh>{_NUM}) km/h (?P<mph>{_NUM}) mph"), "page 1 / Speed"),
    ("DATASHEET_OPERATING_TIME", re.compile(
        rf"Operating Time \(h\) (?P<h>24/7|{_NUM})"), "page 1 / Operating Time (h)"),
    ("DATASHEET_MOTION_ENDURANCE", re.compile(
        rf"Motion Endurance \(h\) (?P<h>{_NUM})"), "page 1 / Motion Endurance (h)"),
    ("DATASHEET_DOF", re.compile(
        r"DoF\* .{0,300}?degrees of freedom of the base unit only and does not include hands "
        r"or end effectors, which may each have up to (?P<hand>\d+) DoF independently\. "
        r"(?P<dof>\d+) Motion Endurance"), "page 1 / DoF"),
    ("DATASHEET_INTERFACES", re.compile(rf"Interfaces (?P<text>{_TEXT}) Payload "),
     "page 1 / Interfaces"),
    ("DATASHEET_SAFETY_OPTION", re.compile(
        r"Safety\* (?P<text>Human detection) .{0,200}?\* Safety human detection sensors are "
        r"(?P<note>optional and available at an additional cost)"), "page 1 / Safety"),
    ("DATASHEET_AVAILABILITY_STATEMENT", re.compile(
        r"to receive your 4NE1 Mini in (?P<when>[A-Za-z]+ 20\d\d)\."), "page 2 / body text"),
    ("DATASHEET_DOCUMENT_VERSION", re.compile(
        r"All rights reserved (?P<v>V\d+ / \d{2}\.\d{2}\.\d{4})"), "footer"),
)

_TARGET = {
    "DATASHEET_HEIGHT": ("robot.height_cm", PARTIAL),
    "DATASHEET_WEIGHT": ("robot.weight_kg", PARTIAL),
    "DATASHEET_PAYLOAD": ("robot.payload_kg", PARTIAL),
    "DATASHEET_SPEED": ("UNMAPPED (walking speed is NOT inferred from a maximum speed)",
                        UNREPRESENTABLE),
    "DATASHEET_OPERATING_TIME": ("UNMAPPED (runtime is NOT inferred from 24/7)",
                                 UNREPRESENTABLE),
    "DATASHEET_MOTION_ENDURANCE": ("robot.runtime_minutes (unit conversion by the reviewer)",
                                   PARTIAL),
    "DATASHEET_DOF": ("robot.degrees_of_freedom (base unit only)", PARTIAL),
    "DATASHEET_INTERFACES": ("specification[common_interfaces] (verbatim)", PARTIAL),
    "DATASHEET_SAFETY_OPTION": ("UNMAPPED (an optional sensor is not a standard capability)",
                                UNREPRESENTABLE),
    "DATASHEET_AVAILABILITY_STATEMENT": ("availability_offer (season-level, not a date)",
                                         PARTIAL),
    "DATASHEET_DOCUMENT_VERSION": ("evidence_source (source_type MANUFACTURER_DOC) provenance",
                                   PARTIAL),
}

_GAP = {
    "DATASHEET_PAYLOAD": "the sheet does not say whether the payload is per arm or in total",
    "DATASHEET_SPEED": "a maximum speed; the sheet does not say walking speed",
    "DATASHEET_OPERATING_TIME": "the sheet does not say what 24/7 operation requires "
                                "(charging, swapping, tethering)",
    "DATASHEET_DOF": "base unit only; hands/end effectors 'may each have up to N DoF'",
    "DATASHEET_AVAILABILITY_STATEMENT": "a season, not an available-from date",
    "DATASHEET_SAFETY_OPTION": "sensors are optional at additional cost",
}
_EXTRA_REVIEW = {
    "DATASHEET_MOTION_ENDURANCE": ("map 'Motion Endurance (h)' to runtime_minutes only if "
                                   "you accept hours x 60 as the same concept",),
    "DATASHEET_DOCUMENT_VERSION": (),
}


@dataclass(frozen=True)
class DatasheetProposal:
    kind: str
    edition: str | None
    target: str
    representability: str
    value: str
    structured: tuple[tuple[str, str], ...]
    evidence: Evidence
    confidence: str
    gap: str | None = None
    review_required: tuple[str, ...] = ()
    source_url: str = DATASHEET_URL
    method: str = "PATTERN"
    claim_status: str = CLAIM_STATUS

    @property
    def digest(self) -> str:
        """Stable identity of the proposal's content (not of the observation)."""
        payload = json.dumps(
            [EXTRACTOR_KEY, EXTRACTOR_VERSION, self.source_url, self.kind, self.edition,
             self.target, self.value, self.structured], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DatasheetProposalSet:
    status: str
    source_url: str
    proposals: tuple[DatasheetProposal, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()   # (label, why it produced no proposal)
    ignored: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()
    extractor: str = f"{EXTRACTOR_KEY}@{EXTRACTOR_VERSION}"

    writes_catalogue = False
    writes_candidate_claims = False


def pdf_pages(body: bytes) -> list[str] | None:
    """The text of each page, or None when the bytes are not a readable PDF."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        return [page.extract_text() or "" for page in reader.pages]
    except Exception:  # noqa: BLE001 - any parser failure means "not readable", never a guess
        return None


def _flat(pages: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(pages)).strip()


def _value(kind: str, m: re.Match) -> tuple[str, tuple[tuple[str, str], ...]]:
    g = m.groupdict()
    if kind == "DATASHEET_HEIGHT":
        return f"{g['cm']} cm", (("cm", g["cm"]),)
    if kind in ("DATASHEET_WEIGHT", "DATASHEET_PAYLOAD"):
        return f"{g['kg']} kg", (("kg", g["kg"]),)
    if kind == "DATASHEET_SPEED":
        return f"Max. {g['kmh']} km/h", (("km_per_h", g["kmh"]),)
    if kind in ("DATASHEET_OPERATING_TIME", "DATASHEET_MOTION_ENDURANCE"):
        return f"{g['h']} h" if g["h"] != "24/7" else "24/7", (("hours_as_stated", g["h"]),)
    if kind == "DATASHEET_DOF":
        return g["dof"], (("dof_base_unit", g["dof"]), ("hand_dof_up_to_each", g["hand"]))
    if kind == "DATASHEET_INTERFACES":
        text = re.sub(r"\s+", " ", g["text"]).strip()
        return text, (("verbatim", text),)
    if kind == "DATASHEET_SAFETY_OPTION":
        return f"{g['text']}: {g['note']}", (("verbatim", f"{g['text']}: {g['note']}"),)
    if kind == "DATASHEET_AVAILABILITY_STATEMENT":
        return g["when"], (("stated", g["when"]),)
    return g["v"], (("document_version", g["v"]),)


def _excerpt(kind: str, m: re.Match) -> str:
    """The bounded verbatim evidence: only the sentence/cells that state the value."""
    g = m.groupdict()
    if kind == "DATASHEET_DOF":
        return ("DoF* ... DoF indicates the degrees of freedom of the base unit only and does "
                f"not include hands or end effectors, which may each have up to {g['hand']} DoF "
                f"independently. {g['dof']}")
    if kind == "DATASHEET_SAFETY_OPTION":
        return f"Safety* {g['text']} ... Safety human detection sensors are {g['note']}"
    return re.sub(r"\s+", " ", m.group(0)).strip()


def propose_neura_mini_datasheet_claims(body: bytes, url: str | None) -> DatasheetProposalSet:
    """Proposals for the 4NE1 Mini datasheet PDF. Pure and deterministic."""
    try:
        page_url = normalize_url(url or "")
    except UnsupportedUrl:
        return DatasheetProposalSet(OUT_OF_SCOPE, url or "", notes=("no usable document URL",))
    if page_url not in PAGE_URLS:
        return DatasheetProposalSet(OUT_OF_SCOPE, page_url, notes=(
            "this extractor reads the 4NE1 Mini datasheet only",))
    pages = pdf_pages(body)
    if not pages:
        return DatasheetProposalSet(NO_PROPOSALS, page_url, notes=(
            "the body is not a readable PDF (no text layer)",))
    text = _flat(pages)
    if "4NE1 Mini" not in text:
        return DatasheetProposalSet(NO_PROPOSALS, page_url, notes=(
            f"identity not confirmed: the document does not name {ROBOT_NAME!r}",))

    proposals: list[DatasheetProposal] = []
    rejected: list[tuple[str, str]] = []
    for kind, pattern, locator in _PATTERNS:
        m = pattern.search(text)
        if m is None:
            rejected.append((kind, "label pattern not found (the sheet may no longer state it)"))
            continue
        value, structured = _value(kind, m)
        ev = _evidence(_excerpt(kind, m), locator)
        if ev is None:      # no bounded excerpt, no proposal
            rejected.append((kind, "evidence excerpt empty or too long"))
            continue
        target, rep = _TARGET[kind]
        review = () if kind == "DATASHEET_DOCUMENT_VERSION" else (_EDITION_QUESTION,)
        proposals.append(DatasheetProposal(
            kind=kind, edition=None, target=target, representability=rep, value=value,
            structured=structured, evidence=ev, confidence="MEDIUM",   # PDF text order
            gap=_GAP.get(kind), review_required=(*review, *_EXTRA_REVIEW.get(kind, ())),
            ))
    proposals.sort(key=lambda p: p.kind)
    return DatasheetProposalSet(
        PROPOSED if proposals else NO_PROPOSALS, page_url, tuple(proposals), tuple(rejected),
        IGNORED_BY_DESIGN)
