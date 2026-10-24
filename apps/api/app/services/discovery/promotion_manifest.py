"""Approved catalogue promotion: the pinned manifest (workstream B).

docs/discovery/CATALOGUE_PROMOTION_AUTOMATION_DESIGN_2026-10-19.md. A manifest is the reviewed,
digest-pinned description of ONE promotion: which discovered claims become which catalogue
facts, with the exact catalogue edit, the preflight expectations and the review text all
derived from it. Merging the PR that carries it is the single owner approval.

Everything here is pure except `propose` (READ-ONLY queries on the discovery tables and the
production snapshot used for fingerprints) and the file edits of `apply_to_catalogue`.

Design decisions (deviations from the design text are recorded in the PR description):

* The base fingerprint of a robot is the sha256 of the canonical JSON of that robot's
  id-free `import_preflight.snapshot` rows (the robot row, every row whose resolved `robot`
  field is that robot, and its robot-subject evidence), with unresolved UUID values dropped,
  audit/discovery/log tables excluded. It is a fingerprint of the DATABASE, so it detects any
  change to the robot made after review, by anyone, through any path.
* The catalogue edit is a TEXT-level append to the robot's `extended_specs` array. The file is
  never re-serialised, so unrelated formatting and price literals stay byte-identical.
* Only additions can be ROUTINE. A changed value, a conflict, a missing definition, an
  ambiguous edition, an ineligible source, a stale or unhashed observation are all
  REVIEW_REQUIRED; a price/availability/publication/commercial/image/evidence/deletion target
  is RESTRICTED. A value that is a non-value ("/", "-", "") is UNKNOWN and is refused: it never
  becomes 0, false or a made-up string (AGENTS.md rule 6).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text

MANIFEST_VERSION = 1
SUPPORTED_VERSIONS = (1, 2)    # 2 = core robot columns from research (promotion_research)
ROUTINE = "ROUTINE"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
RESTRICTED = "RESTRICTED"
FRESHNESS_WINDOW_DAYS = 30
ALLOWED_TABLES = ["specification"]
RESTRICTED_IMPACT_KEYS = ("prices", "availability", "publication", "commercial_status",
                          "images", "deletions", "unrelated_robots")

#: Values that mean "the source does not say". UNKNOWN stays UNKNOWN (AGENTS.md rule 6).
UNKNOWN_TOKENS = frozenset({"", "/", "-", "--", "—", "–", "n/a", "na", "n.a.",
                            "unknown", "tbd", "tba", "?", "null"})
#: Definition keys / field targets that are never a routine long-tail spec.
_RESTRICTED_WORDS = re.compile(
    r"(pric|cost|msrp|availab|stock|publish|commercial_status|image|photo|licen|rights|"
    r"evidence|retract|delet|lead_time|order)", re.IGNORECASE)

REPO_ROOT = Path(__file__).resolve().parents[5]
PROMOTIONS_SUBDIR = "promotions"


class ProposalRefused(Exception):
    """`propose` cannot produce a manifest for these items (UNKNOWN value, rejected claim...)."""


class CatalogueEditRefused(Exception):
    """The deterministic catalogue edit cannot be applied to this file."""


# --------------------------------------------------------------------------------------- #
# Loading the db/ tools (they are scripts, not a package)
# --------------------------------------------------------------------------------------- #
def load_db_tool(name: str):
    """Fresh module object for db/<name>.py (never shared, so a test or run may patch it)."""
    path = REPO_ROOT / "db" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_promotion_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _research():
    """The version-2 (core columns from research) module; imported late: it imports this one."""
    from app.services.discovery import promotion_research

    return promotion_research


# --------------------------------------------------------------------------------------- #
# Canonical JSON and digest
# --------------------------------------------------------------------------------------- #
def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str)


def compute_digest(manifest: dict) -> str:
    body = {k: v for k, v in manifest.items() if k != "digest"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def seal(manifest: dict) -> dict:
    manifest["digest"] = compute_digest(manifest)
    return manifest


# --------------------------------------------------------------------------------------- #
# The 10 checks (design section 3). Each is pure and returns a list of reasons ([] = pass).
# --------------------------------------------------------------------------------------- #
def check_identity(candidate, robot_id) -> list[str]:
    """1. The claim's candidate is MATCHED_EXISTING to exactly this robot."""
    if candidate is None:
        return ["claim has no candidate"]
    if candidate.identity_status != "MATCHED_EXISTING":
        return [f"candidate identity is {candidate.identity_status}, not MATCHED_EXISTING"]
    if robot_id is None or candidate.possible_robot_id != robot_id:
        return ["candidate is matched to a different robot than the one being promoted"]
    return []


