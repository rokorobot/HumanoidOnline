#!/usr/bin/env python3
"""WS8.7 / R26 — release preflight. Runs BEFORE any pull, build or `up`.

THREE gates, all of them refusals rather than warnings. `deploy/release.sh` runs
this script first and stops on a non-zero exit, so nothing is pulled, built or
started until every gate passes.

`pins` — the four base images must be IMMUTABLE.
    Declaring them *required* (no Dockerfile default, `:?` in compose) only
    proves they are non-empty. `PYTHON_IMAGE=python:3.12-slim` is non-empty and
    still means "whatever that tag points at today", which is exactly the
    reproducibility promise R26 makes, broken silently.

      accepted   <image>@sha256:<64 lowercase hex>   e.g. postgres:16@sha256:1f2e…
                 sha256:<64 lowercase hex>           a bare immutable image ID
      rejected   python:3.12-slim   node:20-bookworm-slim   postgres:16   caddy:2
                 anything with no digest, a short/long digest, or upper-case hex

`source` — the release must NAME the source it is built from, truthfully.
    A pinned base image proves nothing about the application layer: `RELEASE_SHA`
    is what the images are tagged with, what the attestation records and what a
    rollback selects. So it must be a full 40-character lower-case SHA, it must
    equal `git rev-parse HEAD`, and the working tree must be clean — no staged
    changes, no tracked modifications, no non-ignored untracked files. Otherwise
    the image contains code that the recorded commit does not, and the rollback
    unit becomes a lie. A clean DETACHED HEAD is fine: deployments legitimately
    check out a commit rather than a branch.

`backup` — in staging/production the off-box destination must be USABLE.
    R30's recovery path is only real if it is configured before the release that
    will need it. This gate proves the configuration resolves — the command
    exists on PATH, the compose file and env file are readable, the backup
    directory is reachable. It deliberately does NOT run an upload: a preflight
    must not have side effects at a remote destination.

Usage (exit 0 = every gate passed; exit 1 = at least one refusal):

    python3 deploy/preflight.py --env-file .env.production
    python3 deploy/preflight.py --env-file … --gates pins,backup   # subset

Only the `source` gate shells out (to `git`); the rest are form and filesystem
checks, so this runs in ordinary CI against fixtures.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

#: The four base images a production release pins. Two are build args, two are
#: runtime image references read by compose — all four must be immutable.
PINNED_IMAGE_VARS = ("PYTHON_IMAGE", "NODE_IMAGE", "POSTGRES_IMAGE", "CADDY_IMAGE")

#: Repository root — `deploy/` lives directly beneath it.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Gate names, in the order they run.
GATES = ("pins", "source", "backup")

#: A full commit id. Short SHAs are rejected: they are ambiguous by design, and
#: an image tagged with one cannot be matched back to exactly one commit forever.
RELEASE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

#: Mirrors deploy/backup.py. A drift test asserts the two agree.
RELAXED_APP_ENVS = frozenset({"development", "test"})
DEFAULT_BACKUP_DIR = "/srv/humanoidonline/backups"
DEFAULT_COMPOSE_FILE = "/srv/humanoidonline/docker-compose.prod.yml"
DEFAULT_COMPOSE_ENV_FILE = "/srv/humanoidonline/.env.production"

#: Lower-case hex only: Docker rejects an upper-case digest, and accepting one
#: here would push the failure into the build instead of catching it now.
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
#: A complete pull-able reference: <name>[:tag]@sha256:<64 hex>.
DIGESTED_REF_RE = re.compile(r"^(?P<name>[^\s@]+)@(?P<digest>sha256:[0-9a-f]{64})$")


class PinError(ValueError):
    """A pin is missing or is not an immutable reference."""


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Read a `KEY=value` file the way systemd's EnvironmentFile and compose's
    `--env-file` both read it: `#` comments, optional `export`, and surrounding
    quotes stripped (a value containing spaces MUST be quoted)."""
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            # An unquoted value ends at a trailing ` #` comment, as both parsers
            # treat it. This is why a value with spaces has to be quoted.
            value = value.split(" #", 1)[0].strip()
        values[key] = value
    return values


