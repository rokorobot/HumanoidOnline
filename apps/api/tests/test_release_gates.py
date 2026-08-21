"""WS8.7 / R26 — the final pre-Ready release gates, tested adversarially.

Four refusals stand between a repository and a running production release:

  1. pins           — base images must be immutable digests
  2. source         — RELEASE_SHA must be the CLEAN, checked-out commit
  3. backup         — staging/production must have a usable off-box destination
  4. manifest       — what was built is recorded durably, and what is started is
                      proven to still BE that (by image ID, not by tag)

Gates 1–3 run before the first Docker operation of any kind; gate 4 is written
after the build and re-verified before compose starts, and is what
`deploy/rollback.sh` consumes.

Every test here asks the hostile question — what does the gate do when the input
is WRONG — because a gate that has only ever been shown a correct input has not
been tested at all.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import stat
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy"
RELEASE_SH = DEPLOY / "release.sh"
ROLLBACK_SH = DEPLOY / "rollback.sh"

HEX = "0123456789abcdef" * 4          # a 64-hex digest body
SHA = "a" * 40                        # a full commit id
OTHER_SHA = "b" * 40


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


preflight = _load("ho_preflight_gates", DEPLOY / "preflight.py")
manifest_mod = _load("ho_release_manifest", DEPLOY / "release_manifest.py")
backup_mod = _load("ho_backup_gates", DEPLOY / "backup.py")


# --------------------------------------------------------------------------- #
# Gate 2 — source identity
# --------------------------------------------------------------------------- #
CLEAN_TREE = {
    ("rev-parse", "HEAD"): (0, SHA),
    ("diff", "--cached", "--name-only"): (0, ""),
    ("diff", "--name-only"): (0, ""),
    ("ls-files", "--others", "--exclude-standard"): (0, ""),
}


def _git_stub(overrides: dict | None = None):
    table = {**CLEAN_TREE, **(overrides or {})}
    calls: list[tuple] = []

    def git(args, repo_root):  # noqa: ANN001
        calls.append(tuple(args))
        return table[tuple(args)]

    git.calls = calls
    return git


def test_a_clean_checkout_of_the_release_commit_passes() -> None:
    assert preflight.check_source_identity({"RELEASE_SHA": SHA}, git=_git_stub()) == []


def test_a_clean_detached_head_is_allowed() -> None:
    """Deploying an exact commit — rather than a branch — is the normal case and
    must not be treated as a defect."""
    git = _git_stub()
    assert preflight.check_source_identity({"RELEASE_SHA": SHA}, git=git) == []
    assert not any("symbolic-ref" in " ".join(call) for call in git.calls), (
        "the gate must not require HEAD to be on a branch"
    )


def test_release_sha_must_be_the_checked_out_commit() -> None:
    """The images are TAGGED with RELEASE_SHA. If it is not the commit being
    built, every downstream record — attestation, manifest, rollback — is wrong."""
    errors = preflight.check_source_identity(
        {"RELEASE_SHA": OTHER_SHA}, git=_git_stub()
    )
    assert any("NOT the checked-out commit" in error for error in errors)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 7,              # short SHA — ambiguous
        "a" * 39,             # one short of a full id
        "a" * 41,
        "A" * 40,             # upper case
        "z" * 40,             # not hex
        f" {SHA[:39]}g ",
    ],
)
def test_release_sha_must_be_a_full_lowercase_commit_id(value: str) -> None:
    errors = preflight.check_source_identity({"RELEASE_SHA": value}, git=_git_stub())
    assert errors, f"{value!r} must be rejected"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("diff", "--cached", "--name-only"), "staged changes"),
        (("diff", "--name-only"), "modifications to tracked files"),
        (("ls-files", "--others", "--exclude-standard"), "untracked files"),
    ],
)
def test_a_dirty_tree_is_refused(args, expected) -> None:
    """Three distinct ways the tree can contain code the commit does not."""
    git = _git_stub({args: (0, "apps/api/app/main.py")})
    errors = preflight.check_source_identity({"RELEASE_SHA": SHA}, git=git)
    assert any(expected in error for error in errors), errors
    assert any("apps/api/app/main.py" in error for error in errors), (
        "the operator must be told WHICH file"
    )


def test_many_dirty_files_are_summarised_not_dumped() -> None:
    files = "\n".join(f"apps/web/f{i}.ts" for i in range(12))
    git = _git_stub({("diff", "--name-only"): (0, files)})
    errors = preflight.check_source_identity({"RELEASE_SHA": SHA}, git=git)
    assert any("(12)" in error and "…" in error for error in errors)


def test_an_ignored_file_is_not_a_dirty_tree() -> None:
    """`--exclude-standard` is what makes this usable: .next/, .venv/ and
    node_modules/ are always present on a build host."""
    assert preflight.check_source_identity({"RELEASE_SHA": SHA}, git=_git_stub()) == []


def test_a_broken_repository_is_a_refusal_not_a_pass() -> None:
    git = _git_stub({("rev-parse", "HEAD"): (128, "")})
    errors = preflight.check_source_identity({"RELEASE_SHA": SHA}, git=git)
    assert errors and any("cannot resolve HEAD" in error for error in errors)


# --------------------------------------------------------------------------- #
# Gate 3 — backup activation
# --------------------------------------------------------------------------- #
BACKUP_ENV = {
    "APP_ENV": "production",
    "BACKUP_UPLOAD_COMMAND": "rclone copy {path} remote:humanoidonline/backups",
    "BACKUP_DIR": "/srv/humanoidonline/backups",
    "BACKUP_COMPOSE_FILE": "/srv/humanoidonline/docker-compose.prod.yml",
    "BACKUP_COMPOSE_ENV_FILE": "/srv/humanoidonline/.env.production",
}


def _backup_check(env, *, found=True, readable=True, isdir=True):
    return preflight.check_backup_activation(
        env,
        which=lambda name: f"/usr/bin/{name}" if found else None,
        is_readable=lambda path: readable,
        isdir=lambda path: isdir,
    )


def test_a_configured_destination_passes() -> None:
    assert _backup_check(BACKUP_ENV) == []


@pytest.mark.parametrize("app_env", ["production", "staging", ""])
def test_a_release_without_an_offbox_destination_is_refused(app_env) -> None:
    errors = _backup_check({**BACKUP_ENV, "APP_ENV": app_env, "BACKUP_UPLOAD_COMMAND": ""})
    assert any("BACKUP_UPLOAD_COMMAND is empty" in error for error in errors)


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_relaxed_environments_are_untouched(app_env) -> None:
    assert _backup_check({"APP_ENV": app_env}) == []


def test_an_upload_executable_that_does_not_exist_is_refused() -> None:
    """The nightly timer would fail every night after the release, and nobody
    would find out until the restore."""
    errors = _backup_check(BACKUP_ENV, found=False)
    assert any("not on PATH" in error for error in errors)
    assert any("rclone" in error for error in errors)


def test_an_unparseable_upload_command_is_refused() -> None:
    errors = _backup_check({**BACKUP_ENV, "BACKUP_UPLOAD_COMMAND": 'rclone "unclosed'})
    assert any("cannot be parsed" in error for error in errors)


def test_unusable_backup_compose_paths_are_refused() -> None:
    errors = _backup_check(BACKUP_ENV, readable=False)
    assert any("BACKUP_COMPOSE_FILE" in error for error in errors)
    assert any("BACKUP_COMPOSE_ENV_FILE" in error for error in errors)


def test_an_unreachable_backup_directory_is_refused() -> None:
    errors = _backup_check(BACKUP_ENV, isdir=False)
    assert any("neither does its parent" in error for error in errors)


def test_the_backup_gate_never_runs_the_upload(monkeypatch) -> None:
    """A preflight with remote side effects is not a preflight. Checking a
    release must not write anything to the destination."""
    def explode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError(f"preflight executed a subprocess: {args!r}")

    monkeypatch.setattr(preflight.subprocess, "run", explode)
    assert preflight.check_backup_activation(
        BACKUP_ENV, which=lambda name: "/usr/bin/rclone",
        is_readable=lambda path: True, isdir=lambda path: True,
    ) == []


def test_preflight_and_backup_agree_on_their_shared_defaults() -> None:
    """Two files read the same variables; a silent divergence would make the
    gate check something the backup does not use."""
    assert preflight.RELAXED_APP_ENVS == backup_mod.RELAXED_APP_ENVS
    assert preflight.DEFAULT_BACKUP_DIR == backup_mod.DEFAULT_BACKUP_DIR
    assert preflight.DEFAULT_COMPOSE_FILE == backup_mod.DEFAULT_COMPOSE_FILE
    assert preflight.DEFAULT_COMPOSE_ENV_FILE == backup_mod.DEFAULT_COMPOSE_ENV_FILE


# --------------------------------------------------------------------------- #
# Gate 4 — the release manifest
# --------------------------------------------------------------------------- #
API_TAG = f"humanoidonline-api:{SHA}"
WEB_TAG = f"humanoidonline-web:{SHA}"
API_ID = f"sha256:{HEX}"
WEB_ID = "sha256:" + "f" * 64


def _manifest(**overrides):
    base = manifest_mod.build_manifest(
        release_sha=SHA,
        pins={name: f"image@sha256:{HEX}" for name in preflight.PINNED_IMAGE_VARS},
        image_ids={"api": API_ID, "web": WEB_ID},
    )
    base.update(overrides)
    return base


def _inspector(table: dict[str, str | None]):
    return lambda reference: table.get(reference)


HONEST_HOST = {API_TAG: API_ID, WEB_TAG: WEB_ID, API_ID: API_ID, WEB_ID: WEB_ID}


def test_the_manifest_records_everything_a_rollback_needs() -> None:
    manifest = _manifest()
    assert manifest["manifest_schema_version"] == manifest_mod.MANIFEST_SCHEMA_VERSION
    assert manifest["release_sha"] == SHA
    assert manifest["created_at"].endswith("Z")
    assert set(manifest["base_image_pins"]) == set(preflight.PINNED_IMAGE_VARS)
    assert manifest["images"]["api"] == {"tag": API_TAG, "id": API_ID}
    assert manifest["images"]["web"] == {"tag": WEB_TAG, "id": WEB_ID}


def test_a_host_that_still_matches_the_manifest_verifies() -> None:
    assert manifest_mod.verify_images(_manifest(), inspect=_inspector(HONEST_HOST)) == []


def test_a_missing_image_refuses_the_rollback() -> None:
    """The target is gone. Re-pulling would not be a rollback — it would fetch
    whatever that name resolves to now."""
    host = {**HONEST_HOST}
    del host[API_ID]
    del host[API_TAG]
    errors = manifest_mod.verify_images(_manifest(), inspect=_inspector(host))
    assert any("NOT present on this host" in error for error in errors)


def test_a_moved_tag_refuses_the_rollback() -> None:
    """Something was rebuilt under the same name: starting the tag would start
    the wrong artefact. This is the failure a tag-based rollback cannot see."""
    moved = {**HONEST_HOST, API_TAG: "sha256:" + "9" * 64}
    errors = manifest_mod.verify_images(_manifest(), inspect=_inspector(moved))
    assert any("has MOVED" in error for error in errors)
    assert any(API_TAG in error for error in errors)


def test_an_incomplete_manifest_entry_is_refused() -> None:
    manifest = _manifest()
    manifest["images"]["api"] = {"tag": API_TAG}
    errors = manifest_mod.verify_images(manifest, inspect=_inspector(HONEST_HOST))
    assert any("incomplete" in error for error in errors)


def test_the_manifest_is_written_0600_in_a_0700_directory(tmp_path) -> None:
    target = manifest_mod.manifest_path(tmp_path / "releases", SHA)
    chmods: list[tuple[str, int]] = []
    real = os.chmod
    manifest_mod.os.chmod = lambda path, mode: (  # type: ignore[assignment]
        chmods.append((str(path), mode)), real(path, mode)
    )[0]
    try:
        written = manifest_mod.write_manifest(target, _manifest())
    finally:
        manifest_mod.os.chmod = real  # type: ignore[assignment]

    assert written.exists()
    assert (str(target.parent), 0o700) in chmods
    assert (str(target), 0o600) in chmods
    assert list(target.parent.glob("*.part")) == [], "promotion must be atomic"
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


def test_a_written_manifest_round_trips(tmp_path) -> None:
    path = manifest_mod.write_manifest(
        manifest_mod.manifest_path(tmp_path, SHA), _manifest())
    assert manifest_mod.load_manifest(path)["images"]["web"]["id"] == WEB_ID


def test_an_unknown_schema_version_is_refused_not_guessed(tmp_path) -> None:
    path = tmp_path / "future.json"
    path.write_text(json.dumps({"manifest_schema_version": 99, "release_sha": SHA,
                                "images": {}}), encoding="utf-8")
    with pytest.raises(manifest_mod.ManifestError) as exc:
        manifest_mod.load_manifest(path)
    assert "Refusing to guess" in str(exc.value)


@pytest.mark.parametrize(
    "content", ["not json at all", '"a string"', '{"release_sha": "x"}', "{}"],
)
def test_a_malformed_manifest_is_refused(tmp_path, content) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(manifest_mod.ManifestError):
        manifest_mod.load_manifest(path)


def test_a_missing_manifest_is_refused(tmp_path) -> None:
    with pytest.raises(manifest_mod.ManifestError):
        manifest_mod.load_manifest(tmp_path / "nope.json")


def test_the_release_directory_lives_outside_the_repository() -> None:
    """A manifest inside the repo could be swept into the build context, or
    removed by checking out the very release it is needed to undo."""
    default = pathlib.PurePosixPath(manifest_mod.DEFAULT_RELEASE_DIR)
    assert default.is_absolute()
    assert not str(default).startswith(str(ROOT)), "must not be inside the repository"
    env = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    assert "RELEASE_DIR=/srv/humanoidonline/releases" in env


# --------------------------------------------------------------------------- #
# Ordering — a gate that runs after the build is decoration
# --------------------------------------------------------------------------- #
def _script_lines(path: pathlib.Path) -> list[str]:
    return [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


DOCKER_PREFIXES = ("docker build", "docker compose", "docker pull", "docker image",
                   "docker run")


def _find(lines: list[str], *fragments: str) -> int:
    """Index of the first line containing every fragment.

    Fragment matching, not exact strings: the scripts quote their paths
    (`"$HERE/release_manifest.py" verify …`), so a naive substring search for
    `release_manifest.py verify` would silently never match and the ordering
    assertion would pass vacuously.
    """
    for index, line in enumerate(lines):
        if all(fragment in line for fragment in fragments):
            return index
    raise AssertionError(f"no line contains all of {fragments}")


def _first_docker(lines: list[str]) -> int:
    indexes = [
        i for i, line in enumerate(lines)
        if line.lstrip().startswith(DOCKER_PREFIXES)
    ]
    assert indexes, "the script must actually do something with Docker"
    return min(indexes)


def test_every_environment_gate_runs_before_the_first_docker_operation() -> None:
    """pins, source and backup are all one invocation, and it comes first."""
    lines = _script_lines(RELEASE_SH)
    preflight_at = next(i for i, line in enumerate(lines) if "preflight.py" in line)
    assert preflight_at < _first_docker(lines)


def test_the_release_path_does_not_narrow_the_gate_set() -> None:
    """`--gates` exists for debugging. A release that quietly skipped the source
    or backup gate would pass this file's other tests and still be unsafe."""
    line = next(line for line in _script_lines(RELEASE_SH) if "preflight.py" in line)
    assert "--gates" not in line, "the supported path must run every gate"


