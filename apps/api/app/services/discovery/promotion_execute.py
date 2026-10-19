"""Approved catalogue promotion: fail-closed execution (workstream B, design section 4).

`execute` runs after the owner merged a manifest PR. Every external system is an INJECTED
interface (`Branches`, `Production`, `Github`, `Web`, plus `clock`/`sleep`), so the whole
sequence is testable without Neon, GitHub or the network. The real adapters are at the bottom.

Order, each step recorded in the receipt:

  manifest -> halt_switch -> concurrency -> already_applied -> base_drift -> safety_branch
  -> rehearsal -> apply -> post_verify -> public_verify -> receipt

Steps up to and including `rehearsal` write NOTHING to production. `apply` is the importer's
single transaction (no --authorize, so the fast lane cannot delete). A failure after the
commit opens a `promotion-incident` issue, keeps the safety branch and does NOT roll back
(restoring from the branch could overwrite concurrent legitimate changes).

Outcomes: SUCCESS | ALREADY_APPLIED | DRY_RUN_OK | REFUSED:<step> | INCIDENT:<step>.
Secrets are never printed or recorded: only exception TYPES are reported for DB/HTTP failures.
"""
from __future__ import annotations

import contextlib
import html
import io
import json
import re
import time
import urllib.error
import urllib.parse
from datetime import UTC, datetime
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


class Production(Protocol):
    url: str


class Github(Protocol):
    def open_incident_exists(self) -> bool: ...
    def open_incident(self, title: str, body: str) -> None: ...
    def comment(self, body: str) -> None: ...


class Web(Protocol):
    def get(self, url: str) -> tuple[int, str]: ...


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


def _import(url: str, robots: list[str], catalogue_dir: Path | None) -> str:
    ic = pm.load_db_tool("import_catalogue")
    if catalogue_dir is not None:
        ic.CATALOGUE_DIR = Path(catalogue_dir)
        ic.ROBOTS_DIR = Path(catalogue_dir) / "robots"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ic.run(ic.normalize_url(url), only=set(robots))
    return out.getvalue()


def _preflight(before: str, after: str, expected: dict) -> dict:
    pf = pm.load_db_tool("import_preflight")
    snaps = []
    for url in (before, after):
        with psycopg.connect(_plain(url), connect_timeout=15) as conn:
            conn.read_only = True
            snaps.append(pf.snapshot(conn))
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


def _contains(body: str, needle: str) -> bool:
    return needle in body or html.escape(needle) in body or html.escape(needle, quote=False) in body


def check_public(manifest: dict, web: Web, api_base: str, web_base: str) -> list[dict]:
    """One pass over every item and surface. Returns one result per (item, surface)."""
    results = []
    for item in manifest["items"]:
        slug, want = item["robot"], item["proposed_value"]
        shown = str(want)
        api_url = f"{api_base.rstrip('/')}/api/robots/{urllib.parse.quote(slug)}"
        page_url = f"{web_base.rstrip('/')}/robots/{urllib.parse.quote(slug)}"
        compare_url = f"{web_base.rstrip('/')}/compare?ids={urllib.parse.quote(slug)}"
        ok, note = False, ""
        try:
            status, body = web.get(api_url)
            if status == 200:
                for entry in json.loads(body).get("extended_specs", []):
                    if (entry.get("key") == item["definition"]
                            and entry.get("variant_slug") == item.get("variant_slug")
                            and _same_value(entry.get("value"), want)
                            and entry.get("source_url") == item["source_url"]):
                        ok = True
            else:
                note = f"HTTP {status}"
        except (OSError, ValueError, urllib.error.URLError) as exc:
            note = _err(exc)
        results.append({"claim_id": item["claim_id"], "surface": "api", "url": api_url,
                        "ok": ok, "note": note})
        for surface, url in (("page", page_url), ("compare", compare_url)):
            ok, note, label_seen = False, "", None
            try:
                status, body = web.get(url)
                if status == 200:
                    ok = _contains(body, shown)
                    label_seen = _contains(body, item["source_label"])
                else:
                    note = f"HTTP {status}"
            except (OSError, ValueError, urllib.error.URLError) as exc:
                note = _err(exc)
            results.append({"claim_id": item["claim_id"], "surface": surface, "url": url,
                            "ok": ok, "note": note, "source_label_visible": label_seen})
    return results