def check_pin(name: str, value: str | None) -> str | None:
    """Return a human-readable error for `value`, or None when it is immutable."""
    value = (value or "").strip()
    if not value:
        return (
            f"{name} is empty. Pin an immutable digest, e.g. "
            f"{name}=<image>@sha256:<64 hex> "
            "(resolve it with `docker buildx imagetools inspect <image>:<tag>`)."
        )
    if any(char.isspace() for char in value):
        return f"{name}={value!r} contains whitespace and is not an image reference."

    if "@" not in value:
        if DIGEST_RE.match(value):
            return None  # bare, immutable image ID
        if value.lower().startswith("sha256:"):
            return (
                f"{name}={value!r} is a malformed digest: expected "
                "sha256:<64 lower-case hex>."
            )
        return (
            f"{name}={value!r} is a MUTABLE TAG. A tag can be re-pointed at any "
            "time, so a build against it is not reproducible (R26). Use "
            f"{value}@sha256:<64 hex>."
        )

    match = DIGESTED_REF_RE.match(value)
    if match is None:
        _, _, digest = value.rpartition("@")
        return (
            f"{name}={value!r} is not a valid digest reference: the part after "
            f"'@' must be sha256:<64 lower-case hex>, got {digest!r}."
        )
    if not match.group("name"):
        return f"{name}={value!r} has no image name before the digest."
    return None


def check_pins(env: dict[str, str], variables: tuple[str, ...] = PINNED_IMAGE_VARS) -> list[str]:
    """Every failure, not just the first — an operator should fix them in one go."""
    return [error for name in variables if (error := check_pin(name, env.get(name)))]


