---
status: ready-for-dev
story_key: 3-6-e2e-spec-j4-adjust-reading-speed-compose-e2e-profile-killrs-startrs-resetstate-helpers
epic: 3
prerequisites: 3.1 (done — RS scaffold + `/health` + compose `default`/`dev` profiles); 3.2 (done — RS `oidc_bearer` + scope enforcement + synthetic-IdP harness); 3.3 (done — RS `ReadingSpeed` model + `/v1/reading-speed` GET/PUT, scope-gated); 3.4 (done — RS `POST /v1/test/reset`); 3.5 (done — BFF `ResourceServerClient` w/ refresh-and-replay + `/v1/reading-speed` proxy + SPA `SettingsPage` + `/settings` route); 1.11 (done — Playwright project + fixtures); 1.12 (done — `compose/app.e2e.yml` overlay + `${TEST_RESET_TOKEN:?...}` pattern); 1.13 (done — J1 + J5 specs; `requireEnv` pattern)
created: 2026-05-17
---

# Story 3.6: E2E spec — J4 adjust reading speed + compose `e2e` profile updates + `killRs`/`startRs`/`resetState` helpers

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a reviewer of the OAuth/OIDC reference,
I want a Playwright E2E spec that drives the full J4 journey against the running stack — including the `freshuser` unset state, a successful save with the `"Saved"` pulse, persistence across page reload, validation rejection, and a `503`-on-save when the RS is down — AND the compose `e2e` profile + helpers updated so `killRs` / `startRs` actually work (preparing Epic 4's J6 spec),
So that the fourth journey is demonstrably correct on every CI-style run and the harness is ready for J6 the moment Epic 4 ships.

## Scope (read this first)

This story is **the J4 E2E spec + the harness extensions that J4 needs to drive a real running stack**. The BFF / RS / SPA implementations all landed in Stories 3.1–3.5; this story consumes them via Playwright.

Concretely, this story delivers:

1. `compose/app.yml` — the `resource-server` service's `profiles:` list extends from `[default, dev]` to `[default, dev, e2e]` so the RS container is included when the `e2e` profile is activated (without this, the playwright `depends_on: resource-server` would never resolve under e2e). [compose/app.yml:98]
2. `compose/app.e2e.yml` — extended with a `resource-server:` block setting `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN: "${TEST_RESET_TOKEN:?...}"`. Same shape as the existing `bff:` block from Story 1.12. Also adds `AUTH_TYPE=oidc_bearer` on the RS so its `Authorization: Bearer <JWT>` validation is on (the RS `.env.example` defaults to `AUTH_TYPE=none` per its archetype heritage — Story 3.6 is the story that activates `oidc_bearer` end-to-end per the comment at `services/resource-server/.env.example:50-52`).
3. `compose/app.yml` — the `playwright` service's `depends_on:` adds `resource-server: { condition: service_healthy }`; `volumes:` mounts `/var/run/docker.sock`; `environment:` adds `RS_BASE_URL`, `COMPOSE_PROJECT_NAME`. [compose/app.yml:101-144]
4. `e2e/Dockerfile` — Docker CLI + compose plugin installed so the runner can `docker compose stop|start resource-server` against the host daemon via the bound socket.
5. `e2e/fixtures/services.ts` (NEW) — owns the compose-CLI plumbing (`stopRs`, `startRs`, `isRsRunning`, `waitForRsHealthy`) so `helpers.ts` stays a thin facade.
6. `e2e/fixtures/helpers.ts` — `killRs()` / `startRs()` go from `: never` stubs (lines 50, 57) to real idempotent `Promise<void>` implementations; `resetState(request, opts)` (line 31) extends to also POST to the RS's `/v1/test/reset` with the same bearer token. Signature unchanged so J1 / J5 specs continue without edits.
7. `e2e/tests/j4-adjust-speed.spec.ts` (NEW) — five Playwright tests covering AC9–AC14 below.
8. `e2e/README.md` — "Environment variables" gains `RS_BASE_URL` + `COMPOSE_PROJECT_NAME`; new "RS killswitch" subsection documents the docker-socket binding; "Specs in this directory" gains the J4 entry; "RS test-reset extension" moves from forward-pointer to present-tense.

Out of scope for 3.6: any SPA component code (Stories 3.5), any BFF / RS endpoint code (Stories 3.1 / 3.3 / 3.4 / 3.5), any new `AppError` discriminated-union variants (3.5 landed `resource_server_unavailable`; 4.3 will land `reading_speed_unset` if needed), the J6 RS-unavailable spec (Story 4.4 — but the `killRs` infra this story ships is **what J6 will use**), the J2 books-manage spec (Story 2.7). No `spa/**` files. No `services/**` files. No new compose profiles.

## Acceptance Criteria

### Compose `e2e` profile updates

**AC1 — `compose/app.yml` `resource-server` service joins the `e2e` profile.**

In `compose/app.yml`, the `resource-server` service's `profiles:` field (currently `[default, dev]` at `compose/app.yml:98`) is changed to `[default, dev, e2e]`. This is the minimal one-line change that makes the RS container participate in the e2e profile (mirroring the BFF's `[default, dev, e2e]` at `compose/app.yml:57`). The Story-3.1 comment at `compose/app.yml:64-67` ("Profiles are `default` + `dev` only; the `e2e` profile addition lands in Story 3.6") becomes obsolete — update it to reflect the present-tense reality.

The `compose/app.yml:65-67` comment block also references "the `ENABLE_TEST_RESET=true` overlay and the `killRs`/`startRs`/`resetState` helper extensions" — that hand-off is exactly this story. Refresh the comment to point at the now-active `compose/app.e2e.yml` `resource-server` block instead of forward-referencing 3.6.

**AC2 — `compose/app.e2e.yml` overlay extends the `resource-server` service for the e2e profile.**

`compose/app.e2e.yml` (currently 33 lines, BFF-only per Story 1.12) gains a `resource-server:` block alongside the existing `bff:` block:

```yaml
  resource-server:
    environment:
      ENABLE_TEST_RESET: "true"
      TEST_RESET_TOKEN: "${TEST_RESET_TOKEN:?TEST_RESET_TOKEN is required when the e2e profile is up}"
      # Story 3.6 activates oidc_bearer end-to-end (the RS .env.example notes
      # this at line 50-52: "the actual wiring flips in Story 3.3 / 3.6").
      # Without this, the RS runs in AUTH_TYPE=none and treats every caller as
      # an unauthenticated synthetic admin — J4's scope-enforcement coverage
      # would silently degrade.
      AUTH_TYPE: oidc_bearer
```

The same `${TEST_RESET_TOKEN:?...}` fail-fast pattern Story 1.12 uses for the BFF — keeps the single source of truth (the repo-root `.env`), and the bearer token is identical for both services so a single helper call hits both. Do NOT duplicate the var into a separate `RS_TEST_RESET_TOKEN` — the architecture documented "Both endpoints require a shared bearer token from `TEST_RESET_TOKEN` env var" (architecture.md §"Operational Details" line 1359).

Update the file's header docstring to mention the RS extension. The `just e2e-up` recipe in the repo-root `Justfile` already wraps `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up` and continues to work unchanged.

**AC3 — `compose/app.yml` `playwright` service depends on RS health.**

The existing `playwright` service block in `compose/app.yml:101-144` is modified so its `depends_on:` adds the `resource-server` entry:

```yaml
    depends_on:
      bff:
        condition: service_healthy
      keycloak:
        condition: service_healthy
      resource-server:
        condition: service_healthy
```

