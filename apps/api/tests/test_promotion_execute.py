"""Catalogue promotion execution (PR B): the fail-closed sequence of design section 4.

SYNTHETIC data only (see promotion_support.py). `LocalBranches` (CREATE DATABASE ... TEMPLATE)
stands in for Neon; GitHub and the public web are recording fakes. Each test starts from its own
writable "production" copy.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import UTC, date, datetime

import psycopg
import pytest
from promotion_support import (  # noqa: F401
    KEY,
    PEER,
    ROBOT,
    VALUE,
    FakeApprovals,
    FakeWeb,
    compare_html,
    page_html,
    template_db,
    world,
)

from app.cli import promotion as cli
from app.services.discovery import promotion_execute as px
from app.services.discovery import promotion_manifest as pm


@pytest.fixture
def compare_supported(monkeypatch):
    """Declare the synthetic spec KEY as a field the compare surface renders (it is not: this
    makes the SUPPORTED code path testable without touching the real field list)."""
    real = px.compare_supported_fields()
    monkeypatch.setattr(px, "compare_supported_fields", lambda: real | {KEY})


def adapters():
    return pm.load_db_tool("promotion_adapters")


def steps(receipt):
    return [(s["step"], s["status"]) for s in receipt["steps"]]


def assert_untouched(world, before):  # noqa: F811
    assert world.spec_rows() == []
    assert world.fingerprints() == before


# --------------------------------------------------------------------------- success ------


def test_single_approval_executes_end_to_end_and_leaves_a_receipt(world):  # noqa: F811
    manifest = world.manifest
    receipt = world.execute()
    assert receipt["outcome"] == "SUCCESS", receipt
    assert world.spec_rows() == [(KEY, VALUE)]
    assert [s for s, _ in steps(receipt)] == [
        "manifest", "approval", "halt_switch", "concurrency", "privileges", "already_applied",
        "eligibility", "base_drift", "safety_branch", "rehearsal", "apply", "post_verify",
        "public_verify"]
    assert receipt["digest"] == manifest["digest"] and receipt["robots"] == [ROBOT]
    assert receipt["fields"] == [f"{ROBOT}:{KEY}"] and receipt["commit"] == "c0ffee"
    assert receipt["rehearsal"]["identity_added"] == [f"specification {ROBOT}:-|{KEY}"]
    assert receipt["post_verify"]["publication_and_status_unchanged"] is True
    assert receipt["after_fingerprints"] != manifest["base"]["robot_fingerprints"]
    # an extended spec is not rendered on compare: that surface is NOT_APPLICABLE (recorded,
    # never a pass); API and page are mandatory and passed
    results = receipt["public_verification"]
    assert {r["surface"] for r in results} == {"api", "page", "compare"}
    assert {r["surface"] for r in results if r["status"] == "PASS"} == {"api", "page"}
    compare = [r for r in results if r["surface"] == "compare"][0]
    assert compare["applicability"] == "NOT_APPLICABLE" and compare["ok"] is False
    assert receipt["public_summary"] == {"api": "PASS", "page": "PASS",
                                         "compare": "NOT_APPLICABLE"}
    assert receipt["compare_applicability"][f"{ROBOT}:{KEY}"]["applicability"] == "NOT_APPLICABLE"
    assert "compare=NOT_APPLICABLE" in px.render_receipt(receipt)
    # the safety branch is retained, the rehearsal branch is gone
    assert len(world.branch_dbs()) == 1 and world.branch_dbs()[0].startswith("promo_")
    assert receipt["branches"]["rehearsal_deleted"] is True
    assert len(world.github.comments) == 1 and world.github.incidents == []
    assert "humanoid:humanoid" not in json.dumps(receipt)       # no connection string
    assert "CATALOGUE_DATABASE_URL" not in json.dumps(receipt)


def test_a_successful_promotion_advances_the_catalogue_updated_date(world):  # noqa: F811
    """Migration 0026: the executor's apply (as the additions-only routine role) moves the
    public CATALOGUE UPDATED date of a published robot; the refused re-run does not."""
    def fresh():
        return world.sql("SELECT latest_public_update_at, latest_update_at "
                         "FROM catalogue_freshness")[0]

    assert world.sql("SELECT is_published FROM robot WHERE slug = %s", (ROBOT,)) == [(True,)]
    before = fresh()
    assert world.execute()["outcome"] == "SUCCESS"
    after = fresh()
    assert after[0] > before[0] and after[1] > before[1]
    assert world.execute()["outcome"] == "ALREADY_APPLIED"
    assert fresh() == after


def test_the_same_manifest_never_applies_twice(world):  # noqa: F811
    first = world.execute()
    assert first["outcome"] == "SUCCESS"
    audit = world.sql("SELECT count(*) FROM catalogue_write_audit")
    state = world.fingerprints()
    branches = world.branch_dbs()
    second = world.execute()
    assert second["outcome"] == "ALREADY_APPLIED", second
    assert world.fingerprints() == state
    assert world.sql("SELECT count(*) FROM catalogue_write_audit") == audit
    assert world.branch_dbs() == branches                      # no new branch, nothing created
    assert [s for s, _ in steps(second)] == [
        "manifest", "approval", "halt_switch", "concurrency", "privileges", "already_applied"]
    assert world.spec_rows() == [(KEY, VALUE)]                  # one row, not two


def test_dry_run_rehearses_but_never_touches_production(world):  # noqa: F811
    before = world.fingerprints()
    receipt = world.execute(dry_run=True)
    assert receipt["outcome"] == "DRY_RUN_OK", receipt
    assert ("apply", "SKIPPED_DRY_RUN") in steps(receipt)
    assert_untouched(world, before)
    assert world.branch_dbs() == []                             # both branches cleaned up


# ------------------------------------------------------------------------- refusals ------


def test_manifest_modified_after_approval_is_refused(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    bad = copy.deepcopy(world.manifest)
    bad["items"][0]["proposed_value"] = "edited after approval"
    receipt = world.execute(bad)
    assert receipt["outcome"] == "REFUSED:manifest" and "digest" in receipt["reason"]
    assert_untouched(world, before)
    assert world.branch_dbs() == []


def test_extra_catalogue_edit_is_refused(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    path = world.head / "robots" / f"{ROBOT}.json"
    path.write_text(path.read_text(encoding="utf-8").replace(
        '"announced_year": 2024', '"announced_year": 2023'), encoding="utf-8")
    receipt = world.execute()
    assert receipt["outcome"] == "REFUSED:manifest" and ROBOT in receipt["reason"]
    assert_untouched(world, before)


def test_non_routine_manifest_never_executes(world):  # noqa: F811
    restricted = world.propose([world.item(definition="price_usd")])
    before = world.fingerprints()
    receipt = world.execute(restricted)
    assert receipt["outcome"] == "REFUSED:manifest" and "only ROUTINE" in receipt["reason"]
    assert_untouched(world, before)


def test_concurrent_promotion_is_refused(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    with psycopg.connect(world.url, autocommit=True) as other:
        assert other.execute("SELECT pg_try_advisory_lock(hashtext('catalogue-promotion'))"
                             ).fetchone()[0]
        receipt = world.execute()
    assert receipt["outcome"] == "REFUSED:concurrency", receipt
    assert "another promotion" in receipt["reason"]
    assert_untouched(world, before)
    assert world.branch_dbs() == []


def test_running_discovery_crawl_blocks_promotion(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    world.sql("INSERT INTO crawl_run (source_id, adapter_key, adapter_version, operator, status)"
              " SELECT id, 'synthetic', '1', 'test', 'RUNNING' FROM discovery_source")
    receipt = world.execute()
    assert receipt["outcome"] == "REFUSED:concurrency" and "RUNNING" in receipt["reason"]
    assert world.spec_rows() == []
    world.sql("DELETE FROM crawl_run WHERE status = 'RUNNING'")
    assert world.fingerprints() == before


@pytest.mark.parametrize("mode", ["open_incident", "unreadable"])
def test_open_incident_halts_promotions(world, mode):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    if mode == "open_incident":
        world.github.incident_open = True
    else:
        world.github.read_error = True          # cannot tell: fail closed
    receipt = world.execute()
    assert receipt["outcome"] == "REFUSED:halt_switch", receipt
    assert_untouched(world, before)


def test_production_drift_since_review_refuses_as_base_drift(world):  # noqa: F811
    world.prepare()
    world.sql("UPDATE robot SET summary = 'edited by someone else' WHERE slug = %s", (ROBOT,))
    receipt = world.execute()
    assert receipt["outcome"] == "REFUSED:base_drift", receipt
    assert ROBOT in receipt["fingerprint_drift"]
    assert world.spec_rows() == [] and world.branch_dbs() == []


def test_unavailable_database_refuses_and_writes_nothing(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    gone = world.url.rsplit("/", 1)[0] + "/promo_no_such_database"
    receipt = world.execute(production=px.StaticProduction(gone))
    assert receipt["outcome"] == "REFUSED:concurrency" and "database unavailable" in receipt[
        "reason"]
    assert "humanoid:humanoid" not in json.dumps(receipt)
    assert_untouched(world, before)
    assert world.branch_dbs() == []


def test_safety_branch_failure_refuses_before_any_write(world):  # noqa: F811
    class Broken:
        requires_exclusive_source = False

        def create(self, name):
            raise OSError("secret-token-123 could not create")

        def delete(self, name):
            raise AssertionError("nothing to delete")

    world.prepare()
    before = world.fingerprints()
    receipt = world.execute(branches=Broken())
    assert receipt["outcome"] == "REFUSED:safety_branch", receipt
    assert "secret-token-123" not in json.dumps(receipt)          # exception type only
    assert "OSError" in receipt["reason"]
    assert_untouched(world, before)


def test_unexpected_rehearsal_difference_refuses_and_production_stays_untouched(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    path = world.head / "robots" / f"{ROBOT}.json"
    path.write_text(path.read_text(encoding="utf-8").replace(
        '"announced_year": 2024', '"announced_year": 2023'), encoding="utf-8")
    # the catalogue-equality check is what normally stops this; without a base the rehearsal
    # preflight is the second line of defence
    receipt = world.execute(base_catalogue_dir=None)
    assert receipt["outcome"] == "REFUSED:rehearsal", receipt
    assert receipt["rehearsal"]["unexplained"] >= 1
    assert "preflight" in receipt["reason"]
    assert_untouched(world, before)
    assert world.branch_dbs() == []                               # rehearsal and safety deleted


def test_importer_refusal_at_apply_writes_nothing(world, monkeypatch):  # noqa: F811
    real = px._import

    def refuse_on_production(url, robots, catalogue_dir, **kw):
        if url == world.url:
            raise SystemExit("IMPORT REFUSED - nothing was written")
        return real(url, robots, catalogue_dir, **kw)

    monkeypatch.setattr(px, "_import", refuse_on_production)
    before = world.fingerprints()
    receipt = world.execute()
    assert receipt["outcome"] == "REFUSED:apply", receipt
    assert_untouched(world, before)


# ------------------------------------------------------------------------- incidents ------


def test_public_verification_failure_opens_an_incident_and_does_not_roll_back(world):  # noqa: F811
    manifest = world.manifest
    slept = []
    receipt = world.execute(web=FakeWeb(manifest, healthy=False), retries=3,
                            sleep=slept.append, retry_wait=7)
    assert receipt["outcome"] == "INCIDENT:public_verify", receipt
    assert slept == [7, 7]                                        # bounded retries
    assert len(world.github.incidents) == 1
    title, body = world.github.incidents[0]
    assert "public_verify" in title and "No automatic rollback" in body
    assert world.spec_rows() == [(KEY, VALUE)]                    # committed, not rolled back
    assert len(world.branch_dbs()) == 1                           # safety branch retained
    assert px.LocalBranches._db(receipt["safety_branch_retained"]) == world.branch_dbs()[0]
    # the halt switch stops the next promotion until the owner closes the incident ...
    world.github.incident_open = True
    assert world.execute()["outcome"] == "REFUSED:halt_switch"
    # ... and a retry after it is closed is safe: it recognises the applied state
    world.github.incident_open = False
    retry = world.execute()
    assert retry["outcome"] == "ALREADY_APPLIED" and world.spec_rows() == [(KEY, VALUE)]


def test_post_verify_failure_opens_an_incident(world, monkeypatch):  # noqa: F811
    calls = iter([0, 3])
    monkeypatch.setattr(px, "_dangling", lambda url: next(calls))
    receipt = world.execute()
    assert receipt["outcome"] == "INCIDENT:post_verify", receipt
    assert "dangling audit targets increased" in receipt["reason"]
    assert len(world.github.incidents) == 1
    assert world.spec_rows() == [(KEY, VALUE)]


def test_importer_crash_that_moved_production_is_an_incident(world, monkeypatch):  # noqa: F811
    real = px._import

    def write_then_crash(url, robots, catalogue_dir, **kw):
        real(url, robots, catalogue_dir, **kw)
        if url == world.url:
            raise RuntimeError("connection lost after commit")

    monkeypatch.setattr(px, "_import", write_then_crash)
    receipt = world.execute()
    assert receipt["outcome"] == "INCIDENT:apply", receipt
    assert len(world.github.incidents) == 1


def test_missing_public_base_urls_are_recorded_not_assumed(world):  # noqa: F811
    receipt = world.execute(web=None, api_base=None, web_base=None)
    assert receipt["outcome"] == "SUCCESS"
    assert ("public_verify", "SKIPPED_NO_BASE_URLS") in steps(receipt)


# --------------------------------------------------------------------- public checks ------


def test_public_check_requires_value_and_source_on_the_api(world, compare_supported):  # noqa: F811
    manifest = world.manifest
    item = manifest["items"][0]

    class Web:
        def __init__(self, entry):
            self.entry = entry

        def get(self, url):
            if "/api/robots/" in url:
                return 200, json.dumps({"extended_specs": [self.entry]})
            return 200, (compare_html(item) if "/compare" in url else page_html(item))

    good = {"key": KEY, "value": VALUE, "source_url": item["source_url"],
            "variant_slug": None, "observed_at": item["observed_at"]}
    assert all(r["ok"] for r in px.check_public(manifest, Web(good), "http://a", "http://w"))
    wrong_source = {**good, "source_url": "https://elsewhere.example/"}
    results = px.check_public(manifest, Web(wrong_source), "http://a", "http://w")
    assert [r["surface"] for r in results if not r["ok"]] == ["api"]
    wrong_value = {**good, "value": "other"}
    assert not px.check_public(manifest, Web(wrong_value), "http://a", "http://w")[0]["ok"]


# ------------------------------------------------------------------------- adapters ------


def test_neon_branches_create_and_delete_via_the_rest_api(monkeypatch):
    monkeypatch.setenv("NEON_API_KEY", "key-should-not-leak")
    monkeypatch.setenv("NEON_PROJECT_ID", "proj-1")
    monkeypatch.setenv("NEON_PRODUCTION_BRANCH_ID", "br-prod")
    calls = []

    def request(method, url, headers, body=None, timeout=60.0):
        calls.append((method, url.split("/api/v2")[1], body))
        assert headers["Authorization"] == "Bearer key-should-not-leak"
        if method == "POST":
            return {"branch": {"id": "br-1", "parent_id": "br-prod", "parent_lsn": "0/1A"},
                    "operations": [{"id": "op-1"}],
                    "endpoints": [{"id": "ep-1"}],
                    "connection_uris": [{"connection_uri": "postgresql://u:p@h/db"}]}
        if url.endswith("/branches/br-prod"):
            return {"branch": {"id": "br-prod", "name": "production", "default": True}}
        if url.endswith("/branches/br-prod/endpoints"):
            return {"endpoints": [{"host": "ep-prod-1.eu.aws.neon.tech"}]}
        if "/operations/" in url:
            return {"operation": {"status": "finished"}}
        return {"operations": []}

    branches = adapters().NeonBranches(
        request=request, sleep=lambda s: None,
        production_url="postgresql://u:p@ep-prod-1-pooler.eu.aws.neon.tech/neondb")
    assert branches.create("promo-x") == "postgresql://u:p@h/db"
    branches.delete("promo-x")
    post = [c for c in calls if c[0] == "POST"][0]
    assert post == ("POST", "/projects/proj-1/branches", {
        "branch": {"name": "promo-x", "parent_id": "br-prod"},
        "endpoints": [{"type": "read_write"}]})
    assert calls[-1][:2] == ("DELETE", "/projects/proj-1/branches/br-1")
    assert branches.origins["promo-x"] == {"branch_id": "br-1", "parent_id": "br-prod",
                                           "parent_lsn": "0/1A"}
    monkeypatch.delenv("NEON_API_KEY")
    with pytest.raises(RuntimeError):
        adapters().NeonBranches()


def test_github_api_incident_and_comment(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    sent = []

    def request(method, url, headers, body=None, timeout=60.0):
        sent.append((method, url.split("/repos/o/r")[1], body))
        if "labels=promotion-incident" in url:
            return [{"number": 1, "pull_request": {}}]        # a PR is not an incident issue
        if url.endswith("/pulls"):
            return [{"number": 42}]
        return {}

    api = adapters().GithubApi("abc", request=request)
    assert api.open_incident_exists() is False
    api.open_incident("t", "b")
    api.comment("receipt")
    assert ("POST", "/issues", {"title": "t", "body": "b", "labels": ["promotion-incident"]}) \
        in sent
    assert ("POST", "/issues/42/comments", {"body": "receipt"}) in sent


def test_cli_execute_refuses_a_commit_that_is_not_checked_out(world, tmp_path, capsys):  # noqa: F811
    path = tmp_path / "m.json"
    path.write_text(json.dumps(world.manifest), encoding="utf-8")
    rc = cli.main(["execute", "--manifest", str(path), "--commit", "0" * 40,
                   "--approved-pr", "7", "--database-url", world.url, "--no-github"])
    assert rc == 2 and "not at --commit" in capsys.readouterr().err
    assert world.spec_rows() == []


def test_derived_preflight_manifest_matches_the_items(world):  # noqa: F811
    derived = pm.derive_preflight_manifest(world.manifest)
    assert derived["expected"] == [{"table": "specification", "kind": "ADDED",
                                    "match": {"robot": ROBOT, "definition": KEY}, "count": 1}]


# ------------------------------------------------------------------------- workflows ------


REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]
PROPOSAL = REPO_ROOT / "docs" / "discovery" / "promotion_executor_proposal"


def _workflow(name, folder=None):
    import yaml

    path = (folder or REPO_ROOT / ".github" / "workflows") / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_no_production_promotion_workflow_is_installed():
    """Owner decision D5: GitHub Actions has no production write access. The executor
    workflow exists only as a proposal outside .github/workflows, so GitHub never runs it."""
    assert not (REPO_ROOT / ".github" / "workflows" / "catalogue-promotion.yml").exists()
    for wf in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        assert "CATALOGUE_DATABASE_URL" not in text and "promotion execute" not in text, wf.name


def test_proposed_promotion_workflow_is_inert_unless_enabled_and_single_flight():
    wf = _workflow("catalogue-promotion.yml", PROPOSAL)
    triggers = wf.get("on", wf.get(True))
    assert set(triggers) == {"push", "workflow_dispatch"}                  # no schedule
    assert triggers["push"]["branches"] == ["main"]
    assert "!db/catalogue/promotions/decisions.json" in triggers["push"]["paths"]
    job = wf["jobs"]["promote"]
    assert job["if"] == ("vars.CATALOGUE_PROMOTION_ENABLED == 'true' && "
                         "github.ref == 'refs/heads/main'")
    assert job["environment"] == "catalogue-production"
    assert wf["concurrency"] == {"group": "catalogue-promotion", "cancel-in-progress": False}
    assert wf["permissions"] == {"contents": "read", "issues": "write",
                                 "pull-requests": "write"}
    assert triggers["workflow_dispatch"]["inputs"]["dry_run"]["default"] is True
    secrets = {v for v in job["env"].values() if "secrets." in str(v)}
    assert secrets == {"${{ secrets.CATALOGUE_DATABASE_URL }}", "${{ secrets.NEON_API_KEY }}",
                       "${{ secrets.NEON_PROJECT_ID }}"}


def test_ci_gates_pull_requests_on_promotion_manifest_verification():
    steps = _workflow("ci.yml")["jobs"]["api-test"]["steps"]
    names = [s.get("name") for s in steps]
    step = steps[names.index("Verify catalogue promotion manifests")]
    assert "continue-on-error" not in step                               # gating
    assert "app.cli.promotion verify" in step["run"] and "merge-base" in step["run"]
    assert names.index("Verify catalogue promotion manifests") < names.index("Test")


def test_compare_is_checked_against_a_peer_never_as_a_one_robot_compare(
        world, compare_supported):  # noqa: F811
    """Pilot finding 2026-10-19: `/compare?ids=<one robot>` renders no comparison, so the
    value can never appear there. The check compares with the manifest's published peer; a
    manifest without a peer is REFUSED at the manifest step (before any write), and if
    check_public is ever asked it records a failure, never a pass."""
    import copy

    seen = []
    item0 = world.manifest["items"][0]

    class Web:
        def get(self, url):
            seen.append(url)
            return 200, compare_html(item0) if "/compare" in url else page_html(item0)

    manifest = copy.deepcopy(world.manifest)
    manifest["items"][0]["compare_peer"] = "peer-robot"
    results = px.check_public(manifest, Web(), "http://a", "http://w")
    compare = [r for r in results if r["surface"] == "compare"][0]
    assert compare["url"].endswith(f"/compare?ids={ROBOT},peer-robot") and compare["ok"]
    assert not any(u.endswith(f"/compare?ids={ROBOT}") for u in seen)
    manifest["items"][0]["compare_peer"] = None
    compare = [r for r in px.check_public(manifest, Web(), "http://a", "http://w")
               if r["surface"] == "compare"][0]
    assert compare["ok"] is False and compare["url"] is None and not compare.get("skipped")


# =========================================================================================== #
# Hardening (owner-required items 1-7, 2026-10-19)
# =========================================================================================== #

# ------------------------------------------------------------- 1. approval binding ------


def _refused(receipt, step, *needles):
    assert receipt["outcome"] == f"REFUSED:{step}", receipt
    for needle in needles:
        assert needle in receipt["reason"], receipt["reason"]


def test_receipt_records_the_approving_pr(world):  # noqa: F811
    receipt = world.execute()
    assert receipt["outcome"] == "SUCCESS", receipt
    assert receipt["approval"] == "GITHUB_PR"
    assert receipt["approval_detail"] == {
        "pr": 7, "head_sha": "headsha", "merge_commit_sha": "c0ffee", "merged_by": "owner",
        "manifest_digest": world.manifest["digest"]}


@pytest.mark.parametrize("case, needle", [
    ("not_merged", "not merged"),
    ("wrong_base", "base is 'develop'"),
    ("wrong_commit", "merge commit is not --commit"),
    ("stranger", "not an approver"),
    ("extra_file", "other than the manifest"),
    ("missing_file", "missing"),
    ("manifest_differs", "differs from the manifest being executed"),
    ("manifest_unreadable", "cannot read the manifest at the approved commit"),
    ("api_error", "cannot read PR #7"),
    ("no_allowlist", "allowlist"),
    ("no_approval_source", "no approval source"),
])
def test_approval_must_be_the_merged_pr_of_exactly_this_manifest(world, case, needle):  # noqa: F811
    manifest = world.manifest
    before = world.fingerprints()
    over = {}
    approvals = {
        "not_merged": FakeApprovals(manifest, merged=False),
        "wrong_base": FakeApprovals(manifest, base_ref="develop"),
        "wrong_commit": FakeApprovals(manifest, commit="deadbeef"),
        "stranger": FakeApprovals(manifest, merged_by="someone-else"),
        "extra_file": FakeApprovals(manifest, files=sorted(
            px.expected_pr_files(manifest)) + ["db/schema.sql"]),
        "missing_file": FakeApprovals(manifest, files=sorted(px.expected_pr_files(manifest))[:2]),
        "api_error": FakeApprovals(manifest, error=True),
    }.get(case, FakeApprovals(manifest))
    over["approvals"] = approvals
    if case == "manifest_differs":
        over["read_at_commit"] = lambda c, p: json.dumps({**manifest, "digest": "0" * 64})
    if case == "manifest_unreadable":
        def boom(c, p):
            raise OSError("git show failed")
        over["read_at_commit"] = boom
    if case == "no_allowlist":
        over["approvers"] = set()
    if case == "no_approval_source":
        over["approvals"], over["approved_pr"] = None, None
    receipt = world.execute(**over)
    _refused(receipt, "approval", needle)
    assert [s for s, _ in steps(receipt)] == ["manifest", "approval"]       # nothing else ran
    assert_untouched(world, before)
    assert world.branch_dbs() == []


def test_approver_login_comparison_ignores_case(world):  # noqa: F811
    receipt = world.execute(approvals=FakeApprovals(world.manifest, merged_by="OWNER"),
                            dry_run=True)
    assert receipt["outcome"] == "DRY_RUN_OK", receipt


def test_manifest_read_at_the_commit_not_the_working_tree(world):  # noqa: F811
    """The executed manifest is compared with `git show <commit>:<path>` (an injected reader),
    asked for exactly the manifest path at exactly --commit."""
    asked = []

    def reader(commit, path):
        asked.append((commit, path))
        return json.dumps(world.manifest)

    receipt = world.execute(read_at_commit=reader, dry_run=True)
    assert receipt["outcome"] == "DRY_RUN_OK", receipt
    assert asked == [("c0ffee", "db/catalogue/promotions/synthetic-promo.json")]


def test_simulated_local_approval_is_recorded_and_only_for_local_branches(world):  # noqa: F811
    class Simulated:
        simulated = True

        def pull_request(self, number):
            raise AssertionError("a simulated approval consults no PR")

    receipt = world.execute(approvals=Simulated(), approved_pr=None, approvers=None,
                            read_at_commit=None)
    assert receipt["outcome"] == "SUCCESS", receipt
    assert receipt["approval"] == "SIMULATED_LOCAL"
    assert ("approval", "SIMULATED_LOCAL") in steps(receipt)

    class NotLocal(px.LocalBranches):
        local = False

    again = world.execute(approvals=Simulated(), branches=NotLocal(world.admin, world.name))
    _refused(again, "approval", "only for local-database branches")


def test_github_approvals_adapter_reads_pr_and_every_page_of_files(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    sent = []

    def request(method, url, headers, body=None, timeout=60.0):
        sent.append((method, url.split("/repos/o/r")[1]))
        assert method == "GET" and body is None            # read-only
        if url.endswith("/pulls/7"):
            return {"merged": True, "base": {"ref": "main"}, "head": {"sha": "h1"},
                    "merge_commit_sha": "m1", "merged_by": {"login": "owner"}}
        if url.endswith("&page=1"):
            return [{"filename": f"f{i}"} for i in range(100)]
        return [{"filename": "last", "previous_filename": "was"}]

    pr = adapters().GithubApprovals(request=request).pull_request(7)
    assert pr["merged"] is True and pr["base_ref"] == "main" and pr["merged_by"] == "owner"
    assert pr["head_sha"] == "h1" and pr["merge_commit_sha"] == "m1"
    assert len(pr["files"]) == 102 and {"last", "was"} <= set(pr["files"])
    assert [p for _, p in sent][1:] == ["/pulls/7/files?per_page=100&page=1",
                                        "/pulls/7/files?per_page=100&page=2"]
    monkeypatch.delenv("GITHUB_TOKEN")
    with pytest.raises(RuntimeError):
        adapters().GithubApprovals()


def test_cli_requires_an_approved_pr_and_no_github_does_not_bypass_approval(
        world, tmp_path, monkeypatch, capsys):  # noqa: F811
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["execute", "--manifest", "m.json", "--commit", "abc"])
    path = tmp_path / "m.json"
    path.write_text(json.dumps(world.manifest), encoding="utf-8")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("NEON_API_KEY", "k")
    monkeypatch.setenv("NEON_PROJECT_ID", "p")
    monkeypatch.setenv("NEON_PRODUCTION_BRANCH_ID", "br-prod")
    head = cli._git("rev-parse", "HEAD")
    rc = cli.main(["execute", "--manifest", str(path), "--commit", head, "--approved-pr", "7",
                   "--database-url", world.url, "--no-github", "--dry-run"])
    assert rc == 4 and "GITHUB_TOKEN" in capsys.readouterr().err        # real approvals needed
    assert world.spec_rows() == []


# --------------------------------------------- 2. no unnecessary database permissions ------


def _schema_tables():
    text = (REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    return set(re.findall(r"^CREATE TABLE (\w+)", text, re.MULTILINE))


def _granted_select(sql_text):
    found = {}
    for grant in re.finditer(r"GRANT SELECT ON\s+(.*?)\s+TO\s+(\w+);", sql_text, re.S):
        found[grant.group(2)] = {t.strip() for t in grant.group(1).split(",")}
    return found


@pytest.mark.parametrize("name, role", [("catalogue_promoter_routine.sql",
                                         "catalogue_promoter_routine"),
                                        ("catalogue_importer.sql", "catalogue_importer")])
def test_role_sql_grants_an_explicit_select_list_without_the_lead_tables(name, role):
    text = (PROPOSAL / name).read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    assert not re.search(r"ON\s+ALL\s+TABLES", code, re.I)
    lead = set(pm.load_db_tool("import_preflight").REDACTED_TABLES)
    assert lead == {"commercial_lead", "commercial_lead_robot", "commercial_lead_provider",
                    "buyer_requirement", "match_result"}
    granted = _granted_select(text)[role]
    assert granted == _schema_tables() - lead          # a new table forces an owner decision
    assert not granted & lead


def test_routine_role_sql_is_additions_only():
    text = "\n".join(line for line in (PROPOSAL / "catalogue_promoter_routine.sql").read_text(
        encoding="utf-8").splitlines() if not line.lstrip().startswith("--"))
    grants = re.findall(r"GRANT\s+(\w+)", text)
    assert set(grants) <= {"USAGE", "SELECT", "INSERT"}
    assert re.search(r"GRANT INSERT ON specification, evidence_source TO "
                     r"catalogue_promoter_routine;", text)
    assert not re.search(r"\b(UPDATE|DELETE|TRUNCATE|OWNER|SUPERUSER|ALL)\b", text.upper())


def test_the_production_role_cannot_read_or_write_lead_tables(world):  # noqa: F811
    with psycopg.connect(world.url, autocommit=True) as conn:
        conn.execute("SET search_path TO humanoid, public")
        for table in sorted(pm.excluded_tables()):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        for statement in ("UPDATE robot SET summary = summary", "DELETE FROM specification",
                          "TRUNCATE specification"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)


def test_snapshot_excludes_named_tables_and_fails_closed_on_any_other_unreadable_one(world):  # noqa: F811
    pf = pm.load_db_tool("import_preflight")
    with psycopg.connect(world.url) as conn:
        conn.read_only = True
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            pf.snapshot(conn)                                   # leads unreadable: no skipping
    with psycopg.connect(world.url) as conn:
        conn.read_only = True
        snap = pf.snapshot(conn, pm.excluded_tables())
    assert not set(snap) & pm.excluded_tables() and "robot" in snap
    # the same exclusion on the owner side gives the same view of the rest
    with psycopg.connect(world.owner_url) as conn:
        conn.read_only = True
        assert pf.snapshot(conn, pm.excluded_tables()).keys() == snap.keys()


def test_receipt_records_the_excluded_tables(world):  # noqa: F811
    receipt = world.execute(dry_run=True)
    assert receipt["excluded_tables"] == sorted(pm.excluded_tables())
    assert "commercial_lead" in receipt["excluded_tables"]


def test_unreadable_non_excluded_table_refuses_before_any_write(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    world.sql(f"REVOKE SELECT ON event_log FROM {world.role}")
    receipt = world.execute()
    _refused(receipt, "base_drift", "database unreadable")
    world.sql(f"GRANT SELECT ON event_log TO {world.role}")
    assert_untouched(world, before)
    assert world.branch_dbs() == []


# ------------------------------------------------- 3. routine = non-destructive privileges ------


def test_production_as_the_schema_owner_is_refused(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    receipt = world.execute(production=px.StaticProduction(world.owner_url))
    _refused(receipt, "privileges", "superuser")
    assert [s for s, _ in steps(receipt)][-1] == "privileges"
    assert_untouched(world, before)
    assert world.branch_dbs() == []


@pytest.mark.parametrize("grant, needle", [
    ("GRANT UPDATE (summary) ON robot TO {role}", "UPDATE on: robot"),
    ("GRANT DELETE ON specification TO {role}", "DELETE on: specification"),
    ("GRANT TRUNCATE ON region TO {role}", "TRUNCATE on: region"),
    ("REVOKE INSERT ON specification FROM {role}", "lacks INSERT on: specification"),
    ("REVOKE INSERT ON evidence_source FROM {role}", "lacks INSERT on: evidence_source"),
])
def test_destructive_or_missing_privileges_refuse(world, grant, needle):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    world.sql(grant.format(role=world.role))
    receipt = world.execute()
    _refused(receipt, "privileges", needle)
    assert_untouched(world, before)


def test_neon_superuser_membership_is_refused(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    created = not world.sql("SELECT 1 FROM pg_roles WHERE rolname = 'neon_superuser'")
    if created:
        world.sql("CREATE ROLE neon_superuser")
    try:
        world.sql(f"GRANT neon_superuser TO {world.role}")
        receipt = world.execute()
    finally:
        world.sql(f"REVOKE neon_superuser FROM {world.role}")
        if created:
            world.sql("DROP ROLE neon_superuser")
    _refused(receipt, "privileges", "member of neon_superuser")
    assert_untouched(world, before)


def test_owning_a_humanoid_table_is_refused(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    world.sql(f"ALTER TABLE region OWNER TO {world.role}")
    receipt = world.execute()
    _refused(receipt, "privileges", "owns: region")
    assert_untouched(world, before)


def test_receipt_records_the_privilege_result_and_routine_import_writes_only_additions(world):  # noqa: F811
    """The import runs AS the additions-only role: it would fail with 'permission denied' on any
    UPDATE or DELETE, so SUCCESS proves a ROUTINE scoped import is INSERT-only (specification)."""
    receipt = world.execute()
    assert receipt["outcome"] == "SUCCESS", receipt
    priv = receipt["privileges"]
    assert priv["ok"] is True and priv["user"] == world.role
    assert priv["superuser"] is False and priv["neon_superuser_member"] is False
    assert priv["owned"] == [] and priv["update"] == [] and priv["delete"] == []
    assert priv["truncate"] == [] and {"specification", "evidence_source"} <= set(
        priv["insert_tables"])
    assert world.spec_rows() == [(KEY, VALUE)]


# ----------------------------------------------- 4. strict public value + provenance ------


def _item(world):  # noqa: F811
    return copy.deepcopy(world.manifest["items"][0])


def test_api_surface_also_matches_observed_at_and_unit(world):  # noqa: F811
    manifest = world.manifest
    item = manifest["items"][0]

    class Web:
        def __init__(self, entry):
            self.entry = entry

        def get(self, url):
            if "/api/robots/" in url:
                return 200, json.dumps({"extended_specs": [self.entry]})
            return 200, compare_html(item) if "/compare" in url else page_html(item)

    good = {"key": KEY, "value": VALUE, "source_url": item["source_url"], "variant_slug": None,
            "observed_at": item["observed_at"]}
    api = px.check_public(manifest, Web(good), "http://a", "http://w")[0]
    assert api["ok"] is True
    for bad in ({**good, "observed_at": "2020-01-01"}, {**good, "observed_at": None}):
        assert px.check_public(manifest, Web(bad), "http://a", "http://w")[0]["ok"] is False
    with_unit = copy.deepcopy(manifest)
    with_unit["items"][0]["unit"] = "GHz"
    assert px.check_public(with_unit, Web(good), "http://a", "http://w")[0]["ok"] is False
    assert px.check_public(with_unit, Web({**good, "unit": "GHz"}), "http://a",
                           "http://w")[0]["ok"] is True


def test_page_requires_the_value_in_its_own_row_with_provenance_in_that_row(world):  # noqa: F811
    item = _item(world)
    label = px._label_for(item, None)
    assert label == "Onboard computer (synthetic)"
    ok, seen = px.check_page_row(page_html(item), item, label)
    assert ok and seen == {"source_link_visible": True, "source_label_visible": True}
    # the value is on the page (summary and elsewhere) but NOT in the labelled row: fail
    decoy, _ = px.check_page_row(page_html(item, decoy_only=True), item, label)
    assert decoy is False and px._collapse(item["proposed_value"]) in page_html(
        item, decoy_only=True)
    # the value is in the row but the row shows no provenance: fail
    bare, seen = px.check_page_row(page_html(item, provenance=False), item, label)
    assert bare is False and seen == {"source_link_visible": False,
                                      "source_label_visible": False}
    # a link to some other URL is not provenance
    other = page_html(item).replace(item["source_url"], "https://elsewhere.example/")
    other = other.replace(item["source_label"].replace("'", "&#x27;"), "something else")
    assert px.check_page_row(other, item, label)[0] is False
    # the value sits in a different label's row
    moved = page_html(item).replace(label, "Another field")
    assert px.check_page_row(moved, item, label)[0] is False


def test_page_row_label_must_match_exactly_unless_variant_scoped(world):  # noqa: F811
    item = _item(world)
    html_ = page_html(item).replace("Onboard computer (synthetic)",
                                    "Onboard computer (synthetic) extra")
    assert px.check_page_row(html_, item, "Onboard computer (synthetic)")[0] is False
    variant = {**item, "variant_slug": "pro"}
    pro = page_html(item).replace(
        '<span class="k">Onboard computer (synthetic)</span>',
        '<span class="k">Onboard computer (synthetic)<span class="ho-syslabel d-blk">'
        'Pro configuration</span></span>')
    assert px.check_page_row(pro, variant, "Onboard computer (synthetic)")[0] is True
    assert px.check_page_row(pro, item, "Onboard computer (synthetic)")[0] is False


def test_compare_requires_the_value_in_the_robots_cell_of_the_labelled_row(world):  # noqa: F811
    item = _item(world)
    label = px._label_for(item, None)
    assert px.check_compare_row(compare_html(item), item, label) is True
    assert px.check_compare_row(compare_html(item, decoy_only=True), item, label) is False
    peer_column = compare_html(item).replace(
        f'<td class="cell">{item["proposed_value"]}</td>'
        '<td class="cell"><span class="hatch">UNKNOWN</span></td>',
        f'<td class="cell"><span class="hatch">UNKNOWN</span></td>'
        f'<td class="cell">{item["proposed_value"]}</td>')
    assert px.check_compare_row(peer_column, item, label) is False      # it is the peer's value


def test_value_matching_by_type():
    assert px._value_matches("8 kg", 8.0, "kg") and px._value_matches("1,200", 1200, None)
    assert not px._value_matches("18 kg", 8, "kg") and not px._value_matches("8 lb", 8, "kg")
    assert px._value_matches("YES", True, None) and not px._value_matches("NO", True, None)
    assert px._value_matches("  8-core   CPU ", "8-core CPU", None)


def test_manifest_without_a_compare_peer_is_refused_before_any_write(
        world, compare_supported):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    unpeered = copy.deepcopy(world.manifest)
    unpeered["items"][0]["compare_peer"] = None
    unpeered.pop("digest")
    unpeered = pm.seal(unpeered)
    receipt = world.execute(unpeered)
    _refused(receipt, "manifest", "no published compare peer")
    assert steps(receipt) == [("manifest", "REFUSED")]
    assert_untouched(world, before)


def test_end_to_end_public_failure_when_value_only_elsewhere_on_the_page(world):  # noqa: F811
    manifest = world.manifest

    class Web(FakeWeb):
        def get(self, url):
            status, body = super().get(url)
            if "/robots/" in url and "/api/" not in url:
                body = page_html(manifest["items"][0], decoy_only=True)
            return status, body

    receipt = world.execute(web=Web(manifest, True), retries=2)
    assert receipt["outcome"] == "INCIDENT:public_verify", receipt
    failed = [r for r in receipt["public_verification"] if r["status"] == "FAILED"]
    assert [r["surface"] for r in failed] == ["page"]


# ------------------------------------------- 5. drift recheck + concurrent-write protection ------


def test_importer_calls_the_hook_before_writing_and_takes_no_lock_by_itself(world):  # noqa: F811
    """The shared importer is opt-in: it takes no advisory lock unless the hook does."""
    seen = {}

    def hook(cur):
        seen["lock"] = cur.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
            " AND granted").fetchone()[0]
        seen["specs"] = cur.execute("SELECT count(*) FROM specification s JOIN spec_definition d "
                                    "ON d.id = s.definition_id WHERE d.key = %s",
                                    (KEY,)).fetchone()[0]

    world.prepare()
    px._import(world.owner_url, [ROBOT], world.head, before_write=hook)
    assert seen == {"lock": 0, "specs": 0}            # no implicit lock; nothing written yet
    assert world.spec_rows() == [(KEY, VALUE)]


def test_promotion_apply_is_serialised_by_the_catalogue_write_lock(world, monkeypatch):  # noqa: F811
    """The executor's before_write hook takes `catalogue-write`: while another transaction
    holds it, the production import waits (an ungranted advisory lock is visible) and has
    written nothing; once released it proceeds."""
    import threading
    import time as _time

    world.prepare()
    real = px._import
    seen = {}

    def import_behind_a_held_lock(url, robots, catalogue_dir, **kw):
        if url != world.url:                       # the rehearsal copy is not under test
            return real(url, robots, catalogue_dir, **kw)
        holder = psycopg.connect(world.owner_url)
        holder.execute("SELECT pg_advisory_xact_lock(hashtext('catalogue-write'))")
        out = {}

        def run():
            try:
                out["summary"] = real(url, robots, catalogue_dir, **kw)
            except BaseException as exc:           # surfaced below, in the test thread
                out["error"] = exc

        thread = threading.Thread(target=run)
        thread.start()
        waiting, deadline = 0, _time.time() + 60
        while not waiting and _time.time() < deadline:
            waiting = holder.execute("SELECT count(*) FROM pg_locks WHERE locktype = "
                                     "'advisory' AND NOT granted").fetchone()[0]
            _time.sleep(0.2)
        seen["waiting"], seen["alive"] = waiting, thread.is_alive()
        seen["specs_while_blocked"] = world.spec_rows()
        holder.rollback()
        thread.join(timeout=120)
        holder.close()
        if "error" in out:
            raise out["error"]
        return out["summary"]

    monkeypatch.setattr(px, "_import", import_behind_a_held_lock)
    receipt = world.execute()
    assert seen == {"waiting": 1, "alive": True, "specs_while_blocked": []}, seen
    assert receipt["outcome"] == "SUCCESS", receipt
    assert world.spec_rows() == [(KEY, VALUE)]


def test_an_insert_only_role_imports_only_with_the_unchanged_row_probe(world):  # noqa: F811
    """INSERT ... ON CONFLICT DO UPDATE needs UPDATE even when nothing changes; the opt-in
    probe is what lets the additions-only role import a robot whose shared rows are current."""
    ic = pm.load_db_tool("import_catalogue")
    world.prepare()
    px._import(world.url, [ROBOT], world.head)               # probe on: succeeds
    ic.CATALOGUE_DIR, ic.ROBOTS_DIR = world.head, world.head / "robots"
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        ic.run(ic.normalize_url(world.url), only={ROBOT})     # default: UPDATE privilege needed
    assert world.spec_rows() == [(KEY, VALUE)]


def test_drift_between_the_check_and_the_apply_is_refused_and_nothing_is_written(
        world, monkeypatch):  # noqa: F811
    world.prepare()
    real = px._import

    def drift_just_before_apply(url, robots, catalogue_dir, **kw):
        if url == world.url:        # after the base_drift step, before the importer's writes
            world.sql("UPDATE robot SET summary = 'edited concurrently' WHERE slug = %s", (ROBOT,))
        return real(url, robots, catalogue_dir, **kw)

    monkeypatch.setattr(px, "_import", drift_just_before_apply)
    receipt = world.execute()
    _refused(receipt, "apply", "between the drift check and the write", ROBOT)
    assert ROBOT in receipt["fingerprint_drift"]
    assert world.spec_rows() == []                                   # the import wrote nothing
    assert world.sql("SELECT summary FROM robot WHERE slug = %s", (ROBOT,)) == [
        ("edited concurrently",)]
    assert world.branch_dbs() == []                                  # safety point not needed
    assert world.github.incidents == []


# ------------------------------------------------ 6. independent eligibility at execute ------


@pytest.mark.parametrize("case, sql, needle", [
    ("source_disabled", "UPDATE discovery_source SET is_enabled = false",
     "source not eligible"),
    ("claim_conflict", "UPDATE candidate_claim SET claim_status = 'CONFLICT'", "CONFLICT"),
    ("content_hash_differs",
     "UPDATE fetched_page SET content_hash = repeat('f', 64)", "content_hash changed"),
    ("claim_value_changed",
     "UPDATE candidate_claim SET claimed_value = 'something else entirely'",
     "claim_value changed"),
    ("candidate_unmatched",
     "UPDATE discovery_candidate SET identity_status = 'NEW_ENTITY'", "candidate identity"),
])
def test_eligibility_is_rederived_from_production_not_trusted_from_the_manifest(
        world, case, sql, needle):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    world.sql(sql)
    receipt = world.execute()
    _refused(receipt, "eligibility", needle)
    assert [s for s, _ in steps(receipt)][-1] == "eligibility"
    assert_untouched(world, before)
    assert world.branch_dbs() == []


def test_stale_observation_is_refused_at_execute(world):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    receipt = world.execute(utc_now=lambda: datetime(2026, 12, 31, tzinfo=UTC))
    _refused(receipt, "eligibility", "observation is")
    assert_untouched(world, before)


def test_a_claim_rejected_after_the_proposal_is_refused(world):  # noqa: F811
    world.prepare()
    pm.record_decision(world.head, world.manifest, "REJECT", "withdrawn", "Owner",
                       date(2026, 10, 19))
    receipt = world.execute()
    _refused(receipt, "eligibility", "REJECTED after the proposal")
    assert world.spec_rows() == []


# --------------------------------------------------------------- 7. neon branch origin ------


def _neon(monkeypatch, *, branch=None, endpoints=None, created_parent="br-prod",
          url="postgresql://u:p@ep-prod-1-pooler.eu.aws.neon.tech/neondb", calls=None):
    monkeypatch.setenv("NEON_API_KEY", "k")
    monkeypatch.setenv("NEON_PROJECT_ID", "proj-1")
    monkeypatch.setenv("NEON_PRODUCTION_BRANCH_ID", "br-prod")
    branch = branch or {"id": "br-prod", "name": "production", "default": True}
    endpoints = endpoints or [{"host": "ep-prod-1.eu.aws.neon.tech"}]

    def request(method, url_, headers, body=None, timeout=60.0):
        if calls is not None:
            calls.append((method, url_.split("/api/v2/projects/proj-1")[1]))
        if method == "POST":
            return {"branch": {"id": "br-1", "parent_id": created_parent, "parent_lsn": "0/9"},
                    "operations": [],
                    "connection_uris": [{"connection_uri": "postgresql://u:p@h/db"}]}
        if url_.endswith("/endpoints"):
            return {"endpoints": endpoints}
        if url_.endswith("/branches/br-prod"):
            return {"branch": branch}
        return {"operations": []}

    return adapters().NeonBranches(request=request, sleep=lambda s: None, production_url=url)


def test_neon_parent_is_verified_before_the_first_create_and_recorded(monkeypatch):
    calls = []
    branches = _neon(monkeypatch, calls=calls)
    assert branches.create("a") == "postgresql://u:p@h/db"
    branches.create("b")
    assert [c[0] for c in calls].count("POST") == 2
    first_post = [c[0] for c in calls].index("POST")
    assert ("GET", "/branches/br-prod") in calls[:first_post]
    assert ("GET", "/branches/br-prod/endpoints") in calls[:first_post]
    assert calls.count(("GET", "/branches/br-prod")) == 1            # verified once, not per create
    assert branches.origins["a"] == {"branch_id": "br-1", "parent_id": "br-prod",
                                     "parent_lsn": "0/9"}


@pytest.mark.parametrize("kwargs, needle", [
    ({"branch": {"id": "br-prod", "name": "production", "default": False}}, "default branch"),
    ({"branch": {"id": "br-prod", "name": "staging", "default": True}}, "named 'staging'"),
    ({"branch": {"id": "br-other", "name": "production", "default": True}}, "does not exist"),
    ({"endpoints": [{"host": "ep-someone-else.eu.aws.neon.tech"}]}, "endpoint host"),
    ({"created_parent": "br-dev"}, "not from production"),
])
def test_neon_refuses_any_origin_mismatch(monkeypatch, kwargs, needle):
    branches = _neon(monkeypatch, **kwargs)
    with pytest.raises(Exception) as caught:
        branches.create("a")
    assert needle in str(caught.value) and caught.value.safe is True


def test_neon_requires_the_production_branch_id_and_allows_a_name_override(monkeypatch):
    monkeypatch.setenv("NEON_API_KEY", "k")
    monkeypatch.setenv("NEON_PROJECT_ID", "p")
    monkeypatch.delenv("NEON_PRODUCTION_BRANCH_ID", raising=False)
    with pytest.raises(RuntimeError, match="NEON_PRODUCTION_BRANCH_ID"):
        adapters().NeonBranches()
    monkeypatch.setenv("NEON_PRODUCTION_BRANCH_NAME", "main")
    branches = _neon(monkeypatch, branch={"id": "br-prod", "name": "main", "default": True})
    assert branches._parent_name == "main"
    assert branches.verify_origin()["parent_name"] == "main"


def test_executor_refuses_when_the_branch_origin_is_not_production(world, monkeypatch):  # noqa: F811
    world.prepare()
    before = world.fingerprints()
    wrong = px.LocalBranches(world.admin, "some_other_database")
    receipt = world.execute(branches=wrong)
    _refused(receipt, "safety_branch", "not the production database")
    assert_untouched(world, before)
    # a Neon-style failure carries its safe message into the receipt, a secret never
    branches = _neon(monkeypatch, created_parent="br-dev")
    receipt = world.execute(branches=_ExclusiveOff(branches))
    _refused(receipt, "safety_branch", "not from production")
    assert "u:p@" not in json.dumps(receipt)


class _ExclusiveOff:
    """A NeonBranches whose production URL check is skipped (the URL belongs to the test DB)."""

    requires_exclusive_source = False

    def __init__(self, inner):
        self.inner, self.origins = inner, inner.origins

    def verify_origin(self, production_url):
        return {"parent_id": "br-prod"}

    def create(self, name):
        return self.inner.create(name)

    def delete(self, name):
        pass


def test_rehearsal_branch_origin_mismatch_is_refused_as_rehearsal(world):  # noqa: F811
    world.prepare()

    class SecondIsWrong(px.LocalBranches):
        def create(self, name):
            if name.startswith("rehearse"):
                raise px.BranchOriginError("branch was created from 'br-dev', not from production")
            return super().create(name)

    receipt = world.execute(branches=SecondIsWrong(world.admin, world.name))
    _refused(receipt, "rehearsal", "not from production")
    assert world.spec_rows() == [] and world.branch_dbs() == []


def test_receipt_records_branch_origins(world):  # noqa: F811
    receipt = world.execute()
    assert receipt["outcome"] == "SUCCESS", receipt
    b = receipt["branches"]
    assert b["production_origin"] == {"template_db": world.name, "production_db": world.name}
    assert b["safety_origin"]["template_db"] == world.name
    assert b["rehearsal_origin"]["template_db"] == world.name


# ------------------------------------------------------- compare applicability (owner B) ------


def test_compare_supported_fields_are_pinned_to_the_real_compare_field_list():
    """Single source of truth: reads.COMPARE_FIELDS (what /api/compare serves). Pinned to a
    literal and to the web's metric policy so a change cannot silently drift."""
    import pathlib

    from app.services import reads

    literal = {
        "commercial_status", "height_cm", "weight_kg", "payload_kg", "walk_speed_ms",
        "runtime_minutes", "mobility", "hand_type", "hand_dof", "has_manipulation", "autonomy",
        "has_teleoperation", "has_vision", "has_language_ui", "has_sdk", "ros_support",
        "developer_edition"}
    assert px.compare_supported_fields() == literal == {a for _g, a, _l in reads.COMPARE_FIELDS}
    policy = (pathlib.Path(__file__).resolve().parents[2] / "web" / "lib"
              / "comparison-policy.ts").read_text(encoding="utf-8")
    in_policy = {k for k in literal if re.search(rf"^\s*{k}:\s*\{{", policy, re.M)}
    assert {"commercial_status", "height_cm", "weight_kg", "payload_kg", "walk_speed_ms",
            "runtime_minutes", "mobility", "hand_type", "hand_dof", "has_manipulation",
            "autonomy", "has_vision"} <= in_policy       # the web keys rows by these same names
    assert px.compare_applicability({"definition": KEY})[0] == "NOT_APPLICABLE"
    assert px.compare_applicability({"definition": "payload_kg"}) == ("SUPPORTED", None)


