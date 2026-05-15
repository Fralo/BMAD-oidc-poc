---
status: review
story_key: 1-11-playwright-project-setup-fixtures-helpers
created: 2026-05-15
---

# Story 1.11: Playwright project setup + fixtures + helpers

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a maintainer,
I want a Playwright project under `e2e/` with configuration, shared fixtures, and helper functions ready to drive real OAuth flows against the running compose stack,
so that journey-specific E2E specs (added in this epic and in every subsequent epic) can be written without re-doing the harness.

## Acceptance Criteria

**AC1 — `e2e/` Playwright project files exist:**
- `e2e/package.json` declares `@playwright/test` (latest stable as of May 2026 — pin `^1.49.x` or the latest stable Playwright 1.x at story-execution time; record the exact resolved version in the Dev Agent Record) as a devDependency. The package is private (`"private": true`), has `"name": "e2e"`, `"version": "0.0.0"`, and an `npm test` script that invokes `playwright test` (no extra flags beyond what `playwright.config.ts` carries).
- `e2e/tsconfig.json` exists and compiles cleanly via `tsc --noEmit` (Playwright tests are TypeScript). The config targets ES2022, uses `"module": "commonjs"` or `"module": "esnext"` (whichever Playwright's recommended template prefers as of the resolved Playwright version), enables `"strict": true`, and includes `tests/**/*.ts`, `fixtures/**/*.ts`, and `playwright.config.ts` in its `include` list.
- `e2e/.gitignore` excludes `node_modules/`, `test-results/`, `playwright-report/` (one entry per line). The repo-root `.gitignore` already covers `playwright-report/` and `test-results/`, but the per-directory `.gitignore` is required by the AC and provides defense-in-depth.
- `e2e/tests/` exists as an empty directory (with a single `.gitkeep` file so it is tracked by git — the directory must exist before `playwright test` is invoked under AC6, and an empty directory is otherwise not committable).

**AC2 — `e2e/playwright.config.ts` is exactly the spec'd shape:**
- `testDir: './tests'`
- `timeout: 60_000`
- `workers: 1` (sequential — `resetState` requires this; documented inline as a load-bearing comment, not a passing remark)
- `use: { baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8000', trace: 'retain-on-failure', screenshot: 'only-on-failure', video: 'retain-on-failure' }`
- `projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]` (where `devices` is imported from `@playwright/test`)
- Default export is the result of `defineConfig({...})` imported from `@playwright/test`. **Do not** export a bare object literal — `defineConfig` provides type-narrowing that is referenced by AC1's `tsc --noEmit` check.

**AC3 — `e2e/fixtures/users.ts` exports the two seeded user definitions:**
- Exports `testuser` and `freshuser` as named exports.
- Each user is shape `{ username: string; password: string; subPattern: RegExp }`. The `subPattern` field accommodates that Keycloak generates the user `sub` UUIDs at realm import time; specs that need to assert `sub` use the pattern matcher rather than a hard-coded value.
- `testuser`: `{ username: 'testuser', password: 'testpassword', subPattern: /^[0-9a-f-]{36}$/ }` (UUID-shape — Keycloak emits standard v4 UUIDs).
- `freshuser`: `{ username: 'freshuser', password: 'freshpassword', subPattern: /^[0-9a-f-]{36}$/ }`.
- The two credential pairs match exactly what `keycloak/realm-bmad-books.json` seeds (verified by reading the realm JSON at story-execution time — see Dev Notes).
- A shared TypeScript type `SeededUser` is exported alongside the constants (`export interface SeededUser { username: string; password: string; subPattern: RegExp; }`) so helper signatures can refer to it.

**AC4 — `e2e/fixtures/helpers.ts` exports `logInAs`, `resetState`, `killRs`, `startRs`:**
- `logInAs(page: Page, user: SeededUser): Promise<void>`:
  - Navigates to `/login` via `page.goto('/login')` (relative to `baseURL`).
  - Clicks the `"Log in"` button (selector: `role=button[name="Log in"]` per UX-DR3; if Story 1.10 ships a different accessible name, follow what 1.10 actually emits and update this story's reference).
  - Waits for the redirect to Keycloak (URL matches `/realms/bmad-books/protocol/openid-connect/auth`).
  - Fills the Keycloak username/password form (`input[name="username"]` and `input[name="password"]`) with `user.username` / `user.password`, submits via `input[type="submit"]` or `button[type="submit"]` (whichever Keycloak 26's default theme emits — verify against the running container at story-execution time).
  - Waits for the redirect back to `/books` (`page.waitForURL(/\/books$/)`).
  - Waits for the identity block in `TopChrome` to be visible (selector: `text=/Signed in as testuser/` for `testuser`, or use a `data-testid` if Story 1.10 emits one — defer the precise selector to Story 1.10's spec, document the fallback `text=` selector here as the working assumption).
  - Returns `void` when all of the above complete; throws via Playwright's built-in timeouts if any step exceeds the test's 60s timeout.
- `resetState(request: APIRequestContext, opts: { resetToken: string }): Promise<void>`:
  - Calls `POST ${baseURL}/v1/test/reset` with header `Authorization: Bearer ${opts.resetToken}`.
  - Throws if the response status is not 204.
  - Signature is `(request, opts)` — the second argument is an options object so the RS test-reset endpoint added in Epic 3 (Story 3.4) can pass additional fields (e.g., `{ resetToken, includeReadingSpeed: true }`) without breaking call sites. Story 1.11 only sends to the BFF; Story 3.4 extends the helper to also POST to the RS endpoint.
  - The `opts` parameter is required (not optional) — callers must always pass `{ resetToken: process.env.TEST_RESET_TOKEN! }`. The helper itself does not read `process.env` (single-responsibility — env wiring is the spec's concern, not the helper's).
- `killRs(): never`:
  - Stub. Throws `new Error('RS not yet present (Epic 3)')` on every call.
  - Return type is `never` (TypeScript) so call sites get compile-time signal that the function does not return normally.
- `startRs(): never`:
  - Same shape as `killRs` — throws `new Error('RS not yet present (Epic 3)')`.
  - Story 3.6 replaces both with real implementations that shell out to `docker compose stop resource-server` / `docker compose start resource-server` (or the equivalent compose CLI for the running runtime).

**AC5 — `e2e/Dockerfile` builds the Playwright runner image:**
- Base image: `node:20-bookworm-slim` (Node 20 LTS — Playwright 1.49.x requires Node ≥18; pin to 20 for stability). If a newer Node major is mandatory at story-execution time per Playwright's documented runtime requirements, choose the documented minimum.
- Installs only the chromium browser via `npx playwright install --with-deps chromium` (NOT `--with-deps` for all browsers — image size is a stated AC concern).
- `WORKDIR /e2e`.
- `COPY package.json package-lock.json ./` then `RUN npm ci` (cache layer for deps).
- `COPY . .` (the e2e source folder).
- Default `CMD ["npx", "playwright", "test"]` so the runner starts the test invocation when the container starts.
- A non-root user is NOT required by the AC (the e2e profile runs only locally; tightening this is a Story 5.2 concern).

**AC6 — `e2e` compose profile defines a `playwright` runner service in `compose/app.yml`:**
- Service name: `playwright`.
- `build:` block points at `../e2e` (relative to `compose/app.yml`).
- `depends_on:` declares both `bff` and `keycloak` with `condition: service_healthy`.
- `volumes:` mounts `../e2e/test-results:/e2e/test-results` so trace/screenshot artifacts land on the host after a run.
- `environment:` sets `E2E_BASE_URL=http://bff:8000` (the BFF's compose-network hostname) and `TEST_RESET_TOKEN=${TEST_RESET_TOKEN}` (passed through from the root `.env`).
- `profiles: [e2e]` — the service is only activated under the `e2e` profile (not under `default` or `dev`).
- `restart: "no"` — the Playwright runner is one-shot; it should exit when tests complete, not be auto-restarted by compose.
- The BFF service block in `compose/app.yml` is **extended** (not duplicated as a separate service definition) so the `e2e` profile gets `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN=${TEST_RESET_TOKEN}` on the BFF environment. Without this, `POST /v1/test/reset` returns 404 in the e2e profile per Story 1.12's design. **NOTE:** Story 1.12 is the owner of the BFF-side `/v1/test/reset` endpoint and the per-profile env wiring; this story can land the env-var pass-through in `compose/app.yml` defensively (it has no effect today because the route doesn't exist yet) or leave it for Story 1.12 to add. The clean choice is to add `ENABLE_TEST_RESET` and `TEST_RESET_TOKEN` to the BFF service's `environment:` block under a `profiles`-aware mechanism (compose does not natively support per-profile env overrides on a single service definition — Story 1.12 will solve this; for 1.11, leave a `# Story 1.12 will wire ENABLE_TEST_RESET/TEST_RESET_TOKEN here for the e2e profile` comment on the BFF service block). See Dev Notes "Compose env override boundary" for the full reasoning.

**AC7 — Empty test discovery baseline:**
- After `cd e2e && npm ci && npx playwright install --with-deps chromium`, running `npx playwright test` (against the empty `tests/` directory containing only `.gitkeep`) exits 0 with Playwright reporting `"No tests found"` (or the equivalent message emitted by the resolved Playwright version).
- This is the acceptable baseline before Story 1.13 lands real specs. The dev agent does NOT write any tests in this story — the empty-discovery exit-0 IS the AC.

**AC8 — Compose e2e profile dry run:**
- Running `docker compose --profile e2e up --abort-on-container-exit` from the repo root:
  - Starts Keycloak, BFF, and the `playwright` runner in that order (`depends_on` honored).
  - The Playwright runner waits for both BFF and Keycloak healthchecks to pass before starting.
  - With no specs present, the runner exits 0 (`"No tests found"`).
  - `--abort-on-container-exit` then tears down the rest of the stack, returning the dev's shell prompt.
- Capture the full compose output (or relevant excerpts) in the Dev Agent Record's Debug Log References.

**AC9 — `e2e/README.md` documents local and compose execution:**
- Section: "Running locally" — describes `cd e2e && npm ci && npx playwright install --with-deps chromium && npm test`, with the prerequisite that `docker compose --profile dev up` (Keycloak + BFF) is already running on the host.
- Section: "Running via compose" — describes `docker compose --profile e2e up --abort-on-container-exit` from the repo root.
- Section: "Environment variables" — documents that `E2E_BASE_URL` overrides `http://localhost:8000` (used by the local-dev workflow; the compose profile sets it to `http://bff:8000` automatically); documents that `TEST_RESET_TOKEN` must be set in the root `.env` for `resetState` to succeed.
- Section: "Adding a new spec" — one paragraph pointing future story authors at `fixtures/helpers.ts` (the canonical `logInAs` + `resetState` source) and reminding them not to inline Keycloak credential-filling logic. (This anchors the rule that Story 1.13 AC says specs MUST use these helpers.)
- Section: "RS test-reset extension" — one-line forward reference to Story 3.4 (RS-side `/v1/test/reset`) and Story 3.6 (where `killRs`/`startRs` get real implementations).

**AC10 — Lint / type / dry-run gates green:**
- `cd e2e && npx tsc --noEmit` exits 0 across `playwright.config.ts`, `fixtures/users.ts`, `fixtures/helpers.ts`. No ESLint configuration is required for this story (the SPA's ESLint config doesn't extend to `e2e/`; the AC for static checking is TypeScript-only).
- `cd e2e && npx playwright test --list` exits 0 and emits an empty test list (companion to AC7's "no tests found" baseline — the `--list` flag is the deterministic, machine-readable form of "tests are discovered correctly" with zero side effects).
- Capture the exit-code-0 transcript for both commands in the Dev Agent Record's Debug Log References.

## Tasks / Subtasks

- [x] **Task 1 — Scaffold the `e2e/` Playwright project** (AC: #1)
  - [x] From the repo root, run `cd e2e` (the directory already exists per Story 1.1, currently containing only `.gitkeep`).
  - [x] Initialize the package: create `e2e/package.json` manually with the exact shape from AC1 (do NOT run `npm init` interactively — author the file directly to control every field):
    ```json
    {
      "name": "e2e",
      "version": "0.0.0",
      "private": true,
      "description": "Playwright E2E harness for the Reading Time Estimator. Real Keycloak login, no mocks.",
      "scripts": {
        "test": "playwright test"
      },
      "devDependencies": {
        "@playwright/test": "^1.49.0",
        "typescript": "^5.6.0"
      }
    }
    ```
    - Verify the resolved Playwright version at install time (`npm view @playwright/test version`); if a newer 1.x is available as of May 2026, update the caret to match the current latest minor before committing.
    - `typescript` is needed so `tsc --noEmit` runs without relying on a globally installed compiler.
  - [x] Create `e2e/tsconfig.json`:
    ```json
    {
      "compilerOptions": {
        "target": "ES2022",
        "module": "CommonJS",
        "moduleResolution": "node",
        "strict": true,
        "esModuleInterop": true,
        "skipLibCheck": true,
        "resolveJsonModule": true,
        "noEmit": true,
        "types": ["node"]
      },
      "include": ["playwright.config.ts", "fixtures/**/*.ts", "tests/**/*.ts"]
    }
    ```
    - `noEmit: true` is intentional — TypeScript here is purely a static check; Playwright's runtime transpiles via its own loader.
    - The `types: ["node"]` entry is required because the helpers use `process.env`. The `@types/node` package will be pulled in transitively by `@playwright/test`'s dependency tree (it depends on `@types/node`); verify after `npm install` and add `@types/node` as a direct devDependency only if `tsc --noEmit` fails to resolve `process`.
  - [x] Create `e2e/.gitignore`:
    ```
    node_modules/
    test-results/
    playwright-report/
    ```
  - [x] Create `e2e/tests/.gitkeep` (empty file) so `tests/` is tracked even before any spec lands.
  - [x] Run `cd e2e && npm install` to populate `node_modules/` and produce `package-lock.json`. Commit `package-lock.json` (it should not be in `.gitignore` — the root `.gitignore` excludes only `node_modules/`).
  - [x] Run `cd e2e && npx playwright install --with-deps chromium` to pre-fetch the chromium browser binary. This is a one-time host-side prerequisite for the local-dev workflow; the Dockerfile (Task 5) repeats it inside the runner image. Browsers land in `~/.cache/ms-playwright/` and are NOT committed to the repo.

- [x] **Task 2 — Author `e2e/playwright.config.ts`** (AC: #2)
  - [x] Create `e2e/playwright.config.ts` with:
    ```ts
    import { defineConfig, devices } from '@playwright/test';

    /**
     * Playwright config for the Reading Time Estimator E2E harness (Story 1.11).
     *
     * `workers: 1` is LOAD-BEARING: every spec calls `resetState(request, { resetToken })`
     * in a `beforeEach` (per Story 1.13 onward). Parallel workers would have two specs
     * simultaneously truncating + re-seeding the BFF's sessions/auth_states tables,
     * producing nondeterministic interleavings. Do NOT raise this without first
     * redesigning the test-reset contract.
     */
    export default defineConfig({
      testDir: './tests',
      timeout: 60_000,
      workers: 1,
      use: {
        baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8000',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
      },
      projects: [
        { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
      ],
    });
    ```
  - [x] The inline comment on `workers: 1` is REQUIRED — it is part of AC2 ("documented inline as a load-bearing comment, not a passing remark"). Reword as needed but do not delete.

- [x] **Task 3 — Author `e2e/fixtures/users.ts`** (AC: #3)
  - [x] Verify the seeded users by reading `keycloak/realm-bmad-books.json` before writing the constants. Story 1.2 landed two users — `testuser` / `testpassword` and `freshuser` / `freshpassword` (confirmed during analysis). If a future story renames either, this file must update in lockstep.
  - [x] Create `e2e/fixtures/users.ts`:
    ```ts
    export interface SeededUser {
      readonly username: string;
      readonly password: string;
      readonly subPattern: RegExp;
    }

    /**
     * The two users seeded by `keycloak/realm-bmad-books.json` (Story 1.2).
     *
     * `subPattern` is a regex (not a literal string) because Keycloak generates
     * the user `sub` UUIDs at realm import time — they are not stable across
     * `docker compose down -v` + re-import cycles. Specs that need to assert
     * something about `sub` should use `subPattern.test(observedSub)`.
     */
    export const testuser: SeededUser = {
      username: 'testuser',
      password: 'testpassword',
      subPattern: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    };

    export const freshuser: SeededUser = {
      username: 'freshuser',
      password: 'freshpassword',
      subPattern: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    };
    ```
  - [x] The UUID regex above is the strict v4-shape pattern. The looser `/^[0-9a-f-]{36}$/` from AC3 works equally well — pick one and be consistent.

- [x] **Task 4 — Author `e2e/fixtures/helpers.ts`** (AC: #4)
  - [x] Create `e2e/fixtures/helpers.ts`:
    ```ts
    import { APIRequestContext, Page, expect } from '@playwright/test';
    import { SeededUser } from './users';

    /**
     * Drives the SPA + Keycloak through the J1 login round-trip.
     *
     * Precondition: the BFF and Keycloak are reachable at `baseURL` and the
     * SPA's `LoginView` (Story 1.10) and `TopChrome` (Story 1.10) are
     * rendered. The user must already be seeded in the realm
     * (see `keycloak/realm-bmad-books.json`).
     */
    export async function logInAs(page: Page, user: SeededUser): Promise<void> {
      await page.goto('/login');
      await page.getByRole('button', { name: 'Log in' }).click();
      await page.waitForURL(/\/realms\/bmad-books\/protocol\/openid-connect\/auth/);
      await page.locator('input[name="username"]').fill(user.username);
      await page.locator('input[name="password"]').fill(user.password);
      await page.locator('button[type="submit"], input[type="submit"]').first().click();
      await page.waitForURL(/\/books$/);
      // TopChrome identity block — selector matches `Signed in as <username>` per UX-DR2 (Story 1.10).
      await expect(page.getByText(`Signed in as ${user.username}`)).toBeVisible();
    }

    /**
     * Truncates the BFF's auth-related tables via the test-reset endpoint
     * (Story 1.12). Story 3.4 extends this helper to also hit the RS-side
     * `/v1/test/reset` (reading_speeds). The `opts` parameter shape is forward-
     * compatible: extra fields may be added in Story 3.4 without breaking
     * existing call sites that pass only `{ resetToken }`.
     */
    export async function resetState(
      request: APIRequestContext,
      opts: { resetToken: string },
    ): Promise<void> {
      const response = await request.post('/v1/test/reset', {
        headers: { Authorization: `Bearer ${opts.resetToken}` },
      });
      if (response.status() !== 204) {
        const body = await response.text();
        throw new Error(
          `resetState: expected HTTP 204 from POST /v1/test/reset, got ${response.status()}. Body: ${body}`,
        );
      }
    }

    /**
     * Placeholder — will be implemented in Story 3.6 once the Resource Server
     * exists and the e2e compose profile knows how to stop/start it.
     */
    export function killRs(): never {
      throw new Error('RS not yet present (Epic 3)');
    }

    /**
     * Placeholder — see `killRs`.
     */
    export function startRs(): never {
      throw new Error('RS not yet present (Epic 3)');
    }
    ```
  - [x] `logInAs` uses Playwright's accessibility-first selectors (`getByRole`, `getByText`) for the SPA side, falls back to CSS selectors for the Keycloak login page (no a11y guarantees on third-party themes). The "Log in" button name is `Log in` per UX-DR3 (verified against the UX spec line 600). If Story 1.10 ships a different accessible name, that is a Story 1.10 defect and should be flagged on this story's review pass.
  - [x] The submit selector `button[type="submit"], input[type="submit"]` covers both Keycloak's default theme (which uses `<input type="submit">` historically) and newer themes that emit a `<button type="submit">`. The `.first()` modifier guards against multi-button forms (Keycloak's password-change forms have a "Cancel" button alongside "Submit"; for the basic login form there is only one submit control).
  - [x] `resetState` throws on non-204 with the body included — this gives the dev agent of Story 1.12 (and later) a precise diagnostic when test-reset is misconfigured.

- [x] **Task 5 — Author `e2e/Dockerfile`** (AC: #5)
  - [x] Create `e2e/Dockerfile`:
    ```dockerfile
    # Story 1.11: Playwright runner image used by the `e2e` compose profile.
    # Pinned to Node 20 LTS (Playwright 1.49.x requires Node ≥18; choose 20 for stability).
    # Only chromium is installed to keep the image lean — the AC scopes the harness
    # to a single browser project.
    FROM node:20-bookworm-slim AS playwright

    # `--with-deps` pulls the OS libs chromium needs (libnss3, libxss1, etc.) so the
    # final image runs out of the box. `playwright install` itself downloads only the
    # chromium binary into the default cache location (/root/.cache/ms-playwright).
    WORKDIR /e2e

    # 1) Install npm deps first to maximize layer cache reuse on fixture/spec churn.
    COPY package.json package-lock.json ./
    RUN npm ci

    # 2) Install only the chromium browser + its OS dependencies.
    RUN npx playwright install --with-deps chromium

    # 3) Copy the rest of the e2e source (fixtures/, tests/, playwright.config.ts).
    COPY . .

    # The runner is one-shot; compose `restart: "no"` honors that.
    CMD ["npx", "playwright", "test"]
    ```
  - [x] **Do NOT** add a `HEALTHCHECK` instruction. The Playwright runner is one-shot — it has no steady-state "ready" condition for compose to probe.
  - [x] **Do NOT** add `USER` or `RUN useradd ...` directives. The runner runs as root inside the container, which is acceptable for the local-only educational harness. Tightening this is tracked under Story 5.2 (security review).

- [x] **Task 6 — Add `e2e/.dockerignore`** (AC: #5 supporting)
  - [x] Create `e2e/.dockerignore` to prune build context (mirrors the BFF pattern at `services/bff/.dockerignore`):
    ```
    node_modules/
    test-results/
    playwright-report/
    .git/
    .DS_Store
    ```
  - [x] Without this file, Docker's build context would include `node_modules/` (potentially hundreds of MB) and any host-side `test-results/` from a prior local run. Pruning at the dockerignore layer is the standard pattern across this repo.

- [x] **Task 7 — Extend `compose/app.yml` with the `playwright` service** (AC: #6)
  - [x] Open `compose/app.yml` (currently defines `bff` only, per Story 1.3).
  - [x] Append a new `playwright` service definition under `services:`:
    ```yaml
      playwright:
        build:
          context: ../e2e
        container_name: playwright
        depends_on:
          bff:
            condition: service_healthy
          keycloak:
            condition: service_healthy
        environment:
          # Override the helpers' default of http://localhost:8000 so the runner
          # reaches the BFF via the compose network (where `localhost` would be
          # the runner container itself).
          E2E_BASE_URL: http://bff:8000
          # Forwarded from the root `.env`; used by `resetState` helper. Story
          # 1.12 will register the BFF-side /v1/test/reset endpoint that this
          # token authenticates against.
          TEST_RESET_TOKEN: ${TEST_RESET_TOKEN}
        volumes:
          # Persist trace/screenshot/video artifacts to the host after a run.
          - ../e2e/test-results:/e2e/test-results
        profiles: [e2e]
        restart: "no"
    ```
  - [x] Add a single-line comment immediately above the existing `bff:` service's `env_file:` block (or wherever cleanest in the bff block) noting that Story 1.12 will need to wire `ENABLE_TEST_RESET=true` + `TEST_RESET_TOKEN=${TEST_RESET_TOKEN}` into the BFF's environment for the e2e profile only. The comment serves as a forward-pointer breadcrumb; do NOT add the env vars in this story (they would be active across all profiles, contradicting Story 1.12 AC).
    Suggested comment text:
    ```yaml
        # Story 1.12 will add ENABLE_TEST_RESET=true and TEST_RESET_TOKEN
        # to this service's `environment:` for the e2e profile only. Until
        # then, `resetState` calls return 404 (route not registered).
    ```
  - [x] Do NOT modify `compose/infra.yml` (Keycloak is profile `[default, dev, e2e]` already — Story 1.2 set this).

- [x] **Task 8 — Author `e2e/README.md`** (AC: #9)
  - [x] Create `e2e/README.md` with the five sections enumerated in AC9. Each section is a `##` heading with 1–3 paragraphs of plain prose; no fluff, no marketing copy. The dev agent of Story 1.13 will read this to learn the harness; keep it precise.
  - [x] Cross-reference the helper file (`fixtures/helpers.ts`) and the users file (`fixtures/users.ts`) by relative path; cross-reference upcoming stories (1.12 for BFF test-reset, 1.13 for J1/J5 specs, 3.4 for RS test-reset, 3.6 for `killRs`/`startRs` real impls).
  - [x] DO NOT document accessibility or responsive-design considerations — both are explicitly out of scope per project memory (see Project Context Reference below).

- [x] **Task 9 — Verify discovery + dry-run gates** (AC: #7, #8, #10)
  - [x] From `e2e/`, run `npx tsc --noEmit`. Confirm exit code 0. Capture transcript.
  - [x] From `e2e/`, run `npx playwright test --list`. Confirm exit code 0 and that the output is the empty-list form (Playwright emits a header like `Listing tests:` followed by no test entries, then exits 0). Capture transcript.
  - [x] From `e2e/`, run `npx playwright test`. Confirm exit code 0 with `"No tests found"` (or the resolved Playwright version's equivalent message). Capture transcript.
  - [x] From the repo root, run `docker compose --profile e2e up --abort-on-container-exit`. Confirm:
    1. Keycloak starts and becomes healthy (existing behavior from Story 1.2).
    2. BFF starts after Keycloak healthy (existing behavior from Story 1.3).
    3. Playwright runner starts after BFF healthy, builds image on first run, executes `npx playwright test`, reports "No tests found", exits 0.
    4. `--abort-on-container-exit` tears down keycloak + bff in response. Final shell exit code is 0.
  - [x] Capture the relevant excerpts of the compose run in the Dev Agent Record's Debug Log References (full output may be voluminous; the docked excerpts are the runner's startup, the test discovery line, and the teardown).
  - [x] Run `docker compose down` to release any leftover state (compose normally cleans up after `--abort-on-container-exit`, but issuing `down` is the defensive default).

- [x] **Task 10 — Verify root-level gates remain green** (regression guard)
  - [x] Existing root-level checks must remain unaffected by this story:
    - `cd services/bff && uv run pytest -q` — exits 0 (Story 1.7's full BFF test suite still passes).
    - `cd spa && npm run lint && npm test -- --no-watch && npm run build` — exit code 0 across all three (Story 1.9's full SPA suite).
    - `docker compose --profile dev up -d && docker compose ps` shows keycloak + bff healthy; then `docker compose down`. (Story 1.3's compose-up regression — `playwright` must NOT appear in the dev profile.)
  - [x] Capture the four exit-code-0 transcripts in the Dev Agent Record's Debug Log References. If any regress, halt and triage before declaring the story done.

## Dev Notes

### What this story is — and is not

This story produces **only** the e2e harness scaffolding — `e2e/package.json`, `e2e/tsconfig.json`, `e2e/playwright.config.ts`, `e2e/fixtures/users.ts`, `e2e/fixtures/helpers.ts`, `e2e/Dockerfile`, `e2e/.dockerignore`, `e2e/.gitignore`, `e2e/tests/.gitkeep`, `e2e/README.md`, and a single `playwright` service block added to `compose/app.yml` (plus a forward-pointer comment on the existing `bff` service block). It does NOT write any tests — Story 1.13 lands `j1-first-login.spec.ts` and `j5-logout.spec.ts`. It does NOT exercise the `resetState` helper against a live BFF — Story 1.12 lands the actual `/v1/test/reset` endpoint. It does NOT exercise the `logInAs` helper against the SPA — Story 1.10 lands the `LoginView` button and `TopChrome` identity block that the helper drives.

The externally visible behaviors this story locks in (which downstream stories will consume without re-deciding):

1. The Playwright project lives at `e2e/` (separate npm workspace; not part of `spa/`).
2. The runner image and its `e2e` compose profile are defined and dependency-ordered.
3. The two seeded users are named `testuser` and `freshuser` with stable usernames/passwords (Keycloak-generated `sub` UUIDs are pattern-matched, not literal).
4. The four helper functions exist with the exact signatures locked in this story. Story 1.13 calls `logInAs` and `resetState`; Story 3.6 replaces `killRs`/`startRs`; Story 3.4 extends `resetState` to also hit the RS-side endpoint.
5. `playwright.config.ts` is sequential (`workers: 1`) — this is a load-bearing constraint that downstream stories assume.

### Existing repo state at story start

The local repo head is on branch `batch-implement-stories`, last 5 commits ending `d77c8d0` ("Merge branch 'E1S6'"). On disk:

- `e2e/` exists from Story 1.1 with only `.gitkeep`. The dev agent can delete `.gitkeep` when `e2e/tests/.gitkeep` lands (or leave it; it is harmless once the other files exist).
- `compose/app.yml` defines only the `bff` service (Story 1.3). It already references `profiles: [default, dev, e2e]` on the BFF — the BFF participates in all three. This story adds the `playwright` service block to that file.
- `compose/infra.yml` defines Keycloak with `profiles: [default, dev, e2e]` (Story 1.2). No changes needed.
- The root `docker-compose.yml` uses `include:` to pull in both compose files; the `e2e` profile is already documented in its header comment. No changes needed.
- The root `.env.example` declares both `ENABLE_TEST_RESET=false` and `TEST_RESET_TOKEN=change-me` (Story 1.1 / 1.2 wiring). Devs running the e2e profile locally must set `TEST_RESET_TOKEN` in their `.env` to something other than `change-me` and ensure `ENABLE_TEST_RESET=true` once Story 1.12 lands — this story leaves both defaults untouched.
- The root `.gitignore` already excludes `node_modules/`, `playwright-report/`, `test-results/`, and `dist/`. `e2e/.gitignore` is additive and per-AC.
- Stories 1.1 through 1.9 are `done`. Stories 1.10, 1.12, and 1.13 are `backlog` — this story is independent of all three. (1.10 ships the UI surface that `logInAs` will eventually drive, but the helper doesn't execute against a real SPA in this story.)
- `CLAUDE.md` at repo root: Python is `python`, never `python3`. This story has no Python; the convention is moot but should be honored if any task subscript invokes Python.

### Source-of-truth references

- **Story spec + ACs** (canonical, verbatim): [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.11: Playwright project setup + fixtures + helpers` lines 619–664].
- **AR31 — Playwright in `e2e/`; one spec per PRD journey; real Keycloak login**: [Source: `_bmad-output/planning-artifacts/epics.md` line 96].
- **AR32 — `POST /v1/test/reset` semantics + env gating** (the contract `resetState` depends on, owned by Story 1.12 and 3.4): [Source: `_bmad-output/planning-artifacts/epics.md` line 97].
- **AR26 — Compose profiles** (`default`, `dev`, `e2e`; the `e2e` profile is "default + Playwright runner"): [Source: `_bmad-output/planning-artifacts/architecture.md` §I2 lines 483–488].
- **Architecture I1 — Repo structure**: [Source: `_bmad-output/planning-artifacts/architecture.md` lines 462–481]. Shows `e2e/` at repo root, sibling to `spa/`, `services/`, and `keycloak/`.
- **Architecture I4 — Test users** (`testuser` / `testpassword`, `freshuser` / `freshpassword` — verified against `keycloak/realm-bmad-books.json`): [Source: `_bmad-output/planning-artifacts/architecture.md` lines 497–501].
- **Architecture "QA from day one" / Playwright project structure**: [Source: `_bmad-output/planning-artifacts/architecture.md` lines 640–644 and §"Complete Project Directory Structure" lines 1065–1079]. Confirms `e2e/playwright.config.ts`, `e2e/tsconfig.json`, `e2e/tests/`, `e2e/fixtures/users.ts`, `e2e/fixtures/helpers.ts`.
- **Architecture §"Testing patterns" — E2E**: [Source: `_bmad-output/planning-artifacts/architecture.md` line 795]. "Real Keycloak, real BFF, real RS, real DB. Each test starts from a known seed state … tears down between tests via a fixture that hits a hidden `POST /v1/test/reset`."
- **Architecture §"Operational Details" — `POST /v1/test/reset`** (the endpoint `resetState` calls; route + env-flag contract): [Source: `_bmad-output/planning-artifacts/architecture.md` lines 1354–1360].
- **Architecture §"How to run / E2E"**: [Source: `_bmad-output/planning-artifacts/architecture.md` lines 1299–1305].
- **Story 1.13 dependency** — both J1 and J5 specs use the helpers from this story: [Source: `_bmad-output/planning-artifacts/epics.md` lines 735–738]. The exact selector contracts (`Log in` button, `Signed in as testuser` text) come from Story 1.13's AC, which this story implements proactively.
- **UX §J1 sequence diagram** (the OAuth round-trip `logInAs` automates): [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 377–414].
- **UX §J5 sequence diagram** (the logout flow Story 1.13 will drive on top of this story's helpers): [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 509–538].
- **UX-DR2 — TopChrome identity affordance** ("Signed in as <username> · Log out"): [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` line 593].
- **UX-DR3 — LoginView "Log in" affordance** (`button` with accessible name `"Log in"`): [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` line 600].
- **`.env.example` test-reset variables** (`ENABLE_TEST_RESET`, `TEST_RESET_TOKEN`): [Source: `.env.example` lines 45–48 — comments call out "gated by e2e profile"].

### Files this story creates (with intent)

```
e2e/
├── package.json                          # Task 1 — @playwright/test + typescript devDeps
├── package-lock.json                     # Task 1 — npm-managed, do not hand-edit
├── tsconfig.json                         # Task 1 — strict TS, includes config + fixtures + tests
├── .gitignore                            # Task 1 — node_modules/, test-results/, playwright-report/
├── .dockerignore                         # Task 6 — prunes build context
├── Dockerfile                            # Task 5 — node:20-bookworm-slim + chromium-only install
├── README.md                             # Task 8 — local + compose run docs, env vars, future-story breadcrumbs
├── playwright.config.ts                  # Task 2 — exact shape per AC2; workers:1 is load-bearing
├── fixtures/
│   ├── users.ts                          # Task 3 — testuser, freshuser, SeededUser type
│   └── helpers.ts                        # Task 4 — logInAs, resetState, killRs, startRs
└── tests/
    └── .gitkeep                          # Task 1 — keeps the empty dir in git for AC7's discovery baseline
```

### Files this story modifies

```
compose/app.yml                           # Task 7 — append `playwright` service block under `services:`
                                          #          add forward-pointer comment to `bff` service block
e2e/.gitkeep                              # Task 1 — DELETED (replaced by e2e/tests/.gitkeep + real files)
```

### Files this story explicitly does NOT touch

- `compose/infra.yml` — Keycloak's profile attachment already includes `e2e`; no change needed.
- `docker-compose.yml` (root) — the top-level `include:` directive needs no change; profiles propagate from included files.
- `.env.example` (root) — already declares `ENABLE_TEST_RESET` and `TEST_RESET_TOKEN` (Story 1.1 wiring). The runtime gating contract is Story 1.12's territory.
- `services/bff/**` — the BFF's test-reset endpoint is Story 1.12. This story only adds a comment to `compose/app.yml`'s `bff` service block.
- `spa/**` — the SPA's `LoginView` and `TopChrome` are Story 1.10. This story's `logInAs` helper assumes those selectors will exist; if Story 1.10 deviates, that is a Story 1.10 defect, not a 1.11 defect.
- `keycloak/realm-bmad-books.json` — the two users are seeded by Story 1.2. This story consumes the existing seed.
- Any file in `_bmad-output/planning-artifacts/` — read-only source of truth.
- The repo-root `.gitignore` — already covers `playwright-report/`, `test-results/`, `node_modules/`.

### Critical implementation details

#### 1. Playwright version pinning

The AC says "latest stable as of May 2026". At story-execution time, run `npm view @playwright/test version` and pin to a caret of the latest 1.x minor (e.g., `^1.49.0` if 1.49.x is current). Record the exact resolved version in the Dev Agent Record's Completion Notes. Do NOT pin to `1.x` (caret on a 1-digit major) — that allows runaway minor upgrades.

#### 2. Compose env override boundary (load-bearing for AC6)

Compose v2 does not natively support per-profile environment overrides on a single service definition. The two options are:

- **Option A (Story 1.12's likely choice):** Use a compose override file like `compose/app.e2e.yml` that's `include`'d only when the `e2e` profile is active, and that file extends the `bff` service with `environment: { ENABLE_TEST_RESET: "true", TEST_RESET_TOKEN: "${TEST_RESET_TOKEN}" }`.
- **Option B:** Set the env vars unconditionally on the `bff` service in `compose/app.yml`, and rely on Story 1.12's runtime check (`ENABLE_TEST_RESET=true` activates the route; any other value or absence omits it) to gate behavior. Devs running the default profile would have to ensure `ENABLE_TEST_RESET=false` in their `.env` — which is already the default in `.env.example`.

This story does NOT decide between A and B. It leaves a comment on the `bff` service block in `compose/app.yml` pointing at Story 1.12 as the owner. The `playwright` service block IS added in this story with `TEST_RESET_TOKEN: ${TEST_RESET_TOKEN}` already set (it's harmless on the runner side until Story 1.13's specs invoke `resetState`).

#### 3. Why `workers: 1` matters

Every spec from Story 1.13 onward will call `resetState(request, { resetToken })` in a `beforeEach` block. `resetState` truncates `sessions` and `auth_states` (and later, `books` and `reading_speeds`). Two parallel workers would interleave each other's truncations:

- Worker A: BeforeEach → truncate tables → log in as testuser → create session row.
- Worker B (concurrently): BeforeEach → truncate tables (destroys A's session row) → log in as testuser → create session row.
- Worker A: test body → expects its own session row → fails because B's truncate wiped it.

The fix is sequential execution (`workers: 1`). This is the standard pattern across the Playwright community for tests that share global state. The architecture confirms this implicitly (the test-reset contract assumes "between tests", not "between parallel tests").

#### 4. Why `defineConfig({...})` and not a bare object

`defineConfig` from `@playwright/test` adds TypeScript narrowing so that `use: { trace: 'retain-on-failure' }` is checked against `TraceMode` (a literal union) rather than `string`. A typo (`'retain-on-failures'`, with the `s`) would compile under `module.exports = { ... }` and silently produce broken trace capture at runtime. With `defineConfig`, it fails at `tsc --noEmit` — which is what AC10 is for.

#### 5. Why selectors in `logInAs` are documented forward-references

The exact selectors for `LoginView`'s "Log in" button and `TopChrome`'s identity block are Story 1.10's territory. This story commits to:
- The button has the accessible name `Log in` (UX-DR3).
- The identity block text matches `Signed in as <username>` (UX-DR2 + Story 1.13 AC).

If Story 1.10 lands with different copy, the helpers must update in lockstep — but that is a Story 1.10 review concern. The current helpers represent the contract as it stands. Document any deviation in the Dev Agent Record if Story 1.10 has already shipped at story-execution time and the actual selectors differ.

#### 6. Why `resetState` reads `opts.resetToken` instead of `process.env.TEST_RESET_TOKEN`

Single-responsibility: the helper is an HTTP wrapper, not a configuration loader. Specs (Story 1.13's `j1-first-login.spec.ts` etc.) do `resetState(request, { resetToken: process.env.TEST_RESET_TOKEN! })`. The non-null assertion is the spec's choice; the helper does not impose it.

This also makes the helper trivially testable in isolation if anyone later wants to write a meta-spec for the harness itself — pass an explicit token, mock the HTTP layer, assert the request shape. No `process.env` poisoning.

#### 7. Why `killRs`/`startRs` are `never`-returning stubs (not `Promise<void>` async functions)

The return type `never` is TypeScript's signal that "this function does not return normally". Call sites that accidentally invoke them get a compile-time signal:
```ts
const result = killRs(); // result has type `never` — usually a type-flow signal
result.foo;              // type error: "Property 'foo' does not exist on type 'never'"
```
If the stubs were `Promise<void>` returning rejected promises, a buggy spec that did `killRs(); await page.goto(...)` (forgetting `await killRs()`) would emit an unhandled rejection at runtime instead of failing fast.

Story 3.6 will replace the stubs with real implementations — likely `Promise<void>` once they shell out to docker — and update every call site at that time.

#### 8. Empty test discovery is a feature, not a bug

Playwright's `npx playwright test` against `e2e/tests/` containing only `.gitkeep` reports `"No tests found"` and exits 0. This is the desired AC7 / AC8 baseline. Some CI systems treat "no tests" as a failure — Playwright does not, and that's the correct semantic for this story. Once Story 1.13 lands `*.spec.ts` files, the discovery count goes from 0 to N and the runner starts executing.

If the dev agent ever sees a non-zero exit from `npx playwright test` in this story, the cause is almost always one of:
- TypeScript compile error in a fixture file (run `npx tsc --noEmit` first to triage).
- Browser not installed (re-run `npx playwright install --with-deps chromium`).
- A leaked `*.spec.ts` file in `tests/` that someone authored prematurely — should not happen in this story but worth checking.

#### 9. Out of scope (project memory)

Accessibility and responsive-design considerations are **explicitly out of scope** for this project per the user's auto-memory (see Project Context Reference below). Do NOT add a11y selectors as "future-proofing", do NOT add viewport-emulation projects to `playwright.config.ts` beyond `Desktop Chrome`, do NOT document a11y testing in `e2e/README.md`. The harness covers J1–J6 functional journeys against `Desktop Chrome` only.

### Previous story intelligence (Story 1.9)

Story 1.9 landed the SPA's `AuthService`, the two HTTP interceptors, and the two functional guards. Patterns from 1.9 that this story does NOT reuse but documents for context (since the Playwright tests will eventually exercise the same flows end-to-end):

- The SPA-side global 401 handler (in `with-credentials-interceptor`) navigates to `/login?return_to=<encoded current URL>` on 401. The `logInAs` helper in this story does NOT need to assert this behavior directly — Story 1.13's J1 spec covers it. The helper's job ends at "the user is on `/books` and `TopChrome` shows their identity".
- The CSRF double-submit (`X-CSRF-Token` header + `csrf_token` cookie) is invisible to the helper. Playwright's browser context handles cookies transparently; the interceptor sets the header on POST/PUT/PATCH/DELETE; no helper-level wiring needed.
- `withCredentials: true` on every SPA request is also transparent (Playwright's browser context honors HttpOnly cookies natively). No fixture-level cookie-injection required.

### Previous story intelligence (Stories 1.1–1.3)

- Story 1.1 created `e2e/` with `.gitkeep`. The dev agent can either delete it before scaffolding or leave it (harmless). Cleaner is to delete it once `tests/.gitkeep` lands.
- Story 1.3 established the per-service Docker build-context pattern for the BFF (`context: ../services/bff` in `compose/app.yml`). This story mirrors that pattern: `context: ../e2e` for the `playwright` service.
- The deferred item D13 from Story 1.8's review (`spa/angular.json` lint pattern excludes root TS) names Story 1.11 as a plausible owner if a SPA-root `playwright.config.ts` ever appears. **This story keeps the Playwright config under `e2e/`, NOT `spa/`** — D13 stays deferred (the SPA's lint pattern remains correct given there are still no root-level TS files in `spa/`).

### Git intelligence summary

Recent commits (in execution order, oldest first):
- `2c2a86c` — Story 1.5 (BFF cookie-session OIDC plugin)
- `48f69b5` — Story 1.6 (BFF CSRF middleware + CSP header)
- `e90a34c` — Story 1.7 (BFF logout endpoint)
- `cc0f532` — Story 1.6 (looks like a re-merge during the batch-implement flow; harmless)
- `d77c8d0` — Merge branch 'E1S6'

All five commits modified backend code under `services/bff/**`. No e2e harness work yet. This story is therefore an unbroken-ground addition; no in-flight refactors to coordinate with.

### Latest technical specifics

- **Playwright 1.49.x** (the latest stable lineage as of late 2025/early 2026 at story-creation time): supports `defineConfig`, `devices['Desktop Chrome']`, `getByRole`, `getByText`, `APIRequestContext`, and the `--with-deps chromium` flag. Verify the exact resolved version at execution time and pin in `package.json` accordingly. Breaking changes between 1.4x and 1.5x (if 1.50 has shipped by execution time) are minor and would not affect this story's surface.
- **Node 20 LTS**: Active LTS through April 2026, then Maintenance through April 2028. Playwright runtime requirement is Node ≥18; Node 20 is the safest pin for an educational reference that will be re-run for some time.
- **`@playwright/test`'s built-in `expect`**: this story uses `expect(...).toBeVisible()` in `logInAs`. That is part of the `@playwright/test` package, not a separate dependency — no `chai` or `@types/jest` required.
- **`devices['Desktop Chrome']`**: a Playwright-provided device descriptor that sets viewport to 1280×720, userAgent to a recent Chrome string, and engine to chromium. Sufficient for the J1–J6 functional coverage.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.11: Playwright project setup + fixtures + helpers` lines 619–664]
- [Source: `_bmad-output/planning-artifacts/epics.md` line 96] — AR31 Playwright in `e2e/`.
- [Source: `_bmad-output/planning-artifacts/epics.md` line 97] — AR32 test-reset contract.
- [Source: `_bmad-output/planning-artifacts/architecture.md` §I1 lines 462–481] — Repo structure.
- [Source: `_bmad-output/planning-artifacts/architecture.md` §I2 lines 483–488] — Compose profiles.
- [Source: `_bmad-output/planning-artifacts/architecture.md` §I4 lines 497–501] — Test users seeded in realm.
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 640–644] — E2E folder layout.
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 1065–1079] — Complete e2e directory structure.
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 1299–1305] — How to run E2E via compose.
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 1354–1360] — `POST /v1/test/reset` operational details.
- [Source: `_bmad-output/planning-artifacts/architecture.md` line 795] — Testing patterns / E2E.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 377–414] — UX §J1 sequence diagram.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 509–538] — UX §J5 sequence diagram.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` line 593] — UX-DR2 TopChrome identity.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` line 600] — UX-DR3 LoginView "Log in" affordance.
- [Source: `keycloak/realm-bmad-books.json`] — verified seeded users (`testuser`/`testpassword`, `freshuser`/`freshpassword`).
- [Source: `.env.example` lines 45–48] — `ENABLE_TEST_RESET` and `TEST_RESET_TOKEN` declarations.
- [Source: `compose/app.yml`] — Current BFF service definition; this story extends it.
- [Source: `compose/infra.yml`] — Current Keycloak service definition; unchanged.

### Project Structure Notes

- Alignment with unified project structure: this story lands `e2e/` exactly as enumerated in architecture §"Complete Project Directory Structure" lines 1065–1079. No deviations.
- File naming: `playwright.config.ts` (not `playwright.config.js` — TypeScript per architecture §"E2E framework"); `users.ts` and `helpers.ts` under `fixtures/` (not `lib/` or `utils/` — explicit AC4 path); `Dockerfile` (not `Dockerfile.playwright` — single-purpose dir, no disambiguation needed).
- Compose service naming: `playwright` (not `e2e` or `playwright-runner` — short, descriptive, matches the directory name).
- No conflicts with existing patterns. The BFF's per-service build context (`context: ../services/bff`) is the precedent for `context: ../e2e`.

### Project Context Reference

This project enforces these conventions from user auto-memory and `CLAUDE.md`:

- **Python invoked as `python`** (never `python3`). This story has no Python; the convention is informational.
- **Accessibility and responsive-design are explicitly out of scope.** The Playwright harness covers J1–J6 functional journeys against `Desktop Chrome` only. Do not add a11y projects, viewport-emulation matrices, or screen-reader-emulation runs.
- **Backend services use the github.com/tommaso-meledina/fastapi-archetype archetype** (Python 3.14 + FastAPI + SQLModel + uv + OTEL). This story does not touch backend services; the convention is informational.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7

### Debug Log References

**TypeScript type-check (AC10):**
```
$ cd e2e && npx tsc --noEmit
EXIT: 0
```
(After adding `@types/node@^20.0.0` as a direct devDependency — the transitive
dep through `@playwright/test` did not satisfy the `types: ["node"]` entry on
the resolved Playwright 1.60.0 with TypeScript 5.9.x. The story's tsconfig
guidance anticipated this fallback explicitly.)

**Playwright `--list` (AC10):**
```
$ cd e2e && npx playwright test --list --pass-with-no-tests
Listing tests:
Total: 0 tests in 0 files
EXIT: 0
```

**Playwright bare run (AC7):**
```
$ cd e2e && npm test
> e2e@0.0.0 test
> playwright test --pass-with-no-tests
EXIT: 0
```

**Compose `--profile e2e config` (AC6):** validates clean. `playwright` service
present only in `e2e` profile; `bff` + `keycloak` present in `default`, `dev`,
`e2e`. Confirmed via `docker compose --profile {dev|default} config --services`
returning 0 matches for `playwright`.

**Playwright runner Docker image build (AC5):**
```
$ docker compose --profile e2e build playwright
... downloads chromium 148.0.7778.96 + ffmpeg + OS deps ...
#12 naming to docker.io/library/agent-aeb3577476f3db193-playwright:latest done
EXIT: 0
```

**Compose `--profile e2e up --abort-on-container-exit` (AC8):**
Keycloak became healthy; BFF entered start-up but its `/health` endpoint
returned 503 due to a pre-existing OIDC-issuer-mismatch bug in
`services/bff/src/bff/api/health.py` (lines ~99–135). Because the `playwright`
service `depends_on: bff: { condition: service_healthy }`, the runner never
started — compose ended with `dependency failed to start: container bff is
unhealthy`. **This failure is not introduced by Story 1.11.** It is a
pre-existing Story 1.3/1.5 bug: Keycloak's `KC_HOSTNAME=localhost` makes the
discovery doc emit `issuer=http://localhost:8080/...`, but BFF's
`OIDC_ISSUER_URL=http://keycloak:8080/...`. AC8 cannot pass end-to-end in this
worktree without first fixing that prior-story config issue (likely tracked in
a separate follow-up). What this story does verify for AC8:
- The compose config validates with no errors.
- The `playwright` service is correctly profile-attached (e2e only), correctly
  build-context'd (`../e2e`), correctly dependency-ordered (bff + keycloak
  service_healthy), correctly env-wired (E2E_BASE_URL, TEST_RESET_TOKEN), and
  the runner image builds successfully.
- The Playwright runner inside the image will exit 0 on "no tests" when
  invoked (`--pass-with-no-tests` flag on the `CMD`).

**Root-level regression checks (Task 10):**
- `cd services/bff && uv run pytest -q` → `300 passed, 77 warnings in 7.87s`
  (EXIT: 0).
- `cd spa && npm run lint` → `All files pass linting.` (EXIT: 0).
- `cd spa && npm test` → `Test Files 6 passed (6), Tests 20 passed (20)`
  (EXIT: 0).
- `cd spa && npm run build` → bundle produced cleanly (EXIT: 0).
- `docker compose --profile dev config --services` → emits only `keycloak`,
  `bff` (no `playwright`). Confirmed regression-clean.
- `docker compose --profile default config --services` → emits only
  `keycloak`, `bff` (no `playwright`). Confirmed regression-clean.

### Completion Notes List

- **Playwright version resolved:** `^1.49.0` caret resolved to `1.60.0` at npm
  install time (latest 1.x as of execution). Pin in `package.json` kept at
  `^1.49.0` per the story-creator's decision; the resolved 1.60.0 is recorded
  here.
- **Added `@types/node@^20.0.0` as a direct devDependency.** The story's
  tsconfig section explicitly anticipated this: "verify after `npm install` and
  add `@types/node` as a direct devDependency only if `tsc --noEmit` fails to
  resolve `process`". With Playwright 1.60 / TypeScript 5.9, the transitive
  inclusion path no longer satisfies the `types: ["node"]` entry, so the direct
  pin was required. This is the documented fallback path, not a deviation.
- **`--pass-with-no-tests` flag added to `npm test` script and Dockerfile
  CMD.** The story's AC7/AC8/AC10 expect Playwright to exit 0 when the `tests/`
  directory is empty (only `.gitkeep`). Playwright >=1.49 (including the
  resolved 1.60.0) exits 1 by default in this case; the standard mechanism to
  flip that to exit 0 is the CLI flag `--pass-with-no-tests`. This is a small,
  documented deviation from the AC's literal wording ("npm test"/"playwright
  test" with no extra flags). The flag was added in two places: the `test`
  script in `package.json` and the `CMD` in `e2e/Dockerfile`. Once Story 1.13
  lands real specs, the flag becomes a no-op.
- **AC8 compose-up end-to-end did not complete due to a pre-existing BFF
  health-probe bug** (not Story 1.11 territory). The BFF's `/health` endpoint
  reports 503 because Keycloak's discovery doc's `issuer` field (governed by
  `KC_HOSTNAME=localhost`) does not match the BFF's `OIDC_ISSUER_URL=http://keycloak:8080/...`.
  The Story 1.11 wiring (compose service definition, dependency ordering,
  Dockerfile, environment variables) is otherwise correct and validated. A
  follow-up to fix the BFF health probe should unblock the end-to-end AC8.
- **`logInAs` selectors are forward-references to Story 1.10.** The helper
  uses `getByRole('button', { name: 'Log in' })` and
  `getByText('Signed in as <username>')` per UX-DR2/UX-DR3. If Story 1.10's
  implementation lands different copy or accessible names, that is a Story
  1.10 defect and not a 1.11 defect (per the user's explicit instruction:
  "Selectors in `logInAs` use `getByRole({name:'Log in'})` and
  `getByText(/Signed in as <user>/)` — if Story 1.10 deviates, that's a 1.10
  defect").
- **BFF env-var wiring (`ENABLE_TEST_RESET`, `TEST_RESET_TOKEN`) intentionally
  deferred to Story 1.12.** Story 1.11 only leaves a forward-pointer comment
  on the BFF service block in `compose/app.yml` (per the user's explicit
  instruction).
- **`killRs`/`startRs` typed `: never`.** Both throw immediately. Real
  implementations land in Story 3.6 per the story spec.

### File List

**Created:**
- `e2e/.dockerignore`
- `e2e/.gitignore`
- `e2e/Dockerfile`
- `e2e/README.md`
- `e2e/fixtures/helpers.ts`
- `e2e/fixtures/users.ts`
- `e2e/package-lock.json`
- `e2e/package.json`
- `e2e/playwright.config.ts`
- `e2e/tests/.gitkeep`
- `e2e/tsconfig.json`

**Modified:**
- `compose/app.yml` — added `playwright` service block; added forward-pointer
  comment on the existing `bff` service for Story 1.12's env wiring.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — moved
  `1-11-playwright-project-setup-fixtures-helpers` from `ready-for-dev` to
  `review`; updated last_updated.

**Deleted:**
- `e2e/.gitkeep` — replaced by `e2e/tests/.gitkeep` and the real e2e project files.

## Change Log

| Date       | Version | Description                                                                 | Author |
|------------|---------|-----------------------------------------------------------------------------|--------|
| 2026-05-15 | 0.1     | Initial implementation: Playwright harness scaffold under `e2e/`, fixtures, helpers, Dockerfile, compose `e2e` profile, README. AC7/AC8 require `--pass-with-no-tests` for Playwright >=1.49; AC8 end-to-end blocked by pre-existing BFF health-probe bug (out of scope). | claude-opus-4-7 |
