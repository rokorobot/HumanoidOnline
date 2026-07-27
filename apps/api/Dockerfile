# syntax=docker/dockerfile:1.7
#
# WS8.7 / R26 — production image for the singleton FastAPI application.
#
# Build context is the REPOSITORY ROOT, because the image carries both the
# application (`apps/api/app`) and the governed migration set (`db/`) — the
# `migrate` service in docker-compose.prod.yml runs `db/bootstrap.py` from this
# same image, so there is exactly ONE bootstrap path (WS8.2 / R10, gap D6).
#
# Reproducibility (R26): dependencies come from the committed `uv.lock`
# (`--frozen`), and the base image is a build ARG so the deployment pins it to an
# immutable DIGEST without editing this file:
#
#   docker build \
#     --build-arg PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:<digest> \
#     -f apps/api/Dockerfile -t humanoidonline-api:<git-sha> .
#
# The resolved digest and the built image digest are recorded in the R26
# attestation artifact (docs/15). Digests are deliberately NOT hard-coded here:
# a fabricated or stale digest is worse than an explicit deployment-time pin.
ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# ---------------------------------------------------------------- builder ----
FROM ${PYTHON_IMAGE} AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir uv==0.5.29

WORKDIR /srv/api

# Only the lock inputs, so dependency resolution caches independently of source.
COPY apps/api/pyproject.toml apps/api/uv.lock ./
# --frozen: fail rather than silently re-resolving. --no-dev: pytest/ruff are not
# production dependencies.
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------- runtime ----
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/srv/api/.venv/bin:$PATH" \
    # The application verifies migration state at startup (WS8.2 / R9).
    MIGRATIONS_DIR=/srv/db/migrations

WORKDIR /srv/api

COPY --from=builder /srv/api/.venv /srv/api/.venv
COPY apps/api/app /srv/api/app
# Governed migrations + bootstrap, shared with the `migrate` service.
COPY db /srv/db

# Never run as root.
RUN groupadd --system app && useradd --system --gid app --home /srv app \
    && chown -R app:app /srv
USER app

EXPOSE 8000

# Liveness only (no dependencies) — readiness is /ready and is checked by the
# proxy. No curl in the slim image, so use the interpreter we already have.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

# DEP P1 — `--no-proxy-headers` is load-bearing. If uvicorn interpreted
# forwarding headers itself it would rewrite `request.client.host` BEFORE
# `app.security.client_ip.resolve_client_ip()` runs, collapsing the trust anchor
# and letting a client-supplied X-Forwarded-For become truth. Our own resolver
# stays the single authority. Never set FORWARDED_ALLOW_IPS=*.
# DEP P2 — exactly one worker: a singleton FastAPI application instance, which is
# what keeps the process-local abuse-control state (P3) valid.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--no-proxy-headers"]
