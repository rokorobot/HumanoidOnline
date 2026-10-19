"""Approved catalogue promotion: fail-closed execution (workstream B, design section 4).

`execute` runs after the owner merged a manifest PR. Every external system is an INJECTED
interface (`Branches`, `Production`, `Github`, `Web`, plus `clock`/`sleep`), so the whole
sequence is testable without Neon, GitHub or the network. The real adapters are at the bottom.

Order, each step recorded in the receipt:

  manifest -> approval -> halt_switch -> concurrency -> privileges -> already_applied
  -> eligibility -> base_drift -> safety_branch -> rehearsal -> apply -> post_verify
  -> public_verify -> receipt

Steps up to and including `rehearsal` write NOTHING to production. `apply` is the importer's
single transaction (no --authorize, so the fast lane cannot delete); inside it, under the
`catalogue-write` advisory lock and before the first write, the scoped robots' fingerprints are
re-checked. A failure after the commit opens a `promotion-incident` issue, keeps the safety
branch and does NOT roll back (restoring from the branch could overwrite concurrent legitimate
changes).

Hardening (owner decisions, 2026-10-19): the merged PR is the approval (`approval`); the
production role must be non-destructive (`privileges`); eligibility is re-derived from
production, not trusted from the manifest (`eligibility`); the safety branch must descend from
the production branch (`safety_branch`); public values are checked in their own row.

Outcomes: SUCCESS | ALREADY_APPLIED | DRY_RUN_OK | REFUSED:<step> | INCIDENT:<step>.
Secrets are never printed or recorded: only exception TYPES are reported for DB/HTTP failures.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import time
import urllib.error
import urllib.parse
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol

import psycopg

from app.services.discovery import promotion_manifest as pm

LOCK_SQL = "SELECT pg_try_advisory_lock(hashtext('catalogue-promotion'))"
UNLOCK_SQL = "SELECT pg_advisory_unlock(hashtext('catalogue-promotion'))"


# --------------------------------------------------------------------------------------- #
# Injected interfaces
# --------------------------------------------------------------------------------------- #
class Branches(Protocol):
    #: True when cloning needs the source database free of other connections (a local
    #: `CREATE DATABASE ... TEMPLATE`). The executor then releases its advisory lock around
    #: the clone and re-checks the baseline after re-acquiring it. Neon branches need no such.
    requires_exclusive_source: bool

    def create(self, name: str) -> str: ...
    def delete(self, name: str) -> None: ...

    # Optional, and always present on the real adapters: `verify_origin(production_url) -> dict`
    # proves the branches descend from the production database; `origins` maps a created branch
    # name to its recorded parent (id / LSN or template database); `local` is True only for
    # local-database branches (the only kind a SIMULATED_LOCAL approval may be used with).


class Production(Protocol):
    url: str


class Github(Protocol):
    def open_incident_exists(self) -> bool: ...
    def open_incident(self, title: str, body: str) -> None: ...
    def comment(self, body: str) -> None: ...


class Web(Protocol):
    def get(self, url: str) -> tuple[int, str]: ...


class Approvals(Protocol):
    """The merged manifest PR is the approval. `simulated` is True only for a local,
    non-production pilot without GitHub (never production)."""

    simulated: bool

    def pull_request(self, number: int) -> dict:
        """{merged, base_ref, head_sha, merge_commit_sha, merged_by, files: [paths]}."""
        ...


class BranchOriginError(RuntimeError):
    """A safety/rehearsal branch is not provably a copy of production. The message holds ids
    and names only, never a credential, so it may be reported (`safe`)."""

    safe = True


class Refused(Exception):
    def __init__(self, step: str, reason: str):
        super().__init__(f"{step}: {reason}")
        self.step, self.reason = step, reason


class Incident(Exception):
    def __init__(self, step: str, reason: str):
        super().__init__(f"{step}: {reason}")
        self.step, self.reason = step, reason


def _plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _err(exc: BaseException) -> str:
    return type(exc).__name__          # never the message: it may carry a connection string


def _why(exc: BaseException) -> str:
    """`_err`, plus the message for exceptions that declare it safe (no credentials)."""
    return f"{type(exc).__name__}: {exc}" if getattr(exc, "safe", False) else _err(exc)


# --------------------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------------------- #
class _Lock:
    """Session-level advisory lock on one dedicated production connection."""

    def __init__(self, url: str):
        self.url = url
        self.conn: psycopg.Connection | None = None

    def acquire(self) -> None:
        try:
            conn = psycopg.connect(_plain(self.url), autocommit=True, connect_timeout=15)
        except psycopg.Error as exc:
            raise Refused("concurrency", f"database unavailable ({_err(exc)})") from None
        try:
            if not conn.execute(LOCK_SQL).fetchone()[0]:
                raise Refused("concurrency", "another promotion holds the lock")
            running = conn.execute(
                "SELECT count(*) FROM humanoid.crawl_run WHERE status = 'RUNNING'").fetchone()[0]
            if running:
                raise Refused("concurrency", f"{running} discovery crawl_run(s) RUNNING")
        except BaseException:
            conn.close()
            raise
        self.conn = conn

    def release(self) -> None:
        if self.conn is not None:
            with contextlib.suppress(psycopg.Error):
                self.conn.execute(UNLOCK_SQL)
            with contextlib.suppress(psycopg.Error):
                self.conn.close()
            self.conn = None


def _query(url: str, sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(_plain(url), connect_timeout=15) as conn:
        conn.read_only = True
        return conn.execute(sql, params).fetchall()


POST_STATE_SQL = """
SELECT s.value_text, s.value_number, s.value_bool, s.source_url, s.observed_at::text
FROM humanoid.specification s
JOIN humanoid.robot r ON r.id = s.robot_id
JOIN humanoid.spec_definition d ON d.id = s.definition_id
LEFT JOIN humanoid.robot_variant v ON v.id = s.variant_id
WHERE r.slug = %s AND d.key = %s AND coalesce(v.slug, '') = %s
"""


def item_applied(url: str, item: dict) -> bool:
    rows = _query(url, POST_STATE_SQL, (item["robot"], item["definition"],
                                        item.get("variant_slug") or ""))
    want = item["proposed_value"]
    for text_, number, boolean, source_url, observed in rows:
        if isinstance(want, bool):
            same = boolean is want
        elif isinstance(want, int | float):
            same = number is not None and float(number) == float(want)
        else:
            same = text_ == want
        if same and source_url == item["source_url"] and observed == item["observed_at"]:
            return True
    return False


def _state(url: str) -> list[tuple]:
    return _query(url, "SELECT slug, is_published, commercial_status::text "
                       "FROM humanoid.robot ORDER BY slug")


def _import(url: str, robots: list[str], catalogue_dir: Path | None,
            before_write: Callable | None = None) -> str:
    ic = pm.load_db_tool("import_catalogue")
    if catalogue_dir is not None:
        ic.CATALOGUE_DIR = Path(catalogue_dir)
        ic.ROBOTS_DIR = Path(catalogue_dir) / "robots"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ic.run(ic.normalize_url(url), only=set(robots), before_write=before_write)
    return out.getvalue()


def _preflight(before: str, after: str, expected: dict, exclude: Iterable[str]) -> dict:
    """The semantic diff of two databases. `exclude` is passed for BOTH sides: the two are
    reached with different roles, so only an explicit, symmetric exclusion keeps them
    comparable. A table that is not excluded and cannot be read raises (fail closed)."""
    pf = pm.load_db_tool("import_preflight")
    snaps = []
    for url in (before, after):
        with psycopg.connect(_plain(url), connect_timeout=15) as conn:
            conn.read_only = True
            snaps.append(pf.snapshot(conn, frozenset(exclude)))
    report = pf.classify(pf.diff(*snaps), expected)
    return report


def _identity(before: str, after: str, robots: list[str]) -> dict:
    idc = pm.load_db_tool("import_identity_check")
    return idc.compare(idc.snapshot(_plain(before)), idc.snapshot(_plain(after)), set(robots))


def _dangling(url: str) -> int:
    idc = pm.load_db_tool("import_identity_check")
    return sum(1 for v in idc.snapshot(_plain(url))["_audit_targets"].values() if not v)


def _summary(pf: dict, ident: dict, expected_added: set[str]) -> dict:
    return {
        "preflight_ok": pf["ok"],
        "business_changes": pf["business_changes"],
        "by_category": pf["by_category"],
        "unexplained": len(pf["unexplained"]),
        "unfulfilled": len(pf["unfulfilled"]),
        "identity_added": sorted(ident["ADDED"]),
        "identity_expected_added": sorted(expected_added),
        "identity_removed": sorted(ident["REMOVED"]),
        "identity_id_changed": sorted(ident["ID_CHANGED"]),
        "identity_ambiguous": sorted(ident["AMBIGUOUS"]),
        "identity_audit_target_lost": sorted(ident["AUDIT_TARGET_LOST"]),
        "identity_touched": sorted(ident["TOUCHED"]),
    }


def _gate_problems(summary: dict) -> list[str]:
    out = []
    if not summary["preflight_ok"]:
        out.append(f"preflight: {summary['unexplained']} unexplained, "
                   f"{summary['unfulfilled']} missing expected change(s)")
    for key in ("identity_id_changed", "identity_ambiguous", "identity_audit_target_lost",
                "identity_removed"):
        if summary[key]:
            out.append(f"identity check {key}: {summary[key][:5]}")
    if summary["identity_added"] != summary["identity_expected_added"]:
        out.append("identity ADDED does not equal the manifest additions: "
                   f"{summary['identity_added'][:5]} vs {summary['identity_expected_added'][:5]}")
    return out


# --------------------------------------------------------------------------------------- #
# Approval binding: the merged PR is the approval
# --------------------------------------------------------------------------------------- #
APPROVAL_BASE_REF = "main"
CATALOGUE_REPO_DIR = "db/catalogue"


def expected_pr_files(manifest: dict) -> set[str]:
    """Exactly the files a manifest PR may change: the manifest, its review, the scoped robots."""
    stem = f"{CATALOGUE_REPO_DIR}/{pm.PROMOTIONS_SUBDIR}/{manifest.get('promotion_id')}"
    files = {f"{stem}.json", f"{stem}.md"}
    files |= {f"{CATALOGUE_REPO_DIR}/robots/{slug}.json"
              for slug in manifest.get("scope", {}).get("robots", [])}
    return files


def check_approval(manifest: dict, *, commit: str, approvals: Approvals | None,
                   pr_number: int | None, approvers: Iterable[str] | None,
                   read_at_commit: Callable[[str, str], str] | None) -> dict:
    """Prove that PR `pr_number`, merged by an allow-listed owner into main as `commit`, is
    exactly this manifest. Any doubt or API error raises Refused('approval'). Returns the
    detail recorded in the receipt."""
    if approvals is None or pr_number is None:
        raise Refused("approval", "no approval source or --approved-pr given")
    allowed = {a.strip().lower() for a in (approvers or ()) if a and a.strip()}
    if not allowed:
        raise Refused("approval", "no approver allowlist (PROMOTION_APPROVERS): refusing")
    try:
        pr = approvals.pull_request(pr_number)
    except Exception as exc:
        raise Refused("approval", f"cannot read PR #{pr_number} ({_err(exc)})") from None
    problems = []
    if pr.get("merged") is not True:
        problems.append("the PR is not merged")
    if pr.get("base_ref") != APPROVAL_BASE_REF:
        problems.append(f"the PR base is {pr.get('base_ref')!r}, not {APPROVAL_BASE_REF!r}")
    if not pr.get("merge_commit_sha") or pr.get("merge_commit_sha") != commit:
        problems.append("the PR merge commit is not --commit")
    if (pr.get("merged_by") or "").lower() not in allowed:
        problems.append(f"merged by {pr.get('merged_by')!r}, who is not an approver")
    files = set(pr.get("files") or [])
    want = expected_pr_files(manifest)
    if files != want:
        problems.append("the PR changes files other than the manifest, its review and the "
                        f"scoped robots (unexpected: {sorted(files - want)[:5]}, "
                        f"missing: {sorted(want - files)[:5]})")
    path = f"{CATALOGUE_REPO_DIR}/{pm.PROMOTIONS_SUBDIR}/{manifest.get('promotion_id')}.json"
    try:
        committed = json.loads(read_at_commit(commit, path)) if read_at_commit else None
    except Exception as exc:
        committed = None
        problems.append(f"cannot read the manifest at the approved commit ({_err(exc)})")
    else:
        if committed is None:
            problems.append("no way to read the manifest at the approved commit")
        elif (committed.get("digest") != manifest.get("digest")
              or pm.canonical_json(committed) != pm.canonical_json(manifest)):
            problems.append("the manifest at the approved commit differs from the manifest "
                            "being executed")
    if problems:
        raise Refused("approval", "; ".join(problems))
    return {"pr": pr_number, "head_sha": pr.get("head_sha"),
            "merge_commit_sha": pr.get("merge_commit_sha"), "merged_by": pr.get("merged_by"),
            "manifest_digest": manifest.get("digest")}


# --------------------------------------------------------------------------------------- #
# Privileges: the production role must be unable to do anything destructive
# --------------------------------------------------------------------------------------- #
INSERT_REQUIRED = ("specification", "evidence_source")
TABLE_PRIVILEGES_SQL = """
SELECT c.relname,
       pg_has_role(current_user, c.relowner, 'MEMBER'),
       has_any_column_privilege(current_user, c.oid, 'UPDATE'),
       has_table_privilege(current_user, c.oid, 'DELETE'),
       has_table_privilege(current_user, c.oid, 'TRUNCATE'),
       has_table_privilege(current_user, c.oid, 'INSERT')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'humanoid' AND c.relkind IN ('r', 'p') ORDER BY c.relname
