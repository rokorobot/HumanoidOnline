"""WS8.7 — the provider-neutral backup path (primary DB recovery).

`deploy/backup.py` is a standalone operator script (stdlib only, no app imports),
so it is loaded by path rather than imported as a package.

What matters here is not that a backup "runs" but that it cannot silently become
a non-backup: a strict environment with no off-box destination must FAIL, a
failed upload must FAIL, and retention must never delete anything it did not
write — nor delete local copies when the upload it depends on did not succeed.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import UTC, datetime

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
BACKUP_PY = ROOT / "deploy" / "backup.py"


def _load():
    spec = importlib.util.spec_from_file_location("ho_backup", BACKUP_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register BEFORE exec: the module's frozen dataclass resolves its annotations
    # through sys.modules, which fails for an unregistered ad-hoc module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


backup = _load()

BASE_ENV = {
    "DATABASE_URL": "postgresql+psycopg://humanoid:pw@db:5432/humanoidonline",
    "BACKUP_DIR": "/srv/backups",
    "BACKUP_UPLOAD_COMMAND": "rclone copy {path} remote:humanoidonline/backups",
}


def _cfg(**overrides):
    env = {**BASE_ENV, **overrides}
    return backup.load_config({k: v for k, v in env.items() if v is not None})


# --------------------------------------------------------------------------- #
# Fail-closed configuration (WS8-L5)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("app_env", ["production", "staging", ""])
def test_strict_environment_requires_an_offbox_destination(app_env) -> None:
    """A dump written only to the database's own host is not a backup."""
    with pytest.raises(backup.BackupConfigError) as exc:
        _cfg(APP_ENV=app_env, BACKUP_UPLOAD_COMMAND=None)
    assert "BACKUP_UPLOAD_COMMAND is required" in str(exc.value)


def test_unset_app_env_is_treated_as_production() -> None:
    with pytest.raises(backup.BackupConfigError):
        _cfg(BACKUP_UPLOAD_COMMAND=None)  # no APP_ENV at all


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_relaxed_environments_may_rehearse_without_a_destination(app_env) -> None:
    config = _cfg(APP_ENV=app_env, BACKUP_UPLOAD_COMMAND=None)
    assert config.upload_command is None
    assert config.is_strict is False


def test_database_url_is_required() -> None:
    with pytest.raises(backup.BackupConfigError):
        _cfg(APP_ENV="development", DATABASE_URL=None)


# --------------------------------------------------------------------------- #
# Command construction
# --------------------------------------------------------------------------- #
def test_dump_command_is_custom_format_and_strips_the_sqlalchemy_driver() -> None:
    config = _cfg(APP_ENV="production")
    target = pathlib.Path("/srv/backups/x.dump")
    cmd = backup.dump_command(config, target)
    assert cmd[0] == "pg_dump"
    assert "--format=custom" in cmd
    assert str(target) in cmd
    # libpq does not understand SQLAlchemy's "+psycopg" token.
    assert cmd[-1] == "postgresql://humanoid:pw@db:5432/humanoidonline"
    assert "+psycopg" not in " ".join(cmd)


def test_artifact_name_is_timestamped_and_sortable() -> None:
    config = _cfg(APP_ENV="production")
    a = backup.artifact_path(config, datetime(2026, 7, 28, 3, 20, 0, tzinfo=UTC))
    b = backup.artifact_path(config, datetime(2026, 7, 29, 3, 20, 0, tzinfo=UTC))
    assert a.name == "humanoidonline-20260728T032000Z.dump"
    assert a.parent == pathlib.Path("/srv/backups")
    # A path with a space must survive intact through the upload command.
    spaced = _cfg(APP_ENV="production", BACKUP_DIR="/srv/my backups")
    cmd = backup.upload_command(spaced, backup.artifact_path(spaced))
    assert str(backup.artifact_path(spaced)) in cmd
    assert a.name < b.name, "names must sort chronologically"


def test_upload_command_substitutes_the_path_placeholder() -> None:
    config = _cfg(APP_ENV="production")
    target = pathlib.Path("/srv/backups/x.dump")
    cmd = backup.upload_command(config, target)
    assert cmd == ["rclone", "copy", str(target), "remote:humanoidonline/backups"]


