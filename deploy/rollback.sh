#!/usr/bin/env bash
# WS8.7 / R26 — roll back to a RETAINED release, verified by image ID.
#
#   sudo ENV_FILE=/srv/humanoidonline/.env.production \
#     deploy/rollback.sh /srv/humanoidonline/releases/<previous-sha>.json
#
# This script NEVER builds and NEVER pulls. Both would defeat the point: a
# rollback must start the artefact that was actually running before, not a fresh
# resolution of a name that may now mean something else. It therefore only
# inspects what is already on this host, and refuses when:
#
#   * a recorded image ID is not present locally (the target is gone — restore
#     it, or roll back to a release whose images are still retained);
#   * a recorded tag no longer resolves to the recorded ID (something was
#     rebuilt under the same name, so the tag would start the wrong artefact);
#   * compose would not actually use the manifest's tags.
#
# The last check matters because compose resolves `${RELEASE_SHA}` from the
# environment and the env file. Rather than trusting precedence, the resolved
# image list is read back from `docker compose config --images` and compared
# with the manifest before anything starts.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

MANIFEST="${1:-}"
[ -n "$MANIFEST" ] || { echo "usage: rollback.sh <retained-release-manifest.json>" >&2; exit 2; }
[ -r "$MANIFEST" ] || { echo "rollback: cannot read manifest $MANIFEST" >&2; exit 1; }

ENV_FILE="${ENV_FILE:-$ROOT/.env.production}"
COMPOSE_PATH="${COMPOSE_PATH:-$ROOT/docker-compose.prod.yml}"
[ -r "$ENV_FILE" ] || { echo "rollback: cannot read $ENV_FILE" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# 1. VERIFY — both images present locally, both tags still resolving to the
#    recorded IDs. No build, no pull.
# --------------------------------------------------------------------------- #
python3 "$HERE/release_manifest.py" verify "$MANIFEST"

TARGET_SHA="$(python3 "$HERE/release_manifest.py" read "$MANIFEST" release_sha)"
[ -n "$TARGET_SHA" ] || { echo "rollback: manifest has no release_sha" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# 2. PROVE COMPOSE WILL USE IT — read back compose's own resolution instead of
#    assuming the exported value wins over the env file.
# --------------------------------------------------------------------------- #
export RELEASE_SHA="$TARGET_SHA"
RESOLVED="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_PATH" config --images)"
for role in api web; do
  want="humanoidonline-$role:$TARGET_SHA"
  case "$RESOLVED" in
    *"$want"*) ;;
    *)
      echo "rollback: compose would NOT use $want (resolved images: $(echo "$RESOLVED" | tr '\n' ' '))" >&2
      exit 1
      ;;
  esac
done

# --------------------------------------------------------------------------- #
# 3. RESTART on the retained release.
# --------------------------------------------------------------------------- #
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_PATH" up -d

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_PATH" ps

echo
echo "rolled back to release $TARGET_SHA (manifest: $MANIFEST)"
