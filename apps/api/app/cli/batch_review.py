"""Batch trace + promotion review CLI (DATA-D1 §9/§18, gates P2/P8/H2).

Clears a discovery queue at human speed without weakening a gate. Two phases,
separated by a file you edit:

    # 1) export every non-terminal candidate to a worksheet
    uv run --directory apps/api python -m app.cli.batch_review export \
        --out var/discovery/review/worksheet.json

    # 2) open each trace_url, decide, then dry-run (default) to see the outcome
    uv run --directory apps/api python -m app.cli.batch_review apply \
        var/discovery/review/worksheet.json --reviewed-by "robert@humanoid.company"

    # 3) same again with --write to commit; add --promote to promote confirmed rows
    uv run --directory apps/api python -m app.cli.batch_review apply \
        var/discovery/review/worksheet.json --reviewed-by "robert@..." --promote --write

`apply` is a DRY RUN unless `--write` is given: it reports exactly what would
happen and rolls the whole transaction back. Re-running a partially applied
worksheet is safe.

**Transaction semantics.** The whole worksheet runs in ONE transaction, with a
savepoint per action. An expected refusal — a gate saying no, or a database
constraint — rolls back only that savepoint and is reported as BLOCKED; anything
else aborts the run. **Each row is validated and isolated within the batch
transaction; successful rows become durable only at the final `--write`
commit.**

Every row carries a `snapshot_hash` binding the decision to the candidate as
exported. Editing `candidate_id`, or a candidate changing between export and
apply, makes the row refuse rather than apply your decision to a different or
newer record.

Promoted robots are created UNPUBLISHED with every specification UNKNOWN.
Publishing is the separate canonical catalogue workflow, never a side effect of
discovery.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.db.session import SessionLocal
from app.services.discovery import DiscoveryError
from app.services.discovery.batch_review import (
    apply_worksheet,
    export_worksheet,
    read_worksheet,
    write_worksheet,
)


def _cmd_export(args: argparse.Namespace) -> int:
    with SessionLocal() as session:
        worksheet = export_worksheet(session, limit=args.limit)
    if args.out:
        path = write_worksheet(args.out, worksheet)
        print(f"wrote {worksheet['candidate_count']} candidate(s) to {path}")
        print("Open each trace_url, confirm the page is about THAT robot, then set")
        print("decision to 'confirm' / 'reject' / 'skip'. A prefilled URL is a lead,")
        print("not proof.")
    else:
        print(json.dumps(worksheet, indent=2, ensure_ascii=False))
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    try:
        worksheet = read_worksheet(args.worksheet)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read worksheet: {exc}", file=sys.stderr)
        return 2
    except DiscoveryError as exc:
        print(f"worksheet refused: {exc}", file=sys.stderr)
        return 2

    dry_run = not args.write
    with SessionLocal() as session:
        try:
            result = apply_worksheet(
                session,
                worksheet,
                reviewed_by=args.reviewed_by,
                promote_confirmed=args.promote,
                dry_run=dry_run,
            )
        except DiscoveryError as exc:
            session.rollback()
            print(f"REFUSED (nothing written): {exc}", file=sys.stderr)
            return 2
        if not dry_run:
            session.commit()

    # ASCII only: this prints to a Windows console under cp1252, where an
    # em-dash renders as a replacement character.
    mode = "DRY RUN - nothing written" if dry_run else "WRITTEN"
    print(f"[{mode}]  reviewed_by={args.reviewed_by}")
    print(f"  traces confirmed : {len(result.confirmed)}")
    print(f"  promoted         : {len(result.promoted)}")
    print(f"  rejected         : {len(result.rejected)}")
    print(f"  skipped          : {len(result.skipped)}")
    print(f"  blocked          : {len(result.blocked)}")

    for row in result.promoted:
        print(f"    PROMOTED  {row['label']} -> {row['robot_slug']}")
    for row in result.blocked:
        print(f"    BLOCKED   {row['label']}: {row['why']}", file=sys.stderr)

    if dry_run and result.acted:
        print("\nRe-run with --write to apply.")
    # Blocked rows are a finding, not a crash: report them and exit nonzero so a
    # script cannot mistake a partial batch for a clean one.
    return 3 if result.blocked else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DATA-D1 batch trace + promotion review")
    sub = ap.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("export", help="write a review worksheet (read-only)")
    ex.add_argument("--out", help="worksheet path; omit to print to stdout")
    ex.add_argument("--limit", type=int, help="export at most N candidates")
    ex.set_defaults(func=_cmd_export)

    ap_ = sub.add_parser("apply", help="apply reviewer decisions (dry run by default)")
    ap_.add_argument("worksheet")
    ap_.add_argument("--reviewed-by", required=True, help="the named human deciding")
    ap_.add_argument("--promote", action="store_true", help="promote confirmed rows (P8)")
    ap_.add_argument("--write", action="store_true", help="commit; without it, dry run")
    ap_.set_defaults(func=_cmd_apply)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
