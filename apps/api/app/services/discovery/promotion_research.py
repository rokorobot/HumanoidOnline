"""HO-DATA Fast Lane FL-1: agent-assisted manufacturer research -> promotion manifest (version 2).

The claim-based path (`promotion_manifest.propose`) promotes DATA-D1 `candidate_claim` rows into
long-tail `extended_specs`. Agent-assisted research (docs/26 A3: HO-DATA-02B/02C, HO-DATA-SR-01)
produces no `candidate_claim`, and the six core columns live on the `robot` row, so until now a
research batch reached the catalogue only as a hand-edited robot JSON plus a hand-written
preflight manifest (PR #191). This module turns an EVIDENCE PACKAGE (already-collected research
records, see `REQUIRED_FIELDS`) into the same kind of sealed, reviewable manifest, so the batch
uses the existing review rendering, deterministic catalogue edit and CI `promotion verify` gate.

Scope, deliberately small:

* Only the six core columns in `CORE_FIELDS`, and only NULL -> value. A known value is a change
  (REVIEW_REQUIRED); the same value is refused; UNKNOWN stays UNKNOWN (AGENTS.md rule 6).
* Only a direct manufacturer statement or an EXACT unit conversion at the column's precision.
  Ranges, rounding, per-arm / up-to / peak qualifiers and other derivations need review.
* Provenance stays `AGENT_ASSISTED_RESEARCH` (docs/26 §3.1): the catalogue edit writes the fixed
  provenance statement into `specs_note` (§3.2) and the verbatim label into `spec_caveats`. It
  never claims human verification and writes no `evidence_source` row.
* A version-2 manifest is NOT executable by `promotion execute` (it refuses it): the executor's
  role and post-state checks cover `specification` additions only. Until that is separately
  decided, an approved v2 manifest is applied by the operator's scoped import, gated by
  `db/import_preflight.py` with `derive_preflight_manifest(manifest)`.

Everything here is pure except `propose_research` (READ-ONLY: the base fingerprints and an
optional lookup of a matching `fetched_page` observation) and the file edits of
`promotion_manifest.apply_to_catalogue`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path

from sqlalchemy import text

from app.services.discovery import promotion_manifest as pm
from app.services.discovery.promotion import _APPROVED_FIELDS

MANIFEST_VERSION = 2
EVIDENCE_CLASS = "AGENT_ASSISTED_RESEARCH"
ALLOWED_TABLES = ["robot"]
ALLOWED_QUALIFIERS = frozenset({"approximately"})
EDITION_SCOPES = ("ALL_EDITIONS", "THIS_EDITION")
NOT_STATED = "NOT_STATED"

#: The sentence the owner replaced in PR #191 review (7a68df9) as misleading once first-party
#: specifications are present, and the owner-approved wording that replaced it.
STALE_NOTE = "Specifications not yet verified."
_EVIDENCE_STATUS = ("Selected specifications retrieved from first-party manufacturer "
                    "documentation on {date} under {work_order}. Evidence status: "
                    "AGENT_ASSISTED_RESEARCH; not human-verified. Remaining specifications are "
                    "unknown unless separately documented.")
#: Existing note wording that may contradict newly filled values: reported, never rewritten.
_CONTRADICTING = re.compile(r"not (yet )?(verified|confirmed)|left NULL", re.IGNORECASE)

REQUIRED_FIELDS = ("robot", "edition", "edition_scope", "field", "stated_value", "verbatim",
                   "excerpt", "source_url", "source_title", "source_class", "content_sha256",
                   "retrieved_at", "retrieval_actor", "retrieval_tool", "initiated_by",
                   "work_order", "scope", "locator")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PLAIN_NUMBER = re.compile(r"^\d+(\.\d+)?$")


@dataclass(frozen=True)
class CoreField:
    label: str
    unit: str | None              # the catalogue column's unit (None: a count)
    step: Fraction                # the column's precision (db/schema.sql)
    integer: bool
    conversions: dict             # stated unit -> exact factor to the column's unit
    needs_condition: bool = False  # speed / runtime only mean something with their condition


def _unit(field: str) -> str | None:
    """height/weight/payload units come from the existing promotion gate, so they cannot drift."""
    return _APPROVED_FIELDS[field][1]


CORE_FIELDS: dict[str, CoreField] = {
    "height_cm": CoreField("Height", _unit("height_cm"), Fraction(1, 10), False,
                           {"cm": Fraction(1), "mm": Fraction(1, 10), "m": Fraction(100)}),
    "weight_kg": CoreField("Weight", _unit("weight_kg"), Fraction(1, 10), False,
                           {"kg": Fraction(1), "g": Fraction(1, 1000)}),
    "payload_kg": CoreField("Payload", _unit("payload_kg"), Fraction(1, 10), False,
                            {"kg": Fraction(1), "g": Fraction(1, 1000)}),
    "walk_speed_ms": CoreField("Walking speed", "m/s", Fraction(1, 100), False,
                               {"m/s": Fraction(1), "km/h": Fraction(1000, 3600)},
                               needs_condition=True),
    "runtime_minutes": CoreField("Runtime", "min", Fraction(1), True,
                                 {"min": Fraction(1), "h": Fraction(60)}, needs_condition=True),
    "degrees_of_freedom": CoreField("Degrees of freedom", None, Fraction(1), True,
                                    {None: Fraction(1)}),
}


# --------------------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------------------- #
def load_records(path: Path) -> list[dict]:
    """An evidence package: {"records": [...]}. Records are data, never instructions."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list) or not records:
        raise pm.ProposalRefused("evidence package has no 'records' list")
    return records


