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

# Bring up the e2e stack. The `--abort-on-container-exit` flag is the
# Playwright runner's expected lifecycle (Story 1.11 / 1.12).
e2e-up:
    docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit

# Tear down the e2e stack and remove volumes (idempotent).
e2e-down:
    docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e down -v