# --------------------------------------------------------------------------- #
# Gate: source identity
# --------------------------------------------------------------------------- #
def _git(args: list[str], repo_root: Path) -> tuple[int, str]:
    """Run git in the repository, returning (exit code, stripped stdout)."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True
    )
    return result.returncode, result.stdout.strip()


def check_source_identity(
    env: dict[str, str],
    *,
    repo_root: Path = REPO_ROOT,
    git=_git,
) -> list[str]:
    """RELEASE_SHA must be a full commit id, must BE the checked-out commit, and
    the tree must have nothing in it that the commit does not describe."""
    errors: list[str] = []
    release_sha = (env.get("RELEASE_SHA") or "").strip()

    if not release_sha:
        errors.append(
            "RELEASE_SHA is empty. It names the exact commit these images are "
            "built from, and is what a rollback selects — set it to the full "
            "`git rev-parse HEAD`."
        )
    elif not RELEASE_SHA_RE.match(release_sha):
        errors.append(
            f"RELEASE_SHA={release_sha!r} is not a full 40-character lower-case "
            "commit id. A short or abbreviated SHA is ambiguous and cannot "
            "identify one commit forever."
        )

    code, head = git(["rev-parse", "HEAD"], repo_root)
    if code != 0:
        errors.append(
            f"cannot resolve HEAD in {repo_root} (git exit {code}). A release "
            "must be built from a real checkout of the release commit."
        )
        return errors  # every remaining check depends on a working repository

    if release_sha and RELEASE_SHA_RE.match(release_sha) and head != release_sha:
        errors.append(
            f"RELEASE_SHA={release_sha} is NOT the checked-out commit "
            f"({head}). The images would be tagged with a commit whose code is "
            "not what gets built. Check out the release commit, or correct "
            "RELEASE_SHA."
        )

    # A detached HEAD is deliberately allowed — checking out a commit rather than
    # a branch is the normal way to deploy an exact release.
    for args, what, remedy in (
        (["diff", "--cached", "--name-only"], "staged changes",
         "commit them or reset the index"),
        (["diff", "--name-only"], "modifications to tracked files",
         "commit or discard them"),
        (["ls-files", "--others", "--exclude-standard"], "untracked files",
         "commit, remove or ignore them"),
    ):
        code, output = git(args, repo_root)
        if code != 0:
            errors.append(f"cannot inspect the working tree for {what} (git exit {code})")
            continue
        if output:
            files = [line for line in output.splitlines() if line.strip()]
            shown = ", ".join(files[:5]) + (" …" if len(files) > 5 else "")
            errors.append(
                f"the working tree has {what} ({len(files)}): {shown}. The image "
                f"would contain code that {head} does not — {remedy}."
            )
    return errors


# --------------------------------------------------------------------------- #
# Gate: backup activation
# --------------------------------------------------------------------------- #
def _is_readable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.R_OK)


def check_backup_activation(
    env: dict[str, str],
    *,
    which=shutil.which,
    is_readable=_is_readable,
    isdir=os.path.isdir,
) -> list[str]:
    """The off-box destination must be CONFIGURED AND RESOLVABLE before a release
    that will depend on it.

    Nothing is uploaded here. A preflight that wrote to the destination would
    have side effects at a remote system every time someone checked a release,
    and a destination that only works when preflight runs is not a backup.
    """
    app_env = (env.get("APP_ENV") or "").strip().lower() or "production"
    if app_env in RELAXED_APP_ENVS:
        return []

    errors: list[str] = []
    command = (env.get("BACKUP_UPLOAD_COMMAND") or "").strip()
    if not command:
        errors.append(
            f'BACKUP_UPLOAD_COMMAND is empty and APP_ENV="{app_env}". Releasing '
            "with no off-box destination means the first incident is also the "
            "first time anyone finds out there is no backup. Set it to any "
            "command that copies {path} off the box."
        )
    else:
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            parts = []
            errors.append(f"BACKUP_UPLOAD_COMMAND cannot be parsed as a command: {exc}")
        if parts:
            executable = parts[0]
            resolved = which(executable)
            if resolved is None:
                errors.append(
                    f"BACKUP_UPLOAD_COMMAND starts with {executable!r}, which is "
                    "not on PATH and is not an executable file. The nightly "
                    "timer would fail every night after the release."
                )

    backup_dir = (env.get("BACKUP_DIR") or "").strip() or DEFAULT_BACKUP_DIR
    if isdir(backup_dir):
        pass
    elif not isdir(str(Path(backup_dir).parent)):
        errors.append(
            f"BACKUP_DIR={backup_dir} does not exist and neither does its parent, "
            "so the backup script cannot create it."
        )

    for name, default in (
        ("BACKUP_COMPOSE_FILE", DEFAULT_COMPOSE_FILE),
        ("BACKUP_COMPOSE_ENV_FILE", DEFAULT_COMPOSE_ENV_FILE),
    ):
        path = (env.get(name) or "").strip() or default
        if not is_readable(path):
            errors.append(
                f"{name}={path} is not a readable file. The backup runs "
                "`docker compose --env-file … -f … exec -T db …`, which cannot "
                "reach the database without both."
            )
    return errors


GATE_HEADLINES = {
    "pins": "base images are not immutably pinned",
    "source": "the release does not truthfully name its source",
    "backup": "the off-box backup destination is not usable",
}
GATE_OK = {
    "pins": "all four base images are pinned to a digest",
    "source": "RELEASE_SHA is the clean checked-out commit",
    "backup": "off-box destination configured and resolvable",
}


def run_gates(env: dict[str, str], gates: tuple[str, ...] = GATES) -> dict[str, list[str]]:
    """Run each requested gate and return its refusals, keyed by gate name."""
    runners = {
        "pins": lambda: check_pins(env),
        "source": lambda: check_source_identity(env),
        "backup": lambda: check_backup_activation(env),
    }
    return {name: runners[name]() for name in gates}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env: dict[str, str] = dict(os.environ)
    if "--env-file" in argv:
        path = argv[argv.index("--env-file") + 1]
        try:
            env = parse_env_file(path)
        except OSError as exc:
            print(f"PREFLIGHT FAILED: cannot read {path}: {exc}", file=sys.stderr)
            return 1

    gates = GATES
    if "--gates" in argv:
        requested = tuple(
            part.strip() for part in argv[argv.index("--gates") + 1].split(",")
            if part.strip()
        )
        unknown = [name for name in requested if name not in GATES]
        if unknown or not requested:
            print(f"PREFLIGHT FAILED: unknown gate(s): {unknown or ['(none given)']}",
                  file=sys.stderr)
            return 1
        gates = requested

    results = run_gates(env, gates)
    failed = False
    for name in gates:
        errors = results[name]
        if errors:
            failed = True
            print(f"PREFLIGHT FAILED [{name}] — {GATE_HEADLINES[name]}:", file=sys.stderr)
            for error in errors:
                print(f"  * {error}", file=sys.stderr)
    if failed:
        return 1
    for name in gates:
        print(f"preflight ok [{name}]: {GATE_OK[name]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
