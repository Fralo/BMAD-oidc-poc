# E2E — Playwright Harness

Playwright project for the Reading Time Estimator. Drives the SPA + BFF +
Keycloak round-trip end-to-end against the real running compose stack; nothing
is mocked. Specs land alongside the features they verify (Stories 1.13, 2.7,
3.6, 4.4 — one journey per spec file).

## Running locally

Prerequisites: the backend + Keycloak must already be running on the host. From
the repo root:

```sh
docker compose --profile dev up -d
```

Then, from this directory:

```sh
cd e2e
npm ci
npx playwright install --with-deps chromium
npm test
```

`npm test` invokes `playwright test` with the configuration in
`playwright.config.ts`. The `dev` profile excludes the SPA — `ng serve` is
expected to be running on the host if a spec needs the SPA in the loop. The
helpers (`fixtures/helpers.ts`) target `http://localhost:8000` by default
(`baseURL` in the config).

## Running via compose

From the repo root:

```sh
docker compose --profile e2e up --abort-on-container-exit
```

This builds the `playwright` runner image, starts Keycloak + BFF, waits for both
to report healthy, then launches the runner against the live stack. The runner
is one-shot — when the test process exits (pass or fail), `--abort-on-container-exit`
tears down the rest of the stack. Test artifacts (traces, screenshots, videos
from failed runs) land in `e2e/test-results/` on the host via the bind mount.

## Environment variables

- `E2E_BASE_URL` — base URL for the SPA + BFF. Defaults to
  `http://localhost:8000` for the local-dev workflow. The `e2e` compose profile
  sets it to `http://bff:8000` automatically so the runner reaches the BFF via
  the compose network.
- `TEST_RESET_TOKEN` — bearer token required by `resetState`. Must be set in
  the repo-root `.env` for either workflow; the `e2e` profile forwards it to
  the runner container. Story 1.12 lands the actual BFF endpoint that validates
  this token; until then, `resetState` calls will return 404 (route not
  registered, by design).

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
