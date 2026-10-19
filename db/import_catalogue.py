#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Import the WS2B verified production catalogue into the canonical schema.

SELF-CONTAINED (no ORM): reads the JSON catalogue under db/catalogue/ and
idempotently loads it into the `humanoid` schema created by db/schema.sql
(via db/bootstrap.py). Safe to run repeatedly — re-running produces no
duplicate rows, no new row ids and no writes.

IDEMPOTENCY MODEL (stable-ID reconciliation)
  - regions, manufacturers, providers, capabilities, use_cases, spec_definitions
    and robots are UPSERTed by their natural key (code / slug). The upsert only
    writes when a column actually differs, so an unchanged row is not rewritten
    and its `updated_at` does not move.
  - A robot's child rows are RECONCILED by natural key, never deleted and
    re-inserted, so a row keeps its id for as long as its key exists:
        robot_variant       (robot, variant slug)
        specification       (robot, variant, spec key)            importer-owned rows
        pricing_offer       (robot, variant, provider, region, transaction_type, condition)
        availability_offer  (same key as pricing_offer)
        deployment          (robot, customer_name, region, started_on)
        robot_image         (robot, image_url)
        robot_capability    (robot, capability)
        use_case_fit        (robot, use case)
        evidence_source     (subject, source_url, source_type, excerpt, observed date)
    Matching is NULL-safe. `is_current`, `price_type` and prices are NOT key
    columns, so a corrected price or a retired offer is an UPDATE in place.
  - Per row: key found and every other column equal -> no statement at all; key
    found and different -> UPDATE that row (same id); key not found -> INSERT.
  - Evidence rows are immutable to the importer: a matched row whose other
    columns differ is refused unless an `update_evidence` authorization names it.
  - FAIL CLOSED. A duplicate natural key in the JSON aborts before anything is
    written. Two database rows on one key abort (the importer never picks one).
    A database row in scope for a selected robot whose key is no longer in the
    JSON is NOT deleted: the run aborts and prints the exact authorization
    entries (table, robot, key) that would permit it. Likewise a protected
    provenance column (image approvals/verification/capture/source/attribution,
    specification source/label/observed date) that the JSON would blank is
    refused unless a `clear` entry names it.
  - Authorization is explicit: `--authorize PATH` takes a JSON file
        {"version": 1, "entries": [{"action": "remove" | "update_evidence" | "clear",
         "table": ..., "robot": <robot slug, or manufacturer slug for company
         evidence>, "key": {...natural key...}, "column": <clear only>}]}
    Nothing is authorized by default, and an entry that matches nothing aborts
    the run (it signals drift). Authorized removals run last, after every
    insert/update; removing a variant that still has a dependent specification,
    pricing_offer or availability_offer not itself being removed is refused.
  - Robots are never deleted. Offer retirement is `is_current` true -> false.
  - Scope of the evidence reconciled: PRICING_OFFER / AVAILABILITY_OFFER /
    DEPLOYMENT evidence under the reconciled rows, COMMERCIAL_STATUS evidence of
    the robot, and MANUFACTURER evidence marked `managed_by = 'CATALOGUE_IMPORT'`
    (migration 0013). Every other evidence row (hand-written ROBOT rows, unmarked
    MANUFACTURER rows) is never touched. Robot-child evidence is still inserted
    unmarked, exactly as before.
  - Every run prints a per-table summary: unchanged / updated / inserted / removed.

MANUFACTURER-ONLY MODE (`--manufacturers-only`)
  Imports manufacturer profiles and their company-level evidence and nothing
  else: robot files are not read, and robots, publication state,
  specifications, offers, capabilities, variants, deployments, images,
  providers, regions and robot-level evidence are not written. The data and its
  source attribution are validated before the transaction opens; the write is a
  single transaction. It is the production rollout path for manufacturer data.

SCOPED IMPORT (`--only <robot>`) IS ROBOT-SCOPED RECONCILIATION
  It reconciles the COMPLETE canonical JSON of the selected robots and what they reference with
  the database; it is not "apply only the newest materialized claims". Evidence and facts in
  those robots' files that production lags behind are synchronized too; unselected robots are
  never touched. Rehearse on a production clone and run `db/import_preflight.py` first
  (db/catalogue/README.md, "Production import preflight").

NULL / UNKNOWN (AGENTS.md rule 6): every field absent or null in the JSON is
written as SQL NULL — never coerced to 0, false or a made-up value.

EVIDENCE (AGENTS.md rule 7): every commercial fact (commercial_status, each
pricing_offer / availability_offer / deployment) carries its evidence_source
row(s), attached polymorphically via (subject_type, subject_id).

Connection: --database-url or $DATABASE_URL (a SQLAlchemy '+psycopg' driver
token is tolerated and stripped).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

import psycopg
from psycopg.types.json import Json

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE_DIR = REPO_ROOT / "db" / "catalogue"
ROBOTS_DIR = CATALOGUE_DIR / "robots"

# Robot columns fed from a robot JSON's flat "specs" object (plus a few top-level
# fields handled separately). Kept explicit for readability (AGENTS.md rule 10).
SPEC_COLUMNS = [
    "height_cm", "weight_kg", "arm_span_cm", "reach_cm", "payload_kg",
    "walk_speed_ms", "runtime_minutes",
    "battery_wh", "mobility", "degrees_of_freedom", "hand_type", "hand_dof",
    "autonomy", "has_manipulation", "has_teleoperation", "has_vision",
    "has_language_ui", "has_sdk", "has_api", "ros_support", "developer_edition",
    "simulation_support",
]

#: Marks the rows this importer OWNS in tables it shares with the seed and with
#: hand authoring (`specification`, `spec_definition`). It refreshes only these;
#: anything else occupying the same logical key is preserved and reported, never
#: overwritten. The catalogue is add-only and does not own what it did not write.
MANAGED_BY = "CATALOGUE_IMPORT"

#: Extra public columns on `pricing_offer` / `availability_offer`: separate facts
#: in separate columns (tax basis, box contents, seller warranty, order status,
#: edition match), so none of them has to be parsed back out of prose.
PRICING_DETAIL_COLUMNS = [
    "price_basis", "shipping_terms", "package_contents", "warranty_terms",
    "order_status_note", "edition_confirmed", "edition_note",
]
#: Offer condition (migration 0024): NEW unless the catalogue entry says otherwise.
OFFER_CONDITIONS = ("NEW", "USED", "OPEN_BOX", "REFURBISHED")


def _condition(offer: dict) -> str:
    value = offer.get("condition", "NEW")
    if value not in OFFER_CONDITIONS:
        raise ValueError(f"offer condition {value!r} is not one of {OFFER_CONDITIONS}")
    return value
AVAILABILITY_DETAIL_COLUMNS = ["seller_wording", "delivery_estimate_label"]


def normalize_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Evidence helper
# --------------------------------------------------------------------------- #
def insert_evidence(cur, subject_type: str, subject_id, ev: dict,
                    *, managed_by: str | None = None) -> None:
    _insert(cur, T_EVIDENCE, _evidence_values(subject_type, subject_id, ev, managed_by))


def _rowcount(result) -> int:
    """Rows affected by the statement just executed (0 when not reported)."""
    count = getattr(result, "rowcount", 0) or 0
    return count if count > 0 else 0


# --------------------------------------------------------------------------- #
# Stable-ID reconciliation machinery
# --------------------------------------------------------------------------- #
class ReconcileRefused(SystemExit):
    """The import was refused because applying it would be ambiguous or destructive.

    Raised inside the import transaction, so nothing is committed.
    """


AUTH_ACTIONS = ("remove", "update_evidence", "clear")
#: Reported in this order; shared entities first, then the robot and its children.
SUMMARY_TABLES = (
    "region", "manufacturer", "provider", "capability", "use_case", "spec_definition",
    "robot", "robot_variant", "specification", "pricing_offer", "availability_offer",
    "deployment", "robot_image", "robot_capability", "use_case_fit", "evidence_source",
)
OUTCOMES = ("unchanged", "updated", "inserted", "removed")
#: Evidence subject type of the tables whose rows carry evidence of their own.
EVIDENCE_SUBJECTS = {
    "pricing_offer": "PRICING_OFFER",
    "availability_offer": "AVAILABILITY_OFFER",
    "deployment": "DEPLOYMENT",
}


def _entry(action: str, table: str, robot: str, key: dict, column: str | None = None) -> dict:
    """An authorization entry, in exactly the form an `--authorize` file holds."""
    entry = {"action": action, "table": table, "robot": robot, "key": key}
    if column is not None:
        entry["column"] = column
    return entry


class Authorization:
    """What the operator has explicitly permitted this run to do (default: nothing)."""

    def __init__(self, entries=()) -> None:
        self.entries: list[dict] = []
        for i, entry in enumerate(entries):
            self.entries.append(self._checked(i, entry))
        self._used = [False] * len(self.entries)

    @staticmethod
    def _checked(i: int, entry) -> dict:
        where = f"authorization entry {i}"
        if not isinstance(entry, dict):
            raise ReconcileRefused(f"{where}: not an object")
        extra = sorted(set(entry) - {"action", "table", "robot", "key", "column"})
        if extra:
            raise ReconcileRefused(f"{where}: unknown field(s) {', '.join(extra)}")
        if entry.get("action") not in AUTH_ACTIONS:
            raise ReconcileRefused(f"{where}: action must be one of {', '.join(AUTH_ACTIONS)}")
        for field in ("table", "robot"):
            if not isinstance(entry.get(field), str) or not entry[field]:
                raise ReconcileRefused(f"{where}: {field} must be a non-empty string")
        if not isinstance(entry.get("key"), dict):
            raise ReconcileRefused(f"{where}: key must be an object")
        if (entry["action"] == "clear") != ("column" in entry):
            raise ReconcileRefused(f"{where}: 'column' is required for, and only for, 'clear'")
        return dict(entry)

    @classmethod
    def load(cls, path) -> Authorization:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return as_authorization(doc, source=str(path))

    def allows(self, entry: dict) -> bool:
        """True when the operator authorized exactly this entry (which is then marked used)."""
        hit = False
        for i, held in enumerate(self.entries):
            if held == entry:
                self._used[i] = True
                hit = True
        return hit

    def unused(self) -> list[dict]:
        return [e for e, used in zip(self.entries, self._used, strict=True) if not used]


