"""DATA-D1 Scheduled Freshness — manual/local interface (docs/22 Phase 9,
WorkOrder "Scheduled Freshness Foundation v0.1" Phase 8).

    uv run --directory apps/api python -m app.cli.freshness_check queue
    uv run --directory apps/api python -m app.cli.freshness_check mark \
        <target-id> --outcome CHECKED_UNCHANGED|CHANGE_FOUND|SOURCE_UNAVAILABLE \
        --operator "ops@humanoid.company" [--note "..."]

FOUNDATION SLICE: no `run` subcommand here yet. `run_due_checks()` (the
scheduled/local-run entry point) is fully implemented and tested at the
service layer, but wiring it into a CLI command needs a real
`FreshnessChecker` (an HTTP client) — deliberately out of scope for this
slice (no external network requests, no browser automation, no RobotShop
access). `queue` and `mark` are the only two commands this slice needs: with
zero registered FreshnessTarget rows (docs/22 Phase 10 — the required
starting state), `queue` reports an empty AUTO_CHECK/MANUAL_CHECK/
ELIGIBILITY_REVIEW_REQUIRED report and `mark` has nothing to act on until a
later slice registers targets.

`mark`/CHANGE_FOUND routes through the identical
`app.services.freshness.service.record_manual_check` -> `record_observation`
-> `create_or_reuse_recheck` path a future scheduled run will use — no
parallel truth pipeline (docs/22 Phase 9).
"""
from __future__ import annotations

import argparse
import sys
import uuid

from app.db.session import SessionLocal
from app.models.freshness import FreshnessTarget
from app.services.freshness import FreshnessError
from app.services.freshness.service import due_manual_targets, record_manual_check


def _cmd_queue(args: argparse.Namespace) -> int:
    with SessionLocal() as session:
        manual = due_manual_targets(session)

    manual_check = [(t, r) for t, mode, r in manual if mode == "MANUAL_CHECK"]
    review_required = [(t, r) for t, mode, r in manual if mode == "ELIGIBILITY_REVIEW_REQUIRED"]

    print("WEEKLY FRESHNESS REVIEW")
    print()
    print("AUTO_CHECK:")
    print("  0 due (no scheduler wired in this foundation slice)")
    print()
    print(f"MANUAL_CHECK: {len(manual_check)} due")
    for target, reason in manual_check:
        print(f"  {target.id}  robot={target.robot_id}  {target.url}  ({reason})")
    print()
    print(f"ELIGIBILITY_REVIEW_REQUIRED: {len(review_required)} due")
    for target, reason in review_required:
        print(f"  {target.id}  robot={target.robot_id}  {target.url}  ({reason})")
    return 0


def _cmd_mark(args: argparse.Namespace) -> int:
    try:
        target_id = uuid.UUID(args.target_id)
    except ValueError:
        print(f"invalid target id: {args.target_id!r}", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        target = session.get(FreshnessTarget, target_id)
        if target is None:
            print(f"freshness target not found: {target_id}", file=sys.stderr)
            return 1

        try:
            obs = record_manual_check(
                session,
                target,
                outcome=args.outcome,
                operator=args.operator,
                note=args.note,
            )
        except FreshnessError as exc:
            session.rollback()
            print(f"MARK REFUSED: {exc}", file=sys.stderr)
            return 3
        session.commit()

    print(f"recorded {args.outcome} for target {target_id} (observation {obs.id})")
    if obs.discovery_candidate_id:
        print(f"  -> DiscoveryCandidate {obs.discovery_candidate_id} (RECHECK_REQUIRED)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DATA-D1 Scheduled Freshness — manual review")
    sub = ap.add_subparsers(dest="command", required=True)

    q = sub.add_parser("queue", help="print the weekly manual review queue (read-only)")
    q.set_defaults(func=_cmd_queue)

    m = sub.add_parser("mark", help="record a manual check outcome for one target")
    m.add_argument("target_id")
    m.add_argument(
        "--outcome", required=True,
        choices=["CHECKED_UNCHANGED", "CHANGE_FOUND", "SOURCE_UNAVAILABLE"],
    )
    m.add_argument("--operator", required=True, help="the named human recording this check")
    m.add_argument("--note", default=None)
    m.set_defaults(func=_cmd_mark)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
