# syntax=docker/dockerfile:1.7
#
# WS8.7 / R26 — production image for the Next.js web tier.
#
# Build context is the REPOSITORY ROOT (shared .dockerignore with the API image).
#
# Reproducibility (R26): dependencies come from the committed `package-lock.json`
# via `npm ci`; the base image is a build ARG so the deployment pins it to an
# immutable DIGEST without editing this file:
#
#   docker build \
#     --build-arg NODE_IMAGE=node:20-bookworm-slim@sha256:<digest> \
#     --build-arg NEXT_PUBLIC_SITE_URL=https://humanoidonline.com \
#     -f apps/web/Dockerfile -t humanoidonline-web:<git-sha> .
#
# NEXT_PUBLIC_SITE_URL is required AT BUILD TIME: next.config.mjs asserts the
# canonical origin is configured (WS8.2 / R8), so a build cannot silently bake in
# a wrong origin. API_BASE_URL is deliberately NOT a build arg — it is resolved
# lazily at request time (WS8.7 / WS8-L5, lib/server.ts) and supplied as runtime
# environment, so one image is not welded to one backend address.
ARG NODE_IMAGE=node:20-bookworm-slim

# ------------------------------------------------------------------- deps ----
FROM ${NODE_IMAGE} AS deps
WORKDIR /srv/web
COPY apps/web/package.json apps/web/package-lock.json ./
# `npm ci` installs exactly the lockfile — never a re-resolved tree.
RUN npm ci

# ---------------------------------------------------------------- builder ----
FROM ${NODE_IMAGE} AS builder
WORKDIR /srv/web
COPY --from=deps /srv/web/node_modules ./node_modules
COPY apps/web ./

ARG NEXT_PUBLIC_SITE_URL
# Standalone output is enabled ONLY here (see next.config.mjs): the trace-copy
# step is broken on Windows, where this project is developed, so ordinary local
# and CI builds must not use it. The image build runs on Linux.
ENV NEXT_OUTPUT_STANDALONE=1 \
    NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL} \
    NEXT_TELEMETRY_DISABLED=1
RUN test -n "$NEXT_PUBLIC_SITE_URL" || \
      (echo "NEXT_PUBLIC_SITE_URL build-arg is required (WS8.2 / R8)" && exit 1)
RUN npm run build

# ---------------------------------------------------------------- runtime ----
FROM ${NODE_IMAGE} AS runtime
WORKDIR /srv/web

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# `output: "standalone"` traces exactly the modules the server needs.
COPY --from=builder /srv/web/.next/standalone ./
COPY --from=builder /srv/web/.next/static ./.next/static
COPY --from=builder /srv/web/public ./public

RUN groupadd --system app && useradd --system --gid app --home /srv app \
    && chown -R app:app /srv
USER app

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=3 \
  CMD node -e "require('http').get('http://127.0.0.1:3000/robots.txt',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