def as_authorization(value, source: str = "authorization") -> Authorization:
    """None (nothing authorized), an Authorization, an entries document, or a file path."""
    if value is None:
        return Authorization()
    if isinstance(value, Authorization):
        return value
    if isinstance(value, dict):
        if value.get("version") != 1 or not isinstance(value.get("entries"), list):
            raise ReconcileRefused(
                f'{source}: an authorization file is {{"version": 1, "entries": [...]}}')
        return Authorization(value["entries"])
    return Authorization.load(value)


class Pending(NamedTuple):
    """An authorized removal, executed after every insert and update."""
    table: Table
    row_id: object
    robot: str
    key: dict


class Reconciliation:
    """Counters, refusals and authorized removals for one import run."""

    def __init__(self, authorize=None) -> None:
        self.authorize = as_authorization(authorize)
        self.counts: dict[str, Counter] = {}
        self.refusals: list[tuple[str, dict | None]] = []
        self.pending: list[Pending] = []

    def count(self, table: str, outcome: str, n: int = 1) -> None:
        self.counts.setdefault(table, Counter())[outcome] += n

    def refuse(self, why: str, entry: dict | None = None) -> None:
        self.refusals.append((why, entry))

    def finish(self) -> None:
        """Raise when anything was refused or an authorization matched nothing."""
        for entry in self.authorize.unused():
            self.refuse("authorization entry matched nothing in this run (drift?): "
                        + json.dumps(entry))
        if not self.refusals:
            return
        lines = ["IMPORT REFUSED - nothing was committed:"]
        lines += [f"  - {why}" for why, _ in self.refusals]
        wanted: list[dict] = []
        for _, entry in self.refusals:
            if entry is not None and entry not in wanted:
                wanted.append(entry)
        if wanted:
            lines += ["To permit exactly these changes, an --authorize file would contain:",
                      json.dumps({"version": 1, "entries": wanted}, indent=2)]
        raise ReconcileRefused("\n".join(lines))

    def summary(self) -> str:
        lines = ["Reconciliation summary (unchanged / updated / inserted / removed):"]
        for table in SUMMARY_TABLES:
            c = self.counts.get(table, Counter())
            lines.append(f"  {table:<19} " + " / ".join(f"{c[o]:>4}" for o in OUTCOMES))
        return "\n".join(lines)


class Table:
    """How one reconciled table is read and matched.

    `key` is the natural key in slug terms: (name, SQL expression over alias `t`
    and the joins). Matching on slugs, not ids, keeps the NULL-safe comparison
    trivial and lets a refusal quote the key exactly as the JSON writes it.
    `fixed` are the insert columns an UPDATE never rewrites (the key and the owner).
    `protected` columns may only be blanked with a `clear` authorization.
    """

    def __init__(self, name, key, fixed, *, joins="", id_cols=("id",), peek=None,
                 protected=()) -> None:
        self.name = name
        self.key = key
        self.names = [n for n, _ in key]
        self.fixed = set(fixed)
        self.joins = joins
        self.id_cols = id_cols
        self.protected = protected
        self.peek = dict(peek or {})
        for col in protected:
            self.peek[col] = f"t.{col} IS NOT NULL"


class Existing(NamedTuple):
    row_id: object
    key: tuple
    peek: dict


_V = "LEFT JOIN robot_variant v ON v.id = t.variant_id"
_PROVIDER = "(SELECT p.slug FROM provider p WHERE p.id = t.provider_id)"
_REGION = "(SELECT g.code FROM region g WHERE g.id = t.region_id)"
_OFFER_KEY = [
    ("variant_slug", "v.slug"),
    ("provider_slug", _PROVIDER),
    ("region_code", _REGION),
    ("transaction_type", "t.transaction_type::text"),
    ("condition", "t.condition::text"),
]
_OFFER_FIXED = ("robot_id", "variant_id", "provider_id", "region_id", "transaction_type",
                "condition")

T_VARIANT = Table("robot_variant", [("slug", "t.slug")], ("robot_id", "slug"))
T_SPEC = Table(
    "specification",
    [("variant_slug", "v.slug"), ("key", "d.key")],
    ("robot_id", "variant_id", "definition_id"),
    joins=_V + " JOIN spec_definition d ON d.id = t.definition_id",
    peek={"managed_by": "coalesce(t.managed_by, 'seed/hand-authored')"},
    protected=("source_url", "source_label", "observed_at"),
)
T_PRICING = Table("pricing_offer", _OFFER_KEY, _OFFER_FIXED, joins=_V)
T_AVAILABILITY = Table("availability_offer", _OFFER_KEY, _OFFER_FIXED, joins=_V)
T_DEPLOYMENT = Table(
    "deployment",
    [("customer_name", "t.customer_name"), ("region_code", _REGION),
     ("started_on", "t.started_on::text")],
    ("robot_id", "customer_name", "region_id", "started_on"),
)
T_IMAGE = Table(
    "robot_image", [("image_url", "t.image_url")], ("robot_id", "image_url"),
    peek={"is_primary": "t.is_primary"},
    protected=("display_approved_by", "display_approved_at", "last_verified_at",
               "captured_at", "source_url", "attribution"),
)
T_CAPABILITY = Table(
    "robot_capability",
    [("capability_slug", "(SELECT c.slug FROM capability c WHERE c.id = t.capability_id)")],
    ("robot_id", "capability_id"), id_cols=("robot_id", "capability_id"),
)
T_FIT = Table(
    "use_case_fit",
    [("use_case_slug", "(SELECT u.slug FROM use_case u WHERE u.id = t.use_case_id)")],
    ("robot_id", "use_case_id"), id_cols=("robot_id", "use_case_id"),
)
T_EVIDENCE = Table(
    "evidence_source",
    [("source_url", "t.source_url"), ("source_type", "t.source_type::text"),
     ("excerpt", "t.excerpt"), ("observed_at", "t.observed_at::date::text")],
    ("subject_type", "subject_id", "source_url", "source_type", "excerpt", "observed_at",
     "managed_by"),
)


def _param(value):
    """Floats become exact decimals, so a NUMERIC column is never compared as float8."""
    return Decimal(str(value)) if isinstance(value, float) else value


def _day(value) -> str | None:
    return None if value is None else str(value)[:10]


def _id_where(table: Table) -> str:
    return " AND ".join(f"{c} = %s" for c in table.id_cols)


def _id_params(table: Table, row_id) -> tuple:
    return tuple(row_id) if len(table.id_cols) > 1 else (row_id,)


def _load_existing(cur, table: Table, where: str, params: tuple) -> list[Existing]:
    exprs = [f"t.{c}" for c in table.id_cols] + [e for _, e in table.key]
    exprs += list(table.peek.values())
    n_id, n_key = len(table.id_cols), len(table.key)
    rows = cur.execute(
        f"SELECT {', '.join(exprs)} FROM {table.name} t {table.joins} WHERE {where}", params
    ).fetchall()
    out = []
    for r in rows:
        row_id = r[0] if n_id == 1 else tuple(r[:n_id])
        peek = dict(zip(table.peek, r[n_id + n_key:], strict=True))
        out.append(Existing(row_id, tuple(r[n_id:n_id + n_key]), peek))
    return out


def _insert(cur, table: Table, values: dict):
    cols = list(values)
    row = cur.execute(
        f"INSERT INTO {table.name} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
        f"RETURNING {', '.join(table.id_cols)}",
        [_param(v) for v in values.values()],
    ).fetchone()
    return row[0] if len(table.id_cols) == 1 else tuple(row)


def _differs(cur, table: Table, row_id, values: dict) -> bool:
    """Let Postgres compare, so numerics, dates, timestamps and arrays use the column types."""
    if not values:
        return False
    cols = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    return cur.execute(
        f"SELECT ({cols}) IS DISTINCT FROM ({marks}) FROM {table.name} WHERE {_id_where(table)}",
        [*(_param(v) for v in values.values()), *_id_params(table, row_id)],
    ).fetchone()[0]


def _update(cur, table: Table, row_id, values: dict) -> None:
    sets = ", ".join(f"{c} = %s" for c in values)
    cur.execute(
        f"UPDATE {table.name} SET {sets} WHERE {_id_where(table)}",
        [*(_param(v) for v in values.values()), *_id_params(table, row_id)],
    )


