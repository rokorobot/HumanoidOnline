"""WS8.7 — the provider-neutral backup path (primary DB recovery).

`deploy/backup.py` is a standalone operator script (stdlib only, no app imports),
so it is loaded by path rather than imported as a package.

What matters here is not that a backup "runs" but that it cannot silently become
a non-backup:

  * it must work with the FROZEN topology — Postgres publishes no host port, so
    the dump runs inside the db container and is streamed to the host; a
    host-side `pg_dump -h db` would require opening the database up;
  * no credential may appear in a process argument;
  * a strict environment with no off-box destination must FAIL;
  * a failed dump must never be promoted to a finished-looking artifact, and a
    failed upload must FAIL while keeping what it has;
  * retention must never delete anything it did not write — nor delete local
    copies when the upload it depends on did not succeed.
"""
from __future__ import annotations

import importlib.util
import os
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
    "BACKUP_DIR": "/srv/backups",
    "BACKUP_UPLOAD_COMMAND": "rclone copy {path} remote:humanoidonline/backups",
    "BACKUP_COMPOSE_FILE": "/srv/humanoidonline/docker-compose.prod.yml",
    "BACKUP_COMPOSE_ENV_FILE": "/srv/humanoidonline/.env.production",
    "BACKUP_COMPOSE_PROJECT": "humanoidonline",
}


def _cfg(**overrides):
    env = {**BASE_ENV, **overrides}
    return backup.load_config({k: v for k, v in env.items() if v is not None})


def _fake_docker(*, dump_rc: int = 0, upload_rc: int = 0, payload: bytes = b"PGDMPfake"):
    """Stand in for `subprocess.run`, recording calls.

    The real dump writes BINARY STDOUT into an open file handle, so the fake has
    to do the same — that is the behaviour under test.
    """
    calls: list[list[str]] = []

    def run(cmd, **kwargs):  # noqa: ANN001, ANN003
        calls.append(cmd)

        class Result:
            stdout = ""
            stderr = ""
            returncode = 0

        if cmd[0] == "docker":
            sink = kwargs.get("stdout")
            if sink is not None and payload:
                sink.write(payload)
            Result.returncode = dump_rc
        else:
            Result.returncode = upload_rc
        return Result()

    return run, calls


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


def test_compose_settings_are_configurable_and_default_to_the_deployment_root() -> None:
    config = backup.load_config({"APP_ENV": "development"})
    assert config.compose_file == backup.DEFAULT_COMPOSE_FILE
    assert config.compose_env_file == backup.DEFAULT_COMPOSE_ENV_FILE
    assert config.compose_project == backup.DEFAULT_COMPOSE_PROJECT
    assert config.db_service == "db"

    custom = _cfg(
        APP_ENV="development",
        BACKUP_COMPOSE_FILE="/opt/ho/compose.yml",
        BACKUP_COMPOSE_ENV_FILE="/opt/ho/env",
        BACKUP_COMPOSE_PROJECT="other",
        BACKUP_DB_SERVICE="database",
    )
    assert custom.compose_file == "/opt/ho/compose.yml"
    assert custom.compose_env_file == "/opt/ho/env"
    assert custom.compose_project == "other"
    assert custom.db_service == "database"


# --------------------------------------------------------------------------- #
# The dump runs INSIDE the container, with no credential in any argument
# --------------------------------------------------------------------------- #
def test_dump_runs_pg_dump_inside_the_db_container_over_compose_exec() -> None:
    """The frozen topology publishes no Postgres port, so there is no host-side
    `pg_dump -h db:5432` to fall back to — and adding one would mean exposing the
    database."""
    cmd = backup.dump_command(_cfg(APP_ENV="production"))
    assert cmd[:2] == ["docker", "compose"]
    assert "--env-file" in cmd and "/srv/humanoidonline/.env.production" in cmd
    assert "-f" in cmd and "/srv/humanoidonline/docker-compose.prod.yml" in cmd
    assert cmd[cmd.index("-p") + 1] == "humanoidonline"
    exec_at = cmd.index("exec")
    # -T: no TTY allocation. With one, docker would corrupt the binary stream.
    assert cmd[exec_at + 1] == "-T"
    assert cmd[exec_at + 2] == "db"
    assert cmd[exec_at + 3 : exec_at + 5] == ["sh", "-c"]
    assert "5432" not in " ".join(cmd), "the database port is never addressed"


def test_dump_uses_the_container_environment_and_never_a_credential_argument() -> None:
    config = _cfg(APP_ENV="production")
    cmd = backup.dump_command(config)
    script = cmd[-1]
    # ONE argument to `sh -c`, expanded by the CONTAINER's shell from the
    # container's own environment — not by the host, and not from DATABASE_URL.
    assert script.count("pg_dump") == 1
    assert '--username "$POSTGRES_USER"' in script
    assert '--dbname "$POSTGRES_DB"' in script
    assert "--format=custom" in script

    joined = " ".join(cmd)
    assert "postgresql://" not in joined and "+psycopg" not in joined
    assert "PGPASSWORD" not in joined
    assert "password" not in joined.lower()


