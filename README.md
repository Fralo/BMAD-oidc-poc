# Reading Time Estimator

A personal reading-list application that lets users track books they want to read, are reading, or have finished, and request a personalized reading-time estimate for any book based on their own reading speed. The primary purpose of the project is architectural: it implements an OAuth2 / OIDC flow across cooperating services — a Single-Page Application, a Backend-for-Frontend (BFF) acting as the OIDC client, a separately-owned Resource Server, and Keycloak as the identity provider — all deployable via `docker compose`.

## Setup

1. **Clone this repository** and `cd` into it.
2. **Clone the FastAPI archetype** into `tools/fastapi-archetype/`. The exact command is established in Story 1.3 (AR1); for Story 1.1 this directory is a placeholder and is gitignored.
3. **Copy `.env.example` to `.env`** at the repo root and adjust values as needed. Real secrets must never be committed.
4. **Bring up the stack:** `docker compose --profile default up`. As of Story 1.2 the `default` profile boots Keycloak with the `bmad-books` realm pre-imported; the BFF, Resource Server, and SPA land in later stories. The admin console is at `http://localhost:8080/admin/` (credentials from `KEYCLOAK_ADMIN_USER` / `KEYCLOAK_ADMIN_PASSWORD` in `.env`) and two end-user accounts are pre-seeded — `testuser` / `testpassword` and `freshuser` / `freshpassword` (the latter intentionally has no reading-speed value, to exercise the J3 412 path in Epic 4).

## Architecture overview

See [`_bmad-output/planning-artifacts/architecture.md`](_bmad-output/planning-artifacts/architecture.md) for the canonical solution design — repository layout, OIDC topology, compose composition, profiles, and service contracts.

## AI integration log

This section is populated by Story 5.3 and will capture how AI tooling (BMAD agents, Claude Code) was used across planning, implementation, and review.
