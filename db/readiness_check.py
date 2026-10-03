#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""G4-3 readiness (DR-G4 sections 7-8): the INTEGRITY gate and the non-blocking COVERAGE audit.

    Incomplete is publishable. Misleading is not.

    uv run db/readiness_check.py integrity [--slug S ...]   # REQUIRED gate: exit 1 on any BLOCK finding
    uv run db/readiness_check.py coverage  [--slug S ...]   # informational: ALWAYS exits 0
    uv run db/readiness_check.py publish --slug S           # would S pass an unpublished -> published flip?

* `integrity` fails only for truthfulness defects (identity, conflict, public-vs-canonical contradiction,
  fabricated transformations, missing required provenance, publication mechanics, loss). It never fails
  for UNKNOWN fields, a missing price/availability/SDK, detail-only or unmapped knowledge, low coverage, or
  a legacy missing summary / legacy unexplained `false` (those are coverage findings).
* `coverage` has no failing outcome. Findings are data. It exits non-zero only if the command itself fails
  technically (cannot connect, cannot read).
* Neither command writes anything or changes publication state. Nothing is ever unpublished.

Connection: --database-url or $DATABASE_URL (a SQLAlchemy '+psycopg' driver prefix is accepted).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.services import readiness as rd  # noqa: E402
from app.services.readiness_loader import load_records  # noqa: E402

BASELINE = REPO_ROOT / "db" / "catalogue" / "legacy_readiness_baseline.json"


def normalize_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def legacy_baseline() -> frozenset[tuple[str, str]]:
    return rd.load_legacy_baseline(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() \
        else frozenset()


def _records(url: str, slugs):
    with psycopg.connect(normalize_url(url)) as conn, conn.cursor() as cur:
        return load_records(cur, set(slugs) if slugs else None)


def cmd_integrity(url: str, slugs, as_json: bool) -> int:
    legacy = legacy_baseline()
    recs = _records(url, slugs)
    blocking = []
    for rec in recs:
        blocking += [(rec.slug, f) for f in rd.integrity_check(rec, legacy=legacy)
                     if f.severity == rd.BLOCK]
    if as_json:
        print(json.dumps({"robots": len(recs), "blocking": [
            {"slug": s, "code": f.code, "message": f.message, "subject": f.subject}
            for s, f in blocking]}, indent=2))
    else:
        for slug, f in blocking:
            print(f"INTEGRITY BLOCK  {slug}: {f.code}: {f.message}")
        print(f"integrity gate: {len(recs)} robot(s) inspected, {len(blocking)} blocking finding(s)")
        print("Integrity gate: " + ("PASS" if not blocking else "FAIL"))
    return 1 if blocking else 0


def cmd_coverage(url: str, slugs, as_json: bool) -> int:
    legacy = legacy_baseline()
    recs = _records(url, slugs)
    reports = [rd.coverage_audit(r, legacy=legacy) for r in recs]
    totals = Counter()
    codes = Counter()
    bands = Counter()
    for rep in reports:
        bands[rep.band] += 1
        for k, v in rep.accounting.as_dict().items():
            if isinstance(v, int):
                totals[k] += v
        for f in rep.findings:
            codes[f.code] += 1
    if as_json:
        print(json.dumps({
            "robots": len(reports), "bands": dict(bands), "accounting": dict(totals),
            "findings": dict(codes),
            "per_robot": {r.slug: {"band": r.band, "known": r.known_buyer_fields,
                                   "of": r.total_buyer_fields,
                                   "findings": [f.code for f in r.findings]} for r in reports},
        }, indent=2))
        return 0
    print("COVERAGE AUDIT (informational; never blocks; exits 0)")
    print(f"robots inspected: {len(reports)}   coverage bands: " + ", ".join(
        f"{b}={bands.get(b, 0)}" for b in ("LOW", "PARTIAL", "GOOD")))
    print("fact accounting (all robots): " + ", ".join(f"{k}={v}" for k, v in sorted(totals.items())))
    print("findings: " + (", ".join(f"{k}={v}" for k, v in sorted(codes.items())) or "none"))
    for rep in reports:
        if len(reports) <= 8 or any(f.severity == rd.WARN for f in rep.findings):
            for f in rep.findings:
                if f.severity == rd.WARN or len(reports) <= 8:
                    print(f"  {rep.slug} [{rep.band}] {f.severity} {f.code}: {f.message}")
    return 0


def cmd_publish(url: str, slugs, as_json: bool) -> int:
    if not slugs:
        print("publish requires --slug", file=sys.stderr)
        return 2
    legacy = legacy_baseline()
    rc = 0
    for rec in _records(url, slugs):
        blockers = rd.publication_check(rec, legacy=legacy)
        warn = rd.coverage_audit(rec, legacy=legacy)
        print(f"{rec.slug}: " + ("PUBLISHABLE" if not blockers else "BLOCKED")
              + f"   coverage={warn.band} (warnings do not block)")
        for f in blockers:
            print(f"  BLOCK {f.code}: {f.message}")
        rc = rc or (1 if blockers else 0)
    return rc


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="G4-3 integrity gate and coverage audit")
    ap.add_argument("mode", choices=["integrity", "coverage", "publish"])
    ap.add_argument("--slug", action="append", default=[])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args(argv)
    if not args.database_url:
        ap.error("no database URL: pass --database-url or set DATABASE_URL")
    fn = {"integrity": cmd_integrity, "coverage": cmd_coverage, "publish": cmd_publish}[args.mode]
    sys.exit(fn(args.database_url, args.slug, args.json))


if __name__ == "__main__":
    main()