class _Web:
    """Serves api + page + compare for one item; a False flag renders that surface without
    the committed value."""

    def __init__(self, item, *, api=True, page=True, compare=True):
        self.item, self.api, self.page, self.compare = item, api, page, compare
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        item = self.item
        if "/api/robots/" in url:
            specs = [{"key": KEY, "value": VALUE if self.api else "other",
                      "unit": item.get("unit"), "source_url": item["source_url"],
                      "variant_slug": item.get("variant_slug"),
                      "observed_at": item["observed_at"]}]
            return 200, json.dumps({"extended_specs": specs})
        if "/compare" in url:
            return 200, compare_html(item, decoy_only=not self.compare)
        return 200, page_html(item, decoy_only=not self.page)


def test_supported_compare_field_passes(world, compare_supported):  # noqa: F811
    item = world.manifest["items"][0]
    results = px.check_public(world.manifest, _Web(item), "http://a", "http://w")
    assert {(r["surface"], r["applicability"], r["status"]) for r in results} == {
        ("api", "SUPPORTED", "PASS"), ("page", "SUPPORTED", "PASS"),
        ("compare", "SUPPORTED", "PASS")}
    assert px.public_ok(results) and px.public_summary(results)["compare"] == "PASS"


def test_unsupported_extended_spec_is_not_applicable_never_a_compare_success(world):  # noqa: F811
    item = world.manifest["items"][0]
    web = _Web(item)
    results = px.check_public(world.manifest, web, "http://a", "http://w")
    compare = [r for r in results if r["surface"] == "compare"][0]
    assert compare["applicability"] == compare["status"] == "NOT_APPLICABLE"
    assert compare["ok"] is False and compare["url"] is None
    assert "extended spec" in compare["note"] and KEY in compare["note"]
    assert not any("/compare" in u for u in web.urls)            # nothing was fetched
    assert px.public_ok(results)                                  # API + page pass => success
    assert px.public_summary(results) == {"api": "PASS", "page": "PASS",
                                          "compare": "NOT_APPLICABLE"}
    # and no peer is needed for it
    unpeered = copy.deepcopy(world.manifest)
    unpeered["items"][0]["compare_peer"] = None
    assert [r for r in px.check_public(unpeered, _Web(item), "http://a", "http://w")
            if r["surface"] == "compare"][0]["status"] == "NOT_APPLICABLE"


