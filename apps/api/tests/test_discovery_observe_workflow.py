"""The Stage F observation workflow (.github/workflows/discovery-observe.yml).

A scheduled event carries no workflow_dispatch inputs, so the workflow must
supply its own: observe (never plan), the registered NEURA source, run_now
false. This resolves the env expressions per event and executes the real
"Observation cycle" script with a stub `uv` to see the exact CLI arguments.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from app.services.discovery.sources import ADAPTERS

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "discovery-observe.yml"
NEURA = "neura-robotics-official"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))  # YAML 1.1 reads `on` as True


def _job(workflow: dict) -> dict:
    return workflow["jobs"]["observe"]


def _resolve(expr: str, event: str, inputs: dict) -> str:
    """Evaluate `${{ github.event_name == 'schedule' && 'X' || inputs.Y }}`."""
    m = re.fullmatch(r"\$\{\{ github\.event_name == 'schedule' && '([^']*)' \|\| "
                     r"inputs\.([a-z_]+) \}\}", expr)
    assert m, f"unexpected expression {expr!r}"
    if event == "schedule":
        return m.group(1)
    value = inputs.get(m.group(2), "")
    return str(value).lower() if isinstance(value, bool) else value


def test_hourly_schedule_at_minute_37_and_manual_dispatch_kept(workflow):
    triggers = _triggers(workflow)
    assert triggers["schedule"] == [{"cron": "37 * * * *"}]
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert inputs["mode"]["default"] == "plan" and inputs["run_now"]["default"] is False
    assert set(triggers) == {"schedule", "workflow_dispatch"}


def test_gate_role_and_concurrency_are_unchanged(workflow):
    job = _job(workflow)
    assert job["if"] == ("vars.DISCOVERY_OBSERVE_ENABLED == 'true' "
                         "&& github.ref == 'refs/heads/main'")
    assert job["environment"] == "discovery-production"
    assert job["env"]["DATABASE_URL"] == "${{ secrets.DISCOVERY_DATABASE_URL }}"
    assert workflow["concurrency"] == {"group": "discovery-observe", "cancel-in-progress": False}
    names = [s.get("name", s.get("uses", "")) for s in job["steps"]]
    assert "Restore raw-body cache" in names and "Save raw-body cache" in names
    assert not any("prune" in str(s.get("run", "")) for s in job["steps"])  # pruning stays off


def test_scheduled_source_is_the_registered_neura_adapter():
    assert NEURA in ADAPTERS


@pytest.mark.parametrize(("event", "inputs", "expected"), [
    ("schedule", {}, ("observe", NEURA, "false")),
    ("workflow_dispatch", {"mode": "plan", "source": "", "run_now": False}, ("plan", "", "false")),
    ("workflow_dispatch", {"mode": "observe", "source": NEURA, "run_now": True},
     ("observe", NEURA, "true")),
])
def test_env_resolves_per_event(workflow, event, inputs, expected):
    env = _job(workflow)["env"]
    assert tuple(_resolve(env[k], event, inputs) for k in ("MODE", "ONLY", "RUN_NOW")) == expected


def _cycle_args(workflow, tmp_path, mode, only, run_now) -> list[str]:
    step = next(s for s in _job(workflow)["steps"] if s.get("name") == "Observation cycle")
    stub = tmp_path / "bin"
    stub.mkdir()
    uv = stub / "uv"
    uv.write_text('#!/bin/sh\nfor a in "$@"; do echo "$a"; done\n')
    uv.chmod(0o755)
    script = tmp_path / "cycle.sh"
    script.write_text(step["run"])
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "MODE": mode, "ONLY": only,
           "RUN_NOW": run_now, "GITHUB_WORKSPACE": str(tmp_path),
           "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(tmp_path / "out")}
    subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
                   env=env, check=True, capture_output=True)
    assert (tmp_path / "out").read_text().strip() == "code=0"
    lines = (tmp_path / "cycle.txt").read_text().split()
    return lines[lines.index("app.cli.discovery") + 1:]


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None,
                    reason="runs the workflow's bash step; covered on the Linux CI runner")
@pytest.mark.parametrize(("event", "inputs", "want", "absent"), [
    ("schedule", {}, ["observe", "--only", NEURA], ["--plan", "--run-now"]),
    ("workflow_dispatch", {"mode": "plan", "source": NEURA, "run_now": False},
     ["--plan", "--only", NEURA], ["--run-now"]),
    ("workflow_dispatch", {"mode": "observe", "source": NEURA, "run_now": True},
     ["--only", NEURA, "--run-now"], ["--plan"]),
])
def test_cycle_step_passes_the_right_cli_arguments(workflow, tmp_path, event, inputs, want,
                                                   absent):
    env = _job(workflow)["env"]
    mode, only, run_now = (_resolve(env[k], event, inputs) for k in ("MODE", "ONLY", "RUN_NOW"))
    args = _cycle_args(workflow, tmp_path, mode, only, run_now)
    assert args[0] == "observe"
    for token in want:
        assert token in args
    for token in absent:
        assert token not in args
    if "--only" in args:
        assert args[args.index("--only") + 1] == NEURA
