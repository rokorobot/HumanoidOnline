#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Semantic preflight gate for a production catalogue import.

READ-ONLY. It compares two databases — BEFORE (production, or the safety branch) and AFTER (a
rehearsal clone on which the exact import / claim chain was run) — row by row, with ids and
timestamps removed and every foreign key replaced by the natural key it points at, and checks
every change against an expected-change MANIFEST. Total row counts are never the test: a row
removed and a different row added leaves the counts unchanged and is reported here.

Why it exists (2026-10-05 Alza import): `import_catalogue.py --only <robot>` is robot-scoped
RECONCILIATION — it makes the selected robots (and what they reference) match their complete
canonical JSON, not merely the newest materialized claim. The rehearsal showed three extra
evidence rows that nobody had listed; only an explicit "every business change is accounted
for" gate makes that a stop instead of a surprise.

    uv run db/import_preflight.py --before "$PROD_URL" --after "$REHEARSAL_URL" \\
        --manifest expected.json

Exit 0: every non-audit business change is explained and every expected change happened.
Exit 2: an unexplained change (or an expected one that did not occur) — DO NOT import.
`--report-only` prints the classified changes and always exits 0 (no manifest, no gate).

Manifest:  {"expected": [{"table": "pricing_offer", "kind": "ADDED",
                          "match": {"robot": "unitree-r1-edu-u4", "provider": "alza-cz"},
                          "count": 1}, ...]}
`kind` is ADDED, REMOVED or CHANGED (a keyed row whose columns changed). `match` entries are
equality tests on the change's resolved fields (foreign keys appear as `robot`, `provider`,
`region`, `variant`, `subject`...); a key ending in `~` is a substring test. `count` defaults to
1.

What needs no manifest entry: ONLY genuinely append-only provenance / history (`AUDIT_TABLES`,
rationale below) and only when rows are ADDED. A REMOVED or altered row in those tables is never
legitimate and is gated too. Everything that is mutable configuration or effective state is
gated: the acquisition source registry (`discovery_source`: enabled flag, ToS/robots state,
cadence ...), freshness targets, crawl runs, discovery candidates, and the lead / requirement
tables (their rows are redacted — only a content hash is compared — so contact details never
reach the report). An unexpected change to a source such as `alza-cz`, whose automated
acquisition must stay disabled, therefore stops the import.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field

#: The ONLY tables whose ADDED rows need no manifest entry: append-only provenance / history.
#: Enforced by the database (append-only triggers) unless noted. A REMOVED or altered row in
#: any of them is gated (see `Change.gated`): history never shrinks or changes.
AUDIT_TABLES = frozenset({
    # DB-enforced append-only (refuse UPDATE/DELETE triggers): immutable decisions and lineage
    "accepted_claim", "claim_retraction", "catalogue_write_audit",
    "discovery_claim_proposal", "discovery_proposal_decision",
    "discovery_proposal_observation", "promotion_audit", "candidate_identity_decision",
    "source_eligibility_review",
    # Written once per observation; NO code path updates them (verified: no UPDATE statement and
    # no attribute assignment in app/ or db/). Not trigger-enforced, hence the removal gate.
    "fetched_page", "extraction_result", "discovery_evidence_excerpt", "freshness_observation",
    # Append-only analytics telemetry; production writes it continuously, so gating its adds
    # would stop every comparison taken from a live system.
    "event_log",
})
#: Mutable configuration / effective state that is NOT audit history, and why it is gated:
#:   discovery_source          enabled flag, ToS/robots state, path prefixes, cadence: decides
#:                             whether anything may ever be fetched automatically
#:   freshness_target          active / interval / manual_override: scheduled-check behaviour
#:   crawl_run                 status is updated (RUNNING -> COMPLETED/FAILED) and a RUNNING row
#:                             blocks other runs of its source (one-running guard)
#:   discovery_candidate,      review-queue state (identity/status/trace) that is edited in place
#:   candidate_claim,
#:   candidate_commercial_signal, candidate_image_ref
#:   commercial_lead (+ _robot/_provider), buyer_requirement, match_result
#:                             user-submitted business records; lead_status is mutable. Gated but
#:                             REDACTED (hash only): contact details must not reach reports, and
#:                             a lead that arrives between the clone and the comparison shows up
#:                             here as "production moved since the rehearsal"
REDACTED_TABLES = frozenset({"commercial_lead", "commercial_lead_robot",
                             "commercial_lead_provider", "buyer_requirement", "match_result"})
#: Natural keys: a removed + added pair with the same key is one CHANGED row. A tuple is a
#: composite key over the resolved field names.
NATURAL_KEY = {"robot": "slug", "provider": "slug", "manufacturer": "slug", "region": "code",
               "capability": "slug", "use_case": "slug", "spec_definition": "key",
               "discovery_source": "key",                       # discovery_source.key (UNIQUE)
               "freshness_target": ("robot", "url"),            # uq_freshness_target_robot_url
               "discovery_candidate": ("source", "external_ref")}  # uq_candidate_source_ref