def reconcile_rows(cur, recon: Reconciliation, table: Table, robot: str,
                   existing: list[Existing], incoming: list[tuple[tuple, dict]], *,
                   parent: dict | None = None, immutable: bool = False) -> list[tuple]:
    """Bring one robot's rows of one table in line with the JSON, keeping row ids.

    `incoming` is [(natural key, insert-column values)]. Returns [(row id, inserted)]
    aligned with `incoming`. Per row: no match -> INSERT; match and equal -> nothing;
    match and different -> UPDATE in place. Rows present but absent from the JSON are
    never deleted here: each becomes a refusal naming its exact key, or, when the
    operator authorized it, a pending removal executed after everything else.
    `immutable` rows (evidence) are not updated without an `update_evidence` entry.
    """
    def key_dict(key):
        return {**(parent or {}), **dict(zip(table.names, key, strict=True))}

    def where(key):
        return f"{table.name} of {robot} {json.dumps(key_dict(key))}"

    seen: set = set()
    for key, _ in incoming:
        if key in seen:
            raise ReconcileRefused(f"duplicate natural key in the JSON: {where(key)}")
        seen.add(key)
    by_key: dict[tuple, list[Existing]] = {}
    for row in existing:
        by_key.setdefault(row.key, []).append(row)
    for key, rows in by_key.items():
        if len(rows) > 1:
            raise ReconcileRefused(
                f"ambiguous: {len(rows)} existing rows share one natural key, "
                f"{where(key)}; the importer will not choose one")

    results: list[tuple] = []
    for key, values in incoming:
        match = by_key.get(key)
        if match is None:
            results.append((_insert(cur, table, values), True))
            recon.count(table.name, "inserted")
            continue
        row = match[0]
        results.append((row.row_id, False))
        changeable = {c: v for c, v in values.items() if c not in table.fixed}
        blocked = False
        for col in table.protected:
            if changeable.get(col) is None and row.peek.get(col):
                entry = _entry("clear", table.name, robot, key_dict(key), col)
                if not recon.authorize.allows(entry):
                    recon.refuse(f"{where(key)}: the JSON would blank protected column {col}",
                                 entry)
                    blocked = True
        if blocked:
            continue
        if not _differs(cur, table, row.row_id, changeable):
            recon.count(table.name, "unchanged")
            continue
        if immutable:
            entry = _entry("update_evidence", table.name, robot, key_dict(key))
            if not recon.authorize.allows(entry):
                recon.refuse(f"{where(key)}: evidence differs from the JSON but is immutable "
                             "to the importer", entry)
                continue
        _update(cur, table, row.row_id, changeable)
        recon.count(table.name, "updated")

    for key, rows in by_key.items():
        if key in seen:
            continue
        entry = _entry("remove", table.name, robot, key_dict(key))
        if recon.authorize.allows(entry):
            recon.pending.append(Pending(table, rows[0].row_id, robot, key_dict(key)))
        else:
            recon.refuse(f"{where(key)}: in the database but no longer in the JSON "
                         "(the importer never deletes without authorization)", entry)
    return results


def apply_removals(cur, recon: Reconciliation) -> None:
    """Execute the authorized removals, last. Offers are retired with is_current, not here."""
    pending, recon.pending = recon.pending, []
    removing = {(p.table.name, p.row_id) for p in pending}
    for p in pending:
        if p.table is not T_VARIANT:
            continue
        for dependent in ("specification", "pricing_offer", "availability_offer"):
            for (dep_id,) in cur.execute(
                f"SELECT id FROM {dependent} WHERE variant_id = %s", (p.row_id,)
            ).fetchall():
                if (dependent, dep_id) not in removing:
                    recon.refuse(
                        f"cannot remove robot_variant {json.dumps(p.key)} of {p.robot}: "
                        f"{dependent} {dep_id} still depends on it and is not itself "
                        "being removed (the delete would cascade)")
    if recon.refusals:
        return
    # Rows first, their variant last.
    for p in sorted(pending, key=lambda p: p.table is T_VARIANT):
        subject = EVIDENCE_SUBJECTS.get(p.table.name)
        if subject:
            gone = _rowcount(cur.execute(
                "DELETE FROM evidence_source WHERE subject_type = %s AND subject_id = %s",
                (subject, p.row_id)))
            recon.count("evidence_source", "removed", gone)
        cur.execute(f"DELETE FROM {p.table.name} WHERE {_id_where(p.table)}",
                    _id_params(p.table, p.row_id))
        recon.count(p.table.name, "removed")


def _evidence_key(ev: dict) -> tuple:
    return (ev.get("source_url"), ev["source_type"], ev.get("excerpt"),
            _day(ev.get("observed_at")))


def _evidence_values(subject_type: str, subject_id, ev: dict, managed_by: str | None) -> dict:
    return {
        "subject_type": subject_type, "subject_id": subject_id,
        "source_url": ev.get("source_url"), "source_type": ev["source_type"],
        "source_title": ev.get("source_title"), "excerpt": ev.get("excerpt"),
        "published_at": ev.get("published_at"), "observed_at": ev.get("observed_at"),
        "verified_at": ev.get("verified_at"), "confidence": ev.get("confidence", "MEDIUM"),
        "note": ev.get("note"),
        # MANUFACTURER rows name the profile fields they support (migration
        # 0013); every other row makes no field claim.
        "claim_fields": ev.get("claim_fields"), "managed_by": managed_by,
    }


def reconcile_evidence(cur, recon: Reconciliation, robot: str, subject_type: str, subject_id,
                       evidence: list[dict], parent: dict, *, managed_by: str | None = None,
                       fresh: bool = False) -> None:
    """Reconcile the evidence under one (stable) subject. `fresh`: the subject was just
    inserted, so it cannot have evidence yet. With `managed_by`, only rows carrying that
    marker are in scope."""
    existing: list[Existing] = []
    if not fresh:
        where, params = "t.subject_type = %s AND t.subject_id = %s", (subject_type, subject_id)
        if managed_by is not None:
            where, params = where + " AND t.managed_by = %s", params + (managed_by,)
        existing = _load_existing(cur, T_EVIDENCE, where, params)
    incoming = [(_evidence_key(ev), _evidence_values(subject_type, subject_id, ev, managed_by))
                for ev in evidence]
    reconcile_rows(cur, recon, T_EVIDENCE, robot, existing, incoming,
                   parent={"subject_type": subject_type, **parent}, immutable=True)


def _upsert(cur, table: str, conflict: str, cols: list[str], vals: list, *,
            skip=(), set_exprs=None, only_if: str | None = None, only_if_params=()):
    """INSERT ... ON CONFLICT DO UPDATE that rewrites a row only if a column differs.

    Returns (id, inserted), or None when the row exists and nothing would change
    (an UPDATE that changes nothing still fires updated_at triggers, so none is issued)."""
    set_exprs = set_exprs or {}
    changing = [c for c in cols if c != conflict and c not in skip]
    new = {c: set_exprs.get(c, f"EXCLUDED.{c}") for c in changing}
    guard = (f"({', '.join(f'{table}.{c}' for c in changing)}) "
             f"IS DISTINCT FROM ({', '.join(new.values())})")
    if only_if:
        guard = f"{only_if} AND {guard}"
    row = cur.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET "
        f"{', '.join(f'{c} = {new[c]}' for c in changing)} WHERE {guard} "
        "RETURNING id, (xmax = 0)",
        [*vals, *only_if_params],
    ).fetchone()
    return None if row is None else (row[0], row[1])


def _upsert_entity(cur, recon: Reconciliation, table: str, conflict: str, cols: list[str],
                   vals: list, **kw):
    """`_upsert` for a table the importer owns outright: always returns the row id."""
    row = _upsert(cur, table, conflict, cols, vals, **kw)
    if row is None:
        recon.count(table, "unchanged")
        return cur.execute(
            f"SELECT id FROM {table} WHERE {conflict} = %s", (vals[cols.index(conflict)],)
        ).fetchone()[0]
    recon.count(table, "inserted" if row[1] else "updated")
    return row[0]


# --------------------------------------------------------------------------- #
# Manufacturer profiles: validation and company-level evidence ownership
# --------------------------------------------------------------------------- #
#: Company facts that must be attributed to an evidence row whenever they are
#: asserted (docs/03 §8). `website_url` may be claimed but predates attribution.
MANUFACTURER_ATTRIBUTED_FIELDS = (
    "legal_name", "country_region_code", "headquarters_city", "incorporation",
    "operating_locations", "founded_year", "description", "target_markets",
    "commercial_model", "deployment_status", "deployment_note",
    "is_public_company", "ticker", "parent_company", "parent_listing",
    "parent_relationship",
)
MANUFACTURER_CLAIMABLE_FIELDS = frozenset(MANUFACTURER_ATTRIBUTED_FIELDS) | {"website_url"}
COMMERCIAL_STATUSES = frozenset({
    "UNKNOWN", "ANNOUNCED", "DEVELOPMENT", "PROTOTYPE", "PILOT", "EARLY_ACCESS",
    "LIMITED_COMMERCIAL", "COMMERCIAL", "RAAS_DEPLOYMENT", "DISCONTINUED",
})
SOURCE_TYPES = frozenset({
    "MANUFACTURER_STORE", "MANUFACTURER_SITE", "PRESS_RELEASE", "NEWS_ARTICLE",
    "ANALYST_REPORT", "FINANCIAL_FILING", "DIRECT_QUOTE", "CONFERENCE",
    "INTERVIEW", "OTHER",
})
CONFIDENCE_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH", "VERIFIED"})
#: docs/26 §3.1 fixed provenance statement prefix.
AGENT_RETRIEVAL_PREFIX = "RETRIEVAL: AGENT_ASSISTED_RESEARCH"
#: Printed for an unmarked company-evidence row sharing a catalogue source's
#: URL, type and observed date. Deliberately says nothing about who wrote it.
EVIDENCE_COLLISION_LABEL = "EVIDENCE COLLISION (unmarked row preserved, ownership not assumed)"


def _asserted(m: dict, field: str) -> bool:
    value = m.get(field)
    if value is None or value == [] or value == "":
        return False
    # UNKNOWN is the explicit absence of a status claim (docs/03 §7).
    return not (field == "deployment_status" and value == "UNKNOWN")