def test_the_script_never_reads_database_url_at_all() -> None:
    """The password lives in DATABASE_URL; the safest handling is not to touch it.

    Only the module docstring may mention it (to say why it is not used)."""
    body = BACKUP_PY.read_text(encoding="utf-8").split('"""')[2]
    assert "DATABASE_URL" not in body


# --------------------------------------------------------------------------- #
# Command construction
# --------------------------------------------------------------------------- #
def test_artifact_name_is_timestamped_and_sortable() -> None:
    config = _cfg(APP_ENV="production")
    a = backup.artifact_path(config, datetime(2026, 7, 28, 3, 20, 0, tzinfo=UTC))
    b = backup.artifact_path(config, datetime(2026, 7, 29, 3, 20, 0, tzinfo=UTC))
    assert a.name == "humanoidonline-20260728T032000Z.dump"
    assert a.parent == pathlib.Path("/srv/backups")
    assert a.name < b.name, "names must sort chronologically"
    # A path with a space must survive intact through the upload command.
    spaced = _cfg(APP_ENV="production", BACKUP_DIR="/srv/my backups")
    cmd = backup.upload_command(spaced, backup.artifact_path(spaced))
    assert str(backup.artifact_path(spaced)) in cmd


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
# Execution: atomic promotion, loud failures, conservative retention
# --------------------------------------------------------------------------- #
def test_successful_backup_promotes_atomically_then_uploads_then_prunes(
    tmp_path, monkeypatch
) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path),
                  BACKUP_RETENTION_DAYS="14")
    run, calls = _fake_docker()
    monkeypatch.setattr(backup.subprocess, "run", run)

    target = backup.run_backup(config)

    assert target.exists() and target.read_bytes() == b"PGDMPfake"
    assert target.suffix == ".dump"
    assert list(tmp_path.glob("*.part")) == [], "the temporary file must be gone"
    assert [c[0] for c in calls] == ["docker", "rclone"], "upload follows the dump"


def test_a_failed_dump_is_never_promoted_but_is_kept_as_evidence(
    tmp_path, monkeypatch
) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path))
    run, calls = _fake_docker(dump_rc=1, payload=b"PGDMPtrunc")
    monkeypatch.setattr(backup.subprocess, "run", run)

    with pytest.raises(backup.BackupCommandError) as exc:
        backup.run_backup(config)

    assert "pg_dump" in str(exc.value)
    assert len(calls) == 1, "upload must not run after a failed dump"
    assert list(tmp_path.glob(f"*{backup.ARTIFACT_SUFFIX}")) == [], (
        "a failed dump must not leave anything that looks like a finished backup"
    )
    partials = list(tmp_path.glob("*.part"))
    assert len(partials) == 1, "the incomplete output is preserved for diagnosis"


def test_output_that_is_not_a_pg_dump_archive_is_not_promoted(
    tmp_path, monkeypatch
) -> None:
    """A zero exit code is not proof: `compose exec` can succeed while emitting
    something else entirely (a warning, an empty stream)."""
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path))
    run, calls = _fake_docker(payload=b"service db is not running")
    monkeypatch.setattr(backup.subprocess, "run", run)

    with pytest.raises(backup.BackupCommandError) as exc:
        backup.run_backup(config)

    assert "not a custom-format pg_dump archive" in str(exc.value)
    assert len(calls) == 1, "nothing may be uploaded"
    assert list(tmp_path.glob(f"*{backup.ARTIFACT_SUFFIX}")) == []


def test_an_empty_dump_is_not_promoted(tmp_path, monkeypatch) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path))
    run, _ = _fake_docker(payload=b"")
    monkeypatch.setattr(backup.subprocess, "run", run)
    with pytest.raises(backup.BackupCommandError) as exc:
        backup.run_backup(config)
    assert "no output" in str(exc.value)


def test_failed_upload_raises_and_keeps_the_local_artifact(tmp_path, monkeypatch) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path))
    run, calls = _fake_docker(upload_rc=1)
    monkeypatch.setattr(backup.subprocess, "run", run)

    with pytest.raises(backup.BackupCommandError) as exc:
        backup.run_backup(config)

    assert "upload" in str(exc.value)
    # The dump is NOT deleted — a failed off-box copy must not also lose the copy
    # we do have.
    kept = list(tmp_path.glob(f"*{backup.ARTIFACT_SUFFIX}"))
    assert len(kept) == 1 and kept[0].read_bytes() == b"PGDMPfake"
    assert [c[0] for c in calls] == ["docker", "rclone"]


