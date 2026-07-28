#!/usr/bin/env python3
"""WS8.7 — provider-neutral database backup (the PRIMARY recovery path).

Three layers were agreed for WS8.7; this is the first and the only one we own:

  1. PRIMARY   — this script: a nightly `pg_dump -Fc` copied OFF the box.
  2. SECONDARY — the hosting provider's automated whole-VPS backup.
  3. CHECKPOINT— a provider snapshot taken immediately before a change. These are
                 short-lived and are NEVER the recovery plan of record.

**It runs pg_dump INSIDE the database container.** Postgres publishes no host
port (DEP: `db` has no `ports:`), so a host-side `pg_dump -h db` or
`-d "$DATABASE_URL"` cannot reach it — the frozen topology would have to be
opened up to make that work, which is precisely what must not happen for a
backup's convenience. Instead:

    docker compose --env-file … -f … exec -T db sh -c 'exec pg_dump …'

The dump is written to the container's STDOUT, captured on the host into a
`.part` file, and only then promoted atomically to its final timestamped name —
so a truncated or failed dump can never be mistaken for a complete artifact.

**No credential ever appears in a process argument.** `pg_dump` runs inside the
container and reads `$POSTGRES_USER` / `$POSTGRES_DB` from the environment that
container already has; `DATABASE_URL` (which embeds the password) is not used
here at all. Artifacts are written 0600 into a 0700 directory, and the systemd
unit sets `UMask=0077`.

**No vendor is chosen or hard-coded here.** The off-box destination is supplied
as an arbitrary shell command template (`BACKUP_UPLOAD_COMMAND`) so the operator
can use rclone, rsync/ssh, aws s3, restic, b2 — anything — without a code change.

Fail-loud rules (WS8-L5):
  * In a strict environment (APP_ENV unset/staging/production) a MISSING
    `BACKUP_UPLOAD_COMMAND` is a hard error. A "backup" that only ever writes to
    the same disk as the database is not a backup, and silently degrading to one
    is exactly the failure this rule exists to prevent.
  * A failed dump or a failed upload exits non-zero and PRESERVES what it has —
    the `.part` file after a failed dump (evidence, and never promotable), the
    promoted artifact after a failed upload — so the timer reports failure
    instead of pretending, and nothing that might be needed is thrown away.
  * Retention only ever deletes this script's own timestamped artifacts, and only
    AFTER a successful upload.

Install (documented path — nothing is installed automatically):

    # systemd timer, nightly at 03:20 with a randomised delay
    sudo install -m 0755 deploy/backup.py /usr/local/bin/humanoidonline-backup
    sudo tee /etc/systemd/system/humanoidonline-backup.service >/dev/null <<'UNIT'
    [Unit]
    Description=HumanoidOnline database backup
    After=docker.service
    Requires=docker.service
    [Service]
    Type=oneshot
    # Values containing spaces MUST be quoted in this file, e.g.
    #   BACKUP_UPLOAD_COMMAND="rclone copy {path} remote:humanoidonline/backups"
    EnvironmentFile=/srv/humanoidonline/.env.production
    # Dumps are database contents: no group/other access, ever.
    UMask=0077
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

    # cron equivalent (same quoting rule applies to the sourced file)
    20 3 * * * root umask 0077; . /srv/humanoidonline/.env.production && \\
        /usr/local/bin/humanoidonline-backup >>/var/log/ho-backup.log 2>&1

RESTORE — also inside the container, into a SCRATCH database first. Never
restore straight over the live database, and never with a host `pg_restore -d
"$DATABASE_URL"`: the SQLAlchemy `+psycopg` URL is not libpq syntax and the
port is not reachable from the host anyway. Rehearsed for real in WS8.8 / R30.

    C="docker compose --env-file /srv/humanoidonline/.env.production \\
        -f /srv/humanoidonline/docker-compose.prod.yml"
    S=restorecheck_$(date -u +%Y%m%d%H%M%S)

    # 1. scratch database, owned by the same role
    $C exec -T db sh -c 'exec createdb --username "$POSTGRES_USER" '"$S"

    # 2. restore the artifact into it (stdin — the file stays on the host)
    $C exec -T db sh -c 'exec pg_restore --no-owner --no-acl \\
        --username "$POSTGRES_USER" --dbname '"$S" < <artifact>

    # 3. prove it: the schema and its rows are really there
    $C exec -T db sh -c 'exec psql --username "$POSTGRES_USER" --dbname '"$S"' \\
        -c "select count(*) from humanoid.robot"'

    # 4. drop the scratch database
    $C exec -T db sh -c 'exec dropdb --username "$POSTGRES_USER" '"$S"

Promoting a verified restore to the live database is a deliberate, separate
operator action (stop the app, `--clean --if-exists` into the real database, or
rename), never something a backup script does.
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
DEFAULT_COMPOSE_FILE = "/srv/humanoidonline/docker-compose.prod.yml"
DEFAULT_COMPOSE_ENV_FILE = "/srv/humanoidonline/.env.production"
#: Matches `name:` in docker-compose.prod.yml.
DEFAULT_COMPOSE_PROJECT = "humanoidonline"
DEFAULT_DB_SERVICE = "db"

#: Marks artifacts this script owns, so retention can never delete anything else.
ARTIFACT_PREFIX = "humanoidonline-"
ARTIFACT_SUFFIX = ".dump"
#: Incomplete dumps carry this extra suffix and are never promoted.
PARTIAL_SUFFIX = ".part"

DIR_MODE = 0o700
FILE_MODE = 0o600

#: Every custom-format pg_dump starts with this magic. Checking it means a
#: successful exit code alone cannot promote a file that is not a dump.
PGDMP_MAGIC = b"PGDMP"

#: Runs INSIDE the db container: `$POSTGRES_USER` / `$POSTGRES_DB` are expanded
#: by the container's own shell from the container's own environment, so no
#: credential or database identity is ever passed as an argument from the host.
PG_DUMP_SH = (
    'exec pg_dump --format=custom --no-owner --no-acl '
    '--username "$POSTGRES_USER" --dbname "$POSTGRES_DB"'
)


class BackupConfigError(RuntimeError):
    """Configuration is missing or unusable. Never downgraded to a warning."""


class BackupCommandError(RuntimeError):
    """A dump or upload command failed."""


@dataclass(frozen=True)
class BackupConfig:
    backup_dir: Path
    upload_command: str | None
    retention_days: int
    app_env: str
    compose_file: str
    compose_env_file: str
    compose_project: str | None
    db_service: str

    @property
    def is_strict(self) -> bool:
        return self.app_env not in RELAXED_APP_ENVS


def load_config(env: dict[str, str] | None = None) -> BackupConfig:
    """Read configuration, refusing to run in a strict environment that has no
    off-box destination."""
    env = dict(os.environ if env is None else env)

    raw_app_env = (env.get("APP_ENV") or "").strip().lower()
    app_env = raw_app_env or "production"  # unset means production (WS8.2 / R7)

    def _value(key: str, default: str) -> str:
        return (env.get(key) or "").strip() or default

    upload_command = (env.get("BACKUP_UPLOAD_COMMAND") or "").strip() or None
    config = BackupConfig(
        backup_dir=Path(_value("BACKUP_DIR", DEFAULT_BACKUP_DIR)),
        upload_command=upload_command,
        retention_days=int(env.get("BACKUP_RETENTION_DAYS") or DEFAULT_RETENTION_DAYS),
        app_env=app_env,
        compose_file=_value("BACKUP_COMPOSE_FILE", DEFAULT_COMPOSE_FILE),
        compose_env_file=_value("BACKUP_COMPOSE_ENV_FILE", DEFAULT_COMPOSE_ENV_FILE),
        compose_project=(env.get("BACKUP_COMPOSE_PROJECT") or "").strip()
        or DEFAULT_COMPOSE_PROJECT,
        db_service=_value("BACKUP_DB_SERVICE", DEFAULT_DB_SERVICE),
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


def partial_path(target: Path) -> Path:
    """Where the dump is written before it earns its final name."""
    return target.with_name(target.name + PARTIAL_SUFFIX)


def dump_command(config: BackupConfig) -> list[str]:
    """`pg_dump -Fc` inside the RUNNING db container, writing to stdout.

    `exec -T` disables TTY allocation, without which docker would corrupt the
    binary stream. The database is not reachable from the host by design, so
    there is no host-side alternative to reintroduce here.
    """
    command = [
        "docker", "compose",
        "--env-file", config.compose_env_file,
        "-f", config.compose_file,
    ]
    if config.compose_project:
        command += ["-p", config.compose_project]
    return [*command, "exec", "-T", config.db_service, "sh", "-c", PG_DUMP_SH]


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
    """Delete this script's own artifacts older than the retention window.

    `.part` files are NOT swept: an incomplete dump is evidence of a failure and
    is removed by the operator who read it.
    """
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


def _run_to_file(command: list[str], destination: Path, what: str) -> None:
    """Run `command`, streaming its binary stdout into `destination` (0600)."""
    handle = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        with os.fdopen(handle, "wb") as sink:
            result = subprocess.run(command, stdout=sink, stderr=subprocess.PIPE)
    except OSError as exc:  # pragma: no cover - filesystem failure
        raise BackupCommandError(f"{what} could not write {destination}: {exc}") from exc
    os.chmod(destination, FILE_MODE)  # umask cannot loosen it, but be explicit
    if result.returncode != 0:
        raise BackupCommandError(
            f"{what} failed with exit code {result.returncode} "
            f"(command: {command[0]}); incomplete output kept at {destination}"
        )


def run_backup(config: BackupConfig, now: datetime | None = None) -> Path:
    """Dump to a `.part` file, verify it, promote it atomically, upload, prune."""
    config.backup_dir.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    os.chmod(config.backup_dir, DIR_MODE)  # existing directories too

    target = artifact_path(config, now)
    partial = partial_path(target)

    _run_to_file(dump_command(config), partial, "pg_dump")

    if not partial.exists() or partial.stat().st_size == 0:
        raise BackupCommandError(f"pg_dump produced no output at {partial}")
    with partial.open("rb") as stream:
        if stream.read(len(PGDMP_MAGIC)) != PGDMP_MAGIC:
            raise BackupCommandError(
                f"{partial} is not a custom-format pg_dump archive; it was NOT "
                "promoted (a zero-exit command can still emit the wrong thing)"
            )

    # Atomic promotion: readers and retention only ever see complete artifacts.
    os.replace(partial, target)
    os.chmod(target, FILE_MODE)

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
