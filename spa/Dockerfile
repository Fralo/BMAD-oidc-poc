# spa/Dockerfile
# Story 6.2: SPA SSR edge image. Three-stage Node multi-stage build that
# produces the Angular 21 SSR Express server (`dist/spa/server/server.mjs`)
# wired up by Story 6.1. Mirrors the BFF Dockerfile's pattern: distinct
# `deps` / `build` / `runtime` stages, non-root `app` user in the runtime
# stage, and a stdlib-only HEALTHCHECK (Node 22's global `fetch` here, the
# BFF uses Python's `urllib.request` — same idea, different language).
#
# Build context is `../spa` (set in compose/app.yml), NOT the repo root.
# That keeps the build context tight (~5 MB after `.dockerignore`) compared
# to the BFF's root context (~250 MB). Only `spa/.dockerignore` is consulted.
#
# No `node_modules` in the runtime stage by design: Angular 21's
# `@angular/build:application` builder with `outputMode: "server"` bundles
# every SSR dep (Express, `http-proxy-middleware`, `@angular/ssr/node`) into
# `dist/spa/server/main.server.mjs`, so the runtime image only carries the
# Node binary plus `dist/spa/`. See Story 6.2 Dev Notes §"Why no
# node_modules in the runtime image".

# ── Stage 0: dependency install ────────────────────────────────────────────
FROM node:22-slim AS deps

WORKDIR /spa

# Lockfile-only copy keeps this layer cache-friendly: only re-runs when
# package.json or package-lock.json changes.
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline --no-audit --no-fund

# ── Stage 1: build ─────────────────────────────────────────────────────────
FROM node:22-slim AS build

WORKDIR /spa

# Reuse the populated node_modules from the deps stage; then copy the rest of
# the SPA source on top and run the production build. Output lands at
# /spa/dist/spa/{browser,server}.
COPY --from=deps /spa/node_modules ./node_modules
COPY . ./
RUN npm run build

# ── Stage 2: runtime ───────────────────────────────────────────────────────
FROM node:22-slim

# Non-root `app` user — same shape as services/bff/Dockerfile:45-46/65.
RUN groupadd --system app && useradd --system --gid app app

WORKDIR /app

# Copy ONLY the built artefacts. The `@angular/build:application` builder
# bundled all SSR deps into the server entry, so we do NOT carry node_modules
# into the runtime image.
COPY --from=build --chown=app:app /spa/dist/spa /app/dist/spa

ENV NODE_ENV=production \
    PORT=4000

USER app
EXPOSE 4000

# Image-level HEALTHCHECK uses Node 22's global `fetch` against the
# /_health route wired by Story 6.1 in spa/src/server.ts. No curl/wget
# package install — keeps the runtime image slim and avoids drift between
# image probe and compose probe. The compose-level healthcheck
# (compose/app.yml `spa.healthcheck:`) overrides this at runtime but the
# image-level one keeps `docker run` standalone-usable.
HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=15s \
    CMD node -e "fetch('http://localhost:4000/_health').then(r => process.exit(r.ok ? 0 : 1)).catch(e => { console.error('healthcheck:', e && e.message || e); process.exit(1); })"

ENTRYPOINT ["node", "dist/spa/server/server.mjs"]