def test_the_manifest_is_recorded_and_verified_before_compose_starts() -> None:
    lines = _script_lines(RELEASE_SH)
    record_at = _find(lines, "release_manifest.py", " record ")
    verify_at = _find(lines, "release_manifest.py", " verify ")
    up_at = _find(lines, "docker compose", " up ")
    build_at = [i for i, line in enumerate(lines) if line.lstrip().startswith("docker build")]
    assert build_at, "the release must build both images"
    assert max(build_at) < record_at, "the manifest records what was actually built"
    assert record_at < verify_at < up_at, "nothing starts before the record is proven"


def test_rollback_verifies_before_it_starts_anything() -> None:
    lines = _script_lines(ROLLBACK_SH)
    verify_at = _find(lines, "release_manifest.py", " verify ")
    up_at = _find(lines, "docker compose", " up ")
    assert verify_at < up_at


def test_rollback_never_builds_and_never_pulls() -> None:
    """A rollback that rebuilds is not a rollback: it resolves names again, and
    the whole point is that a name may now mean something else."""
    for line in _script_lines(ROLLBACK_SH):
        assert not line.lstrip().startswith("docker build"), line
        assert not line.lstrip().startswith("docker pull"), line
    source = ROLLBACK_SH.read_text(encoding="utf-8")
    assert "config --images" in source, (
        "the rollback must read back compose's own resolution rather than "
        "assuming an exported variable wins over the env file"
    )


def test_rollback_requires_a_manifest_argument() -> None:
    source = ROLLBACK_SH.read_text(encoding="utf-8")
    assert 'MANIFEST="${1:-}"' in source
    assert "exit 2" in source, "a missing argument must be a usage error, not a default"
