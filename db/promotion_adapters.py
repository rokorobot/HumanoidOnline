"""Network adapters for the approved catalogue promotion (workstream B).

Implements the `Branches`, `Github` and `Web` interfaces of
apps/api/app/services/discovery/promotion_execute.py with the standard library only. They live
in db/ (operational tooling, like import_catalogue.py) and NOT under apps/api/app, because the
app tree is guarded against importing any HTTP client (tests/test_acquisition_schema.py,
`_SLICE_A_HTTP_EXCEPTIONS`). They talk to Neon, GitHub and the project's own public site,
never to a manufacturer.

Secrets come from the environment (NEON_API_KEY, NEON_PROJECT_ID, GITHUB_TOKEN,
GITHUB_REPOSITORY) and are never printed or put in an error message. Neon safety/rehearsal
branches are created with an explicit parent (NEON_PRODUCTION_BRANCH_ID, and optionally
NEON_PRODUCTION_BRANCH_NAME, default "production"), verified before the first create.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

NEON_API = "https://console.neon.tech/api/v2"
INCIDENT_LABEL = "promotion-incident"


def _json_request(method: str, url: str, headers: dict, body: dict | None = None,
                  timeout: float = 60.0) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Accept": "application/json", "Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:      # noqa: S310
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


class BranchOriginError(RuntimeError):
    """A branch is not provably a copy of production. Ids and names only: safe to report."""

    safe = True


def _endpoint_host(host: str) -> str:
    """A Neon host without the pooler marker: 'ep-x-pooler.r.aws.neon.tech' -> 'ep-x.r...'."""
    head, _, rest = (host or "").lower().partition(".")
    return f"{head.removesuffix('-pooler')}.{rest}"


class NeonBranches:
    """Neon branches via the REST API. NEON_API_KEY / NEON_PROJECT_ID come from the
    environment and are never printed. Every branch is created from the production branch
    NEON_PRODUCTION_BRANCH_ID, passed explicitly as `parent_id` and checked in the response;
    before the first create the parent is verified to exist, be the project's default branch,
    be named `production` (NEON_PRODUCTION_BRANCH_NAME) and own the endpoint of the production
    URL. Any mismatch raises BranchOriginError (the executor then refuses)."""

    requires_exclusive_source = False
    local = False

    def __init__(self, request=None, sleep=time.sleep, production_url: str | None = None):
        self._key = os.environ.get("NEON_API_KEY", "")
        self._project = os.environ.get("NEON_PROJECT_ID", "")
        if not self._key or not self._project:
            raise RuntimeError("NEON_API_KEY and NEON_PROJECT_ID are required")
        self._parent = os.environ.get("NEON_PRODUCTION_BRANCH_ID", "")
        if not self._parent:
            raise RuntimeError("NEON_PRODUCTION_BRANCH_ID is required")
        self._parent_name = os.environ.get("NEON_PRODUCTION_BRANCH_NAME", "production")
        self._database = os.environ.get("NEON_DATABASE_NAME", "neondb")
        self._role = os.environ.get("NEON_ROLE_NAME", "neondb_owner")
        self._request = request or _json_request
        self._sleep = sleep
        self._ids: dict[str, str] = {}
        self._production_url = production_url
        self._verified: dict | None = None
        self.origins: dict[str, dict] = {}

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        return self._request(method, f"{NEON_API}/projects/{self._project}{path}",
                             {"Authorization": f"Bearer {self._key}"}, body)

    def _wait(self, operations: list[dict]) -> None:
        for op in operations or []:
            for _ in range(60):
                state = self._call("GET", f"/operations/{op['id']}").get(
                    "operation", {}).get("status")
                if state == "finished":
                    break
                if state in ("failed", "cancelled", "error"):
                    raise RuntimeError(f"neon operation {state}")
                self._sleep(2)

    def verify_origin(self, production_url: str | None = None) -> dict:
        """Prove the parent branch IS production. Cached after the first success."""
        if production_url:
            self._production_url = production_url
        if self._verified is not None:
            return self._verified
        if not self._production_url:
            raise BranchOriginError("the production URL is unknown: cannot verify the parent")
        try:
            branch = self._call("GET", f"/branches/{self._parent}").get("branch") or {}
            endpoints = self._call("GET", f"/branches/{self._parent}/endpoints").get(
                "endpoints", [])
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise BranchOriginError(
                f"cannot read the production branch {self._parent} ({type(exc).__name__})"
            ) from None
        if branch.get("id") != self._parent:
            raise BranchOriginError(f"production branch {self._parent} does not exist")
        if not (branch.get("default") or branch.get("primary")):
            raise BranchOriginError(f"branch {self._parent} is not the project's default branch")
        if branch.get("name") != self._parent_name:
            raise BranchOriginError(f"branch {self._parent} is named {branch.get('name')!r}, "
                                    f"not {self._parent_name!r}")
        host = _endpoint_host(urllib.parse.urlsplit(self._production_url).hostname or "")
        if host not in {_endpoint_host(e.get("host", "")) for e in endpoints}:
            raise BranchOriginError(f"the production URL's endpoint host does not belong to "
                                    f"branch {self._parent}")
        self._verified = {"parent_id": self._parent, "parent_name": branch.get("name"),
                          "default": True, "endpoint_host_matches": True}
        return self._verified

    def create(self, name: str) -> str:
        self.verify_origin()
        made = self._call("POST", "/branches", {
            "branch": {"name": name, "parent_id": self._parent},
            "endpoints": [{"type": "read_write"}]})
        branch = made["branch"]
        branch_id = branch["id"]
        self._ids[name] = branch_id
        self.origins[name] = {"branch_id": branch_id, "parent_id": branch.get("parent_id"),
                              "parent_lsn": branch.get("parent_lsn")}
        if branch.get("parent_id") != self._parent:
            raise BranchOriginError(f"branch {branch_id} was created from "
                                    f"{branch.get('parent_id')!r}, not from production")
        self._wait(made.get("operations", []))
        uris = made.get("connection_uris") or []
        if uris:
            return uris[0]["connection_uri"]
        endpoint = made["endpoints"][0]["id"]
        query = urllib.parse.urlencode({"branch_id": branch_id, "endpoint_id": endpoint,
                                        "database_name": self._database,
                                        "role_name": self._role})
        return self._call("GET", f"/connection_uri?{query}")["uri"]

    def delete(self, name: str) -> None:
        branch_id = self._ids.get(name)
        if branch_id is None:
            listing = self._call("GET", "/branches").get("branches", [])
            branch_id = next((b["id"] for b in listing if b.get("name") == name), None)
        if branch_id is None:
            return
        self._wait(self._call("DELETE", f"/branches/{branch_id}").get("operations", []))


class GithubApi:
    """Incident issue and PR comment via the GitHub REST API (GITHUB_TOKEN, GITHUB_REPOSITORY)."""

    def __init__(self, commit: str, request=None):
        self._token = os.environ.get("GITHUB_TOKEN", "")
        self._repo = os.environ.get("GITHUB_REPOSITORY", "")
        if not self._token or not self._repo:
            raise RuntimeError("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
        self._commit = commit
        self._request = request or _json_request

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        return self._request(method, f"https://api.github.com/repos/{self._repo}{path}", {
            "Authorization": f"Bearer {self._token}", "X-GitHub-Api-Version": "2022-11-28",
            "Accept": "application/vnd.github+json"}, body)

    def open_incident_exists(self) -> bool:
        issues = self._call("GET", f"/issues?labels={INCIDENT_LABEL}&state=open&per_page=5")
        return any("pull_request" not in i for i in issues)

    def open_incident(self, title: str, body: str) -> None:
        self._call("POST", "/issues", {"title": title, "body": body, "labels": [INCIDENT_LABEL]})

    def comment(self, body: str) -> None:
        pulls = self._call("GET", f"/commits/{self._commit}/pulls")
        if pulls:
            self._call("POST", f"/issues/{pulls[0]['number']}/comments", {"body": body})


class GithubApprovals:
    """The merged manifest PR as the approval (GITHUB_TOKEN, GITHUB_REPOSITORY). Read-only."""

    simulated = False

    def __init__(self, request=None):
        self._token = os.environ.get("GITHUB_TOKEN", "")
        self._repo = os.environ.get("GITHUB_REPOSITORY", "")
        if not self._token or not self._repo:
            raise RuntimeError("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
        self._request = request or _json_request

    def _call(self, path: str) -> Any:
        return self._request("GET", f"https://api.github.com/repos/{self._repo}{path}", {
            "Authorization": f"Bearer {self._token}", "X-GitHub-Api-Version": "2022-11-28",
            "Accept": "application/vnd.github+json"}, None)

    def pull_request(self, number: int) -> dict:
        pr = self._call(f"/pulls/{int(number)}")
        files: list[str] = []
        for page in range(1, 31):               # GitHub lists at most 3000 files of a PR
            batch = self._call(f"/pulls/{int(number)}/files?per_page=100&page={page}")
            for f in batch:
                files.append(f["filename"])
                if f.get("previous_filename"):          # a rename also touches the old path
                    files.append(f["previous_filename"])
            if len(batch) < 100:
                break
        else:
            raise RuntimeError("PR has too many files to inspect")
        return {"merged": bool(pr.get("merged")), "base_ref": (pr.get("base") or {}).get("ref"),
                "head_sha": (pr.get("head") or {}).get("sha"),
                "merge_commit_sha": pr.get("merge_commit_sha"),
                "merged_by": (pr.get("merged_by") or {}).get("login"), "files": files}


class HttpWeb:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def get(self, url: str) -> tuple[int, str]:
        req = urllib.request.Request(url, headers={"User-Agent": "humanoidonline-promotion/1"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:   # noqa: S310
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, ""
