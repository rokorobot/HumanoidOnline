"""G5-4: HUMAN REVIEW summary, workflow exit semantics and the deduplicated review-queue issue."""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from app.services.discovery import human_review as hr

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "discovery_review_queue.py"
WORKFLOW = ROOT / ".github" / "workflows" / "discovery-observe.yml"
_spec = importlib.util.spec_from_file_location("discovery_review_queue", SCRIPT)
rq = importlib.util.module_from_spec(_spec)
sys.modules["discovery_review_queue"] = rq
_spec.loader.exec_module(rq)

RUN = "https://github.com/o/r/actions/runs/1"


def summary(p=("a", "b"), i=(), s=(), new_p=0, new_i=0):
    return hr.summarize(p, i, s, new_p, new_i)


def report(h):
    return {"human_review": h}


def issue(h, number=7, state="OPEN"):
    return {"number": number, "state": state, "title": rq.TITLE, "body": rq.render_body(h, RUN)}


# ------------------------------------------------------------------ digest and summary


def test_the_digest_is_deterministic_and_order_independent():
    a = summary(("p2", "p1"), ("c:1",), ("robot|https://x",))
    b = summary(("p1", "p2"), ("c:1",), ("robot|https://x",))
    assert a["queue_digest"] == b["queue_digest"] and len(a["queue_digest"]) == 64
    assert summary(("p1",))["queue_digest"] != summary(("p1", "p2"))["queue_digest"]


def test_the_digest_ignores_the_new_this_cycle_marker():
    one = summary(("p1",), new_p=1)["queue_digest"]
    assert one == summary(("p1",), new_p=0)["queue_digest"]


def test_source_review_participates_in_the_queue():
    s = summary((), (), ("fourier|https://www.fftai.com/",))
    assert s["source_review_items"] == 1 and s["total"] == 1
    assert s["queue_digest"] != summary((), (), ())["queue_digest"]


def test_new_work_is_distinguished_from_the_standing_queue():
    s = summary(("p1", "p2", "p3"), ("c:1",), (), new_p=1, new_i=0)
    assert s["new_this_cycle"]["total"] == 1 and s["standing_queue"] == 3
    quiet = summary(("p1", "p2"), new_p=0)
    assert quiet["new_this_cycle"]["total"] == 0 and quiet["standing_queue"] == 2


def test_the_human_review_lines_show_counts_digest_and_new_vs_standing():
    text = "\n".join(hr.lines(summary(("p1",), ("c:1",), ("r|u",), new_p=1)))
    for needle in ("HUMAN REVIEW", "proposals awaiting decision=1", "identity review=1",
                   "source review=1", "new this cycle=1", "standing queue=2", "queue digest="):
        assert needle in text
    assert "could not be established" in "\n".join(hr.lines(hr.incomplete("X")))


# ------------------------------------------------------------------ issue decisions


def test_actionable_items_with_no_issue_create_one_managed_issue():
    a = rq.decide(report(summary()), [], RUN, "4")
    assert a.kind == rq.CREATE and rq.MARKER in a.body
    assert "queue-digest" in a.body and RUN in a.body


def test_an_unchanged_digest_does_nothing_no_edit_no_comment():
    h = summary()
    for code in ("4", "0"):                      # a quiet cycle with old work still open
        a = rq.decide(report(h), [issue(h)], RUN, code)
        assert a.kind == rq.NOOP and a.comment is None and a.body is None


def test_a_changed_digest_edits_the_issue_and_comments_only_for_new_items():
    old = summary(("a",))
    new_item = rq.decide(report(summary(("a", "b"), new_p=1)), [issue(old)], RUN, "4")
    assert new_item.kind == rq.UPDATE and new_item.number == 7 and new_item.comment
    shrunk = rq.decide(report(summary(("b",))), [issue(old)], RUN, "0")
    assert shrunk.kind == rq.UPDATE and shrunk.comment is None


def test_there_is_only_one_managed_issue_and_a_foreign_issue_is_ignored():
    h = summary()
    foreign = {"number": 1, "state": "OPEN", "title": rq.TITLE, "body": "unrelated"}
    twin = issue(h, number=9)
    a = rq.decide(report(summary(("z",))), [foreign, twin, issue(h, number=7)], RUN, "4")
    assert a.kind == rq.UPDATE and a.number == 7           # lowest managed number, no new issue
    assert rq.decide(report(h), [foreign], RUN, "4").kind == rq.CREATE


