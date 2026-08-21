#!/usr/bin/env python3
"""WS8.7 / R26 — the durable release manifest, and the rollback's evidence.

"Roll back to the previous release" is only a real capability if something
durable says what the previous release WAS. A tag does not: tags move, and
`humanoidonline-api:<sha>` can be re-pointed at a rebuilt image with the same
name and different content. The rollback unit is therefore an **image ID**, and
this file is where it is written down.

Written AFTER both images are built, and read by `deploy/rollback.sh`:

    {
      "manifest_schema_version": 1,
      "release_sha": "<40 hex>",
      "created_at": "2026-07-29T…Z",
      "base_image_pins": {"PYTHON_IMAGE": "…@sha256:…", …},
      "images": {
        "api": {"tag": "humanoidonline-api:<sha>", "id": "sha256:…"},
        "web": {"tag": "humanoidonline-web:<sha>", "id": "sha256:…"}
      }
    }

Where it lives matters. `RELEASE_DIR` defaults to `/srv/humanoidonline/releases`:
**outside the repository and outside the Docker build context**, so a manifest
can never be swept into an image, committed by accident, or destroyed by a
checkout of the very release it would be needed to undo. Directory 0700, file
0600 — it records exactly which artefacts are running.

    python3 deploy/release_manifest.py record --env-file /srv/…/.env.production
    python3 deploy/release_manifest.py verify  /srv/…/releases/<sha>.json
    python3 deploy/release_manifest.py read    <manifest> release_sha

`record` and `verify` both prove that each recorded TAG still resolves to the
recorded ID. `verify` performs no build and no pull: it only inspects what is
already on the host, so a rollback cannot quietly become a re-fetch.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from preflight import PINNED_IMAGE_VARS, parse_env_file  # noqa: E402

MANIFEST_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

#: Operator-owned, outside the repository AND outside the build context.
DEFAULT_RELEASE_DIR = "/srv/humanoidonline/releases"

DIR_MODE = 0o700
FILE_MODE = 0o600

IMAGE_TAG_PREFIX = {"api": "humanoidonline-api", "web": "humanoidonline-web"}


class ManifestError(RuntimeError):
    """The manifest is missing, malformed, or no longer describes the host."""


# --------------------------------------------------------------------------- #
# Docker inspection (the only thing here that touches the daemon)
# --------------------------------------------------------------------------- #
def docker_image_id(reference: str) -> str | None:
    """The local image ID for `reference`, or None if it does not exist here.

    `docker image inspect` reads the local store only — it never pulls, which is
    what makes this safe to use as a rollback precondition.
    """
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", reference],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    identifier = result.stdout.strip()
    return identifier or None


# --------------------------------------------------------------------------- #
# Building, writing and reading the manifest
# --------------------------------------------------------------------------- #
def release_tags(release_sha: str) -> dict[str, str]:
    return {role: f"{prefix}:{release_sha}" for role, prefix in IMAGE_TAG_PREFIX.items()}


def build_manifest(
    *,
    release_sha: str,
    pins: dict[str, str],
    image_ids: dict[str, str],
    created_at: datetime | None = None,
) -> dict:
    tags = release_tags(release_sha)
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "release_sha": release_sha,
        "created_at": (created_at or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_image_pins": {name: pins[name] for name in PINNED_IMAGE_VARS},
        "images": {
            role: {"tag": tags[role], "id": image_ids[role]}
            for role in sorted(IMAGE_TAG_PREFIX)
        },
    }


def manifest_path(release_dir: str | Path, release_sha: str) -> Path:
    return Path(release_dir) / f"{release_sha}.json"


def write_manifest(path: Path, manifest: dict) -> Path:
    """0600 inside a 0700 directory, promoted atomically.

    A half-written manifest is worse than none: it would be read during exactly
    the incident it exists for.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    os.chmod(path.parent, DIR_MODE)
    partial = path.with_name(path.name + ".part")
    handle = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    with os.fdopen(handle, "w", encoding="utf-8") as sink:
        json.dump(manifest, sink, indent=2, sort_keys=True)
        sink.write("\n")
    os.chmod(partial, FILE_MODE)
    os.replace(partial, path)
    os.chmod(path, FILE_MODE)
    return path


