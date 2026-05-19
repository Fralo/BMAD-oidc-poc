# E2E — Playwright Harness

Playwright project for the Reading Time Estimator. Drives the SPA + BFF +
Keycloak round-trip end-to-end against the real running compose stack; nothing
is mocked. Specs land alongside the features they verify (Stories 1.13, 2.7,
3.6, 4.4 — one journey per spec file).

## Running locally

Prerequisites: Keycloak + the BFF must already be running on the host with
the test-reset gate enabled. From the repo root, use the same overlay file
the `e2e` profile uses (so `ENABLE_TEST_RESET=true` lands on the BFF):

```sh
docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up -d keycloak bff
```

Bringing up only `keycloak` and `bff` (not `playwright`) leaves the runner
inactive — you'll drive the specs from the host instead.

Then, from this directory:

```sh
cd e2e
npm ci
npx playwright install --with-deps chromium
TEST_RESET_TOKEN=$TEST_RESET_TOKEN \
BFF_CLIENT_SECRET=$BFF_CLIENT_SECRET \
OIDC_CLIENT_ID=bmad-books-bff \
KEYCLOAK_INTERNAL_URL=http://localhost:8080 \
  npm test
```

`KEYCLOAK_INTERNAL_URL=http://localhost:8080` is the host-side value
(Keycloak's `:8080` is published per `compose/infra.yml`); the compose
runner uses `http://keycloak:8080` instead and the playwright service in
`compose/app.yml` sets it automatically.

`npm test` invokes `playwright test` with the configuration in
`playwright.config.ts`. Post-Epic-6 the fully containerised stack (Keycloak +
BFF + RS + SPA SSR edge) is the only supported E2E target. The `dev` profile
and the `ng serve` / `spa/proxy.conf.json` host-side workflow were retired by
Story 6.1. The helpers (`fixtures/helpers.ts`) target `http://localhost:4000`
by default (`baseURL` in the config — flipped from `:8000` by Story 6.4).

Pick the `baseURL` based on which stack you're targeting:

- **Fully containerised stack** (SPA SSR edge on `:4000` proxies the BFF): the
  default `http://localhost:4000` is correct — leave `E2E_BASE_URL` unset.

## Running via compose

From the repo root, use the `just` recipe (which wraps the canonical
multi-file compose invocation):

```sh
just e2e-up
```

Equivalent to:

```sh
docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit
```

This builds the `playwright` runner image, starts Keycloak + BFF, waits for both
to report healthy, then launches the runner against the live stack. The runner
is one-shot — when the test process exits (pass or fail), `--abort-on-container-exit`
tears down the rest of the stack. Test artifacts (traces, screenshots, videos
from failed runs) land in `e2e/test-results/` on the host via the bind mount.

## Environment variables

- `E2E_BASE_URL` — base URL Playwright navigates to. Defaults to
  `http://localhost:4000` (SPA SSR edge, the browser-facing origin post-Epic-6).
  The `e2e` compose profile sets it to `http://localhost:4000` automatically
  via `compose/app.yml` playwright service `E2E_BASE_URL` (Story 6.4 flip).
  The `ng serve` / `:4200` override and the `dev` profile were retired by
  Story 6.1.
- `TEST_RESET_TOKEN` — bearer token required by `resetState` and by the J5
  spec's `GET /v1/test/session-debug` capture. Must be set in the repo-root
  `.env` for either workflow; the `e2e` profile forwards it to the runner
  container. The `BFF` side is validated by Story 1.12; the `session-debug`
  variant is added in Story 1.13. The `:?` fail-fast on `compose/app.e2e.yml`
  refuses to start the e2e profile when this var is unset.
- `BFF_CLIENT_SECRET` — confidential client secret shared with the
  `bmad-books-bff` Keycloak client. Required by the J5 spec's refresh-token
  revocation assertion: it POSTs `grant_type=refresh_token` directly to
  Keycloak's `/token` endpoint, which 400s with `invalid_client` instead of
  the expected `invalid_grant` if the secret is missing. The `e2e` compose
  profile sets it on the runner via `${BFF_CLIENT_SECRET:?...}` — fail-fast
  when unset.
- `OIDC_CLIENT_ID` — Keycloak client id the BFF authenticates as. Defaults
  to `bmad-books-bff` (the value seeded in `keycloak/realm-bmad-books.json`).
  Used alongside `BFF_CLIENT_SECRET` in the J5 refresh-grant assertion.
- `KEYCLOAK_INTERNAL_URL` — base URL of Keycloak from the perspective of the
  Playwright runner. Set to `http://localhost:8080` for the local-dev
  workflow and `http://keycloak:8080` for the compose-network workflow; the
  `e2e` compose profile sets it automatically. Required for the J5
  refresh-token revocation POST (the runner cannot resolve
  `localhost:8080` to Keycloak from inside a container).
- `RS_BASE_URL` — base URL of the Resource Server from the runner's
  perspective. Defaults to `http://resource-server:8000` (correct for the
  `e2e` compose profile, where the runner reaches the RS via the compose
  network). Consumed by `resetState`'s RS-side `POST /v1/test/reset`
  (Story 3.6 extension of the Story 1.12 helper). Host-side workflow
  cannot easily reach the RS — see "RS killswitch (J4 + J6)" below.
- `COMPOSE_PROJECT_NAME` — Compose v2 project-name prefix. Defaults to
  `bmad-books` and is set by the `e2e` profile on the playwright service
  via `${COMPOSE_PROJECT_NAME:-bmad-books}`. Pinned so the runner's
  `docker compose stop|start resource-server` (issued via the bound docker
  socket) targets the right container — without this pin the runner's
  working directory `/e2e` would derive project name `e2e` and the lookup
  would resolve to nothing.

## RS killswitch (J4 + J6)

Story 3.6's `killRs` / `startRs` helpers (`fixtures/helpers.ts` thin facade
over `fixtures/services.ts`) shell out to `docker compose stop|start
resource-server`. Inside the playwright runner container, the host docker
daemon is reachable via the `/var/run/docker.sock` bind defined on the
playwright service in `compose/app.yml`. From the host, `npm test` shells
out to the same daemon (Docker Desktop on macOS / Linux), so the helpers
work in both workflows without modification.