This guarantees the runner does not start until the RS `/health` is 200 (DB reachable + Alembic at head + JWKS fetchable, per Story 3.1's healthcheck contract).

**AC4 — `compose/app.yml` `playwright` service mounts the docker socket and sets `COMPOSE_PROJECT_NAME`.**

The `playwright` service block is also modified to add:

```yaml
    volumes:
      - ../e2e/test-results:/e2e/test-results
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      # ... existing E2E_BASE_URL, TEST_RESET_TOKEN, OIDC_CLIENT_ID,
      # BFF_CLIENT_SECRET, KEYCLOAK_INTERNAL_URL …
      RS_BASE_URL: http://resource-server:8000
      COMPOSE_PROJECT_NAME: ${COMPOSE_PROJECT_NAME:-bmad-books}
```

Why each:

- The docker-socket bind lets the runner shell out to `docker compose stop resource-server` and `docker compose start resource-server` from inside the container, hitting the host daemon (standard Docker-in-Docker-via-socket pattern). Read-write — `stop`/`start` are write operations.
- `COMPOSE_PROJECT_NAME` is the prefix Compose v2 derives from the directory containing `docker-compose.yml`. From inside the runner container, the working directory is `/e2e`, so the default project name would be `e2e` (wrong — would target nothing). Pinning to the repo-root project name (`bmad-books` by default, overridable in `.env`) ensures `docker compose stop resource-server` finds the right container.
- `RS_BASE_URL` so `resetState`'s new RS-side POST has a configurable target (the runner needs to reach the RS at `http://resource-server:8000` on the compose network, NOT `localhost`). The helper falls back to that default if the env is unset (AC7).

Document the security boundary inline on the volume bind — the runner is local-only and treated as trusted; production hardening is Story 5.2's territory.

### `e2e/Dockerfile` extension

**AC5 — `e2e/Dockerfile` installs Docker CLI + compose plugin.**

The runner needs the `docker` binary and the `compose` plugin to shell out. Insert an apt-install layer AFTER `WORKDIR /e2e` and BEFORE `COPY package.json package-lock.json ./` (layer-cache ordering — apt deps change less often than fixtures/specs):

```dockerfile
# Story 3.6: Docker CLI + compose plugin for killRs/startRs. The daemon
# comes from the host via the /var/run/docker.sock bind in compose/app.yml;
# we install only the client + compose plugin here.
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
  && install -m 0755 -d /etc/apt/keyrings \
  && curl -fsSL https://download.docker.com/linux/debian/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
  && chmod a+r /etc/apt/keyrings/docker.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
       > /etc/apt/sources.list.d/docker.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
  && rm -rf /var/lib/apt/lists/*
```

Verification: `docker compose version` inside the built image emits a v2.x line. From the runner started under `e2e` profile, `docker compose ps --services` lists `bff`, `keycloak`, `resource-server`, `playwright` (the socket bind works and `COMPOSE_PROJECT_NAME` aligns).

**Do NOT** install `docker-ce` (the daemon). Only `docker-ce-cli` + `docker-compose-plugin`.

### Helper extensions

**AC6 — `e2e/fixtures/services.ts` (NEW) owns the compose-CLI plumbing.**

Create `e2e/fixtures/services.ts` exporting:

```ts
export async function stopRs(): Promise<void>            // docker compose stop resource-server
export async function startRs(): Promise<void>           // docker compose start resource-server
export async function isRsRunning(): Promise<boolean>    // docker compose ps --format json resource-server
export async function waitForRsHealthy(timeoutMs?: number): Promise<void>  // docker inspect health-status poll
```

Implementation contract:

- Uses `util.promisify(child_process.execFile)` (injection-safe — `execFile` doesn't go through a shell). Each call: `execFile('docker', ['compose', 'stop'|'start', 'resource-server'], { encoding: 'utf8' })`.
- `isRsRunning()`: invoke `docker compose ps --format json resource-server`. Compose v2 emits NDJSON (one object per line) in v2.20+; older v2.x emits a single JSON array — parse both shapes defensively. Return `true` iff there's a line whose `.State === 'running'`.
- `waitForRsHealthy(timeoutMs = 30_000)`: poll `docker inspect --format '{{.State.Health.Status}}' resource-server` every 500ms until the trimmed stdout equals `healthy`. Throw on timeout with `Error('RS did not become healthy within ${timeoutMs}ms; last status: ${last}')`. The container has a healthcheck per Story 3.1 (compose/app.yml:89-97).
- `stopRs` / `startRs`: thin wrappers. Don't wait for healthy in `stopRs` (transitioning to stopped); do wait for healthy AFTER `startRs` (the caller wants a usable RS).
- Capture stdout + stderr on every call. On error, throw with the full captured streams in the message — failing CI runs need the diagnostic inline.

**AC7 — `e2e/fixtures/helpers.ts` `killRs()` + `startRs()` real implementations.**

Replace the `: never`-returning stubs at `e2e/fixtures/helpers.ts:50` and `e2e/fixtures/helpers.ts:57`:

```ts
import {
  isRsRunning,
  startRs as startRsService,
  stopRs,
  waitForRsHealthy,
} from './services';

/**
 * Stops the resource-server container via the host docker daemon
 * (socket-bound). Idempotent: if the container is already stopped, no-op.
 *
 * Used by J4's "RS down" tests (this story) and J6 (Story 4.4).
 */
export async function killRs(): Promise<void> {
  if (!(await isRsRunning())) return;
  await stopRs();
}

/**
 * Starts the resource-server container and waits for its /health probe to
 * report 200. Idempotent: if the container is already running, just waits
 * for healthy (cheap if already there) and returns.
 *
 * The J4 spec uses this in an `afterEach` to guard against a previous test
 * having left the RS stopped.
 */
export async function startRs(): Promise<void> {
  if (!(await isRsRunning())) {
    await startRsService();
  }
  await waitForRsHealthy();
}
```

Both idempotent (verified explicitly by the AC9 `afterEach` + AC13/AC14 in-test calls). The return type changes from `: never` to `Promise<void>` — deliberate breaking type change. No current callers exist (`grep -rn "killRs\|startRs" e2e/` shows zero usage sites today); J4 is the first consumer. The Story 2.7 J2 spec (currently `backlog` in Epic 2 worktree) does not call them.

**AC8 — `e2e/fixtures/helpers.ts` `resetState()` extended to also POST to the RS.**

The existing `resetState(request, opts)` at `e2e/fixtures/helpers.ts:31-44` POSTs once to `/v1/test/reset` (the BFF, served at the runner's `baseURL`). Extend it to also POST to the RS's `/v1/test/reset` with the same bearer:

```ts
export async function resetState(
  request: APIRequestContext,
  opts: { resetToken: string },
): Promise<void> {
  // BFF reset — truncates books, sessions, auth_states (Story 1.12 / 2.3).
  const bffResp = await request.post('/v1/test/reset', {
    headers: { Authorization: `Bearer ${opts.resetToken}` },
  });
  if (bffResp.status() !== 204) {
    const body = await bffResp.text();
    throw new Error(
      `resetState: BFF expected HTTP 204 from POST /v1/test/reset, got ${bffResp.status()}. Body: ${body}`,
    );
  }

  // RS reset — truncates reading_speeds (Story 3.4). Story 3.6 wires this in.
  // Compose runner reaches RS at http://resource-server:8000; host-side
  // workflow targets the RS's published port (set RS_BASE_URL accordingly).
  const rsBaseUrl = process.env.RS_BASE_URL ?? 'http://resource-server:8000';
  const rsResp = await request.post(`${rsBaseUrl}/v1/test/reset`, {
    headers: { Authorization: `Bearer ${opts.resetToken}` },
  });
  if (rsResp.status() !== 204) {
    const body = await rsResp.text();
    throw new Error(
      `resetState: RS expected HTTP 204 from POST ${rsBaseUrl}/v1/test/reset, got ${rsResp.status()}. Body: ${body}`,
    );
  }
}
```

Why a separate `RS_BASE_URL`: the RS is NOT same-origin with the SPA / BFF. The runner's `baseURL` is `http://bff:8000` (compose) or `http://localhost:8000` (host); the RS is at `http://resource-server:8000` (compose) or `http://localhost:<published-port>` (host — but RS has no `ports:` block in `compose/app.yml`, see Dev Notes §"Host-side RS access").

Signature unchanged from Story 1.11/2.3 — `(request, opts)`, with `opts.resetToken` the only required field. Call sites in `j1-first-login.spec.ts` and `j5-logout.spec.ts` continue to work unchanged. If the BFF returns 204 but the RS returns 401 (wrong token), the helper throws on the RS step with a clear message — explicit failure, no silent half-reset.

### J4 spec — `e2e/tests/j4-adjust-speed.spec.ts`

**AC9 — File exists at `e2e/tests/j4-adjust-speed.spec.ts` and uses the standard describe + before/after pattern.**

```ts
import { expect, test } from '@playwright/test';

import { killRs, logInAs, resetState, startRs } from '../fixtures/helpers';
import { freshuser, testuser } from '../fixtures/users';

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Required env var ${name} is not set. See e2e/README.md "Environment variables" for the expected values.`,
    );
  }
  return value;
}