"""


def check_privileges(conn) -> dict:
    """Refuse unless the connected role is additions-only: not a superuser, not a member of
    `neon_superuser`, owns no humanoid table, has no UPDATE / DELETE / TRUNCATE on any, and
    may INSERT into the tables a ROUTINE promotion adds to. Raises Refused('privileges')."""
    user, superuser = conn.execute(
        "SELECT current_user, current_setting('is_superuser') = 'on'").fetchone()
    neon = False
    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'neon_superuser'").fetchone():
        neon = bool(conn.execute(
            "SELECT pg_has_role(current_user, 'neon_superuser', 'MEMBER')").fetchone()[0])
    rows = conn.execute(TABLE_PRIVILEGES_SQL).fetchall()
    owned = [r[0] for r in rows if r[1]]
    updatable = [r[0] for r in rows if r[2]]
    deletable = [r[0] for r in rows if r[3]]
    truncatable = [r[0] for r in rows if r[4]]
    insertable = {r[0] for r in rows if r[5]}
    missing = [t for t in INSERT_REQUIRED if t not in insertable]
    problems = []
    if not rows:
        problems.append("no humanoid tables are visible")
    if superuser:
        problems.append("the role is a superuser")
    if neon:
        problems.append("the role is a member of neon_superuser")
    for what, tables in (("owns", owned), ("has UPDATE on", updatable),
                         ("has DELETE on", deletable), ("has TRUNCATE on", truncatable)):
        if tables:
            problems.append(f"the role {what}: {', '.join(tables[:6])}")
    if missing:
        problems.append(f"the role lacks INSERT on: {', '.join(missing)}")
    detail = {"user": user, "superuser": superuser, "neon_superuser_member": neon,
              "tables_checked": len(rows), "insert_tables": sorted(insertable),
              "owned": owned, "update": updatable, "delete": deletable,
              "truncate": truncatable, "ok": not problems}
    if problems:
        raise Refused("privileges", "; ".join(problems))
    return detail


# --------------------------------------------------------------------------------------- #
# Eligibility: re-derived from production, never trusted from the manifest
# --------------------------------------------------------------------------------------- #
ELIGIBILITY_FIELDS = ("robot", "definition", "variant_slug", "edition", "claim_field_key",
                      "proposed_value", "claim_value", "source_url", "observed_at",
                      "content_hash")


def _sa_url(url: str) -> str:
    return _plain(url).replace("postgresql://", "postgresql+psycopg://", 1)


def revalidate_eligibility(manifest: dict, url: str, *, base_catalogue_dir: Path,
                           head_catalogue_dir: Path, today) -> list[str]:
    """Re-run the proposal checks (identity, edition, source, observation, value, conflict,
    definition, freshness, restricted, addition against the BASE catalogue) on a READ-ONLY
    session and return every way the result differs from the manifest ([] = still eligible)."""
    from sqlalchemy import create_engine
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    scope = manifest.get("scope", {})
    rejected = pm.rejected_claim_ids(head_catalogue_dir)
    problems = [f"claim {i['claim_id']} was REJECTED after the proposal"
                for i in manifest["items"] if i["claim_id"] in rejected]
    engine = create_engine(_sa_url(url), connect_args={
        "options": "-csearch_path=humanoid,public -cdefault_transaction_read_only=on"})
    try:
        with Session(engine) as session:
            for robot in sorted({i["robot"] for i in manifest["items"]}):
                mine = [i for i in manifest["items"] if i["robot"] == robot]
                raw = [{k: i.get(k) for k in ("claim_id", "definition", "proposed_value",
                                              "variant_slug", "interpretation", "edition",
                                              "evidence_locator", "display")} for i in mine]
                try:
                    fresh = pm.propose(
                        session, robot, raw, catalogue_dir=base_catalogue_dir,
                        base_commit=manifest["base"]["catalogue_commit"],
                        promotion_id=manifest["promotion_id"], today=today,
                        edition_map=scope.get("edition_map") or {},
                        fingerprints=manifest["base"]["robot_fingerprints"])
                except pm.ProposalRefused as exc:
                    problems.append(f"{robot}: re-proposal refused: {exc}")
                    continue
                now = {(i["definition"], i.get("variant_slug")): i for i in fresh["items"]}
                for item in mine:
                    again = now.get((item["definition"], item.get("variant_slug")))
                    name = f"{robot}:{item['definition']}"
                    if again is None:
                        problems.append(f"{name}: not re-derived")
                        continue
                    if again["classification"] != pm.ROUTINE or again["conflict"] != "NONE":
                        problems.append(f"{name}: now {again['classification']} / conflict "
                                        f"{again['conflict']} ({'; '.join(again['reasons'][:3])})")
                    for field in ELIGIBILITY_FIELDS:
                        if again.get(field) != item.get(field):
                            problems.append(f"{name}: {field} changed since the proposal")
    except SQLAlchemyError as exc:
        raise Refused("eligibility", f"database unreadable ({_err(exc)})") from None
    finally:
        engine.dispose()
    return problems


# --------------------------------------------------------------------------------------- #
# Public verification
# --------------------------------------------------------------------------------------- #
def _same_value(have: Any, want: Any) -> bool:
    if isinstance(want, bool) or isinstance(have, bool):
        return have is want
    if isinstance(want, int | float) and isinstance(have, int | float | str):
        try:
            return float(have) == float(want)
        except ValueError:
            return False
    return have == want


def _collapse(text_: str) -> str:
    return re.sub(r"\s+", " ", text_ or "").strip()


def _same_date(have: Any, want: Any) -> bool:
    if have is None or want is None:
        return have is None and want is None
    return str(have)[:10] == str(want)[:10]


def entry_matches(entry: dict, item: dict) -> bool:
    """One `extended_specs` entry is THE committed fact: key, variant, value, source, the
    observation date and (when the item has one) the unit all agree."""
    return (entry.get("key") == item["definition"]
            and entry.get("variant_slug") == item.get("variant_slug")
            and _same_value(entry.get("value"), item["proposed_value"])
            and entry.get("source_url") == item["source_url"]
            and _same_date(entry.get("observed_at"), item.get("observed_at"))
            and (not item.get("unit") or entry.get("unit") == item["unit"]))


_VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                        "meta", "source", "track", "wbr"})


class _SpecRows(HTMLParser):
    """The rendered 'rows' of a page, by the markup the web app really emits:

    * `div.srow` - the robot detail page: `span.k` is the label (plus a variant note), `span.v`
      the value, and the attribution is an `<a href=source_url>` inside the same row
      (apps/web/app/robots/[slug]/page.tsx `ExtendedSpecRow`);
    * `tr` - the compare matrix: `th` is the row label, each `td` one robot's cell, in the
      order of the `ids` (apps/web/app/compare/CompareView.tsx `ApiRow`).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, frozenset]] = []
        self.rows: list[dict] = []
        self.cur: dict | None = None
        self.cur_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _VOID_TAGS:
            return
        attr = dict(attrs)
        classes = frozenset((attr.get("class") or "").split())
        if self.cur is None and ((tag == "div" and "srow" in classes) or tag == "tr"):
            self.cur = {"kind": "srow" if tag == "div" else "tr", "label": [], "value": [],
                        "cells": [], "anchors": [], "text": []}
            self.cur_depth = len(self.stack)
        self.stack.append((tag, classes))
        if self.cur is not None:
            if tag == "td":
                self.cur["cells"].append([])
            elif tag == "a":
                self.cur["anchors"].append({"href": attr.get("href"), "text": []})

    def handle_data(self, data):
        if self.cur is None:
            return
        row = self.cur
        row["text"].append(data)
        for tag, classes in self.stack[self.cur_depth + 1:]:
            if "k" in classes or tag == "th":
                row["label"].append(data)
            if "v" in classes:
                row["value"].append(data)
            if tag == "td" and row["cells"]:
                row["cells"][-1].append(data)
            if tag == "a" and row["anchors"]:
                row["anchors"][-1]["text"].append(data)

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if self.cur is not None and len(self.stack) <= self.cur_depth:
            row = self.cur
            self.rows.append({
                "kind": row["kind"], "label": _collapse(" ".join(row["label"])),
                "value": _collapse(" ".join(row["value"])),
                "cells": [_collapse(" ".join(c)) for c in row["cells"]],
                "anchors": [{"href": a["href"], "text": _collapse(" ".join(a["text"]))}
                            for a in row["anchors"]],
                "text": _collapse(" ".join(row["text"]))})
            self.cur = None


