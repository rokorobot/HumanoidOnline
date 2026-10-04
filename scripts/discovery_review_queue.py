#!/usr/bin/env python3
"""Maintain ONE GitHub issue that is the human discovery-review inbox (G5-4).

The database is canonical; the issue is only an operational pointer. It is identified by a stable
machine marker in its body (never by title alone), so there is at most one managed issue.

Policy (pure function `decide`, unit-tested):
- A technical execution failure, or an incomplete/unavailable queue report, changes nothing.
- Actionable items exist and no managed issue: create it. Closed: reopen and reuse it.
- Same queue digest: do nothing (no edit, no comment, no notification).
- Changed digest: edit the body; comment only when new items appeared this run.
- Close ONLY when the report proves the GLOBAL queue is empty (complete report, total == 0).
  One quiet cycle is never proof of emptiness.

Usage: discovery_review_queue.py issue --report cycle.json --code 4 --run-url URL [--dry-run]
       discovery_review_queue.py headline --code N
Needs GH_TOKEN (the workflow's GITHUB_TOKEN with issues: write) and the `gh` CLI.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass

TITLE = "Discovery review queue"
MARKER = "<!-- humanoidonline-discovery-review-queue -->"
DIGEST_RE = re.compile(r"<!-- queue-digest: ([0-9a-f]{64}) -->")
NOOP, CREATE, UPDATE, REOPEN, CLOSE = "NOOP", "CREATE", "UPDATE", "REOPEN", "CLOSE"


@dataclass(frozen=True)
class Action:
    kind: str
    reason: str
    number: int | None = None
    body: str | None = None
    comment: str | None = None


def headline(code: str) -> tuple[str, str]:
    """(workflow annotation level, headline) for a CLI exit code. Red means something broke."""
    if code == "0":
        return "notice", "NO ACTION NEEDED: cycle completed; nothing requires a human."
    if code == "4":
        return "warning", ("REVIEW REQUIRED — discovery completed successfully; human review "
                           "queue has actionable items.")
    return "error", (f"EXECUTION FAILURE (exit {code or 'none'}): a source run failed or the "
                     "cycle could not run.")


def workflow_fails(code: str) -> bool:
    return code not in ("0", "4")


def render_body(hr: dict, run_url: str) -> str:
    new = hr["new_this_cycle"]
    return "\n".join([
        MARKER, f"<!-- queue-digest: {hr['queue_digest']} -->", "",
        "Operational inbox for the HumanoidOnline discovery review queue. The database is "
        "canonical; this issue is only a pointer and is maintained by "
        "`scripts/discovery_review_queue.py`.", "",
        f"- Proposals awaiting a decision: **{hr['proposals_awaiting_decision']}**",
        f"- Identity-review items: **{hr['identity_review_items']}**",
        f"- Source-policy review items: **{hr['source_review_items']}**",
        f"- New in the latest meaningful run: {new['total']} "
        f"(proposals {new['proposals']}, identity {new['identity_items']})",
        f"- Queue digest: `{hr['queue_digest'][:16]}`",
        f"- Latest meaningful run: {run_url}", "",
        "Review with `python -m app.cli.discovery proposals list` and "
        "`python -m app.cli.discovery review`. Decisions are made by a human only."])


def managed(issues: list[dict]) -> dict | None:
    mine = sorted((i for i in issues if MARKER in (i.get("body") or "")),
                  key=lambda i: i["number"])
    return mine[0] if mine else None


def decide(report: dict | None, issues: list[dict], run_url: str, code: str) -> Action:
    if workflow_fails(code):
        return Action(NOOP, "technical failure: the queue is not touched")
    hr = (report or {}).get("human_review")
    if not hr or not hr.get("complete") or hr.get("total") is None:
        return Action(NOOP, "global queue could not be established: nothing is inferred")
    issue = managed(issues)
    if hr["total"] > 0:
        body = render_body(hr, run_url)
        if issue is None:
            return Action(CREATE, "actionable items and no managed issue", body=body)
        if issue.get("state", "").upper() == "CLOSED":
            return Action(REOPEN, "actionable items again: reuse the managed issue",
                          number=issue["number"], body=body,
                          comment="New actionable review items. " + run_url)
        old = DIGEST_RE.search(issue.get("body") or "")
        if old and old.group(1) == hr["queue_digest"]:
            return Action(NOOP, "queue digest unchanged", number=issue["number"])
        comment = (f"{hr['new_this_cycle']['total']} new review item(s). {run_url}"
                   if hr["new_this_cycle"]["total"] > 0 else None)
        return Action(UPDATE, "queue digest changed", number=issue["number"], body=body,
                      comment=comment)
    if issue is not None and issue.get("state", "").upper() == "OPEN":
        return Action(CLOSE, "the global queue is provably empty", number=issue["number"],
                      comment="The review queue is empty (complete report: 0 proposals, 0 "
                              "identity items, 0 source-review items). " + run_url)
    return Action(NOOP, "queue empty and no open managed issue")


def _gh(*args: str, input_: str | None = None) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True,
                          input=input_).stdout


def list_issues() -> list[dict]:
    out = _gh("issue", "list", "--state", "all", "--search", f'in:title "{TITLE}"',
              "--limit", "50", "--json", "number,state,title,body")
    return [i for i in json.loads(out) if i.get("title") == TITLE]


def apply(action: Action) -> None:
    if action.kind == CREATE:
        _gh("issue", "create", "--title", TITLE, "--body-file", "-", input_=action.body)
        return
    n = str(action.number)
    if action.kind == REOPEN:
        _gh("issue", "reopen", n)
    if action.kind in (REOPEN, UPDATE):
        _gh("issue", "edit", n, "--body-file", "-", input_=action.body)
    if action.comment:
        _gh("issue", "comment", n, "--body", action.comment)
    if action.kind == CLOSE:
        _gh("issue", "close", n, "--reason", "completed")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("headline")
    h.add_argument("--code", default="")
    i = sub.add_parser("issue")
    i.add_argument("--report", required=True)
    i.add_argument("--code", required=True)
    i.add_argument("--run-url", required=True)
    i.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "headline":
        level, text = headline(args.code)
        print(f"::{level}::{text}" if level != "notice" else text)
        return 1 if workflow_fails(args.code) else 0
    try:
        report = json.load(open(args.report, encoding="utf-8"))
    except (OSError, ValueError):
        report = None
    action = decide(report, [] if workflow_fails(args.code) else list_issues(), args.run_url,
                    args.code)
    print(f"review queue: {action.kind} ({action.reason})")
    if not args.dry_run:
        apply(action)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
