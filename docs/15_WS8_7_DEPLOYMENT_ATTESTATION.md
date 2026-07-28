# WS8.7 / R26 + R27 — deployment attestation checklist

> **STATUS: TEMPLATE — NOT ATTESTED.** This is the repeatable execution and
> evidence checklist for the two WS8.7 gates. Both are **[Attested]** by frozen
> contract (§9.7, WS8-L8): they require a **named human operator** and a dated
> evidence artifact captured against a **physically deployed** system.
>
> **Capability is not compliance.** The repository can prepare every artifact and
> an agent can run the probes and capture output, but **no agent may complete the
> record below**. Until a person does, `docs/13` must show R26 and R27 as
> **PENDING DEPLOYMENT / ATTESTATION**.

## Scope

- **R26** — deployment shape (§5.6) realized with explicit secrets, reproducible
  build, proxy-wired health/readiness, and **DEP P1–P5 bound** to the selected
  infrastructure (Hostinger KVM 4 · Ubuntu 24.04 · Docker/Compose).
- **R27** — the **network boundary physically realized** per DEP P4: admin on a
  separate protected listener, not publicly routable (B1 stage 2).

Stage 3 (the external negative probe, **R29**) belongs to WS8.8 and re-proves
this from outside the deployment. R26/R27 are not a substitute for it.

## Pre-flight (before first `up`)

- [ ] **Subnet collision check** — `ip route` and `docker network ls` / `inspect`
      confirm `172.30.0.0/24` is free. If not, choose another /24 **and** update
      `TRUSTED_PROXY_IPS` to the proxy's address on it.
- [ ] DNS: `humanoidonline.com` and `www.` resolve to the VPS **before** Caddy
      first starts (ACME issuance ordering).
- [ ] `.env.production` present, root-owned, `chmod 600`, every value filled.
- [ ] Host firewall default-deny inbound; only 22/80/443 allowed.

## Build (R26 — reproducibility)

Record the exact inputs and outputs; the rollback unit is an **image digest**,
never "rebuild an old tag".

Use the supported path — `deploy/release.sh` — rather than hand-typed commands:

```
sudo ENV_FILE=/srv/humanoidonline/.env.production deploy/release.sh
```

It runs `deploy/preflight.py` **first**, before anything is pulled, built or
started. All four pins are MANDATORY and, more than that, must be **immutable in
form**: required-ness (`:?`, an ARG with no default) only proves *non-empty*, and
`POSTGRES_IMAGE=postgres:16` is non-empty while meaning "whatever that tag points
at today". The preflight accepts `<image>@sha256:<64 lower-case hex>` (or a bare
`sha256:<64 hex>` image ID) and rejects `python:3.12-slim`, `node:20-bookworm-slim`,
`postgres:16`, `caddy:2` and every other mutable tag.

```
Release commit SHA:          ____________________
Base image pins used (all four REQUIRED, digest form):
  PYTHON_IMAGE               ____________________  (…@sha256:…)
  NODE_IMAGE                 ____________________  (…@sha256:…)
  POSTGRES_IMAGE             ____________________  (…@sha256:…)
  CADDY_IMAGE                ____________________  (…@sha256:…)
Built image digests:
  humanoidonline-api:<sha>   sha256:______________
  humanoidonline-web:<sha>   sha256:______________
Previous image digests retained for rollback:
  api  sha256:______________   web  sha256:______________
```

- [ ] `deploy/preflight.py` output captured: **"preflight ok: all four base images
      are pinned to a digest"**. (Sanity-check the gate itself once: temporarily
      set one pin to `postgres:16`, confirm the release **stops** with a
      `MUTABLE TAG` error and that **nothing was built or started**, then restore
      the digest.)
- [ ] Images built from the exact commit above with `npm ci` / `uv sync --frozen`.
- [ ] `docker compose -f docker-compose.prod.yml config` output captured.

## R26 evidence — deployment shape + DEP bound

- [ ] **Migration-before-app-start**: logs show `migrate` exiting 0 **before**
      `api` starts (`service_completed_successfully`).
- [ ] **Health/readiness**: `GET /health` → 200; `GET /ready` → 200.
- [ ] **Simulated dependency outage** (`docker compose stop db`, wait for one
      health interval — 10s — then measure at the PUBLIC surface):
      - [ ] `curl -o /dev/null -w '%{http_code}' https://<domain>/health` → **200**.
            Liveness must keep answering: it is what distinguishes "the API is
            gone" from "the API is up, its database is not". It is served through
            a separate, deliberately un-health-checked proxy path
            (`to_api_liveness` in `deploy/Caddyfile`).
      - [ ] `curl -o /dev/null -w '%{http_code}' https://<domain>/ready` →
            **non-2xx** (503 from the API, or 502 once Caddy has marked the
            upstream down — either proves the dependency is not being hidden).
      - [ ] `https://<domain>/api/...` also fails rather than serving from a
            known-broken upstream.
      - [ ] `docker compose start db`; within ~10s `/ready` returns to 200 and the
            upstream returns to rotation. `/health` never went down.
- [ ] **Ingress starts only after the app is healthy**: compose reports `caddy`
      starting after `api`/`web` are healthy, and `api` only after `migrate`
      exited 0.
- [ ] **Public HTTP→HTTPS redirect**: `curl -I http://humanoidonline.com/robots`
      → 301/308 to `https://`. Automatic HTTPS is deliberately NOT disabled.
