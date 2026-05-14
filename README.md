# Reading Time Estimator

A personal reading-list application that lets users track books they want to read, are reading, or have finished, and request a personalized reading-time estimate for any book based on their own reading speed. The primary purpose of the project is architectural: it implements an OAuth2 / OIDC flow across cooperating services — a Single-Page Application, a Backend-for-Frontend (BFF) acting as the OIDC client, a separately-owned Resource Server, and Keycloak as the identity provider — all deployable via `docker compose`.

## Setup

1. **Clone this repository** and `cd` into it.
2. **Clone the FastAPI archetype** into `tools/fastapi-archetype/`. The exact command is established in Story 1.3 (AR1); for Story 1.1 this directory is a placeholder and is gitignored.
3. **Copy `.env.example` to `.env`** at the repo root and adjust values as needed. Real secrets must never be committed.
4. **Bring up the stack:** `docker compose up`. Story 1.1 only ships an empty compose skeleton (`docker compose config` validates cleanly); subsequent stories add Keycloak, the BFF, the Resource Server, and the SPA into the `default`, `dev`, and `e2e` profiles.

## Architecture overview

See [`_bmad-output/planning-artifacts/architecture.md`](_bmad-output/planning-artifacts/architecture.md) for the canonical solution design — repository layout, OIDC topology, compose composition, profiles, and service contracts.

## AI integration log

This section is populated by Story 5.3 and will capture how AI tooling (BMAD agents, Claude Code) was used across planning, implementation, and review.