def claim_edition(field_key: str | None) -> str | None:
    found = re.search(r"\[([^\]]+)\]", field_key or "")
    return found.group(1).strip() if found else None


def check_edition(field_key: str | None, item_edition: str | None, robot_slug: str,
                  edition_map: dict | None) -> list[str]:
    """2. The edition in the claim's field key is this robot's own edition, by an explicit
    map. Never inferred from family names."""
    named = claim_edition(field_key)
    if not named:
        return ["claim field key names no edition"]
    if not item_edition:
        return ["item names no edition"]
    reasons: list[str] = []
    if named != item_edition:
        reasons.append(f"claim is for edition {named!r}, item says {item_edition!r}")
    declared = (edition_map or {}).get(robot_slug)
    if declared is None:
        reasons.append(f"no explicit edition mapping for robot {robot_slug!r}")
    elif declared != item_edition:
        reasons.append(f"edition mapping says {declared!r}, item says {item_edition!r}")
    return reasons


def check_source(source, page_url: str | None) -> list[str]:
    """3. The source is enabled and eligible, and the page is inside its approved scope."""
    from app.services.discovery.eligibility import url_ineligibility

    if source is None:
        return ["claim has no discovery source"]
    reasons: list[str] = []
    problem = url_ineligibility(source, page_url) if page_url else "NO_PAGE_URL"
    if problem:
        reasons.append(f"source not eligible for this page: {problem}")
    if getattr(source, "source_class", None) != "MANUFACTURER":
        reasons.append(f"source class is {source.source_class}, not MANUFACTURER")
    return reasons


def check_observation(page) -> list[str]:
    """4. An immutable observation: fetched page with a content hash and a time."""
    if page is None:
        return ["claim has no fetched page"]
    reasons = []
    if not page.content_hash:
        reasons.append("fetched page has no content hash")
    if page.retrieved_at is None:
        reasons.append("fetched page has no retrieval time")
    return reasons


def _collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def check_value(proposed: Any, definition: dict | None, claim_value: str | None,
                interpretation: str | None) -> tuple[Any, list[str], bool]:
    """5. The value normalises under the definition. Returns (normalised, reasons, unknown).

    `unknown` is True for a non-value: the caller refuses it, it never becomes an item."""
    if isinstance(proposed, str) and _collapse(proposed).lower() in UNKNOWN_TOKENS:
        return None, ["value is UNKNOWN (the source states no value)"], True
    if proposed is None:
        return None, ["value is UNKNOWN (none given)"], True
    if definition is None:
        return proposed, [], False        # reported by check_definition
    vtype = definition.get("value_type")
    reasons: list[str] = []
    value = proposed
    if vtype == "TEXT":
        if not isinstance(proposed, str):
            reasons.append("TEXT definition needs a text value")
        elif _collapse(proposed) != proposed:
            reasons.append("text value is not normalised (whitespace)")
    elif vtype == "NUMBER":
        if isinstance(proposed, bool) or not isinstance(proposed, int | float):
            reasons.append("NUMBER definition needs a numeric value")
    elif vtype == "BOOLEAN":
        if not isinstance(proposed, bool):
            reasons.append("BOOLEAN definition needs a true/false value")
    else:
        reasons.append(f"unsupported value_type {vtype!r}")
    if claim_value is not None and not reasons:
        if _collapse(str(claim_value)) != str(proposed) and not (interpretation or "").strip():
            reasons.append("value differs from the claim's and no interpretation is given")
    return value, reasons, False