def test_the_issue_closes_only_when_the_global_queue_is_provably_empty():
    empty = summary((), (), ())
    close = rq.decide(report(empty), [issue(summary())], RUN, "0")
    assert close.kind == rq.CLOSE and close.number == 7
    for rep in (None, {}, report(hr.incomplete("Boom")), {"human_review": None}):
        assert rq.decide(rep, [issue(summary())], RUN, "0").kind == rq.NOOP
    assert rq.decide(report(summary(("p",))), [issue(summary())], RUN, "0").kind != rq.CLOSE


def test_a_quiet_cycle_with_old_review_work_keeps_the_issue_open():
    standing = summary(("old1", "old2"), new_p=0)
    assert rq.decide(report(standing), [issue(standing)], RUN, "0").kind == rq.NOOP


def test_a_closed_issue_is_reused_when_work_returns():
    closed = issue(summary((), (), ()), state="CLOSED")
    a = rq.decide(report(summary()), [closed], RUN, "4")
    assert a.kind == rq.REOPEN and a.number == 7


def test_a_technical_failure_never_touches_the_queue():
    for code in ("1", "2", "", "137"):
        a = rq.decide(report(summary()), [], RUN, code)
        assert a.kind == rq.NOOP and "technical failure" in a.reason
        assert rq.decide(report(summary((), (), ())), [issue(summary())], RUN, code).kind == rq.NOOP


# ------------------------------------------------------------------ workflow semantics


def test_exit_four_is_a_green_warning_and_failures_are_red():
    assert rq.headline("0")[0] == "notice" and "NO ACTION NEEDED" in rq.headline("0")[1]
    level, text = rq.headline("4")
    assert level == "warning" and text == (
        "REVIEW REQUIRED — discovery completed successfully; human review queue has "
        "actionable items.")
    assert [rq.workflow_fails(c) for c in ("0", "4", "1", "", "137")] == [
        False, False, True, True, True]
    assert rq.headline("1")[0] == "error" and rq.headline("")[0] == "error"


@pytest.mark.parametrize(("code", "rc", "needle"), [
    ("0", 0, "NO ACTION NEEDED"), ("4", 0, "::warning::REVIEW REQUIRED"),
    ("1", 1, "::error::EXECUTION FAILURE"), ("", 1, "::error::EXECUTION FAILURE")])
def test_the_headline_command_exit_status_and_annotation(code, rc, needle):
    done = subprocess.run([sys.executable, str(SCRIPT), "headline", "--code", code],
                          capture_output=True, text=True, check=False)
    assert done.returncode == rc and needle in done.stdout


def test_the_workflow_runs_the_headline_and_the_issue_step_only_after_a_valid_cycle():
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert wf["permissions"] == {"contents": "read", "issues": "write"}
    steps = {s.get("name"): s for s in wf["jobs"]["observe"]["steps"]}
    assert "discovery_review_queue.py headline" in steps["Summary"]["run"]
    assert 'exit "$rc"' in steps["Summary"]["run"]
    issue_step = steps["Review queue issue"]
    cond = issue_step["if"]
    assert "env.MODE == 'observe'" in cond and "code == '0'" in cond and "code == '4'" in cond
    assert issue_step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "secrets." not in str(issue_step)


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None,
                    reason="runs the workflow's bash step; covered on the Linux CI runner")
@pytest.mark.parametrize(("code", "ok"), [("0", True), ("4", True), ("1", False), ("", False)])
def test_the_summary_step_is_green_for_0_and_4_and_red_otherwise(tmp_path, code, ok):
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(s for s in wf["jobs"]["observe"]["steps"] if s.get("name") == "Summary")
    script = tmp_path / "s.sh"
    script.write_text(step["run"].replace("${{ github.event_name }}", "schedule"))
    env = {**os.environ, "CODE": code, "MODE": "observe", "ONLY": "", "RUN_NOW": "false",
           "RUNNER_TEMP": str(tmp_path), "GITHUB_STEP_SUMMARY": str(tmp_path / "sum.md")}
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
                          cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    assert (done.returncode == 0) is ok
    if code == "4":
        assert "::warning::" in done.stdout


# ------------------------------------------------------------------ guards


def test_nothing_in_the_review_path_can_change_publication():
    for path in (SCRIPT, Path(hr.__file__)):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"is_published\s*=[^=]|SET\s+is_published|INSERT |UPDATE |DELETE ",
                             src), path
