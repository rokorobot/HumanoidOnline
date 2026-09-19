#!/usr/bin/env python3
"""Read-only CI/production observer. Python 3.12 stdlib; no application imports."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPO = "rokorobot/HumanoidOnline"
GH = f"https://api.github.com/repos/{REPO}"
MAX_BODY = 4 * 1024 * 1024


class ObservationError(Exception):
    def __init__(self, state, message):
        self.state = state
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a provider token, or accept a login redirect.


class Reader:
    def __init__(self, env, deadline):
        self.deadline = deadline
        self.tokens = {
            "api.github.com": env.get("GITHUB_TOKEN", ""),
            "api.netlify.com": env.get("WATCHER_NETLIFY_TOKEN", ""),
            "api.vercel.com": env.get("WATCHER_VERCEL_TOKEN", ""),
        }
        self.opener = build_opener(NoRedirect())

    def get(self, url, *, as_json=True):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ObservationError("PENDING", "Observation deadline reached")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ObservationError("UNVERIFIED", "HTTPS URL without credentials required")
        headers = {"User-Agent": "HumanoidOnline-deployment-watcher", "Cache-Control": "no-cache"}
        token = self.tokens.get(parsed.hostname)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if parsed.hostname == "api.github.com":
            headers.update(
                {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
            )
        try:
            with self.opener.open(
                Request(url, headers=headers, method="GET"), timeout=min(10, remaining)
            ) as response:
                if response.status != 200:
                    raise ObservationError(
                        "PENDING", f"Expected HTTP 200, received {response.status}"
                    )
                body = response.read(MAX_BODY + 1)
                content_type = response.headers.get("Content-Type", "")
        except HTTPError as exc:
            state = "UNVERIFIED" if exc.code in (401, 403) else "PENDING"
            # Do not put response bodies, headers or credential values in reports.
            raise ObservationError(state, f"HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ObservationError("PENDING", "Network request failed or timed out") from None
        if len(body) > MAX_BODY:
            raise ObservationError("UNVERIFIED", "Response exceeds size limit")
        if not as_json:
            return body.decode("utf-8", errors="replace"), content_type
        try:
            return json.loads(body)
        except (ValueError, UnicodeError):
            raise ObservationError("UNVERIFIED", "Expected valid JSON") from None


def row(name, state, detail, url=""):
    return {"name": name, "state": state, "detail": detail, "url": url}


def observe(name, fn):
    try:
        return fn()
    except ObservationError as exc:
        return row(name, exc.state, str(exc))
    except (KeyError, TypeError, ValueError, AttributeError):
        return row(name, "UNVERIFIED", "Unexpected provider response shape")


def origin(value):
    p = urlsplit(value)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.port not in (None, 443)
        or p.query
        or p.fragment
        or p.path not in ("", "/")
    ):
        raise ObservationError(
            "UNVERIFIED", "Configure an HTTPS origin without path or credentials"
        )
    return f"https://{p.hostname}"


def pages(reader, url, key=None):
    result = []
    for page in range(1, 21):
        data = reader.get(f"{url}{'&' if '?' in url else '?'}per_page=100&page={page}")
        items = data[key] if key else data
        if not isinstance(items, list):
            raise ObservationError("UNVERIFIED", "Expected paginated list")
        result.extend(items)
        if len(items) < 100:
            return result
    raise ObservationError("UNVERIFIED", "Pagination limit reached; refusing partial evidence")


def ci_observation(reader, run, expected_sha):
    url = f"https://github.com/{REPO}/actions/runs/{run['id']}"
    if (
        run.get("head_sha") != expected_sha
        or run.get("path") != ".github/workflows/ci.yml"
        or run.get("repository", {}).get("full_name") != REPO
    ):
        return row(
            "CI", "UNVERIFIED", "Run does not match repository, workflow and exact commit", url
        )
    if run.get("status") != "completed":
        return row("CI", "PENDING", "CI is still running", url)
    jobs = pages(
        reader, f"{GH}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs", "jobs"
    )
    failures = []
    for job in jobs:
        if job.get("conclusion") not in ("success", "skipped"):
            failed_steps = [
                str(s.get("name", "unnamed"))
                for s in job.get("steps", [])
                if s.get("conclusion") in ("failure", "cancelled", "timed_out")
            ]
            detail = ", ".join(failed_steps) or job.get("conclusion") or "pending"
            failures.append(f"{job.get('name', 'job')}: {detail}")
    if run.get("conclusion") != "success" or failures:
        return row(
            "CI",
            "FAIL",
            f"Attempt {run['run_attempt']}: {run.get('conclusion')}; " + "; ".join(failures),
            url,
        )
    if not jobs:
        return row("CI", "UNVERIFIED", "Completed run has no job evidence", url)
    return row(
        "CI",
        "PASS",
        f"Attempt {run['run_attempt']}: {len(jobs)} jobs; includes post-job cleanup",
        url,
    )


def current_main(reader, sha):
    current = reader.get(f"{GH}/git/ref/heads/main")["object"]["sha"]
    if current != sha:
        return row(
            "main",
            "SUPERSEDED",
            f"Current main is {current}; historical commit is not certified live",
        )
    return row("main", "PASS", f"main still points to {sha}")


def netlify_observation(reader, env, sha):
    name = "Netlify production"
    site_id = env.get("WATCHER_NETLIFY_SITE_ID", "")
    if not site_id or not env.get("WATCHER_NETLIFY_TOKEN"):
        return row(
            name, "UNVERIFIED", "Configure WATCHER_NETLIFY_SITE_ID and WATCHER_NETLIFY_TOKEN"
        )
    web = origin(env.get("WATCHER_WEB_ORIGIN", "https://humanoidonline.com"))
    site = reader.get(f"https://api.netlify.com/api/v1/sites/{quote(site_id, safe='')}")
    if site.get("id") != site_id or origin(site.get("ssl_url", "")) != web:
        return row(
            name, "UNVERIFIED", "Site ID or primary production origin does not match configuration"
        )
    deploy = site.get("published_deploy") or {}
    actual = deploy.get("commit_ref")
    site_name = quote(site.get("name", ""), safe="")
    deploy_id = quote(deploy.get("id", ""), safe="")
    evidence = f"https://app.netlify.com/sites/{site_name}/deploys/{deploy_id}"
    if not actual:
        return row(name, "UNVERIFIED", "Published deployment has no commit_ref", evidence)
    if actual != sha:
        return row(name, "PENDING", f"Published commit is {actual}; waiting for {sha}", evidence)
    if deploy.get("context") != "production":
        return row(name, "UNVERIFIED", "Published deployment lacks production context", evidence)
    if deploy.get("state") in ("error", "failed"):
        return row(name, "FAIL", "Published deployment reports failure", evidence)
    if deploy.get("state") != "ready":
        return row(name, "PENDING", "Published deployment is not ready", evidence)
    return row(
        name, "PASS", f"Published deployment {deploy['id']} serves exact commit {sha}", evidence
    )


def vercel_observation(reader, env, sha, role):
    name = f"Vercel {role.lower()} production"
    prefix = f"WATCHER_VERCEL_{role}_"
    project = env.get(prefix + "PROJECT_ID", "")
    alias = env.get(prefix + "ALIAS", "")
    if not project or not alias or not env.get("WATCHER_VERCEL_TOKEN"):
        return row(
            name,
            "UNVERIFIED",
            f"Configure {prefix}PROJECT_ID, {prefix}ALIAS and WATCHER_VERCEL_TOKEN",
        )
    if urlsplit(origin("https://" + alias)).hostname != alias:
        return row(name, "UNVERIFIED", "Alias must be a bare lowercase hostname")
    if role == "API" and origin(env.get("WATCHER_API_ORIGIN", "")) != "https://" + alias:
        return row(name, "UNVERIFIED", "API health origin must equal the verified Vercel API alias")
    query = {"teamId": env["WATCHER_VERCEL_TEAM_ID"]} if env.get("WATCHER_VERCEL_TEAM_ID") else {}
    alias_data = reader.get(
        f"https://api.vercel.com/v4/aliases/{quote(alias, safe='')}?{urlencode(query)}"
    )
    if (
        alias_data.get("projectId") != project
        or alias_data.get("alias") != alias
        or alias_data.get("redirect")
    ):
        return row(name, "UNVERIFIED", "Alias does not directly serve the configured project")
    deployment_id = alias_data.get("deploymentId")
    if not deployment_id:
        return row(name, "PENDING", "Production alias has no deployment")
    query["withGitRepoInfo"] = "true"
    data = reader.get(
        f"https://api.vercel.com/v13/deployments/{quote(deployment_id, safe='')}?{urlencode(query)}"
    )
    if data.get("id") != deployment_id:
        return row(name, "UNVERIFIED", "Deployment identity mismatch")
    # Some API versions return gitSource; older ones provide githubCommitSha.
    git_sha = (data.get("gitSource") or {}).get("sha")
    meta_sha = (data.get("meta") or {}).get("githubCommitSha")
    if git_sha and meta_sha and git_sha != meta_sha:
        return row(name, "UNVERIFIED", "Conflicting deployment commit metadata")
    actual = git_sha or meta_sha
    if not actual:
        return row(name, "UNVERIFIED", "Deployment has no Git commit metadata")
    if actual != sha:
        return row(name, "PENDING", f"Alias serves {actual}; waiting for {sha}", "https://" + alias)
    if data.get("target") != "production":
        return row(name, "UNVERIFIED", "Alias points to a non-production deployment")
    if data.get("readyState") in ("ERROR", "CANCELED"):
        return row(name, "FAIL", "Aliased deployment failed or was cancelled")
    if data.get("readyState") != "READY":
        return row(name, "PENDING", "Aliased deployment is not ready")
    return row(
        name, "PASS", f"Alias serves deployment {deployment_id} at {sha}", "https://" + alias
    )


def health_observations(reader, env):
    api = origin(env.get("WATCHER_API_ORIGIN", ""))
    web = origin(env.get("WATCHER_WEB_ORIGIN", "https://humanoidonline.com"))
    checks = []
    for path, expected in (
        ("/health", {"status": "ok"}),
        ("/ready", {"status": "ok", "database": "up"}),
    ):
        url = api + path

        def api_check(url=url, expected=expected):
            data = reader.get(url)
            ok = isinstance(data, dict) and all(data.get(k) == v for k, v in expected.items())
            return row(
                url,
                "PASS" if ok else "PENDING",
                "Expected health payload" if ok else "Unexpected health payload",
                url,
            )

        checks.append(observe(url, api_check))
    for path in ("/", "/robots", "/manufacturers", "/find-a-humanoid"):
        url = web + path

        def web_check(url=url):
            body, content_type = reader.get(url, as_json=False)
            ok = "text/html" in content_type.lower() and "humanoid" in body.lower()
            return row(
                url,
                "PASS" if ok else "PENDING",
                "HTTP 200 and HTML marker" if ok else "Unexpected page content",
                url,
            )

        checks.append(observe(url, web_check))
    return checks


def snapshot(reader, env, run_id, sha):
    run = reader.get(f"{GH}/actions/runs/{run_id}")
    checks = [observe("CI", lambda: ci_observation(reader, run, sha))]
    if checks[0]["state"] == "UNVERIFIED":
        return "unverified", checks
    production = run.get("event") == "push" and run.get("head_branch") == "main"
    scope = "production" if production else "CI only (PR/non-production run)"
    if not production:
        # A successful PR CI run must never certify the existing production site.
        checks.append(
            row(
                "Production",
                "NOT_CHECKED",
                "Production observation only follows a main push CI run",
            )
        )
        return scope, checks
    checks.append(observe("main", lambda: current_main(reader, sha)))
    if checks[-1]["state"] == "SUPERSEDED":
        return scope, checks
    checks.append(observe("Netlify production", lambda: netlify_observation(reader, env, sha)))
    for role in ("API", "WEB"):
        checks.append(
            observe(
                f"Vercel {role.lower()} production",
                lambda role=role: vercel_observation(reader, env, sha, role),
            )
        )
    if all(c["state"] == "PASS" for c in checks):
        try:
            checks.extend(health_observations(reader, env))
        except ObservationError as exc:
            checks.append(row("Live health", exc.state, str(exc)))
        # Recheck mutable aliases/site pointer after health to catch a deployment
        # changing between identity verification and the live probes.
        checks.append(
            observe("Netlify production recheck", lambda: netlify_observation(reader, env, sha))
        )
        for role in ("API", "WEB"):
            checks.append(
                observe(
                    f"Vercel {role} recheck",
                    lambda role=role: vercel_observation(reader, env, sha, role),
                )
            )
        checks.append(observe("main recheck", lambda: current_main(reader, sha)))
    else:
        checks.append(
            row(
                "Live health", "NOT_CHECKED", "Waiting for CI and all production identities to pass"
            )
        )
    return scope, checks


def outcome(checks, expired=False):
    states = {c["state"] for c in checks}
    for state in ("SUPERSEDED", "FAIL", "UNVERIFIED"):
        if state in states:
            return state
    if "PENDING" in states:
        return "TIMEOUT" if expired else "PENDING"
    return "PASS" if "PASS" in states else "UNVERIFIED"


def markdown(report):
    def safe(value):
        return (
            html.escape(str(value))
            .replace("|", "&#124;")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("`", "&#96;")
        )

    lines = [
        f"# HumanoidOnline watcher: {report['result']}",
        "",
        f"Scope: **{safe(report['scope'])}**",
        "",
        f"Commit: `{safe(report['sha'])}` · CI run: {safe(report['run_id'])}",
        "",
        f"Observed at: {safe(report['observed_at'])}",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    for check in report["checks"]:
        evidence = safe(check["detail"])
        if check["url"]:
            # Keep provider-returned text as escaped text, never executable HTML.
            evidence += " — [source](" + safe(check["url"]) + ")"
        lines.append(f"| {safe(check['name'])} | {check['state']} | {evidence} |")
    lines += [
        "",
        "Read-only observation; no repairs, reruns, merges, deployments or data writes.",
        "PASS is limited to the stated scope and observation time. "
        "HTTP probes do not replace browser journey tests.",
        "",
    ]
    return "\n".join(lines)


def watch(
    reader, env, run_id, sha, deadline, interval, output, *, clock=time.monotonic, sleep=time.sleep
):
    while True:
        try:
            scope, checks = snapshot(reader, env, run_id, sha)
        except ObservationError as exc:
            scope, checks = "unverified", [row("Observation", exc.state, str(exc))]
        except (KeyError, TypeError, ValueError, AttributeError):
            scope, checks = (
                "unverified",
                [row("Observation", "UNVERIFIED", "Unexpected provider response shape")],
            )
        result = outcome(checks, expired=clock() >= deadline)
        report = {
            "version": 1,
            "repository": REPO,
            "sha": sha,
            "run_id": run_id,
            "scope": scope,
            "observed_at": datetime.now(UTC).isoformat(),
            "result": result,
            "checks": checks,
        }
        output.mkdir(parents=True, exist_ok=True)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (output / "report.md").write_text(markdown(report), encoding="utf-8")
        if result != "PENDING":
            return report
        sleep(min(interval, max(0, deadline - clock())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=os.getenv("WATCHER_CI_RUN_ID", ""))
    parser.add_argument("--sha", default=os.getenv("WATCHER_EXPECTED_SHA", ""))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("var/deployment-watcher"))
    args = parser.parse_args()
    if not re.fullmatch(r"[1-9][0-9]*", args.run_id):
        parser.error("--run-id must be a positive numeric CI run ID")
    if args.sha and not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        parser.error("--sha must be a full 40-character commit SHA")
    if not 1 <= args.timeout <= 1200 or not 1 <= args.interval <= 60:
        parser.error("timeout must be 1..1200 seconds; interval 1..60 seconds")
    deadline = time.monotonic() + args.timeout
    reader = Reader(os.environ, deadline)
    sha = args.sha
    if not sha:
        try:
            sha = reader.get(f"{GH}/actions/runs/{args.run_id}")["head_sha"]
            if not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise ValueError("bad sha")
        except (ObservationError, KeyError, ValueError, TypeError):
            # Let watch produce an explicit report even when target lookup failed.
            sha = "UNKNOWN"
    report = watch(reader, os.environ, args.run_id, sha, deadline, args.interval, args.output)
    text = markdown(report)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(text)
    print(f"Watcher: {report['result']} ({report['scope']}); report: {args.output / 'report.md'}")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