test.describe('J4: adjust reading speed', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
    await logInAs(page, testuser);
  });

  test.afterEach(async () => {
    // Defensive: a test that called killRs and threw before startRs would
    // leave the RS dead. startRs is idempotent — cheap when RS is already
    // running.
    await startRs();
  });

  // … tests AC10–AC14 below
});
```

Mirrors `j1-first-login.spec.ts` and `j5-logout.spec.ts` exactly: same `requireEnv` shim shape, same `beforeEach`/`afterEach` structure. Do NOT diverge.

**AC10 — Test: `freshuser sees the unset state on first /settings visit`.**

```ts
test('freshuser sees the unset state on first /settings visit', async ({
  page,
  request,
  context,
}) => {
  // Override the default testuser login from beforeEach. Order matters:
  //   1. resetState — truncates BFF sessions/auth_states + RS reading_speeds.
  //   2. context.clearCookies() — drops the testuser bff_session cookie that
  //      the beforeEach just set. Without this, the next page.goto('/login')
  //      runs with a stale cookie that points to a now-deleted DB row;
  //      authGuard's /api/me call gets 401, the interceptor clears the
  //      cookie and redirects to /login — works through the chain, but
  //      flakes under slow CI conditions. Clearing up front is deterministic.
  //   3. logInAs(freshuser) — fresh OAuth round-trip as freshuser.
  await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
  await context.clearCookies();
  await logInAs(page, freshuser);

  await page.goto('/settings');

  // Per Story 3.5 SettingsPage + UX-DR9: 412 unset renders empty input,
  // helper text "e.g., 30" as the only cue, NO ErrorMessage rendered.
  const input = page.getByLabel('Pages per hour');
  await expect(input).toBeVisible();
  await expect(input).toHaveValue('');
  await expect(page.getByText('e.g., 30')).toBeVisible();

  // The SettingsPage template (settings-page.html:15-23) renders
  // <app-error-message> only when validationError / loadErrorMessage /
  // saveErrorMessage is non-null. For freshuser's 412, all three are null
  // → zero <app-error-message> elements on the page.
  await expect(page.locator('app-error-message')).toHaveCount(0);
});
```

**AC11 — Test: `setting a value shows the Saved pulse and persists across reload`.**

```ts
test('setting a value shows the Saved pulse and persists across reload', async ({
  page,
}) => {
  await page.goto('/settings');

  await page.getByLabel('Pages per hour').fill('30');

  // CRITICAL: lock to a stable selector that survives the button-text change.
  //
  // The button's accessible name changes Save → Saving… → Saved → Save
  // (settings-page.html:24-30 + settings-page.ts:49-53 saveButtonLabel
  // computed). page.getByRole('button', { name: 'Save' }) re-queries each
  // assertion; once the text becomes "Saved", that query returns 0 matches
  // and the toHaveText assertion times out with "0 elements".
  //
  // Use the class-name selector instead — the .settings-save class is
  // stable across label transitions.
  const saveButton = page.locator('button.settings-save');
  await saveButton.click();

  // Per UX-DR9 + Story 3.5 ReadingSpeedService.save: the button briefly
  // relabels to "Saved" for ~1s (JUST_SAVED_PULSE_MS = 1000 in
  // reading-speed-service.ts:25). 2000ms timeout is comfortable headroom.
  await expect(saveButton).toHaveText('Saved', { timeout: 2000 });

  // Reload triggers ReadingSpeedService.load() → GET /v1/reading-speed →
  // 200 {pages_per_hour: 30} → input populated.
  await page.reload();
  await expect(page.getByLabel('Pages per hour')).toHaveValue('30');
});
```

The spec does NOT assert the post-pulse return to `"Save"` — that'd test implementation timing (the ~1s pulse window) without adding meaningful coverage. The unit tests in `settings-page.spec.ts` (already shipped by Story 3.5) verify the precise pulse behavior; this E2E asserts the user-visible "value persisted on reload" outcome.

**AC12 — Test: `validation rejects pages_per_hour = 0 and preserves the typed value`.**

```ts
test('validation rejects pages_per_hour = 0 and preserves the typed value', async ({
  page,
}) => {
  await page.goto('/settings');

  // Track whether the PUT is fired. Register the route handler BEFORE the
  // click so the GET that already fired on page-load passes through; only
  // a subsequent PUT would flip the flag.
  let putWasFired = false;
  await page.route('**/v1/reading-speed', (route) => {
    if (route.request().method() === 'PUT') {
      putWasFired = true;
    }
    return route.continue();
  });

  await page.getByLabel('Pages per hour').fill('0');
  await page.locator('button.settings-save').click();

  // Per Story 3.5 settings-page.ts:116-118: the regex /^[1-9]\d*$/ rejects
  // '0' (leading zero blocked); _validationError.set('Enter a positive
  // number'); the function returns BEFORE calling save() — no PUT fires.
  // The ErrorMessage component renders the literal text.
  await expect(page.getByText('Enter a positive number')).toBeVisible();
  await expect(page.getByLabel('Pages per hour')).toHaveValue('0');
  expect(putWasFired).toBe(false);
});
```

The `page.route('**/v1/reading-speed', ...)` glob matches both GET (which fired on page-load) and PUT (which must NOT fire). `route.continue()` lets the GET pass through; the closure flips only on PUT.

**AC13 — Test: `save while RS is down renders the named 503 error`.**

```ts
test('save while RS is down renders the named 503 error', async ({ page }) => {
  await killRs();

  await page.goto('/settings');

  // ReadingSpeedService.load() fires on ngOnInit (settings-page.ts:102-104),
  // gets 503 from the BFF (BFF proxy → RS unreachable → 503
  // resource_server_unavailable per Story 3.5), and finally{} sets
  // loading.set(false) — so the input is NOT disabled when we try to fill it.
  //
  // The load-error renders the same 503 copy as the save-error (the load
  // and save error variants both surface "Service unavailable — try again
  // shortly" per settings-page.ts:60-67 + 76-86). That's expected; this
  // test focuses on the save-path 503 specifically by typing + clicking.
  await page.getByLabel('Pages per hour').fill('30');
  await page.locator('button.settings-save').click();

  // The named 503 copy per UX-DR12 — emitted by either loadErrorMessage or
  // saveErrorMessage (both produce the same string for kind:
  // 'resource_server_unavailable'). Use toBeVisible on the literal text;
  // multiple error messages with the same copy are fine — toBeVisible
  // passes when at least one matches.
  await expect(
    page.getByText('Service unavailable — try again shortly').first(),
  ).toBeVisible();

  // Restore so subsequent tests don't inherit a dead RS. The afterEach also
  // calls startRs — belt-and-suspenders, idempotent.
  await startRs();
});
```

**AC14 — Test: `load while RS is down renders the named 503 error`.**

```ts
test('load while RS is down renders the named 503 error', async ({ page }) => {
  await killRs();

  // Fresh navigation triggers ReadingSpeedService.load() → GET
  // /v1/reading-speed → BFF proxy → RS unreachable → BFF emits 503
  // resource_server_unavailable → SettingsPage's loadErrorMessage computed
  // produces "Service unavailable — try again shortly".
  await page.goto('/settings');

  await expect(
    page.getByText('Service unavailable — try again shortly'),
  ).toBeVisible();

  await startRs();
});
```

### Harness contract + gates

**AC15 — Specs use only the helpers from `fixtures/helpers.ts`.**

No `page.evaluate(() => fetch(...))` for the reset endpoint. No inline `child_process.execFile('docker', ...)` in the spec body. No inline Keycloak credential filling (`logInAs` is the sole truth). No tokens hardcoded in the spec — always `requireEnv('TEST_RESET_TOKEN')`. This is the Story-1.13-codified rule (epics.md line 1509 echoes it for 3.6).

**AC16 — Live-stack acceptance: `just e2e-up` exits 0 with all journey specs green.**

Per Epic 1 retro action item P2 ("Compose-stack ACs run live or are explicitly downgraded"), this story's `done` gate requires:

```sh
just e2e-up
```

(equivalent to `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit`)

exits 0 and the runner's stdout shows:

- The previously-passing J1 + J5 specs (Story 1.13) still pass.
- The J2 spec (Story 2.7) if landed by 3.6 implementation time, still passes.
- The five J4 specs (AC10–AC14) all pass.
- Traces / screenshots / videos for any failure land under `e2e/test-results/` on the host (existing bind-mount from Story 1.11).

If this AC cannot be met because of a defect in 3.1–3.5 (unlikely — all are `done` — but possible if 3.6's selector assumptions hit edge cases), the story stays in `review` with a deferred-work entry pointing at the upstream defect. Do NOT close based on static gates alone — retro P2.

**AC17 — Static + lint gates remain green.**

- `cd e2e && npx tsc --noEmit` — exit 0. The new `services.ts` and the modified `helpers.ts` typecheck. `child_process` + `util.promisify` are satisfied by `@types/node` (direct devDep from Story 1.11 per `e2e/package.json:11`).
- `cd e2e && npx playwright test --list` — exit 0; reports J1, J5, (J2 if present), and 5 × J4 specs.
- `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` — exit 0. The `playwright` service shows the new env vars (`RS_BASE_URL`, `COMPOSE_PROJECT_NAME`) + the docker-socket volume bind + the `resource-server: service_healthy` depends_on entry; the `resource-server` service shows the e2e-overlay env vars (`ENABLE_TEST_RESET=true`, `TEST_RESET_TOKEN`, `AUTH_TYPE=oidc_bearer`).
- `docker compose --profile dev config --services` — emits `keycloak`, `bff`, `resource-server` (no `playwright`). Regression check.
- `docker compose --profile default config --services` — same as dev (no `playwright`).

Capture all transcripts in the Dev Agent Record's Debug Log References.

## Tasks / Subtasks

- [ ] **Task 1 — Add `e2e` to `compose/app.yml` `resource-server` profiles list** (AC: #1)
  - [ ] 1.1 Open `compose/app.yml`; locate the `resource-server` service block (starts at line 60). Find the `profiles: [default, dev]` line (line 98). Change to `profiles: [default, dev, e2e]`.
  - [ ] 1.2 Update the comment block at lines 64–67 — replace "Profiles are `default` + `dev` only; the `e2e` profile addition lands in Story 3.6 paired with the `ENABLE_TEST_RESET=true` overlay and the `killRs`/`startRs`/`resetState` helper extensions." with present-tense prose describing the now-active wiring (e2e overlay in `compose/app.e2e.yml` activates `ENABLE_TEST_RESET=true` + `AUTH_TYPE=oidc_bearer`; `killRs`/`startRs` real impl lives in `e2e/fixtures/services.ts`).
  - [ ] 1.3 `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config --services` — confirm exit 0 and `resource-server` is in the list.

- [ ] **Task 2 — Extend `compose/app.e2e.yml` with the `resource-server` block** (AC: #2)
  - [ ] 2.1 Open `compose/app.e2e.yml` (currently 33 lines, BFF-only per Story 1.12).
  - [ ] 2.2 Append a `resource-server:` block under `services:` with `ENABLE_TEST_RESET=true`, `TEST_RESET_TOKEN: "${TEST_RESET_TOKEN:?...}"`, and `AUTH_TYPE=oidc_bearer` per AC2. Keep the existing `bff:` block exactly as-is.
  - [ ] 2.3 Update the file's header docstring to mention the RS extension in addition to the BFF one. Preserve the `include:`-vs-`-f` rationale paragraph verbatim (the Story-1.12 decision is still load-bearing).
  - [ ] 2.4 Confirm `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` exits 0 and the `resource-server` service in the config dump shows all three env vars.

- [ ] **Task 3 — Modify `compose/app.yml` `playwright` service** (AC: #3, #4)
  - [ ] 3.1 Open `compose/app.yml`; locate the `playwright:` block starting at line 101.
  - [ ] 3.2 In `depends_on:` (current contents at lines 116-120 — bff + keycloak), add the `resource-server: { condition: service_healthy }` entry. Keep alphabetical order: bff → keycloak → resource-server.
  - [ ] 3.3 In `volumes:` (currently a single `../e2e/test-results:/e2e/test-results` at line 142), add `- /var/run/docker.sock:/var/run/docker.sock` with a single-line comment: `# Docker-socket bind: enables killRs/startRs via host daemon. Trusted local-only; production hardening is Story 5.2 territory.`
  - [ ] 3.4 In `environment:` (currently ends at line 139 with `KEYCLOAK_INTERNAL_URL: http://keycloak:8080`), add `RS_BASE_URL: http://resource-server:8000` and `COMPOSE_PROJECT_NAME: ${COMPOSE_PROJECT_NAME:-bmad-books}`. The default-fallback `:-` is correct (a wrong project name would loud-fail when `docker compose stop` finds nothing; no silent corruption).
  - [ ] 3.5 Confirm `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` exits 0 and the `playwright` service shows all four additions.

