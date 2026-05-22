---
title: 'Only-SSO login — delete /login, redirect anonymous traffic to /auth/login'
type: 'refactor'
created: '2026-05-22'
status: 'done'
baseline_commit: '675114cffcb066801151b3cea8f27d64040d627f'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/1-10-spa-loginview-topchrome-route-table.md'
  - '{project-root}/_bmad-output/implementation-artifacts/6-1-spa-angular-ssr-scaffold-proxy-cookie-forwarding.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `LoginView` (story 1.10) is an in-app screen whose only function is a button that redirects to `/auth/login`. It adds a useless hop, ships protected-route hints to anonymous browsers, and is dead weight now that Keycloak is the only auth path.

**Approach:** Delete `LoginView` + `redirectIfAuthedGuard`. Convert `authGuard` from `CanActivateFn` to `CanMatchFn` so lazy chunks never download for anonymous users. On auth failure emit a platform-aware redirect to `/auth/login?return_to=<path>` — SSR via returning a `RedirectCommand` from the guard (Angular SSR's engine emits a real empty-body 302 via `createRedirectResponse` when the router's `lastSuccessfulNavigation().finalUrl` differs from the rendered URL); browser via `window.location.href`. A stub route for `auth/login` is added to `app.routes.ts` so the internal `RedirectCommand` navigation succeeds (the path is physically proxied by `server.ts` before Angular SSR runs, so the stub is never rendered in production). Update the mid-session 401 interceptor and `TopChrome.logout()` to the same target. Endpoint contracts, cookie semantics, CSRF, discovery, role mapping are unchanged.

## Boundaries & Constraints

**Always:**
- Anonymous SSR requests resolve as `302 → /auth/login?return_to=<requested-path>` with empty body. No HTML for unauthenticated users.
- Protected routes are gated by `CanMatch` (not `CanActivate`) so `book-list-page` / `settings-page` chunks never reach an anonymous browser.
- `return_to` must start with `/` and not `//`.

**Ask First:**
- Any need to touch BFF `/auth/*` endpoints, `Role` enum, session schema, or CSRF middleware.

**Never:**
- No in-app "logged out" / "session expired" page.
- No changes to `/auth/login|callback|logout` contracts.
- No structured auth event logging or RP-initiated end_session in this story.
- No widening of `SSR_PROXIED_PREFIXES`.

## I/O & Edge-Case Matrix

| Scenario | Input | Expected |
|---|---|---|
| Anonymous cold visit | `GET /` SSR | `302 Location: /auth/login?return_to=%2F`, empty body |
| Anonymous deep link | `GET /books/42` SSR | `302 Location: /auth/login?return_to=%2Fbooks%2F42` |
| Authenticated SSR | `GET /books` w/ session | `200` + rendered page |
| In-app nav, authed | router `→/settings` | guard reads cached `me`, chunk loads, no `/auth/login` call |
| Mid-session 401 | XHR `/api/v1/*` → 401 | browser `window.location.href = '/auth/login?return_to=<router.url>'`; `/api/me` and `/auth/logout` excluded |
| Logout | click Log out | `POST /auth/logout` (any outcome) → `window.location.href = '/'` → guard 302s to `/auth/login` |

</frozen-after-approval>

## Code Map

- `spa/src/app/login/*` — delete (4 files)
- `spa/src/app/auth/redirect-if-authed-guard.{ts,spec.ts}` — delete
- `spa/src/app/auth/auth-guard.{ts,spec.ts}` — rewrite as `CanMatchFn`, SSR returns `RedirectCommand` + browser-redirect, short-circuit when `me()` already populated, capture full URL (query+fragment) via `Router.getCurrentNavigation()`, try/catch around `loadMe()` for non-401 errors, two-platform spec
- `spa/src/app/app.routes.ts` — drop `/login` + `''→books`; add stub `{ path: 'auth/login', loadComponent: ... }` so SSR `RedirectCommand` navigates successfully; group `books`/`settings` under one `path: ''` with `canMatch: [authGuard]`; keep `**→books`
- `spa/src/app/shared/http/with-credentials-interceptor.{ts,spec.ts}` — `router.navigateByUrl('/login?...')` → `window.location.href = '/auth/login?...'`; exclude both `/api/me` and `/auth/logout` from the 401 redirect
- `spa/src/app/shared/chrome/top-chrome.ts` — replace post-logout `router.navigateByUrl('/login')` with `window.location.href = '/'`
- `spa/src/app/{books/estimate-cell.ts, settings/reading-speed-service.ts, shared/errors/app-error.types.ts}` — comments only: update `/login?return_to=...` → `/auth/login?return_to=...`
- `e2e/fixtures/helpers.ts` + `e2e/tests/{j1-first-login,j5-logout,j4-adjust-speed}.spec.ts` — update flows and URL assertions to traverse `/auth/login` → Keycloak directly (no `/login` step)