The compose-network `RS_BASE_URL=http://resource-server:8000` is the
canonical target. The host-side workflow has a known constraint: the RS has
NO `ports:` block in `compose/app.yml` (architecture §F3 / §I6 — only the
BFF exposes a user-facing port), so `resetState`'s RS-side POST cannot
reach the RS from the host on `http://localhost:<port>`.

Workarounds:

1. **Run via compose (canonical):** `just e2e-up` from the repo root. The
   runner is in the compose network and reaches the RS via DNS at
   `http://resource-server:8000`. This is the workflow `just e2e-up` exists
   to support and the one the close gate (AC16, Story 3.6) requires.
2. **Temporary host port (ad-hoc):** add `ports: ["8001:8000"]` to the
   `resource-server` block in your local `compose/app.yml` (do NOT commit)
   and export `RS_BASE_URL=http://localhost:8001` before running `npm test`
   from `e2e/`. Useful for fast-iteration debugging; not a documented
   long-term workflow.

## Specs in this directory

- `tests/j1-first-login.spec.ts` (Story 1.13) — J1: drives an unauthenticated
  visitor through `/login`, the OAuth round-trip against the real Keycloak,
  and back to the `/books` placeholder; also asserts the `authGuard`
  redirect-with-`return_to` flow.
- `tests/j5-logout.spec.ts` (Story 1.13) — J5: clicks `Log out` from the
  authenticated `TopChrome`, asserts the session cookie is cleared and the
  protected route bounces back to `/login`; then captures the stored
  refresh_token via the test-only `GET /v1/test/session-debug` and asserts
  Keycloak rejects a refresh-grant attempt with `error=invalid_grant`.