def validate_manufacturer_profiles(data: dict) -> list[str]:
    """Every reason `manufacturers.json` must not be written, or [] when clean.

    Pure (no database): the vocabularies, the three-state listing rule and the
    source-attribution rule `db/validate_catalogue.py` enforces after an import,
    checked BEFORE one, so an invalid profile never reaches a transaction.
    """
    rows = data.get("manufacturers")
    if not isinstance(rows, list) or not rows:
        return ["manufacturers.json has no non-empty 'manufacturers' list"]

    errors: list[str] = []
    seen: set[str] = set()
    for i, m in enumerate(rows):
        slug = m.get("slug")
        where = slug if isinstance(slug, str) and slug.strip() else f"manufacturers[{i}]"
        if where != slug:
            errors.append(f"{where}: missing slug")
        elif slug in seen:
            errors.append(f"{slug}: duplicate slug")
        else:
            seen.add(slug)
        if not isinstance(m.get("name"), str) or not m["name"].strip():
            errors.append(f"{where}: missing name")

        status = m.get("deployment_status")
        if status is not None and status not in COMMERCIAL_STATUSES:
            errors.append(f"{where}: deployment_status {status!r} is not a commercial_status")
        listed = m.get("is_public_company")
        if listed not in (True, False, None):
            errors.append(f"{where}: is_public_company must be true, false or null")
        if m.get("ticker") and listed is not True:
            errors.append(f"{where}: ticker given for an entity not recorded as listed")
        has_parent_detail = m.get("parent_listing") or m.get("parent_relationship")
        if has_parent_detail and not m.get("parent_company"):
            errors.append(f"{where}: parent listing/relationship without parent_company")
        year = m.get("founded_year")
        if year is not None and (isinstance(year, bool) or not isinstance(year, int)
                                 or not 1900 <= year <= 2100):
            errors.append(f"{where}: founded_year {year!r} outside 1900-2100")
        for field in ("operating_locations", "target_markets"):
            value = m.get(field)
            if value is not None and not (
                isinstance(value, list) and all(isinstance(v, str) for v in value)
            ):
                errors.append(f"{where}: {field} must be a list of strings")

        claimed: set[str] = set()
        for j, ev in enumerate(m.get("evidence") or []):
            at = f"{where} evidence[{j}]"
            if ev.get("source_type") not in SOURCE_TYPES:
                errors.append(f"{at}: source_type {ev.get('source_type')!r} is not a source_type")
            if ev.get("confidence", "MEDIUM") not in CONFIDENCE_LEVELS:
                errors.append(
                    f"{at}: confidence {ev.get('confidence')!r} is not a confidence_level"
                )
            if not ev.get("observed_at"):
                errors.append(f"{at}: missing observed_at")
            fields = ev.get("claim_fields")
            if fields is not None:
                if not isinstance(fields, list) or any(
                    f not in MANUFACTURER_CLAIMABLE_FIELDS for f in fields
                ):
                    errors.append(f"{at}: claim_fields names an unknown profile field")
                else:
                    claimed |= set(fields)
            if (ev.get("note") or "").startswith(AGENT_RETRIEVAL_PREFIX) and ev.get("verified_at"):
                errors.append(f"{at}: agent-assisted research row marked verified")

        unattributed = [f for f in MANUFACTURER_ATTRIBUTED_FIELDS
                        if _asserted(m, f) and f not in claimed]
        if unattributed:
            errors.append(f"{where}: asserted but no evidence row claims: "
                          + ", ".join(unattributed))
    return errors


def manufacturer_key_problems(data: dict) -> list[str]:
    """A natural key (source, type, excerpt, observed date) given twice for one manufacturer.

    Pure. Checked before any write, so an ambiguous catalogue never reaches a transaction."""
    out: list[str] = []
    for m in data.get("manufacturers", []):
        keys = [_evidence_key(ev) for ev in m.get("evidence") or []
                if "source_type" in ev]
        out += [f"manufacturer {m.get('slug')!r}: duplicate evidence key {k}"
                for k, n in Counter(keys).items() if n > 1]
    return out


def reconcile_manufacturer_evidence(cur, recon: Reconciliation, manufacturer_slug: str,
                                    manufacturer_id, evidence: list[dict]) -> dict:
    """Reconcile ONE manufacturer's company-level evidence without touching rows this
    importer does not own.

    * `managed_by = CATALOGUE_IMPORT` rows are the importer's. They are matched by
      (source_url, source_type, excerpt, observed date): equal rows are left alone
      (same id, no write), new sources are inserted with that marker, and a managed
      row whose source left the JSON is never deleted without a `remove`
      authorization. A matched row whose content differs is refused unless an
      `update_evidence` entry names it.
    * Every UNMARKED row is preserved exactly as it is: content, ownership and
      subject. The importer never deletes, rewrites or takes ownership of one.
      Row content says nothing reliable about who wrote a row, so even an
      unmarked row identical to a catalogue source is left alone; the
      catalogue's own marked copy is maintained separately beside it.
    * An unmarked row that shares a catalogue source's URL, type and observed
      date (whether its other content matches or not) is reported as a
      collision. The report asserts no ownership; resolving it is an owner
      decision, never an import side effect.
    """
    before = Counter(recon.counts.get("evidence_source", Counter()))
    collisions: list[str] = []
    for ev in evidence:
        shared = cur.execute(
            """
            SELECT count(*) FROM evidence_source
            WHERE subject_type='MANUFACTURER' AND subject_id=%s AND managed_by IS NULL
              AND source_url IS NOT DISTINCT FROM %s AND source_type = %s
              AND observed_at::date IS NOT DISTINCT FROM %s::date
            """,
            (manufacturer_id, ev.get("source_url"), ev["source_type"], ev.get("observed_at")),
        ).fetchone()[0]
        if shared:
            collisions.append(
                f"{ev.get('source_url')} ({shared} unmarked row(s) share its URL, type "
                "and observed date; preserved, ownership not assumed)"
            )
    reconcile_evidence(cur, recon, manufacturer_slug, "MANUFACTURER", manufacturer_id,
                       evidence, {}, managed_by=MANAGED_BY)
    apply_removals(cur, recon)
    after = recon.counts.get("evidence_source", Counter())
    delta = {o: after[o] - before[o] for o in OUTCOMES}
    return {**delta, "collisions": collisions}


# --------------------------------------------------------------------------- #
# Catalogue-level entities (upsert by natural key)
# --------------------------------------------------------------------------- #
def import_regions(cur, data: dict, recon: Reconciliation | None = None) -> None:
    recon = recon or Reconciliation()
    rows = data["regions"]
    # Parents first so parent_code can resolve.
    for row in sorted(rows, key=lambda r: r.get("parent_code") is not None):
        parent_id = None
        if row.get("parent_code"):
            parent_id = cur.execute(
                "SELECT id FROM region WHERE code = %s", (row["parent_code"],)
            ).fetchone()[0]
        _upsert_entity(
            cur, recon, "region", "code",
            ["parent_id", "type", "code", "name", "iso_country"],
            [parent_id, row["type"], row["code"], row["name"], row.get("iso_country")],
        )


def import_manufacturers(cur, data: dict, region_id, recon: Reconciliation | None = None) -> dict:
    """Upsert manufacturer profiles by slug and reconcile their company evidence.

    Shared by the full catalogue import and `--manufacturers-only`, so both write
    manufacturer data identically. Returns summed evidence counts and every
    evidence collision with an unmarked row (`slug: source_url (...)`).
    Called without a shared `recon`, it finishes (and may refuse) on its own.
    """
    own = recon is None
    recon = recon or Reconciliation()
    totals: dict = {"manufacturers": 0, "removed": 0, "inserted": 0, "updated": 0,
                    "unchanged": 0, "collisions": []}
    for m in data["manufacturers"]:
        mid = _upsert_entity(
            cur, recon, "manufacturer", "slug",
            ["slug", "name", "legal_name", "country_region_id", "headquarters_city",
             "incorporation", "operating_locations", "website_url", "founded_year",
             "description", "target_markets", "commercial_model", "deployment_status",
             "deployment_note", "is_public_company", "ticker", "parent_company",
             "parent_listing", "parent_relationship"],
            [
                m["slug"], m["name"], m.get("legal_name"),
                region_id(m.get("country_region_code")), m.get("headquarters_city"),
                m.get("incorporation"), m.get("operating_locations"), m.get("website_url"),
                m.get("founded_year"), m.get("description"), m.get("target_markets"),
                m.get("commercial_model"), m.get("deployment_status"),
                m.get("deployment_note"),
                # No default: a missing key is NULL (listing status unknown), never
                # FALSE. FALSE is a claim and needs a source (validate_catalogue).
                m.get("is_public_company"), m.get("ticker"),
                m.get("parent_company"), m.get("parent_listing"),
                m.get("parent_relationship"),
            ],
        )
        # Reconcile only this importer's own company evidence: idempotent, and
        # manually maintained rows survive (see reconcile_manufacturer_evidence).
        counts = reconcile_manufacturer_evidence(
            cur, recon, m["slug"], mid, m.get("evidence") or [])
        totals["manufacturers"] += 1
        for key in ("removed", "inserted", "updated", "unchanged"):
            totals[key] += counts[key]
        totals["collisions"].extend(f"{m['slug']}: {line}" for line in counts["collisions"])
    if own:
        recon.finish()
    return totals


def import_providers(cur, data: dict, region_id, manufacturer_id,
                     recon: Reconciliation | None = None) -> None:
    recon = recon or Reconciliation()
    for p in data["providers"]:
        _upsert_entity(
            cur, recon, "provider", "slug",
            ["slug", "type", "name", "manufacturer_id", "country_region_id",
             "website_url", "description"],
            [
                p["slug"], p["type"], p["name"],
                manufacturer_id(p.get("manufacturer_slug")),
                region_id(p.get("country_region_code")),
                p.get("website_url"), p.get("description"),
            ],
        )