## Tasks & Acceptance

**Execution:**
- [x] `auth-guard.ts` + spec — convert to `CanMatchFn`; SSR returns `new RedirectCommand(router.parseUrl(loginUrl))`; browser sets `window.location.href`; short-circuit when `me()` is populated; try/catch around `loadMe()` for non-401 errors; capture query+fragment via `router.getCurrentNavigation()?.extractedUrl`
- [x] `auth-redirect-stub.ts` — minimal standalone `AuthRedirectStub` component (empty template) so the SSR `RedirectCommand` navigation succeeds and Angular's engine emits a 302
- [x] `app.routes.ts` — restructure to `[{ path: 'auth/login', component: AuthRedirectStub }, { path: '', canMatch: [authGuard], children: [books, settings] }, { path: '**', redirectTo: 'books' }]`
- [x] Delete `login/` and `redirect-if-authed-guard*`
- [x] `with-credentials-interceptor.ts` + spec — swap router-nav for `window.location.href`; exclude both `/api/me` and `/auth/logout` from the 401 redirect
- [x] `top-chrome.ts` — `window.location.href = '/'` post-logout; drop unused `Router` if orphaned
- [x] Three comment-only updates
- [x] E2E helpers + j1/j5/j4 specs updated for new flow
- [x] `cd spa && npm run lint && npm test -- --watch=false && npm run build` — all green
- [ ] E2E suite passes (`docker compose --profile e2e up --abort-on-container-exit`)

**Acceptance Criteria:**
- Given anonymous browser, when `GET /books/42`, then HTTP 302 with `Location: /auth/login?return_to=%2Fbooks%2F42` and no `book-list-page` chunk in body.
- Given authed user navigating `/books` → `/settings`, when router runs, then no call to `/auth/login` and settings chunk loads.
- Given expired session, when any `/api/*` or `/v1/*` XHR 401s, then `window.location.href = '/auth/login?return_to=<current>'`; `/api/me` bootstrap is exempt.
- Given Log out click, when BFF POST resolves or fails, then browser navigates to `/` and guard re-evaluates.
- Given post-build SPA, when grep `dist/spa/browser/*.js` for `LoginView|login-view|redirectIfAuthedGuard|'/login'`, then zero matches.

## Spec Change Log

### 2026-05-22 — SSR redirect mechanism + four review patches (iteration 2)

**Trigger:** three-layer adversarial review found that `inject(RESPONSE_INIT)` (specified inside `<frozen-after-approval>`) does NOT produce an SSR 302 in Angular 21 — the engine only honors `responseInit` for *successful* renders. A `CanMatchFn` returning `false` causes the router to fall to `**→books`, loop on `canMatch`, set `hasNavigationError=true`, and the SSR engine returns `null` → Express 404. Confirmed against `@angular/ssr@21.2.x` `ssr.mjs` lines 154–178, 1280–1311.

**Amended:** the frozen `Approach` paragraph was rewritten with explicit user authorization to specify `RedirectCommand` + an `auth/login` stub route as the SSR mechanism. The frozen Ask-First trigger for `RESPONSE_INIT` was removed (resolved). Code Map and I/O matrix were updated accordingly.

**Known-bad state avoided:** anonymous SSR requests returning HTTP 404 instead of `302 → /auth/login` — visible UX flash and broken deep-link auth flow.

**KEEP:** the platform-aware split (SSR vs browser branch), the `CanMatch` choice (not `CanActivate`), the `__Host-session` cookie/CSRF/discovery untouched-ness, the open-redirect guard on `return_to`, and the empty-body 302 outcome from the I/O matrix.

