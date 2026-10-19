"""Catalogue promotion execution (PR B): the fail-closed sequence of design section 4.

SYNTHETIC data only (see promotion_support.py). `LocalBranches` (CREATE DATABASE ... TEMPLATE)
stands in for Neon; GitHub and the public web are recording fakes. Each test starts from its own
writable "production" copy.
"""
from __future__ import annotations

import copy
import json

import psycopg
import pytest
from promotion_support import KEY, ROBOT, VALUE, FakeWeb, template_db, world  # noqa: F401

from app.cli import promotion as cli
from app.services.discovery import promotion_execute as px
from app.services.discovery import promotion_manifest as pm


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
        "manifest", "halt_switch", "concurrency", "already_applied", "base_drift",
        "safety_branch", "rehearsal", "apply", "post_verify", "public_verify"]
    assert receipt["digest"] == manifest["digest"] and receipt["robots"] == [ROBOT]
    assert receipt["fields"] == [f"{ROBOT}:{KEY}"] and receipt["commit"] == "c0ffee"
    assert receipt["rehearsal"]["identity_added"] == [f"specification {ROBOT}:-|{KEY}"]
    assert receipt["post_verify"]["publication_and_status_unchanged"] is True
    assert receipt["after_fingerprints"] != manifest["base"]["robot_fingerprints"]
    assert all(r["ok"] for r in receipt["public_verification"])
    assert {r["surface"] for r in receipt["public_verification"]} == {"api", "page", "compare"}
    # the safety branch is retained, the rehearsal branch is gone
    assert len(world.branch_dbs()) == 1 and world.branch_dbs()[0].startswith("promo_")
    assert receipt["branches"]["rehearsal_deleted"] is True
    assert len(world.github.comments) == 1 and world.github.incidents == []
    assert "humanoid:humanoid" not in json.dumps(receipt)       # no connection string
    assert "CATALOGUE_DATABASE_URL" not in json.dumps(receipt)


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
        "manifest", "halt_switch", "concurrency", "already_applied"]
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

    def refuse_on_production(url, robots, catalogue_dir):
        if url == world.url:
            raise SystemExit("IMPORT REFUSED - nothing was written")
        return real(url, robots, catalogue_dir)

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

    def write_then_crash(url, robots, catalogue_dir):
        real(url, robots, catalogue_dir)
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


def test_public_check_requires_value_and_source_on_the_api(world):  # noqa: F811
    manifest = world.manifest

    class Web:
        def __init__(self, entry):
            self.entry = entry

        def get(self, url):
            if "/api/robots/" in url:
                return 200, json.dumps({"extended_specs": [self.entry]})
            return 200, f"<p>{VALUE}</p>"

    good = {"key": KEY, "value": VALUE, "source_url": manifest["items"][0]["source_url"],
            "variant_slug": None}
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
    calls = []

    def request(method, url, headers, body=None, timeout=60.0):
        calls.append((method, url.split("/api/v2")[1], body))
        assert headers["Authorization"] == "Bearer key-should-not-leak"
        if method == "POST":
            return {"branch": {"id": "br-1"}, "operations": [{"id": "op-1"}],
                    "endpoints": [{"id": "ep-1"}],
                    "connection_uris": [{"connection_uri": "postgresql://u:p@h/db"}]}
        if "/operations/" in url:
            return {"operation": {"status": "finished"}}
        return {"operations": []}

    branches = adapters().NeonBranches(request=request, sleep=lambda s: None)
    assert branches.create("promo-x") == "postgresql://u:p@h/db"
    branches.delete("promo-x")
    assert calls[0] == ("POST", "/projects/proj-1/branches",
                        {"branch": {"name": "promo-x"}, "endpoints": [{"type": "read_write"}]})
    assert calls[-1][:2] == ("DELETE", "/projects/proj-1/branches/br-1")
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
                   "--database-url", world.url, "--no-github"])
    assert rc == 2 and "not at --commit" in capsys.readouterr().err
    assert world.spec_rows() == []


def test_derived_preflight_manifest_matches_the_items(world):  # noqa: F811
    derived = pm.derive_preflight_manifest(world.manifest)
    assert derived["expected"] == [{"table": "specification", "kind": "ADDED",
                                    "match": {"robot": ROBOT, "definition": KEY}, "count": 1}]


# ------------------------------------------------------------------------- workflows ------


def _workflow(name):
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_promotion_workflow_is_inert_unless_enabled_and_single_flight():
    wf = _workflow("catalogue-promotion.yml")
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