def import_capabilities(cur, data: dict, recon: Reconciliation | None = None) -> None:
    recon = recon or Reconciliation()
    for c in data["capabilities"]:
        _upsert_entity(
            cur, recon, "capability", "slug",
            ["slug", "name", "category", "description"],
            [c["slug"], c["name"], c["category"], c.get("description")],
        )


def import_use_cases(cur, data: dict, recon: Reconciliation | None = None) -> None:
    recon = recon or Reconciliation()
    for u in data["use_cases"]:
        _upsert_entity(
            cur, recon, "use_case", "slug",
            ["slug", "name", "category", "description", "typical_tasks",
             "typical_requirements", "key_limitations"],
            [u["slug"], u["name"], u.get("category"), u.get("description"),
             u.get("typical_tasks"), u.get("typical_requirements"),
             u.get("key_limitations")],
            # a file that omits these never clears a value already recorded
            set_exprs={
                "typical_requirements": "COALESCE(EXCLUDED.typical_requirements, "
                                        "use_case.typical_requirements)",
                "key_limitations": "COALESCE(EXCLUDED.key_limitations, use_case.key_limitations)",
            },
        )


def import_spec_definitions(cur, data: dict, collisions: list[str],
                            recon: Reconciliation | None = None) -> None:
    """Upsert the long-tail spec keys this catalogue uses — its OWN ones only.

    `spec_definition` is shared with `db/seed/seed.sql`, which authors keys like
    `swappable_battery` with its own labels, units and `is_filterable` flags. A
    blanket UPSERT would let the catalogue quietly redefine a key it does not
    own, changing the meaning of every existing value pointing at it. So the
    UPDATE is conditional on `managed_by = MANAGED_BY`: an unmanaged definition
    keeps its own shape and is reported. The catalogue may still *reference* it —
    only redefining it is refused.
    """
    recon = recon or Reconciliation()
    for d in data["spec_definitions"]:
        row = _upsert(
            cur, "spec_definition", "key",
            ["key", "label", "category", "value_type", "unit", "is_filterable",
             "sort_order", "managed_by"],
            [d["key"], d["label"], d.get("category", "OTHER"), d["value_type"],
             d.get("unit"), d.get("is_filterable", False), d.get("sort_order", 0),
             MANAGED_BY],
            skip=("managed_by",),
            only_if="spec_definition.managed_by = %s", only_if_params=(MANAGED_BY,),
        )
        if row is not None:
            recon.count("spec_definition", "inserted" if row[1] else "updated")
            continue
        # Nothing was written: either the definition is ours and unchanged, or the
        # conflicting row exists but is not ours. Keep theirs, and say so.
        owner = cur.execute(
            "SELECT coalesce(managed_by, 'seed/hand-authored') FROM spec_definition WHERE key = %s",
            (d["key"],),
        ).fetchone()[0]
        if owner == MANAGED_BY:
            recon.count("spec_definition", "unchanged")
            continue
        collisions.append(
            f"spec_definition {d['key']!r} already exists and is owned by "
            f"{owner} — its definition was preserved, not overwritten"
        )


# --------------------------------------------------------------------------- #
# Robots (+ children). Upsert the robot by slug; reconcile its children by natural key.
# --------------------------------------------------------------------------- #
# Columns the importer owns outright: catalogue FACTS, refreshed from JSON on
# every run. `is_published` is deliberately NOT among them — see below.
EDITORIAL_COLUMNS = ("is_published",)

# Verified product images (MEDIA-01). Provenance is mandatory and a synthesized
# identity image is categorically rejected — `source_type` must be a real-source
# enum value; GENERATED (or anything outside the enum) aborts the import rather
# than silently degrading. Display eligibility is decided at read time by
# identity_status + rights_status, never by the mere presence of image_url.
_ALLOWED_IMAGE_SOURCES = {
    "MANUFACTURER", "PRESS_KIT", "DISTRIBUTOR", "EDITORIAL", "VIDEO_FRAME",
}


def _offer_key(offer: dict) -> tuple:
    return (offer.get("variant_slug"), offer.get("provider_slug"), offer.get("region_code"),
            offer["transaction_type"], _condition(offer))


def _spec_key(spec: dict) -> tuple:
    return (spec.get("variant_slug"), spec["key"])


def _deployment_key(d: dict) -> tuple:
    started = d.get("started_on")
    return (d.get("customer_name"), d.get("region_code"),
            None if started is None else str(started))


def incoming_problems(robot: dict) -> list[str]:
    """Everything in one robot's JSON that makes reconciliation ambiguous. Pure.

    A natural key given twice, a variant reference that resolves to nothing (it
    would silently widen a variant-scoped fact to the whole product), or two
    primary images. Checked before any write."""
    slug = robot.get("slug")
    out: list[str] = []

    def duplicates(label: str, keys: list) -> None:
        out.extend(f"robot {slug!r}: duplicate {label} {k!r} in the JSON"
                   for k, n in Counter(keys).items() if n > 1)

    variants = robot.get("variants", [])
    offers = robot.get("pricing_offers", [])
    availability = robot.get("availability_offers", [])
    deployments = robot.get("deployments", [])
    duplicates("variant", [v["slug"] for v in variants])
    duplicates("extended spec", [_spec_key(x) for x in robot.get("extended_specs", [])])
    duplicates("pricing offer", [_offer_key(o) for o in offers])
    duplicates("availability offer", [_offer_key(o) for o in availability])
    duplicates("deployment", [_deployment_key(d) for d in deployments])
    duplicates("image", [i["image_url"] for i in robot.get("images", [])])
    duplicates("capability", [c["slug"] for c in robot.get("capabilities", [])])
    duplicates("use-case fit", [f["use_case_slug"] for f in robot.get("use_case_fits", [])])
    if sum(1 for i in robot.get("images", []) if i.get("is_primary")) > 1:
        out.append(f"robot {slug!r}: more than one primary image in the JSON")

    known = {v["slug"] for v in variants}
    for x in robot.get("extended_specs", []):
        vs = x.get("variant_slug")
        # An extended spec may identify ONE of this robot's own variants (G2-3, DR-A5);
        # absent or null it is a product-level spec. An unknown slug fails loudly,
        # never silently widening a variant-scoped fact to the whole product.
        if vs is not None and vs not in known:
            out.append(f"robot {slug!r}: extended spec {x['key']!r} names variant "
                       f"{vs!r}, which is not one of its variants")
    for label, rows in (("pricing offer", offers), ("availability offer", availability)):
        for o in rows:
            vs = o.get("variant_slug")
            if vs is not None and vs not in known:
                out.append(f"robot {slug!r}: {label} names variant {vs!r}, which is not "
                           "one of its variants")

    evidence_lists = [("commercial_status_evidence", robot.get("commercial_status_evidence", []))]
    for label, rows, key in (("pricing offer", offers, _offer_key),
                             ("availability offer", availability, _offer_key),
                             ("deployment", deployments, _deployment_key)):
        evidence_lists += [(f"{label} {key(r)!r} evidence", r.get("evidence", [])) for r in rows]
    for label, evs in evidence_lists:
        duplicates(f"evidence key in {label}", [_evidence_key(e) for e in evs])
    return out


