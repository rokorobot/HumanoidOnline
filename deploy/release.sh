#!/usr/bin/env bash
# WS8.7 / R26 — the SUPPORTED production build + deploy path.
#
# Run this on the VPS instead of hand-typing `docker build` / `docker compose up`:
# it enforces the reproducibility promise BEFORE anything is pulled, built or
# started. Ad-hoc commands can still be run by an operator, but only this path is
# supported and only this path is what the R26 attestation records.
#
#   sudo ENV_FILE=/srv/humanoidonline/.env.production deploy/release.sh
#
# Order is load-bearing:
#   1. pin preflight   — every base image must be an immutable digest
#   2. build           — both images, tagged with RELEASE_SHA
#   3. up              — compose, reading the same env file
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

ENV_FILE="${ENV_FILE:-$ROOT/.env.production}"
# Deliberately NOT named COMPOSE_FILE: that name is meaningful to docker compose
# itself, and this script sources the env file into its own environment.
COMPOSE_PATH="${COMPOSE_PATH:-$ROOT/docker-compose.prod.yml}"

[ -r "$ENV_FILE" ] || { echo "release: cannot read $ENV_FILE" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# 1. PIN PREFLIGHT — before any pull, build or up.
#
# A non-empty value is not a pinned value: `PYTHON_IMAGE=python:3.12-slim` would
# otherwise sail through the Dockerfile's no-default ARG and compose's `:?`.
# --------------------------------------------------------------------------- #
python3 "$HERE/preflight.py" --env-file "$ENV_FILE"

# Values with spaces must be quoted in the env file (see .env.production.example).
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${RELEASE_SHA:?RELEASE_SHA is required — the exact commit being released}"
: "${NEXT_PUBLIC_SITE_URL:?NEXT_PUBLIC_SITE_URL is required at build time (R8)}"

# --------------------------------------------------------------------------- #
# 2. BUILD — both images from the repository root, pinned bases only.
# --------------------------------------------------------------------------- #
docker build \
  --build-arg PYTHON_IMAGE="$PYTHON_IMAGE" \
  -f "$ROOT/apps/api/Dockerfile" \
  -t "humanoidonline-api:$RELEASE_SHA" \
  "$ROOT"

docker build \
  --build-arg NODE_IMAGE="$NODE_IMAGE" \
  --build-arg NEXT_PUBLIC_SITE_URL="$NEXT_PUBLIC_SITE_URL" \
  -f "$ROOT/apps/web/Dockerfile" \
  -t "humanoidonline-web:$RELEASE_SHA" \
  "$ROOT"

# Record what was actually built — the rollback unit is a DIGEST, never a tag.
docker image inspect --format '{{.RepoTags}} {{.Id}}' \
  "humanoidonline-api:$RELEASE_SHA" "humanoidonline-web:$RELEASE_SHA"

# --------------------------------------------------------------------------- #
# 3. UP — compose reads the SAME env file, so the runtime pins are the ones the
#    preflight just validated.
# --------------------------------------------------------------------------- #
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_PATH" up -d

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_PATH" ps
