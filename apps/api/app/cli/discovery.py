"""Discovery operator CLI (docs/16 §14): sources, plan / crawl / report, adapters.

    python -m app.cli.discovery source register <key> --name N --class C --homepage URL --by WHO
    python -m app.cli.discovery source review   <key> --reviewed-by WHO --tos-decision D
                                                --robots-decision D --path-prefix /p/ ...
                                                [--tos-url U] [--robots-url U] [--notes T]
    python -m app.cli.discovery source enable   <key> --by WHO
    python -m app.cli.discovery source disable  <key> --by WHO --reason WHY
    python -m app.cli.discovery source show     <key>
    python -m app.cli.discovery source cadence  <key> (--every 24h|7d | --off) --by WHO
    python -m app.cli.discovery observe [--plan] [--only KEY] [--report-json PATH]
    python -m app.cli.discovery cache prune [--apply] [--cache-dir DIR]
    python -m app.cli.discovery plan   <source-key> --url URL [--url URL ...] [--urls-file F]
    python -m app.cli.discovery crawl  <source-key> --operator "Name" --url URL ...
                                       [--limit N] [--dry-run] [--cache-dir DIR]
    python -m app.cli.discovery crawl  <source-key> --operator "Name" --resume <run-id>
    python -m app.cli.discovery adapter plan <source-key>
    python -m app.cli.discovery adapter run  <source-key> --operator "Name" [--resume <run-id>]
    python -m app.cli.discovery run fail <run-id> --by WHO --reason WHY
    python -m app.cli.discovery report <run-id>
    python -m app.cli.discovery review list
    python -m app.cli.discovery review show <candidate-id>
    python -m app.cli.discovery review history <candidate-id>
    python -m app.cli.discovery review same-as <candidate-a> <candidate-b> --by WHO --reason WHY
    python -m app.cli.discovery review not-same-as <candidate-a> <candidate-b> --by WHO --reason WHY
    python -m app.cli.discovery review reject <candidate-id> --reason-code OUT_OF_SCOPE
                                       --by WHO --reason WHY
    python -m app.cli.discovery review propose-alias <candidate-id> <robot-slug>
    python -m app.cli.discovery review trace <candidate-id> --source KEY --url URL --by WHO

- `review` is the Stage E exception-only workflow (docs/16 §17.1). `list`,
  `show`, `history` and `propose-alias` never write; `propose-alias` only PRINTS
  a register entry for a human to confirm in a reviewed change. `same-as`,
  `not-same-as` and `reject` append attributed history (nothing is merged or
  deleted) and re-run the deterministic pipeline on the affected candidates.
  `trace` records a confirmed authoritative trace through the existing
  record_trace path: the source must be an official class and approve the URL's
  host/path; an identical re-record is a no-op, a different one is refused.
  Nothing here promotes.

- `--resume` continues a FAILED or CANCELLED run as a NEW run linked to it, with
  the parent's manifest and limits, fetching only planned URLs the run chain has
  not fetched successfully. It never re-requests or duplicates an observation.
  A COMPLETED or HALTED_BY_POLICY run is not resumable; neither is a RUNNING
  one until `run fail` has recorded that its process is gone.
- `run fail` is the governed recovery for a run whose process died without
  recording an end: attributed, with a reason, refused while the run shows
  activity in the last 30 minutes.

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

- `observe` (Stage F, docs/16 §17.2) runs ONE observation cycle over every
  enabled source that has a cadence and is due, through each source's reviewed
  adapter (the same gates as `adapter run`). A failing source never stops the
  others; a policy halt is not retried; a FAILED run is resumed at most once.
  `--plan` shows what a cycle would do: no request, no write. Nothing here
  decides a Stage E question, confirms an alias, traces or promotes.
  Exit: 0 nothing needs a human, 4 a source or new review item needs a human,
  1 a source run failed.
- `source cadence` sets the attributed observation interval (6h..90d) or turns
  it off. It never enables a source and never fetches.
- `cache prune` applies the LIVE.10 retention to raw bodies (90 days; latest
  observation of each URL and open runs always kept; provenance never removed).
  Dry run unless `--apply`.

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


def _parent_limits(session, run_id: str):
    """The resumed run's FetchLimits, read from its manifest (same manifest, §7)."""
    from app.models.acquisition import CrawlRun
    from app.services.discovery.fetcher import FetchLimits

    parent = session.get(CrawlRun, uuid.UUID(run_id))
    limits = (parent.run_manifest or {}).get("limits") if parent is not None else None
    return FetchLimits(**limits) if limits else None


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
        resume_acquisition,
        run_acquisition,
    )
    from app.services.discovery.fetcher import FetchLimits, HttpFetcher

    urls = _urls(args)
    with SessionLocal() as session:
        limits = FetchLimits(page_cap=args.limit)
        if args.resume:
            limits = _parent_limits(session, args.resume) or limits
        with HttpFetcher(limits=limits, kill_switch=kill_switch_for(args.source_key)) as fetcher:
            source = _load_source(session, args.source_key)
            try:
                if args.dry_run:
                    result = dry_run(source, urls, fetcher)
                    print(f"DRY RUN source={args.source_key}: robots.txt only, "
                          "no target page requested, nothing written")
                    for url, decision in result.decisions:
                        print(f"  {decision:<40} {url}")
                    return 0
                if args.resume:
                    run = resume_acquisition(
                        session, parent_run_id=uuid.UUID(args.resume), source=source,
                        operator=args.operator or "", fetcher=fetcher,
                        cache_dir=Path(args.cache_dir), checkpoint=session.commit)
                else:
                    run = run_acquisition(
                        session, source=source, urls=urls, operator=args.operator or "",
                        fetcher=fetcher, cache_dir=Path(args.cache_dir),
                        checkpoint=session.commit)
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
        elif args.action == "cadence":
            source = registry.set_cadence(session, args.key,
                                          every=None if args.off else args.every, by=args.by)
        else:
            source = registry.get_source(session, args.key)
        if args.action != "show":
            session.commit()
        print("\n".join(registry.describe(source)))
    return 0


