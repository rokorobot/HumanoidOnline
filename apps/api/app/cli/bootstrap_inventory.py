"""MANUAL_BOOTSTRAP inventory ingest — DATA-D1.LIVE §2.1.

Fills the discovery queue from a committed, reviewable dataset. No network, no
adapter, no traversal.

    uv run --directory apps/api python -m app.cli.bootstrap_inventory \
        humanoid_radar_v1 --operator "ops@humanoid.company"

    ... --dry-run          # validate and report; write nothing

What this does NOT do: put a robot in the catalogue. Every entry lands as a
NOT_VERIFIED candidate that still needs a confirmed official trace and a human
promotion (`python -m app.cli.promote_candidate`). That is the point — the queue
is meant to be full and the catalogue is meant to be earned.
"""
from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.services.discovery import DiscoveryError
from app.services.discovery.bootstrap import (
    bootstrap,
    load_dataset,
    validate_dataset,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DATA-D1.LIVE MANUAL_BOOTSTRAP ingest")
    ap.add_argument("dataset", help="dataset name under db/discovery/bootstrap/")
    ap.add_argument(
        "--operator",
        help="the named human accountable for this batch (LIVE.4). Required to write.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="validate the dataset and report; write nothing",
    )
    args = ap.parse_args(argv)

    try:
        records = load_dataset(args.dataset)
        validate_dataset(records)
    except DiscoveryError as exc:
        print(f"BOOTSTRAP REFUSED: {exc}", file=sys.stderr)
        return 1

    makers = sorted({str(r.get("manufacturer")) for r in records})
    claims = sum(len(r.get("claims") or []) for r in records)
    print(f"dataset {args.dataset}: {len(records)} humanoid(s), "
          f"{len(makers)} manufacturer(s), {claims} evidence-bound claim(s)")

    if args.dry_run:
        for record in records:
            print(f"  {record['manufacturer']} / {record['name']}"
                  f"  <- {record.get('data', {}).get('official_url', '-')}")
        print("dry run: nothing written")
        return 0

    if not args.operator:
        print("BOOTSTRAP REFUSED: --operator is required to write (LIVE.4)",
              file=sys.stderr)
        return 2

    with SessionLocal() as session:
        try:
            source, created = bootstrap(
                session, dataset=args.dataset, operator=args.operator
            )
        except DiscoveryError as exc:
            session.rollback()
            print(f"BOOTSTRAP REFUSED: {exc}", file=sys.stderr)
            return 1
        session.commit()

    print(f"source {source.key} (reviewed by {source.eligibility_reviewed_by})")
    print(f"created {len(created)} new candidate(s); "
          f"{len(records) - len(created)} already present (re-seen)")
    print()
    print("These are CANDIDATES, not catalogue entries. Each still needs a "
          "confirmed official trace and a human promotion:")
    print("  python -m app.cli.promote_candidate <candidate-id> --show")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