def test_upload_command_appends_the_path_when_no_placeholder_is_used() -> None:
    config = _cfg(APP_ENV="production",
                  BACKUP_UPLOAD_COMMAND="aws s3 cp --only-show-errors")
    target = pathlib.Path("/srv/backups/x.dump")
    cmd = backup.upload_command(config, target)
    assert cmd[:2] == ["aws", "s3"]
    assert cmd[-1] == str(target)


def test_upload_command_is_vendor_neutral() -> None:
    """No provider is hard-coded anywhere in the script."""
    source = BACKUP_PY.read_text(encoding="utf-8")
    directives = [
        line for line in source.splitlines()
        if not line.lstrip().startswith("#") and '"""' not in line
    ]
    body = "\n".join(directives).lower()
    for vendor in ("hostinger", "s3.amazonaws", "backblaze", "digitalocean"):
        assert vendor not in body, f"{vendor} must not be hard-coded"


# --------------------------------------------------------------------------- #
# Execution: failures are loud, retention is conservative
# --------------------------------------------------------------------------- #
def test_failed_dump_raises_and_uploads_nothing(tmp_path, monkeypatch) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path))
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text):  # noqa: ANN001
        calls.append(cmd)

        class R:
            returncode = 1
            stdout = ""
            stderr = "connection refused"

        return R()

    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    with pytest.raises(backup.BackupCommandError) as exc:
        backup.run_backup(config)
    assert "pg_dump" in str(exc.value)
    assert len(calls) == 1, "upload must not run after a failed dump"


def test_failed_upload_raises_and_keeps_the_local_artifact(tmp_path, monkeypatch) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path))
    created: dict[str, pathlib.Path] = {}

    def fake_run(cmd, capture_output, text):  # noqa: ANN001
        class R:
            stdout = ""
            stderr = ""
            returncode = 0

        if cmd[0] == "pg_dump":
            target = pathlib.Path(cmd[cmd.index("--file") + 1])
            target.write_bytes(b"PGDMP-fake")
            created["target"] = target
            return R()
        R.returncode = 1  # the upload fails
        return R()

    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    with pytest.raises(backup.BackupCommandError) as exc:
        backup.run_backup(config)
    assert "upload" in str(exc.value)
    # The dump is NOT deleted — a failed off-box copy must not also lose the copy
    # we do have.
    assert created["target"].exists()


def test_successful_backup_uploads_then_prunes(tmp_path, monkeypatch) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path),
                  BACKUP_RETENTION_DAYS="14")
    order: list[str] = []

    def fake_run(cmd, capture_output, text):  # noqa: ANN001
        order.append(cmd[0])
        if cmd[0] == "pg_dump":
            pathlib.Path(cmd[cmd.index("--file") + 1]).write_bytes(b"PGDMP-fake")

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    target = backup.run_backup(config)
    assert target.exists()
    assert order == ["pg_dump", "rclone"], "upload must follow the dump"


def test_prune_only_touches_its_own_old_artifacts(tmp_path) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path),
                  BACKUP_RETENTION_DAYS="7")
    old = tmp_path / "humanoidonline-20200101T000000Z.dump"
    recent = tmp_path / "humanoidonline-20991231T000000Z.dump"
    foreign = tmp_path / "someone-elses-database.dump"
    for path in (old, recent, foreign):
        path.write_bytes(b"x")
    import os
    ancient = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
    os.utime(old, (ancient, ancient))
    os.utime(foreign, (ancient, ancient))

    removed = backup.prune(config)
    assert removed == [old]
    assert recent.exists()
    assert foreign.exists(), "retention must never delete files it did not write"


def test_retention_disabled_deletes_nothing(tmp_path) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path),
                  BACKUP_RETENTION_DAYS="0")
    assert backup.prune(config) == []


def test_install_path_is_documented() -> None:
    """The timer/cron installation must be written down, not folklore."""
    source = BACKUP_PY.read_text(encoding="utf-8")
    for token in ("systemd", "OnCalendar", "cron", "pg_restore"):
        assert token in source, f"installation/restore docs missing: {token}"