**Other patches folded in same iteration (all non-frozen):**
- `buildReturnTo` now captures the full URL (query + fragment) via `Router.getCurrentNavigation()?.extractedUrl` (was: segments only — dropped query string).
- Guard short-circuits when `authService.me() !== null` (was: re-fired `/api/me` on every navigation).
- Guard wraps `loadMe()` in try/catch and treats any thrown error as "no session" (was: non-401 errors propagated and crashed navigation).
- `with-credentials-interceptor` now excludes both `/api/me` AND `/auth/logout` from the 401 redirect (was: `/auth/logout` 401 would race with `top-chrome`'s `window.location.href = '/'`).

## Verification

**Commands:**
- `cd spa && npm run lint` — clean
- `cd spa && npm test -- --watch=false` — all green
- `cd spa && npm run build && grep -rE "(LoginView|login-view|'/login')" dist/spa/browser/*.js` — empty
- `docker compose --profile e2e up --abort-on-container-exit` — J1/J2/J4/J5 green
- `docker compose up && curl -sI http://localhost:4000/books` — `HTTP/1.1 302` with `Location: /auth/login?return_to=%2Fbooks`

## Suggested Review Order

**SSR 302 mechanism (the load-bearing change)**

- New guard: short-circuit on hot signal, then RedirectCommand on SSR vs `window.location.href` on browser
  [`auth-guard.ts:23`](../../spa/src/app/auth/auth-guard.ts#L23)

- Stub route — present only so the SSR `RedirectCommand` navigation succeeds, never rendered in production
  [`app.routes.ts:11`](../../spa/src/app/app.routes.ts#L11)

- Empty standalone component; sole reason: `lastSuccessfulNavigation().finalUrl` needs to land somewhere
  [`auth-redirect-stub.ts:6`](../../spa/src/app/auth-redirect-stub.ts#L6)

- Why this mechanism: full rationale in the change log entry below the tasks
  [`7-4-only-sso-login.md`](./7-4-only-sso-login.md)

**Login-surface removal**

- New protected-route group under `path: ''` with `canMatch: [authGuard]` — lazy chunks gated, not just rejected
  [`app.routes.ts:13`](../../spa/src/app/app.routes.ts#L13)

- Deleted: `spa/src/app/login/*` (4 files) and `spa/src/app/auth/redirect-if-authed-guard.{ts,spec.ts}`

**Mid-session 401 + logout flow**

- 401 redirect now full-page `window.location.href`; `/auth/logout` joins `/api/me` in the exempt set
  [`with-credentials-interceptor.ts:9`](../../spa/src/app/shared/http/with-credentials-interceptor.ts#L9)

- Post-logout: `window.location.href = '/'` lets the guard re-evaluate end-to-end
  [`top-chrome.ts:55`](../../spa/src/app/shared/chrome/top-chrome.ts#L55)

**Unit tests**

- Two-platform coverage: browser branch checks `window.location.href`, server branch asserts `RedirectCommand`
  [`auth-guard.spec.ts:124`](../../spa/src/app/auth/auth-guard.spec.ts#L124)

- New exclusion test for `/auth/logout` and the short-circuit-on-populated-`me` regression coverage
  [`with-credentials-interceptor.spec.ts:84`](../../spa/src/app/shared/http/with-credentials-interceptor.spec.ts#L84)

- Top-chrome's post-logout target now asserts `assignedHref === '/'`
  [`top-chrome.spec.ts:1`](../../spa/src/app/shared/chrome/top-chrome.spec.ts#L1)

**E2E updates**

- `logInAs` skips the deleted `/login` view, hits `/books` directly, waits for the Keycloak round-trip
  [`helpers.ts:1`](../../e2e/fixtures/helpers.ts#L1)

- J1 / J5 assertions rewritten for the new redirect chain
  [`j1-first-login.spec.ts:1`](../../e2e/tests/j1-first-login.spec.ts#L1)
  [`j5-logout.spec.ts:1`](../../e2e/tests/j5-logout.spec.ts#L1)

**Cosmetic comment updates** (no behavior change)

- Three comment refs migrated from `/login?return_to=...` to `/auth/login?return_to=...`
  [`estimate-cell.ts:116`](../../spa/src/app/books/estimate-cell.ts#L116)
  [`reading-speed-service.ts:22`](../../spa/src/app/settings/reading-speed-service.ts#L22)
  [`app-error.types.ts:10`](../../spa/src/app/shared/errors/app-error.types.ts#L10)
