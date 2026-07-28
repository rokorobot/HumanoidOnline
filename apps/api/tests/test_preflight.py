"""WS8.7 / R26 — the image-pin preflight actually enforces a DIGEST.

The earlier corrective pass made the four base-image variables *required*: no
Dockerfile default, `:?` in compose. That only proves they are non-empty, and
`POSTGRES_IMAGE=postgres:16` is non-empty while meaning "whatever that tag points
at today" — the exact thing R26's reproducible-build promise forbids.

`deploy/preflight.py` closes that gap by checking the FORM of each value, and
`deploy/release.sh` — the supported production path — runs it BEFORE anything is
pulled, built or started.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
PREFLIGHT_PY = ROOT / "deploy" / "preflight.py"
RELEASE_SH = ROOT / "deploy" / "release.sh"
ENV_EXAMPLE = ROOT / ".env.production.example"

HEX = "0123456789abcdef" * 4  # 64 lower-case hex characters


def _load():
    spec = importlib.util.spec_from_file_location("ho_preflight", PREFLIGHT_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


preflight = _load()


# --------------------------------------------------------------------------- #
# Accepted: immutable references
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [
        f"python:3.12-slim-bookworm@sha256:{HEX}",
        f"node:20-bookworm-slim@sha256:{HEX}",
        f"postgres:16@sha256:{HEX}",
        f"caddy:2@sha256:{HEX}",
        # A digest reference needs no tag, and may be fully qualified.
        f"postgres@sha256:{HEX}",
        f"docker.io/library/caddy@sha256:{HEX}",
        f"registry.example.com:5000/team/api:1.2.3@sha256:{HEX}",
        # A bare image ID is immutable too.
        f"sha256:{HEX}",
    ],
)
def test_digest_references_are_accepted(value: str) -> None:
    assert preflight.check_pin("PYTHON_IMAGE", value) is None


def test_surrounding_whitespace_is_tolerated() -> None:
    assert preflight.check_pin("CADDY_IMAGE", f"  caddy:2@sha256:{HEX}  ") is None


# --------------------------------------------------------------------------- #
# Rejected: mutable tags — the whole point of the gate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [
        "python:3.12-slim",
        "python:3.12-slim-bookworm",
        "node:20-bookworm-slim",
        "postgres:16",
        "caddy:2",
        "caddy:latest",
        "postgres",  # no tag at all — resolves to :latest
        "docker.io/library/postgres:16",
    ],
)
def test_mutable_tags_are_rejected(value: str) -> None:
    error = preflight.check_pin("POSTGRES_IMAGE", value)
    assert error is not None, f"{value} is a mutable tag and must be rejected"
    assert "MUTABLE TAG" in error
    assert "sha256" in error, "the message must say what to do instead"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        None,
    ],
)
def test_missing_values_are_rejected(value) -> None:
    error = preflight.check_pin("NODE_IMAGE", value)
    assert error is not None and "empty" in error


@pytest.mark.parametrize(
    "value",
    [
        f"postgres:16@sha256:{HEX[:63]}",           # too short
        f"postgres:16@sha256:{HEX}0",               # too long
        f"postgres:16@sha256:{HEX.upper()}",        # upper-case hex
        f"postgres:16@sha512:{HEX}",                # wrong algorithm
        f"postgres:16@{HEX}",                       # no algorithm
        f"@sha256:{HEX}",                           # no image name
        f"postgres:16 @sha256:{HEX}",               # whitespace inside
        "sha256:deadbeef",                          # malformed bare digest
        f"sha256:{HEX.upper()}",                    # upper-case bare digest
    ],
)
def test_malformed_digests_are_rejected(value: str) -> None:
    assert preflight.check_pin("CADDY_IMAGE", value) is not None


# --------------------------------------------------------------------------- #
# The gate as a whole
# --------------------------------------------------------------------------- #
def test_all_four_production_images_are_checked() -> None:
    assert preflight.PINNED_IMAGE_VARS == (
        "PYTHON_IMAGE", "NODE_IMAGE", "POSTGRES_IMAGE", "CADDY_IMAGE",
    )


def test_every_failure_is_reported_not_just_the_first() -> None:
    errors = preflight.check_pins({
        "PYTHON_IMAGE": f"python:3.12-slim-bookworm@sha256:{HEX}",
        "NODE_IMAGE": "node:20-bookworm-slim",
        "POSTGRES_IMAGE": "postgres:16",
        "CADDY_IMAGE": "",
    })
    assert len(errors) == 3
    assert not any(error.startswith("PYTHON_IMAGE") for error in errors)


def test_a_fully_pinned_environment_passes() -> None:
    assert preflight.check_pins({var: f"x@sha256:{HEX}"
                                 for var in preflight.PINNED_IMAGE_VARS}) == []


def test_the_shipped_template_does_not_pass_preflight() -> None:
    """All four pins ship BLANK, so an operator cannot deploy the template as-is
    and end up on mutable tags by accident."""
    values = preflight.parse_env_file(ENV_EXAMPLE)
    for var in preflight.PINNED_IMAGE_VARS:
        assert values[var] == "", f"{var} must ship blank"
    assert len(preflight.check_pins(values)) == 4


def test_cli_exits_non_zero_for_a_mutable_tag(tmp_path, capsys) -> None:
    env_file = tmp_path / "env"
    env_file.write_text(
        f"PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:{HEX}\n"
        f"NODE_IMAGE=node:20-bookworm-slim@sha256:{HEX}\n"
        "POSTGRES_IMAGE=postgres:16\n"
        f"CADDY_IMAGE=caddy:2@sha256:{HEX}\n",
        encoding="utf-8",
    )
    assert preflight.main(["--env-file", str(env_file)]) == 1
    assert "POSTGRES_IMAGE" in capsys.readouterr().err


def test_cli_exits_zero_when_every_pin_is_a_digest(tmp_path) -> None:
    env_file = tmp_path / "env"
    env_file.write_text(
        "".join(f"{var}=image@sha256:{HEX}\n" for var in preflight.PINNED_IMAGE_VARS),
        encoding="utf-8",
    )
    assert preflight.main(["--env-file", str(env_file)]) == 0


def test_cli_reports_an_unreadable_env_file(tmp_path, capsys) -> None:
    assert preflight.main(["--env-file", str(tmp_path / "nope")]) == 1
    assert "cannot read" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Env-file parsing — the same quoting rules the operator is told to follow
# --------------------------------------------------------------------------- #
def test_env_file_parsing_matches_the_documented_quoting(tmp_path) -> None:
    env_file = tmp_path / "env"
    env_file.write_text(
        "# a comment\n"
        "\n"
        "PLAIN=value\n"
        "SPACED=\"rclone copy {path} remote:humanoidonline/backups\"\n"
        "TRAILING=value            # explanatory comment\n"
        "export EXPORTED=exported-value\n"
        "NOT_AN_ASSIGNMENT\n",
        encoding="utf-8",
    )
    values = preflight.parse_env_file(env_file)
    assert values["PLAIN"] == "value"
    assert values["SPACED"] == "rclone copy {path} remote:humanoidonline/backups"
    assert values["TRAILING"] == "value"
    assert values["EXPORTED"] == "exported-value"
    assert "NOT_AN_ASSIGNMENT" not in values


# --------------------------------------------------------------------------- #
# Ordering: the gate is useless if it runs after the build
# --------------------------------------------------------------------------- #
def test_release_script_runs_the_preflight_before_any_docker_operation() -> None:
    lines = [
        line for line in RELEASE_SH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    preflight_at = next(i for i, line in enumerate(lines) if "preflight.py" in line)
    docker_at = [
        i for i, line in enumerate(lines)
        if line.lstrip().startswith(("docker build", "docker compose", "docker pull",
                                     "docker image"))
    ]
    assert docker_at, "the release path must actually build and start something"
    assert preflight_at < min(docker_at), (
        "the pin preflight must run BEFORE any pull, build or up operation"
    )


def test_release_script_builds_both_images_with_the_pinned_bases() -> None:
    source = RELEASE_SH.read_text(encoding="utf-8")
    assert '--build-arg PYTHON_IMAGE="$PYTHON_IMAGE"' in source
    assert '--build-arg NODE_IMAGE="$NODE_IMAGE"' in source
    assert "docker compose --env-file" in source
    assert "set -euo pipefail" in source, "a failed step must stop the release"