def test_supported_compare_field_that_fails_is_failed_and_an_incident(world, compare_supported):  # noqa: F811
    item = world.manifest["items"][0]
    results = px.check_public(world.manifest, _Web(item, compare=False), "http://a", "http://w")
    compare = [r for r in results if r["surface"] == "compare"][0]
    assert compare["status"] == "FAILED" and compare["ok"] is False
    assert not px.public_ok(results)
    receipt = world.execute(web=_Web(item, compare=False), retries=2, sleep=lambda s: None)
    assert receipt["outcome"] == "INCIDENT:public_verify", receipt
    assert receipt["public_summary"]["compare"] == "FAILED"


def test_api_or_page_failure_fails_even_when_compare_is_not_applicable(world):  # noqa: F811
    item = world.manifest["items"][0]
    for kw, surface in (({"api": False}, "api"), ({"page": False}, "page")):
        results = px.check_public(world.manifest, _Web(item, **kw), "http://a", "http://w")
        assert [r["surface"] for r in results if r["status"] == "FAILED"] == [surface]
        assert not px.public_ok(results)
    receipt = world.execute(web=_Web(item, page=False), retries=2, sleep=lambda s: None)
    assert receipt["outcome"] == "INCIDENT:public_verify", receipt
    assert receipt["public_summary"] == {"api": "PASS", "page": "FAILED",
                                         "compare": "NOT_APPLICABLE"}