def spec_rows(body: str) -> list[dict]:
    parser = _SpecRows()
    parser.feed(body)
    parser.close()
    return parser.rows


def _label_matches(row_label: str, label: str, variant: bool) -> bool:
    """The row names this definition. A variant-scoped row reads '<label> <variant>
    configuration'; anything else must be the label exactly (so 'Battery' never matches
    'Battery capacity')."""
    if row_label == label:
        return True
    return variant and row_label.startswith(label + " ") and row_label.endswith("configuration")


def _value_matches(shown: str, want: Any, unit: str | None) -> bool:
    shown = _collapse(shown)
    if isinstance(want, bool):
        return shown.upper() == ("YES" if want else "NO")
    if isinstance(want, int | float):
        found = re.search(r"-?\d[\d,]*\.?\d*", shown)
        try:
            same = bool(found) and float(found.group().replace(",", "")) == float(want)
        except ValueError:
            return False
        return same and (not unit or unit in shown)
    return _collapse(str(want)) in shown


def _label_for(item: dict, labels: dict | None) -> str | None:
    if labels and labels.get(item["definition"]):
        return labels[item["definition"]]
    found = re.search(r"'(.*): " + re.escape(str(item["proposed_value"])) + r"'",
                      item.get("display") or "")
    return found.group(1) if found else None