- [ ] **Task 4 — Extend `e2e/Dockerfile` with the Docker CLI** (AC: #5)
  - [ ] 4.1 Open `e2e/Dockerfile` (current state: 26 lines per Story 1.11; `node:20-bookworm-slim` base; `WORKDIR /e2e`; `npm ci`; `npx playwright install --with-deps chromium`; `COPY . .`; `CMD ["npx", "playwright", "test", "--pass-with-no-tests"]`).
  - [ ] 4.2 Insert the docker-ce-cli + docker-compose-plugin RUN layer AFTER `WORKDIR /e2e` (currently line 10) and BEFORE `COPY package.json package-lock.json ./` (line 13). The placement matters for layer caching — apt deps change less often than npm/spec churn.
  - [ ] 4.3 Build the image: `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e build playwright`. Confirm exit 0.
  - [ ] 4.4 Smoke the CLI from a temporary container: `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e run --rm playwright sh -c 'docker compose version'`. Capture the v2.x version string in the Dev Agent Record.
  - [ ] 4.5 Leave `--pass-with-no-tests` in the `CMD` and in `e2e/package.json:7` `test` script. Once 3.6's J4 spec lands, the flag is a no-op (tests/ is non-empty), but it matches Story 1.11's documented stance.

- [ ] **Task 5 — Create `e2e/fixtures/services.ts`** (AC: #6)
  - [ ] 5.1 Create the file with the four exports from AC6. Use `util.promisify(child_process.execFile)`.
  - [ ] 5.2 `isRsRunning`: parse `docker compose ps --format json resource-server`. Handle BOTH the NDJSON-per-line shape (v2.20+) and the single-array shape (older v2.x) — wrap in `try { JSON.parse(stdout) }` first; if that fails, split by `\n`, filter non-empty lines, `JSON.parse` each. Return `state === 'running'`.
  - [ ] 5.3 `waitForRsHealthy`: poll `docker inspect --format '{{.State.Health.Status}}' resource-server` every 500ms with a 30s default timeout. Trim the output; only `healthy` returns. On timeout throw `Error('RS did not become healthy within 30000ms; last status: ${last}')`.
  - [ ] 5.4 `stopRs`, `startRs`: `execFile('docker', ['compose', 'stop'|'start', 'resource-server'])`. Capture stdout + stderr; on rejection re-throw with both streams in the message.
  - [ ] 5.5 Note in a module-level docstring: this module exists to keep `helpers.ts` a thin facade. Splitting the host-process plumbing out makes the harness easier to mock if anyone later writes a meta-spec for it.

- [ ] **Task 6 — Extend `e2e/fixtures/helpers.ts`** (AC: #7, #8)
  - [ ] 6.1 Open `e2e/fixtures/helpers.ts`; current `killRs` `: never` stub at line 50; `startRs` `: never` stub at line 57.
  - [ ] 6.2 Add `import { isRsRunning, startRs as startRsService, stopRs, waitForRsHealthy } from './services';` to the import block at the top.
  - [ ] 6.3 Replace both stubs with the `Promise<void>` implementations from AC7.
  - [ ] 6.4 Modify the existing `resetState` at line 31 per AC8: keep the BFF POST; add the RS POST with `process.env.RS_BASE_URL ?? 'http://resource-server:8000'`; throw with distinct messages per step.
  - [ ] 6.5 Run `cd e2e && npx tsc --noEmit`. Expect exit 0. No current callers depend on the `: never` shape — `grep -rn "killRs\|startRs" e2e/` to confirm zero existing usage before modifying.

- [ ] **Task 7 — Create `e2e/tests/j4-adjust-speed.spec.ts`** (AC: #9, #10, #11, #12, #13, #14)
  - [ ] 7.1 Create the file with the describe + `requireEnv` + `beforeEach` / `afterEach` from AC9.
  - [ ] 7.2 Add the five `test(...)` blocks for AC10–AC14 in that order. Test names verbatim from the AC headers.
  - [ ] 7.3 Use `page.locator('button.settings-save')` for the save button in AC11 / AC12 / AC13 — the accessible-name approach `getByRole('button', {name: 'Save'})` does NOT survive the label transition (see AC11's CRITICAL note). The `.settings-save` class is stable per `settings-page.html:26`.
  - [ ] 7.4 For AC10's no-error assertion, use `page.locator('app-error-message')` — the single Angular component selector (no `data-testid` fallback needed; the component exists in the epic-3 worktree at `spa/src/app/shared/ui/error-message.ts:4`).
  - [ ] 7.5 For AC13's 503 assertion, use `.first()` on the text locator because the load-error AND save-error paths produce the same UX-DR12 copy, so two `<app-error-message>` elements may both contain the string momentarily (load completed → loadError set → user clicks Save → saveError ALSO becomes set → both elements render).

- [ ] **Task 8 — Update `e2e/README.md`** (AC supporting #4, #7, #8, #16)
  - [ ] 8.1 In "Environment variables", add entries for `RS_BASE_URL` (default `http://resource-server:8000` for the compose runner; host-side workflow can't easily reach the RS — see below) and `COMPOSE_PROJECT_NAME` (default `bmad-books`).
  - [ ] 8.2 Add a new subsection "RS killswitch (J4 + J6)" under "Running locally" documenting:
    - The runner now shells out to `docker compose stop|start resource-server` via the bound socket; `npm test` from `e2e/` on the HOST also shells out — to the same daemon if running Docker Desktop, so it works locally on macOS/Linux without changes.
    - The host-side workflow does NOT have RS published to a localhost port (architecture §F3 says only the BFF exposes a user-facing port); `resetState`'s RS POST therefore can't reach the RS from the host. Workarounds: (a) run the e2e suite via `just e2e-up` instead of host-side `npm test`, OR (b) add a temporary `ports: ["8001:8000"]` to the `resource-server` block in your local `compose/app.yml` (do NOT commit) and set `RS_BASE_URL=http://localhost:8001`. Document option (a) as canonical; (b) as ad-hoc developer workflow.
  - [ ] 8.3 Add a "Specs in this directory" entry for `tests/j4-adjust-speed.spec.ts (Story 3.6) — J4: adjust reading speed, including freshuser unset state, Saved pulse, validation, and RS-unavailable error variants.`
  - [ ] 8.4 Update the existing "RS test-reset extension" section: move from forward-pointer ("Story 3.6 will replace the stubs") to present-tense ("Story 3.6 replaced the stubs and extended `resetState` to also POST to the RS").
  - [ ] 8.5 Do NOT document accessibility / responsive considerations — out of scope per project memory.

- [ ] **Task 9 — Live-stack verification** (AC: #16)
  - [ ] 9.1 From the repo root, run `just e2e-up` (or the explicit `-f` form).
  - [ ] 9.2 Confirm: Keycloak healthy → BFF + RS start (RS now in e2e profile per Task 1) → all three services healthy → playwright runner starts → specs run → runner exits 0 → compose tears down → final shell exit 0.
  - [ ] 9.3 Capture the runner's `npx playwright test` summary line (specs passed / failed / duration) in the Dev Agent Record's Debug Log References.
  - [ ] 9.4 If ANY spec fails: move to triage. Don't close based on static gates — retro P2.

- [ ] **Task 10 — Static gates + regression checks** (AC: #17)
  - [ ] 10.1 `cd e2e && npx tsc --noEmit` — exit 0; capture transcript.
  - [ ] 10.2 `cd e2e && npx playwright test --list` — exit 0; capture the list.
  - [ ] 10.3 `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` — exit 0; capture the `playwright` and `resource-server` service blocks from the config dump.
  - [ ] 10.4 `docker compose --profile dev config --services` and `docker compose --profile default config --services` — emit `keycloak`, `bff`, `resource-server` (NO `playwright`); capture both.
  - [ ] 10.5 `cd services/bff && uv run pytest -q` — exit 0. No BFF code changed in 3.6, but the live `just e2e-up` exercises BFF code paths.
  - [ ] 10.6 `cd services/resource-server && uv run pytest -q` — exit 0. Same rationale.
  - [ ] 10.7 `cd spa && npm run lint && npm test -- --watch=false && npm run build` — exit 0 across all three.

## Dev Notes

### What this story is — and is not

**Is:** A Playwright spec for J4 + the compose / Dockerfile / helper plumbing needed for `killRs` and `startRs` to actually stop and start a real `resource-server` container. Deliverables:

1. `compose/app.yml` — `resource-server` profiles `[default, dev]` → `[default, dev, e2e]`; playwright service mods (depends_on RS healthy + socket bind + `RS_BASE_URL` + `COMPOSE_PROJECT_NAME`).
2. `compose/app.e2e.yml` — extended with RS overlay block (`ENABLE_TEST_RESET=true`, `TEST_RESET_TOKEN`, `AUTH_TYPE=oidc_bearer`).
3. `e2e/Dockerfile` — Docker CLI + compose plugin installed.
4. `e2e/fixtures/services.ts` (NEW) — compose-CLI wrapper.
5. `e2e/fixtures/helpers.ts` — `killRs`/`startRs` real impl; `resetState` extended.
6. `e2e/tests/j4-adjust-speed.spec.ts` (NEW) — five tests.
7. `e2e/README.md` — RS killswitch + J4 entry + env vars.

**Is NOT:** Any SPA / BFF / RS code (Stories 3.1–3.5 already done), any new `AppError` variants (3.5 added `resource_server_unavailable`), the J6 RS-unavailable spec (Story 4.4 — but the `killRs` infra this story ships is what J6 will use), the J2 books-manage spec (Story 2.7 — runs in a different worktree).

### Critical: `AUTH_TYPE=oidc_bearer` must be activated in the e2e overlay

The RS's `services/resource-server/.env.example` (lines 40-52) documents that the default `AUTH_TYPE=none` runs the archetype's synthetic-admin auth — every caller is treated as an unauthenticated superuser. Comment at line 50-52:

> Compose profiles default + dev + e2e SHOULD set AUTH_TYPE=oidc_bearer (the actual wiring flips in Story 3.3 / 3.6 once a scope-gated handler exists to consume it).

Story 3.3 added the scope-gated handler; this story is responsible for actually flipping `AUTH_TYPE=oidc_bearer` on the e2e profile. Without it, the J4 spec's scope-enforcement coverage silently degrades — `reading-speed:read` / `reading-speed:write` validation becomes a no-op because the RS treats the bearer as the synthetic admin.

**Verify at story-execution time** that `services/resource-server/.env` (gitignored, copied from `.env.example`) does NOT set `AUTH_TYPE=oidc_bearer` unconditionally — that would leak into `default` / `dev` profiles. The right place is the e2e overlay (AC2), so it only activates under e2e. If the dev agent finds `AUTH_TYPE=oidc_bearer` already in the per-service `.env`, surface it as a deferred-work item (it's an out-of-band activation that bypassed the overlay pattern) and consider whether to remove it.

### Compose-stack AC pattern — live verification required (Epic 1 retro P2)

The Epic 1 retro identified that "Compose-stack ACs ran statically" (D45 / D46 both surfaced because `docker compose config` passed but `docker compose up` had bugs). Retro action item P2:

> If a story has an AC that depends on `docker compose ... up`, the story does NOT close to `done` until either (a) the live run succeeded, or (b) the AC is explicitly downgraded with a tracking entry referencing the blocker.

Story 3.6's AC16 IS that live AC. Run `just e2e-up` end-to-end; capture the runner's output. Static gates are necessary but not sufficient.

### Compose env override boundary — DO NOT add `ENABLE_TEST_RESET` to `compose/app.yml` directly

The `ENABLE_TEST_RESET=true` + `TEST_RESET_TOKEN` env vars must NOT live unconditionally on the `resource-server` service in `compose/app.yml`. They go in the `compose/app.e2e.yml` overlay (the same one Story 1.12 created for the BFF) and the overlay is applied via the `-f` flag pattern wrapped by `just e2e-up`.

Why not `include:` instead of `-f`: Compose v2's `include:` is unconditional — entries are loaded regardless of which `--profile` is active. The `${TEST_RESET_TOKEN:?...}` fail-fast would fire on `default` / `dev` profile invocations (which don't need test-reset and may not have `TEST_RESET_TOKEN` set), breaking the default workflow with a confusing "missing TEST_RESET_TOKEN" error. The header comment in `compose/app.yml:9-17` and `compose/app.e2e.yml:10-22` documents this Story-1.12 verdict; 3.6 doesn't revisit it.

### `killRs` / `startRs` implementation choice — docker-socket binding

The epic's Story 3.6 AC text (epics.md line 1487) says implementer's choice between:

- (A) Bind `/var/run/docker.sock` into the runner; shell out to `docker compose stop|start resource-server`.
- (B) A REST shim (another container) exposing `/kill-rs` / `/start-rs` endpoints.

**This story chose A** because:

1. **Fewer moving parts.** One extra `volumes:` line + one apt layer in the Dockerfile. Option B needs a new service, image, healthcheck, and auth.
2. **Standard pattern.** Docker-socket binding for compose orchestration from a test container is the canonical recipe.
3. **No new container surface.** Just expanding the runner's existing capabilities.

Trade-off: a bound docker socket gives the runner root-equivalent access to the host. Acceptable because the runner is local-only, e2e is operator-opt-in, and production hardening is Story 5.2's territory. Document inline on the volume bind per Task 3.3.

### Where to put the docker-compose plumbing — `services.ts` (separate module)

Two reasonable shapes:

- (A) Inline in `helpers.ts` — `killRs` does the `execFile` shell-out directly.
- (B) Extract to `e2e/fixtures/services.ts`; `helpers.ts` becomes a thin facade.

**This story chose B** because:

1. **Single responsibility.** `helpers.ts` is the test-facing API (`logInAs`, `resetState`, `killRs`, `startRs`). `services.ts` is the Node-shell-out plumbing (`execFile`, `docker compose`, JSON parsing).
2. **Testability.** A meta-spec for the harness can mock `services.ts` cleanly; mocking `child_process` from inside `helpers.ts` is awkward.
3. **Mirrors the `users.ts` / `helpers.ts` split.** Data → behavior → infra is the same pattern.

If the dev agent strongly prefers (A) at implementation time, mark the deviation in the Completion Notes.

### Idempotency — what it buys + what it doesn't

The epic AC requires both helpers idempotent (line 1489). What it buys: the `afterEach` calls `startRs` even after a test that ended with RS running — no error. What it does NOT promise: recovery from broken state (running-but-unhealthy, exited-but-still-listed). The AC7 impl is:

```ts
if (!(await isRsRunning())) await startRsService();
await waitForRsHealthy();
```

If RS is running-but-unhealthy, `isRsRunning` returns true, `startRsService` is skipped, `waitForRsHealthy` polls until timeout, then throws. Correct — a stuck RS is a debugging signal, not something to paper over with `docker compose restart`. Don't add restart logic here; different operation, different semantics.

### Wire-contract from Stories 3.3–3.5 — what 3.6 consumes

| Endpoint | Method | Where it lives | What 3.6 asserts |
|---|---|---|---|
| `/v1/test/reset` | POST | BFF (Story 1.12) | 204 on correct bearer; truncates books/sessions/auth_states. |
| `/v1/test/reset` | POST | RS (Story 3.4) | 204 on correct bearer; truncates reading_speeds. |
| `/v1/reading-speed` | GET | BFF proxy (Story 3.5) | 200 `{pages_per_hour: int}` happy; 412 `{errorCode: reading_speed_unset, ...}` when no row; 503 `{errorCode: resource_server_unavailable, ...}` when RS unreachable. |
| `/v1/reading-speed` | PUT | BFF proxy (Story 3.5) | 200 `{pages_per_hour: int}` happy; 422 `{errorCode: invalid_input, ...}` on bad body; 503 `resource_server_unavailable` when RS unreachable. |
| `/settings` | route | SPA (Story 3.5) | `SettingsPage` rendered; input labelled `Pages per hour`; button class `.settings-save` (text Save/Saving…/Saved); `<app-error-message>` for errors; UX-DR12 copy `"Service unavailable — try again shortly"` on 503; client-side `"Enter a positive number"` for non-positive-integer. |

### Selector contracts — precise mapping to Story 3.5's emitted markup

`spa/src/app/settings/settings-page.html` emits (verified in epic-3 worktree):

- `<h1 class="settings-heading">Reading speed</h1>` — page heading.
- `<label for="pages-per-hour" class="settings-label">Pages per hour</label>` + `<input id="pages-per-hour" type="number" min="1" class="settings-input" ...>`. Playwright's `page.getByLabel('Pages per hour')` resolves via the `for`/`id` linkage.
- `<p class="settings-helper">e.g., 30</p>` — helper text. `page.getByText('e.g., 30')`.
- `<app-error-message [message]="msg" />` — Angular component selector `app-error-message`. Emits `<p class="error-message">{{message()}}</p>`. `page.locator('app-error-message')` counts the rendered instances; `page.getByText('<literal>')` matches inner content.
- `<button type="submit" class="settings-save" [disabled]="...">{{ saveButtonLabel() }}</button>` — text is `Save` / `Saving…` / `Saved` per `settings-page.ts:49-53`. **The accessible name changes** with the text. `page.getByRole('button', { name: 'Save' })` does NOT match when the button reads `Saved`. Use `page.locator('button.settings-save')` — class-name selector is stable across label transitions.

The `<app-error-message>` count assertion in AC10 is reliable: the SettingsPage template (`settings-page.html:15-23`) renders `<app-error-message>` ONLY when `validationError()` / `loadErrorMessage()` / `saveErrorMessage()` is non-null. For freshuser's 412, all three are null (412 sets `pagesPerHour` to null AND `loadError` to null per `reading-speed-service.ts:60-65`) → zero error elements rendered.

### Host-side RS access — known constraint

The RS has NO `ports:` block in `compose/app.yml` (architecture §F3 + §I6: only the BFF exposes a user-facing port — `compose/app.yml:36-41`). For the host workflow (`cd e2e && npm test`), `resetState`'s extension can't reach the RS at `http://localhost:<port>` because nothing's published. Three options:

1. **Run via compose** (`just e2e-up`) — canonical. The runner reaches the RS via the compose network at `http://resource-server:8000`.
2. **Temporary host port** — add `ports: ["8001:8000"]` to the `resource-server` block in your local `compose/app.yml` (don't commit) and set `RS_BASE_URL=http://localhost:8001`. Ad-hoc developer workflow.
3. **Sidecar exec** — `docker compose exec resource-server curl -X POST ...` from the host. Possible but defeats the helper's HTTP-client model.

Document option 1 as canonical in the README (Task 8.2); mention option 2 as ad-hoc; skip option 3.

### Test isolation — `workers: 1` + `afterEach startRs` guard

`e2e/playwright.config.ts:15` sets `workers: 1` (load-bearing, documented in Story 1.11). Every spec runs sequentially. The `killRs`/`startRs` pattern fundamentally assumes a single RS singleton — two parallel tests cannot both control it. If a future refactor introduces parallelism, this whole story's harness needs a redesign (per-worker RS, or a different J6/J4 model).

The `afterEach` is the primary cleanup; the in-test `await startRs()` at the end of AC13 / AC14 is defense-in-depth.

### Previous story intelligence

**Story 3.5 (done, merged at `630ee6d`):**
- Delivered `ResourceServerClient` (refresh-and-replay), `/v1/reading-speed` BFF proxy, `SettingsPage`, `ReadingSpeedService`, `/settings` route.
- The `saveErrorMessage` computed falls back to `"Couldn't save — try again"` for unknown error kinds (`settings-page.ts:85`). The J4 spec only asserts the `resource_server_unavailable` and `invalid_input` copy explicitly per UX-DR12; other kinds produce the fallback but the spec doesn't exercise them.
- `JUST_SAVED_PULSE_MS = 1000` (`reading-speed-service.ts:25`). AC11's `toHaveText('Saved', { timeout: 2000 })` is safe headroom.
- Story 3.5's CR7 added `_clear_session_cookies` to the BFF logout / 401 paths — irrelevant for 3.6 directly, but means the J4 spec's cookie-clear in AC10 is one of three clearing mechanisms; verified to work alongside the others.

**Story 3.4 (done, merged at `053a8ff`):**
- RS `POST /v1/test/reset` gated by `ENABLE_TEST_RESET=true` + `TEST_RESET_TOKEN` bearer. Same contract as BFF's (Story 1.12). `resetState`'s extension in AC8 is exactly what 3.4 was designed for.

**Story 3.3 (done, merged at `61b28c5`):**
- RS `/v1/reading-speed` GET/PUT scope-gated. Wire codes are `reading_speed_unset` (412), `invalid_input` (422), `forbidden_scope` (403). Story 3.5's BFF proxy forwards these directly to the SPA.

**Story 3.2 (done, merged at `119a25a`):**
- RS `oidc_bearer` JWKS-validated auth plugin. Activated via `AUTH_TYPE=oidc_bearer` env var. The e2e overlay in AC2 is what flips this for the e2e profile.

**Story 3.1 (done, merged at `2a35822`):**
- RS scaffolded; `/health` checks DB reachable + Alembic at head + JWKS fetchable. `resource-server` service in `compose/app.yml` profiles `[default, dev]` — Story 3.6 widens to `[default, dev, e2e]` (AC1).

**Stories 1.11–1.14 (done in main):**
- 1.11 — Playwright project scaffold; `killRs`/`startRs` `: never` stubs; the `workers: 1` invariant. 3.6 replaces the stubs.
- 1.12 — `compose/app.e2e.yml` overlay pattern (NOT include); BFF `POST /v1/test/reset`. 3.6 extends the overlay.
- 1.13 — J1 + J5 specs; `requireEnv` pattern; `resetState; logInAs` beforeEach shape. 3.6 mirrors.
- 1.14 — BFF same-origin SPA serving. The runner's `baseURL=http://bff:8000` lands on the SPA correctly; no change in 3.6.

### Project context (from auto-memory + CLAUDE.md)

- **Python invoked as `python`** (never `python3`). 3.6 has no Python; the convention is moot but should be honored.
- **Accessibility and responsive design are explicitly out of scope.** Use Playwright's accessibility-first locators (`getByLabel`, `getByText`) for stability, NOT for WCAG coverage. Cover J4 on `Desktop Chrome` only.
- **Backend services use github.com/tommaso-meledina/fastapi-archetype.** 3.6 has no backend changes; informational.

### Files this story creates

```
e2e/
├── fixtures/
│   └── services.ts                                  (NEW — compose-CLI wrapper)
└── tests/
    └── j4-adjust-speed.spec.ts                      (NEW — five J4 tests)
```

### Files this story modifies

```
compose/app.yml                                      # Task 1, 3 — RS profiles list; playwright depends_on/volumes/env
compose/app.e2e.yml                                  # Task 2 — append resource-server block
e2e/Dockerfile                                       # Task 4 — install docker-ce-cli + docker-compose-plugin
e2e/fixtures/helpers.ts                              # Task 6 — killRs/startRs real impl; resetState extended
e2e/README.md                                        # Task 8 — RS killswitch + J4 entry + env vars
```

### Files this story explicitly does NOT touch

- `compose/infra.yml` — Keycloak unchanged.
- `docker-compose.yml` (root) — the top-level `include:` directive needs no change; the e2e overlay continues to be applied via `-f`.
- `services/bff/**`, `services/resource-server/**`, `spa/**` — no application code changes.
- `keycloak/realm-bmad-books.json` — users + scopes + audience already seeded by Stories 1.2 + 3.1.
- `e2e/tests/j1-first-login.spec.ts` / `e2e/tests/j5-logout.spec.ts` — they call `resetState` via the unchanged signature; no edits needed.
- `e2e/fixtures/users.ts` — `testuser` + `freshuser` already defined.
- `e2e/playwright.config.ts` — `workers: 1` invariant preserved.
- `_bmad-output/planning-artifacts/**` — read-only source of truth.
- Repo-root `.gitignore` / `.dockerignore` — already cover the relevant paths.

### Git intelligence (recent commits on `epic-3`)

```
630ee6d Merge story 3.5 — BFF ResourceServerClient + SPA SettingsView for /settings
d1a846f chore(3.5): code review — CR1–CR10 applied, mark done, log D80–D102
3f24bba feat(3.5): BFF ResourceServerClient + SPA SettingsView for /settings
637d148 chore(3.5): create story — BFF ResourceServerClient + SPA SettingsView
053a8ff Merge story 3.4 — RS POST /v1/test/reset gated truncate of reading_speeds
b92925c chore(3.4): code review — CR1–CR3 applied, mark done, log D74–D79
5248e62 feat(3.4): RS POST /v1/test/reset — gated truncate of reading_speeds
2338bba chore(3.4): create story — RS POST /v1/test/reset endpoint
61b28c5 Merge story 3.3 — RS ReadingSpeed model + /v1/reading-speed GET+PUT scope-gated
2f78bc5 chore: 3.3 code review — CR1–CR3 applied, mark done, log D66–D70
```

23 commits ahead of `main`. Stories 3.1–3.5 all show the same pattern: `create story → feat (dev) → chore code-review CRs + defers → Merge`. Story 3.6 follows the same flow.

### Latest tech information

- **Playwright `^1.49.0`** (resolved to 1.60.0 at Story 1.11 install time per `e2e/package.json:10`). `page.route('**/...')`, `getByLabel`, `getByRole`, `getByText`, `toHaveValue`, `toHaveText` with `timeout` are stable.
- **Docker Compose v2 `docker compose ps --format json`** emits NDJSON in v2.20+; older v2.x emits a single JSON array. `services.ts` handles both.
- **`docker inspect --format '{{.State.Health.Status}}'`** returns `healthy` / `unhealthy` / `starting` / `none`. Story 3.1's healthcheck is declared, so `none` should never appear.
- **Node 20 LTS** (from Story 1.11's Dockerfile). `util.promisify(child_process.execFile)` is the canonical async wrapper.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.6: E2E spec — J4 adjust reading speed + compose `e2e` profile updates + `killRs`/`startRs`/`resetState` helpers` lines 1468–1515] (verbatim AC source)
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.5` lines 1316–1466] (BFF proxy + SPA SettingsPage contract this spec verifies)
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.4` lines 1282–1314] (RS `/v1/test/reset` endpoint `resetState` extends to hit)
- [Source: `_bmad-output/planning-artifacts/epics.md#AR17` line 74] (`RESOURCE_SERVER_UNAVAILABLE` 503, `READING_SPEED_UNSET` 412, `INVALID_INPUT` 422)
- [Source: `_bmad-output/planning-artifacts/epics.md#AR26` line 89] (compose profiles `default` / `dev` / `e2e`; e2e adds Playwright)
- [Source: `_bmad-output/planning-artifacts/epics.md#AR31` line 96] (Playwright in `e2e/`; one spec per PRD journey; real Keycloak login)
- [Source: `_bmad-output/planning-artifacts/epics.md#AR32` line 97] (POST `/v1/test/reset` semantics + env gating on BFF + RS; shared `TEST_RESET_TOKEN`)
- [Source: `_bmad-output/planning-artifacts/epics.md#UX-DR9` line 111] ("Saved" pulse ~1s; loading / loaded / unset / saving / saved / validation-error / load-error / save-error states; positive-integer validation copy)
- [Source: `_bmad-output/planning-artifacts/epics.md#UX-DR12` lines 114–119] (failure copy `"Service unavailable — try again shortly"` for J6 / 503; `"Enter a positive number"` for positive-integer validation)
- [Source: `_bmad-output/planning-artifacts/epics.md#UX-DR15` line 122] (validation on submit; native HTML controls; inputs preserve values on failure)
- [Source: `_bmad-output/planning-artifacts/architecture.md#Operational Details — POST /v1/test/reset` lines 1354–1360] (truncates `reading_speeds` on RS; shared bearer)
- [Source: `_bmad-output/planning-artifacts/architecture.md#§"How to run / E2E"` lines 1299–1305] (canonical e2e invocation)
- [Source: `_bmad-output/planning-artifacts/architecture.md#Failure path — J6 (RS unavailable)` lines 1239–1250] (the BFF→503 path AC13 / AC14 verify end-to-end)
- [Source: `_bmad-output/implementation-artifacts/epic-1-retro-2026-05-16.md#Action items P2` lines 142–146] (compose-stack ACs run live or are explicitly downgraded — AC16's verification gate)
- [Pattern: `compose/app.yml:60-99`] (existing `resource-server` service block — profiles list to widen at line 98)
- [Pattern: `compose/app.yml:101-144`] (existing `playwright` service block to modify)
- [Pattern: `compose/app.e2e.yml`] (Story 1.12's overlay shape — `${TEST_RESET_TOKEN:?...}` fail-fast; extend with RS block)
- [Pattern: `e2e/Dockerfile`] (existing Dockerfile — extend with apt layer)
- [Pattern: `e2e/fixtures/helpers.ts:31-44`] (existing `resetState` to extend)
- [Pattern: `e2e/fixtures/helpers.ts:50,57`] (existing `killRs`/`startRs` `: never` stubs to replace)
- [Pattern: `e2e/tests/j1-first-login.spec.ts`] (describe + `requireEnv` + `beforeEach` shape — mirror exactly)
- [Pattern: `e2e/tests/j5-logout.spec.ts`] (dual `request` + `page` fixture usage in a single test)
- [Pattern: `e2e/playwright.config.ts:15`] (`workers: 1` load-bearing — informs test isolation reasoning)
- [Pattern: `spa/src/app/settings/settings-page.html`] (selector contracts — `.settings-save` class; `<app-error-message>` selector; `<label for="pages-per-hour">`)
- [Pattern: `spa/src/app/settings/settings-page.ts:49-53`] (saveButtonLabel computed — Save/Saving…/Saved transitions)
- [Pattern: `spa/src/app/settings/reading-speed-service.ts:25`] (JUST_SAVED_PULSE_MS = 1000 — informs AC11 timeout)
- [Pattern: `services/resource-server/.env.example:40-52`] (AUTH_TYPE contract — `oidc_bearer` activation in 3.3/3.6)
- [Pattern: `Justfile`] (`just e2e-up` recipe wraps the multi-`-f` compose invocation)

## Definition of Done

1. `compose/app.yml` `resource-server` `profiles:` widened to `[default, dev, e2e]`; comment block at lines 64-67 refreshed to present-tense.
2. `compose/app.e2e.yml` extended with the `resource-server` block (`ENABLE_TEST_RESET=true`, `TEST_RESET_TOKEN: "${TEST_RESET_TOKEN:?...}"`, `AUTH_TYPE=oidc_bearer`); header docstring updated.
3. `compose/app.yml` `playwright` service modified: `depends_on` adds `resource-server: { condition: service_healthy }`; `volumes` mounts `/var/run/docker.sock`; `environment` adds `RS_BASE_URL=http://resource-server:8000` and `COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-bmad-books}`.
4. `e2e/Dockerfile` extended with `docker-ce-cli` + `docker-compose-plugin` apt-install layer placed for cache reuse; image builds clean; `docker compose version` works inside the image.
5. `e2e/fixtures/services.ts` (NEW) exports `stopRs`, `startRs`, `isRsRunning`, `waitForRsHealthy` per AC6 (or implementation deviation documented in Completion Notes per the "Where to put the docker-compose plumbing" decision).
6. `e2e/fixtures/helpers.ts` modified: `killRs` and `startRs` are `Promise<void>` real implementations idempotent against stale state; `resetState` posts to both BFF and RS.
7. `e2e/tests/j4-adjust-speed.spec.ts` (NEW) contains five tests (AC10–AC14) matching the describe / `requireEnv` / `beforeEach` / `afterEach` pattern from `j1-first-login.spec.ts`. The save-button locator is `page.locator('button.settings-save')` (NOT `getByRole('button', {name: 'Save'})` — the label transition breaks that).
8. `e2e/README.md` updated: `RS_BASE_URL` + `COMPOSE_PROJECT_NAME` documented; "RS killswitch (J4 + J6)" subsection added; "Specs in this directory" gains J4 entry; "RS test-reset extension" moves to present-tense.
9. `cd e2e && npx tsc --noEmit` exits 0.
10. `cd e2e && npx playwright test --list` exits 0 and reports J1, J5, (J2 if present), and 5 × J4 specs.
11. `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` exits 0 with the documented `playwright` and `resource-server` shapes.
12. `docker compose --profile dev config --services` and `docker compose --profile default config --services` emit `keycloak`, `bff`, `resource-server` (NO `playwright`).
13. **Live `just e2e-up` exits 0 with all five J4 specs + J1 + J5 + J2 (if present) passing.** Load-bearing AC per retro P2.
14. `cd services/bff && uv run pytest -q`, `cd services/resource-server && uv run pytest -q`, `cd spa && npm run lint && npm test -- --watch=false && npm run build` all exit 0.
15. No changes to any file outside the seven files (modified + new) listed in §"Files this story creates / modifies."
16. Any items surfaced during dev / code review are logged in `_bmad-output/implementation-artifacts/deferred-work.md` under a new "Deferred from: code review of 3-6-..." section with surfacing / owning / severity tags.

## Dev Agent Record

### Agent Model Used

<!-- filled by dev-story -->

### Debug Log References

<!-- filled by dev-story -->

### Completion Notes List

<!-- filled by dev-story -->

### File List

<!-- filled by dev-story -->

### Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-05-17 | 0.1 | Story file created. Prerequisite stories 3.1–3.5 all `done` on the `epic-3` branch (HEAD `630ee6d`). Live `just e2e-up` (AC16) is the load-bearing close gate per retro P2. | claude-opus-4-7 |
