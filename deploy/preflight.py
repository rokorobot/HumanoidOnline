#!/usr/bin/env python3
"""WS8.7 / R26 — image-pin preflight. Runs BEFORE any pull, build or `up`.

Declaring the four image variables as *required* (no Dockerfile default, `:?` in
compose) only proves they are **non-empty**. `PYTHON_IMAGE=python:3.12-slim` is
non-empty and still means "whatever that tag points at today" — which is exactly
the reproducibility promise R26 makes, broken silently.

So the supported production path (`deploy/release.sh`) validates the FORM of
every pin first and refuses to continue:

  accepted   <image>@sha256:<64 lowercase hex>   e.g. postgres:16@sha256:1f2e…
             sha256:<64 lowercase hex>           a bare immutable image ID
  rejected   python:3.12-slim   node:20-bookworm-slim   postgres:16   caddy:2
             anything with no digest, a short/long digest, or upper-case hex

Usage (exit 0 = every pin is immutable; exit 1 = at least one is not):

    python3 deploy/preflight.py                       # validate the environment
    python3 deploy/preflight.py --env-file .env.production

Nothing here talks to Docker, the network or the VPS: it is a pure form check on
values, so it can also run in ordinary CI against fixtures.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

#: The four base images a production release pins. Two are build args, two are
#: runtime image references read by compose — all four must be immutable.
PINNED_IMAGE_VARS = ("PYTHON_IMAGE", "NODE_IMAGE", "POSTGRES_IMAGE", "CADDY_IMAGE")

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

    errors = check_pins(env)
    if errors:
        print("PREFLIGHT FAILED — base images are not immutably pinned:", file=sys.stderr)
        for error in errors:
            print(f"  * {error}", file=sys.stderr)
        return 1
    print("preflight ok: all four base images are pinned to a digest")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
