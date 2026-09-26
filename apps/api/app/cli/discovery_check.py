"""Discovery foundation: read-only status and an explicitly unavailable runner.

Exit codes: 0 prerequisites present (status only), 1 inspection error,
2 invalid arguments, 3 missing prerequisites, 4 execution not implemented.
No acquisition, candidate writes or scheduling is provided in this slice.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.config import ConfigurationError
from app.services.discovery import DiscoveryError

NOT_READY = 3
NOT_IMPLEMENTED = 4


def _cmd_status(args: argparse.Namespace) -> int:
    try:
        # Keep help and the inert run command independent of DB configuration.
        from app.db.session import SessionLocal
        from app.services.discovery.readiness import check_readiness

        with SessionLocal() as session:
            report = check_readiness(session)
    except (SQLAlchemyError, DiscoveryError, ConfigurationError, OSError, ValueError):
        # Connection exceptions can contain credentials: never echo them.
        print("STATUS_ERROR: check database configuration and baseline dataset.", file=sys.stderr)
        return 1

    print(f"Prerequisites: {'READY' if report.prerequisites_ready else 'NOT_READY'}")
    print("Execution: NOT_IMPLEMENTED (foundation slice)")
    print(f"Baseline source present: {report.baseline_source_present}")
    print(f"Baseline coverage: {report.expected_lead_count - len(report.missing_lead_refs)}"
          f"/{report.expected_lead_count}")
    print(f"Radar-eligible live sources: {len(report.eligible_source_keys)}")
    for prerequisite in report.missing_prerequisites:
        print(f"  missing: {prerequisite}")
    for ref in report.missing_lead_refs:
        print(f"  missing lead: {ref}")
    return 0 if report.prerequisites_ready else NOT_READY


def _cmd_run(args: argparse.Namespace) -> int:
    print("NOT_IMPLEMENTED: discovery execution is unavailable in Stage A.", file=sys.stderr)
    return NOT_IMPLEMENTED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discovery foundation — initialization status")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="inspect initialization prerequisites (read-only)")
    status.set_defaults(func=_cmd_status)
    run = commands.add_parser("run", help="unavailable: exits without connecting or fetching")
    run.set_defaults(func=_cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