def load_manifest(path: str | Path) -> dict:
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError(f"cannot read release manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"release manifest {path} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ManifestError(f"release manifest {path} is not an object")
    version = manifest.get("manifest_schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestError(
            f"release manifest {path} has schema version {version!r}; this tool "
            f"supports {sorted(SUPPORTED_SCHEMA_VERSIONS)}. Refusing to guess."
        )
    for field in ("release_sha", "images"):
        if not manifest.get(field):
            raise ManifestError(f"release manifest {path} has no {field}")
    return manifest


# --------------------------------------------------------------------------- #
# Verification — the rollback precondition
# --------------------------------------------------------------------------- #
def verify_images(manifest: dict, *, inspect=docker_image_id) -> list[str]:
    """Every recorded image must still exist HERE, and its tag must still point
    at it. Both halves matter:

      * a missing image means the rollback target is gone (pruned, or never on
        this host) — and re-pulling it is not a rollback, it is a fetch of
        whatever that name resolves to now;
      * a tag that resolves to a DIFFERENT id means something was rebuilt under
        the same name, so starting "that tag" would start the wrong artefact.
    """
    errors: list[str] = []
    images = manifest.get("images") or {}
    for role in sorted(images):
        entry = images[role] or {}
        tag, recorded = entry.get("tag"), entry.get("id")
        if not tag or not recorded:
            errors.append(f"{role}: manifest entry is incomplete (tag={tag!r}, id={recorded!r})")
            continue

        by_id = inspect(recorded)
        if by_id is None:
            errors.append(
                f"{role}: image {recorded} is NOT present on this host. The "
                "rollback target no longer exists; re-pulling would not be a "
                "rollback. Restore the image, or roll back to a release whose "
                "images are still retained."
            )
        by_tag = inspect(tag)
        if by_tag is None:
            errors.append(
                f"{role}: tag {tag} does not exist on this host (recorded id "
                f"{recorded})."
            )
        elif by_tag != recorded:
            errors.append(
                f"{role}: tag {tag} has MOVED — it now resolves to {by_tag}, not "
                f"the recorded {recorded}. Something was rebuilt under the same "
                "name; starting this tag would start the wrong artefact."
            )
    return errors


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _record(argv: list[str]) -> int:
    if "--env-file" not in argv:
        print("usage: release_manifest.py record --env-file PATH [--release-dir DIR]",
              file=sys.stderr)
        return 2
    env = parse_env_file(argv[argv.index("--env-file") + 1])
    release_dir = (
        argv[argv.index("--release-dir") + 1] if "--release-dir" in argv
        else (env.get("RELEASE_DIR") or "").strip() or DEFAULT_RELEASE_DIR
    )
    release_sha = (env.get("RELEASE_SHA") or "").strip()
    if not release_sha:
        print("MANIFEST FAILED: RELEASE_SHA is empty", file=sys.stderr)
        return 1

    tags = release_tags(release_sha)
    image_ids: dict[str, str] = {}
    for role, tag in sorted(tags.items()):
        identifier = docker_image_id(tag)
        if identifier is None:
            print(f"MANIFEST FAILED: {tag} was not built or is not present locally",
                  file=sys.stderr)
            return 1
        image_ids[role] = identifier

    manifest = build_manifest(
        release_sha=release_sha,
        pins={name: (env.get(name) or "").strip() for name in PINNED_IMAGE_VARS},
        image_ids=image_ids,
    )
    errors = verify_images(manifest)
    if errors:
        print("MANIFEST FAILED — recorded images do not resolve:", file=sys.stderr)
        for error in errors:
            print(f"  * {error}", file=sys.stderr)
        return 1

    path = write_manifest(manifest_path(release_dir, release_sha), manifest)
    print(f"release manifest written: {path}")
    for role in sorted(manifest["images"]):
        entry = manifest["images"][role]
        print(f"  {role}: {entry['tag']} -> {entry['id']}")
    return 0


def _verify(argv: list[str]) -> int:
    if not argv:
        print("usage: release_manifest.py verify MANIFEST", file=sys.stderr)
        return 2
    try:
        manifest = load_manifest(argv[0])
    except ManifestError as exc:
        print(f"MANIFEST FAILED: {exc}", file=sys.stderr)
        return 1
    errors = verify_images(manifest)
    if errors:
        print(f"MANIFEST FAILED — {argv[0]} no longer describes this host:",
              file=sys.stderr)
        for error in errors:
            print(f"  * {error}", file=sys.stderr)
        return 1
    print(f"manifest ok: release {manifest['release_sha']} — every recorded image "
          "is present and its tag still resolves to it")
    return 0


def _read(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: release_manifest.py read MANIFEST FIELD", file=sys.stderr)
        return 2
    try:
        manifest = load_manifest(argv[0])
    except ManifestError as exc:
        print(f"MANIFEST FAILED: {exc}", file=sys.stderr)
        return 1
    value = manifest.get(argv[1])
    if value is None:
        print(f"MANIFEST FAILED: no field {argv[1]!r}", file=sys.stderr)
        return 1
    print(value)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: release_manifest.py {record|verify|read} …", file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    handlers = {"record": _record, "verify": _verify, "read": _read}
    if command not in handlers:
        print(f"unknown command {command!r}", file=sys.stderr)
        return 2
    return handlers[command](rest)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
