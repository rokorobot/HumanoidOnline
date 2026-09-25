"""Contract/regression tests: exact identity, false greens, retries and read-only I/O."""

import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError, URLError

import deployment_watcher as w

SHA = "a" * 40
OLD = "b" * 40
ENV = {
    "WATCHER_NETLIFY_TOKEN": "netlify-secret",
    "WATCHER_NETLIFY_SITE_ID": "site-1",
    "WATCHER_VERCEL_TOKEN": "vercel-secret",
    "WATCHER_VERCEL_API_PROJECT_ID": "prj_api",
    "WATCHER_VERCEL_API_ALIAS": "api.example.com",
    "WATCHER_VERCEL_WEB_PROJECT_ID": "prj_web",
    "WATCHER_VERCEL_WEB_ALIAS": "web.example.com",
    "WATCHER_API_ORIGIN": "https://api.example.com",
    "WATCHER_WEB_ORIGIN": "https://humanoidonline.com",
}
ENV_PROVIDERS = dict(ENV, WATCHER_PROVIDER_CHECKS="netlify,vercel-api,vercel-web")
CLOSED = ("https://api.example.com/api/discovery-review", "https://humanoidonline.com/discovery-review")
RUN = {
    "id": 12,
    "head_sha": SHA,
    "path": ".github/workflows/ci.yml",
    "repository": {"full_name": w.REPO},
    "status": "completed",
    "conclusion": "success",
    "run_attempt": 2,
    "event": "push",
    "head_branch": "main",
}
JOBS_URL = f"{w.GH}/actions/runs/12/attempts/2/jobs?per_page=100&page=1"
SITE_URL = "https://api.netlify.com/api/v1/sites/site-1"