def check_addition(existing: dict | None, proposed: Any) -> tuple[list[str], str]:
    """6. The catalogue has no value yet. Returns (reasons, state): ADD | SAME | CHANGE."""
    if existing is None:
        return [], "ADD"
    if existing.get("value") == proposed:
        return [], "SAME"
    return ["catalogue already holds a different value: this is a change, not an addition"], \
        "CHANGE"


def check_conflict(claim, other_claims) -> tuple[list[str], str]:
    """7. No other active claim for the same field disagrees. Returns (reasons, conflict)."""
    reasons: list[str] = []
    if claim.claim_status in ("CONFLICT", "REJECTED", "UNKNOWN"):
        reasons.append(f"the claim itself is {claim.claim_status}")
    mine = _collapse(claim.claimed_value or "")
    disagree = sorted({_collapse(c.claimed_value or "") for c in other_claims
                       if c.id != claim.id and c.claim_status != "REJECTED"
                       and _collapse(c.claimed_value or "") != mine})
    if disagree:
        reasons.append("another active claim for the same field disagrees: "
                       + "; ".join(repr(v) for v in disagree))
    return reasons, ("DISPUTED" if reasons else "NONE")


def check_definition(definition: dict | None, key: str) -> list[str]:
    """8. A spec definition exists for the field. A new definition is new semantics."""
    return [] if definition else [f"no spec definition {key!r}: a new definition is new "
                                   "semantics and needs review"]


def check_freshness(page, today: date, window_days: int = FRESHNESS_WINDOW_DAYS) -> list[str]:
    """9. The observation is inside the freshness window."""
    if page is None or page.retrieved_at is None:
        return []                       # reported by check_observation
    age = (today - page.retrieved_at.date()).days
    if age > window_days:
        return [f"observation is {age} days old (window {window_days})"]
    if age < 0:
        return ["observation is dated in the future"]
    return []


def check_restricted(field_target: str, definition_key: str) -> list[str]:
    """10. Not price, availability, publication, commercial status, image/rights, evidence
    withdrawal or deletion."""
    reasons = []
    if not field_target.startswith("extended_specs."):
        reasons.append(f"target {field_target!r} is not a long-tail specification")
    if _RESTRICTED_WORDS.search(definition_key) or _RESTRICTED_WORDS.search(field_target):
        reasons.append(f"{definition_key!r} is a restricted field (price, availability, "
                       "publication, commercial status, image/rights, evidence or deletion)")
    return reasons


def classify(restricted: list[str], review: list[str]) -> str:
    return RESTRICTED if restricted else REVIEW_REQUIRED if review else ROUTINE


# --------------------------------------------------------------------------------------- #
# Catalogue files
# --------------------------------------------------------------------------------------- #
def robot_path(catalogue_dir: Path, slug: str) -> Path:
    return Path(catalogue_dir) / "robots" / f"{slug}.json"


def load_definitions(catalogue_dir: Path) -> dict[str, dict]:
    path = Path(catalogue_dir) / "spec_definitions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {d["key"]: d for d in data["spec_definitions"]}


def _find_spec(robot: dict, key: str, variant_slug: str | None) -> dict | None:
    for entry in robot.get("extended_specs", []) or []:
        if entry.get("key") == key and entry.get("variant_slug") == variant_slug:
            return entry
    return None


def spec_entry(item: dict) -> dict:
    """The exact extended_specs object an item writes."""
    entry: dict[str, Any] = {"key": item["definition"], "value": item["proposed_value"]}
    if item.get("unit"):
        entry["unit"] = item["unit"]
    if item.get("variant_slug"):
        entry["variant_slug"] = item["variant_slug"]
    entry.update({
        "source_label": item["source_label"],
        "source_url": item["source_url"],
        "source_kind": item["evidence_class"],
        "edition_scope": item["edition_scope"],
        "observed_at": item["observed_at"],
    })
    return entry


def _matching_bracket(text_: str, start: int) -> int:
    """Index of the `]` closing the `[` at `start`, skipping JSON strings."""
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
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise CatalogueEditRefused("unbalanced brackets in the robot JSON")