def check_page_row(body: str, item: dict, label: str | None) -> tuple[bool, dict]:
    """Detail page: the value is in the spec row of this definition's label, and that same row
    shows where it comes from (a link to source_url, or the rendered source label)."""
    seen = {"source_link_visible": False, "source_label_visible": False}
    if not label:
        return False, seen
    for row in spec_rows(body):
        if row["kind"] != "srow" or not _label_matches(
                row["label"], label, bool(item.get("variant_slug"))):
            continue
        if not _value_matches(row["value"], item["proposed_value"], item.get("unit")):
            continue
        link = any(a["href"] == item["source_url"] for a in row["anchors"])
        shown = _collapse(item["source_label"]) in row["text"]
        seen = {"source_link_visible": link, "source_label_visible": shown}
        if link or shown:
            return True, seen
    return False, seen


def check_compare_row(body: str, item: dict, label: str | None) -> bool:
    """Compare matrix: the value is in this robot's cell (the first column) of the row for the
    definition's label."""
    if not label:
        return False
    return any(row["kind"] == "tr" and _label_matches(row["label"], label, False)
               and row["cells"] and _value_matches(row["cells"][0], item["proposed_value"],
                                                   item.get("unit"))
               for row in spec_rows(body))


def check_public(manifest: dict, web: Web, api_base: str, web_base: str,
                 labels: dict | None = None) -> list[dict]:
    """One pass over every item and surface. Returns one result per (item, surface).

    api      the item's `extended_specs` entry matches key, variant, value, unit, source_url
             and observed_at;
    page     the value is in that definition's spec row, with its provenance in the same row;
    compare  the value is in that definition's row, in this robot's column, of a comparison
             with the manifest's published peer.
    `labels` maps definition key -> label (the catalogue's spec_definitions)."""
    results = []
    for item in manifest["items"]:
        slug = item["robot"]
        api_url = f"{api_base.rstrip('/')}/api/robots/{urllib.parse.quote(slug)}"
        page_url = f"{web_base.rstrip('/')}/robots/{urllib.parse.quote(slug)}"
        # A one-robot compare renders no comparison: compare against the manifest's peer.
        peer = item.get("compare_peer")
        compare_url = (f"{web_base.rstrip('/')}/compare?ids={urllib.parse.quote(slug)},"
                       f"{urllib.parse.quote(peer)}" if peer else None)
        label = _label_for(item, labels)
        ok, note = False, ""
        try:
            status, body = web.get(api_url)
            if status == 200:
                ok = any(entry_matches(entry, item)
                         for entry in json.loads(body).get("extended_specs", []))
            else:
                note = f"HTTP {status}"
        except (OSError, ValueError, urllib.error.URLError) as exc:
            note = _err(exc)
        results.append({"claim_id": item["claim_id"], "surface": "api", "url": api_url,
                        "ok": ok, "note": note})
        for surface, url in (("page", page_url), ("compare", compare_url)):
            if url is None:     # refused earlier at the manifest step; never a pass
                results.append({"claim_id": item["claim_id"], "surface": surface, "url": None,
                                "ok": False, "note": "no published compare peer"})
                continue
            ok, note, seen = False, "", {}
            try:
                status, body = web.get(url)
                if status != 200:
                    note = f"HTTP {status}"
                elif surface == "page":
                    ok, seen = check_page_row(body, item, label)
                else:
                    ok = check_compare_row(body, item, label)
                if status == 200 and not ok:
                    note = ("no spec row for the label" if not label else
                            "value (and provenance) not in the row for " + repr(label))
            except (OSError, ValueError, urllib.error.URLError) as exc:
                note = _err(exc)
            results.append({"claim_id": item["claim_id"], "surface": surface, "url": url,
                            "ok": ok, "note": note, **seen})
    return results


