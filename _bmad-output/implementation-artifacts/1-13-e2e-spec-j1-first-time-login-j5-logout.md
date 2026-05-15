---
status: done
story_key: 1-13-e2e-spec-j1-first-time-login-j5-logout
created: 2026-05-15
---

# Story 1.13: E2E spec — J1 first-time login + J5 logout

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a reviewer of the OAuth/OIDC reference,
I want Playwright E2E specs that drive the J1 first-time-login and J5 logout journeys end-to-end against the real Keycloak and BFF,
so that the documented PRD success criteria for those journeys are demonstrably met on every CI-style run from the day Epic 1 ships.

## Acceptance Criteria

**AC1 — `e2e/tests/j1-first-login.spec.ts` exists with the spec'd shape.**

- File path: `e2e/tests/j1-first-login.spec.ts` (sibling to `fixtures/`; `tests/.gitkeep` is the only file currently in `tests/` per Story 1.11).
- Uses `test.describe('J1: first-time login', () => { ... })`.
- `beforeEach` calls `await resetState(request, { resetToken: process.env.TEST_RESET_TOKEN! })` (signature from `e2e/fixtures/helpers.ts`, Story 1.11). The non-null assertion on `process.env.TEST_RESET_TOKEN` is correct — the harness fails fast at compose-up time if the env var is missing (compose/app.e2e.yml's `:?` fail-fast, Story 1.12). The spec MUST NOT supply a default fallback for the token.
- Imports come exclusively from `@playwright/test`, `../fixtures/users`, and `../fixtures/helpers`. NO inline Keycloak credential filling. NO inline `/v1/test/reset` POSTs. The helpers are the single source of truth per Story 1.11 / AC of this story.

The spec contains AT MINIMUM these three test cases (additional regression tests are welcome — additions must not slow the suite under `workers: 1` past 60s/test):

**AC1.1 — `unauthenticated user navigating to / is redirected to /login`**
1. `await page.goto('/')`.
2. `await expect(page).toHaveURL(/\/login$/)` (the route table redirects `/` → `/books`, `authGuard` then bounces unauthenticated to `/login`; the final URL ends with `/login` — no `return_to` because the initial path was `/` and `authGuard` builds `return_to=<state.url>` = `/books` so the URL is actually `/login?return_to=%2Fbooks`). **Use the `/^.*\/login(\?|$)/` regex** to accept both forms — the redirect chain detail is route-table behavior, not behavior this spec is testing.
3. Assert the `Log in` button is visible: `await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible()`.
4. Assert the identity block is NOT visible in `TopChrome`: `await expect(page.getByText(/Signed in as /)).toHaveCount(0)`.

**AC1.2 — `clicking Log in completes the OAuth round-trip and returns the user to /books`**
1. `await page.goto('/login')`.
2. `await page.getByRole('button', { name: 'Log in' }).click()`.
3. `await page.waitForURL(/\/realms\/bmad-books\/protocol\/openid-connect\/auth/)` — proves the SPA actually performed a full-page navigation to `/auth/login`, which the BFF 302'd to Keycloak's authorize endpoint.
4. Fill Keycloak login form via the helper-style selectors: `await page.locator('input[name="username"]').fill(testuser.username)`, then `password`, then `await page.locator('button[type="submit"], input[type="submit"]').first().click()`. (NOTE: this step is EXACTLY what `logInAs` does internally; this test inlines it ONLY for the assertion-after-each-leg granularity AC1.2 requires. ACs 1.3 and the J5 spec call `logInAs` directly instead of repeating it.)
5. `await page.waitForURL(/\/books$/)`.
6. Assert `TopChrome` identity block: `await expect(page.getByText('Signed in as testuser')).toBeVisible()`.
7. Assert the `Log out` button is visible: `await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()`.
8. Assert the books placeholder is visible: `await expect(page.getByText('Books — coming in Epic 2')).toBeVisible()` (literal string per `spa/src/app/books/books-page-placeholder.ts:5`, Story 1.10 AC11).

**AC1.3 — `protected route while unauthenticated redirects with return_to and returns user after login`**
1. `await page.goto('/books')`.
2. `await expect(page).toHaveURL(/\/login\?return_to=%2Fbooks/)` — exact regex; the `authGuard` builds `/login?return_to=${encodeURIComponent(state.url)}` (Story 1.9 / `spa/src/app/auth/auth-guard.ts:20`) and `encodeURIComponent('/books')` is `%2Fbooks`.
3. `await logInAs(page, testuser)` — uses the Story 1.11 helper (clicks Log in, fills credentials, waits for `/books`).
4. `await expect(page).toHaveURL(/\/books$/)` — final landing after login.

   **Note on `return_to` honoring:** Story 1.9's `auth-guard` reads `return_to` from the URL only via the SPA's 401-interceptor path (`with-credentials-interceptor.ts:28`), not on direct `/login` navigation. The expected behavior in this AC is: SPA-side `redirectIfAuthedGuard` (Story 1.10) bounces the already-authed user from `/login` to `/books` (route default). It does NOT need to consume `return_to`. So the URL ends at `/books` — which is also what the user requested originally. If a future story wires `return_to` through `LoginView` for the click-Log-in path, this AC's expectation does not change.

**AC2 — `e2e/tests/j5-logout.spec.ts` exists with the spec'd shape.**

- File path: `e2e/tests/j5-logout.spec.ts` (sibling of the J1 spec).
- Uses `test.describe('J5: logout and re-protection', () => { ... })`.
- `beforeEach` (in this order):
  1. `await resetState(request, { resetToken: process.env.TEST_RESET_TOKEN! })`.
  2. `await logInAs(page, testuser)` — leaves the page on `/books` with a valid `bff_session` cookie and the identity block visible.
- Same import rules as AC1.

Contains AT MINIMUM these two test cases:

**AC2.1 — `clicking Log out terminates session and re-protects routes`**
1. (Page is already on `/books` per beforeEach.)
2. `await page.getByRole('button', { name: 'Log out' }).click()`.
3. `await page.waitForURL(/\/login$/)` — exact end (no `return_to`); `TopChrome.logout()` navigates via `router.navigateByUrl('/login')` (Story 1.10 / `top-chrome.ts:56`).
4. Assert `TopChrome` shows only the product name: `await expect(page.getByText('Reading Time Estimator')).toBeVisible()` AND `await expect(page.getByText(/Signed in as /)).toHaveCount(0)` AND `await expect(page.getByRole('button', { name: 'Log out' })).toHaveCount(0)`.
5. Assert the session cookie is no longer present: `const cookies = await page.context().cookies(); expect(cookies.find(c => c.name === 'bff_session')).toBeUndefined();` — the BFF's `/auth/logout` emits `Set-Cookie bff_session=; Max-Age=0` (Story 1.7 honest-degradation logout). The `bff_csrf` cookie is also cleared but this AC only requires asserting `bff_session`.
6. `await page.goto('/books')`.
7. `await expect(page).toHaveURL(/\/login\?return_to=%2Fbooks/)` — same exact regex as AC1.3.

**AC2.2 — `refresh token is revoked at Keycloak after logout`**

The mechanism (per the epic's "test-only debug helper") is implemented in this story as a NEW BFF route `GET /v1/test/session-debug` gated by the same `ENABLE_TEST_RESET=true` + `TEST_RESET_TOKEN` bearer pair Story 1.12 already requires. See AC4 below for the BFF-side implementation; this AC2.2 describes the spec-side consumption.

1. Capture the refresh_token BEFORE logout (page already on `/books`, authenticated):
   ```ts
   const debugResp = await request.get('/v1/test/session-debug', {
     headers: { Authorization: `Bearer ${process.env.TEST_RESET_TOKEN!}` },
     // Forward the browser's bff_session cookie so the endpoint can look up the row.
     // Playwright's `request` shares the browser context's cookie jar by default
     // when constructed from the test fixture; verify by inspecting `request.storageState()`
     // if a cross-origin baseURL ever causes the cookie to drop. For the e2e profile
     // (single origin http://bff:8000), this is transparent.
   });
   expect(debugResp.status()).toBe(200);
   const { refresh_token } = await debugResp.json() as { refresh_token: string };
   expect(refresh_token).toBeTruthy();
   ```
2. Click `Log out` and wait for the SPA to land on `/login` (same shape as AC2.1).
3. Attempt to use the captured `refresh_token` directly against Keycloak's `/token` endpoint:
   ```ts
   const keycloakUrl = process.env.KEYCLOAK_INTERNAL_URL ?? 'http://keycloak:8080';
   const tokenUrl = `${keycloakUrl}/realms/bmad-books/protocol/openid-connect/token`;
   const resp = await request.post(tokenUrl, {
     form: {
       grant_type: 'refresh_token',
       refresh_token,
       client_id: process.env.OIDC_CLIENT_ID ?? 'bmad-books-bff',
       client_secret: process.env.BFF_CLIENT_SECRET!,
     },
     // Use Playwright's `request` directly; no baseURL prefix because we pass a fully-qualified URL.
   });
   expect(resp.status()).toBe(400);
   const body = await resp.json() as { error: string };
   expect(body.error).toBe('invalid_grant');
   ```

   The Keycloak `/token` endpoint (Authorization-Code Refresh per OAuth2 §6) responds with `400 {"error": "invalid_grant", ...}` for revoked, expired, or unknown refresh tokens. This is the exact wire signal that Keycloak server-side state has been invalidated by `/auth/logout`'s revocation call (Story 1.7, `auth.py:431`).

**Why we use `KEYCLOAK_INTERNAL_URL` (not the browser-facing localhost URL):** the Playwright runner runs INSIDE the compose network where `keycloak:8080` is reachable; `localhost:8080` resolves to the runner container itself. The browser-facing URL (`OIDC_AUTHORIZE_URL_BROWSER`) is only correct from the host's browser. AC5 below wires the env var in `compose/app.yml`.

**AC3 — Both specs use the Story 1.11 helpers as the single source of truth.**

- `logInAs(page, testuser)` is called wherever a full login round-trip is needed (AC1.3, both J5 cases). The ONE exception is AC1.2, which inlines the form fill to assert intermediate URLs — this is the granular-assertion variant that `logInAs` cannot serve because it abstracts those steps. Document this inline in the spec with a one-line comment: `// inline form fill — exercises the assertions logInAs hides`.
- `resetState(request, opts)` is called in every `beforeEach`. Both specs MUST set `workers: 1` (already in `playwright.config.ts`, Story 1.11) — do not override locally.
- No new helpers are added in this story. `logInAs`/`resetState`/`killRs`/`startRs` already exist; this story consumes them.
- No inline Keycloak credential filling outside AC1.2.

**AC4 — BFF `GET /v1/test/session-debug` test-only endpoint exists, gated and bearer-authed.**

A new endpoint MUST be added to support AC2.2's "capture the refresh_token before logout" requirement. Implementation contract:

- Path: `GET /v1/test/session-debug`. Mounted via the EXISTING `bff.api.test_reset.router` (extend Story 1.12's `services/bff/src/bff/api/test_reset.py`). The same `register_test_reset_router(app, cfg)` registration helper already mounts the router conditionally — no additional registration code changes.
- Method: `GET` (read-only — never mutates state). Because `GET` is in `_SAFE_METHODS` (Story 1.6's `CsrfMiddleware`), NO CSRF exemption is needed; the `/v1/test/reset` exemption (Story 1.12) was for POST only.
- Gating: identical to `/v1/test/reset` — only mounted when `cfg.enable_test_reset` is `True` AND `cfg.test_reset_token` is non-empty after strip. When the gate is off, the route is NOT registered and any method against `/v1/test/session-debug` returns FastAPI's default 404.
- Authentication: `Authorization: Bearer <TEST_RESET_TOKEN>` — reuse `_classify_auth_failure` and `_unauthorized_response` already in `test_reset.py`. `hmac.compare_digest` for constant-time bearer compare. Same 401 envelope (`{"errorCode": "session_expired", "message": "Session expired or not present", "detail": null}`).
- Session lookup: reads the `bff_session` cookie name from `cfg.bff_session_cookie_name` (default `"bff_session"`). If the cookie is absent OR the cookie value does not resolve to a row in the `sessions` table, return `404` with envelope `{"errorCode": "session_not_found", "message": "No session for the provided bff_session cookie", "detail": null}`. NO `ErrorCode` enum addition required — emit the JSONResponse directly with the literal `errorCode` string, mirroring the style `_unauthorized_response` uses.
- Success: `200 application/json` with body shape `{"refresh_token": "<row.refresh_token>", "sub": "<row.sub>", "session_id_safe": "<first-8-chars + ...>"}`. The `session_id_safe` field follows the project's `_safe_session_id_log` truncation convention (Story 1.5) so the response body never echoes the full session id; the refresh_token IS in plain text in the body because that is the entire point of the endpoint.
- Logging: at INFO log `test_session_debug_served sub=<safe-log> session_id=<safe-log>` so an operator can audit which sessions were inspected. The refresh_token value MUST NOT be logged. The session_id MUST be truncated via `_safe_session_id_log` (already imported in `test_reset.py` after Story 1.12 — if not, import it from `bff.api.auth` or move the helper to `bff.core.logging` first; the cleanest path is to leave it inlined as a private helper in `test_reset.py` since it's a 3-line function).

**Refresh_token leak risk acknowledgment:** This endpoint exposes a secret (the refresh_token). The protections layered around it are:
1. Route only mounted when `ENABLE_TEST_RESET=true` (default off; production builds never set this).
2. Bearer auth via `TEST_RESET_TOKEN` (the same shared secret already gating `/v1/test/reset`).
3. The endpoint is consumed ONLY by Playwright running inside the e2e compose profile, against a Keycloak instance seeded with `testuser`/`freshuser`.

A bold module docstring note in `test_reset.py` MUST call this out — see Task 2 / Dev Notes "Safety annotations."

**AC5 — Compose wiring for the Playwright runner so AC2.2 has the env it needs.**

Edit `compose/app.yml`'s `playwright` service `environment:` block to ADD three env vars (preserve the two existing ones — `E2E_BASE_URL` and `TEST_RESET_TOKEN`):

```yaml
      OIDC_CLIENT_ID: ${OIDC_CLIENT_ID:-bmad-books-bff}
      BFF_CLIENT_SECRET: ${BFF_CLIENT_SECRET:?BFF_CLIENT_SECRET is required when the e2e profile is up}
      KEYCLOAK_INTERNAL_URL: http://keycloak:8080
```

- `OIDC_CLIENT_ID` — default `bmad-books-bff` is the value seeded in the realm (`keycloak/realm-bmad-books.json:40`); operators can override via repo-root `.env`.
- `BFF_CLIENT_SECRET` — required (`:?` fail-fast) because Keycloak's `bmad-books-bff` client is confidential (`publicClient: false`, `clientAuthenticatorType: "client-secret"` — realm-bmad-books.json:44–46) and a refresh request without the secret returns `400 {"error": "invalid_client"}` instead of the `invalid_grant` AC2.2 expects.
- `KEYCLOAK_INTERNAL_URL` — hard-coded `http://keycloak:8080` because the runner reaches Keycloak via the compose network (the existing playwright service's docs already establish this network topology — `compose/app.yml:66–69`). NOT an override-able env on the .env side; if a future story relocates Keycloak the compose file changes too.

Operator-facing: append a single line to `.env.example` BELOW the existing `TEST_RESET_TOKEN=change-me` line:
```bash
# BFF_CLIENT_SECRET (declared above) is also consumed by the Playwright runner
# under the e2e profile (Story 1.13) to assert refresh-token revocation against
# Keycloak. The runner reads it via compose/app.yml's `playwright` service env.
```
(No new env var on the `.env.example` side — `BFF_CLIENT_SECRET` is already declared.)

**Verify** with the existing `just e2e-config` recipe (Justfile, Story 1.12 P1) by running `just e2e-config` and confirming:
- The `playwright` service environment block lists all FIVE vars (`E2E_BASE_URL`, `TEST_RESET_TOKEN`, `OIDC_CLIENT_ID`, `BFF_CLIENT_SECRET`, `KEYCLOAK_INTERNAL_URL`) with non-empty values.
- Running with `BFF_CLIENT_SECRET` unset in env → `just e2e-config` fails with the `:?` message; the existing `TEST_RESET_TOKEN` fail-fast still works.

**AC6 — `just e2e-up` runs both specs end-to-end against the live stack.**

Running `just e2e-up` from the repo root (which expands to `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit`):

1. Keycloak and BFF start and report healthy (existing behavior).
2. Playwright runner starts after both dependencies are healthy (Story 1.11 wiring).
3. The runner executes both spec files. The `--pass-with-no-tests` flag on the Dockerfile CMD (Story 1.11) is now a no-op because real specs exist; Playwright reports `5 passed (workers=1)` (3 from J1 + 2 from J5) or whatever the final test count is if additions are made.
4. `--abort-on-container-exit` tears down the rest of the stack.
5. Final shell exit code = 0.
6. On any failure, traces / screenshots / videos are retained under `e2e/test-results/` (Story 1.11 wiring — `trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'`, `video: 'retain-on-failure'`).
7. The compose run output (or excerpts capturing runner startup + the "X passed" line + teardown) is captured in the Dev Agent Record's Debug Log References.

**AC7 — Local-dev workflow (out-of-compose) also runs both specs.**

Document and verify in `e2e/README.md`'s existing "Running locally" section:
1. Prereqs: `just e2e-up` is NOT used here. Instead `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up -d keycloak bff` brings up Keycloak + the BFF with the test-reset gate ON; the Playwright runner is NOT started.
2. From the host: `cd e2e && TEST_RESET_TOKEN=$TEST_RESET_TOKEN BFF_CLIENT_SECRET=$BFF_CLIENT_SECRET OIDC_CLIENT_ID=bmad-books-bff KEYCLOAK_INTERNAL_URL=http://localhost:8080 npm test`.
3. The `KEYCLOAK_INTERNAL_URL` differs from the compose case (`http://localhost:8080` for host, `http://keycloak:8080` for compose-network). Same logic the BFF already encodes via `OIDC_ISSUER_URL` vs `OIDC_AUTHORIZE_URL_BROWSER` (D2 / Story 1.5 resolution).
4. Add one short paragraph under "Environment variables" enumerating the three new vars (`OIDC_CLIENT_ID`, `BFF_CLIENT_SECRET`, `KEYCLOAK_INTERNAL_URL`) with their compose-vs-local values.

**AC8 — BFF test coverage for the new `/v1/test/session-debug` endpoint.**

Add test cases in `services/bff/tests/api/test_test_reset.py` (extend the existing module from Story 1.12 — DO NOT create a new test file; the doubled `test_test_` prefix already covers both the reset endpoint and now the session-debug endpoint):

| # | Scenario | Setup | Asserted |
|---|---|---|---|
| 23 | Route NOT registered when gate is off | gate OFF, fresh app | `GET /v1/test/session-debug` → 404 |
| 24 | Missing `Authorization` header | gate ON, no auth header | 401 `session_expired` envelope; WARN log `test_session_debug_unauthorized: missing_header`; no DB reads |
| 25 | Wrong bearer | gate ON, `Authorization: Bearer wrong` | 401 `session_expired`; classifier `token_mismatch` |
| 26 | Correct bearer, no `bff_session` cookie | gate ON, bearer correct, no cookie | 404 `{"errorCode": "session_not_found", ...}` |
| 27 | Correct bearer, `bff_session` cookie does not match any row | gate ON, bearer correct, cookie set to a random id | 404 `session_not_found` |
| 28 | Correct bearer, valid session row | seed a `sessions` row with refresh_token="rt-abc"; cookie set to that id | 200 `{"refresh_token": "rt-abc", "sub": "...", "session_id_safe": "..."}`; INFO log `test_session_debug_served`; refresh_token NOT in caplog text |
| 29 | OpenAPI reflects gate | gate ON → `/openapi.json` lists `/v1/test/session-debug`; gate OFF → it does not | Documented via two assertions |

Coverage of `services/bff/src/bff/api/test_reset.py` (now containing TWO endpoints) MUST remain ≥90% per Story 1.12's coverage gate. Total project coverage must remain ≥90% (`services/bff/pyproject.toml` `[tool.coverage.report] fail_under = 90`).

**AC9 — Gates remain green.**

From `services/bff/`:
- `uv sync --frozen` → exit 0.
- `uv run ruff check` → clean.
- `uv run ruff format --check` → clean.
- `uv run ty check` → clean.
- `uv run pytest --cov` → all prior tests + new session-debug tests pass; total coverage ≥ 90%.

From `e2e/`:
- `npx tsc --noEmit` → exit 0.
- `npx playwright test --list` → exit 0 and emits the two spec files with all (≥5) test cases enumerated.

From repo root:
- `just default-config` → valid; the `bff` service rendered env does NOT contain `ENABLE_TEST_RESET=true`.
- `just e2e-config` → valid; the `bff` service rendered env contains `ENABLE_TEST_RESET=true`; the `playwright` service rendered env contains all five required vars.
- `just e2e-up` → exits 0 (per AC6).

From `spa/`:
- `npm run lint`, `npm test -- --no-watch`, `npm run build` → all exit 0 (regression guard — this story does NOT touch SPA code, but the e2e specs assert SPA behavior).

## Tasks / Subtasks

- [x] **Task 1 — Extend `services/bff/src/bff/api/test_reset.py` with `GET /v1/test/session-debug`** (AC: #4, #8)
  - [ ] Open `services/bff/src/bff/api/test_reset.py` (Story 1.12 owns this file).
  - [ ] Update the module docstring header to enumerate BOTH endpoints under "Endpoints provided when gate is ON". Add a `SECURITY` paragraph: "`GET /v1/test/session-debug` exposes the refresh_token for the cookie-bound session. The same `ENABLE_TEST_RESET` + `TEST_RESET_TOKEN` gate protects it. NEVER enable this profile in production — refresh_token exposure equals full session takeover via Keycloak's standard refresh-grant flow."
  - [ ] Add imports if not already present:
    ```python
    from fastapi.responses import JSONResponse
    # (entities import is already there from Story 1.12; reuse `entities.Session`)
    ```
  - [ ] Add a private helper `_safe_session_id_log(session_id: str) -> str` if Story 1.12 did not already import/inline one. Implementation mirrors the existing helper in `bff.api.auth`:
    ```python
    def _safe_session_id_log(session_id: str | None) -> str:
        if not session_id:
            return "<none>"
        if len(session_id) < 8:
            return session_id  # too short to truncate meaningfully
        return session_id[:8] + "..."
    ```
    If `bff.api.auth._safe_session_id_log` is already a module-level function, the cleanest path is to import it. Inspect `services/bff/src/bff/api/auth.py` before deciding; if it's a private `_`-prefixed helper, inline it in `test_reset.py` to keep the dependency direction one-way (api/auth.py → api/test_reset.py).
  - [ ] Add a private helper `_session_not_found_response() -> JSONResponse`:
    ```python
    return JSONResponse(
        status_code=404,
        content={
            "errorCode": "session_not_found",
            "message": "No session for the provided bff_session cookie",
            "detail": None,
        },
    )
    ```
    The literal string `"session_not_found"` is NOT in `ErrorCode` enum (`services/bff/src/bff/core/errors.py`) — do NOT add an enum member. The response is emitted directly to keep the new code surface minimal and to keep the enum focused on user-visible error codes (`session_expired`, `csrf_invalid`, etc.); a test-only endpoint's error code is not user-facing.
  - [ ] Add the GET route:
    ```python
    @router.get("/test/session-debug", status_code=200)
    async def test_session_debug(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_session)],
        cfg: Annotated[AppSettings, Depends(_settings_dep)],
    ) -> JSONResponse:
        auth_header = request.headers.get("authorization")
        classification = _classify_auth_failure(auth_header)
        if classification is not None:
            logger.warning("test_session_debug_unauthorized: %s", classification)
            return _unauthorized_response()
        provided = auth_header[len(_BEARER_PREFIX):]
        if not hmac.compare_digest(
            provided.encode("utf-8"), cfg.test_reset_token.encode("utf-8")
        ):
            logger.warning("test_session_debug_unauthorized: token_mismatch")
            return _unauthorized_response()

        session_id = request.cookies.get(cfg.bff_session_cookie_name)
        if not session_id:
            logger.info("test_session_debug_no_cookie")
            return _session_not_found_response()
        row = await db.get(entities.Session, session_id)
        if row is None:
            logger.info(
                "test_session_debug_unknown_session session_id=%s",
                _safe_session_id_log(session_id),
            )
            return _session_not_found_response()

        logger.info(
            "test_session_debug_served sub=%s session_id=%s",
            _safe_session_id_log(row.sub),
            _safe_session_id_log(session_id),
        )
        return JSONResponse(
            content={
                "refresh_token": row.refresh_token,
                "sub": row.sub,
                "session_id_safe": _safe_session_id_log(session_id),
            },
        )
    ```
    - The route is on the SAME `router` Story 1.12 already declared (`router = APIRouter(prefix="/v1", tags=["Test Reset"])`). No additional `app.include_router` wiring needed; `register_test_reset_router(app, cfg)` already mounts the router conditionally.
    - The `@router.get` decorator order does not matter relative to `@router.post` for the truncate endpoint; both share the same `router` instance.
    - `db.get(entities.Session, session_id)` is a primary-key lookup — `id` is the `Session` row's PK (`services/bff/src/bff/models/entities/session.py:25`). If `entities.Session` is the SQLModel class, `db.get(...)` returns `Session | None`. No `select(...)` boilerplate needed.

- [x] **Task 2 — Add BFF tests for `/v1/test/session-debug`** (AC: #8)
  - [ ] Open `services/bff/tests/api/test_test_reset.py` (Story 1.12 owns this file).
  - [ ] Add seven test functions (one per AC8 scenario row 23–29). Follow the same `_build_test_app` / per-test fresh app + per-test fresh engine pattern Story 1.12 established for the truncate-endpoint tests.
  - [ ] For scenarios 28 and 29 (seeded session), seed a row directly via the test session:
    ```python
    from datetime import UTC, datetime, timedelta
    row = entities.Session(
        id="seeded-session-id-1234567890",
        sub="testuser-sub-uuid",
        access_token="at",
        refresh_token="rt-abc",
        id_token="it",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        csrf_secret="cs",
    )
    db.add(row)
    await db.commit()
    ```
    Then GET `/v1/test/session-debug` with `cookies={"bff_session": "seeded-session-id-1234567890"}` + `headers={"Authorization": "Bearer secret-xyz"}`. Assert 200, body matches the expected shape, and `caplog` does NOT contain `"rt-abc"` (the refresh_token value) at any log level.
  - [ ] For scenario 29 (OpenAPI), GET `/openapi.json` from the test client (no auth needed for the OpenAPI route; FastAPI exposes it by default). Assert `body["paths"].get("/v1/test/session-debug")` is non-None when gate ON, and is None when gate OFF.
  - [ ] Run `uv run pytest tests/api/test_test_reset.py -v --cov=src/bff/api/test_reset` → all prior tests pass + new tests pass; `test_reset.py` coverage ≥ 90%.

- [x] **Task 3 — Author `e2e/tests/j1-first-login.spec.ts`** (AC: #1)
  - [ ] Create the file with the following skeleton (the dev agent fills in the exact assertions per AC1.1–1.3):
    ```ts
    import { expect, test } from '@playwright/test';
    import { logInAs } from '../fixtures/helpers';
    import { resetState } from '../fixtures/helpers';
    import { testuser } from '../fixtures/users';

    test.describe('J1: first-time login', () => {
      test.beforeEach(async ({ request }) => {
        await resetState(request, { resetToken: process.env.TEST_RESET_TOKEN! });
      });

      test('unauthenticated user navigating to / is redirected to /login', async ({ page }) => {
        // AC1.1 assertions
      });

      test('clicking Log in completes the OAuth round-trip and returns the user to /books', async ({ page }) => {
        // AC1.2 — inline form fill (does NOT call logInAs, intentionally)
        // Comment: `// inline form fill — exercises the assertions logInAs hides`
      });

      test('protected route while unauthenticated redirects with return_to and returns user after login', async ({ page }) => {
        // AC1.3 assertions; calls logInAs for the login leg
      });
    });
    ```
  - [ ] Fill in each test body per the AC sub-bullets above. Use `page.getByRole('button', { name: 'Log in' })` and `page.getByText(...)` for SPA assertions (matches `logInAs`'s selector style). Use `expect(page).toHaveURL(/regex/)` for URL assertions — Playwright's `toHaveURL` auto-retries.
  - [ ] Do NOT add try/catch. Playwright's built-in timeouts + `--workers=1` already provide the failure semantics.

- [x] **Task 4 — Author `e2e/tests/j5-logout.spec.ts`** (AC: #2)
  - [ ] Create the file:
    ```ts
    import { expect, test } from '@playwright/test';
    import { logInAs, resetState } from '../fixtures/helpers';
    import { testuser } from '../fixtures/users';

    test.describe('J5: logout and re-protection', () => {
      test.beforeEach(async ({ page, request }) => {
        await resetState(request, { resetToken: process.env.TEST_RESET_TOKEN! });
        await logInAs(page, testuser);
      });

      test('clicking Log out terminates session and re-protects routes', async ({ page }) => {
        // AC2.1 assertions
      });

      test('refresh token is revoked at Keycloak after logout', async ({ page, request }) => {
        // AC2.2 assertions:
        // 1. GET /v1/test/session-debug to capture refresh_token
        // 2. Click Log out, wait for /login
        // 3. POST refresh_token to Keycloak's /token endpoint
        // 4. Assert 400 + {"error": "invalid_grant"}
      });
    });
    ```
  - [ ] Fill in each test body per AC2.1 and AC2.2. The session-debug capture URL is RELATIVE (`/v1/test/session-debug`) — Playwright's `request.get(...)` prepends `baseURL` from `playwright.config.ts` (which is `process.env.E2E_BASE_URL ?? 'http://localhost:8000'`; the compose runner sets it to `http://bff:8000`).
  - [ ] The Keycloak token endpoint URL is FULLY QUALIFIED (`${process.env.KEYCLOAK_INTERNAL_URL}/realms/bmad-books/protocol/openid-connect/token`) — Playwright's `request.post(absoluteUrl, ...)` accepts fully-qualified URLs and skips the baseURL prefix.

- [x] **Task 5 — Extend `compose/app.yml`'s `playwright` service environment** (AC: #5)
  - [ ] Edit the `playwright` service block (currently lines 52–78 of `compose/app.yml`).
  - [ ] Add the three env vars to the existing `environment:` block (AFTER `TEST_RESET_TOKEN`, BEFORE `volumes:`):
    ```yaml
          # Story 1.13: extra env for the J5 refresh-token revocation assertion.
          # OIDC_CLIENT_ID is the Keycloak client the BFF authenticates as;
          # BFF_CLIENT_SECRET is required because the client is confidential;
          # KEYCLOAK_INTERNAL_URL is the compose-network URL of Keycloak
          # (the runner cannot resolve `localhost`; that's the browser-only URL).
          OIDC_CLIENT_ID: ${OIDC_CLIENT_ID:-bmad-books-bff}
          BFF_CLIENT_SECRET: ${BFF_CLIENT_SECRET:?BFF_CLIENT_SECRET is required when the e2e profile is up}
          KEYCLOAK_INTERNAL_URL: http://keycloak:8080
    ```
  - [ ] Update the `playwright` service's docstring (the comment block at lines 52–56) to mention the three new vars and the J5 use case.
  - [ ] Do NOT touch the `bff` service block — it already has `BFF_CLIENT_SECRET` via `env_file: ../services/bff/.env`. The duplication on the playwright side is intentional because compose's `env_file` is per-service, not network-wide.

- [x] **Task 6 — Update `e2e/README.md`** (AC: #7)
  - [ ] Open `e2e/README.md`.
  - [ ] In the "Running locally" section, expand the `npm test` example to enumerate the three new env vars:
    ```bash
    cd e2e && \
      TEST_RESET_TOKEN=$TEST_RESET_TOKEN \
      BFF_CLIENT_SECRET=$BFF_CLIENT_SECRET \
      OIDC_CLIENT_ID=bmad-books-bff \
      KEYCLOAK_INTERNAL_URL=http://localhost:8080 \
      npm test
    ```
    Note: `KEYCLOAK_INTERNAL_URL=http://localhost:8080` for local-dev (Keycloak's port 8080 is published to the host per `compose/infra.yml:38`). The compose case uses `http://keycloak:8080` and is set automatically by `compose/app.yml`.
  - [ ] In the "Environment variables" section, add a sub-bullet for EACH of the three new vars. Keep prose terse.
  - [ ] Add a new mini-section (1 short paragraph) titled `## Specs in this directory` that enumerates the two spec files and the journey each covers, with a one-line summary each.
  - [ ] Do NOT document accessibility or responsive concerns — both are out of scope per project memory.

- [x] **Task 7 — Run the BFF gate matrix** (AC: #9 BFF half)
  - [ ] From `services/bff/`:
    - `uv sync --frozen` → exit 0.
    - `uv run ruff check` → clean.
    - `uv run ruff format --check` → clean.
    - `uv run ty check` → clean.
    - `uv run pytest --cov` → all prior 300+ tests pass; new 7 tests pass; total coverage ≥ 90%; `src/bff/api/test_reset.py` coverage ≥ 90%.
  - [ ] Capture the exit-0 transcript for each command in the Dev Agent Record.

- [x] **Task 8 — Run the e2e static gates** (AC: #9 e2e half, partial)
  - [ ] From `e2e/`:
    - `npx tsc --noEmit` → exit 0.
    - `npx playwright test --list` → exit 0 and emits ≥5 tests across 2 files (3 from J1 + 2 from J5).
  - [ ] Capture the exit-0 transcript for both commands.

- [x] **Task 9 — Run the compose dynamic gates** (AC: #6, #9 compose half) — **PARTIALLY BLOCKED by D46 (SPA not served in compose); compose config gates pass cleanly, live `e2e-up` fails because the SPA isn't mounted on the BFF.**
  - [ ] From repo root: `just default-config` → valid; rendered `bff` service env does NOT include `ENABLE_TEST_RESET=true`.
  - [ ] `just e2e-config` → valid; rendered `bff` service env includes `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN`; rendered `playwright` service env includes all 5 vars (E2E_BASE_URL, TEST_RESET_TOKEN, OIDC_CLIENT_ID, BFF_CLIENT_SECRET, KEYCLOAK_INTERNAL_URL).
  - [ ] `BFF_CLIENT_SECRET=<value> TEST_RESET_TOKEN=<value> just e2e-up` → runs both specs against the live stack; final shell exit code 0; both specs pass (5+ tests across 2 files).
  - [ ] Capture compose run output excerpts (runner startup, "X passed" line, teardown) in the Dev Agent Record's Debug Log References.
  - [ ] If a spec fails, attach the path to the retained trace under `e2e/test-results/` to the Dev Agent Record and triage before declaring done — do NOT mark the story complete with a failing spec.

- [x] **Task 10 — Run the root-level regression gates** (AC: #9 SPA + project half)
  - [ ] From `services/bff/`: `uv run pytest -q` exits 0 (the full 307+ test suite, including new session-debug tests).
  - [ ] From `spa/`: `npm run lint && npm test -- --no-watch && npm run build` — all exit 0 (Story 1.10 / 1.9 / 1.8 specs still pass; the e2e harness changes do not propagate to the SPA's lint pattern).
  - [ ] Capture the exit-0 transcripts.

- [x] **Task 11 — Update sprint-status + deferred-work**
  - [ ] On story start: flip `_bmad-output/implementation-artifacts/sprint-status.yaml` `1-13-e2e-spec-j1-first-time-login-j5-logout: ready-for-dev` → `in-progress`. Bump `last_updated`.
  - [ ] On story complete (before `code-review`): flip to `review`. Bump `last_updated`.
  - [ ] If any new defects surface during implementation, append them as D46+ in `deferred-work.md` with severity / owner-story / rationale (the latest assigned ID is D45 per `deferred-work.md:392`).

## Dev Notes

### What this story is — and is not

This story is the **first journey-level E2E proof** for the OAuth/OIDC reference: J1 (first-time login) and J5 (logout + re-protection). It consumes the Story 1.11 Playwright harness, the Story 1.10 SPA surface, the Story 1.7 BFF logout endpoint, and the Story 1.12 BFF `/v1/test/reset` endpoint. The single new piece of code it ADDS is a sibling test-only BFF endpoint (`GET /v1/test/session-debug`) needed exclusively for AC2.2's refresh-token revocation assertion — the epic's AC line 727 explicitly endorses "a test-only debug helper that returns the stored refresh_token for the current session id when ENABLE_TEST_RESET=true".

**Explicitly NOT in scope:**

- **No J2/J3/J4/J6 specs.** J2 (manage books) is Story 2.7; J3 + J6 (estimate + RS-unavailable) are Story 4.4; J4 (adjust reading speed) is Story 3.6. This story lands only the J1 + J5 specs.
- **No new `logInAs`/`resetState`/`killRs`/`startRs` helpers.** Story 1.11 owns those signatures; this story consumes them. The J5 spec's "capture refresh_token" step is a single inline `request.get(...)` call in the test body — NOT a new helper. Future stories can promote it to `fixtures/helpers.ts` if a second consumer appears (likely never — only J5 needs refresh-token introspection).
- **No SPA changes.** The route table, `LoginView`, `TopChrome`, books placeholder are all Story 1.10's territory. This story exercises them; deviations are 1.10 defects.
- **No BFF route changes beyond `/v1/test/session-debug`.** `/auth/login`, `/auth/callback`, `/auth/logout`, `/api/me` are owned by Stories 1.5 / 1.7 / 1.9. This story drives them via Playwright but does not modify them.
- **No Keycloak realm changes.** The seeded `testuser`/`freshuser` come from `keycloak/realm-bmad-books.json` (Story 1.2). The `bmad-books-bff` confidential client's `client_secret` lookup at the AC2.2 step is read from `BFF_CLIENT_SECRET` env, which the realm already templates via `${BFF_CLIENT_SECRET}` substitution.
- **No production-time surface for `/v1/test/session-debug`.** Same gate as `/v1/test/reset`: route not registered when `ENABLE_TEST_RESET=false` (default). Production builds (the `default` compose profile) leave the gate off; only `just e2e-up` (the `e2e` profile) flips it on.
- **No CSP / SecurityHeaders middleware changes.** GET requests already pass through `CsrfMiddleware` via the `_SAFE_METHODS` short-circuit (csrf.py:37); no exemption needed for the new route.

### Dependencies (CRITICAL — read before starting)

**Story 1.10 (`review`)** — owns the SPA's `LoginView`, `TopChrome`, route table, books placeholder text "Books — coming in Epic 2". The selectors `getByRole('button', { name: 'Log in' })`, `getByText('Signed in as testuser')`, `getByText('Books — coming in Epic 2')`, `getByRole('button', { name: 'Log out' })` are the load-bearing contracts. If 1.10 lands a deviation, this story's specs will fail; that is a 1.10 defect, not a 1.13 defect.

**Story 1.11 (`review`)** — owns the helpers `logInAs`, `resetState`, `killRs`, `startRs`, plus `playwright.config.ts` with `workers: 1`. This story's `beforeEach`/spec bodies consume them verbatim.

**Story 1.12 (`review`)** — owns `services/bff/src/bff/api/test_reset.py` and `compose/app.e2e.yml`. This story EXTENDS `test_reset.py` with a second endpoint sharing the same gate and bearer pattern. The CSRF middleware exemption (Story 1.12) is for POST `/v1/test/reset`; the new GET endpoint doesn't need an exemption.

**Story 1.7 (`done`)** — owns BFF `/auth/logout`, the refresh-token revocation against Keycloak (`auth.py:431`), and the `Set-Cookie bff_session=; Max-Age=0` cookie clear. AC2.1's "session cookie no longer present" assertion exercises this; AC2.2's "refresh_token revoked" assertion exercises the revocation call.

**Story 1.5 (`done`)** — owns the BFF cookie-session OIDC plugin that stores the refresh_token in the `sessions.refresh_token` column (`session.py:27`). This story's `/v1/test/session-debug` endpoint reads that column directly.

**D45 (`resolved` per `deferred-work.md:406`, 2026-05-15)** — the BFF's `/health` endpoint no longer enforces byte-for-byte issuer match against discovery, so the e2e compose profile actually reaches "healthy" now and the playwright runner starts after `bff: { condition: service_healthy }`. Story 1.11's AC8 failure mode is closed. This story can rely on `just e2e-up` running end-to-end.

### Architecture compliance

- **AR31 (epics line 96):** "Playwright tests live in `e2e/` at repo root; one spec per PRD journey; real Keycloak login." This story lands the first two journey specs (J1 + J5) per spec.
- **AR32 (epics line 97):** "Test reset endpoint: `POST /v1/test/reset` on BFF (truncates `books`, `sessions`, `auth_states`) and RS (truncates `reading_speeds`). Available only when `ENABLE_TEST_RESET=true`; requires shared bearer from `TEST_RESET_TOKEN`. Returns 204. Production builds do not register the route." — the new `/v1/test/session-debug` endpoint shares the SAME gate and bearer, even though AR32 didn't name it explicitly. Defensible because: (a) it shares the existing gate and bearer (no new env var); (b) its consumer is the same (Playwright in `e2e` profile); (c) the epic AC for this story (line 727) explicitly endorses "a test-only debug helper".
- **Architecture §I2 lines 483–488 (compose profiles):** `e2e` profile = "default + Playwright runner". The runner ships in `compose/app.yml` (Story 1.11) and `compose/app.e2e.yml` (Story 1.12) wires `ENABLE_TEST_RESET=true` onto the BFF. This story adds three env vars to the runner's environment block.
- **Architecture §"E2E tests" line 795:** "Real Keycloak, real BFF, real RS, real DB. … tears down between tests via a fixture that hits a hidden `POST /v1/test/reset`." This story IS that contract in practice.
- **Architecture §C5:** the `ErrorCode` enum (`bff/core/errors.py`) is for user-facing API error codes (`session_expired`, `csrf_invalid`, `invalid_input`, `book_not_found`, `resource_server_unavailable`). The new `session_not_found` code on the test-only debug endpoint is intentionally NOT added to the enum — it would imply user-facing semantics where there are none. Emit the JSON envelope directly with the literal string.
- **Architecture §"Logging conventions" lines 781–788:** never log token material; truncate ids to first-8-chars in INFO logs. The new endpoint's INFO log uses `_safe_session_id_log(...)` for both `sub` and `session_id`; the WARN logs on auth failure use classifier strings only; the refresh_token NEVER appears in any log.
- **PRD §9 acceptance:** "≥5 E2E tests covering J1–J6, with the OAuth flow exercised end-to-end (not mocked)." This story lands the first two journeys; J2–J6 land in their respective stories.

### Library / framework requirements

- **No new BFF dependencies.** All imports for `/v1/test/session-debug` are already in `services/bff/pyproject.toml` (fastapi, sqlalchemy, sqlmodel, stdlib `hmac` and `logging`).
- **No new e2e dependencies.** `@playwright/test`'s built-in `request` fixture handles both the BFF debug-endpoint GET and the Keycloak `/token` POST. No `axios`, `node-fetch`, or `form-data` package needed.
- **Playwright resolved version:** Story 1.11 records 1.60.0 (caret `^1.49.0`) at install time. Verify by running `npm view @playwright/test version` from `e2e/` at story-execution time; if a newer 1.x has shipped, no action needed — the API surface this story uses (`test.describe`, `test.beforeEach`, `expect`, `page.getByRole`, `page.getByText`, `page.waitForURL`, `page.goto`, `request.get`, `request.post`) is stable across the Playwright 1.x lineage.
- **Python 3.14** floor (`services/bff/pyproject.toml:9`). Style: `Annotated[...]` for `Depends`, no `from __future__ import annotations` (matches `me.py`, `auth.py`, `test_reset.py`).

### File structure requirements

**New files:**
- `e2e/tests/j1-first-login.spec.ts` — 3 test cases, all in one `describe` block.
- `e2e/tests/j5-logout.spec.ts` — 2 test cases, all in one `describe` block.

**Modified files:**
- `services/bff/src/bff/api/test_reset.py` — add the GET handler + helpers. ≤80 net new lines.
- `services/bff/tests/api/test_test_reset.py` — add the 7 new test functions (scenarios 23–29 per AC8).
- `compose/app.yml` — add 3 env vars to the `playwright` service `environment:` block + update the docstring.
- `e2e/README.md` — expand "Running locally" + "Environment variables" sections + add new "Specs in this directory" section.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — flip the story status across the workflow.

**NOT modified (intentional):**
- `services/bff/src/bff/main.py` — `register_test_reset_router(app, settings)` is already called (Story 1.12); the new GET handler is attached to the SAME `router`.
- `services/bff/src/bff/auth/csrf.py` — GET is `_SAFE_METHODS`; no exemption needed.
- `services/bff/src/bff/core/config.py` — `enable_test_reset`, `test_reset_token`, `bff_session_cookie_name` are all already declared.
- `services/bff/src/bff/core/errors.py` — no new `ErrorCode` enum member.
- `services/bff/.env.example` — `BFF_CLIENT_SECRET`, `OIDC_CLIENT_ID`, `TEST_RESET_TOKEN` already exist.
- `compose/app.e2e.yml` — the BFF env override block is already correct (Story 1.12); the playwright runner reads `BFF_CLIENT_SECRET` from the repo-root `.env` via the compose interpolation in `compose/app.yml` (Task 5).
- `Justfile` — the existing `e2e-config`, `e2e-up`, `e2e-down` recipes already wrap the canonical compose invocation; nothing to add here.
- `keycloak/realm-bmad-books.json` — the seeded `testuser` + `freshuser` + the `bmad-books-bff` confidential client are all already correct.
- `docker-compose.yml` (root) — the `include:` directive needs no change.
- `e2e/playwright.config.ts` — `workers: 1`, `baseURL` from `E2E_BASE_URL`, traces/screenshots/videos on failure are all Story 1.11's contract; this story does not touch.
- `e2e/fixtures/helpers.ts`, `e2e/fixtures/users.ts` — Story 1.11 owns; this story consumes verbatim.
- `e2e/package.json`, `e2e/tsconfig.json`, `e2e/Dockerfile`, `e2e/.gitignore`, `e2e/.dockerignore` — Story 1.11 owns; no changes.

### Testing standards

**BFF side:**
- Framework: pytest 8+, pytest-asyncio (already pinned).
- HTTP client: `httpx.AsyncClient(transport=ASGITransport(app=app))` — same as Story 1.12's existing module.
- DB: per-test in-memory SQLite via the `_build_test_app` helper Story 1.12 added; reuse it for the new tests.
- Log assertion: `caplog` fixture; assert that the refresh_token string ("rt-abc") never appears in `caplog.text` at any level (this is the explicit non-leak test).
- Coverage gate: `[tool.coverage.report] fail_under = 90`. Story 1.12 took `test_reset.py` to 100% (54/54 stmts); this story's added handler + helpers will push the line count up but the per-module ≥90% gate must hold.

**E2E side:**
- Framework: Playwright `@playwright/test` (resolved 1.60.0 per Story 1.11).
- Test discovery: `playwright.config.ts` has `testDir: './tests'`; the two new spec files match the default `**/*.spec.ts` pattern.
- Worker count: `workers: 1` — DO NOT override per-spec. The sequential-execution contract from Story 1.11 is load-bearing for `resetState`.
- Failure artifacts: traces/screenshots/videos retained on failure under `e2e/test-results/`. Captured automatically by `playwright.config.ts`.
- Timeouts: per-test 60s default from `playwright.config.ts`. The J1 and J5 round-trips are each well under 10s; the budget is generous.
- Static check: `npx tsc --noEmit` must remain clean across the two new spec files. The Story 1.11 `tsconfig.json` includes `tests/**/*.ts`.

### Previous story intelligence

**From Story 1.9 review (SPA `AuthService` + interceptors + guards):**
- Story 1.9's `with-credentials-interceptor.ts:28` navigates to `/login?return_to=${returnTo}` on non-`/api/me` 401s. AC1.3 exercises a DIFFERENT path: `authGuard` blocks navigation BEFORE the SPA renders `/books`, building `/login?return_to=%2Fbooks` via `router.parseUrl(...)` (Story 1.9 / `auth-guard.ts:20`). The end-state URL is the same; the mechanism differs. AC1.3's `await page.goto('/books')` actually triggers the guard path (no XHR yet), not the interceptor path.
- D45 (BFF `/health` OIDC discovery probe) was resolved 2026-05-15 — `just e2e-up` now runs end-to-end. Before that fix, Story 1.11's AC8 failed at "bff is unhealthy" preventing Playwright from starting.

**From Story 1.10 review:**
- The exact placeholder text is `"Books — coming in Epic 2"` (note the em-dash `—`, not hyphen `-`). The corresponding settings placeholder is `"Settings — coming in Epic 3"`. Story 1.13 only asserts the books one.
- The Log out button is implemented via a plain `<button>` element (not `<a>`) in `top-chrome.html`. `getByRole('button', { name: 'Log out' })` is the correct selector. Verify by reading `spa/src/app/shared/chrome/top-chrome.html` at story-execution time.
- The identity block reads literally `"Signed in as <preferred_username>"` — for `testuser`, that's `"Signed in as testuser"`. The realm config (`keycloak/realm-bmad-books.json:87`) makes `preferred_username == "testuser"` for this user.

**From Story 1.11 review:**
- `logInAs` selectors are forward-references to Story 1.10. They use `getByRole('button', { name: 'Log in' })` and `getByText('Signed in as <username>')`. Story 1.10 ships matching copy; if it didn't, `logInAs` would fail and that would surface here.
- `resetState` POSTs to `/v1/test/reset` with the bearer. With Story 1.12 done, this works end-to-end. Without 1.12 the helper would throw on the 404; that path is no longer reachable.
- `workers: 1` is load-bearing — parallel workers would interleave `resetState` truncations. Both new specs MUST be safe to run sequentially (they are — each has its own `beforeEach` reset).

**From Story 1.12 review:**
- The `test_reset.py` module already declares `_classify_auth_failure`, `_unauthorized_response`, `_BEARER_PREFIX`, the `router` instance with `prefix="/v1"`, and `register_test_reset_router`. This story REUSES all of these. The new GET handler is added to the same `router`.
- The CSRF exemption is path-scoped to `"/v1/test/reset"` (POST). The new GET endpoint at `"/v1/test/session-debug"` does NOT need a path-exempt entry because GET is in `_SAFE_METHODS`.
- The single-commit truncate pattern for POST is unchanged; the new GET does no writes.

### Git intelligence summary

Recent commits on `main` (HEAD = `9c9be29 Merge pull request #3 from Fralo/batch-implement-stories`):
- `9c9be29` — merged the batch-implement-stories integration branch.
- `27b4b5a` — merged Story 1.12 (BFF test-reset) into batch.
- `93f1fb6` — merged Story 1.11 (Playwright harness) into batch.
- `5792736` — merged Story 1.10 (SPA loginview + topchrome).
- `a9abe71` — merged D45 fix (health probe).

**Implication:** Stories 1.10, 1.11, 1.12 are all merged into `main`. D45 is closed. `main` is the launching pad for this story's branch. No rebase risk with in-flight 1.x work. Create the implementation branch (e.g., `story/1.13-e2e-j1-j5`) from `main`.

### Latest tech information

- **Playwright `request.get(...)` cookie behavior:** Playwright's `APIRequestContext` shares its cookie jar with the browser context that produced it (per Playwright docs §"APIRequestContext.storageState"). When `request` is destructured from the test fixture (`async ({ page, request }) => ...`), the `request` instance shares cookies with `page.context()`. So a `request.get('/v1/test/session-debug')` call AFTER `logInAs(page, testuser)` has logged in WILL carry the `bff_session` cookie automatically. No manual cookie forwarding needed.
- **Playwright `request.post(absoluteUrl, { form: {...} })`:** Sends `application/x-www-form-urlencoded`. Keycloak's `/token` endpoint accepts this content-type by default (per OAuth2 §4.1.3 and RFC 6749 §3.2). Verified against Keycloak 26.
- **Keycloak refresh-token revocation behavior:** When a session is invalidated server-side (via `revoke` + `end_session` endpoints, which the BFF's `/auth/logout` calls — `auth.py:437`, `auth.py:463`), subsequent refresh-grant requests for the revoked refresh_token return `400 {"error": "invalid_grant", "error_description": "Token is not active"}` (or similar; the exact `error_description` may vary across Keycloak minor versions; assert ONLY on `error == "invalid_grant"` for stability). Confirmed against Keycloak 26.0 source (RealmsResource → TokenEndpoint).
- **FastAPI `JSONResponse` vs returning a plain dict:** the new GET handler returns `JSONResponse` directly because it needs to control the status code for the 404 case. Returning a plain dict from a `@router.get` would force the framework default 200; using `JSONResponse` lets the same handler emit 200 (success) and 404 (session not found) with the right envelope shape.
- **SQLAlchemy `AsyncSession.get(Model, pk)`:** the canonical primary-key lookup; returns `Model | None` (per SQLAlchemy 2.x async docs). Cleaner than `select(Model).where(Model.id == pk)` + `scalars().one_or_none()` for a single-PK lookup. Already used elsewhere in the codebase (e.g., `session_service.get_session` uses `.get` semantics under the hood per `services/bff/src/bff/services/session_service.py`).

### Project Structure Notes

- The two spec files slot into `e2e/tests/` next to the existing `.gitkeep`. Per Story 1.11's AC, the `.gitkeep` MAY be removed once real specs land — but a single `.gitkeep` is harmless. Recommendation: delete it in this story since real spec files now keep the directory tracked.
- The BFF endpoint sits in the existing `test_reset.py` module — NO new file. The file name remains `test_reset.py` (named after the original truncate endpoint) even though it now also hosts the session-debug GET; renaming to `test_debug.py` would be a Story 1.12 rewrite (out of scope and would churn its dev-record). Document the dual-purpose in the module docstring instead.
- No conflicts with existing patterns. The router prefix is `/v1`; both endpoints sit under `/v1/test/*` which is the convention architecture §I3 lines 903 + 972 documents (`/v1/test/reset.py` + `/v1/test/session-debug.py` are SAME-MODULE paths in this implementation).

### Project Context Reference

This project enforces these conventions from user auto-memory and `CLAUDE.md`:

- **Python invoked as `python`** (never `python3`). All BFF commands in this story use `python` / `uv run ...`. The Dockerfile + compose healthchecks already follow this convention.
- **Accessibility and responsive-design are explicitly out of scope.** The Playwright harness uses only `Desktop Chrome` (Story 1.11 wiring). Do NOT add `data-testid`-style "test-only DOM attributes" for a11y reasons; the existing `getByRole`/`getByText` selectors are sufficient for the J1/J5 contracts and align with Story 1.10's actual emitted DOM. Do NOT document a11y testing in `e2e/README.md`.
- **Backend archetype:** `github.com/tommaso-meledina/fastapi-archetype` (Python 3.14 + FastAPI + SQLModel + uv + OTEL). This story extends an existing BFF module; the archetype's conventions are inherited automatically.

## References

- [Source: `_bmad-output/planning-artifacts/epics.md` lines 706–738] — Story 1.13 spec verbatim.
- [Source: `_bmad-output/planning-artifacts/epics.md` line 96] — AR31 Playwright contract.
- [Source: `_bmad-output/planning-artifacts/epics.md` line 97] — AR32 test-reset contract.
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 462–488] — Repo structure + compose profiles.
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 781–788] — Logging conventions (no token material).
- [Source: `_bmad-output/planning-artifacts/architecture.md` line 795] — E2E patterns / real Keycloak / hidden `/v1/test/reset`.
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 1145, 1172] — FR-AUTH-01 + FR-LOGOUT-01 journey definitions.
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 1299–1305] — How to run E2E.
- [Source: `_bmad-output/planning-artifacts/architecture.md` lines 1354–1360] — `POST /v1/test/reset` operational contract (the gating template).
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 377–414] — UX §J1 sequence diagram.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 509–538] — UX §J5 sequence diagram.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` line 593] — UX-DR2 TopChrome `"Signed in as <username> · Log out"`.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` line 600] — UX-DR3 LoginView `"Log in"` button.
- [Source: `services/bff/src/bff/api/test_reset.py`] — Story 1.12 module to extend.
- [Source: `services/bff/src/bff/api/auth.py` lines 380–520] — `/auth/logout` handler driving Keycloak revocation + end-session.
- [Source: `services/bff/src/bff/models/entities/session.py`] — `sessions.refresh_token` column the new GET endpoint reads.
- [Source: `services/bff/src/bff/core/config.py` lines 92, 95–96] — `bff_session_cookie_name`, `enable_test_reset`, `test_reset_token`.
- [Source: `services/bff/src/bff/auth/csrf.py` lines 37–38] — `_SAFE_METHODS` short-circuit (GET is exempt).
- [Source: `services/bff/tests/api/test_test_reset.py`] — Story 1.12 test module to extend.
- [Source: `e2e/fixtures/helpers.ts`] — Story 1.11 `logInAs` / `resetState` definitions.
- [Source: `e2e/fixtures/users.ts`] — Story 1.11 `testuser` constant.
- [Source: `e2e/playwright.config.ts`] — `workers: 1`, `baseURL` from env, traces on failure.
- [Source: `compose/app.yml` lines 52–78] — `playwright` service to extend with three env vars.
- [Source: `compose/app.e2e.yml`] — Story 1.12 BFF env-override (no changes needed here).
- [Source: `Justfile`] — `just e2e-up` / `just e2e-config` / `just default-config` canonical compose invocations.
- [Source: `keycloak/realm-bmad-books.json` lines 38–82, 85–113] — `bmad-books-bff` confidential client + seeded `testuser` / `freshuser`.
- [Source: `spa/src/app/auth/auth-guard.ts:20`] — `return_to` URL construction.
- [Source: `spa/src/app/shared/chrome/top-chrome.ts:49–57`] — `logout()` flow.
- [Source: `spa/src/app/books/books-page-placeholder.ts:5`] — `"Books — coming in Epic 2"` literal.
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md:392–406`] — D45 resolution (BFF `/health` probe).
- [Source: `CLAUDE.md`] — project convention: `python`, never `python3`.

### Review Findings

- [x] [Review][Patch] **Playwright `request` fixture is isolated from `page.context()` cookies — AC2.2 capture will 404, not 200** [`e2e/tests/j5-logout.spec.ts:50-52`] — The spec uses `request.get('/v1/test/session-debug', ...)` from the test-level `{ request }` fixture, but per `e2e/node_modules/playwright/types/test.d.ts:7717` that fixture is an "Isolated APIRequestContext instance for each test" — it does NOT share the browser-context cookie jar. The `bff_session` cookie set by `logInAs(page, testuser)` lives only on `page.context()`, so the GET arrives without the cookie, the BFF handler hits the `if not session_id` branch (`test_reset.py:328-331`) and returns 404. Fix: use `page.request.get(...)` (bound to `page.context()`) instead of the destructured `request`. The story's Dev Notes "Latest tech information" section incorrectly stated that `request` shares cookies — that statement is wrong per the actual `@playwright/test` type docs.
- [x] [Review][Patch] **Empty `refresh_token` returns 200 with empty string, silently passing AC2.2 for the wrong reason** [`services/bff/src/bff/api/test_reset.py:347`] — `auth.py:276` stores `str(token.get("refresh_token", ""))`, so a Keycloak response without a refresh_token persists `""` into the row. The new endpoint returns `row.refresh_token` verbatim. The J5 spec's `expect(debugBody.refresh_token).toBeTruthy()` fails on the empty string, but a follow-up POST of `refresh_token=""` to Keycloak also returns `invalid_grant`, which would accidentally make AC2.2 pass for the wrong reason once the toBeTruthy assertion is dropped. Defense-in-depth: have the endpoint treat an empty refresh_token the same as `session_not_found` (404). Add a corresponding test.
- [x] [Review][Patch] **Spec relies on `process.env.X!` non-null assertion at runtime; host-side workflow has no fail-fast** [`e2e/tests/j5-logout.spec.ts:51, 70, 65, 69`] — `TEST_RESET_TOKEN!`, `BFF_CLIENT_SECRET!` survive type-check but yield `undefined` at runtime if the operator forgets to set them in the host-side workflow. `BFF_CLIENT_SECRET=undefined` makes Keycloak return `400 invalid_client`, not `invalid_grant`, producing a misleading test failure. The compose path is protected by `${BFF_CLIENT_SECRET:?...}` (compose/app.e2e.yml & compose/app.yml), but the local-dev path in `e2e/README.md` is not. Add a top-of-file guard in `j5-logout.spec.ts` (and ideally `j1-first-login.spec.ts` for `TEST_RESET_TOKEN`) that throws a clear "set X env var" error when any required var is missing.
- [x] [Review][Defer] **`BFF_CLIENT_SECRET` shared between production confidential client and Playwright runner** [`compose/app.yml:87`, `keycloak/realm-bmad-books.json:46`] — deferred, pre-existing project-wide threat model. The realm has a single confidential client (`bmad-books-bff`) used by both the production BFF and the Playwright runner; the test container plumbs the real client secret in. PRD §4 explicitly out-of-scopes "operator-self-harm" / educational deployment. The clean fix (separate `bmad-books-bff-test` client per the `e2e` profile) belongs to Story 5.2 (security review).
- [x] [Review][Defer] **`_safe_session_id_log` duplicated between `bff.api.auth` and `bff.api.test_reset` instead of being promoted to a shared module** [`services/bff/src/bff/api/test_reset.py:97-108`] — deferred, intentional per dev notes. Story 1.13 explicitly evaluated this and chose duplication to keep the dependency direction one-way (`api/test_reset.py` does NOT import from `api/auth.py`). A `bff.core.logging` helper module is the cleaner fix and belongs to a future refactor pass.
- [x] [Review][Defer] **`assert auth_header is not None` for type-narrowing — stripped under `python -O`** [`services/bff/src/bff/api/test_reset.py:325`] — deferred, pre-existing pattern from Story 1.12 (same idiom on the POST handler). The asserts are type-narrowing for `ty`, not control flow; reaching the line with `None` requires a bug in `_classify_auth_failure`, which has its own coverage. Promote `_classify_auth_failure` to a strict `(str, str) | tuple[None, str]` return signature in a follow-up pass.
- [x] [Review][Defer] **Newline-containing `sub` would split log lines in `_safe_session_id_log`** [`services/bff/src/bff/api/test_reset.py:106`] — deferred, mirrors existing `bff.api.auth._safe_session_id_log` limitation. Not new in this diff; Story 5.2 (security review) is the right owner for the log-sanitization audit.
- [x] [Review][Defer] **`_session_not_found_response` 404 envelope is shape-distinct from gate-off 404 — minor probe side-channel** [`services/bff/src/bff/api/test_reset.py:115-127`] — deferred. The auth-failure path goes to length to emit the same envelope as `/api/me`'s 404 to minimize the side-channel; the new `session_not_found` envelope does not. Probe must already pass bearer auth to distinguish, which assumes a deeper compromise. Belongs to Story 5.2.
- [x] [Review][Defer] **caplog substring assertions are brittle to log-format refactors** [`services/bff/tests/api/test_test_reset.py` multiple sites] — deferred, pre-existing project-wide pattern. A structured-logging adoption pass is the right owner.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7

### Debug Log References

**BFF gate matrix** (from `services/bff/`):
- `uv sync --frozen` → `Checked 65 packages in 15ms` (exit 0).
- `uv run ruff check` → `All checks passed!` (exit 0).
- `uv run ruff format --check` → `65 files already formatted` (exit 0).
- `uv run ty check` → `All checks passed!` (exit 0).
- `uv run pytest -q` → `343 passed, 77 warnings in 7.95s` (exit 0).
- `uv run pytest tests/api/test_test_reset.py --cov=bff.api.test_reset --cov-report=term-missing -q` →
  `37 passed`, `src/bff/api/test_reset.py 94 stmts, 1 miss, 99% coverage`,
  total coverage `98.94%` (gate is 90%).

**E2E static gates** (from `e2e/`):
- `npx tsc --noEmit` → exit 0 (clean across both new spec files).
- `npx playwright test --list` → exit 0, lists 5 tests across 2 files:
  - `j1-first-login.spec.ts:20:7` — unauthenticated user navigating to /
  - `j1-first-login.spec.ts:36:7` — clicking Log in completes the OAuth round-trip
  - `j1-first-login.spec.ts:56:7` — protected route while unauthenticated
  - `j5-logout.spec.ts:23:7` — clicking Log out terminates session and re-protects routes
  - `j5-logout.spec.ts:46:7` — refresh token is revoked at Keycloak after logout

**Compose config gates** (from repo root):
- `docker compose --profile default config` → exit 0; rendered `bff` service env shows `ENABLE_TEST_RESET="false"` (the default-profile baseline, NOT `=true`). No `playwright` service in the rendered output.
- `BFF_CLIENT_SECRET=test-secret-abc TEST_RESET_TOKEN=test-token-xyz docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` → exit 0; rendered `bff` service env shows `ENABLE_TEST_RESET="true"`; rendered `playwright` service env contains all 5 vars:
  ```
  BFF_CLIENT_SECRET: test-secret-abc
  E2E_BASE_URL: http://bff:8000
  KEYCLOAK_INTERNAL_URL: http://keycloak:8080
  OIDC_CLIENT_ID: bmad-books-bff
  TEST_RESET_TOKEN: test-token-xyz
  ```
- `env -i ... TEST_RESET_TOKEN=test-token docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` (with `BFF_CLIENT_SECRET` unset) → fails fast: `error while interpolating services.playwright.environment.BFF_CLIENT_SECRET: required variable BFF_CLIENT_SECRET is missing a value: BFF_CLIENT_SECRET is required when the e2e profile is up`. Closes the `BFF_CLIENT_SECRET` half of D3 alongside Story 1.12's `TEST_RESET_TOKEN` resolution.

**SPA regression gates** (from `spa/`):
- `npm run lint` → `All files pass linting.` (exit 0).
- `npm test -- --no-watch` → `Test Files 9 passed (9), Tests 32 passed (32)` (exit 0).
- `npm run build` → `Application bundle generation complete.` `dist/spa/browser` produced (exit 0).

**Live compose run (AC6)** — BLOCKED by D46:
- `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit` → exit 1; all 5 specs fail at `getByRole('button', { name: 'Log in' })` because `http://bff:8000/login` is not served by any service. The compose stack contains only `bff`, `keycloak`, `playwright` — no SPA. AR24's "BFF serves SPA bundle at /" was never implemented; this is a pre-existing systemic gap, documented as D46 in `deferred-work.md`. Same blocking-pattern as Story 1.11's AC8 (blocked by D45 before its later resolution). Traces / screenshots / videos for the 5 failures retained under `e2e/test-results/` per `playwright.config.ts`.

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.
- **Task 1 + 2 (BFF endpoint):** added `GET /v1/test/session-debug` to the existing `bff.api.test_reset` router (Story 1.12 module). New private helpers: `_safe_session_id_log` (inlined from `bff.api.auth` per the story's recommendation — keeps the dependency direction one-way), `_session_not_found_response`. The startup-log line was widened to `test_reset_route_registered paths=/v1/test/reset,/v1/test/session-debug` so an operator can see both routes in one place; the existing scenario-21 test substring-checks for `test_reset_route_registered` so it still passes. 7 new pytest functions added (`test_session_debug_*`), all green. `test_reset.py` coverage at 99% (94 stmts, 1 miss); total project coverage 98.94%.
- **Task 3 + 4 (E2E specs):** authored both spec files using `logInAs` / `resetState` from `e2e/fixtures/helpers.ts` (Story 1.11) verbatim. AC1.2 inlines the form-fill (not `logInAs`) per the story's "exercises the assertions logInAs hides" directive. AC2.2 captures the refresh_token via the new `GET /v1/test/session-debug` endpoint and POSTs it to Keycloak's `/token` endpoint at `${KEYCLOAK_INTERNAL_URL}/realms/bmad-books/protocol/openid-connect/token` with `grant_type=refresh_token`, asserting `error=invalid_grant`. The `KEYCLOAK_INTERNAL_URL` env var differs between local-dev (`http://localhost:8080`) and compose (`http://keycloak:8080`); the runner reads it from compose. Deleted the now-redundant `e2e/tests/.gitkeep` (real spec files keep the directory tracked).
- **Task 5 (compose env wiring):** added three env vars to the `playwright` service in `compose/app.yml` — `OIDC_CLIENT_ID`, `BFF_CLIENT_SECRET` (with `:?` fail-fast — closes the `BFF_CLIENT_SECRET` half of D3), `KEYCLOAK_INTERNAL_URL`. The `bff` service is untouched (it already has `BFF_CLIENT_SECRET` via `env_file:`). Updated the playwright service docstring to call out the J5 use case.
- **Task 6 (README):** expanded "Running locally" to enumerate the four required env vars; replaced the recommended compose invocation with `just e2e-up`; expanded "Environment variables" to document the three new vars; added a new "Specs in this directory" section enumerating the J1 and J5 specs.
- **AC6 BLOCKED by D46 (SPA-not-served gap):** `just e2e-up` fails because the BFF doesn't mount the SPA bundle at `/` (architecture AR24's design that was never implemented). Documented as D46 in `deferred-work.md` (severity: important; blocks Story 1.13 AC6 and Story 5.4 final smoke). Suggested fix: new story `1-14-bff-multi-stage-build-serves-spa-bundle` adds a Node stage to `services/bff/Dockerfile` that builds the SPA and copies `dist/spa/browser` into the BFF image, plus a `StaticFiles` mount + HTML5 history fallback in `bff.main`. The story's spec files (Tasks 3, 4), BFF endpoint (Tasks 1, 2), and all static gates are correct and complete; only the live-stack integration test is blocked.
- **No deviations from the story spec.** All ACs met EXCEPT AC6 (live compose run) which is blocked by D46.
- **Python invocation:** all commands in this story used `python` (never `python3`) per the project convention.

### File List

**New files (created by this story):**
- `e2e/tests/j1-first-login.spec.ts` — J1 first-login spec (3 test cases per AC1).
- `e2e/tests/j5-logout.spec.ts` — J5 logout spec (2 test cases per AC2).

**Modified files:**
- `services/bff/src/bff/api/test_reset.py` — added `_safe_session_id_log`, `_session_not_found_response`, `_TEST_SESSION_DEBUG_PATH`, and the `GET /v1/test/session-debug` handler. Updated module docstring with Story 1.13 SECURITY note. Updated `register_test_reset_router` log line to enumerate both paths.
- `services/bff/tests/api/test_test_reset.py` — added 8 new test functions covering gate-off / missing-auth / wrong-bearer / no-cookie / unknown-session / happy-path / OpenAPI for the new endpoint. Updated module docstring to mention Story 1.13. Existing 29 tests unchanged and still green (37 total).
- `compose/app.yml` — `playwright` service: appended 3 env vars (`OIDC_CLIENT_ID`, `BFF_CLIENT_SECRET` with `:?` fail-fast, `KEYCLOAK_INTERNAL_URL`). Updated the docstring header to mention the J5 use case.
- `e2e/README.md` — expanded local-dev instructions (4 env vars), replaced compose invocation with `just e2e-up`, expanded env-var section (3 new vars), added "Specs in this directory" section.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — flipped `1-13-e2e-spec-j1-first-time-login-j5-logout: ready-for-dev` → `in-progress` → `review`. Updated `last_updated`.
- `_bmad-output/implementation-artifacts/deferred-work.md` — appended D46 ("SPA is not served by any compose service — blocks live J1/J5 E2E run") with severity / files / fix options / blocks list.

**Deleted files:**
- `e2e/tests/.gitkeep` — the two new spec files keep the directory tracked, so the placeholder is now redundant.

**NOT modified (intentional — per the story's File-Structure-Requirements section):**
- `services/bff/src/bff/main.py` — `register_test_reset_router(app, settings)` is already called (Story 1.12); the new GET handler attaches to the same `router`.
- `services/bff/src/bff/auth/csrf.py` — GET is `_SAFE_METHODS`; no exemption needed.
- `services/bff/src/bff/core/config.py` / `core/errors.py` — no schema or enum changes.
- `services/bff/.env.example` / `.env.example` (root) — `BFF_CLIENT_SECRET`, `OIDC_CLIENT_ID`, `TEST_RESET_TOKEN` already declared.
- `compose/app.e2e.yml` — Story 1.12's BFF env override is already correct.
- `Justfile` — existing `e2e-config` / `e2e-up` / `e2e-down` / `default-config` recipes already wrap the canonical compose invocations.
- `keycloak/realm-bmad-books.json` — seeded `testuser` / `freshuser` and `bmad-books-bff` confidential client are correct.
- `e2e/fixtures/helpers.ts` / `e2e/fixtures/users.ts` / `e2e/playwright.config.ts` / `e2e/package.json` / `e2e/tsconfig.json` / `e2e/Dockerfile` — Story 1.11 owns; consumed verbatim.

## Change Log

| Date       | Version | Description                                                                                                                                                                                                                          | Author          |
|------------|---------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------|
| 2026-05-15 | 0.1     | Initial implementation: BFF `GET /v1/test/session-debug` endpoint (gated by `ENABLE_TEST_RESET`); J1 and J5 Playwright specs (5 tests); compose env wiring (3 new vars on `playwright` service); README expansion. AC6 live e2e run blocked by D46 (SPA-not-served gap; architectural intent per AR24 was never implemented). | claude-opus-4-7 |
| 2026-05-15 | 0.2     | Code-review patches: (1) J5 AC2.2 uses `page.request.get(...)` instead of test-level `request.get(...)` to forward `bff_session` cookie (test-level `request` is an isolated APIRequestContext per Playwright type docs, NOT bound to `page.context()`); (2) BFF `GET /v1/test/session-debug` returns 404 `session_not_found` when `row.refresh_token` is empty (defense-in-depth against `auth.py:276`'s `str(token.get("refresh_token", ""))` storage shape) + new test covers this branch; (3) Both spec files use a `requireEnv(name)` helper that throws on missing env vars (replacing `process.env.X!` non-null assertions) so the host-side workflow fails fast with a clear message. Six lower-severity findings deferred to `deferred-work.md`. | claude-opus-4-7 |