def import_robot(cur, robot: dict, region_id, manufacturer_id,
                 capability_id, use_case_id, spec_definition=None,
                 collisions=None, *,
                 apply_publication_state: bool = False,
                 authorize=None, recon: Reconciliation | None = None) -> None:
    """Upsert one robot and reconcile its children by natural key.

    The master catalogue (what we know about a robot) and the public catalogue
    (what is currently approved for display) are two different things. This
    importer owns the first and must not silently rewrite the second: a routine
    fact refresh must never change what the public sees. So `is_published` is
    written when the row is FIRST created and preserved on every later import,
    unless a deliberate publishing operation opts in via
    `apply_publication_state`.

    Without this, `is_published` behaves like disposable importer-controlled
    data: stub entries carry `"is_published": false`, so any editorial decision
    to display them is silently reverted by the next import. That is exactly how
    46 stored robots once collapsed to 7 on screen.

    Children keep their ids (see the module docstring). Anything that would need a
    delete, or blank protected provenance, or change an evidence row, is refused
    unless `authorize` names it. `recon` is shared by `run()`; called alone, this
    function finishes (and may refuse) by itself.
    """
    own = recon is None
    recon = recon or Reconciliation(authorize)
    slug = robot["slug"]
    problems = incoming_problems(robot)
    if problems:
        raise ReconcileRefused("IMPORT REFUSED - nothing was written:\n  " + "\n  ".join(problems))
    extended = robot.get("extended_specs", [])
    # `spec_definition`/`collisions` default to None so a caller inspecting the
    # robot upsert alone (the publication-state tests do exactly this) need not
    # build a definition registry. They become required the moment there is
    # actually a long-tail spec to write: writing one without a registry is
    # impossible, and silently DROPPING it would lose an attributed fact. So
    # their absence fails loudly here rather than quietly skipping the loop.
    if extended and (spec_definition is None or collisions is None):
        raise ValueError(
            f"robot {slug!r} carries {len(extended)} extended_specs, which "
            "require both `spec_definition` and `collisions`"
        )

    specs = robot.get("specs", {})
    caveats = robot.get("spec_caveats")
    cols = ["slug", "manufacturer_id", "name", "model_code", "summary",
            "announced_year", "official_url", "spec_caveats",
            "commercial_status", "is_published"] + SPEC_COLUMNS
    vals = [
        slug, manufacturer_id(robot["manufacturer_slug"]), robot["name"],
        robot.get("model_code"), robot.get("summary"), robot.get("announced_year"),
        # The maker's page for this model, and the per-field caveats explaining
        # UNKNOWNs/conflicts. Both were carried by the JSON and dropped for want
        # of a column until migration 0011.
        robot.get("official_url"), Json(caveats) if caveats else None,
        # Absent maturity means UNVERIFIED, not ANNOUNCED: an omitted key must
        # not become a factual claim the file never made.
        robot.get("commercial_status", "UNKNOWN"), robot.get("is_published", False),
    ] + [specs.get(c) for c in SPEC_COLUMNS]

    # On INSERT every column is written: a brand-new record has no editorial
    # state to preserve. On UPDATE the editorial columns are held back. A row
    # whose columns all already match is not rewritten at all.
    preserved = () if apply_publication_state else EDITORIAL_COLUMNS
    row = _upsert(cur, "robot", "slug", cols, vals, skip=preserved)
    if row is None:
        robot_id = cur.execute("SELECT id FROM robot WHERE slug = %s", (slug,)).fetchone()[0]
        robot_outcome = "unchanged"
    else:
        robot_id, robot_outcome = row[0], "inserted" if row[1] else "updated"

    def reconcile(table, incoming, existing=None):
        if existing is None:
            existing = _load_existing(cur, table, "t.robot_id = %s", (robot_id,))
        return reconcile_rows(cur, recon, table, slug, existing, incoming)

    def reconcile_subject_evidence(subject_type, table, rows, incoming, got):
        for r, (key, _), (subject_id, fresh) in zip(rows, incoming, got, strict=True):
            parent = dict(zip(table.names, key, strict=True))
            reconcile_evidence(cur, recon, slug, subject_type, subject_id,
                               r.get("evidence", []), parent, fresh=fresh)

    # Variants first: their ids are what the variant-scoped rows below point at.
    variants = robot.get("variants", [])
    got = reconcile(T_VARIANT, [
        ((v["slug"],), {"robot_id": robot_id, "slug": v["slug"], "name": v["name"],
                        "description": v.get("description"),
                        "is_developer": v.get("is_developer", False)})
        for v in variants])
    variant_id = {v["slug"]: r[0] for v, r in zip(variants, got, strict=True)}

    def vid_of(variant_slug):
        return variant_id[variant_slug] if variant_slug else None

    # Long-tail specs. Each carries its own attribution and edition scope: these
    # values have no evidence_source row (they are descriptive, not commercial
    # facts), so provenance travels with the value or it does not exist at all.
    # `specification` is NOT wholly owned here: the seed and hand authoring write
    # rows to the same table. Only this importer's own rows are reconciled; a row
    # of anyone else's occupying a key is preserved and reported, never overwritten.
    spec_rows = _load_existing(cur, T_SPEC, "t.robot_id = %s", (robot_id,))
    foreign = {r.key: r.peek["managed_by"] for r in spec_rows
               if r.peek["managed_by"] != MANAGED_BY}
    incoming = []
    for x in extended:
        key = _spec_key(x)
        if key in foreign:
            collisions.append(
                f"robot {slug!r}: specification {x['key']!r} already exists "
                f"and is owned by {foreign[key]} — the catalogue value was skipped, "
                f"the existing row preserved"
            )
            continue
        definition_id, value_type = spec_definition(x["key"])
        value = x.get("value")
        incoming.append((key, {
            "robot_id": robot_id, "variant_id": vid_of(x.get("variant_slug")),
            "definition_id": definition_id,
            "value_number": value if value_type == "NUMBER" else None,
            "value_bool": value if value_type == "BOOLEAN" else None,
            "value_text": value if value_type == "TEXT" else None,
            "unit": x.get("unit"), "managed_by": MANAGED_BY,
            "source_label": x.get("source_label"), "source_url": x.get("source_url"),
            "source_kind": x.get("source_kind"), "edition_scope": x.get("edition_scope"),
            "observed_at": x.get("observed_at"),
        }))
    reconcile(T_SPEC, incoming,
              existing=[r for r in spec_rows if r.peek["managed_by"] == MANAGED_BY])

    # Pricing offers. A retired offer keeps its row and its evidence; it simply stops
    # being current (is_current is not part of the key). `edition_confirmed` stays
    # tri-state: absent in the JSON means NOT ASSESSED (NULL), never "confirmed".
    pricing = robot.get("pricing_offers", [])
    incoming = [(_offer_key(po), {
        "robot_id": robot_id, "variant_id": vid_of(po.get("variant_slug")),
        "provider_id": _provider(cur, po.get("provider_slug")),
        "region_id": region_id(po.get("region_code")),
        "transaction_type": po["transaction_type"], "price_type": po["price_type"],
        "currency": po.get("currency", "USD"), "price": po.get("price"),
        "price_min": po.get("price_min"), "price_max": po.get("price_max"),
        "billing_period": po.get("billing_period", "ONE_TIME"), "note": po.get("note"),
        "is_current": po.get("is_current", True),
        **{c: po.get(c) for c in PRICING_DETAIL_COLUMNS},
        "condition": _condition(po),
    }) for po in pricing]
    got = reconcile(T_PRICING, incoming)
    reconcile_subject_evidence("PRICING_OFFER", T_PRICING, pricing, incoming, got)

    # Availability offers.
    availability = robot.get("availability_offers", [])
    incoming = [(_offer_key(ao), {
        "robot_id": robot_id, "variant_id": vid_of(ao.get("variant_slug")),
        "provider_id": _provider(cur, ao.get("provider_slug")),
        "region_id": region_id(ao.get("region_code")),
        "transaction_type": ao["transaction_type"],
        "availability_status": ao.get("availability_status", "ON_REQUEST"),
        "available_from": ao.get("available_from"), "lead_time_days": ao.get("lead_time_days"),
        "min_order_qty": ao.get("min_order_qty"), "note": ao.get("note"),
        "is_current": ao.get("is_current", True),
        **{c: ao.get(c) for c in AVAILABILITY_DETAIL_COLUMNS},
        "condition": _condition(ao),
    }) for ao in availability]
    got = reconcile(T_AVAILABILITY, incoming)
    reconcile_subject_evidence("AVAILABILITY_OFFER", T_AVAILABILITY, availability, incoming, got)

    # Deployments.
    deployments = robot.get("deployments", [])
    incoming = [(_deployment_key(d), {
        "robot_id": robot_id, "provider_id": _provider(cur, d.get("provider_slug")),
        "customer_name": d.get("customer_name"), "region_id": region_id(d.get("region_code")),
        "use_case_id": use_case_id(d.get("use_case_slug")),
        "transaction_type": d.get("transaction_type"), "unit_count": d.get("unit_count"),
        "contract_value": d.get("contract_value"),
        "contract_currency": d.get("contract_currency"),
        "started_on": d.get("started_on"), "status": d.get("status"),
        "summary": d.get("summary"),
    }) for d in deployments]
    got = reconcile(T_DEPLOYMENT, incoming)
    reconcile_subject_evidence("DEPLOYMENT", T_DEPLOYMENT, deployments, incoming, got)

    # Verified product images (MEDIA-01; see _ALLOWED_IMAGE_SOURCES).
    incoming = []
    for im in robot.get("images", []):
        src = im.get("source_type")
        if src not in _ALLOWED_IMAGE_SOURCES:
            raise ValueError(
                f"robot {slug!r}: illegal image source_type {src!r} "
                f"(MEDIA-01 forbids generated/synthesized identity imagery; "
                f"allowed: {sorted(_ALLOWED_IMAGE_SOURCES)})"
            )
        incoming.append(((im["image_url"],), {
            "robot_id": robot_id, "image_url": im["image_url"],
            "source_url": im.get("source_url"), "source_name": im.get("source_name"),
            "source_type": src, "image_type": im.get("image_type", "FRONT"),
            "identity_status": im.get("identity_status", "UNVERIFIED"),
            "rights_status": im.get("rights_status", "UNKNOWN"),
            "usage_basis": im.get("usage_basis", "NONE"),
            "is_official": im.get("is_official", False),
            "is_primary": im.get("is_primary", False), "attribution": im.get("attribution"),
            "is_representative": im.get("is_representative", False),
            "representative_note": im.get("representative_note"),
            "display_approved_by": im.get("display_approved_by"),
            "display_approved_at": im.get("display_approved_at"),
            "captured_at": im.get("captured_at"), "last_verified_at": im.get("last_verified_at"),
        }))
    images = _load_existing(cur, T_IMAGE, "t.robot_id = %s", (robot_id,))
    # At most one primary image per robot (uq_robot_image_primary). Clear an old primary
    # that is leaving before the new one is set; rows that stay are updated non-primary
    # first, so the index can never fire.
    incoming_keys = {k for k, _ in incoming}
    if any(v["is_primary"] for _, v in incoming):
        for old in images:
            if old.peek["is_primary"] and old.key not in incoming_keys:
                cur.execute("UPDATE robot_image SET is_primary = false WHERE id = %s",
                            (old.row_id,))
    reconcile(T_IMAGE, sorted(incoming, key=lambda kv: kv[1]["is_primary"]), existing=images)

    # Capabilities.
    reconcile(T_CAPABILITY, [
        ((c["slug"],), {"robot_id": robot_id, "capability_id": capability_id(c["slug"]),
                        "supported": c.get("supported", True), "detail": c.get("detail")})
        for c in robot.get("capabilities", [])])

    # Use-case fits (subjective fits carry LOW/MEDIUM confidence in the JSON note).
    reconcile(T_FIT, [
        ((f["use_case_slug"],), {
            "robot_id": robot_id, "use_case_id": use_case_id(f["use_case_slug"]),
            "fit_score": f.get("fit_score"), "is_primary": f.get("is_primary", False),
            "commercial_readiness": f.get("commercial_readiness"),
            "notes": f.get("notes"), "limitations": f.get("limitations")})
        for f in robot.get("use_case_fits", [])])

    # Commercial-status evidence (subject = the robot row).
    reconcile_evidence(cur, recon, slug, "COMMERCIAL_STATUS", robot_id,
                       robot.get("commercial_status_evidence", []), {})

    # Authorized removals run last, after every insert and update.
    apply_removals(cur, recon)

    # Denormalised lowest purchase price cache (source of truth stays pricing_offer).
    if _refresh_lowest_price(cur, robot_id) and robot_outcome == "unchanged":
        robot_outcome = "updated"
    recon.count("robot", robot_outcome)
    if own:
        recon.finish()


