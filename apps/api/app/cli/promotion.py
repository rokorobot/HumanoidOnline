"""Approved catalogue promotion (workstream B). Operator and CI entry point.

    uv run --directory apps/api python -m app.cli.promotion propose --robot unitree-g1 \\
        --edition G1 --claim <claim-id> --definition compute_base \\
        --value "8-core high-performance CPU" --promotion-id 2026-10-19-unitree-g1-compute
    ... render  --manifest db/catalogue/promotions/<id>.json
    ... verify  --manifest db/catalogue/promotions/<id>.json --base-ref origin/main
    ... execute --manifest ... --commit <sha> --approved-pr N [--dry-run] [--receipt PATH]
    ... decide  --manifest ... --reject|--defer --reason "..." --by "Name"

Exit codes
    0  ok (propose: ROUTINE manifest written; execute: SUCCESS, ALREADY_APPLIED or DRY_RUN_OK)
    1  verify failed
    2  refused (propose: nothing proposable; execute: REFUSED:<step>) or a usage error
    3  propose wrote a manifest that is NOT fast-lane (REVIEW_REQUIRED / RESTRICTED);
       execute: INCIDENT:<step> (failed after commit, incident opened, safety branch kept)
    4  configuration or database/HTTP failure (only the exception TYPE is printed)

`propose` reads production READ-ONLY (the session is opened `default_transaction_read_only`).
`execute` is bound to the merged manifest PR (`--approved-pr`): the PR must be merged into main
as `--commit` by a login in PROMOTION_APPROVERS (comma-separated; unset = refuse) and change only
the manifest, its review and the scoped robot files. `--no-github` replaces incident/comment
output only; combined with `--local-branches` (a non-production pilot) the approval is
SIMULATED_LOCAL and recorded as such. Production runs as the additions-only role, never as the
schema owner. Secrets are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from app.services.discovery import promotion_manifest as pm

DEFAULT_CATALOGUE = pm.REPO_ROOT / "db" / "catalogue"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=pm.REPO_ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def materialize_base(ref: str, target: Path) -> Path:
    """db/catalogue as of git `ref` (promotions/ excluded) into `target`."""
    names = _git("ls-tree", "-r", "--name-only", ref, "db/catalogue").splitlines()
    for name in names:
        rel = name[len("db/catalogue/"):]
        if rel.startswith(pm.PROMOTIONS_SUBDIR + "/"):
            continue
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob = subprocess.run(["git", "show", f"{ref}:{name}"], cwd=pm.REPO_ROOT, check=True,
                              capture_output=True).stdout
        dest.write_bytes(blob)
    return target


def read_at_commit(commit: str, path: str) -> str:
    """A file as committed at `commit` (never the working tree)."""
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=pm.REPO_ROOT, check=True,
                          capture_output=True).stdout.decode("utf-8")


def _load_manifest(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------- #
def cmd_propose(args) -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    url = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        print("no database URL: pass --database-url or set DATABASE_URL", file=sys.stderr)
        return 4
    catalogue = Path(args.catalogue_dir)
    if args.items:
        items = json.loads(Path(args.items).read_text(encoding="utf-8"))
    else:
        missing = [f for f in ("claim", "definition", "value") if getattr(args, f) is None]
        if missing:
            print("give --items FILE, or --claim, --definition and --value", file=sys.stderr)
            return 2
        items = [{"claim_id": args.claim, "definition": args.definition,
                  "proposed_value": args.value, "variant_slug": args.variant,
                  "interpretation": args.interpretation, "evidence_locator": args.locator,
                  "display": args.display}]
    for item in items:
        item.setdefault("edition", args.edition)
    edition_map = dict(e.split("=", 1) for e in args.edition_map or [])
    if args.edition:
        edition_map.setdefault(args.robot, args.edition)
    try:
        base_commit = args.base_commit or _git("rev-parse", "origin/main")
    except (subprocess.CalledProcessError, OSError):
        base_commit = args.base_commit or _git("rev-parse", "HEAD")
    today = date.fromisoformat(args.today) if args.today else datetime.now(UTC).date()
    promotion_id = args.promotion_id or f"{today.isoformat()}-{args.robot}"
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(
        url, connect_args={"options": "-csearch_path=humanoid,public "
                                      "-cdefault_transaction_read_only=on"})
    try:
        with Session(engine) as session:
            manifest = pm.propose(session, args.robot, items, catalogue_dir=catalogue,
                                  base_commit=base_commit, promotion_id=promotion_id,
                                  today=today, edition_map=edition_map,
                                  reconsider=args.reconsider)
    except pm.ProposalRefused as exc:
        print(f"PROPOSAL REFUSED: {exc}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(f"DATABASE ERROR ({type(exc).__name__}): check the connection URL.",
              file=sys.stderr)
        return 4
    finally:
        engine.dispose()

    routine = all(i["classification"] == pm.ROUTINE for i in manifest["items"])
    out_dir = Path(args.dry_run_output) if args.dry_run_output else catalogue / pm.PROMOTIONS_SUBDIR
    _write_json(out_dir / f"{promotion_id}.json", manifest)
    (out_dir / f"{promotion_id}.md").write_text(pm.render_review(manifest), encoding="utf-8")
    edited: list[str] = []
    if routine and not args.dry_run_output:
        edited = pm.apply_to_catalogue(manifest, catalogue)
    print(f"promotion {promotion_id}: {'ROUTINE' if routine else 'NOT fast-lane'}  "
          f"digest {manifest['digest']}")
    for item in manifest["items"]:
        print(f"  {item['definition']} = {item['proposed_value']!r}  "
              f"[{item['classification']}]  claim {item['claim_id']}")
        for reason in item["reasons"]:
            print(f"    - {reason}")
    print(f"wrote {out_dir / (promotion_id + '.json')} and .md"
          + (f"; edited catalogue: {', '.join(edited)}" if edited else
             "; catalogue NOT edited" + (" (dry-run output)" if args.dry_run_output else "")))
    return 0 if routine else 3


def cmd_render(args) -> int:
    print(pm.render_review(_load_manifest(args.manifest)))
    return 0


def cmd_verify(args) -> int:
    manifest = _load_manifest(args.manifest)
    path = Path(args.manifest)
    problems = []
    if path.stem != manifest.get("promotion_id"):
        problems.append("manifest file name does not match promotion_id")
    review = path.with_suffix(".md")
    if not review.exists():
        problems.append(f"missing review file {review.name}")
    elif review.read_text(encoding="utf-8").replace("\r\n", "\n") != pm.render_review(manifest):
        problems.append("review file is not the rendering of the manifest")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            base = materialize_base(args.base_ref, Path(tmp))
        except (subprocess.CalledProcessError, OSError):
            print(f"cannot read the base catalogue at {args.base_ref!r}", file=sys.stderr)
            return 4
        result = pm.verify(manifest, base_catalogue_dir=base,
                           head_catalogue_dir=Path(args.catalogue_dir))
    problems += result.reasons
    for line in problems:
        print(f"VERIFY FAIL: {line}")
    if not problems:
        print(f"VERIFY OK: {manifest['promotion_id']} digest {manifest['digest'][:16]}")
    return 1 if problems else 0


def cmd_decide(args) -> int:
    manifest = _load_manifest(args.manifest)
    decision = "REJECT" if args.reject else "DEFER"
    entry = pm.record_decision(Path(args.catalogue_dir), manifest, decision, args.reason,
                               args.by, date.fromisoformat(args.today) if args.today
                               else datetime.now(UTC).date())
    print(f"recorded {decision} for {entry['promotion_id']} ({len(entry['claim_ids'])} claim(s))")
    return 0


def cmd_execute(args) -> int:
    from app.services.discovery import promotion_execute as px

    # network adapters live in db/ (outside the app tree's no-HTTP-client guard)
    ad = pm.load_db_tool("promotion_adapters")
    manifest = _load_manifest(args.manifest)
    try:
        head = _git("rev-parse", "HEAD")
    except (subprocess.CalledProcessError, OSError):
        head = None
    if head != args.commit:
        print("REFUSED: the working tree is not at --commit (the approved merge commit)",
              file=sys.stderr)
        return 2
    url = args.database_url or os.environ.get("CATALOGUE_DATABASE_URL")
    if not url:
        print("no production URL: set CATALOGUE_DATABASE_URL", file=sys.stderr)
        return 4
    try:
        if args.local_branches:
            if not args.source_db:
                print("--local-branches needs --source-db", file=sys.stderr)
                return 4
            branches = px.LocalBranches(args.local_branches, args.source_db)
        else:
            branches = ad.NeonBranches(production_url=url)
        if args.no_github:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print("--no-github is for local pilots only", file=sys.stderr)
                return 4
            github = _NullGithub()
        else:
            github = ad.GithubApi(args.commit)
        # --no-github does not bypass approval. Only a local-database pilot may go without
        # GitHub, and its receipt says so.
        if args.no_github and args.local_branches:
            approvals = _SimulatedLocalApprovals()
        else:
            approvals = ad.GithubApprovals()
    except RuntimeError as exc:
        print(f"CONFIGURATION ERROR: {exc}", file=sys.stderr)
        return 4
    approvers = [a for a in os.environ.get("PROMOTION_APPROVERS", "").split(",") if a.strip()]
    web = ad.HttpWeb() if args.api_base and args.web_base else None
    if not args.dry_run and web is None and not args.skip_public_verify:
        print("--api-base and --web-base are required (or --skip-public-verify)", file=sys.stderr)
        return 4
    with tempfile.TemporaryDirectory() as tmp:
        try:
            base = materialize_base(args.base_ref or f"{args.commit}^", Path(tmp))
        except (subprocess.CalledProcessError, OSError):
            print("REFUSED: cannot read the base catalogue", file=sys.stderr)
            return 4
        receipt = px.execute(
            manifest, commit=args.commit, production=px.StaticProduction(url),
            branches=branches, github=github, approvals=approvals,
            approved_pr=args.approved_pr, approvers=approvers, read_at_commit=read_at_commit,
            web=web, api_base=args.api_base,
            web_base=args.web_base, catalogue_dir=Path(args.catalogue_dir),
            base_catalogue_dir=base, dry_run=args.dry_run)
    _write_json(Path(args.receipt), receipt)
    print(px.render_receipt(receipt))
    outcome = receipt["outcome"]
    if outcome in ("SUCCESS", "ALREADY_APPLIED", "DRY_RUN_OK"):
        return 0
    return 3 if outcome.startswith("INCIDENT") else 2


class _SimulatedLocalApprovals:
    """No PR is consulted: a local, non-production pilot only (the executor insists on
    local-database branches and records `approval: SIMULATED_LOCAL`)."""

    simulated = True

    def pull_request(self, number: int) -> dict:
        raise RuntimeError("a simulated approval has no pull request")


class _NullGithub:
    """Local pilots without GitHub: no incident can be read, and incidents go to stderr."""

    def open_incident_exists(self) -> bool:
        return False

    def open_incident(self, title: str, body: str) -> None:
        print(f"INCIDENT: {title}\n{body}", file=sys.stderr)

    def comment(self, body: str) -> None:
        return None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="promotion", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--catalogue-dir", default=str(DEFAULT_CATALOGUE))

    p = sub.add_parser("propose", parents=[common])
    p.add_argument("--robot", required=True)
    p.add_argument("--items", help="JSON list of items (claim_id, definition, proposed_value...)")
    p.add_argument("--claim")
    p.add_argument("--definition")
    p.add_argument("--value")
    p.add_argument("--variant")
    p.add_argument("--edition")
    p.add_argument("--edition-map", action="append", metavar="ROBOT=EDITION")
    p.add_argument("--interpretation")
    p.add_argument("--locator")
    p.add_argument("--display")
    p.add_argument("--promotion-id")
    p.add_argument("--database-url", help="read-only; default DATABASE_URL")
    p.add_argument("--base-commit")
    p.add_argument("--today", help="YYYY-MM-DD (default: today UTC)")
    p.add_argument("--reconsider", action="store_true")
    p.add_argument("--dry-run-output", metavar="DIR",
                   help="write manifest and review here; do not edit the catalogue")
    p.set_defaults(func=cmd_propose)

    p = sub.add_parser("render")
    p.add_argument("--manifest", required=True)
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("verify", parents=[common])
    p.add_argument("--manifest", required=True)
    p.add_argument("--base-ref", required=True)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("decide", parents=[common])
    p.add_argument("--manifest", required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--reject", action="store_true")
    group.add_argument("--defer", action="store_true")
    p.add_argument("--reason", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--today")
    p.set_defaults(func=cmd_decide)

    p = sub.add_parser("execute", parents=[common])
    p.add_argument("--manifest", required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--approved-pr", required=True, type=int, metavar="N",
                   help="the merged manifest PR that approved this run")
    p.add_argument("--base-ref", help="default: <commit>^")
    p.add_argument("--database-url", help="default: CATALOGUE_DATABASE_URL")
    p.add_argument("--local-branches", metavar="ADMIN_URL")
    p.add_argument("--source-db")
    p.add_argument("--api-base")
    p.add_argument("--web-base")
    p.add_argument("--skip-public-verify", action="store_true")
    p.add_argument("--no-github", action="store_true",
                   help="no incident issue / PR comment; does NOT bypass approval "
                        "(with --local-branches the approval is SIMULATED_LOCAL)")
    p.add_argument("--receipt", default="promotion-receipt.json")
    p.add_argument("--dry-run", action="store_true",
                   help="stop after the rehearsal; production is never written")
    p.set_defaults(func=cmd_execute)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR ({type(exc).__name__}): {exc}" if isinstance(exc, ValueError | KeyError)
              else f"ERROR ({type(exc).__name__})", file=sys.stderr)
        return 4
    except Exception as exc:    # DB / HTTP: the type only, never a connection string
        print(f"ERROR ({type(exc).__name__})", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
