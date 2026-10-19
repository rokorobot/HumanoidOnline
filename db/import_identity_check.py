#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Read-only identity check: did an import keep every row's id?

    uv run db/import_identity_check.py --before URL --after URL [--robot SLUG ...] [--json PATH]

`db/import_preflight.py` compares CONTENT with ids stripped. This compares IDENTITY: for every
id-bearing catalogue table it maps each row's natural key (resolved to slugs, codes and keys) to
its id and `updated_at`, in both databases, and reports

  ID_CHANGED      the same logical row has a different id (delete + reinsert);
  TOUCHED         same id, but `updated_at` moved (the row was rewritten);
  ADDED / REMOVED a logical key present on one side only;
  AMBIGUOUS       two rows share one natural key (identity cannot be decided).

It also checks that every `catalogue_write_audit.target_row_id` that existed before still exists
after. Both connections are READ ONLY. Exit 0 = no ID_CHANGED, AMBIGUOUS or lost audit target
(ADDED/REMOVED/TOUCHED are reported for the operator to compare with the expected changes);
1 = identity regression; 2 = usage/connection error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter

import psycopg

# table -> SQL returning (robot_slug_or_None, key_text, id, updated_at_or_None)
KEYS = {
    "region": "SELECT NULL, code, id, NULL FROM region",
    "manufacturer": "SELECT NULL, slug, id, updated_at FROM manufacturer",
    "provider": "SELECT NULL, slug, id, updated_at FROM provider",
    "capability": "SELECT NULL, slug, id, NULL FROM capability",
    "use_case": "SELECT NULL, slug, id, NULL FROM use_case",
    "spec_definition": "SELECT NULL, key, id, NULL FROM spec_definition",
    "robot": "SELECT slug, slug, id, updated_at FROM robot",
    "robot_variant": "SELECT r.slug, v.slug, v.id, NULL FROM robot_variant v "
                     "JOIN robot r ON r.id = v.robot_id",
    "specification": "SELECT r.slug, concat_ws('|', coalesce(v.slug, '-'), d.key), s.id, NULL "
                     "FROM specification s JOIN robot r ON r.id = s.robot_id "
                     "JOIN spec_definition d ON d.id = s.definition_id "
                     "LEFT JOIN robot_variant v ON v.id = s.variant_id",
    "pricing_offer": "SELECT r.slug, concat_ws('|', coalesce(v.slug, '-'), coalesce(p.slug, '-'), "
                     "coalesce(g.code, '-'), o.transaction_type::text, o.condition::text), o.id, "
                     "o.updated_at FROM pricing_offer o JOIN robot r ON r.id = o.robot_id "
                     "LEFT JOIN robot_variant v ON v.id = o.variant_id "
                     "LEFT JOIN provider p ON p.id = o.provider_id "
                     "LEFT JOIN region g ON g.id = o.region_id",
    "availability_offer": "SELECT r.slug, concat_ws('|', coalesce(v.slug, '-'), "
                          "coalesce(p.slug, '-'), coalesce(g.code, '-'), "
                          "o.transaction_type::text, o.condition::text), o.id, o.updated_at "
                          "FROM availability_offer o JOIN robot r ON r.id = o.robot_id "
                          "LEFT JOIN robot_variant v ON v.id = o.variant_id "
                          "LEFT JOIN provider p ON p.id = o.provider_id "
                          "LEFT JOIN region g ON g.id = o.region_id",
    "deployment": "SELECT r.slug, concat_ws('|', coalesce(d.customer_name, '-'), "
                  "coalesce(g.code, '-'), coalesce(d.started_on::text, '-')), d.id, NULL "
                  "FROM deployment d JOIN robot r ON r.id = d.robot_id "
                  "LEFT JOIN region g ON g.id = d.region_id",
    "robot_image": "SELECT r.slug, i.image_url, i.id, NULL FROM robot_image i "
                   "JOIN robot r ON r.id = i.robot_id",
}
EVIDENCE = ("SELECT id, subject_type::text, subject_id::text, coalesce(source_url, '-'), "
            "source_type::text, coalesce(excerpt, ''), coalesce(observed_at::date::text, '-') "
            "FROM evidence_source")
ID_TABLES_FOR_SUBJECTS = ("robot", "manufacturer", "provider", "robot_variant", "specification",
                          "pricing_offer", "availability_offer", "deployment")


def _has_updated_at(cur, table: str) -> bool:
    return cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'humanoid' "
        "AND table_name = %s AND column_name = 'updated_at'", (table,)).fetchone() is not None