def evidence_id(record: dict) -> str:
    """Deterministic id of one research record (stands in for a claim id in decisions.json)."""
    return "research-" + hashlib.sha256(pm.canonical_json(record).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------------------- #
# Checks (pure; each returns a list of reasons, [] = pass)
# --------------------------------------------------------------------------------------- #
def check_provenance(record: dict, today: date) -> list[str]:
    missing = [f for f in REQUIRED_FIELDS if not str(record.get(f) or "").strip()]
    if missing:
        return [f"missing evidence: {', '.join(missing)}"]
    reasons = []
    if record["source_class"] != "MANUFACTURER":
        reasons.append(f"source class is {record['source_class']}, not MANUFACTURER")
    if not str(record["source_url"]).startswith("https://"):
        reasons.append("source URL is not an https page URL")
    if not _SHA256.match(str(record["content_sha256"])):
        reasons.append("content_sha256 is not a sha256 hex digest")
    if len(record["excerpt"]) > 1000:
        reasons.append("excerpt is longer than 1000 characters (docs/26 §3)")
    if record["verbatim"] not in record["excerpt"]:
        reasons.append("the verbatim label is not part of the excerpt")
    if str(record["stated_value"]) not in record["verbatim"]:
        reasons.append("the stated value is not part of the verbatim label")
    retrieved = retrieved_on(record)
    if retrieved is None:
        reasons.append("retrieved_at is not an ISO date")
    else:
        reasons += pm.check_freshness(_Observed(retrieved), today)
    return reasons


class _Observed:
    """Adapter so `promotion_manifest.check_freshness` judges a research retrieval date."""

    def __init__(self, day: date):
        self.retrieved_at = datetime(day.year, day.month, day.day)


def retrieved_on(record: dict) -> date | None:
    try:
        return date.fromisoformat(str(record.get("retrieved_at", ""))[:10])
    except ValueError:
        return None


def check_identity(record: dict, robot_json: dict, edition_map: dict | None) -> list[str]:
    """The record is for exactly this robot and edition; a core column is product-level."""
    slug = robot_json["slug"]
    reasons = []
    declared = (edition_map or {}).get(slug)
    if declared is None:
        reasons.append(f"no explicit edition mapping for robot {slug!r}")
    elif declared != record.get("edition"):
        reasons.append(f"edition mapping says {declared!r}, evidence is for "
                       f"{record.get('edition')!r}")
    scope = record.get("edition_scope")
    if scope not in EDITION_SCOPES:
        reasons.append(f"edition_scope {scope!r} is not one of {', '.join(EDITION_SCOPES)}")
    elif scope == "THIS_EDITION" and len(robot_json.get("variants") or []) > 1:
        reasons.append("a core column is product-level: an edition-scoped value on a robot "
                       "with several editions needs review")
    return reasons


def convert(record: dict, core: CoreField) -> tuple[Fraction | None, str, list[str]]:
    """(exact value in the column's unit, conversion text, reasons). Never rounds."""
    stated = str(record["stated_value"]).strip()
    if not _PLAIN_NUMBER.match(stated):
        return None, "", [f"stated value {stated!r} is not a plain number (ranges, separators "
                          "and words need review)"]
    unit = record.get("stated_unit") or None
    if unit not in core.conversions:
        return None, "", [f"stated unit {unit!r} has no exact conversion to "
                          f"{core.unit or 'a count'}"]
    value = Fraction(stated) * core.conversions[unit]
    reasons = []
    if (value / core.step).denominator != 1:
        reasons.append(f"{stated} {unit} is not exact at the column's precision "
                       f"({float(core.step)} {core.unit}); rounding needs review")
    if value <= 0:
        reasons.append("a zero or negative value is not a specification")
    if unit == core.unit:
        return value, "none", reasons
    return value, f"{stated} {unit} = {_literal(value, core)} {core.unit}", reasons


def check_qualifiers(record: dict, core: CoreField) -> list[str]:
    reasons = []
    qualifiers = record.get("qualifiers") or []
    if not isinstance(qualifiers, list):
        return ["qualifiers must be a list"]
    extra = sorted(set(qualifiers) - ALLOWED_QUALIFIERS)
    if extra:
        reasons.append(f"qualifier(s) {', '.join(extra)} change the meaning of the column "
                       "(policy decision, not routine)")
    if core.needs_condition and not str(record.get("measurement_condition") or "").strip():
        reasons.append("speed/runtime needs its measurement condition, or "
                       f"'{NOT_STATED}' when the source states none")
    return reasons


def _literal(value: Fraction, core: CoreField) -> str:
    """The JSON literal for the column: ints for INT columns, at least one decimal otherwise
    (as the catalogue writes NUMERIC columns, e.g. 118.0, 1.0, 1.25)."""
    if core.integer:
        return str(int(value))
    text_ = f"{float(value):.2f}".rstrip("0")
    return text_ + "0" if text_.endswith(".") else text_


def _json_value(value: Fraction, core: CoreField):
    return int(value) if core.integer else float(_literal(value, core))


def caveat_text(item: dict) -> str:
    core = CORE_FIELDS[item["definition"]]
    parts = [f"{item['source_title']} states '{item['verbatim']}'"]
    if "approximately" in item["qualifiers"]:
        parts.append("the figure is stated as approximate")
    if item["conversion"] != "none":
        parts.append(f"{item['proposed_value']} {core.unit} is a unit conversion")
    if core.needs_condition:
        cond = item["measurement_condition"]
        parts.append("no measurement condition is stated" if cond == NOT_STATED
                     else f"stated measurement condition: {cond}")
    parts.append(f"evidence {EVIDENCE_CLASS}, not human-verified")
    return "; ".join(parts) + "."


# --------------------------------------------------------------------------------------- #
# propose
# --------------------------------------------------------------------------------------- #
def _observation(session, content_sha256: str) -> dict:
    """Bind a governed observation when one holds the same bytes (manual capture or crawl)."""
    if session is None or not _SHA256.match(content_sha256 or ""):
        return {"kind": "EVIDENCE_PACKAGE", "fetched_page_id": None}
    row = session.execute(text("SELECT id::text FROM fetched_page WHERE content_hash = :h "
                               "ORDER BY retrieved_at, id LIMIT 1"),
                          {"h": content_sha256}).first()
    return ({"kind": "FETCHED_PAGE", "fetched_page_id": row[0]} if row
            else {"kind": "EVIDENCE_PACKAGE", "fetched_page_id": None})


def propose_research(session, records: list[dict], *, catalogue_dir: Path, base_commit: str,
                     promotion_id: str, today: date, edition_map: dict | None = None,
                     reconsider: bool = False, fingerprints: dict | None = None) -> dict:
    """Build the sealed version-2 manifest for an evidence package. READ-ONLY on `session`."""
    if not records:
        raise pm.ProposalRefused("no records")
    catalogue_dir = Path(catalogue_dir)
    rejected = set() if reconsider else pm.rejected_claim_ids(catalogue_dir)
    robots: dict[str, dict] = {}
    by_slot: dict[tuple, list[dict]] = {}
    unknown: list[str] = []
    for record in records:
        slug, field = str(record.get("robot") or ""), str(record.get("field") or "")
        path = pm.robot_path(catalogue_dir, slug)
        if not slug or not path.exists():
            raise pm.ProposalRefused(f"no catalogue file for robot {slug!r}: research never "
                                     "creates a robot")
        robots.setdefault(slug, json.loads(path.read_text(encoding="utf-8")))
        stated = record.get("stated_value")
        if stated is None or pm._collapse(str(stated)).lower() in pm.UNKNOWN_TOKENS:
            unknown.append(f"{slug} {field}")
            continue
        if evidence_id(record) in rejected:
            raise pm.ProposalRefused(f"evidence {evidence_id(record)} was REJECTED in "
                                     "decisions.json (pass --reconsider to propose it again)")
        by_slot.setdefault((slug, field), []).append(record)
    if unknown:
        raise pm.ProposalRefused("UNKNOWN values are never promoted: " + "; ".join(unknown))
    if not by_slot:
        raise pm.ProposalRefused("no records")

    items = []
    for (slug, field), group in sorted(by_slot.items()):
        values = {pm._collapse(f"{r.get('stated_value')} {r.get('stated_unit') or ''}")
                  for r in group}
        if len(group) > 1 and len(values) == 1:
            raise pm.ProposalRefused(f"{slug}: two records for {field!r}; submit one")
        for record in group:
            items.append(_item(session, record, robots[slug], edition_map, today,
                               disputed=len(values) > 1))

    if fingerprints is None:
        fingerprints = pm.fingerprints_from_connection(
            session.connection().connection.dbapi_connection, sorted(robots))
    restricted_impact = dict.fromkeys(pm.RESTRICTED_IMPACT_KEYS, 0)
    for item in items:
        if item["classification"] == pm.RESTRICTED:
            restricted_impact[pm._impact_key(item)] += 1
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "promotion_id": promotion_id,
        "base": {"catalogue_commit": base_commit, "robot_fingerprints": fingerprints},
        "scope": {"robots": sorted(robots), "allowed_tables": list(ALLOWED_TABLES),
                  "edition_map": dict(edition_map or {})},
        "items": items,
        "restricted_impact": restricted_impact,
        "review_notes": _review_notes(robots, items),
        "generated_on": today.isoformat(),
    }
    return pm.seal(manifest)


