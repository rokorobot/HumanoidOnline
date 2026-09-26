"""Discovery Stage B operator CLI (docs/16 §14 subset): plan / crawl / report.

    python -m app.cli.discovery plan   <source-key> --url URL [--url URL ...] [--urls-file F]
    python -m app.cli.discovery crawl  <source-key> --operator "Name" --url URL ...
                                       [--limit N] [--dry-run] [--cache-dir DIR]
    python -m app.cli.discovery report <run-id>

- `plan` issues NO network request and writes nothing: it prints the policy
  verdict for each URL (source eligibility, approved host/path prefixes).
- `crawl --dry-run` checks policy, issues exactly ONE request (the source's
  robots.txt) and prints what would be fetched. No target page is requested
  and nothing is written to the database.
- `crawl` is a MANUAL run by a named operator over an explicit URL list: no
  link-following, no sitemap expansion, no scheduling. Writes discovery tables
  only (crawl_run, fetched_page, discovery_source bookkeeping).

Kill switch: create `var/discovery/KILL` (all sources) or
`var/discovery/KILL.<source-key>`; it is checked before every request.

Exit codes: 0 completed / ok, 1 error, 2 invalid arguments, 3 refused by
policy (nothing requested), 5 halted by policy, 6 cancelled (kill switch).
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import ConfigurationError
from app.services.discovery import DiscoveryError
from app.services.discovery.cache import DEFAULT_CACHE_DIR

REFUSED, HALTED, CANCELLED = 3, 5, 6
KILL_DIR = DEFAULT_CACHE_DIR.parent


def kill_switch_for(source_key: str, kill_dir: Path = KILL_DIR):
    return lambda: (kill_dir / "KILL").exists() or (kill_dir / f"KILL.{source_key}").exists()


def _urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.url or [])
    if args.urls_file:
        text = Path(args.urls_file).read_text(encoding="utf-8")
        urls += [line.strip() for line in text.splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
    return urls


def _load_source(session, key: str):
    from app.models.discovery import DiscoverySource

    return session.scalars(select(DiscoverySource).where(DiscoverySource.key == key)).first()


def _print_refusal(exc) -> int:
    print("REFUSED: nothing was requested.", file=sys.stderr)
    for url, reason in exc.problems:
        print(f"  {reason:<28} {url}", file=sys.stderr)
    return REFUSED


def _cmd_plan(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal
    from app.services.discovery.acquisition import plan

    with SessionLocal() as session:
        source = _load_source(session, args.source_key)
        verdicts = plan(source, _urls(args), args.limit)
    print(f"PLAN source={args.source_key} (no request issued; robots.txt is read at crawl time)")
    for url, verdict in verdicts:
        print(f"  {verdict:<28} {url}")
    return 0 if all(v == "OK" for _, v in verdicts) else REFUSED


def _cmd_crawl(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal
    from app.services.discovery.acquisition import (
        AcquisitionRefused,
        dry_run,
        run_acquisition,
    )
    from app.services.discovery.fetcher import FetchLimits, HttpFetcher

    limits = FetchLimits(page_cap=args.limit)
    urls = _urls(args)
    with SessionLocal() as session, HttpFetcher(
        limits=limits, kill_switch=kill_switch_for(args.source_key)
    ) as fetcher:
        source = _load_source(session, args.source_key)
        try:
            if args.dry_run:
                result = dry_run(source, urls, fetcher)
                print(f"DRY RUN source={args.source_key}: robots.txt only, "
                      "no target page requested, nothing written")
                for url, decision in result.decisions:
                    print(f"  {decision:<40} {url}")
                return 0
            run = run_acquisition(
                session, source=source, urls=urls, operator=args.operator or "",
                fetcher=fetcher, cache_dir=Path(args.cache_dir), checkpoint=session.commit,
            )
        except AcquisitionRefused as exc:
            session.rollback()
            return _print_refusal(exc)
        print(f"RUN {run.id} status={run.status}")
        print(f"report: python -m app.cli.discovery report {run.id}")
        return {"COMPLETED": 0, "HALTED_BY_POLICY": HALTED, "CANCELLED": CANCELLED}.get(
            run.status, 1)


def _cmd_report(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal
    from app.services.discovery.acquisition import build_report

    try:
        run_id = uuid.UUID(args.run_id)
    except ValueError:
        print("invalid run id", file=sys.stderr)
        return 2
    with SessionLocal() as session:
        print(build_report(session, run_id))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discovery Stage B — bounded acquisition")
    commands = parser.add_subparsers(dest="command", required=True)

    def url_args(p):
        p.add_argument("source_key")
        p.add_argument("--url", action="append", help="explicit URL (repeatable)")
        p.add_argument("--urls-file", help="one URL per line; # comments allowed")
        p.add_argument("--limit", type=int, default=200, help="page cap (1-200)")

    plan = commands.add_parser("plan", help="policy verdict per URL; no network")
    url_args(plan)
    plan.set_defaults(func=_cmd_plan)

    crawl = commands.add_parser("crawl", help="manual bounded HTTP acquisition")
    url_args(crawl)
    crawl.add_argument("--operator", help="the named human running this (required)")
    crawl.add_argument("--dry-run", action="store_true",
                       help="robots.txt only; no target page, no database write")
    crawl.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    crawl.set_defaults(func=_cmd_crawl)

    report = commands.add_parser("report", help="print a run report from the database")
    report.add_argument("run_id")
    report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    if args.command == "crawl" and not args.dry_run and not (args.operator or "").strip():
        parser.error("crawl requires --operator (LIVE.4: a named human starts every run)")
    if args.command in ("plan", "crawl") and not 1 <= args.limit <= 200:
        parser.error("--limit must be between 1 and 200")
    try:
        return args.func(args)
    except (SQLAlchemyError, ConfigurationError, DiscoveryError, OSError) as exc:
        # Connection errors can contain credentials: print the class only.
        print(f"ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