class FakeReader:
    def __init__(self):
        self.calls = []
        self.data = {
            f"{w.GH}/actions/runs/12": copy.deepcopy(RUN),
            JOBS_URL: {"jobs": [{"name": "Backend", "conclusion": "success", "steps": []}]},
            f"{w.GH}/git/ref/heads/main": {"object": {"sha": SHA}},
            SITE_URL: {
                "id": "site-1",
                "name": "humanoidonline",
                "ssl_url": "https://humanoidonline.com",
                "published_deploy": {
                    "id": "deploy-1",
                    "commit_ref": SHA,
                    "context": "production",
                    "state": "ready",
                },
            },
            "https://api.example.com/health": {"status": "ok"},
            "https://api.example.com/ready": {"status": "ok", "database": "up"},
        }
        for role in ("api", "web"):
            self.data[f"https://api.vercel.com/v4/aliases/{role}.example.com?"] = {
                "alias": f"{role}.example.com",
                "projectId": "prj_" + role,
                "deploymentId": "dpl_" + role,
            }
            self.data[f"https://api.vercel.com/v13/deployments/dpl_{role}?withGitRepoInfo=true"] = {
                "id": "dpl_" + role,
                "target": "production",
                "readyState": "READY",
                "gitSource": {"sha": SHA},
            }
        for path in ("/", "/robots", "/manufacturers", "/find-a-humanoid"):
            self.data["https://humanoidonline.com" + path] = (
                "<html>HumanoidOnline</html>",
                "text/html; charset=utf-8",
            )
        self.statuses = {url: 404 for url in CLOSED}

    def status(self, url):
        self.calls.append(url)
        return self.statuses[url]

    def get(self, url, *, as_json=True):
        self.calls.append(url)
        result = self.data[url]
        if isinstance(result, Exception):
            raise result
        if callable(result):
            return result()
        return copy.deepcopy(result)


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.reader = FakeReader()

    def snapshot(self, env=None):
        return w.snapshot(self.reader, ENV if env is None else env, "12", SHA)

    def test_default_production_pass_needs_no_provider_and_says_identity_unverified(self):
        scope, checks = self.snapshot()
        self.assertEqual(scope, "production health — deployment identity not verified")
        self.assertEqual(w.outcome(checks), "PASS")
        self.assertEqual(len([c for c in checks if c["state"] == "NOT_APPLICABLE"]), 3)
        # 6 health/route probes + 2 closed-surface probes.
        self.assertEqual(len([c for c in checks if c["name"].startswith("https://")]), 8)
        self.assertFalse(any("api.netlify.com" in u or "api.vercel.com" in u
                             for u in self.reader.calls))

    def test_production_pass_with_all_provider_checks_enabled(self):
        scope, checks = self.snapshot(ENV_PROVIDERS)
        self.assertIn("provider deployment identity (netlify, vercel-api, vercel-web)", scope)
        self.assertEqual(w.outcome(checks), "PASS")
        self.assertNotIn("NOT_APPLICABLE", {c["state"] for c in checks})
        self.assertEqual(self.reader.calls.count(SITE_URL), 2)

    def test_enabled_provider_missing_config_is_unverified_disabled_is_neutral(self):
        env = {
            "WATCHER_API_ORIGIN": "https://api.example.com",
            "WATCHER_PROVIDER_CHECKS": "netlify",
        }
        _, checks = self.snapshot(env)
        states = {c["name"]: c["state"] for c in checks}
        self.assertEqual(states["Netlify production"], "UNVERIFIED")
        self.assertEqual(states["Vercel api production"], "NOT_APPLICABLE")
        self.assertEqual(w.outcome(checks), "UNVERIFIED")

    def test_unknown_provider_name_is_unverified(self):
        _, checks = self.snapshot(dict(ENV, WATCHER_PROVIDER_CHECKS="netlify,heroku"))
        self.assertEqual(w.outcome(checks), "UNVERIFIED")
        self.assertIn("heroku", checks[-1]["detail"])

    def test_pr_scope_is_informational_and_never_uses_provider_credentials(self):
        self.reader.data[f"{w.GH}/actions/runs/12"]["event"] = "pull_request"
        scope, checks = self.snapshot(ENV_PROVIDERS)
        self.assertEqual(scope, w.PR_SCOPE)
        self.assertEqual(w.outcome(checks), "PASS")
        self.assertEqual(checks[-1]["state"], "NOT_CHECKED")
        self.assertTrue(all(url.startswith(w.GH) for url in self.reader.calls))

    def test_exit_codes_pr_informational_production_enforced(self):
        for enforced, result, code in (
            (False, "FAIL", 0),
            (False, "UNVERIFIED", 0),
            (False, "TIMEOUT", 0),
            (True, "PASS", 0),
            (True, "SUPERSEDED", 0),
            (True, "FAIL", 1),
            (True, "UNVERIFIED", 1),
            (True, "TIMEOUT", 1),
        ):
            with self.subTest(enforced=enforced, result=result):
                self.assertEqual(w.exit_code({"enforced": enforced, "result": result}), code)

    def test_failed_pr_ci_is_reported_but_not_enforced(self):
        self.reader.data[f"{w.GH}/actions/runs/12"].update(
            event="pull_request", conclusion="failure"
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = w.watch(
                self.reader, ENV, "12", SHA, 60, 30, Path(tmp), clock=lambda: 0, sleep=Mock()
            )
        self.assertEqual(report["result"], "FAIL")
        self.assertFalse(report["enforced"])
        self.assertEqual(w.exit_code(report), 0)

    def test_closed_surfaces_must_be_404_and_200_is_a_hard_fail(self):
        for code, state in ((404, "PASS"), (200, "FAIL"), (204, "FAIL"), (503, "PENDING")):
            with self.subTest(code=code):
                self.reader = FakeReader()
                self.reader.statuses[CLOSED[1]] = code
                _, checks = self.snapshot()
                self.assertEqual({c["name"]: c["state"] for c in checks}[CLOSED[1]], state)
                if state == "FAIL":
                    self.assertEqual(w.outcome(checks), "FAIL")

    def test_missing_api_origin_is_unverified(self):
        env = dict(ENV)
        del env["WATCHER_API_ORIGIN"]
        _, checks = self.snapshot(env)
        self.assertEqual(w.outcome(checks), "UNVERIFIED")
        self.assertIn("WATCHER_API_ORIGIN", checks[-2]["detail"])

    def test_alias_coupling_applies_only_when_vercel_api_enabled(self):
        env = dict(ENV, WATCHER_VERCEL_API_ALIAS="unrelated.example.com")
        _, checks = self.snapshot(env)
        self.assertEqual(w.outcome(checks), "PASS")

    def test_post_cleanup_failure_is_failure_even_when_tests_passed(self):
        run = self.reader.data[f"{w.GH}/actions/runs/12"]
        run["conclusion"] = "failure"
        self.reader.data[JOBS_URL]["jobs"] = [
            {
                "name": "Frontend",
                "conclusion": "failure",
                "steps": [
                    {"name": "Tests", "conclusion": "success"},
                    {"name": "Post Run astral-sh/setup-uv@v5", "conclusion": "failure"},
                ],
            }
        ]
        _, checks = self.snapshot()
        self.assertEqual(w.outcome(checks), "FAIL")
        self.assertIn("Post Run astral-sh/setup-uv", checks[0]["detail"])

    def test_wrong_sha_workflow_or_repository_cannot_pass(self):
        for field, value in (
            ("head_sha", OLD),
            ("path", ".github/workflows/other.yml"),
            ("repository", {"full_name": "someone/else"}),
        ):
            with self.subTest(field=field):
                run = copy.deepcopy(RUN)
                run[field] = value
                self.assertEqual(w.ci_observation(self.reader, run, SHA)["state"], "UNVERIFIED")

    def test_ci_cancellation_and_empty_job_evidence(self):
        run = dict(RUN, conclusion="cancelled")
        self.assertEqual(w.ci_observation(self.reader, run, SHA)["state"], "FAIL")
        self.reader.data[JOBS_URL]["jobs"] = []
        self.assertEqual(w.ci_observation(self.reader, RUN, SHA)["state"], "UNVERIFIED")

    def test_missing_configuration_never_passes(self):
        _, checks = self.snapshot({"WATCHER_PROVIDER_CHECKS": "netlify,vercel-api,vercel-web"})
        self.assertEqual(w.outcome(checks), "UNVERIFIED")
        self.assertEqual(len([c for c in checks if c["state"] == "UNVERIFIED"]), 3)

    def test_old_netlify_commit_does_not_pass_because_site_is_healthy(self):
        self.reader.data[SITE_URL]["published_deploy"]["commit_ref"] = OLD
        _, checks = self.snapshot(ENV_PROVIDERS)
        self.assertEqual(w.outcome(checks), "PENDING")
        self.assertEqual(w.outcome(checks, expired=True), "TIMEOUT")
        self.assertFalse(
            any(url.startswith("https://humanoidonline.com") for url in self.reader.calls)
        )

    def test_netlify_wrong_site_or_origin_is_unverified(self):
        for field, value in (("id", "wrong"), ("ssl_url", "https://other.example.com")):
            with self.subTest(field=field):
                self.reader = FakeReader()
                self.reader.data[SITE_URL][field] = value
                self.assertEqual(
                    w.netlify_observation(self.reader, ENV, SHA)["state"], "UNVERIFIED"
                )

    def test_netlify_unknown_sha_and_preview_are_unverified(self):
        deploy = self.reader.data[SITE_URL]["published_deploy"]
        for key, value in (("commit_ref", None), ("context", "deploy-preview")):
            original = deploy[key]
            deploy[key] = value
            self.assertEqual(w.netlify_observation(self.reader, ENV, SHA)["state"], "UNVERIFIED")
            deploy[key] = original

    def test_vercel_project_mismatch_redirect_and_missing_pointer(self):
        url = "https://api.vercel.com/v4/aliases/api.example.com?"
        for field, value, state in (
            ("projectId", "wrong", "UNVERIFIED"),
            ("redirect", "https://other.com", "UNVERIFIED"),
            ("deploymentId", None, "PENDING"),
        ):
            with self.subTest(field=field):
                self.reader = FakeReader()
                self.reader.data[url][field] = value
                self.assertEqual(w.vercel_observation(self.reader, ENV, SHA, "API")["state"], state)

    def test_vercel_exact_sha_and_production_target_required(self):
        url = "https://api.vercel.com/v13/deployments/dpl_api?withGitRepoInfo=true"
        for field, value, state in (
            ("gitSource", {"sha": OLD}, "PENDING"),
            ("gitSource", {}, "UNVERIFIED"),
            ("target", "preview", "UNVERIFIED"),
            ("readyState", "ERROR", "FAIL"),
            ("readyState", "BUILDING", "PENDING"),
        ):
            with self.subTest(field=field):
                self.reader = FakeReader()
                self.reader.data[url][field] = value
                self.assertEqual(w.vercel_observation(self.reader, ENV, SHA, "API")["state"], state)

    def test_vercel_conflicting_metadata_fails_closed(self):
        url = "https://api.vercel.com/v13/deployments/dpl_api?withGitRepoInfo=true"
        self.reader.data[url]["meta"] = {"githubCommitSha": OLD}
        self.assertEqual(w.vercel_observation(self.reader, ENV, SHA, "API")["state"], "UNVERIFIED")

    def test_api_probe_must_use_verified_alias(self):
        env = dict(ENV, WATCHER_API_ORIGIN="https://unrelated.example.com")
        self.assertEqual(w.vercel_observation(self.reader, env, SHA, "API")["state"], "UNVERIFIED")

    def test_advanced_main_is_superseded_before_probes(self):
        self.reader.data[f"{w.GH}/git/ref/heads/main"]["object"]["sha"] = OLD
        _, checks = self.snapshot(ENV_PROVIDERS)
        self.assertEqual(w.outcome(checks), "SUPERSEDED")
        self.assertNotIn(SITE_URL, self.reader.calls)
        self.assertFalse(any(u.startswith("https://humanoidonline.com") for u in self.reader.calls))

    def test_main_advances_during_health_cannot_pass(self):
        values = iter(({"object": {"sha": SHA}}, {"object": {"sha": OLD}}))
        self.reader.data[f"{w.GH}/git/ref/heads/main"] = lambda: next(values)
        _, checks = self.snapshot()
        self.assertEqual(w.outcome(checks), "SUPERSEDED")

    def test_alias_changes_during_health_cannot_pass(self):
        site = copy.deepcopy(self.reader.data[SITE_URL])
        changed = copy.deepcopy(site)
        changed["published_deploy"]["commit_ref"] = OLD
        values = iter((site, changed))
        self.reader.data[SITE_URL] = lambda: next(values)
        _, checks = self.snapshot(ENV_PROVIDERS)
        self.assertEqual(w.outcome(checks), "PENDING")

    def test_readiness_payload_and_html_are_checked(self):
        self.reader.data["https://api.example.com/ready"] = {"status": "ok", "database": "down"}
        self.reader.data["https://humanoidonline.com/robots"] = ("login", "text/html")
        checks = w.health_observations(self.reader, ENV)
        self.assertEqual(len([c for c in checks if c["state"] == "PENDING"]), 2)

    def test_job_pagination_uses_latest_attempt_and_includes_late_failure(self):
        self.reader.data[JOBS_URL]["jobs"] = [{"name": "ok", "conclusion": "success"}] * 100
        self.reader.data[JOBS_URL.replace("&page=1", "&page=2")] = {
            "jobs": [{"name": "late", "conclusion": "failure"}]
        }
        result = w.ci_observation(self.reader, RUN, SHA)
        self.assertEqual(result["state"], "FAIL")
        self.assertIn("late", result["detail"])

    def test_polling_converges_and_writes_reports(self):
        clock = Mock(side_effect=[0, 0, 30])
        sleep = Mock()
        pending = [w.row("deploy", "PENDING", "waiting")]
        passed = [w.row("deploy", "PASS", "ready")]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(
                w, "snapshot", side_effect=[("production", pending), ("production", passed)]
            ),
        ):
            result = w.watch(
                self.reader, ENV, "12", SHA, 60, 30, Path(tmp), clock=clock, sleep=sleep
            )
            self.assertEqual(result["result"], "PASS")
            self.assertEqual(json.loads((Path(tmp) / "report.json").read_text())["sha"], SHA)
            self.assertIn("production", (Path(tmp) / "report.md").read_text())
            sleep.assert_called_once_with(30)

    def test_deadline_writes_timeout_with_pending_evidence(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(
                w,
                "snapshot",
                return_value=("production", [w.row("deploy", "PENDING", "old commit")]),
            ),
        ):
            result = w.watch(
                self.reader, ENV, "12", SHA, 60, 30, Path(tmp), clock=lambda: 60, sleep=Mock()
            )
            self.assertEqual(result["result"], "TIMEOUT")
            self.assertEqual(result["checks"][0]["state"], "PENDING")

    def test_malformed_provider_response_writes_unverified_report(self):
        self.reader.data[SITE_URL] = []
        _, checks = self.snapshot(ENV_PROVIDERS)
        self.assertEqual(w.outcome(checks), "UNVERIFIED")

    def test_markdown_escapes_untrusted_step_names(self):
        report = {
            "result": "FAIL",
            "scope": "CI",
            "enforced": True,
            "sha": SHA,
            "run_id": "12",
            "observed_at": "now",
            "checks": [w.row("<script>|x", "FAIL", "bad\nrow")],
        }
        md = w.markdown(report)
        self.assertNotIn("<script>", md)
        self.assertIn("&#124;", md)