def edit_robot_text(original: str, entries: list[dict], key: str = "extended_specs") -> str:
    """Append `entries` to the robot's `key` array (default extended_specs) without
    re-serialising anything else."""
    if not entries:
        return original
    eol = "\r\n" if "\r\n" in original else "\n"

    def block(entry: dict) -> str:
        body = json.dumps(entry, indent=2, ensure_ascii=False)
        return eol.join("    " + line for line in body.split("\n"))

    new = ("," + eol).join(block(e) for e in entries)
    marker = re.search(rf'^  "{key}": \[', original, re.MULTILINE)
    if marker is None:
        end = original.rstrip().rfind("}")
        if end < 0:
            raise CatalogueEditRefused("robot JSON has no closing brace")
        head = original[:end].rstrip()
        return (head + "," + eol + f'  "{key}": [' + eol + new + eol + "  ]"
                + eol + original[end:])
    open_at = marker.end() - 1
    close_at = _matching_bracket(original, open_at)
    inner = original[open_at + 1:close_at]
    if not inner.strip():
        return original[:open_at + 1] + eol + new + eol + "  " + original[close_at:]
    last = open_at + 1 + len(inner.rstrip())
    return original[:last] + "," + eol + new + original[last:]


def _planned_edits(manifest: dict, catalogue_dir: Path) -> dict[str, tuple[Path, str, str]]:
    """slug -> (path, original_text, new_text) for robots that need an edit. Idempotent: an
    entry already present and identical is skipped; present but different is refused."""
    if manifest.get("manifest_version") == 2:
        return _research().planned_edits(manifest, catalogue_dir)
    by_robot: dict[str, list[dict]] = {}
    for item in manifest["items"]:
        by_robot.setdefault(item["robot"], []).append(item)
    plans = {}
    for slug, items in sorted(by_robot.items()):
        path = robot_path(catalogue_dir, slug)
        if not path.exists():
            raise CatalogueEditRefused(f"no catalogue file for robot {slug!r}")
        original = path.read_bytes().decode("utf-8")
        parsed = json.loads(original)
        to_add = []
        for item in items:
            entry = spec_entry(item)
            have = _find_spec(parsed, item["definition"], item.get("variant_slug"))
            if have is None:
                to_add.append(entry)
            elif have != entry:
                raise CatalogueEditRefused(
                    f"{slug}: extended spec {item['definition']!r} already exists with "
                    "different content; refusing to add or change it")
        if to_add:
            plans[slug] = (path, original, edit_robot_text(original, to_add))
    return plans


def apply_to_catalogue(manifest: dict, catalogue_dir: Path) -> list[str]:
    """Write the manifest's catalogue edit. Returns the slugs changed ([] = already applied)."""
    if any(i["classification"] != ROUTINE for i in manifest["items"]):
        raise CatalogueEditRefused("only an all-ROUTINE manifest has a deterministic edit")
    plans = _planned_edits(manifest, Path(catalogue_dir))
    for path, _old, new in plans.values():
        path.write_bytes(new.encode("utf-8"))
    return sorted(plans)


def expected_catalogue_texts(manifest: dict, base_dir: Path) -> dict[str, str]:
    """Relative path -> expected text of every robot file the manifest edits (pure)."""
    out = {}
    base_dir = Path(base_dir)
    for path, _original, new in _planned_edits(manifest, base_dir).values():
        out[path.relative_to(base_dir).as_posix()] = new
    # an already-present identical entry yields no plan; unchanged files are compared as-is
    return out


# --------------------------------------------------------------------------------------- #
# Fingerprints
# --------------------------------------------------------------------------------------- #
_FP_SKIP_PREFIXES = ("discovery_", "candidate_", "crawl_", "freshness_", "commercial_lead",
                     "buyer_", "match_", "event_", "fetched_", "extraction_", "promotion_",
                     "claim_", "accepted_", "catalogue_write_", "source_eligibility")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def fingerprint_snapshot(snapshot: dict, slug: str) -> str:
    """sha256 over one robot's id-free preflight rows (see module docstring)."""
    rows: list[str] = []
    for table, table_rows in snapshot.items():
        if table.startswith(_FP_SKIP_PREFIXES):
            continue
        for row in table_rows:
            if table == "robot":
                mine = row.get("slug") == slug
            elif table == "evidence_source":
                subject = str(row.get("subject", ""))
                mine = subject == slug or subject.startswith(slug + "|")
            else:
                mine = row.get("robot") == slug
            if not mine:
                continue
            clean = {k: v for k, v in row.items()
                     if not (isinstance(v, str) and _UUID_RE.match(v))}
            rows.append(canonical_json({"t": table, "r": clean}))
    return hashlib.sha256("\n".join(sorted(rows)).encode("utf-8")).hexdigest()