def _item(session, record: dict, robot_json: dict, edition_map, today: date,
          disputed: bool) -> dict:
    slug, field = robot_json["slug"], str(record.get("field"))
    core = CORE_FIELDS.get(field)
    restricted = []
    if core is None and pm._RESTRICTED_WORDS.search(field):
        restricted.append(f"{field!r} is a restricted field (price, availability, publication, "
                          "commercial status, image/rights, evidence or deletion)")
    review = check_provenance(record, today) + check_identity(record, robot_json, edition_map)
    value, conversion = None, "none"
    if core is None:
        if not restricted:
            review.append(f"{field!r} is not one of the Fast Lane core columns "
                          f"({', '.join(CORE_FIELDS)})")
    else:
        value, conversion, value_reasons = convert(record, core)
        review += value_reasons + check_qualifiers(record, core)
    specs = robot_json.get("specs") or {}
    existing = specs.get(field)
    if core is not None and field not in specs:
        review.append(f"the robot file has no specs.{field} entry")
    elif existing is not None:
        if value is not None and Fraction(str(existing)) == value:
            raise pm.ProposalRefused(f"{slug}: {field} already has exactly this value")
        review.append(f"catalogue already holds {existing!r}: this is a change, not an "
                      "addition")
    if any(c.get("field") == field for c in robot_json.get("spec_caveats") or []):
        review.append(f"an existing spec caveat for {field} would need editorial change")
    conflicts = [str(c) for c in record.get("conflicting_statements") or []]
    if disputed or conflicts:
        review.append("another statement for the same field disagrees"
                      + (": " + "; ".join(conflicts) if conflicts else ""))
    classification = pm.classify(restricted, review)
    item = {
        "robot": slug,
        "edition": record.get("edition"),
        "edition_scope": record.get("edition_scope"),
        "table": "robot",
        "field": f"specs.{field}",
        "definition": field,
        "unit": core.unit if core else None,
        "existing_value": existing,
        "proposed_value": _json_value(value, core) if core and value is not None else None,
        "stated_value": str(record.get("stated_value")),
        "stated_unit": record.get("stated_unit") or None,
        "conversion": conversion,
        "qualifiers": sorted(record.get("qualifiers") or []),
        "measurement_condition": record.get("measurement_condition") or None,
        "verbatim": record.get("verbatim"),
        "excerpt": record.get("excerpt"),
        "source_title": record.get("source_title"),
        "source_url": record.get("source_url"),
        "content_sha256": record.get("content_sha256"),
        "observed_at": retrieved_on(record).isoformat() if retrieved_on(record) else None,
        "evidence_locator": record.get("locator") or "",
        "retrieval": {k: record.get(k) for k in ("retrieved_at", "retrieval_actor",
                                                  "retrieval_tool", "initiated_by",
                                                  "work_order", "scope")},
        "observation": _observation(session, str(record.get("content_sha256") or "")),
        "claim_id": evidence_id(record),
        "evidence_class": EVIDENCE_CLASS,
        "verification": "NOT_HUMAN_VERIFIED",
        "classification": classification,
        "reasons": restricted + review,
        "conflict": "DISPUTED" if disputed or conflicts else "NONE",
        "expected_change": {"table": "robot", "kind": "CHANGED", "match": {"slug": slug}},
    }
    item["caveat"] = caveat_text(item) if classification == pm.ROUTINE else None
    item["display"] = (f"Robot detail: '{core.label}: {item['proposed_value']}"
                       f"{' ' + core.unit if core.unit else ''}', with caveat"
                       if core and item["proposed_value"] is not None else "")
    return item


