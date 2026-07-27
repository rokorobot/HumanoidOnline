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

```
Release commit SHA:          ____________________
Base image pins used:
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

- [ ] Images built from the exact commit above with `npm ci` / `uv sync --frozen`.
- [ ] `docker compose -f docker-compose.prod.yml config` output captured.

## R26 evidence — deployment shape + DEP bound

- [ ] **Migration-before-app-start**: logs show `migrate` exiting 0 **before**
      `api` starts (`service_completed_successfully`).
- [ ] **Health/readiness**: `GET /health` → 200; `GET /ready` → 200.
- [ ] **Readiness is real**: with the database stopped, `GET /ready` → **503**.
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

- [ ] Nightly `pg_dump -Fc` scheduled; **off-box destination configured**
      (owner decision — must be resolved before production activation).
- [ ] Hostinger automated backup active (secondary, whole-VPS recovery).
- [ ] Manual snapshot taken immediately before this deployment, understood to be
      a **temporary (~1-day) checkpoint**, never the recovery plan of record.
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