def test_retention_does_not_run_when_the_upload_failed(tmp_path, monkeypatch) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path),
                  BACKUP_RETENTION_DAYS="7")
    old = tmp_path / "humanoidonline-20200101T000000Z.dump"
    old.write_bytes(b"PGDMPold")
    ancient = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
    os.utime(old, (ancient, ancient))

    run, _ = _fake_docker(upload_rc=1)
    monkeypatch.setattr(backup.subprocess, "run", run)
    with pytest.raises(backup.BackupCommandError):
        backup.run_backup(config)

    assert old.exists(), (
        "retention must not erode local copies while the off-box destination is "
        "broken — that is when they matter most"
    )


def test_prune_only_touches_its_own_old_artifacts(tmp_path) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path),
                  BACKUP_RETENTION_DAYS="7")
    old = tmp_path / "humanoidonline-20200101T000000Z.dump"
    recent = tmp_path / "humanoidonline-20991231T000000Z.dump"
    foreign = tmp_path / "someone-elses-database.dump"
    partial = tmp_path / "humanoidonline-20200101T000000Z.dump.part"
    for path in (old, recent, foreign, partial):
        path.write_bytes(b"x")
    ancient = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
    for path in (old, foreign, partial):
        os.utime(path, (ancient, ancient))

    removed = backup.prune(config)
    assert removed == [old]
    assert recent.exists()
    assert foreign.exists(), "retention must never delete files it did not write"
    assert partial.exists(), "an incomplete dump is evidence, not a stale artifact"


def test_retention_disabled_deletes_nothing(tmp_path) -> None:
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(tmp_path),
                  BACKUP_RETENTION_DAYS="0")
    assert backup.prune(config) == []


# --------------------------------------------------------------------------- #
# Permissions — a dump is a full copy of the database
# --------------------------------------------------------------------------- #
def test_directory_and_artifacts_are_created_restrictively(tmp_path, monkeypatch) -> None:
    """0700 directory, 0600 artifacts. Asserted through the calls so it holds on
    every platform the gates run on; the real mode is checked below on POSIX."""
    target_dir = tmp_path / "backups"
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(target_dir))
    run, _ = _fake_docker()
    monkeypatch.setattr(backup.subprocess, "run", run)

    chmods: list[tuple[str, int]] = []
    real_chmod = os.chmod
    monkeypatch.setattr(
        backup.os, "chmod",
        lambda path, mode: (chmods.append((str(path), mode)), real_chmod(path, mode))[0],
    )
    opens: list[int] = []
    real_open = os.open
    monkeypatch.setattr(
        backup.os, "open",
        lambda path, flags, mode=0o777: (opens.append(mode), real_open(path, flags, mode))[1],
    )

    target = backup.run_backup(config)

    assert (str(target_dir), 0o700) in chmods, "the backup directory must be 0700"
    assert (str(target), 0o600) in chmods, "the promoted artifact must be 0600"
    assert opens == [0o600], "the temporary file is created 0600 from the start"


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_real_modes_are_restrictive_on_posix(tmp_path, monkeypatch) -> None:
    import stat

    target_dir = tmp_path / "backups"
    config = _cfg(APP_ENV="production", BACKUP_DIR=str(target_dir))
    run, _ = _fake_docker()
    monkeypatch.setattr(backup.subprocess, "run", run)

    target = backup.run_backup(config)

    assert stat.S_IMODE(target_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


# --------------------------------------------------------------------------- #
# The operator documentation is part of the deliverable
# --------------------------------------------------------------------------- #
def test_install_path_is_documented() -> None:
    """The timer/cron installation must be written down, not folklore."""
    source = BACKUP_PY.read_text(encoding="utf-8")
    for token in ("systemd", "OnCalendar", "cron", "UMask=0077"):
        assert token in source, f"installation docs missing: {token}"


def test_restore_is_documented_inside_the_container_and_into_a_scratch_database() -> None:
    """`pg_restore -d "$DATABASE_URL"` from the host cannot work here (no port, and
    the SQLAlchemy URL is not libpq syntax) — and restoring over the live database
    is not a rehearsal, it is an outage."""
    source = BACKUP_PY.read_text(encoding="utf-8")
    assert "pg_restore" in source
    assert "createdb" in source and "dropdb" in source, "scratch database lifecycle"
    assert "scratch" in source.lower()
    block = source.split("# 2. restore the artifact")[1].split("# 3.")[0]
    assert "exec -T db" in block, "the restore runs inside the pinned db container"
    assert "pg_restore" in block and '"$POSTGRES_USER"' in block
    assert "DATABASE_URL" not in block
