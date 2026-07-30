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
#   1. preflight       — pins immutable, RELEASE_SHA is the clean checked-out
#                        commit, off-box backup destination usable. ALL of it
#                        before the first pull, build or up.
#   2. build           — both images, tagged with RELEASE_SHA
#   3. manifest        — durable record of what was built (image IDs), written
#                        outside the repository; tags re-verified against it
#   4. up              — compose, reading the same env file
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

ENV_FILE="${ENV_FILE:-$ROOT/.env.production}"
# Deliberately NOT named COMPOSE_FILE: that name is meaningful to docker compose
# itself, and this script sources the env file into its own environment.
COMPOSE_PATH="${COMPOSE_PATH:-$ROOT/docker-compose.prod.yml}"

[ -r "$ENV_FILE" ] || { echo "release: cannot read $ENV_FILE" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# 1. PREFLIGHT — all three gates, before any pull, build or up.
#
#   pins   — a non-empty value is not a pinned value: `PYTHON_IMAGE=python:3.12-slim`
#            would otherwise sail through the no-default ARG and compose's `:?`.
#   source — RELEASE_SHA must be a full commit id, must BE the checked-out
#            commit, and the tree must be clean. Otherwise the images contain
#            code the recorded commit does not describe.
#   backup — in staging/production the off-box destination must resolve. Nothing
#            is uploaded; a preflight must not have remote side effects.
#
# No --gates flag here: the supported path runs every gate. Narrowing the set is
# a debugging affordance, not a release affordance.
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

# --------------------------------------------------------------------------- #
# 3. MANIFEST — record what was actually built, durably and outside this
#    repository, BEFORE anything starts. The rollback unit is an image ID; a tag
#    can be re-pointed at a different image under the same name.
#
#    `record` also re-verifies that each tag still resolves to the id it just
#    recorded, and `verify` re-reads the file from disk — so what a future
#    rollback will read is proven readable now, not assumed.
# --------------------------------------------------------------------------- #
python3 "$HERE/release_manifest.py" record --env-file "$ENV_FILE"

RELEASE_DIR="${RELEASE_DIR:-/srv/humanoidonline/releases}"
MANIFEST="$RELEASE_DIR/$RELEASE_SHA.json"
python3 "$HERE/release_manifest.py" verify "$MANIFEST"

# --------------------------------------------------------------------------- #
# 4. UP — compose reads the SAME env file, so the runtime pins are the ones the
#    preflight validated and the images are the ones the manifest recorded.
# --------------------------------------------------------------------------- #
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_PATH" up -d

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_PATH" ps

echo
echo "release $RELEASE_SHA is up. Retain this manifest for rollback:"
echo "  $MANIFEST"