CATEGORY = {"robot": "robot", "provider": "provider", "pricing_offer": "pricing_offer",
            "availability_offer": "availability_offer", "evidence_source": "evidence_source",
            "robot_variant": "variant", "discovery_source": "source",
            "freshness_target": "freshness_config", "crawl_run": "acquisition_run",
            "discovery_candidate": "discovery_candidate", "candidate_claim": "discovery_candidate",
            "candidate_commercial_signal": "discovery_candidate",
            "candidate_image_ref": "discovery_candidate",
            **{t: "runtime_user_data" for t in REDACTED_TABLES}}
DROP = {"id", "created_at", "updated_at", "search_vector"}
LABEL_TABLES = {  # table -> expression naming a row by its natural key
    "robot": "slug", "provider": "slug", "region": "code", "manufacturer": "slug",
    "capability": "slug", "use_case": "slug", "spec_definition": "key",
    "discovery_source": "key",
}


@dataclass
class Change:
    table: str
    kind: str                       # ADDED | REMOVED | CHANGED
    fields: dict
    detail: dict = field(default_factory=dict)   # CHANGED: {column: [before, after]}

    @property
    def audit(self) -> bool:
        """An ADDED row of an append-only history table: counted, never gated."""
        return self.table in AUDIT_TABLES and self.kind == "ADDED"

    @property
    def gated(self) -> bool:
        return not self.audit

    @property
    def category(self) -> str:
        if self.table == "robot" and self.kind == "CHANGED" and "is_published" in self.detail:
            return "publication"
        if self.table == "robot" and self.kind == "ADDED" and self.fields.get("is_published"):
            return "publication"
        if self.table in AUDIT_TABLES:
            return "audit_removal"           # history lost or altered: never legitimate
        if self.kind == "REMOVED":
            return "removal"
        return CATEGORY.get(self.table, "other_catalogue")