def _review_notes(robots: dict[str, dict], items: list[dict]) -> list[str]:
    """Non-blocking: existing note wording that may contradict the new values."""
    notes = []
    for slug in sorted({i["robot"] for i in items if i["classification"] == pm.ROUTINE}):
        note = (robots[slug].get("specs_note") or "").replace(STALE_NOTE, "")
        for sentence in re.split(r"(?<=\.)\s+", note):
            if _CONTRADICTING.search(sentence):
                notes.append(f"{slug}: existing specs_note wording kept verbatim; check it does "
                             f"not contradict the new values: '{sentence.strip()}'")
    return notes


# --------------------------------------------------------------------------------------- #
# The deterministic catalogue edit (text level; nothing else is re-serialised)
# --------------------------------------------------------------------------------------- #
def provenance_note(items: list[dict]) -> str:
    """The docs/26 §3.1 statement (and the sources) for one robot's items, deterministic."""
    by_source: dict[tuple, list[dict]] = {}
    for i in sorted(items, key=lambda i: i["definition"]):
        by_source.setdefault((i["source_title"], i["source_url"], i["content_sha256"]),
                             []).append(i)
    sources = "; ".join(
        f"{', '.join(CORE_FIELDS[i['definition']].label.lower() for i in group)} from "
        f"{title} {url} (sha256 {sha[:16]}…)" for (title, url, sha), group in by_source.items())
    work_orders = sorted({i["retrieval"]["work_order"] for i in items})
    dates = sorted({i["observed_at"] for i in items})
    statements = sorted({
        f"RETRIEVAL: AGENT_ASSISTED_RESEARCH (docs/26) — retrieved {i['observed_at']} by "
        f"{i['retrieval']['retrieval_actor']} ({i['retrieval']['retrieval_tool']}) in a session "
        f"initiated by {i['retrieval']['initiated_by']} for {i['retrieval']['scope']}, under "
        f"research work order {i['retrieval']['work_order']} (docs/26 §2.1). Not a "
        "MANUAL_BOOTSTRAP reading. Not human-verified." for i in items})
    return (f"SPECIFICATIONS ({', '.join(work_orders)}, {', '.join(dates)}): {sources}. "
            + " ".join(statements))