def excluded_tables() -> frozenset[str]:
    """Tables the promotion gates never read: the lead / buyer tables (owner decision: they are
    out of scope of the promotion role, which has no privilege on them). The fingerprint skips
    them anyway (`_FP_SKIP_PREFIXES`), so excluding them changes no fingerprint."""
    return frozenset(load_db_tool("import_preflight").REDACTED_TABLES)


def fingerprints_from_connection(conn, slugs, exclude_tables=None) -> dict[str, str]:
    snap = load_db_tool("import_preflight").snapshot(
        conn, excluded_tables() if exclude_tables is None else exclude_tables)
    return {s: fingerprint_snapshot(snap, s) for s in sorted(slugs)}


def fingerprints_from_url(url: str, slugs, exclude_tables=None) -> dict[str, str]:
    import psycopg

    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1)) as conn:
        conn.read_only = True
        return fingerprints_from_connection(conn, slugs, exclude_tables)


# --------------------------------------------------------------------------------------- #
# Decisions log
# --------------------------------------------------------------------------------------- #
def decisions_path(catalogue_dir: Path) -> Path:
    return Path(catalogue_dir) / PROMOTIONS_SUBDIR / "decisions.json"


def load_decisions(catalogue_dir: Path) -> list[dict]:
    path = decisions_path(catalogue_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("decisions", [])


def rejected_claim_ids(catalogue_dir: Path) -> set[str]:
    return {c for d in load_decisions(catalogue_dir) if d.get("decision") == "REJECT"
            for c in d.get("claim_ids", [])}


def record_decision(catalogue_dir: Path, manifest: dict, decision: str, reason: str, by: str,
                    at: date) -> dict:
    if decision not in ("REJECT", "DEFER"):
        raise ValueError("decision must be REJECT or DEFER")
    if not reason.strip() or not by.strip():
        raise ValueError("a reason and a decider are required")
    path = decisions_path(catalogue_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    decisions = load_decisions(catalogue_dir)
    entry = {"promotion_id": manifest["promotion_id"], "digest": manifest["digest"],
             "decision": decision, "claim_ids": sorted(i["claim_id"] for i in manifest["items"]),
             "reason": reason.strip(), "by": by.strip(), "at": at.isoformat()}
    decisions.append(entry)
    path.write_text(json.dumps({"decisions": decisions}, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return entry


# --------------------------------------------------------------------------------------- #
# propose
# --------------------------------------------------------------------------------------- #
def _compare_peer(session, robot_slug: str, definition: str) -> str | None:
    """A published robot to compare against (a one-robot compare renders no comparison).
    Prefers one that has the same field, so the row appears; deterministic (first by slug)."""
    row = session.execute(text(
        "SELECT r.slug FROM robot r WHERE r.is_published AND r.slug <> :s ORDER BY "
        "EXISTS (SELECT 1 FROM specification x JOIN spec_definition d ON d.id = x.definition_id "
        "WHERE x.robot_id = r.id AND d.key = :k) DESC, r.slug LIMIT 1"),
        {"s": robot_slug, "k": definition}).first()
    return row[0] if row else None


def propose(session, robot_slug: str, items: list[dict], *, catalogue_dir: Path,
            base_commit: str, promotion_id: str, today: date,
            edition_map: dict | None = None, reconsider: bool = False,
            window_days: int = FRESHNESS_WINDOW_DAYS,
            fingerprints: dict | None = None) -> dict:
    """Build the sealed manifest for `items` on `robot_slug`. READ-ONLY on `session`."""
    from app.models.acquisition import FetchedPage
    from app.models.discovery import CandidateClaim, DiscoveryCandidate, DiscoverySource

    if not items:
        raise ProposalRefused("no items")
    catalogue_dir = Path(catalogue_dir)
    robot_file = robot_path(catalogue_dir, robot_slug)
    if not robot_file.exists():
        raise ProposalRefused(f"no catalogue file for robot {robot_slug!r}")
    robot_json = json.loads(robot_file.read_text(encoding="utf-8"))
    definitions = load_definitions(catalogue_dir)
    rejected = set() if reconsider else rejected_claim_ids(catalogue_dir)
    robot_id = session.execute(text("SELECT id FROM robot WHERE slug = :s"),
                               {"s": robot_slug}).scalar()
    seen: set[tuple] = set()
    out_items: list[dict] = []
    unknown: list[str] = []

    for raw in items:
        claim_id = str(raw["claim_id"])
        if claim_id in rejected:
            raise ProposalRefused(f"claim {claim_id} was REJECTED in decisions.json "
                                  "(pass --reconsider to propose it again)")
        claim = session.get(CandidateClaim, claim_id)
        if claim is None:
            raise ProposalRefused(f"claim {claim_id} does not exist")
        key = raw["definition"]
        variant_slug = raw.get("variant_slug")
        if (variant_slug, key) in seen:
            raise ProposalRefused(f"two items for {key!r}")
        seen.add((variant_slug, key))
        candidate = session.get(DiscoveryCandidate, claim.candidate_id)
        source = session.get(DiscoverySource, claim.discovery_source_id)
        page = session.get(FetchedPage, claim.fetched_page_id) if claim.fetched_page_id else None
        others = session.query(CandidateClaim).filter(
            CandidateClaim.field_key == claim.field_key).all()
        definition = definitions.get(key)
        target = raw.get("field") or f"extended_specs.{key}"
        edition = raw.get("edition")

        value, value_reasons, is_unknown = check_value(
            raw.get("proposed_value"), definition, claim.claimed_value,
            raw.get("interpretation"))
        if is_unknown:
            unknown.append(f"{key} (claim {claim_id}): {value_reasons[0]}")
            continue
        existing = _find_spec(robot_json, key, variant_slug)
        addition_reasons, state = check_addition(existing, value)
        if state == "SAME":
            raise ProposalRefused(f"{key!r} already has exactly this value in the catalogue")
        conflict_reasons, conflict = check_conflict(claim, others)

        restricted = check_restricted(target, key)
        review = (check_identity(candidate, robot_id) + check_edition(
            claim.field_key, edition, robot_slug, edition_map) + check_source(
            source, page.url if page else claim.evidence_url) + check_observation(page)
            + value_reasons + addition_reasons + conflict_reasons
            + check_definition(definition, key) + check_freshness(page, today, window_days))
        classification = classify(restricted, review)
        source_url = page.url if page else (claim.evidence_url or "")
        observed = page.retrieved_at.date().isoformat() if page and page.retrieved_at else None
        unit = (definition or {}).get("unit")
        label = (definition or {}).get("label", key)
        expected = {"table": "specification", "kind": "ADDED",
                    "match": {"robot": robot_slug, "definition": key}}
        if variant_slug:
            expected["match"]["variant"] = f"{robot_slug}/{variant_slug}"
        out_items.append({
            "robot": robot_slug,
            "edition": edition,
            "variant_slug": variant_slug,
            "field": target,
            "definition": key,
            "unit": unit,
            "existing_value": existing.get("value") if existing else None,
            "proposed_value": value,
            "claim_value": claim.claimed_value,
            "interpretation": raw.get("interpretation") or "",
            "claim_id": claim_id,
            "claim_field_key": claim.field_key,
            "source_label": (f"{source.name} official page, {edition} column; discovery claim "
                             f"{claim_id[:8]} (verbatim: '{_collapse(claim.claimed_value or '')}')"
                             if source else ""),
            "source_url": source_url,
            "observed_at": observed,
            "content_hash": page.content_hash if page else None,
            "evidence_locator": raw.get("evidence_locator") or "",
            "evidence_class": "MANUFACTURER",
            "edition_scope": "THIS_EDITION",
            "confidence": claim.extraction_confidence,
            "classification": classification,
            "reasons": restricted + review,
            "conflict": conflict,
            "expected_change": expected,
            "display": raw.get("display")
            or f"Robot detail spec table: '{label}: {value}', with source",
            "compare_peer": _compare_peer(session, robot_slug, key),
        })

    if unknown:
        raise ProposalRefused("UNKNOWN values are never promoted: " + "; ".join(unknown))
    if not out_items:
        raise ProposalRefused("no items")
    if fingerprints is None:
        fingerprints = fingerprints_from_connection(
            session.connection().connection.dbapi_connection, [robot_slug])
    restricted_impact = dict.fromkeys(RESTRICTED_IMPACT_KEYS, 0)
    for item in out_items:
        if item["classification"] == RESTRICTED:
            restricted_impact[_impact_key(item)] += 1
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "promotion_id": promotion_id,
        "base": {"catalogue_commit": base_commit, "robot_fingerprints": fingerprints},
        "scope": {"robots": [robot_slug], "allowed_tables": list(ALLOWED_TABLES),
                  "edition_map": dict(edition_map or {})},
        "items": out_items,
        "restricted_impact": restricted_impact,
        "generated_on": today.isoformat(),
    }
    return seal(manifest)


def _impact_key(item: dict) -> str:
    probe = f"{item['field']} {item['definition']}".lower()
    for needle, key in (("pric", "prices"), ("cost", "prices"), ("msrp", "prices"),
                        ("availab", "availability"), ("stock", "availability"),
                        ("publish", "publication"), ("commercial_status", "commercial_status"),
                        ("image", "images"), ("photo", "images"), ("delet", "deletions")):
        if needle in probe:
            return key
    return "publication" if not item["field"].startswith("extended_specs.") else "images"


# --------------------------------------------------------------------------------------- #
# Derived artefacts
# --------------------------------------------------------------------------------------- #
def derive_preflight_manifest(manifest: dict) -> dict:
    """The import_preflight expected-change manifest, derived from the items only."""
    if manifest.get("manifest_version") == 2:
        return _research().derive_preflight_manifest(manifest)
    return {"_comment": f"derived from promotion {manifest['promotion_id']} "
                        f"(digest {manifest.get('digest', '')[:12]})",
            "expected": [{**i["expected_change"], "count": 1} for i in manifest["items"]]}


def expected_added_keys(manifest: dict) -> set[str]:
    """The import_identity_check ADDED lines the manifest predicts."""
    if manifest.get("manifest_version") == 2:
        return set()                     # core columns change the robot row; nothing is added
    return {f"specification {i['robot']}:{i.get('variant_slug') or '-'}|{i['definition']}"
            for i in manifest["items"]}


def render_review(manifest: dict) -> str:
    if manifest.get("manifest_version") == 2:
        return _research().render_review(manifest)
    items = manifest["items"]
    robots = ", ".join(manifest["scope"]["robots"])
    lanes = {i["classification"] for i in items}
    classification = ROUTINE if lanes == {ROUTINE} else (
        RESTRICTED if RESTRICTED in lanes else REVIEW_REQUIRED)
    lines = [f"# Catalogue promotion: {manifest['promotion_id']}", "",
             f"**Robot:** {robots}  ",
             f"**Classification:** {classification}  ",
             f"**Digest:** `{manifest.get('digest', '')}`  ",
             f"**Base commit:** `{manifest['base']['catalogue_commit']}`", "",
             "## New manufacturer facts", ""]
    for i in items:
        shown = i["proposed_value"] if not i.get("unit") else f"{i['proposed_value']} {i['unit']}"
        lines.append(f"- **{i['definition']}** ({i['edition']}): {shown}")
        if i.get("existing_value") is not None:
            lines.append(f"  - replaces existing value: {i['existing_value']}")
        lines.append(f"  - will show as: {i['display']}")
    lines += ["", "## Evidence", ""]
    for i in items:
        lines.append(f"- {i['definition']}: {i['source_url']} (observed {i['observed_at']}; "
                     f"claim `{i['claim_id']}`; page hash `{(i['content_hash'] or '')[:12]}`)")
        if i.get("evidence_locator"):
            lines.append(f"  - locator: {i['evidence_locator']}")
        if i.get("interpretation"):
            lines.append(f"  - interpretation: {i['interpretation']}")
    lines += ["", "## Impact", "",
              f"{len(items)} specification addition{'s' if len(items) != 1 else ''}; no changes "
              "to price, availability, publication, images or unrelated robots." if
              classification == ROUTINE and not any(manifest["restricted_impact"].values())
              else "See the item reasons below; this manifest does NOT qualify for the fast lane.",
              ""]
    for i in items:
        for reason in i.get("reasons", []):
            lines.append(f"- {i['definition']}: {reason}")
    lines += ["", "## Decision", "",
              "APPROVE (merge) / REJECT / DEFER (close PR with label)", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------------------- #
@dataclass
class VerifyResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def _tree(base: Path) -> dict[str, bytes]:
    out = {}
    base = Path(base)
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = p.relative_to(base).as_posix()
            if rel == PROMOTIONS_SUBDIR or rel.startswith(PROMOTIONS_SUBDIR + "/"):
                continue
            out[rel] = p.read_bytes().replace(b"\r\n", b"\n")
    return out


def manifest_problems(manifest: dict) -> list[str]:
    """Every check that needs no catalogue files: version, digest, lane, scope, impact."""
    reasons: list[str] = []
    if manifest.get("manifest_version") not in SUPPORTED_VERSIONS:
        return [f"unsupported manifest_version {manifest.get('manifest_version')!r}"]
    if manifest.get("digest") != compute_digest(manifest):
        reasons.append("digest does not match the manifest content")
    items = manifest.get("items") or []
    if not items:
        reasons.append("manifest has no items")
    for i in items:
        if i.get("classification") != ROUTINE:
            reasons.append(f"{i.get('definition')}: classification is "
                           f"{i.get('classification')}, only ROUTINE may use the fast lane")
        if i.get("conflict") != "NONE":
            reasons.append(f"{i.get('definition')}: conflict is {i.get('conflict')}")
        if not str(i.get("proposed_value", "")).strip() and not isinstance(
                i.get("proposed_value"), bool | int | float):
            reasons.append(f"{i.get('definition')}: empty value")
    impact = manifest.get("restricted_impact", {})
    if any(impact.get(k, 0) for k in RESTRICTED_IMPACT_KEYS) or set(impact) - set(
            RESTRICTED_IMPACT_KEYS):
        reasons.append("restricted impact is not all zero")
    scope = manifest.get("scope", {})
    if manifest["manifest_version"] == 2:
        reasons += _research().manifest_problems(manifest)
    elif scope.get("allowed_tables") != ALLOWED_TABLES:
        reasons.append("scope.allowed_tables must be exactly ['specification']")
    if sorted(scope.get("robots", [])) != sorted({i["robot"] for i in items}):
        reasons.append("scope.robots does not equal the robots named by the items")
    if set(manifest.get("base", {}).get("robot_fingerprints", {})) != set(
            scope.get("robots", [])):
        reasons.append("base.robot_fingerprints must cover exactly the scoped robots")
    return reasons


def verify(manifest: dict, *, base_catalogue_dir: Path, head_catalogue_dir: Path) -> VerifyResult:
    reasons = manifest_problems(manifest)
    if reasons:
        return VerifyResult(False, reasons)
    # The catalogue at head must be exactly base + the manifest's edit.
    try:
        expected_texts = expected_catalogue_texts(manifest, Path(base_catalogue_dir))
    except (CatalogueEditRefused, json.JSONDecodeError, OSError) as exc:
        return VerifyResult(False, [f"manifest edit cannot be applied to the base: {exc}"])
    base_tree, head_tree = _tree(base_catalogue_dir), _tree(head_catalogue_dir)
    for rel, new in expected_texts.items():
        base_tree[rel] = new.encode("utf-8").replace(b"\r\n", b"\n")
    for rel in sorted(set(base_tree) | set(head_tree)):
        if rel not in head_tree:
            reasons.append(f"catalogue file removed: {rel}")
        elif rel not in base_tree:
            reasons.append(f"catalogue file added outside the manifest: {rel}")
        elif base_tree[rel] != head_tree[rel]:
            reasons.append(f"catalogue file differs from base + manifest edit: {rel}")
    return VerifyResult(not reasons, reasons)
