# Reading Time Estimator

A personal reading-list application that lets users track books they want to read, are reading, or have finished, and request a personalized reading-time estimate for any book based on their own reading speed. The primary purpose of the project is architectural: it implements an OAuth2 / OIDC flow across cooperating services — a Single-Page Application, a Backend-for-Frontend (BFF) acting as the OIDC client, a separately-owned Resource Server, and Keycloak as the identity provider — all deployable via `docker compose`.

## Setup

1. **Clone this repository** and `cd` into it.
2. **Clone the FastAPI archetype** into `tools/fastapi-archetype/`. The exact command is established in Story 1.3 (AR1); for Story 1.1 this directory is a placeholder and is gitignored.
3. **Copy `.env.example` to `.env`** at the repo root and adjust values as needed. Real secrets must never be committed.
4. **Bring up the stack:** `docker compose --profile default up`. As of Story 1.2 the `default` profile boots Keycloak with the `bmad-books` realm pre-imported; the BFF, Resource Server, and SPA land in later stories. The admin console is at `http://localhost:8080/admin/` (credentials from `KEYCLOAK_ADMIN_USER` / `KEYCLOAK_ADMIN_PASSWORD` in `.env`) and two end-user accounts are pre-seeded — `testuser` / `testpassword` and `freshuser` / `freshpassword` (the latter intentionally has no reading-speed value, to exercise the J3 412 path in Epic 4).

### E2E profile

The `e2e` profile flips on the bearer-authenticated `POST /v1/test/reset` endpoint (Story 1.12). It REQUIRES the `compose/app.e2e.yml` overlay to be applied via an explicit `-f` flag — compose's top-level `include:` directive is unconditional and cannot gate the overlay by profile (its nominal `profiles:` field is silently ignored). To avoid the foot-gun, use the repo-root `Justfile` (requires [`just`](https://github.com/casey/just)):

- `just e2e-config` — validate the merged config
- `just e2e-up` — bring up the e2e stack with `--abort-on-container-exit`
- `just e2e-down` — tear it down and drop volumes

`TEST_RESET_TOKEN` must be set in your shell or the repo-root `.env` before invoking these recipes; the overlay declares the variable with `${TEST_RESET_TOKEN:?...}` so compose refuses to start when it's missing.

## Architecture overview

See [`_bmad-output/planning-artifacts/architecture.md`](_bmad-output/planning-artifacts/architecture.md) for the canonical solution design — repository layout, OIDC topology, compose composition, profiles, and service contracts.

See [`docs/coverage-report.md`](docs/coverage-report.md) for the per-surface coverage snapshot and thresholds.

See [`docs/security-review.md`](docs/security-review.md) for the OAuth/OIDC security review (PRD §9 envelope: token storage, cookie attributes, CSRF, JWT validation, scope enforcement, SPA concerns).

## AI integration log

This section is populated by Story 5.3 and will capture how AI tooling (BMAD agents, Claude Code) was used across planning, implementation, and review.