def _provider(cur, slug):
    if not slug:
        return None
    row = cur.execute("SELECT id FROM provider WHERE slug = %s", (slug,)).fetchone()
    if not row:
        raise SystemExit(f"unknown provider slug referenced: {slug!r}")
    return row[0]


def _refresh_lowest_price(cur, robot_id) -> bool:
    """Set robot.lowest_purchase_price to the cheapest current PUBLIC/FROM PURCHASE
    point price, else NULL. Denormalised cache only (schema comment). Writes only when
    the cached value or currency actually changes; returns whether it did."""
    row = cur.execute(
        """
        SELECT price, currency FROM pricing_offer
        WHERE robot_id = %s AND is_current
          -- A listing whose edition does not match this record is a qualified
          -- listing: it may be shown, but it never sets this robot's price.
          -- NULL (not assessed) keeps its existing behaviour.
          AND edition_confirmed IS DISTINCT FROM FALSE
          -- NEW only: a used / open-box / refurbished price never sets the robot's price.
          AND condition = 'NEW'
          AND transaction_type = 'PURCHASE'
          AND price_type IN ('PUBLIC','FROM') AND price IS NOT NULL
        ORDER BY price ASC LIMIT 1
        """,
        (robot_id,),
    ).fetchone()
    wanted = (row[0], row[1]) if row else (None, None)
    cached = cur.execute(
        "SELECT lowest_purchase_price, lowest_price_currency FROM robot WHERE id = %s",
        (robot_id,),
    ).fetchone()
    if tuple(cached[:2]) == wanted:
        return False
    cur.execute(
        "UPDATE robot SET lowest_purchase_price=%s, lowest_price_currency=%s WHERE id=%s",
        (*wanted, robot_id),
    )
    return True


class UnknownSlugs(SystemExit):
    """`--only` named robot slugs the catalogue does not contain."""


def select_robot_files(only: set[str] | None) -> list[Path]:
    """The robot files this run will import.

    `None` (the default) is every file — unchanged behaviour. A non-empty
    allowlist is validated against the catalogue HERE, before any connection is
    opened, so an unknown slug can never be discovered halfway through a
    partially written import.
    """
    available = {p.stem: p for p in sorted(ROBOTS_DIR.glob("*.json"))}
    if only is None:
        return list(available.values())
    unknown = sorted(only - set(available))
    if unknown:
        raise UnknownSlugs(
            "unknown robot slug(s) in --only: " + ", ".join(unknown)
            + f" (catalogue has {len(available)} records)"
        )
    return [available[s] for s in sorted(only)]


def _ancestors(regions: dict, codes: set[str]) -> set[str]:
    """Referenced region codes plus every `parent_code` above them.

    A scoped import must not create a region whose parent is absent: `DE`
    without `EU` would break the applicability walk the catalogue depends on.
    """
    by_code = {r["code"]: r for r in regions["regions"]}
    out: set[str] = set()
    frontier = list(codes)
    while frontier:
        code = frontier.pop()
        if code in out or code not in by_code:
            continue
        out.add(code)
        parent = by_code[code].get("parent_code")
        if parent:
            frontier.append(parent)
    return out


def scoped_dependencies(robots: list[dict], regions: dict) -> dict[str, set[str]]:
    """Shared entities the SELECTED records actually reference.

    Restricting the shared upserts to these is what keeps a scoped import
    scoped: without it, importing one robot would still rewrite every
    manufacturer, provider, capability, use case and spec definition in the
    catalogue — rows belonging to robots the caller did not select.
    """
    deps: dict[str, set[str]] = {
        "manufacturers": set(), "providers": set(), "regions": set(),
        "capabilities": set(), "use_cases": set(), "spec_definitions": set(),
    }
    for r in robots:
        if r.get("manufacturer_slug"):
            deps["manufacturers"].add(r["manufacturer_slug"])
        for kind in ("pricing_offers", "availability_offers", "deployments"):
            for row in r.get(kind) or []:
                if row.get("provider_slug"):
                    deps["providers"].add(row["provider_slug"])
                if row.get("region_code"):
                    deps["regions"].add(row["region_code"])
        for c in r.get("capabilities") or []:
            slug = c.get("capability_slug") or c.get("slug")
            if slug:
                deps["capabilities"].add(slug)
        for f in r.get("use_case_fits") or []:
            if f.get("use_case_slug"):
                deps["use_cases"].add(f["use_case_slug"])
        for x in r.get("extended_specs") or []:
            deps["spec_definitions"].add(x["key"])
    # A provider may be owned by a manufacturer the selection does not name.
    deps["regions"] = _ancestors(regions, deps["regions"])
    return deps


def _narrow(data: dict, key: str, field: str, keep: set[str]) -> dict:
    """The same payload shape, carrying only the entries `keep` names."""
    return {key: [row for row in data[key] if row.get(field) in keep]}


# --------------------------------------------------------------------------- #
def _check_publication_transitions(cur, loaded: list[dict], was_published: dict) -> None:
    """G4-3 (DR-G4 section 8.3): refuse an `is_published` false -> true flip that would make the
    public record misleading. INTEGRITY blocks; COVERAGE never does (UNKNOWN fields, a missing price,
    detail-only knowledge, low coverage ... are reported as warnings and the robot still publishes).
    Raising here aborts the whole transaction: nothing is written and nothing is published."""
    transitioning = sorted(
        r["slug"] for r in loaded
        if r.get("is_published") is True and was_published.get(r["slug"]) is not True)
    if not transitioning:
        return
    sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
    from app.services import readiness as rd
    from app.services.readiness_loader import load_records

    baseline = CATALOGUE_DIR / "legacy_readiness_baseline.json"
    legacy = rd.load_legacy_baseline(
        baseline.read_text(encoding="utf-8") if baseline.exists() else None)
    blocked = False
    for rec in load_records(cur, set(transitioning)):
        blockers = rd.publication_check(rec, legacy=legacy)
        coverage = rd.coverage_audit(rec, legacy=legacy)
        warnings = [f for f in coverage.findings if f.severity == rd.WARN]
        print(f"PUBLICATION CHECK {rec.slug}: "
              + ("integrity PASS" if not blockers else "integrity FAIL")
              + f"; coverage {coverage.band} ({len(coverage.findings)} non-blocking finding(s))")
        for f in blockers:
            print(f"  BLOCK {f.code}: {f.message}")
        for f in warnings:
            print(f"  warn  {f.code}: {f.message}")
        blocked = blocked or bool(blockers)
    if blocked:
        raise SystemExit(
            "PUBLICATION REFUSED (integrity): fix the BLOCK findings above. Nothing was written. "
            "Incomplete is publishable; misleading is not.")


