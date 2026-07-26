"""Governed human promotion gate (DATA-D1 §18/§25-G) — the ONLY canonical writer.

Run internally (network-gated), never by the pipeline/crawler:

    uv run --directory apps/api python -m app.cli.promote_candidate \
        <candidate_id> --approve --approved-by "ops@humanoid.company"

    ... --reject --approved-by "ops@..." --reason "no independent source"
    ... --show          # print the structured proposal + failing gates, no write

`--approve` refuses (nonzero exit, no write) if any IMPLEMENTED promotion gate
fails (P1, P2, P4, P6, readiness, and the P8 human approval).
"""
from __future__ import annotations

import argparse
import sys
import uuid

from app.db.session import SessionLocal
from app.models.discovery import DiscoveryCandidate
from app.services.discovery import PromotionError
from app.services.discovery.pipeline import advance
from app.services.discovery.promotion import build_proposal, promote, reject


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DATA-D1 governed promotion gate")
    ap.add_argument("candidate_id")
    ap.add_argument("--approved-by", help="the approving human (required for --approve/--reject)")
    ap.add_argument("--advance", action="store_true", help="run the pipeline before acting")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--approve", action="store_true", help="promote to canonical")
    group.add_argument("--reject", action="store_true", help="record a rejection")
    group.add_argument("--show", action="store_true", help="print the proposal only")
    ap.add_argument("--reason", default="", help="rejection reason")
    args = ap.parse_args(argv)

    try:
        cid = uuid.UUID(args.candidate_id)
    except ValueError:
        print(f"invalid candidate id: {args.candidate_id!r}", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        candidate = session.get(DiscoveryCandidate, cid)
        if candidate is None:
            print(f"candidate not found: {cid}", file=sys.stderr)
            return 1

        if args.advance:
            advance(session, candidate)

        if args.approve:
            if not args.approved_by:
                print("--approve requires --approved-by", file=sys.stderr)
                return 2
            try:
                robot = promote(session, candidate, args.approved_by)
            except PromotionError as exc:
                session.rollback()
                print(f"PROMOTION BLOCKED: {exc}", file=sys.stderr)
                return 3
            session.commit()
            print(f"PROMOTED candidate {cid} -> robot {robot.slug} ({robot.id})")
            return 0

        if args.reject:
            if not args.approved_by:
                print("--reject requires --approved-by", file=sys.stderr)
                return 2
            try:
                reject(session, candidate, args.approved_by, args.reason)
            except PromotionError as exc:
                session.rollback()
                print(f"REJECTION REFUSED: {exc}", file=sys.stderr)
                return 3
            session.commit()
            print(f"REJECTED candidate {cid}")
            return 0

        # default / --show: print the proposal, no write
        import json

        print(json.dumps(build_proposal(session, candidate), indent=2, default=str))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
