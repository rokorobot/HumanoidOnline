"""Importer Hardening Phase 0: read-only catalogue integrity report.

    python -m app.cli.audit_integrity [--json PATH] [--verbose]

Runs in a READ ONLY transaction and rolls back; it never writes. Reports:
  1. catalogue_write_audit rows classified CURRENT / RELINKABLE / SUPERSEDED / RETRACTED /
     UNRESOLVED (see app.services.discovery.audit_integrity), and which targets dangle;
  2. evidence_source rows whose subject row is missing;
  3. variant-scoped specification rows not owned by the importer.

Exit codes: 0 report produced (a report, not a gate), 1 database error.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import ConfigurationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only catalogue integrity report")
    parser.add_argument("--json", type=Path, help="also write the full report as JSON")
    parser.add_argument("--verbose", action="store_true", help="list every audit row")
    args = parser.parse_args(argv)
    try:
        from app.db.session import SessionLocal
        from app.services.discovery.audit_integrity import build_report

        with SessionLocal() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            report = build_report(session)
            session.rollback()
    except (SQLAlchemyError, ConfigurationError, OSError) as exc:
        # Connection exceptions can contain credentials: never echo them.
        print(f"REPORT_ERROR ({type(exc).__name__}): check database configuration.",
              file=sys.stderr)
        return 1

    counts = report.counts()
    print(f"catalogue_write_audit: {len(report.audits)} rows, "
          f"{len(report.dangling)} with a missing target_row_id")
    for cls, n in counts.items():
        dangling = sum(1 for a in report.dangling if a.classification == cls)
        print(f"  {cls:<11} {n:>4}  (dangling {dangling})")
    by_robot: dict[str, dict[str, int]] = {}
    for a in report.dangling:
        by_robot.setdefault(a.robot_slug, {}).setdefault(a.target_table, 0)
        by_robot[a.robot_slug][a.target_table] += 1
    for slug, tables in sorted(by_robot.items()):
        print(f"  dangling {slug}: "
              + ", ".join(f"{t} {n}" for t, n in sorted(tables.items())))
    for a in report.audits:
        if args.verbose or a.classification == "UNRESOLVED":
            print(f"  #{a.audit_seq} {a.classification} {a.robot_slug} {a.target_table} "
                  f"{a.target_row_id[:8]} exists={a.target_exists} "
                  f"now={(a.current_row_id or '-')[:8]} {a.reason}")
    print(f"evidence_source orphans: {len(report.evidence_orphans)}")
    for o in report.evidence_orphans:
        print(f"  {o['subject_type']} {o['subject_id'][:8]} {o['source_url']}")
    print(f"variant-scoped specification rows not importer-owned: "
          f"{len(report.unmanaged_variant_specs)}")
    for s in report.unmanaged_variant_specs:
        print(f"  {s['robot']}/{s['variant']} {s['key']} managed_by={s['managed_by']}")
    if args.json:
        args.json.write_text(json.dumps({
            "counts": counts, "audits": [asdict(a) for a in report.audits],
            "evidence_orphans": report.evidence_orphans,
            "unmanaged_variant_specs": report.unmanaged_variant_specs,
        }, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