# --------------------------------------------------------------------------------------- #
# execute
# --------------------------------------------------------------------------------------- #
def _branch_name(prefix: str, promotion_id: str, stamp: str) -> str:
    safe = re.sub(r"[^a-z0-9-]+", "-", promotion_id.lower()).strip("-")[:40]
    return f"{prefix}-{safe}-{stamp}"


def execute(manifest: dict, *, commit: str, production: Production, branches: Branches,
            github: Github, approvals: Approvals | None = None, approved_pr: int | None = None,
            approvers: Iterable[str] | None = None,
            read_at_commit: Callable[[str, str], str] | None = None,
            web: Web | None = None, api_base: str | None = None,
            web_base: str | None = None, catalogue_dir: Path | None = None,
            base_catalogue_dir: Path | None = None, dry_run: bool = False,
            clock=time.time, sleep=time.sleep, retries: int = 12, retry_wait: float = 60.0,
            utc_now=lambda: datetime.now(UTC)) -> dict:
    """Run the promotion. Never raises for an expected failure: the outcome is in the receipt.

    `approvals` + `approved_pr` + `approvers` + `read_at_commit` bind the run to the merged PR
    (see `check_approval`); without them every run is REFUSED:approval."""
    started = clock()
    robots = sorted(manifest.get("scope", {}).get("robots", []))
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    excluded = sorted(pm.excluded_tables())
    receipt: dict[str, Any] = {
        "promotion_id": manifest.get("promotion_id"), "digest": manifest.get("digest"),
        "commit": commit, "robots": robots,
        "fields": [f"{i.get('robot')}:{i.get('definition')}" for i in manifest.get("items", [])],
        "dry_run": dry_run, "steps": [], "branches": {}, "outcome": None,
        "approval": None, "excluded_tables": excluded,
    }

    try:
        head_dir = catalogue_dir or pm.REPO_ROOT / "db" / "catalogue"
        labels = {k: d.get("label") for k, d in pm.load_definitions(head_dir).items()}
    except (OSError, ValueError, KeyError):
        labels = None

    def step(name: str, status: str, **detail) -> None:
        receipt["steps"].append({"step": name, "status": status,
                                 "t": round(clock() - started, 3), **detail})

    lock = _Lock(production.url)
    safety = rehearsal = None
    written = False
    try:
        # 1. manifest ---------------------------------------------------------------------
        problems = pm.manifest_problems(manifest)
        if problems:
            raise Refused("manifest", "; ".join(problems))
        # Public compare verification needs a published peer: found now, never after a write.
        no_peer = [f"{i.get('robot')}:{i.get('definition')}" for i in manifest["items"]
                   if not i.get("compare_peer")]
        if no_peer:
            raise Refused("manifest", "no published compare peer for: " + ", ".join(no_peer))
        if base_catalogue_dir is not None:
            head = catalogue_dir or pm.REPO_ROOT / "db" / "catalogue"
            result = pm.verify(manifest, base_catalogue_dir=base_catalogue_dir,
                               head_catalogue_dir=head)
            if not result.ok:
                raise Refused("manifest", "; ".join(result.reasons))
            step("manifest", "OK", catalogue_equals_base_plus_manifest=True)
        else:
            step("manifest", "OK", catalogue_equals_base_plus_manifest="NOT_CHECKED")

        # 1b. approval: the merged PR is the approval -------------------------------------
        if getattr(approvals, "simulated", False):
            if not getattr(branches, "local", False):
                raise Refused("approval", "a simulated approval is only for local-database "
                              "branches (non-production pilots)")
            receipt["approval"] = "SIMULATED_LOCAL"
            receipt["approval_detail"] = {"pr": approved_pr, "note": "no PR was consulted"}
            step("approval", "SIMULATED_LOCAL")
        else:
            detail = check_approval(manifest, commit=commit, approvals=approvals,
                                    pr_number=approved_pr, approvers=approvers,
                                    read_at_commit=read_at_commit)
            receipt["approval"] = "GITHUB_PR"
            receipt["approval_detail"] = detail
            step("approval", "OK", pr=approved_pr)

        # 2. halt switch ------------------------------------------------------------------
        try:
            halted = github.open_incident_exists()
        except Exception as exc:
            raise Refused("halt_switch", f"cannot read incident state ({_err(exc)})") from None
        if halted:
            raise Refused("halt_switch", "an open promotion-incident issue stops promotions")
        step("halt_switch", "OK")

        # 3. concurrency ------------------------------------------------------------------
        lock.acquire()
        step("concurrency", "OK", exclusive_source=bool(branches.requires_exclusive_source))

        # 3b. privileges of the production role (additions-only, never an owner) ----------
        try:
            receipt["privileges"] = check_privileges(lock.conn)
        except psycopg.Error as exc:
            raise Refused("privileges", f"cannot inspect privileges ({_err(exc)})") from None
        step("privileges", "OK", user=receipt["privileges"]["user"])

        # 4. already applied --------------------------------------------------------------
        try:
            applied = [item_applied(production.url, i) for i in manifest["items"]]
        except psycopg.Error as exc:
            raise Refused("already_applied", f"database unreadable ({_err(exc)})") from None
        if all(applied):
            step("already_applied", "ALREADY_APPLIED")
            receipt["outcome"] = "ALREADY_APPLIED"
            if web and api_base and web_base:
                receipt["public_verification"] = check_public(
                    manifest, web, api_base, web_base, labels)
            return _finish(receipt, github, started, clock)
        step("already_applied", "NO", applied=applied)

        # 4b. eligibility, re-derived from production ------------------------------------
        if base_catalogue_dir is not None:
            head = catalogue_dir or pm.REPO_ROOT / "db" / "catalogue"
            problems = revalidate_eligibility(
                manifest, production.url, base_catalogue_dir=base_catalogue_dir,
                head_catalogue_dir=head, today=utc_now().date())
            if problems:
                raise Refused("eligibility", "; ".join(problems)[:900])
            step("eligibility", "OK", rederived_items=len(manifest["items"]))
        else:
            step("eligibility", "NOT_CHECKED")

        # 5. baseline ---------------------------------------------------------------------
        def drift() -> dict | None:
            try:
                now = pm.fingerprints_from_url(production.url, robots)
            except psycopg.Error as exc:
                raise Refused("base_drift", f"database unreadable ({_err(exc)})") from None
            want = manifest["base"]["robot_fingerprints"]
            return {s: {"expected": want.get(s), "actual": now.get(s)}
                    for s in robots if want.get(s) != now.get(s)} or None

        changed = drift()
        if changed:
            receipt["fingerprint_drift"] = changed
            raise Refused("base_drift", "production changed since review for: "
                          + ", ".join(sorted(changed)))
        step("base_drift", "OK", fingerprints=manifest["base"]["robot_fingerprints"])

        # 6-7. safety branch and rehearsal -----------------------------------------------
        if branches.requires_exclusive_source:
            lock.release()
        safety_name = _branch_name("promo", manifest["promotion_id"], stamp)
        verify_origin = getattr(branches, "verify_origin", None)
        try:
            if verify_origin is not None:       # the real adapters always have it
                receipt["branches"]["production_origin"] = verify_origin(production.url)
            safety_url = branches.create(safety_name)
            safety = safety_name
        except Exception as exc:
            raise Refused("safety_branch", f"cannot create safety branch ({_why(exc)})") from None
        receipt["branches"]["safety"] = safety
        receipt["branches"]["safety_origin"] = getattr(branches, "origins", {}).get(safety)
        step("safety_branch", "OK", branch=safety)
        rehearsal_name = _branch_name("rehearse", manifest["promotion_id"], stamp)
        try:
            rehearsal_url = branches.create(rehearsal_name)
            rehearsal = rehearsal_name
        except Exception as exc:
            raise Refused("rehearsal", f"cannot create rehearsal branch ({_why(exc)})") from None
        receipt["branches"]["rehearsal"] = rehearsal
        receipt["branches"]["rehearsal_origin"] = getattr(branches, "origins", {}).get(rehearsal)
        if branches.requires_exclusive_source:
            lock.acquire()
            if drift():
                raise Refused("base_drift", "production changed while branching")

        expected_pf = pm.derive_preflight_manifest(manifest)
        expected_added = pm.expected_added_keys(manifest)
        try:
            _import(rehearsal_url, robots, catalogue_dir)
            pf_r = _preflight(safety_url, rehearsal_url, expected_pf, excluded)
            id_r = _identity(safety_url, rehearsal_url, robots)
        except (Exception, SystemExit) as exc:
            raise Refused("rehearsal", f"rehearsal import failed ({_err(exc)}): "
                          f"{exc if isinstance(exc, SystemExit) else ''}"[:600]) from None
        rehearsal_summary = _summary(pf_r, id_r, expected_added)
        receipt["rehearsal"] = rehearsal_summary
        bad = _gate_problems(rehearsal_summary)
        if bad:
            receipt["rehearsal_report"] = {"unexplained": pf_r["unexplained"][:10],
                                           "unfulfilled": pf_r["unfulfilled"][:10]}
            raise Refused("rehearsal", "; ".join(bad))
        step("rehearsal", "PASS")
        with contextlib.suppress(Exception):
            branches.delete(rehearsal)
            receipt["branches"]["rehearsal_deleted"] = True
            rehearsal = None

        if dry_run:
            step("apply", "SKIPPED_DRY_RUN")
            receipt["outcome"] = "DRY_RUN_OK"
            return _finish(receipt, github, started, clock, comment=False)

        # 8. apply ------------------------------------------------------------------------
        before_apply = pm.fingerprints_from_url(production.url, robots)
        want_fp = manifest["base"]["robot_fingerprints"]
        drifted: dict[str, dict] = {}

        def recheck_under_lock(cur) -> None:
            """Runs inside the importer's transaction, after the `catalogue-write` lock and
            before its first write: the same snapshot, so nothing can slip in between."""
            now = pm.fingerprints_from_connection(cur.connection, robots, excluded)
            for slug in robots:
                if want_fp.get(slug) != now.get(slug):
                    drifted[slug] = {"expected": want_fp.get(slug), "actual": now.get(slug)}
            if drifted:
                raise pm.load_db_tool("import_catalogue").ReconcileRefused(
                    "IMPORT REFUSED - production changed since review; nothing was written")

        written = True
        try:
            receipt["importer_summary"] = _import(
                production.url, robots, catalogue_dir, before_write=recheck_under_lock)[-2000:]
        except (Exception, SystemExit) as exc:
            if drifted:
                written = False
                receipt["fingerprint_drift"] = drifted
                raise Refused("apply", "production changed between the drift check and the "
                              "write; nothing was written for: " + ", ".join(sorted(drifted))
                              ) from None
            # The importer's transaction rolled back. Prove nothing moved before saying so.
            try:
                moved = pm.fingerprints_from_url(production.url, robots) != before_apply
            except Exception:
                moved = True
            if moved:
                raise Incident("apply", f"importer failed and production state is not the "
                               f"pre-apply state ({_err(exc)})") from None
            written = False
            raise Refused("apply", f"importer refused, nothing written ({_err(exc)}): "
                          f"{exc if isinstance(exc, SystemExit) else ''}"[:600]) from None
        step("apply", "COMMITTED")

        # 9. post-verify ------------------------------------------------------------------
        try:
            pf_p = _preflight(safety_url, production.url, expected_pf, excluded)
            id_p = _identity(safety_url, production.url, robots)
            receipt["after_fingerprints"] = pm.fingerprints_from_url(production.url, robots)
            same_state = _state(safety_url) == _state(production.url)
            dangling_before, dangling_after = _dangling(safety_url), _dangling(production.url)
        except Exception as exc:
            raise Incident("post_verify", f"post-verification failed ({_err(exc)})") from None
        prod_summary = _summary(pf_p, id_p, expected_added)
        receipt["post_verify"] = {"summary": prod_summary, "publication_and_status_unchanged":
                                  same_state, "dangling_audit_before": dangling_before,
                                  "dangling_audit_after": dangling_after}
        problems = _gate_problems(prod_summary)
        keys = ("preflight_ok", "business_changes", "by_category", "identity_added",
                "identity_removed", "identity_id_changed", "identity_touched")
        if {k: prod_summary[k] for k in keys} != {k: rehearsal_summary[k] for k in keys}:
            problems.append("production result differs from the rehearsal")
        if not same_state:
            problems.append("publication or commercial status changed")
        if dangling_after > dangling_before:
            problems.append("dangling audit targets increased")
        if problems:
            raise Incident("post_verify", "; ".join(problems))
        step("post_verify", "PASS")

        # 10. public verification ---------------------------------------------------------
        if web and api_base and web_base:
            attempts, results = 0, []
            for attempts in range(1, retries + 1):
                results = check_public(manifest, web, api_base, web_base, labels)
                if all(r["ok"] for r in results):
                    break
                if attempts < retries:
                    sleep(retry_wait)
            receipt["public_verification"] = results
            if not all(r["ok"] for r in results):
                step("public_verify", "FAILED", attempts=attempts)
                raise Incident("public_verify", "the committed value is not visible publicly "
                               f"after {attempts} attempt(s): "
                               + ", ".join(f"{r['surface']}:{r['claim_id'][:8]}"
                                           for r in results if not r["ok"]))
            step("public_verify", "PASS", attempts=attempts)
        else:
            step("public_verify", "SKIPPED_NO_BASE_URLS")
        receipt["outcome"] = "SUCCESS"
        return _finish(receipt, github, started, clock)

    except Refused as exc:
        step(exc.step, "REFUSED", reason=exc.reason)
        receipt["outcome"] = f"REFUSED:{exc.step}"
        receipt["reason"] = exc.reason
        if safety and not written:
            with contextlib.suppress(Exception):    # nothing was written: no safety point needed
                branches.delete(safety)
                receipt["branches"]["safety_deleted"] = True
        return _finish(receipt, github, started, clock)
    except Incident as exc:
        step(exc.step, "INCIDENT", reason=exc.reason)
        receipt["outcome"] = f"INCIDENT:{exc.step}"
        receipt["reason"] = exc.reason
        receipt["safety_branch_retained"] = safety
        try:
            github.open_incident(
                f"Catalogue promotion {manifest.get('promotion_id')} failed after commit "
                f"({exc.step})",
                "A promotion failed AFTER its database commit. No automatic rollback was done.\n\n"
                f"- reason: {exc.reason}\n- safety branch (retained): {safety}\n"
                f"- commit: {commit}\n- digest: {manifest.get('digest')}\n\n"
                "Close this issue to allow further promotions.")
            receipt["incident_opened"] = True
        except Exception as exc2:
            receipt["incident_opened"] = False
            receipt["incident_error"] = _err(exc2)
        return _finish(receipt, github, started, clock)
    finally:
        lock.release()
        if rehearsal:
            with contextlib.suppress(Exception):
                branches.delete(rehearsal)
        if dry_run and safety and receipt.get("outcome") == "DRY_RUN_OK":
            with contextlib.suppress(Exception):
                branches.delete(safety)
                receipt["branches"]["safety_deleted"] = True


