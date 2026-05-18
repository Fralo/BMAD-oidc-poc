# Reading Time Estimator

A personal reading-list application that lets users track books they want to read, are reading, or have finished, and request a personalized reading-time estimate for any book based on their own reading speed. The primary purpose of the project is architectural: it implements an OAuth2 / OIDC flow across cooperating services — a Single-Page Application, a Backend-for-Frontend (BFF) acting as the OIDC client, a separately-owned Resource Server, and Keycloak as the identity provider — all deployable via `docker compose`. This repository is the BMAD capstone project for the AI-native engineering course, and the build itself was conducted with BMAD agent skills (see [AI integration log](#ai-integration-log)).

## Prerequisites

- **Node.js** ≥20 LTS — required by the Angular 21 SPA build and the Playwright runner.
- **Python** ≥3.14 — matches `requires-python = ">=3.14"` in `services/bff/pyproject.toml` and `services/resource-server/pyproject.toml`.
- **[`uv`](https://docs.astral.sh/uv/)** — backend dependency manager (the FastAPI archetype this project is built on uses `uv`; see [architecture.md § Backend Starter](_bmad-output/planning-artifacts/architecture.md#backend-starter--locked-no-evaluation)).
- **Docker** + **Docker Compose v2.20+** — the top-level `docker-compose.yml` uses the `include:` directive, stabilized in Compose v2.20.
- **`npx`** — ships with Node ≥20; needed for Playwright invocations.
- **[`just`](https://github.com/casey/just)** — task runner. Optional for the default and dev profiles; **required for the E2E profile** because the `-f compose/app.e2e.yml` overlay is not self-activating (Story 1.12 P1; see the `Justfile` preamble for the full rationale).
- **`ng` CLI** — optional; required only for SPA HMR development (`ng serve`).

## Setup

1. **Clone this repository** and `cd` into it.
2. **Clone the FastAPI archetype** into `tools/fastapi-archetype/` (gitignored). The archetype lives at `https://github.com/tommaso-meledina/fastapi-archetype`; Stories 1.3 and 3.1 establish the canonical AR1 scaffold invocation. The repo ships `tools/` empty as a placeholder — the archetype is intentionally kept out of the working tree so it can be updated independently and so the project's own diffs stay focused on the BFF/RS extensions rather than archetype churn.
3. **Copy `.env.example` to `.env`** at the repo root and fill in values. Never commit a real `.env` — it is `.gitignored`. At minimum the operator must provide values for these env-var **names** (see `.env.example` for the full inventory and inline comments):
   - `KEYCLOAK_ADMIN_USER` / `KEYCLOAK_ADMIN_PASSWORD` — Keycloak admin console credentials.
   - `BFF_CLIENT_SECRET` — the OAuth client secret shared with Keycloak's `bmad-books-bff` confidential client. Must match the secret in the realm JSON or the OIDC token exchange will fail.
   - `TEST_RESET_TOKEN` — bearer token gating `POST /v1/test/reset` on the BFF and RS. Required only when running with the `e2e` profile; the `${TEST_RESET_TOKEN:?...}` directive in `compose/app.e2e.yml` fails compose-up early if it's unset.
   - `OIDC_ISSUER_URL` / `OIDC_AUTHORIZE_URL_BROWSER` / `OIDC_JWKS_URL` — already filled in `.env.example` with the compose-local Keycloak URLs; only override if you point at a non-default Keycloak.
4. **First bring-up:** `docker compose up` (default profile — full topology with the SPA baked into the BFF image). The Keycloak realm at `keycloak/realm-bmad-books.json` is pre-imported on container start; two end-user accounts are seeded: `testuser` / `testpassword` and `freshuser` / `freshpassword`. The latter has no reading-speed value set, intentionally exercising the J3 412 "Set your reading speed in Settings to enable estimates" path (Epic 4).
5. **Verify the stack is healthy:** `docker compose ps` should show every service with status `healthy`. The Keycloak admin console is at `http://localhost:8080/admin/` using `KEYCLOAK_ADMIN_USER` / `KEYCLOAK_ADMIN_PASSWORD`.
6. **Open the app** at `http://localhost:8000` in a desktop browser. In the default profile the SPA is served same-origin from the BFF — there is no `:4200` to navigate to. Click **Log in**, authenticate at the Keycloak prompt as `testuser` / `testpassword`, and you should land on `/books` with the user's identity rendered in the top-right of the chrome.
7. **Reset between runs (optional):** to wipe the BFF and RS databases (`books`, `sessions`, `auth_states` on the BFF; `reading_speeds` on the RS), run `docker compose down -v && docker compose up --build`. The `-v` flag drops the `bff_data` and `rs_data` named volumes (the SQLite database files live there). Keycloak runs without a persistent volume in this stack, so the realm at `keycloak/realm-bmad-books.json` is re-imported on every container (re-)creation — `docker compose down` alone is enough to reseed the realm users; `-v` is needed only for the BFF/RS data volumes.

**Troubleshooting** (the most common first-run trips):

- **Realm import failure** — confirm the admin password matches `KEYCLOAK_ADMIN_PASSWORD` in `.env`, then `docker compose down && docker compose up` to recreate the Keycloak container. Keycloak runs without a persistent volume in this stack, so the realm at `keycloak/realm-bmad-books.json` is re-imported on every container (re-)creation; you do **not** need `-v` to force a re-import.
- **BFF cannot reach OIDC** — confirm `OIDC_ISSUER_URL` and `OIDC_AUTHORIZE_URL_BROWSER` resolve correctly. The first is consumed inside the BFF container and uses the compose service name `keycloak`; the second is the browser-facing URL and uses `localhost`. The split is intentional — the browser cannot resolve compose service names, and the BFF cannot use `localhost` from inside its container.
- **`/v1/test/reset` returns 404** — that endpoint is gated by `ENABLE_TEST_RESET=true`, which is only set in the E2E profile overlay (`compose/app.e2e.yml`). Use `just e2e-up`, not `docker compose --profile e2e up`, or the overlay won't be applied.
- **Port conflict on `:8000`, `:8080`, `:9000`, or `:4200`** — another process on the host is bound. Stop the conflicting process or remap the port in `compose/infra.yml` / `compose/app.yml`. (The Resource Server has no host-published port in any profile — `:8001` only matters when running the RS directly on the host outside compose, e.g. for `uv run pytest`.)

## Architecture overview

The Reading Time Estimator is built from four cooperating components. The **SPA** (Angular 21, Tailwind v4) is the only browser-facing surface; in the prod-shaped deployment it is served same-origin by the BFF, in dev it runs locally via `ng serve` and proxies API calls to the BFF. The **BFF** (FastAPI cookie-session OIDC client; built from the `fastapi-archetype`) owns the books domain, holds session state in SQLite, and never bypasses the RS for J6's degrade-honestly contract. The **Resource Server** (FastAPI; bearer-JWT validated against Keycloak's JWKS) owns the reading-speed value and the estimate computation; scope enforcement (`reading-speed:read`, `reading-speed:write`) lives here. **Keycloak** runs the `bmad-books` realm imported from `keycloak/realm-bmad-books.json`.

The load-bearing concepts are: Authorization Code + PKCE; HttpOnly server-side token storage (no browser-readable tokens); JWKS-cached signature validation; scope-enforced RS computation; and `sub`-keyed identity propagation (no shared DB between services).

```text
┌──────────────┐   cookie-authenticated REST   ┌──────────────────────────┐
│              │ ───────────────────────────►  │                          │
│     SPA      │       (HttpOnly, CSRF)        │           BFF            │
│  (Angular)   │ ◄───────────────────────────  │     (FastAPI, books)     │
│              │       JSON snake_case          │                          │
└──────────────┘                                │  ┌─────────────────────┐ │
                                                │  │  cookie-session     │ │
                                                │  │  OIDC client        │ │
                                                │  │  (Authlib)          │ │
                                                │  └─────────────────────┘ │
                                                └────┬─────────────┬────────┘
                                                     │             │
                                  Auth Code + PKCE   │             │ Bearer JWT
                                  refresh, end-sess  │             │ (forward user
                                  (Authlib)          │             │  access token)
                                                     ▼             ▼
                                          ┌──────────────┐   ┌──────────────────┐
                                          │              │   │                  │
                                          │   Keycloak   │   │  Resource Server │
                                          │   (realm     │   │  (FastAPI; JWKS  │
                                          │   imported)  │◄──┤   validation;    │
                                          │              │   │   scope enforce) │
                                          └──────────────┘   └──────────────────┘
                                              JWKS fetch (RS → Keycloak, cached 24h)
```

A few things to call out from the diagram:

- The **SPA never speaks to the Resource Server directly.** Every RS call is proxied by the BFF, which attaches the user's access token as `Authorization: Bearer …`. This is the load-bearing isolation that keeps tokens out of the browser.
- The **single 401-refresh-replay cycle** on the BFF ↔ RS edge: when the RS rejects with `401 invalid_token`, the BFF refreshes the user's access token against Keycloak and replays the in-flight request. The SPA sees neither the 401 nor the refresh.
- The **RS ↔ Keycloak edge is JWKS-only.** No session, no token exchange, no admin-API usage. Public keys are cached with `kid`-rotation re-fetch.

For the canonical solution design — repository layout, OIDC topology, compose composition, profiles, service contracts, and the full set of architectural decisions (A1–A8 on auth/security, C1–C8 on API patterns, F1–F6 on the frontend, I1–I8 on infrastructure) — see [`_bmad-output/planning-artifacts/architecture.md`](_bmad-output/planning-artifacts/architecture.md).

For the per-surface coverage snapshot and thresholds, see [`docs/coverage-report.md`](docs/coverage-report.md).

For the OAuth/OIDC security review (PRD §9 envelope: token storage, cookie attributes, CSRF, JWT validation, scope enforcement, SPA concerns), see [`docs/security-review.md`](docs/security-review.md).

## Dev workflow

The dev workflow is the iterative loop for SPA work with HMR while the BFF, RS, and Keycloak run in compose. The SPA is **not** baked into the BFF image in this mode.

```bash
# Terminal 1 — backend stack (Keycloak + BFF + RS; no SPA container)
docker compose --profile dev up

# Terminal 2 — SPA on the host with HMR (uses spa/package.json's `start` script,
# which runs `ng serve` without requiring a global @angular/cli install)
cd spa && npm start
```

The SPA's `spa/proxy.conf.json` proxies `/v1`, `/api`, and `/auth` from the dev server (`http://localhost:4200`) to the BFF (`http://localhost:8000`). To the browser, every API call appears to come from the same origin as the SPA, so the existing HttpOnly + `SameSite=Lax` cookies and double-submit CSRF tokens flow without cross-origin CORS gymnastics.

| Service | Port | Notes |
|---------|------|-------|
| SPA (`ng serve`) | `4200` | Local dev only; not in the prod build path |
| BFF | `8000` | Cookie-session OIDC client; owns `/api/*`, `/v1/books*`, `/auth/*` |
| Resource Server | `8001` | Bearer-JWT; reached from the BFF (in compose) or `localhost` (on host) |
| Keycloak | `8080` | Admin console at `/admin/`, realm at `/realms/bmad-books` |

Seeded end-user credentials (version-controlled in `keycloak/realm-bmad-books.json` — these are test fixtures, not secrets):

- `testuser` / `testpassword` — has a pre-set reading-speed; exercises the J3 estimate happy path.
- `freshuser` / `freshpassword` — has **no** reading-speed set; exercises the J3 412 "Set your reading speed in Settings to enable estimates" path.

Keycloak admin credentials are read from the `.env` values for `KEYCLOAK_ADMIN_USER` / `KEYCLOAK_ADMIN_PASSWORD`.

## E2E workflow

The Playwright suite has two run modes.

**Compose-driven E2E (the canonical run):**

```bash
just e2e-up
```

This wraps a two-phase invocation: `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up -d --wait keycloak bff resource-server` brings the infra services up detached and healthy, then `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e run --rm --build playwright` runs the test suite as a one-shot container. (The earlier `up --abort-on-container-exit` form was retired in Story 3.6 because J4's `killRs()` would SIGTERM the runner mid-test.) The `just` wrapper exists because Compose's top-level `include:` directive does not honor `profiles:` on overlay files — a bare `docker compose --profile e2e up` would NOT apply `compose/app.e2e.yml` and the `${TEST_RESET_TOKEN:?...}` fail-fast inside the overlay would never trigger. See the `Justfile` preamble for the full rationale (Story 1.12 patch P1; Story 3.6 two-phase revision).

**Local-against-dev-stack E2E:**

```bash
# Bring the backend up under the e2e overlay so /v1/test/reset is mounted.
# (The bare `--profile dev` stack does NOT enable the reset endpoint —
# ENABLE_TEST_RESET=true is only set by compose/app.e2e.yml.)
docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e \
    up -d --wait keycloak bff resource-server

# In another terminal, run Playwright on the host:
cd e2e && npm test
```

Playwright runs on the host against the backend in compose. Two env vars must be set on the BFF before this mode works: `ENABLE_TEST_RESET=true` mounts the `/v1/test/reset` route (it is not exposed in the default or `dev` profiles), and `TEST_RESET_TOKEN` is the bearer the `resetState` helper authenticates with (the same token must also be in the Playwright host env). The overlay-driven bring-up above sets both. This mode is the right iteration loop when authoring a new spec — you get instant Playwright re-runs (`npx playwright test --ui` for the inspector, or `npx playwright test e2e/tests/j3-estimate.spec.ts:42 --debug` to step through one test) without rebuilding the compose runner image each time. Use `cd spa && npm start` in a third terminal if the spec depends on local SPA changes; the SPA's proxy config forwards `/v1`, `/api`, `/auth` to the compose BFF so the auth flow still works.

The six journey specs:

- `e2e/tests/j1-first-login.spec.ts` — first-time OIDC login (J1).
- `e2e/tests/j2-manage-books.spec.ts` — full books CRUD + status transitions (J2).
- `e2e/tests/j3-estimate.spec.ts` — estimate happy path + Re-estimate after speed change (J3).
- `e2e/tests/j4-adjust-speed.spec.ts` — settings save + persistence across reload (J4).
- `e2e/tests/j5-logout.spec.ts` — logout + return-to redirect on protected nav (J5).
- `e2e/tests/j6-rs-unavailable.spec.ts` — RS-down honest error + RS-up recovery (J6).

On failure, Playwright retains traces and screenshots under `e2e/test-results/`; the latest HTML report is at `e2e/playwright-report/index.html`.

`playwright.config.ts` pins `workers: 1` (sequential). The shared `resetState` helper requires this — do not raise it. Between specs, `resetState` calls `POST /v1/test/reset` on both the BFF (truncates `books` + `sessions` + `auth_states`) and the RS (truncates `reading_speeds`), then re-seeds the two fixture users via the Keycloak realm import. Running specs in parallel would race the truncate.

## Prod-shaped workflow

The prod-shaped workflow is the **default** compose profile: full topology with the SPA baked into the BFF image via the multi-stage `services/bff/Dockerfile` (Story 1.14). This is the deployment path the final smoke checklist (Story 5.4) verifies.

```bash
# Clean reset (optional but recommended for a fresh evaluation)
docker compose down -v

# Bring up the full topology with the SPA-in-BFF baked build
docker compose up --build
```

Services declare `profiles: [default, dev, e2e]` in `compose/app.yml` and `compose/infra.yml`, so the default profile activates automatically — there is no `--profile default` flag required (though it is accepted for explicitness). (The Playwright runner is the only service scoped to `[e2e]` only.)

What's different from the dev profile: the SPA container is replaced by the BFF static-serving the built bundle at `/`. No `ng serve`. No port `:4200`. Single origin everywhere (`http://localhost:8000`).

See [`docs/smoke-run.md`](docs/smoke-run.md) for the manual smoke checklist that verifies all six journeys (J1–J6) against this build path. The Run Record at the bottom of that file captures the submission-state evidence (date, commit SHA, per-step checkbox results, anomalies); Story 5.4 documents two execution modes — operator-driven (canonical PASS path) and programmatic-agent partial-smoke (PASS WITH ANOMALIES, with the browser-required journey steps left for an operator follow-up).

## Per-surface test commands

| Surface | Base test command | Coverage variant |
|---------|-------------------|------------------|
| BFF | `cd services/bff && uv run pytest` | `cd services/bff && uv run pytest --cov=src/bff --cov-report=term-missing --cov-report=html` |
| Resource Server | `cd services/resource-server && uv run pytest` | `cd services/resource-server && uv run pytest --cov=src/resource_server --cov-report=term-missing --cov-report=html` |
| SPA | `cd spa && npm test` | `cd spa && npm test -- --coverage` |
| E2E | `cd e2e && npm test` | `just e2e-up` (full-suite execution against the compose stack — see the E2E workflow section above for the two-phase expansion) |

For per-surface thresholds, per-file floors, and the canonical coverage snapshot, see [`docs/coverage-report.md`](docs/coverage-report.md). The thresholds themselves are NFR11 requirements stated in [`_bmad-output/planning-artifacts/architecture.md`](_bmad-output/planning-artifacts/architecture.md) and verified by Story 5.1.

For local iteration, the terse-output forms below are the right speed-of-iteration commands. The `--cov` variants in the table are slower and only useful when regenerating the coverage audit:

- **BFF / RS terse run:** `uv run pytest -q --tb=short` (from each service's directory).
- **BFF / RS single-test focus:** `uv run pytest tests/auth/test_csrf.py::test_post_header_cookie_mismatch_returns_403 -xvs` — fail-fast + capture print output for fast debug.
- **SPA terse run:** `npm test` runs Vitest 4 against the Angular 21 unit tree with the Vite-driven incremental file watcher; `npm test -- --coverage` produces `spa/coverage/spa/index.html`.
- **SPA single-file focus:** `cd spa && npx vitest run src/app/books/estimate-cell.spec.ts` — runs one spec file without watch mode.
- **E2E base run:** `cd e2e && npm test` expects a backend stack already running under `--profile dev`; the canonical full-suite run is the compose `just e2e-up` invocation above.

## Project structure

```text
bmad-books/                # repo root
├── README.md              # THIS FILE
├── CLAUDE.md              # project conventions (python = python; no python3)
├── docker-compose.yml     # include: compose/infra.yml + compose/app.yml
├── Justfile               # e2e-up / e2e-config / e2e-down (compose foot-gun fix)
├── .env.example           # full env-var inventory consumed by every service
│
├── compose/               # infra.yml (Keycloak) + app.yml + app.e2e.yml overlay
├── keycloak/              # realm-bmad-books.json + Dockerfile (realm import)
├── services/
│   ├── bff/               # FastAPI BFF (from fastapi-archetype)
│   └── resource-server/   # FastAPI RS (from fastapi-archetype)
├── spa/                   # Angular 21 SPA (Tailwind v4)
├── e2e/                   # Playwright 1.49 — 6 journey specs
├── docs/                  # coverage-report.md, security-review.md, smoke-run.md (5.4)
├── tools/                 # fastapi-archetype clone target (gitignored)
└── _bmad-output/          # planning + implementation artifacts (BMAD)
    ├── planning-artifacts/
    └── implementation-artifacts/
```

For the deep tree (per-service `src/` layout, test mirrors, archetype extension points), see [`_bmad-output/planning-artifacts/architecture.md § Complete Project Directory Structure`](_bmad-output/planning-artifacts/architecture.md#complete-project-directory-structure).

## AI integration log

This is a chronological record of how the AI-native build was conducted. Each entry's date is verified against `git log --format='%ad %s' --date=short`; the Claude model attribution is verified against the `Co-Authored-By:` trailers on the commits of that date. All references to "Claude Opus 4.7" and "Claude Opus 4.7 (1M context)" name the same Opus 4.7 model — the parenthetical suffix marks when the `Co-Authored-By:` trailer convention started explicitly noting the 1M-token context window, not a model version change.

- **2026-05-14** — Planning phase. `bmad-create-prd` → PRD (`_bmad-output/planning-artifacts/PRD.md`); `bmad-validate-prd` → PRD validation report; `bmad-create-ux-design` → UX specification (`ux-design-specification.md`, commit `a6562d0`); `bmad-create-architecture` → architecture decision document (`architecture.md`, commit `e0227e0`); `bmad-check-implementation-readiness` → readiness report (commit `489796f`); `bmad-create-epics-and-stories` → epic + 30-story breakdown (`epics.md`). Model: **Claude Opus 4.7**.
- **2026-05-14** — Notable AI-assisted decision: **Angular v21 + Tailwind CSS v4** chosen for the SPA stack after `bmad-technical-research`-driven starter evaluation (vs. React + Vite, Svelte, Solid). The deciding factors were Angular's first-class signals story (which the SPA's optimistic-UI status-control and estimate-cell both lean on heavily) and Tailwind v4's `@theme` block landing the design tokens in a single CSS import. Recorded at `_bmad-output/planning-artifacts/architecture.md` § "Starter Template Evaluation — SPA Starter — Angular v21 + Tailwind CSS v4" (line 156 onward).
- **2026-05-14** — Notable AI-assisted decision: **Backend archetype lock-in**. The BFF and RS are both built on `github.com/tommaso-meledina/fastapi-archetype` (Python 3.14 + FastAPI + SQLModel + `uv` + OTEL). `bmad-create-architecture` evaluated alternatives (raw FastAPI scaffold, Django REST, Litestar) and chose the archetype because it tightens the test-coverage floor to >90% by default and ships the `RoleMappingProvider` extension point the RS's scope enforcement plugs into.
- **2026-05-14 → 2026-05-15** — Epic 1 (foundational auth + SPA scaffold + Playwright harness). Stories 1.1 through 1.14:
  - 1.1 repo scaffold + compose skeleton; 1.2 Keycloak realm-as-code; 1.3 BFF scaffold from archetype; 1.4 BFF session schema + Alembic; 1.5 BFF cookie-session OIDC plugin + PKCE + synthetic IdP; 1.6 BFF CSRF middleware + CSP header; 1.7 BFF logout + revoke + end-session.
  - 1.8 SPA scaffold + Tailwind v4 tokens; 1.9 SPA AuthService + interceptors + functional guards; 1.10 SPA LoginView + TopChrome + route table.
  - 1.11 Playwright project setup; 1.12 BFF `POST /v1/test/reset`; 1.13 J1 + J5 E2E specs; 1.14 BFF multi-stage build serves the SPA bundle.
  - Each story followed the `bmad-create-story` → `bmad-dev-story` → `bmad-code-review` triplet. The code-review pass deliberately ran in a fresh context using **Claude Sonnet 4.6** (the "different LLM for review" convention introduced in Story 1.10); the create-story and dev-story passes used **Claude Opus 4.7**.
- **2026-05-14** — Notable AI-assisted decision: **Sprint change proposal** (`_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-14.md`) authored mid-Epic-1 to admit Story 1.14 (BFF multi-stage build serving the SPA bundle) after Story 1.10 review surfaced that the architecture's I6 decision needed a story owner.
- **2026-05-16** — Epic 1 retrospective via `bmad-retrospective` → `epic-1-retro-2026-05-16.md` (commit `0a58442`). The `Co-Authored-By:` trailer convention started explicitly noting **Claude Opus 4.7 (1M context)** from this date forward (same Opus 4.7 model as the earlier commits; the suffix simply marks the larger context window the trailer convention adopted to disambiguate).
- **2026-05-16 → 2026-05-17** — Epic 2 (books CRUD: BFF + SPA + J2 E2E) and Epic 3 (RS scaffold, OIDC bearer + scopes, reading-speed CRUD, J4 E2E + compose `e2e` profile) running in parallel via `git worktree`s. Each story followed the same `bmad-create-story` → `bmad-dev-story` → `bmad-code-review` triplet; the merge-into-`epic-N` branches kept the cross-epic parallelization coherent. Model: Claude Opus 4.7 (1M context).
- **2026-05-17** — Notable AI-assisted decision: **Parallel-epic execution via worktrees**. After Epic 1 closed serially, `bmad-correct-course` proposed running Epic 2 (BFF + SPA books) and Epic 3 (RS reading-speed) concurrently — they have no shared source files until the proxy in Story 3.5. Each story file logs the `worktree-agent-…` branch the dev pass ran in; the `Merge branch 'worktree-agent-…' into epic-N` commit titles in the log are the reconciliation points.
- **2026-05-17** — Epic 2 retrospective via `bmad-retrospective` → `epic-2-retro-2026-05-17.md` (commit `73cbfea`).
- **2026-05-17 → 2026-05-18** — Epic 4 (the defining J3 estimate interaction + J6 honest-failure surface). Stories 4.1 (RS `POST /v1/estimate`), 4.2 (BFF compute-estimate proxy), 4.3 (SPA EstimateCell real component), 4.4 (J3 + J6 E2E specs). Model: Claude Opus 4.7 (1M context).
- **2026-05-18** — Notable AI-assisted decision: **Honest-failure contract for J6**. Story 4.2's BFF compute-estimate proxy explicitly refuses to fabricate an estimate when the RS is unreachable; instead it maps `httpx` transport errors and RS 5xx responses to `ResourceServerUnavailableError`, which the SPA renders as the dedicated J6 "Service unavailable — try again shortly" state. This was a `bmad-create-story`-driven design call: the temptation to "degrade gracefully" with a stale or last-known value is exactly the failure mode PRD §8's "BFF does not bypass the RS" rule forbids.
- **2026-05-18** — Epic 5 documentation pass: Story 5.1 (`docs/coverage-report.md` — pure attestation; no source or test changes), Story 5.2 (`docs/security-review.md` — PRD §9 six-topic envelope; pure documentation citing implementing code paths verbatim), and Story 5.3 (this README rewrite + AI integration log). Model: Claude Opus 4.7 (1M context).
- **2026-05-18** — Notable AI-assisted decision: **Coverage threshold soften (DN1)** during Story 5.1's code-review pass. The original "≥90% with `fail_under = 90`" hard floor would have created per-pass flake on borderline-pure-data files; the resolution kept the `precision = 0` rounding behavior (effective floor ≈ 89.5%) and softened the doc framing to match — a documentation-coherence call rather than a gate change.
- **2026-05-18** — Notable AI-assisted decision: **Security review structure mirrors PRD §9 verbatim**. Story 5.2's `docs/security-review.md` resisted the temptation to add a STRIDE / LINDDUN / ASVS cross-walk; instead the six top-level sections map 1-to-1 to PRD §9's six topics, each citing implementing code paths (`auth/keycloak_cookie_session.py`, `auth/csrf.py`, `middleware/security_headers.py:17–21`, `auth/oidc_bearer.py`, etc.) and the pin-tests that lock the behavior. The reviewer's verdict is verifiable from the document and the code, not from a framework cross-walk.

The build deliberately ran without a GitHub Actions CI pipeline (PRD §4 / architecture I7 out-of-scope per the project charter). Local test gates (`uv run pytest`, `npm test`, `just e2e-up`) are the test surfaces.

**Other AI-assisted decisions left as accepted scope** (PRD §4 out-of-scope; the security review names each one):

- Plaintext at-rest token storage in the BFF's `sessions` SQLite columns — mitigated by named-volume isolation; production alternatives (KEK encryption, dedicated encrypted store, JWE session cookie) are named in `docs/security-review.md` § Accepted Risks.
- No idle-session timeout beyond the refresh-token chain.
- No CSP hardening pass (`object-src 'none'`, nonce-based scripts, CSP report endpoint).
- No additional security headers (`X-Content-Type-Options`, `Referrer-Policy`, HSTS).
- No mobile or responsive layout in the SPA (desktop-only reference; `[project_bmad_books_scope]` memory).
- No OWASP ASVS / NIST SSDF cross-walk in the security review (PRD §9's six-topic envelope is the structure).

**Retrospectives** capturing what the AI-assisted build went well at and what it would do differently are at `_bmad-output/implementation-artifacts/epic-1-retro-2026-05-16.md` and `epic-2-retro-2026-05-17.md`. Epic 3/4/5 retros are optional per the sprint plan.

## References

- [`_bmad-output/planning-artifacts/PRD.md`](_bmad-output/planning-artifacts/PRD.md) — Product Requirements Document.
- [`_bmad-output/planning-artifacts/architecture.md`](_bmad-output/planning-artifacts/architecture.md) — Architecture decision document.
- [`_bmad-output/planning-artifacts/ux-design-specification.md`](_bmad-output/planning-artifacts/ux-design-specification.md) — UX design specification.
- [`_bmad-output/planning-artifacts/epics.md`](_bmad-output/planning-artifacts/epics.md) — Epics + stories breakdown.
- [`docs/security-review.md`](docs/security-review.md) — OAuth/OIDC security review (Story 5.2).
- [`docs/coverage-report.md`](docs/coverage-report.md) — Per-surface coverage snapshot (Story 5.1).
- [`docs/smoke-run.md`](docs/smoke-run.md) — Final default-profile smoke run (Story 5.4).
- [`fastapi-archetype`](https://github.com/tommaso-meledina/fastapi-archetype) — the backend archetype the BFF and RS are built from.
- [`just` task runner](https://github.com/casey/just) — required for the E2E workflow.
