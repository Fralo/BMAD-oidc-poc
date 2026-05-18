# Top-level task runner for the Reading Time Estimator stack.
# Usage: just <recipe>   (requires https://github.com/casey/just)
#
# This Justfile owns the multi-file compose invocations that operators
# must NOT forget. The classic foot-gun (Story 1.12 Patch P1) is that
# `docker compose --profile e2e up` runs WITHOUT `compose/app.e2e.yml`
# because compose's top-level `include:` directive is unconditional —
# the `${TEST_RESET_TOKEN:?...}` fail-fast in app.e2e.yml would fire on
# every default-profile invocation. Compose's `include:` accepts a
# `profiles:` field but it is silently ignored (verified against
# compose v5.1.3) so we cannot make the overlay self-activating; the
# next-smallest correct fix is to put the `-f compose/app.e2e.yml`
# pattern behind a named recipe so it's impossible to forget.

default:
    @just --list

# Validate the default profile stack (Keycloak + BFF + RS + SPA).
default-config:
    docker compose --profile default config

# Validate the e2e profile stack with the test-reset endpoint enabled.
# TEST_RESET_TOKEN must be set in the environment or the repo-root .env.
# The `-f docker-compose.yml -f compose/app.e2e.yml` form is the canonical
# pattern: `docker-compose.yml` brings in both `compose/infra.yml`
# (Keycloak) and `compose/app.yml` (BFF + RS + SPA) via its top-level
# `include:`, then `compose/app.e2e.yml` merges the `ENABLE_TEST_RESET=true`
# override onto the BFF service.
e2e-config:
    docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config

# Bring up the e2e stack and run the test suite.
#
# Two-phase orchestration (revised in Story 3.6): bring infra services up
# detached + healthy, THEN run the playwright runner as a one-shot.
# Story 3.6's J4 tests stop and restart the `resource-server` container
# mid-test via the bound docker socket (`killRs()` / `startRs()`). The
# original `up --abort-on-container-exit` form interpreted that intentional
# stop as a service crash and SIGTERM'd the playwright runner before the
# test could call `startRs()`, masking the AC10-AC14 results.
#
# `set -e` + `trap … EXIT` runs the `down` cleanup on any failure path —
# the previous three-line `&&`-chain left services running when `up` or
# the playwright run failed, breaking the next invocation on
# `container_name: playwright` collisions (review patch P1).
#
# `--build` on the `run` step is LOAD-BEARING for spec iteration (Story 4.4
# dev discovery): `e2e/Dockerfile` does `COPY . .` so specs are baked into
# the runner image at build time. Without `--build`, `docker compose run`
# reuses the cached image and silently runs the old spec set — manifested
# during Story 4.4 dev as `Running 18 tests` (Epic-3 image) instead of the
# expected 26 (after J3 + J6 specs landed). The `--build` flag forces
# Compose to rebuild only when files copied into the runner image have
# changed; layer caching keeps the typical edit cycle fast (~0.1s rebuild
# when only spec files changed).
e2e-up:
    #!/usr/bin/env bash
    set -e
    trap 'docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e down' EXIT
    docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up -d --wait keycloak bff resource-server
    docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e run --rm --build playwright

# Tear down the e2e stack and remove volumes (idempotent).
e2e-down:
    docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e down -v