def snapshot(conn) -> dict[str, list[dict]]:
    """Every humanoid table as id-free rows with foreign keys resolved to natural keys."""
    cur = conn.cursor()
    cur.execute("SET search_path TO humanoid, public")
    cur.execute("select tablename from pg_tables where schemaname = 'humanoid' order by 1")
    tables = [r[0] for r in cur.fetchall()]
    labels: dict[str, str] = {}
    for table, col in LABEL_TABLES.items():
        if table in tables:
            cur.execute(f"select id::text, {col} from humanoid.{table}")
            labels.update({i: f"{table}:{v}" for i, v in cur.fetchall()})

    def short(i):
        return labels.get(i, i).split(":", 1)[-1]

    if "robot_variant" in tables:
        cur.execute("select v.id::text, v.slug, r.slug from humanoid.robot_variant v "
                    "join humanoid.robot r on r.id = v.robot_id")
        labels.update({i: f"robot_variant:{r}/{s}" for i, s, r in cur.fetchall()})
    offers = {"pricing_offer": ("robot_id", "provider_id", "region_id", "variant_id",
                                "condition", "transaction_type", "price_type"),
              "availability_offer": ("robot_id", "provider_id", "region_id", "variant_id",
                                     "condition", "transaction_type")}
    for table, cols in offers.items():
        if table in tables:
            cur.execute(f"select id::text, {', '.join(f'{c}::text' for c in cols)} "
                        f"from humanoid.{table}")
            for row in cur.fetchall():
                parts = [short(v) if c.endswith("_id") and v else (v or "-")
                         for c, v in zip(cols, row[1:], strict=True)]
                labels[row[0]] = f"{table}:" + "|".join(parts)
    for table, name in (("deployment", "customer_name"), ("robot_image", "image_url")):
        if table in tables:
            cur.execute(f"select id::text, robot_id::text, {name} from humanoid.{table}")
            labels.update({i: f"{table}:{short(r)}|{n}" for i, r, n in cur.fetchall()})
    out: dict[str, list[dict]] = {}
    for table in tables:
        cur.execute(f"select row_to_json(x)::text from humanoid.{table} x")
        rows = []
        for (txt,) in cur.fetchall():
            row = json.loads(txt)
            clean = {}
            for k, v in row.items():
                if k in DROP:
                    continue
                if isinstance(v, str) and v in labels:
                    clean[k[:-3] if k.endswith("_id") else k] = labels[v].split(":", 1)[-1]
                elif k.endswith("_id") and isinstance(v, str):
                    clean[k[:-3]] = labels.get(v, v)    # unresolved FK: keep the raw id
                else:
                    clean[k] = v
            if table in REDACTED_TABLES:
                clean = {"redacted_content_sha": hashlib.sha256(
                    json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()[:16]}
            rows.append(clean)
        out[table] = rows
    return out


def diff(before: dict, after: dict) -> list[Change]:
    changes: list[Change] = []
    for table in sorted(set(before) | set(after)):
        b = Counter(json.dumps(r, sort_keys=True, default=str) for r in before.get(table, []))
        a = Counter(json.dumps(r, sort_keys=True, default=str) for r in after.get(table, []))
        removed = [json.loads(k) for k, n in (b - a).items() for _ in range(n)]
        added = [json.loads(k) for k, n in (a - b).items() for _ in range(n)]
        key = NATURAL_KEY.get(table)
        if key:    # pair a removed + added row with the same natural key into CHANGED
            keys = (key,) if isinstance(key, str) else key

            def kf(r, keys=keys):
                return tuple(r.get(k) for k in keys)

            by_key = {kf(r): r for r in removed}
            for row in list(added):
                old = by_key.pop(kf(row), None)
                if old is not None:
                    added.remove(row)
                    removed.remove(old)
                    detail = {c: [old.get(c), row.get(c)] for c in sorted(set(old) | set(row))
                              if old.get(c) != row.get(c)}
                    changes.append(Change(table, "CHANGED", row, detail))
        changes += [Change(table, "REMOVED", r) for r in removed]
        changes += [Change(table, "ADDED", r) for r in added]
    return changes


def _matches(change: Change, entry: dict) -> bool:
    if entry["table"] != change.table or entry["kind"] != change.kind:
        return False
    for k, want in entry.get("match", {}).items():
        if k.endswith("~"):
            if str(want) not in str(change.fields.get(k[:-1], "")):
                return False
        elif change.fields.get(k) != want:
            return False
    return True


def classify(changes: list[Change], manifest: dict) -> dict:
    """Account for every non-audit change. Returns the report; `ok` is the gate."""
    budget = [[e, e.get("count", 1)] for e in manifest.get("expected", [])]
    unexplained: list[Change] = []
    for change in changes:
        if change.audit:
            continue
        for slot in budget:
            if slot[1] > 0 and _matches(change, slot[0]):
                slot[1] -= 1
                break
        else:
            unexplained.append(change)
    unfulfilled = [{"expected": e, "missing": n} for e, n in budget if n > 0]
    business = [c for c in changes if c.gated]
    return {
        "ok": not unexplained and not unfulfilled,
        "business_changes": len(business),
        "by_category": dict(Counter(c.category for c in business)),
        "audit_history_added": dict(Counter(c.table for c in changes if c.audit)),
        "unexplained": [{"table": c.table, "kind": c.kind, "category": c.category,
                         "fields": c.fields, "detail": c.detail} for c in unexplained],
        "unfulfilled": unfulfilled,
    }


def render(report: dict) -> str:
    lines = [f"business changes: {report['business_changes']}  {report['by_category']}",
             f"append-only history rows ADDED (not gated): {report['audit_history_added']}"]
    for u in report["unexplained"]:
        shown = u["fields"] if u["kind"] != "CHANGED" else u["detail"]
        lines.append(f"UNEXPLAINED {u['kind']} {u['table']} [{u['category']}]: "
                     f"{json.dumps(shown, default=str, ensure_ascii=False)[:300]}")
    for m in report["unfulfilled"]:
        lines.append(f"EXPECTED BUT ABSENT x{m['missing']}: {json.dumps(m['expected'])}")
    lines.append("PREFLIGHT " + ("PASS: every business change is accounted for"
                                 if report["ok"] else "STOP: do not run the production import"))
    return "\n".join(lines)


def main(argv=None) -> int:
    import psycopg

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", required=True, help="production / safety-branch URL (read-only)")
    ap.add_argument("--after", required=True, help="rehearsal clone URL (read-only)")
    ap.add_argument("--manifest", help="expected-change manifest (JSON)")
    ap.add_argument("--report-only", action="store_true", help="print only; no gate")
    ap.add_argument("--json", help="write the full report here")
    args = ap.parse_args(argv)
    if not args.manifest and not args.report_only:
        ap.error("a manifest is required (or --report-only, which is not a gate)")
    snaps = []
    for url in (args.before, args.after):
        with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1)) as conn:
            conn.read_only = True
            snaps.append(snapshot(conn))
    changes = diff(*snaps)
    manifest = json.load(open(args.manifest, encoding="utf-8")) if args.manifest else {}
    report = classify(changes, manifest)
    if args.json:
        open(args.json, "w", encoding="utf-8").write(json.dumps(report, indent=1, default=str,
                                                                 ensure_ascii=False))
    print(render(report))
    return 0 if args.report_only or report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