def run(url: str, *, apply_publication_state: bool = False,
        only: set[str] | None = None, authorize=None) -> Reconciliation:
    """Import the catalogue (or the `only` robots) in ONE transaction and return the
    reconciliation (its counters). `authorize` is an Authorization, an entries document
    or an `--authorize` file path; the default authorizes nothing."""
    recon = Reconciliation(authorize)
    regions = _load(CATALOGUE_DIR / "regions.json")
    providers = _load(CATALOGUE_DIR / "providers.json")
    capabilities = _load(CATALOGUE_DIR / "capabilities.json")
    use_cases = _load(CATALOGUE_DIR / "use_cases.json")
    spec_definitions = _load(CATALOGUE_DIR / "spec_definitions.json")
    manufacturers = _load(CATALOGUE_DIR / "manufacturers.json")

    # Validated BEFORE the connection opens: an unknown slug aborts with nothing
    # written, and the filter is applied before any robot or child-row mutation.
    robot_files = select_robot_files(only)
    loaded = [_load(p) for p in robot_files]
    # Ambiguity in the JSON itself (a natural key given twice) aborts before anything
    # is written, and before a connection is opened.
    problems = manufacturer_key_problems(manufacturers) + [
        line for robot in loaded for line in incoming_problems(robot)]
    if problems:
        raise ReconcileRefused(
            "IMPORT REFUSED - nothing was written:\n  " + "\n  ".join(problems))

    if only is not None:
        deps = scoped_dependencies(loaded, regions)
        # A provider's own manufacturer must exist before the provider upsert
        # resolves `manufacturer_slug`.
        provider_rows = [p for p in providers["providers"] if p["slug"] in deps["providers"]]
        deps["manufacturers"] |= {
            p["manufacturer_slug"] for p in provider_rows if p.get("manufacturer_slug")
        }
        manufacturer_rows = [
            m for m in manufacturers["manufacturers"] if m["slug"] in deps["manufacturers"]
        ]
        deps["regions"] |= _ancestors(regions, {
            m["country_region_code"] for m in manufacturer_rows
            if m.get("country_region_code")
        } | {
            p["country_region_code"] for p in provider_rows if p.get("country_region_code")
        })
        regions = _narrow(regions, "regions", "code", deps["regions"])
        manufacturers = {"manufacturers": manufacturer_rows}
        providers = {"providers": provider_rows}
        capabilities = _narrow(capabilities, "capabilities", "slug", deps["capabilities"])
        use_cases = _narrow(use_cases, "use_cases", "slug", deps["use_cases"])
        spec_definitions = _narrow(
            spec_definitions, "spec_definitions", "key", deps["spec_definitions"]
        )

    with psycopg.connect(url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO humanoid, public")

            # Resolver closures backed by simple per-key lookups.
            def region_id(code):
                if not code:
                    return None
                r = cur.execute("SELECT id FROM region WHERE code=%s", (code,)).fetchone()
                if not r:
                    raise SystemExit(f"unknown region code referenced: {code!r}")
                return r[0]

            def manufacturer_id(slug):
                if not slug:
                    return None
                r = cur.execute("SELECT id FROM manufacturer WHERE slug=%s", (slug,)).fetchone()
                if not r:
                    raise SystemExit(f"unknown manufacturer slug referenced: {slug!r}")
                return r[0]

            def capability_id(slug):
                r = cur.execute("SELECT id FROM capability WHERE slug=%s", (slug,)).fetchone()
                if not r:
                    raise SystemExit(f"unknown capability slug referenced: {slug!r}")
                return r[0]

            def use_case_id(slug):
                if not slug:
                    return None
                r = cur.execute("SELECT id FROM use_case WHERE slug=%s", (slug,)).fetchone()
                if not r:
                    raise SystemExit(f"unknown use_case slug referenced: {slug!r}")
                return r[0]

            def spec_definition(key):
                """(id, value_type) for a long-tail spec key. The value_type decides
                which of value_number/value_bool/value_text carries the value, so a
                definition and its values can never disagree about their own type."""
                r = cur.execute(
                    "SELECT id, value_type FROM spec_definition WHERE key=%s", (key,)
                ).fetchone()
                if not r:
                    raise SystemExit(f"unknown spec_definition key referenced: {key!r}")
                return r[0], r[1]

            collisions: list[str] = []

            import_regions(cur, regions, recon)
            manufacturer_totals = import_manufacturers(cur, manufacturers, region_id, recon)
            import_providers(cur, providers, region_id, manufacturer_id, recon)
            import_capabilities(cur, capabilities, recon)
            import_use_cases(cur, use_cases, recon)
            import_spec_definitions(cur, spec_definitions, collisions, recon)

            # G4-3: which robots are about to go from NOT published to published? Captured BEFORE
            # the import so the transition is judged against what the public sees today.
            was_published = (
                dict(cur.execute("SELECT slug, is_published FROM robot").fetchall())
                if apply_publication_state else {}
            )

            n_robots = 0
            for robot in loaded:
                import_robot(cur, robot, region_id, manufacturer_id,
                             capability_id, use_case_id, spec_definition, collisions,
                             apply_publication_state=apply_publication_state, recon=recon)
                n_robots += 1

            # Refusals and unused authorizations abort here, inside the transaction:
            # nothing above is committed.
            recon.finish()

            if apply_publication_state:
                _check_publication_transitions(cur, loaded, was_published)

            stored, displayed = cur.execute(
                "SELECT count(*), count(*) FILTER (WHERE is_published) FROM robot"
            ).fetchone()

        conn.commit()

    if only is not None:
        print(f"SCOPED IMPORT — {n_robots} selected record(s): "
              + ", ".join(sorted(only)))
    print(f"Catalogue import OK: {len(manufacturers['manufacturers'])} manufacturers, "
          f"{len(providers['providers'])} providers, {n_robots} robots.")
    # Stored vs displayed, always reported: the master catalogue is cumulative,
    # the public view is a subset of it, and a surprising gap should be visible
    # the moment it appears rather than discovered later in a browser.
    print(f"Catalogue state: {stored} stored, {displayed} displayed.")
    # Preserved, not silently skipped: a collision means someone else's row held a
    # key this catalogue also describes, and their row won. Saying so is the point.
    for line in collisions:
        print(f"PRESERVED (not overwritten): {line}")
    if collisions:
        print(f"{len(collisions)} unmanaged record(s) preserved on logical-key collision.")
    for line in manufacturer_totals["collisions"]:
        print(f"{EVIDENCE_COLLISION_LABEL}: {line}")
    if apply_publication_state:
        print("Publication state was REWRITTEN from JSON (--apply-publication-state).")
    print(recon.summary())
    return recon


class ManufacturerImportAborted(SystemExit):
    """`--manufacturers-only` refused before writing anything."""


def run_manufacturers_only(url: str, *, manufacturers_path: Path | None = None,
                           authorize=None) -> dict:
    """Import ONLY manufacturer profiles and their company-level evidence.

    Reads `manufacturers.json` and nothing else. No robot file is opened, and no
    robot, publication flag, specification, offer, capability, variant,
    deployment, image, provider, region or robot-level evidence row is written.

    Order: validate the file (vocabularies, listing rule, source attribution)
    -> open ONE transaction -> confirm every headquarters region already exists
    (this mode never writes regions) -> upsert the profiles and refresh only the
    importer's own company evidence -> commit. Any failure before the commit
    rolls the whole transaction back, so nothing is half-written.
    """
    path = manufacturers_path or CATALOGUE_DIR / "manufacturers.json"
    manufacturers = _load(path)
    errors = validate_manufacturer_profiles(manufacturers) + manufacturer_key_problems(
        manufacturers)
    if errors:
        raise ManufacturerImportAborted(
            "manufacturer-only import refused before writing — "
            f"{len(errors)} problem(s) in {path.name}:\n  " + "\n  ".join(errors)
        )

    with psycopg.connect(url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO humanoid, public")
            regions = dict(cur.execute("SELECT code, id FROM region").fetchall())
            missing = sorted({
                m["country_region_code"] for m in manufacturers["manufacturers"]
                if m.get("country_region_code") and m["country_region_code"] not in regions
            })
            if missing:
                raise ManufacturerImportAborted(
                    "manufacturer-only import refused before writing — region code(s) "
                    f"not in the database: {', '.join(missing)}. This mode does not "
                    "write regions; load them through the catalogue import first."
                )
            recon = Reconciliation(authorize)
            totals = import_manufacturers(
                cur, manufacturers, lambda code: regions[code] if code else None, recon
            )
            recon.finish()
            preserved = cur.execute(
                "SELECT count(*) FROM evidence_source "
                "WHERE subject_type='MANUFACTURER' AND managed_by IS DISTINCT FROM %s",
                (MANAGED_BY,),
            ).fetchone()[0]
        conn.commit()

    totals["preserved"] = preserved
    print(f"MANUFACTURER-ONLY IMPORT OK: {totals['manufacturers']} "
          "manufacturer profile(s) upserted.")
    print(f"Company evidence: {totals['inserted']} catalogue-managed row(s) inserted, "
          f"{totals['updated']} updated in place, {totals['unchanged']} unchanged, "
          f"{totals['removed']} removed (authorized), "
          f"{preserved} unmarked row(s) preserved, "
          f"{len(totals['collisions'])} collision(s) with unmarked rows.")
    # Reported, never resolved here: content cannot show who wrote an unmarked row.
    for line in totals["collisions"]:
        print(f"{EVIDENCE_COLLISION_LABEL}: {line}")
    print(recon.summary())
    print("Robot records, publication state and robot-level evidence were not read or written.")
    return totals


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Import the WS2B verified catalogue")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument(
        "--apply-publication-state",
        action="store_true",
        help="ALSO rewrite is_published from the JSON files. This is a publishing "
             "operation, not a fact refresh: it changes what the public sees. "
             "Omitted (the default), an import updates catalogue facts and leaves "
             "the existing publication state of every known robot untouched.",
    )
    ap.add_argument(
        "--only",
        action="append",
        metavar="SLUG",
        help="Import ONLY these robot slugs (repeatable, or comma-separated). "
             "Shared entities (regions, manufacturers, providers, capabilities, "
             "use cases, spec definitions) are narrowed to what the selected "
             "records reference. Unknown slugs abort before anything is written. "
             "Omitted, every catalogue record is imported, exactly as before.",
    )
    ap.add_argument(
        "--manufacturers-only",
        action="store_true",
        help="Import ONLY manufacturer profiles and their company-level evidence "
             "from manufacturers.json. No robot file is read, and no robot, "
             "publication flag, specification, offer, capability, variant, "
             "deployment, image, provider, region or robot-level evidence row is "
             "written. Data and source attribution are validated before writing, "
             "in one transaction. Cannot be combined with --only or "
             "--apply-publication-state.",
    )
    ap.add_argument(
        "--authorize",
        metavar="PATH",
        help="JSON file of changes the importer may make beyond inserting and updating "
             "rows by natural key: {\"version\": 1, \"entries\": [{\"action\": "
             "\"remove\" | \"update_evidence\" | \"clear\", \"table\": ..., "
             "\"robot\": ..., \"key\": {...}, \"column\": ...}]}. A refused run prints "
             "the exact entries that would permit it. Nothing is authorized by default, "
             "and an entry that matches nothing aborts the run.",
    )
    args = ap.parse_args(argv)
    if args.manufacturers_only:
        conflicts = [flag for flag, given in (
            ("--only", bool(args.only)),
            ("--apply-publication-state", args.apply_publication_state),
        ) if given]
        if conflicts:
            ap.error("--manufacturers-only cannot be combined with " + ", ".join(conflicts))
    if not args.database_url:
        ap.error("no database URL: pass --database-url or set DATABASE_URL")
    if args.manufacturers_only:
        run_manufacturers_only(normalize_url(args.database_url), authorize=args.authorize)
        return
    only = None
    if args.only:
        only = {s.strip() for item in args.only for s in item.split(",") if s.strip()}
        if not only:
            ap.error("--only was given with no slugs")
    run(normalize_url(args.database_url), only=only,
        apply_publication_state=args.apply_publication_state, authorize=args.authorize)


if __name__ == "__main__":
    main()