# --------------------------------------------------------------------------------------- #
# execute
# --------------------------------------------------------------------------------------- #
def _branch_name(prefix: str, promotion_id: str, stamp: str) -> str:
    safe = re.sub(r"[^a-z0-9-]+", "-", promotion_id.lower()).strip("-")[:40]
    return f"{prefix}-{safe}-{stamp}"


def execute(manifest: dict, *, commit: str, production: Production, branches: Branches,
            github: Github, web: Web | None = None, api_base: str | None = None,
            web_base: str | None = None, catalogue_dir: Path | None = None,
            base_catalogue_dir: Path | None = None, dry_run: bool = False,
            clock=time.time, sleep=time.sleep, retries: int = 12, retry_wait: float = 60.0,
            utc_now=lambda: datetime.now(UTC)) -> dict:
    """Run the promotion. Never raises for an expected failure: the outcome is in the receipt."""
    started = clock()
    robots = sorted(manifest.get("scope", {}).get("robots", []))
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    receipt: dict[str, Any] = {
        "promotion_id": manifest.get("promotion_id"), "digest": manifest.get("digest"),
        "commit": commit, "robots": robots,
        "fields": [f"{i.get('robot')}:{i.get('definition')}" for i in manifest.get("items", [])],
        "dry_run": dry_run, "steps": [], "branches": {}, "outcome": None,
    }

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
        if base_catalogue_dir is not None:
            head = catalogue_dir or pm.REPO_ROOT / "db" / "catalogue"
            result = pm.verify(manifest, base_catalogue_dir=base_catalogue_dir,
                               head_catalogue_dir=head)
            if not result.ok:
                raise Refused("manifest", "; ".join(result.reasons))
            step("manifest", "OK", catalogue_equals_base_plus_manifest=True)
        else:
            step("manifest", "OK", catalogue_equals_base_plus_manifest="NOT_CHECKED")

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

        # 4. already applied --------------------------------------------------------------
        try:
            applied = [item_applied(production.url, i) for i in manifest["items"]]
        except psycopg.Error as exc:
            raise Refused("already_applied", f"database unreadable ({_err(exc)})") from None
        if all(applied):
            step("already_applied", "ALREADY_APPLIED")
            receipt["outcome"] = "ALREADY_APPLIED"
            if web and api_base and web_base:
                receipt["public_verification"] = check_public(manifest, web, api_base, web_base)
            return _finish(receipt, github, started, clock)
        step("already_applied", "NO", applied=applied)

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
        try:
            safety_url = branches.create(safety_name)
            safety = safety_name
        except Exception as exc:
            raise Refused("safety_branch", f"cannot create safety branch ({_err(exc)})") from None
        receipt["branches"]["safety"] = safety
        step("safety_branch", "OK", branch=safety)
        rehearsal_name = _branch_name("rehearse", manifest["promotion_id"], stamp)
        try:
            rehearsal_url = branches.create(rehearsal_name)
            rehearsal = rehearsal_name
        except Exception as exc:
            raise Refused("rehearsal", f"cannot create rehearsal branch ({_err(exc)})") from None
        receipt["branches"]["rehearsal"] = rehearsal
        if branches.requires_exclusive_source:
            lock.acquire()
            if drift():
                raise Refused("base_drift", "production changed while branching")

        expected_pf = pm.derive_preflight_manifest(manifest)
        expected_added = pm.expected_added_keys(manifest)
        try:
            _import(rehearsal_url, robots, catalogue_dir)
            pf_r = _preflight(safety_url, rehearsal_url, expected_pf)
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
        written = True
        try:
            receipt["importer_summary"] = _import(production.url, robots, catalogue_dir)[-2000:]
        except (Exception, SystemExit) as exc:
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
            pf_p = _preflight(safety_url, production.url, expected_pf)
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
                results = check_public(manifest, web, api_base, web_base)
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

    def __init__(self, admin_url: str, source_db: str):
        from sqlalchemy import make_url

        self._make_url = make_url
        self.admin_url = _plain(admin_url)
        self.source_db = source_db

    @staticmethod
    def _db(name: str) -> str:
        return re.sub(r"[^a-z0-9_]+", "_", name.lower())[:60]

    def _url(self, db: str) -> str:
        return self._make_url(self.admin_url).set(database=db).render_as_string(
            hide_password=False)

    def create(self, name: str) -> str:
        db = self._db(name)
        with psycopg.connect(self.admin_url, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{db}" TEMPLATE "{self.source_db}"')
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
