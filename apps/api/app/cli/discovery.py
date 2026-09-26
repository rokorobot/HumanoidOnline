"""Discovery operator CLI (docs/16 §14): sources, plan / crawl / report, adapters.

    python -m app.cli.discovery source register <key> --name N --class C --homepage URL --by WHO
    python -m app.cli.discovery source review   <key> --reviewed-by WHO --tos-decision D
                                                --robots-decision D --path-prefix /p/ ...
                                                [--tos-url U] [--robots-url U] [--notes T]
    python -m app.cli.discovery source enable   <key> --by WHO
    python -m app.cli.discovery source disable  <key> --by WHO --reason WHY
    python -m app.cli.discovery source show     <key>
    python -m app.cli.discovery plan   <source-key> --url URL [--url URL ...] [--urls-file F]
    python -m app.cli.discovery crawl  <source-key> --operator "Name" --url URL ...
                                       [--limit N] [--dry-run] [--cache-dir DIR]
    python -m app.cli.discovery adapter plan <source-key>
    python -m app.cli.discovery adapter run  <source-key> --operator "Name" [--cache-dir DIR]
    python -m app.cli.discovery report <run-id>

- `source *` never makes a network request. `review` records the owner's own
  decisions (DR-A4: he reads the terms himself) and never enables; `enable` is a
  separate attributed act that refuses unless the review allows acquisition.
- `adapter plan` prints why the reviewed adapter module may or may not run
  against the registered source. No request, no write.
- `adapter run` is a MANUAL run of the source's reviewed adapter module:
  reviewed seeds, ONE level of product/announcement URLs (same host, approved
  prefixes, adapter pattern, robots-allowed, capped; the rest deferred and
  listed), extraction into discovery-layer rows, existing identity resolution.

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
_RUN_EXIT = {"COMPLETED": 0, "HALTED_BY_POLICY": HALTED, "CANCELLED": CANCELLED}
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
        return _RUN_EXIT.get(run.status, 1)


def _cmd_source(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal
    from app.services.discovery import source_registry as registry

    with SessionLocal() as session:
        if args.action == "register":
            source = registry.register_source(
                session, key=args.key, name=args.name, source_class=args.source_class,
                homepage_url=args.homepage, registered_by=args.by)
        elif args.action == "review":
            registry.review_source(
                session, args.key, reviewed_by=args.reviewed_by,
                tos_decision=args.tos_decision, robots_decision=args.robots_decision,
                path_prefixes=args.path_prefix or [], tos_url=args.tos_url,
                robots_url=args.robots_url, notes=args.notes)
            source = registry.get_source(session, args.key)
        elif args.action == "enable":
            source = registry.enable_source(session, args.key, by=args.by)
        elif args.action == "disable":
            source = registry.disable_source(session, args.key, by=args.by, reason=args.reason)
        else:
            source = registry.get_source(session, args.key)
        if args.action != "show":
            session.commit()
        print("\n".join(registry.describe(source)))
    return 0


def _cmd_adapter(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal
    from app.services.discovery.acquisition import AcquisitionRefused
    from app.services.discovery.adapter_run import AdapterRefused, plan_adapter, run_adapter
    from app.services.discovery.fetcher import FetchLimits, HttpFetcher
    from app.services.discovery.sources import adapter_for

    config = adapter_for(args.source_key)
    if config is None:
        print(f"REFUSED: no reviewed adapter module for {args.source_key!r}", file=sys.stderr)
        return REFUSED
    with SessionLocal() as session:
        source = _load_source(session, args.source_key)
        if args.action == "plan":
            problems = plan_adapter(config, source)
            print(f"ADAPTER {config.key}@{config.version} source={args.source_key} "
                  "(no request issued)")
            for seed in config.seed_urls:
                print(f"  SEED {seed}")
            for problem in problems:
                print(f"  REFUSED {problem}")
            print("  RUNNABLE" if not problems else "  NOT RUNNABLE")
            return 0 if not problems else REFUSED
        limits = FetchLimits(page_cap=min(200, len(config.seed_urls) + config.target_cap))
        with HttpFetcher(limits=limits, kill_switch=kill_switch_for(args.source_key)) as fetcher:
            try:
                run = run_adapter(session, source=source, config=config,
                                  operator=args.operator or "", fetcher=fetcher,
                                  cache_dir=Path(args.cache_dir), checkpoint=session.commit)
            except (AdapterRefused, AcquisitionRefused) as exc:
                session.rollback()
                return _print_refusal(exc)
        print(f"RUN {run.id} status={run.status}")
        print(f"report: python -m app.cli.discovery report {run.id}")
        return _RUN_EXIT.get(run.status, 1)


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
    parser = argparse.ArgumentParser(description="Discovery — sources and bounded acquisition")
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

    source = commands.add_parser("source", help="governed source registration (no network)")
    actions = source.add_subparsers(dest="action", required=True)
    register = actions.add_parser("register", help="register a DISABLED source")
    register.add_argument("key")
    register.add_argument("--name", required=True)
    register.add_argument("--class", dest="source_class", required=True)
    register.add_argument("--homepage", required=True, help="https origin, e.g. https://x.com/")
    register.add_argument("--by", required=True)
    review = actions.add_parser("review", help="record the owner's review; never enables")
    review.add_argument("key")
    review.add_argument("--reviewed-by", required=True)
    review.add_argument("--tos-decision", required=True,
                        choices=["ALLOWED", "RESTRICTED", "PROHIBITED", "UNKNOWN"])
    review.add_argument("--robots-decision", required=True,
                        choices=["ALLOWED", "DISALLOWED", "NOT_APPLICABLE", "UNKNOWN"])
    review.add_argument("--path-prefix", action="append", help="approved path prefix (repeat)")
    review.add_argument("--tos-url")
    review.add_argument("--robots-url")
    review.add_argument("--notes")
    enable = actions.add_parser("enable", help="enable a reviewed, ToS-ALLOWED source")
    enable.add_argument("key")
    enable.add_argument("--by", required=True)
    disable = actions.add_parser("disable", help="disable a source")
    disable.add_argument("key")
    disable.add_argument("--by", required=True)
    disable.add_argument("--reason", required=True)
    show = actions.add_parser("show", help="print a source's recorded state")
    show.add_argument("key")
    source.set_defaults(func=_cmd_source)

    adapter = commands.add_parser("adapter", help="the source's reviewed adapter module")
    adapter_actions = adapter.add_subparsers(dest="action", required=True)
    adapter_plan = adapter_actions.add_parser("plan", help="why it may / may not run; no network")
    adapter_plan.add_argument("source_key")
    adapter_run = adapter_actions.add_parser("run", help="manual adapter run (live network)")
    adapter_run.add_argument("source_key")
    adapter_run.add_argument("--operator", required=True,
                             help="the named human running this (LIVE.4)")
    adapter_run.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    adapter.set_defaults(func=_cmd_adapter)

    report = commands.add_parser("report", help="print a run report from the database")
    report.add_argument("run_id")
    report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    if args.command == "crawl" and not args.dry_run and not (args.operator or "").strip():
        parser.error("crawl requires --operator (LIVE.4: a named human starts every run)")
    if args.command == "adapter" and args.action == "run" and not args.operator.strip():
        parser.error("adapter run requires --operator (LIVE.4: a named human starts every run)")
    if args.command in ("plan", "crawl") and not 1 <= args.limit <= 200:
        parser.error("--limit must be between 1 and 200")
    try:
        return args.func(args)
    except DiscoveryError as exc:
        # Policy refusals are written by this codebase, never from a connection
        # string, so the operator gets the reason.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (SQLAlchemyError, ConfigurationError, OSError) as exc:
        # Connection errors can contain credentials: print the class only.
        print(f"ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