def snapshot(url: str) -> dict:
    with psycopg.connect(url) as conn:
        conn.read_only = True
        cur = conn.cursor()
        cur.execute("SET search_path TO humanoid, public")
        out: dict = {}
        label: dict[str, str] = {}               # row id -> "table:robot:key", for evidence
        for table, sql in KEYS.items():
            if "updated_at" in sql and not _has_updated_at(cur, table):
                sql = sql.replace("updated_at", "NULL").replace("o.NULL", "NULL")
            rows: dict = {}
            dup = Counter()
            for robot, key, rid, upd in cur.execute(sql).fetchall():
                k = f"{robot or '*'}:{key}"
                dup[k] += 1
                rows[k] = (str(rid), upd.isoformat() if upd else None)
                label[str(rid)] = f"{table}:{k}"
            out[table] = {"rows": rows, "ambiguous": sorted(k for k, n in dup.items() if n > 1)}
        rows, dup = {}, Counter()
        for rid, st, sid, url_, stype, excerpt, obs in cur.execute(EVIDENCE).fetchall():
            subject = label.get(sid, f"?{sid}")
            k = "|".join([st, subject, url_, stype,
                          hashlib.sha256(excerpt.encode()).hexdigest()[:16], obs])
            dup[k] += 1
            rows[k] = (str(rid), None)
        out["evidence_source"] = {"rows": rows,
                                  "ambiguous": sorted(k for k, n in dup.items() if n > 1)}
        out["_audit_targets"] = {
            str(r[0]): bool(r[2]) for r in cur.execute(
                "SELECT a.audit_seq, a.target_table, EXISTS ("
                " SELECT 1 FROM robot_variant WHERE id = a.target_row_id UNION ALL"
                " SELECT 1 FROM specification WHERE id = a.target_row_id UNION ALL"
                " SELECT 1 FROM pricing_offer WHERE id = a.target_row_id UNION ALL"
                " SELECT 1 FROM availability_offer WHERE id = a.target_row_id UNION ALL"
                " SELECT 1 FROM robot WHERE id = a.target_row_id) "
                "FROM catalogue_write_audit a").fetchall()}
        return out


def _robot_of(key: str) -> str:
    return key.split(":", 1)[0]


def compare(before: dict, after: dict, robots: set[str] | None = None) -> dict:
    report = {"ID_CHANGED": [], "TOUCHED": [], "ADDED": [], "REMOVED": [], "AMBIGUOUS": [],
              "AUDIT_TARGET_LOST": []}
    for table in before:
        if table.startswith("_"):
            continue
        b, a = before[table]["rows"], after[table]["rows"]

        def scoped(k, table=table):
            if robots is None or table == "evidence_source":
                return True
            return _robot_of(k) in robots or _robot_of(k) == "*"
        for k in sorted(set(b) | set(a)):
            if not scoped(k):
                continue
            if k in b and k not in a:
                report["REMOVED"].append(f"{table} {k}")
            elif k in a and k not in b:
                report["ADDED"].append(f"{table} {k}")
            elif b[k][0] != a[k][0]:
                report["ID_CHANGED"].append(f"{table} {k}")
            elif b[k][1] != a[k][1]:
                report["TOUCHED"].append(f"{table} {k}")
        report["AMBIGUOUS"] += [f"{table} {k}" for k in after[table]["ambiguous"]]
    for seq, existed in before["_audit_targets"].items():
        if existed and not after["_audit_targets"].get(seq, False):
            report["AUDIT_TARGET_LOST"].append(f"audit_seq {seq}")
    report["dangling_audit_targets_after"] = sum(
        1 for v in after["_audit_targets"].values() if not v)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--robot", action="append", help="limit robot-scoped tables to these slugs")
    ap.add_argument("--json", help="write the full report here")
    args = ap.parse_args(argv)
    try:
        before, after = snapshot(args.before), snapshot(args.after)
    except psycopg.Error as exc:
        print(f"IDENTITY_CHECK_ERROR ({type(exc).__name__}): check the connection URLs.",
              file=sys.stderr)
        return 2
    report = compare(before, after, set(args.robot) if args.robot else None)
    for kind in ("ID_CHANGED", "AMBIGUOUS", "AUDIT_TARGET_LOST", "REMOVED", "ADDED", "TOUCHED"):
        print(f"{kind}: {len(report[kind])}")
        for line in report[kind][:50]:
            print(f"  {line}")
    print(f"dangling audit targets after: {report['dangling_audit_targets_after']}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    bad = report["ID_CHANGED"] or report["AMBIGUOUS"] or report["AUDIT_TARGET_LOST"]
    print("IDENTITY CHECK " + ("FAIL" if bad else "PASS"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