- [ ] **TLS**: `curl -I https://humanoidonline.com` → valid certificate, and
      `Strict-Transport-Security` present.
- [ ] **www → apex**: `curl -I https://www.humanoidonline.com/robots` → **308**
      to the apex, path preserved.
- [ ] **P1 bound**: `TRUSTED_PROXY_IPS` equals Caddy's address on the production
      network; uvicorn runs `--no-proxy-headers`; `FORWARDED_ALLOW_IPS` unset.
- [ ] **P2/P3 bound**: exactly one `api` container, one worker, no replicas.
- [ ] **Database not public**: connection to `<public-ip>:5432` refused.
- [ ] **Secrets explicit**: no credential or hostname defaults in effect; the web
      tier refuses to start a governed read without `API_BASE_URL` (WS8-L5).

## R27 evidence — admin boundary realized

Assert the **invariant**, not a particular framework status code (SQLAdmin may
use a login/redirect flow rather than a literal 401).

- [ ] `curl -i https://humanoidonline.com/admin` → **404**.
- [ ] `curl -i https://humanoidonline.com/admin/statics/…` → **404**.
- [ ] `curl http://<public-ip>:8001/admin` → **refused/unreachable**.
- [ ] External port scan of the public IP shows **only 22/80/443**.
- [ ] Through `ssh -L 8001:127.0.0.1:8001 <vps>`, `http://127.0.0.1:8001/admin`
      is reachable.
- [ ] **Unauthenticated** access there returns **no admin data** (no model list,
      no records) — redirect or error both acceptable.
- [ ] **Wrong credentials** rejected; still **no admin data**.
- [ ] **Correct credentials** grant access.
- [ ] Admin **session cookie attributes** verified (HttpOnly / SameSite, and
      `Secure` behaviour over the plain-HTTP loopback tunnel) — carried-forward
      WS8.1 item recorded in `docs/13`.

## Backup / rollback readiness (rehearsed in WS8.8 / R30)

- [ ] **Primary — `deploy/backup.py` installed** as the systemd timer (or cron
      equivalent) documented in that file's header, **`UMask=0077`** set on the
      unit, and one run completed successfully.
- [ ] The dump ran **inside the `db` container** (`docker compose … exec -T db sh
      -c 'exec pg_dump …'`) and was streamed to the host. Postgres publishes no
      port, so a host-side `pg_dump -h db:5432` cannot work — and must not be
      made to work by exposing the database.
- [ ] **No credential in any process argument**: `ps` during a run shows no
      password and no `DATABASE_URL`; `pg_dump` reads `$POSTGRES_USER` /
      `$POSTGRES_DB` from the container's own environment.
- [ ] **Permissions**: `ls -ld $BACKUP_DIR` → `drwx------` (0700); `ls -l` on an
      artifact → `-rw-------` (0600).
- [ ] `BACKUP_UPLOAD_COMMAND` set to a real off-box destination, **quoted**
      (it contains spaces; systemd, compose and `sh` all end an unquoted value at
      whitespace). The script **refuses to run** in a strict environment without
      it, so an unset value is a hard failure rather than a local-only "backup".
      *(Vendor still an owner decision; the code is provider-neutral.)*
- [ ] `BACKUP_DIR`, `BACKUP_RETENTION_DAYS` and the `BACKUP_COMPOSE_*` settings
      match this deployment; retention verified to delete only this script's own
      timestamped artifacts, and only after a successful upload.
- [ ] **Atomic promotion observed**: an interrupted dump leaves only a `.part`
      file, never something that looks like a finished `.dump`.
- [ ] A dump has been **restored into a scratch database inside the container**
      (`createdb` → `pg_restore --no-owner --no-acl --dbname <scratch>` over
      stdin → row count → `dropdb`), exactly as documented in the header of
      `deploy/backup.py`. Never a host `pg_restore -d "$DATABASE_URL"`: that URL
      carries SQLAlchemy's `+psycopg` token, which is not libpq syntax, and the
      port is unreachable from the host in any case. Rehearsed for real in
      WS8.8 / R30.
- [ ] Provider automated backup active (**secondary**, whole-VPS recovery).
- [ ] Provider manual snapshot taken immediately before this deployment,
      understood to be a **temporary (~1-day) checkpoint**, never the recovery
      plan of record.
- [ ] Rollback path confirmed: previous image digests still present on the host.

## Attestation record (complete to PASS R26 / R27)

```
Operator (name / role):        ____________________________  (REQUIRED)
Date:                          ____________________________  (REQUIRED)
Exact release commit SHA:      ____________________________  (REQUIRED)
Image digests (api / web):     ____________________________
Infrastructure identity:       Hostinger KVM 4 · Ubuntu 24.04 · ______________
Evidence artifacts reviewed:   ____________________________
                               (compose config, ss -tlnp, ufw status, curl
                                transcripts, TLS check, health/ready captures)

R26 — deployment shape / DEP P1–P5 bound:      PASS / FAIL
R27 — admin boundary physically realized:      PASS / FAIL

Notes / exceptions:            ____________________________
Attestation:                   ____________________________
```

> Until this record is completed by a person, R26 and R27 are **PENDING**, and
> the Release Invariant Matrix must show them as such. WS8.7 delivers the
> deployment artifacts and the means to prove them; it cannot self-certify them.
