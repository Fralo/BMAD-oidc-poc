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
`playwright.config.ts`. The `dev` profile excludes the SPA — `ng serve` is
expected to be running on the host if a spec needs the SPA in the loop. The
helpers (`fixtures/helpers.ts`) target `http://localhost:8000` by default
(`baseURL` in the config).

Pick the `baseURL` based on which stack you're targeting:

- **Fully containerized stack** (BFF serves the built SPA bundle): the default
  `http://localhost:8000` is correct — leave `E2E_BASE_URL` unset.
- **Local dev with `ng serve`** (the typical Angular dev workflow under the
  `dev` profile): export `E2E_BASE_URL=http://localhost:4200` before running
  `npm test`. The SPA's `/login` route is served by `ng serve` at `:4200`
  (the BFF has no `/login` endpoint); `ng serve`'s proxy (`spa/proxy.conf.json`)
  forwards `/auth`, `/api`, and `/v1` calls back to the BFF at `:8000`.

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
  `http://localhost:8000`, which is correct when targeting the fully
  containerized stack (BFF serves the built SPA bundle). Override to
  `http://localhost:4200` when targeting `ng serve` under the `dev` profile,
  since the SPA's `/login` route lives on the dev server (not the BFF). The
  `e2e` compose profile sets it to `http://bff:8000` automatically so the
  runner reaches the BFF via the compose network.
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

## Adding a new spec

New specs live under `tests/` as `j<N>-<journey>.spec.ts` (one journey per
file). Always import `logInAs` and `resetState` from `fixtures/helpers.ts` —
do NOT inline Keycloak credential-filling logic, and do NOT inline HTTP calls
to `/v1/test/reset`. The seeded users (`testuser`, `freshuser`) are exported
from `fixtures/users.ts`. The harness runs sequentially (`workers: 1`) because
every spec is expected to call `resetState` in a `beforeEach`; do not change
that without rewriting the test-reset contract.

## RS test-reset extension

The `resetState` helper currently only hits the BFF's `POST /v1/test/reset`
endpoint. Story 3.4 will land the equivalent RS endpoint and extend
`resetState` to also POST to it (the second argument is an options object so
new fields can be added without breaking call sites). Story 3.6 will replace
the `killRs` / `startRs` stubs in `fixtures/helpers.ts` with real
implementations that drive `docker compose stop resource-server` /
`docker compose start resource-server` (or an equivalent compose-CLI
mechanism).