def _cmd_adapter(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal
    from app.services.discovery.acquisition import AcquisitionRefused
    from app.services.discovery.adapter_run import (
        AdapterRefused,
        index_adapter,
        plan_adapter,
        resume_adapter,
        run_adapter,
    )
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
        if args.resume:
            limits = _parent_limits(session, args.resume) or limits
        with HttpFetcher(limits=limits, kill_switch=kill_switch_for(args.source_key)) as fetcher:
            try:
                if args.index_only:
                    run = index_adapter(
                        session, source=source, config=config, operator=args.operator or "",
                        fetcher=fetcher, cache_dir=Path(args.cache_dir),
                        checkpoint=session.commit)
                elif args.resume:
                    run = resume_adapter(
                        session, parent_run_id=uuid.UUID(args.resume), source=source,
                        config=config, operator=args.operator or "", fetcher=fetcher,
                        cache_dir=Path(args.cache_dir), checkpoint=session.commit)
                else:
                    run = run_adapter(
                        session, source=source, config=config,
                        operator=args.operator or "", fetcher=fetcher,
                        cache_dir=Path(args.cache_dir), checkpoint=session.commit)
            except (AdapterRefused, AcquisitionRefused) as exc:
                session.rollback()
                return _print_refusal(exc)
        print(f"RUN {run.id} status={run.status}")
        if args.index_only:
            from app.services.discovery.acquisition import build_report

            print(build_report(session, run.id))
        print(f"report: python -m app.cli.discovery report {run.id}")
        return _RUN_EXIT.get(run.status, 1)


def _cmd_run(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal
    from app.services.discovery.acquisition import mark_stale_run_failed

    with SessionLocal() as session:
        run = mark_stale_run_failed(session, uuid.UUID(args.run_id), by=args.by,
                                    reason=args.reason)
        session.commit()
        print(f"RUN {run.id} status={run.status} ({run.counters.get('halt_reason')})")
        print(f"resume: python -m app.cli.discovery crawl|adapter run ... --resume {run.id}")
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    import json

    from app.db.session import SessionLocal
    from app.services.discovery import review

    with SessionLocal() as session:
        if args.action == "list":
            items = review.review_queue(session)
            print(f"REVIEW QUEUE ({len(items)} item(s) needing a human)")
            for item in items:
                ids = " ".join(str(i) for i in item.candidate_ids)
                print(f"  {item.kind:<24} {item.summary}\n  {'':<24} {ids}")
            return 0
        if args.action == "show":
            print("\n".join(review.show(session, uuid.UUID(args.candidate_id))))
            return 0
        if args.action == "history":
            lines = review.history(session, uuid.UUID(args.candidate_id))
            print("\n".join(lines) if lines else "(no history)")
            return 0
        if args.action == "propose-alias":
            entry = review.propose_alias(session, uuid.UUID(args.candidate_id), args.robot_slug)
            print("PROPOSAL ONLY: nothing was written. To make it effective, add this entry to")
            print("db/discovery/identity_aliases.json in a reviewed change, with the confirming")
            print("human's confirmed_by / confirmed_at set:")
            print(json.dumps(entry, indent=2, ensure_ascii=False))
            return 0
        if args.action == "trace":
            candidate, recorded = review.record_source_trace(
                session, uuid.UUID(args.candidate_id), source=args.source, url=args.url,
                by=args.by)
            session.commit()
            print(f"{'TRACE RECORDED' if recorded else 'TRACE ALREADY RECORDED'} "
                  f"{candidate.id} {candidate.trace_url} ({candidate.trace_source_type}) "
                  f"status={candidate.status}; not promoted")
            return 0
        if args.action in ("same-as", "not-same-as"):
            decision = review.SAME_ENTITY if args.action == "same-as" else review.NOT_SAME_ENTITY
            row, created = review.decide_pair(
                session, uuid.UUID(args.candidate_a), uuid.UUID(args.candidate_b), decision,
                decided_by=args.by, reason=args.reason)
            session.commit()
            print(f"{'RECORDED' if created else 'ALREADY IN EFFECT'} {row.decision} "
                  f"#{row.decision_seq} {row.candidate_a_id} {row.candidate_b_id}")
            return 0
        candidate = review.reject_candidate(session, uuid.UUID(args.candidate_id), by=args.by,
                                            reason=args.reason, reason_code=args.reason_code)
        session.commit()
        print(f"REJECTED {candidate.id} ({args.reason_code or 'no code'})")
        return 0


def _cmd_observe(args: argparse.Namespace) -> int:
    import json

    from app.db.session import SessionLocal
    from app.services.discovery.observe import observe
    from app.services.discovery.sources import ADAPTERS

    with SessionLocal() as session:
        result = observe(
            session, ADAPTERS, plan_only=args.plan, cache_dir=Path(args.cache_dir),
            kill_switch_for=kill_switch_for, only=args.only,
            checkpoint=None if args.plan else session.commit)
        if args.plan:
            session.rollback()
    print("\n".join(result.lines()))
    if args.report_json:
        path = Path(args.report_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return result.exit_code


def _cmd_cache(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal
    from app.services.discovery.cache_retention import prune_cache

    with SessionLocal() as session:
        report = prune_cache(session, Path(args.cache_dir), apply=args.apply)
    print("\n".join(report.lines()))
    return 0


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
    crawl.add_argument("--resume", metavar="RUN_ID",
                       help="continue a FAILED/CANCELLED run; no --url, no --dry-run")
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
    cadence = actions.add_parser("cadence", help="set the Stage F observation cadence")
    cadence.add_argument("key")
    every = cadence.add_mutually_exclusive_group(required=True)
    every.add_argument("--every", help="interval: whole hours or days, e.g. 24h, 7d (6h..90d)")
    every.add_argument("--off", action="store_true", help="stop scheduled observation")
    cadence.add_argument("--by", required=True)
    source.set_defaults(func=_cmd_source)

    observe_cmd = commands.add_parser("observe", help="one Stage F observation cycle")
    observe_cmd.add_argument("--plan", action="store_true",
                             help="what a cycle would do now; no request, no write")
    observe_cmd.add_argument("--only", metavar="SOURCE_KEY", help="consider one source only")
    observe_cmd.add_argument("--report-json", metavar="PATH",
                             help="also write the machine-readable cycle result")
    observe_cmd.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    observe_cmd.set_defaults(func=_cmd_observe)

    cache_cmd = commands.add_parser("cache", help="raw-body cache retention (LIVE.10)")
    cache_actions = cache_cmd.add_subparsers(dest="action", required=True)
    prune = cache_actions.add_parser("prune", help="report (or --apply) expired bodies")
    prune.add_argument("--apply", action="store_true", help="remove; default is a dry run")
    prune.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    cache_cmd.set_defaults(func=_cmd_cache)

    adapter = commands.add_parser("adapter", help="the source's reviewed adapter module")
    adapter_actions = adapter.add_subparsers(dest="action", required=True)
    adapter_plan = adapter_actions.add_parser("plan", help="why it may / may not run; no network")
    adapter_plan.add_argument("source_key")
    adapter_run = adapter_actions.add_parser("run", help="manual adapter run (live network)")
    adapter_run.add_argument("source_key")
    adapter_run.add_argument("--operator", required=True,
                             help="the named human running this (LIVE.4)")
    adapter_run.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    adapter_run.add_argument("--resume", metavar="RUN_ID",
                             help="continue a FAILED/CANCELLED adapter run")
    adapter_run.add_argument("--index-only", action="store_true",
                             help="fetch only the reviewed seeds and report what would be "
                                  "targeted; no target page, no extraction")
    adapter.set_defaults(func=_cmd_adapter)

    run_cmd = commands.add_parser("run", help="governed run lifecycle (no network)")
    run_actions = run_cmd.add_subparsers(dest="action", required=True)
    fail = run_actions.add_parser("fail", help="mark a stale RUNNING run FAILED")
    fail.add_argument("run_id")
    fail.add_argument("--by", required=True)
    fail.add_argument("--reason", required=True)
    run_cmd.set_defaults(func=_cmd_run)

    review_cmd = commands.add_parser("review", help="Stage E exception-only review (CLI)")
    review_actions = review_cmd.add_subparsers(dest="action", required=True)
    review_actions.add_parser("list", help="candidates needing a human; no write")
    for name in ("show", "history"):
        sub = review_actions.add_parser(name, help=f"{name} one candidate; no write")
        sub.add_argument("candidate_id")
    for name in ("same-as", "not-same-as"):
        sub = review_actions.add_parser(name, help="record a pairwise identity decision")
        sub.add_argument("candidate_a")
        sub.add_argument("candidate_b")
        sub.add_argument("--by", required=True)
        sub.add_argument("--reason", required=True)
    rej = review_actions.add_parser("reject", help="reject a candidate (existing path)")
    rej.add_argument("candidate_id")
    rej.add_argument("--reason-code", choices=["OUT_OF_SCOPE"])
    rej.add_argument("--by", required=True)
    rej.add_argument("--reason", required=True)
    trace = review_actions.add_parser("trace", help="record a confirmed authoritative trace")
    trace.add_argument("candidate_id")
    trace.add_argument("--source", required=True, help="official discovery source key or id")
    trace.add_argument("--url", required=True, help="the official page that traces the entity")
    trace.add_argument("--by", required=True)
    alias = review_actions.add_parser("propose-alias", help="print a register proposal; no write")
    alias.add_argument("candidate_id")
    alias.add_argument("robot_slug")
    review_cmd.set_defaults(func=_cmd_review)

    report = commands.add_parser("report", help="print a run report from the database")
    report.add_argument("run_id")
    report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    if args.command == "crawl" and not args.dry_run and not (args.operator or "").strip():
        parser.error("crawl requires --operator (LIVE.4: a named human starts every run)")
    if args.command == "adapter" and args.action == "run" and not args.operator.strip():
        parser.error("adapter run requires --operator (LIVE.4: a named human starts every run)")
    if args.command == "adapter" and args.action == "run" and args.index_only and args.resume:
        parser.error("--index-only and --resume cannot be combined")
    if args.command == "crawl" and args.resume and (_urls(args) or args.dry_run):
        parser.error("--resume takes its URLs from the resumed run: no --url/--urls-file, "
                     "no --dry-run")
    ids = [getattr(args, "resume", None), args.run_id if args.command == "run" else None]
    if args.command == "review":
        ids += [getattr(args, n, None) for n in ("candidate_id", "candidate_a", "candidate_b")]
    for run_id in ids:
        if run_id:
            try:
                uuid.UUID(run_id)
            except ValueError:
                parser.error(f"invalid id {run_id!r}")
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