def _finish(receipt: dict, github: Github, started: float, clock, comment: bool = True) -> dict:
    receipt["elapsed_seconds"] = round(clock() - started, 3)
    if comment:
        try:
            github.comment(render_receipt(receipt))
        except Exception as exc:
            receipt["comment_error"] = _err(exc)
    return receipt


def render_receipt(receipt: dict) -> str:
    lines = [f"### Catalogue promotion receipt: {receipt['outcome']}", "",
             f"- promotion: `{receipt['promotion_id']}` digest `{(receipt['digest'] or '')[:16]}`",
             f"- commit: `{receipt['commit']}`",
             f"- robots: {', '.join(receipt['robots'])}",
             f"- fields: {', '.join(receipt['fields'])}",
             f"- safety branch: `{receipt['branches'].get('safety')}`"]
    if receipt.get("reason"):
        lines.append(f"- reason: {receipt['reason']}")
    lines.append("- steps: " + " > ".join(f"{s['step']}={s['status']}" for s in receipt["steps"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------- #
# Real adapters. Local ones live here; the network ones (Neon REST, GitHub REST, public site
# GET) are in db/promotion_adapters.py, outside apps/api/app, so this package keeps importing no
# HTTP client (tests/test_acquisition_schema.py guards that for the whole app tree).
# --------------------------------------------------------------------------------------- #
class LocalBranches:
    """Branches as local databases (`CREATE DATABASE ... TEMPLATE`). Rehearsals and the pilot."""

    requires_exclusive_source = True
    local = True

    def __init__(self, admin_url: str, source_db: str):
        from sqlalchemy import make_url

        self._make_url = make_url
        self.admin_url = _plain(admin_url)
        self.source_db = source_db
        self.origins: dict[str, dict] = {}

    def verify_origin(self, production_url: str) -> dict:
        """The template these branches copy must be the production database itself."""
        production_db = self._make_url(_plain(production_url)).database
        if production_db != self.source_db:
            raise BranchOriginError(
                f"the branch template database {self.source_db!r} is not the production "
                f"database {production_db!r}")
        return {"template_db": self.source_db, "production_db": production_db}

    @staticmethod
    def _db(name: str) -> str:
        return re.sub(r"[^a-z0-9_]+", "_", name.lower())[:60]

    def _url(self, db: str) -> str:
        return self._make_url(self.admin_url).set(database=db).render_as_string(
            hide_password=False)

    def create(self, name: str) -> str:
        db = self._db(name)
        with psycopg.connect(self.admin_url, autocommit=True) as conn:
            # A template copy needs the source to have no other sessions. Local only: a locally
            # running API's idle pool connections to the source are ended (it reconnects).
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                         "WHERE datname = %s AND pid <> pg_backend_pid()", (self.source_db,))
            conn.execute(f'CREATE DATABASE "{db}" TEMPLATE "{self.source_db}"')
        self.origins[name] = {"template_db": self.source_db, "database": db}
        return self._url(db)

    def delete(self, name: str) -> None:
        db = self._db(name)
        with psycopg.connect(self.admin_url, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                         "WHERE datname = %s AND pid <> pg_backend_pid()", (db,))
            conn.execute(f'DROP DATABASE IF EXISTS "{db}"')


class StaticProduction:
    def __init__(self, url: str):
        self.url = url
