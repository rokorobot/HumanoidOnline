#!/usr/bin/env python3
"""WS8.7 — provider-neutral database backup (the PRIMARY recovery path).

Three layers were agreed for WS8.7; this is the first and the only one we own:

  1. PRIMARY   — this script: a nightly `pg_dump -Fc` copied OFF the box.
  2. SECONDARY — the hosting provider's automated whole-VPS backup.
  3. CHECKPOINT— a provider snapshot taken immediately before a change. These are
                 short-lived and are NEVER the recovery plan of record.

**No vendor is chosen or hard-coded here.** The off-box destination is supplied as
an arbitrary shell command template (`BACKUP_UPLOAD_COMMAND`) so the operator can
use rclone, rsync/ssh, aws s3, restic, b2 — anything — without a code change.

Fail-loud rules (WS8-L5):
  * In a strict environment (APP_ENV unset/staging/production) a MISSING
    `BACKUP_UPLOAD_COMMAND` is a hard error. A "backup" that only ever writes to
    the same disk as the database is not a backup, and silently degrading to one
    is exactly the failure this rule exists to prevent.
  * A failed dump or a failed upload exits non-zero and leaves the artifact in
    place, so the systemd timer / cron job reports failure instead of pretending.
  * Retention only ever deletes this script's own timestamped artifacts, and only
    AFTER a successful upload.

Install (documented path — nothing is installed automatically):

    # systemd timer, nightly at 03:20 with a randomised delay
    sudo install -m 0755 deploy/backup.py /usr/local/bin/humanoidonline-backup
    sudo tee /etc/systemd/system/humanoidonline-backup.service >/dev/null <<'UNIT'
    [Unit]
    Description=HumanoidOnline database backup
    After=docker.service
    [Service]
    Type=oneshot
    EnvironmentFile=/srv/humanoidonline/.env.production
    ExecStart=/usr/local/bin/humanoidonline-backup
    UNIT
    sudo tee /etc/systemd/system/humanoidonline-backup.timer >/dev/null <<'UNIT'
    [Unit]
    Description=Nightly HumanoidOnline database backup
    [Timer]
    OnCalendar=*-*-* 03:20:00
    RandomizedDelaySec=900
    Persistent=true
    [Install]
    WantedBy=timers.target
    UNIT
    sudo systemctl daemon-reload
    sudo systemctl enable --now humanoidonline-backup.timer

    # cron equivalent
    20 3 * * * root . /srv/humanoidonline/.env.production && \\
        /usr/local/bin/humanoidonline-backup >>/var/log/ho-backup.log 2>&1

Restore is rehearsed in WS8.8 / R30:

    pg_restore --clean --if-exists -d "$DATABASE_URL" <artifact>
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

#: Environments where an off-box destination may be omitted (local rehearsal).
RELAXED_APP_ENVS = frozenset({"development", "test"})

DEFAULT_BACKUP_DIR = "/srv/humanoidonline/backups"
DEFAULT_RETENTION_DAYS = 14
#: Marks artifacts this script owns, so retention can never delete anything else.
ARTIFACT_PREFIX = "humanoidonline-"
ARTIFACT_SUFFIX = ".dump"


class BackupConfigError(RuntimeError):
    """Configuration is missing or unusable. Never downgraded to a warning."""


class BackupCommandError(RuntimeError):
    """A dump or upload command failed."""


@dataclass(frozen=True)
class BackupConfig:
    database_url: str
    backup_dir: Path
    upload_command: str | None
    retention_days: int
    app_env: str

    @property
    def is_strict(self) -> bool:
        return self.app_env not in RELAXED_APP_ENVS


def load_config(env: dict[str, str] | None = None) -> BackupConfig:
    """Read configuration, refusing to run in a strict environment that has no
    off-box destination."""
    env = dict(os.environ if env is None else env)

    raw_app_env = (env.get("APP_ENV") or "").strip().lower()
    app_env = raw_app_env or "production"  # unset means production (WS8.2 / R7)

    database_url = (env.get("DATABASE_URL") or "").strip()
    if not database_url:
        raise BackupConfigError("DATABASE_URL is required to take a backup")

    upload_command = (env.get("BACKUP_UPLOAD_COMMAND") or "").strip() or None
    config = BackupConfig(
        database_url=database_url,
        backup_dir=Path((env.get("BACKUP_DIR") or DEFAULT_BACKUP_DIR).strip()),
        upload_command=upload_command,
        retention_days=int(env.get("BACKUP_RETENTION_DAYS") or DEFAULT_RETENTION_DAYS),
        app_env=app_env,
    )
    if config.is_strict and config.upload_command is None:
        raise BackupConfigError(
            "BACKUP_UPLOAD_COMMAND is required when APP_ENV="
            f'"{app_env}". A dump written only to the same host as the database '
            "is not a backup. Set it to any command that copies {path} off the "
            'box, e.g. \'rclone copy {path} remote:humanoidonline/backups\' or '
            "'aws s3 cp {path} s3://bucket/backups/'."
        )
    return config


def artifact_path(config: BackupConfig, now: datetime | None = None) -> Path:
    """Timestamped, collision-free artifact name (UTC, sortable)."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return config.backup_dir / f"{ARTIFACT_PREFIX}{stamp}{ARTIFACT_SUFFIX}"