- `tests/j2-manage-books.spec.ts` (Story 2.7) — J2: drives the full
  manage-books journey for `testuser` — adding a book, optimistic
  status change with reload-survives, edit with replace-then-save,
  cancel-edit, delete via native confirm (accept + dismiss), client-
  side validation rendering for `pages=0`, and cross-user isolation
  between `testuser` and `freshuser`. Relies on Story 2.3's books
  truncation in `/v1/test/reset` for test isolation.
- `tests/j4-adjust-speed.spec.ts` (Story 3.6) — J4: adjust reading speed,
  including freshuser unset state, Saved pulse, validation, and
  RS-unavailable error variants.
- `tests/j3-estimate.spec.ts` (Story 4.4) — J3: reading-time estimate happy
  path (default speed), J4↔J3 coupling (speed change yields different
  estimate), freshuser 412 precondition with link to /settings, in-place
  re-estimate, generic non-J6 failure with the generic copy ("Couldn’t get
  an estimate — try again"). Pessimistic UI throughout — no silent retry.
- `tests/j6-rs-unavailable.spec.ts` (Story 4.4) — J6: estimate while RS is
  down renders the named J6 error in the row's estimate cell, retry-after-
  RS-recovery succeeds (proving manual-retry rule), and settings save while
  RS is down renders the same copy (pinning the uniform 503 surface across
  estimate and settings).

## Adding a new spec

New specs live under `tests/` as `j<N>-<journey>.spec.ts` (one journey per
file). Always import `logInAs` and `resetState` from `fixtures/helpers.ts` —
do NOT inline Keycloak credential-filling logic, and do NOT inline HTTP calls
to `/v1/test/reset`. The seeded users (`testuser`, `freshuser`) are exported
from `fixtures/users.ts`. The harness runs sequentially (`workers: 1`) because
every spec is expected to call `resetState` in a `beforeEach`; do not change
that without rewriting the test-reset contract.

**Compose-runner gotcha (`docker compose run` cached image):** the playwright
runner image is built from `e2e/Dockerfile`, which does `COPY . .` — specs
are baked into the image at build time. `docker compose run` reuses the
cached image, so a freshly-added spec file will NOT appear in the runner
until the image is rebuilt. The canonical `just e2e-up` recipe passes
`--build` to the `run` step for exactly this reason (Story 4.4 dev
discovery: an unflagged `run` silently executed only the pre-Story-4.4 spec
set). If you invoke compose directly instead of through `just`, pass
`--build` on the `run` step or pre-build with
`docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e build playwright`.
Layer caching keeps the typical rebuild fast (~0.1s when only specs
changed). The host-side workflow (`npm test` from `e2e/`) is immune — it
reads specs directly from disk.

## RS test-reset extension

Story 3.6 replaced the `killRs` / `startRs` `: never` stubs in
`fixtures/helpers.ts` with real implementations that drive
`docker compose stop|start resource-server` via the host docker daemon
(socket-bound from the runner). The compose-CLI plumbing lives in
`fixtures/services.ts` (thin facade pattern); `helpers.ts` re-exports
`killRs` / `startRs` with idempotent guards (no-op when already in the
target state).

Story 3.6 also extended `resetState` to POST `/v1/test/reset` against
**both** services — the BFF (Story 1.12 — books, sessions, auth_states)
and the RS (Story 3.4 — reading_speeds) — using the same
`TEST_RESET_TOKEN` bearer. The signature is unchanged from Story 1.11/2.3
(`request, opts: { resetToken }`) so existing call sites in
`j1-first-login.spec.ts` / `j5-logout.spec.ts` continue to work without
edits. The RS URL is configurable via `RS_BASE_URL` (defaults to
`http://resource-server:8000` — the compose-network value).