class TransportTests(unittest.TestCase):
    def reader(self):
        reader = w.Reader(dict(ENV, GITHUB_TOKEN="github-secret"), time.monotonic() + 60)
        reader.opener = MagicMock()
        response = Mock(status=200, headers={"Content-Type": "application/json"})
        response.read.return_value = b'{"status":"ok"}'
        reader.opener.open.return_value.__enter__.return_value = response
        return reader

    def test_get_only_and_tokens_never_sent_to_live_site(self):
        reader = self.reader()
        for url, expected in (
            (w.GH, "Bearer github-secret"),
            ("https://api.vercel.com/v4/aliases/x", "Bearer vercel-secret"),
            ("https://humanoidonline.com/", None),
        ):
            reader.get(url)
            req = reader.opener.open.call_args.args[0]
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(req.get_header("Authorization"), expected)
            self.assertIsNone(req.data)

    def test_provider_errors_do_not_expose_bodies_or_tokens(self):
        for code, state in (
            (401, "UNVERIFIED"),
            (403, "UNVERIFIED"),
            (429, "PENDING"),
            (503, "PENDING"),
            (302, "PENDING"),
        ):
            reader = self.reader()
            reader.opener.open.side_effect = HTTPError(
                w.GH, code, "secret", {}, io.BytesIO(b"github-secret")
            )
            with self.assertRaises(w.ObservationError) as exc:
                reader.get(w.GH)
            self.assertEqual(exc.exception.state, state)
            self.assertNotIn("secret", str(exc.exception))

    def test_network_failure_retry_and_no_redirect_following(self):
        reader = self.reader()
        reader.opener.open.side_effect = URLError("secret")
        with self.assertRaises(w.ObservationError) as exc:
            reader.get(w.GH)
        self.assertEqual(exc.exception.state, "PENDING")
        self.assertIsNone(
            w.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")
        )

    def test_response_size_and_json_and_status_are_checked(self):
        for body, status, state in (
            (b"x" * (w.MAX_BODY + 1), 200, "UNVERIFIED"),
            (b"not json", 200, "UNVERIFIED"),
            (b"{}", 204, "PENDING"),
        ):
            reader = self.reader()
            response = reader.opener.open.return_value.__enter__.return_value
            response.read.return_value, response.status = body, status
            with self.assertRaises(w.ObservationError) as exc:
                reader.get(w.GH)
            self.assertEqual(exc.exception.state, state)

    def test_status_probe_returns_code_without_token_or_body(self):
        reader = self.reader()
        reader.opener.open.side_effect = HTTPError(
            "https://humanoidonline.com/discovery-review", 404, "nf", {}, io.BytesIO(b"x")
        )
        self.assertEqual(reader.status("https://humanoidonline.com/discovery-review"), 404)
        req = reader.opener.open.call_args.args[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.get_header("Authorization"))
        reader.opener.open.side_effect = None
        self.assertEqual(reader.status("https://humanoidonline.com/discovery-review"), 200)
        reader.opener.open.side_effect = URLError("down")
        with self.assertRaises(w.ObservationError) as exc:
            reader.status("https://humanoidonline.com/discovery-review")
        self.assertEqual(exc.exception.state, "PENDING")

    def test_origin_rejects_credentials_paths_and_insecure_scheme(self):
        for value in (
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com/path",
            "https://example.com?token=x",
        ):
            with self.subTest(value=value), self.assertRaises(w.ObservationError):
                w.origin(value)


if __name__ == "__main__":
    unittest.main()