def new_specs_note(original: str | None, items: list[dict]) -> str:
    statement = provenance_note(items)
    note = original or ""
    if statement in note:
        return note                                   # already applied
    if STALE_NOTE in note:
        first = min(items, key=lambda i: (i["observed_at"], i["retrieval"]["work_order"]))
        note = note.replace(STALE_NOTE, _EVIDENCE_STATUS.format(
            date=first["observed_at"], work_order=first["retrieval"]["work_order"]), 1)
    return f"{note} {statement}".strip()


def _matching_brace(text_: str, start: int) -> int:
    depth, i, in_str = 0, start, False
    while i < len(text_):
        ch = text_[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise pm.CatalogueEditRefused("unbalanced braces in the robot JSON")


def edit_robot_core(original: str, items: list[dict]) -> str:
    """Fill `specs.<field>: null`, append the caveats and the provenance note. Idempotent: a
    field already holding exactly the value is skipped; any other value is refused."""
    parsed = json.loads(original)
    marker = re.search(r'^  "specs": \{', original, re.MULTILINE)
    if marker is None:
        raise pm.CatalogueEditRefused("robot JSON has no top-level specs object")
    open_at = marker.end() - 1
    close_at = _matching_brace(original, open_at)
    block = original[open_at:close_at]
    caveats, filled = [], []
    for item in sorted(items, key=lambda i: i["definition"]):
        field, core = item["definition"], CORE_FIELDS[item["definition"]]
        have = (parsed.get("specs") or {}).get(field)
        literal = _literal(Fraction(str(item["proposed_value"])), core)
        entry = {"field": field, "text": item["caveat"]}
        if have is not None:
            if Fraction(str(have)) != Fraction(str(item["proposed_value"])):
                raise pm.CatalogueEditRefused(f"{parsed['slug']}: specs.{field} already holds "
                                              f"{have!r}; refusing to change it")
        else:
            block, n = re.subn(rf'^(    "{field}": )null(,?\r?)$', rf"\g<1>{literal}\g<2>", block,
                               flags=re.MULTILINE)
            if n != 1:
                raise pm.CatalogueEditRefused(f"{parsed['slug']}: specs.{field} is not a "
                                              "single null line")
            filled.append(item)
        existing = [c for c in parsed.get("spec_caveats") or [] if c.get("field") == field]
        if not existing:
            caveats.append(entry)
        elif existing != [entry]:
            raise pm.CatalogueEditRefused(f"{parsed['slug']}: a different caveat for {field} "
                                          "exists; refusing to change it")
    new = original[:open_at] + block + original[close_at:]
    new = pm.edit_robot_text(new, caveats, key="spec_caveats")
    note_match = re.search(r'^  "specs_note": (null|"(?:[^"\\]|\\.)*")(,?\r?)$', new,
                           re.MULTILINE)
    if note_match is None:
        raise pm.CatalogueEditRefused(f"{parsed['slug']}: specs_note is not a single line")
    old_note = json.loads(note_match.group(1))
    note = new_specs_note(old_note, items)
    if note != (old_note or ""):
        new = (new[:note_match.start(1)] + json.dumps(note, ensure_ascii=False)
               + new[note_match.end(1):])
    return new


def planned_edits(manifest: dict, catalogue_dir: Path) -> dict[str, tuple[Path, str, str]]:
    by_robot: dict[str, list[dict]] = {}
    for item in manifest["items"]:
        by_robot.setdefault(item["robot"], []).append(item)
    plans = {}
    for slug, items in sorted(by_robot.items()):
        path = pm.robot_path(catalogue_dir, slug)
        if not path.exists():
            raise pm.CatalogueEditRefused(f"no catalogue file for robot {slug!r}")
        original = path.read_bytes().decode("utf-8")
        new = edit_robot_core(original, items)
        if new != original:
            plans[slug] = (path, original, new)
    return plans


# --------------------------------------------------------------------------------------- #
# Manifest checks, derived artefacts, review
# --------------------------------------------------------------------------------------- #
def manifest_problems(manifest: dict) -> list[str]:
    """Version-2 scope: the robot table, the six core columns, research provenance only."""
    reasons = []
    if manifest.get("scope", {}).get("allowed_tables") != ALLOWED_TABLES:
        reasons.append("scope.allowed_tables must be exactly ['robot']")
    for i in manifest.get("items") or []:
        if i.get("table") != "robot" or i.get("definition") not in CORE_FIELDS \
                or i.get("field") != f"specs.{i.get('definition')}":
            reasons.append(f"{i.get('definition')}: not a core robot column")
        if i.get("evidence_class") != EVIDENCE_CLASS or i.get("verification") != \
                "NOT_HUMAN_VERIFIED":
            reasons.append(f"{i.get('definition')}: provenance must stay {EVIDENCE_CLASS}, "
                           "not human-verified")
        if i.get("existing_value") is not None:
            reasons.append(f"{i.get('definition')}: only NULL -> value additions are routine")
        if not i.get("caveat"):
            reasons.append(f"{i.get('definition')}: no caveat")
    return reasons


def derive_preflight_manifest(manifest: dict) -> dict:
    """One `robot CHANGED` per scoped robot, and nothing else (no spec, offer or evidence row)."""
    return {"_comment": f"derived from promotion {manifest['promotion_id']} "
                        f"(digest {manifest.get('digest', '')[:12]}); version-2 (core columns)",
            "expected": [{"table": "robot", "kind": "CHANGED", "match": {"slug": slug},
                          "count": 1} for slug in manifest["scope"]["robots"]]}


def render_review(manifest: dict) -> str:
    items = manifest["items"]
    lanes = {i["classification"] for i in items}
    classification = pm.ROUTINE if lanes == {pm.ROUTINE} else (
        pm.RESTRICTED if pm.RESTRICTED in lanes else pm.REVIEW_REQUIRED)
    lines = [f"# Catalogue promotion: {manifest['promotion_id']}", "",
             f"**Robots:** {', '.join(manifest['scope']['robots'])}  ",
             f"**Classification:** {classification}  ",
             f"**Evidence:** {EVIDENCE_CLASS} (not human-verified)  ",
             f"**Digest:** `{manifest.get('digest', '')}`  ",
             f"**Base commit:** `{manifest['base']['catalogue_commit']}`  ",
             "**Execution:** not by `promotion execute` (version 2); scoped import gated by "
             "`db/import_preflight.py` after the owner's approval", "",
             "## Core specifications (UNKNOWN -> value)", ""]
    for i in items:
        unit = f" {i['unit']}" if i.get("unit") else ""
        lines.append(f"- **{i['robot']}** `{i['definition']}` ({i['edition']}, "
                     f"{i['edition_scope']}): UNKNOWN -> {i['proposed_value']}{unit}  "
                     f"[{i['classification']}]")
        if i.get("existing_value") is not None:
            lines.append(f"  - catalogue already holds: {i['existing_value']}")
        lines.append(f"  - verbatim: '{i['verbatim']}'")
        if i["conversion"] != "none":
            lines.append(f"  - conversion: {i['conversion']}")
        if i["qualifiers"]:
            lines.append(f"  - qualifiers: {', '.join(i['qualifiers'])}")
        if i.get("measurement_condition"):
            lines.append(f"  - measurement condition: {i['measurement_condition']}")
        if i.get("caveat"):
            lines.append(f"  - caveat: {i['caveat']}")
    lines += ["", "## Evidence", ""]
    for i in items:
        r = i["retrieval"]
        lines.append(f"- {i['robot']} {i['definition']}: {i['source_title']} {i['source_url']} "
                     f"(retrieved {r['retrieved_at']} by {r['retrieval_actor']} via "
                     f"{r['retrieval_tool']}; work order {r['work_order']}; initiated by "
                     f"{r['initiated_by']}; sha256 `{(i['content_sha256'] or '')[:16]}`; "
                     f"observation {i['observation']['kind']}; evidence `{i['claim_id']}`)")
        lines.append(f"  - locator: {i['evidence_locator']}")
    lines += ["", "## Impact", ""]
    if classification == pm.ROUTINE and not any(manifest["restricted_impact"].values()):
        lines.append(f"{len(items)} core value{'s' if len(items) != 1 else ''} filled from "
                     "UNKNOWN on existing robots, with caveats and the docs/26 provenance "
                     "statement in specs_note; no change to known values, offers, evidence "
                     "rows, images, publication or commercial status.")
    else:
        lines.append("See the item reasons below; this manifest does NOT qualify for the fast "
                     "lane.")
    lines.append("")
    for i in items:
        for reason in i.get("reasons", []):
            lines.append(f"- {i['robot']} {i['definition']}: {reason}")
    if manifest.get("review_notes"):
        lines += ["", "## Review notes (non-blocking)", ""]
        lines += [f"- {n}" for n in manifest["review_notes"]]
    lines += ["", "## Decision", "",
              "APPROVE (merge, then the named scoped import) / REJECT / DEFER (close PR with "
              "label)", ""]
    return "\n".join(lines)