def dump_command(config: BackupConfig, target: Path) -> list[str]:
    """`pg_dump` in the custom format — compressed and restorable selectively.

    SQLAlchemy's "+psycopg" driver token is not valid libpq syntax, so it is
    stripped; the rest of the URL is passed through untouched.
    """
    url = config.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return ["pg_dump", "--format=custom", "--no-owner", "--no-acl",
            "--file", str(target), url]


def upload_command(config: BackupConfig, target: Path) -> list[str]:
    """Render the operator's own command. `{path}` is substituted; if the template
    omits it the artifact path is appended, so a bare `rclone copy … remote:` still
    works."""
    if not config.upload_command:
        raise BackupConfigError("no BACKUP_UPLOAD_COMMAND configured")
    # Split the TEMPLATE first, then substitute the path into the resulting
    # argument list. Splitting after substitution would let a path containing
    # spaces (or a Windows-style separator) be re-tokenised or escape-mangled.
    parts = shlex.split(config.upload_command)
    if any("{path}" in part for part in parts):
        return [part.replace("{path}", str(target)) for part in parts]
    return [*parts, str(target)]


def prune(config: BackupConfig, now: datetime | None = None) -> list[Path]:
    """Delete this script's own artifacts older than the retention window."""
    if config.retention_days <= 0 or not config.backup_dir.is_dir():
        return []
    cutoff = (now or datetime.now(UTC)).timestamp() - config.retention_days * 86400
    removed: list[Path] = []
    for path in sorted(config.backup_dir.glob(f"{ARTIFACT_PREFIX}*{ARTIFACT_SUFFIX}")):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path)
    return removed


def _run(command: list[str], what: str) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        # stderr can carry a connection string; report the failure, not the payload.
        raise BackupCommandError(
            f"{what} failed with exit code {result.returncode} "
            f"(command: {command[0]})"
        )


def run_backup(config: BackupConfig, now: datetime | None = None) -> Path:
    """Dump, upload, then prune. Any failure raises and leaves the artifact."""
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    target = artifact_path(config, now)

    _run(dump_command(config, target), "pg_dump")
    if not target.exists() or target.stat().st_size == 0:
        raise BackupCommandError(f"pg_dump produced no output at {target}")

    if config.upload_command:
        _run(upload_command(config, target), "off-box upload")
        # Retention runs ONLY after a successful upload — otherwise a broken
        # destination would quietly erode the local copies too.
        prune(config, now)
    return target


def main(argv: list[str] | None = None) -> int:
    try:
        config = load_config()
        target = run_backup(config)
    except (BackupConfigError, BackupCommandError) as exc:
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"backup ok: {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
