---
status: review
story_key: 1-10-spa-loginview-topchrome-route-table
created: 2026-05-15
---

# Story 1.10: SPA LoginView + TopChrome + route table

Status: review

## Story

As an unauthenticated visitor,
I want to land on `/login`, click a single "Log in" button, complete a real Keycloak round-trip, and return signed in to `/books` with my identity displayed in the top chrome and a clearly visible "Log out" affordance,
So that J1 and J5 work end-to-end in the running SPA.

## Acceptance Criteria

**AC1 — Route table wired in `app.routes.ts` per AR23 / Architecture F5:**
- `''` (empty path) → `pathMatch: 'full'`, `redirectTo: 'books'`.
- `'login'` → loads `LoginView` (lazy via `loadComponent`), `canActivate: [redirectIfAuthedGuard]`.
- `'books'` → loads `BooksPagePlaceholder` (lazy via `loadComponent`), `canActivate: [authGuard]`.
- `'settings'` → loads `SettingsPagePlaceholder` (lazy via `loadComponent`), `canActivate: [authGuard]`.
- `'**'` → `redirectTo: 'books'`.

**AC2 — `LoginView` source files exist:**
- `spa/src/app/login/login-view.ts`, `login-view.html`, `login-view.css`, `login-view.spec.ts` all exist.
- Component selector follows project convention (`kebab-case`, `app-` prefix).

**AC3 — `LoginView` renders default state:**
- Centered in the 720px content column.
- Headline element with the exact text `"Sign in to Reading Time Estimator"` in `--text-page-title`.
- Single paragraph with the exact text `"You'll be redirected to authenticate, then returned here."` in `--text-body` / `--color-text-muted`.
- Single primary button with the exact text `"Log in"` styled with `--color-accent` background and white text.

**AC4 — `LoginView` "Log in" performs a full-page navigation:**
- Clicking the `"Log in"` button performs a full-page navigation to `/auth/login` (assigning `window.location.href` or equivalent). It does NOT use `HttpClient`, does NOT use Angular's `Router`, and does NOT trigger an XHR — the BFF needs to issue a 302 to Keycloak, which requires browser-level navigation.

**AC5 — `LoginView` `?error=auth` state (UX-DR12):**
- When the URL has `?error=auth`, an `ErrorMessage` is rendered above the button with the literal copy `"Login didn't complete — try again."`.
- When `?error=auth` is absent, the error message is NOT rendered.

**AC6 — `TopChrome` source files exist:**
- `spa/src/app/shared/chrome/top-chrome.ts`, `top-chrome.html`, `top-chrome.css`, `top-chrome.spec.ts` all exist.

**AC7 — `TopChrome` unauthenticated variant:**
- When `AuthService.me()` is `null`, `TopChrome` renders ONLY the product name `"Reading Time Estimator"` on the left, in `--text-page-title`.
- No identity block. No route link.

**AC8 — `TopChrome` authenticated variant on `/books`:**
- When `AuthService.me()` is non-null and the current route is `/books`, `TopChrome` renders:
  - Product name `"Reading Time Estimator"` on the left.
  - In the middle, a `"Settings"` route link pointing to `/settings`.
  - On the right: text `"Signed in as "` in `--color-text-muted`, immediately followed by `<preferred_username>` in `--color-text`, then `" · "`, then a `"Log out"` text button.

**AC9 — `TopChrome` authenticated variant on `/settings`:**
- Same as AC8, except the middle route link reads `"Books"` and points to `/books` (contextual swap per UX-DR2).

**AC10 — `TopChrome` `"Log out"` flow (J5):**
- Clicking `"Log out"` issues `POST /auth/logout` via `HttpClient` (so `withCredentialsInterceptor` and `csrfInterceptor` attach the cookie + CSRF header).
- On a 2xx response, the SPA clears the auth state (`AuthService.clear()`) and navigates to `/login` via the Angular `Router`.
- On a non-2xx response, the SPA still clears the auth state and navigates to `/login` (degrade open — the local session is gone regardless of remote outcome, per J5).
- After logout, when the SPA re-renders `/login`, `TopChrome` shows the unauthenticated variant (product name only).

**AC11 — `BooksPagePlaceholder` and `SettingsPagePlaceholder` exist:**
- `spa/src/app/books/books-page-placeholder.ts` (+ inline-or-external template) exports a standalone component that renders the literal text `"Books — coming in Epic 2"` in default body styling. No styling beyond the body default.
- `spa/src/app/settings/settings-page-placeholder.ts` similarly renders `"Settings — coming in Epic 3"`.

**AC12 — `ErrorMessage` shared component exists:**
- `spa/src/app/shared/ui/error-message.ts` (+ template/style/spec) exists as a stateless standalone component.
- Inputs: `message: string` (required) via Angular `input()` signal.
- Renders a single line in `--text-small` / `--color-error`.
- Reusable across the SPA (used by `LoginView` in this story; future stories will consume it elsewhere).

**AC13 — `App` root renders `TopChrome` + `<router-outlet>`:**
- `spa/src/app/app.html` is updated to render `<app-top-chrome />` followed by a centered 720px content container that contains `<router-outlet />`.
- The Story 1.8 smoke fragment is removed (the routed views are now the rendered content).
- `app.ts` imports `TopChrome` (and `RouterOutlet`, already there).
- The replaced Story 1.8 smoke test is updated to assert that `app-top-chrome` renders and the router outlet is present.

**AC14 — `AuthService` bootstrap on app start:**
- `app.config.ts` registers `provideAppInitializer(() => inject(AuthService).loadMe())` so the initial `me()` value is populated before the first route activation.
- `AuthService.loadMe()` already swallows 401 silently (Story 1.9 contract), so an unauthenticated visitor still proceeds to route activation; the guards then make the redirect decision.

**AC15 — Tests pass for new components:**
- `login-view.spec.ts` asserts: default state renders headline + paragraph + button with exact text; clicking the button triggers full-page navigation to `/auth/login`; `?error=auth` route param renders the `ErrorMessage` with the exact UX-DR12 copy; default state does NOT render the `ErrorMessage`.
- `top-chrome.spec.ts` asserts: unauthenticated variant renders product name only and no identity block / route link; authenticated variant on `/books` renders product name + `"Settings"` link + identity block with `Signed in as <username>` + `Log out` button; authenticated variant on `/settings` renders the `"Books"` link instead; clicking `"Log out"` issues `POST /auth/logout`, calls `AuthService.clear()`, and navigates to `/login`.
- `error-message.spec.ts` asserts: renders the `message` input verbatim; uses `--text-small` / `--color-error` token-derived classes.
- `app.spec.ts` is updated to assert `<app-top-chrome>` renders and the router outlet is present.

**AC16 — Existing gates still green:**
- `npm run lint` exits 0.
- `npm run build` exits 0; `dist/spa/browser/index.html` still produced.
- `npm test -- --no-watch` exits 0; all Story 1.8 + 1.9 + new specs pass.

## Tasks / Subtasks

- [x] **Task 1 — Create `ErrorMessage` shared component** (AC: #12)
  - [x] `spa/src/app/shared/ui/error-message.ts` — standalone component, selector `app-error-message`, input signal `message`.
  - [x] `spa/src/app/shared/ui/error-message.html` — single `<p>` rendering the message.
  - [x] `spa/src/app/shared/ui/error-message.css` — token-derived classes (`--text-small`, `--color-error`).
  - [x] `spa/src/app/shared/ui/error-message.spec.ts` — asserts message renders + classes applied.

- [x] **Task 2 — Create `LoginView` component** (AC: #2, #3, #4, #5)
  - [x] `spa/src/app/login/login-view.ts` — standalone component, selector `app-login-view`, imports `ErrorMessage`. Reads `?error=auth` from `ActivatedRoute.queryParamMap` and exposes a computed signal `showAuthError`. Button click handler sets `window.location.href = '/auth/login'`.
  - [x] `spa/src/app/login/login-view.html` — headline, paragraph, optional `<app-error-message>`, primary button.
  - [x] `spa/src/app/login/login-view.css` — centered content; primary button styled with `--color-accent`.
  - [x] `spa/src/app/login/login-view.spec.ts` — default state, `?error=auth` state, button click navigates.

- [x] **Task 3 — Create `TopChrome` component** (AC: #6, #7, #8, #9, #10)
  - [x] `spa/src/app/shared/chrome/top-chrome.ts` — standalone component, selector `app-top-chrome`. Injects `AuthService`, `HttpClient`, `Router`. Subscribes to `Router.events` (or uses computed signal from current URL) to compute `contextualLink` (`/settings` link when on `/books`, `/books` link when on `/settings`). Exposes `me()` from `AuthService`. `logout()` POSTs to `/auth/logout`, then calls `AuthService.clear()` and `router.navigateByUrl('/login')`.
  - [x] `spa/src/app/shared/chrome/top-chrome.html` — ~48px bar; left product name; conditional middle route link; conditional right identity block + logout button.
  - [x] `spa/src/app/shared/chrome/top-chrome.css` — flex layout, padding mirrors content column.
  - [x] `spa/src/app/shared/chrome/top-chrome.spec.ts` — three render variants + logout click handler.

- [x] **Task 4 — Create placeholder pages** (AC: #11)
  - [x] `spa/src/app/books/books-page-placeholder.ts` — minimal standalone component, inline template, renders `"Books — coming in Epic 2"`.
  - [x] `spa/src/app/settings/settings-page-placeholder.ts` — same pattern, renders `"Settings — coming in Epic 3"`.

- [x] **Task 5 — Wire route table** (AC: #1)
  - [x] Update `spa/src/app/app.routes.ts` with five routes per AC1, lazy-loading all three view components, importing the two guards from `./auth/auth-guard` and `./auth/redirect-if-authed-guard`.

- [x] **Task 6 — Update `app.html`, `app.ts`, `app.config.ts`** (AC: #13, #14)
  - [x] Replace the Story 1.8 smoke fragment in `app.html` with `<app-top-chrome />` followed by a centered 720px content container wrapping `<router-outlet />`.
  - [x] Import `TopChrome` in `app.ts`.
  - [x] Add `provideAppInitializer(() => inject(AuthService).loadMe())` to `app.config.ts` providers.

- [x] **Task 7 — Update `app.spec.ts`** (AC: #13, #15)
  - [x] Replace the smoke-fragment assertion with `<app-top-chrome>` + router outlet assertions. Mock `AuthService` so `loadMe` resolves and `me()` returns `null` initially. Use `provideRouter([])` + `provideHttpClient()` + `provideHttpClientTesting()` in TestBed.

- [x] **Task 8 — Verify gates** (AC: #16)
  - [x] `cd spa && npm run lint` — exits 0.
  - [x] `npm test -- --no-watch` — exits 0 (Story 1.8's 2 specs replaced; Story 1.9's 5 specs intact; new specs for login-view, top-chrome, error-message all pass).
  - [x] `npm run build` — exits 0; `dist/spa/browser/index.html` produced.

## Dev Notes

### What this story is — and is not

This story produces the **routed shell** of the SPA: the route table, the two auth-state UIs (`LoginView`, `TopChrome`), a small shared `ErrorMessage` component, and two placeholder pages for `/books` and `/settings`. The placeholders are intentional — Epic 2 (`/books`) and Epic 3 (`/settings`) replace them with real pages later. This story does NOT implement books CRUD, reading-speed settings, estimates, or any feature beyond the auth chrome.

After this story, J1 (first-time login) and J5 (logout) work end-to-end in the running SPA against a running BFF + Keycloak compose stack. The BFF endpoints already exist (Stories 1.5 / 1.7). The SPA-side plumbing (Story 1.9) is already in place. This story stitches it all together in the UI.

### Decisions baked in by create-story (do not relitigate)

1. **`TopChrome` is rendered once at the `App` root** (in `app.html`), not per-route. The unauthenticated variant degrades to product-name-only when `me()` is null, so it stays visible on `/login` too. This avoids duplicating `<app-top-chrome />` in every routed component.
2. **`AuthService.loadMe()` is invoked via `provideAppInitializer`** at app startup so the initial signal value is populated before route activation. The guards also call `/api/me` themselves (Story 1.9 contract) — the initializer is a quality-of-life improvement for the immediate-after-bootstrap render, not the source of truth.
3. **The contextual route link inside `TopChrome` is computed reactively from the current URL.** Use Angular's `Router.events` (`NavigationEnd` filter) or read `Router.url` on render — both are acceptable; choose the form that yields cleanest test code.
4. **Placeholder pages are minimal standalone components.** No service wiring, no styling beyond the body default. Their job is to render a single line of text and satisfy the route table.
5. **`LoginView` does a full-page navigation, not an Angular route navigation.** The "Log in" click sets `window.location.href = '/auth/login'`. Angular's `Router` only navigates within the SPA, but `/auth/login` is a BFF endpoint that issues a 302 to Keycloak — that flow requires a browser-level navigation so the cookies and redirects work.
6. **`TopChrome.logout()` degrades open.** Whatever the BFF returns, the SPA clears local state and navigates to `/login`. The user does not get stuck in a broken state if `/auth/logout` 5xx's.

### Source-of-truth references

- **Epic 1 Story 1.10 ACs:** [`_bmad-output/planning-artifacts/epics.md` §"Story 1.10: SPA LoginView + TopChrome + route table"].
- **Architecture F5 — route table:** [`_bmad-output/planning-artifacts/architecture.md` lines 443–456]. This story replaces the lazy `BookListPage` / `SettingsPage` references in F5 with `BooksPagePlaceholder` / `SettingsPagePlaceholder` for Epic 1 only; later stories swap them back to the real pages.
- **Architecture F1 — `AuthService` as signal source of truth:** [`architecture.md` lines 424–429].
- **UX-DR1 design tokens:** [`epics.md` line 103].
- **UX-DR2 TopChrome:** [`epics.md` line 104].
- **UX-DR3 LoginView:** [`epics.md` line 105].
- **UX-DR10 ErrorMessage:** [`epics.md` line 112].
- **UX-DR12 failure copy strings:** [`epics.md` line 114] — `"Login didn't complete — try again."` is the exact string.
- **UX-DR14 button hierarchy:** [`epics.md` line 121] — single primary action per surface, styled with `--color-accent`.
- **UX-DR16 layout structure:** [`epics.md` line 123] — 720px column, mirrored top-chrome padding.
- **J1 sequence diagram:** [`ux-design-specification.md` lines 377–414].
- **J5 sequence diagram:** [`ux-design-specification.md` lines 509–538].
- **Project component directory pattern:** [`architecture.md` lines 620–633] — `login/`, `shared/chrome/`, `shared/ui/`, `books/`, `settings/`.

### Files this story creates

```
spa/src/app/login/
├── login-view.ts
├── login-view.html
├── login-view.css
└── login-view.spec.ts

spa/src/app/shared/chrome/
├── top-chrome.ts
├── top-chrome.html
├── top-chrome.css
└── top-chrome.spec.ts

spa/src/app/shared/ui/
├── error-message.ts
├── error-message.html
├── error-message.css
└── error-message.spec.ts

spa/src/app/books/
└── books-page-placeholder.ts        # inline template + styleless

spa/src/app/settings/
└── settings-page-placeholder.ts     # inline template + styleless
```

### Files this story modifies

```
spa/src/app/app.routes.ts             # populate route table
spa/src/app/app.config.ts             # add provideAppInitializer for AuthService.loadMe()
spa/src/app/app.html                  # replace smoke fragment with <app-top-chrome /> + content column wrapping <router-outlet />
spa/src/app/app.ts                    # import TopChrome
spa/src/app/app.spec.ts               # update assertions to match new app.html
```

### Files this story explicitly does NOT touch

- `spa/src/app/auth/**` — Story 1.9 owns these; they activate when the route table wires the guards (this story).
- `spa/src/app/shared/http/**` — Story 1.9 owns these.
- `spa/src/styles.css` — UX-DR1 tokens, untouched.
- `spa/proxy.conf.json` — untouched.
- `spa/eslint.config.js`, `spa/angular.json`, `spa/tsconfig*.json` — untouched.

### Critical implementation details

#### Full-page navigation from `LoginView`

```ts
// login-view.ts
onLogin(): void {
  window.location.href = '/auth/login';
}
```

Do NOT use `Router.navigateByUrl('/auth/login')` — Angular's Router would treat `/auth/login` as an internal route, not produce the browser-level navigation the BFF needs to issue a 302. In tests, this is asserted by spying on the `window.location` href setter or by extracting the handler into a method that takes the redirect target as a parameter.

#### Reading `?error=auth` reactively in `LoginView`

```ts
private readonly route = inject(ActivatedRoute);
readonly showAuthError = toSignal(
  this.route.queryParamMap.pipe(map(p => p.get('error') === 'auth')),
  { initialValue: false },
);
```

Alternative: read it synchronously in the constructor / `ngOnInit` from `route.snapshot.queryParamMap`. Either is acceptable; the signal form is consistent with the architecture's preferred state pattern.

#### Contextual route link in `TopChrome`

```ts
// top-chrome.ts
private readonly router = inject(Router);
readonly currentUrl = toSignal(
  this.router.events.pipe(
    filter((e): e is NavigationEnd => e instanceof NavigationEnd),
    map(e => e.urlAfterRedirects),
    startWith(this.router.url),
  ),
  { initialValue: this.router.url },
);
readonly contextualLink = computed(() => {
  const url = this.currentUrl();
  if (url.startsWith('/books')) return { label: 'Settings', path: '/settings' };
  if (url.startsWith('/settings')) return { label: 'Books', path: '/books' };
  return null; // no link on /login or other paths
});
```

#### Logout handler

```ts
async logout(): Promise<void> {
  try {
    await firstValueFrom(this.http.post('/auth/logout', null));
  } catch {
    // degrade open per J5 — local session is gone regardless
  }
  this.authService.clear();
  await this.router.navigateByUrl('/login');
}
```

Note: the `csrfInterceptor` (Story 1.9) attaches the `X-CSRF-Token` header automatically based on the `csrf_token` cookie. No explicit header in this code.

#### TopChrome in `app.html`

```html
<app-top-chrome />
<main class="mx-auto max-w-[720px] px-4 py-8">
  <router-outlet />
</main>
```

#### `provideAppInitializer` in `app.config.ts`

```ts
import { provideAppInitializer, inject } from '@angular/core';
import { AuthService } from './auth/auth-service';

providers: [
  // ...existing providers
  provideAppInitializer(() => inject(AuthService).loadMe()),
],
```

`loadMe()` already returns a `Promise<void>` and swallows 401 (Story 1.9 contract), so this never rejects on the unauthenticated path.

### Test patterns to follow

- **TestBed + provideHttpClientTesting()** for any spec that needs to mock HTTP (the logout test and the app initializer's loadMe call).
- **Standalone components are imported directly** in `TestBed.configureTestingModule({ imports: [Component] })`.
- **Signal assertions:** `expect(component.showAuthError()).toBe(true)`.
- **DOM assertions:** `fixture.nativeElement.querySelector(...)` after `fixture.detectChanges() + await fixture.whenStable()` (zoneless change detection requires the explicit cycle).
- **Router events in tests:** provide a stub `Router` with a `url` getter and an `events` Observable, OR use `provideRouter([])` and call `router.navigateByUrl` to drive the URL.
- **`window.location` in tests:** because `jsdom` allows `window.location.href` reads but not assignments by default, prefer extracting the redirect into a method `redirectToAuthLogin()` that wraps the assignment, then spy on the method in tests rather than trying to assert on `window.location` directly. Alternatively, inject a small `WindowRef`/`Location` token. The simplest, most testable approach: factor the `window.location.href = ...` assignment into a private method or a small helper, and spy on that.

### Edge cases / decisions

- **What if `me()` is null but the URL is `/books`?** The `authGuard` (Story 1.9) redirects to `/login?return_to=/books` before the route activates. `TopChrome` never sees a `null me()` on `/books` in practice. But the component must still handle the `null` case gracefully (render the unauthenticated variant) so it does not crash on the brief gap between route navigation and signal update.
- **What if logout fails (network error)?** Degrade open: clear local state, navigate to `/login`. The user will see the unauthenticated chrome; if their session is still valid server-side, the next `/api/me` call will recover them — but this is rare and acceptable for an educational project.
- **What if `?error=auth` is present on `/login` AND the user is already authenticated?** `redirectIfAuthedGuard` (Story 1.9) bounces them to `/books` before `LoginView` renders, so the error message never paints. Confirmed by the guard's contract.

### Coding standards

- Standalone components only (no `NgModule`).
- File names: `kebab-case.ts` (no `.component.` suffix).
- Component selectors: `kebab-case` with `app-` prefix.
- Imports: TypeScript `import` order — Angular framework, then RxJS, then local relative.
- No `console.log` (`no-console` rule). `console.warn` / `console.error` allowed in non-spec files; specs are exempt.
- No empty catch blocks (`no-empty` rule with `allowEmptyCatch: false`) — the logout handler's catch must have a comment or a no-op statement explaining the intentional swallow.

## Dev Agent Record

### Implementation Plan

1. Scaffold `ErrorMessage` shared component (`shared/ui/`) first — it's a leaf dependency for `LoginView`.
2. Build `LoginView` (`login/`) with `ActivatedRoute` query-param reading and a redirect indirection seam for testing.
3. Build `TopChrome` (`shared/chrome/`) with `AuthService` + `Router` reactivity, and a degrade-open logout handler.
4. Add two minimal placeholder pages (`books/`, `settings/`).
5. Populate `app.routes.ts` with the five-route table per AC1 / Architecture F5.
6. Update `app.html`, `app.ts`, `app.css` to render `TopChrome` + the 720px content column wrapping the router outlet.
7. Update `app.config.ts` with `provideAppInitializer(() => inject(AuthService).loadMe())`.
8. Rewrite `app.spec.ts` so its assertions match the new `app.html`.
9. Run `npm run lint`, `npm test -- --no-watch`, `npm run build` and capture transcripts.

### Debug Log References

- **Baseline (pre-story) tests:** 20 passed (6 files) — Story 1.8 (2) + Story 1.9 (5 specs).
- **Post-implementation tests:** 31 passed (9 files) — added `error-message.spec.ts` (2), `login-view.spec.ts` (4), `top-chrome.spec.ts` (5); rewrote `app.spec.ts` (2 retained). Net +11 new test cases.
- **Lint:** `All files pass linting.`
- **Build:** `dist/spa/browser/index.html` produced; three lazy chunks (`login-view`, `books-page-placeholder`, `settings-page-placeholder`) confirm route-level code-splitting works.

### Completion Notes

- The smoke-fragment test from Story 1.8 (AC7 utility-class assertion on `bg-surface-muted` / `text-accent` / `p-3`) was removed when its DOM target was deleted. The replacement asserts the new structural contract (`<app-top-chrome>` + `<main.app-content>` + `<router-outlet>`). This is consistent with the story's AC13 + AC15 which explicitly call for `app.spec.ts` to be updated.
- The `LoginView` button-click test asserts indirectly via a spy on `redirectToAuthLogin()` (the indirection seam documented in Dev Notes) rather than asserting on `window.location.href`. Direct assertion is impossible under jsdom without polluting the test environment; the indirection seam is cleaner and the assertion that the seam is invoked is equivalent in coverage.
- `TopChrome` reads the current URL via `Router.events` filtered to `NavigationEnd`, with `startWith(this.router.url)` so the initial render reflects the current location without waiting for the first navigation event. The `contextualLink` computed signal returns `null` on `/login` and on any unrecognized path — the unauthenticated variant suppresses the link via the `me()` guard in the template, so the `null` path is only hit during the brief gap between mount and the first `NavigationEnd`.
- The logout handler is **degrade-open** per J5: a 5xx or network error still clears local state and navigates to `/login`. This matches the architecture's directive that local-session teardown must succeed even if the BFF revocation fails. A dedicated test (`logout still clears state + navigates even when /auth/logout fails`) locks this behavior in.
- `provideAppInitializer` is the new Angular v21 idiomatic form (replacing the deprecated `APP_INITIALIZER` token). The inject-style closure mirrors how functional interceptors and guards already work in this codebase.

### Validation

- **`npm run lint`** — exit 0. No new ESLint violations.
- **`npm test -- --no-watch`** — exit 0. 9 test files, 31 tests, 0 failures.
- **`npm run build`** — exit 0. `dist/spa/browser/index.html` produced. Lazy chunks confirmed for the three lazy-loaded route components.

## File List

**Created:**
- `spa/src/app/shared/ui/error-message.ts`
- `spa/src/app/shared/ui/error-message.html`
- `spa/src/app/shared/ui/error-message.css`
- `spa/src/app/shared/ui/error-message.spec.ts`
- `spa/src/app/login/login-view.ts`
- `spa/src/app/login/login-view.html`
- `spa/src/app/login/login-view.css`
- `spa/src/app/login/login-view.spec.ts`
- `spa/src/app/shared/chrome/top-chrome.ts`
- `spa/src/app/shared/chrome/top-chrome.html`
- `spa/src/app/shared/chrome/top-chrome.css`
- `spa/src/app/shared/chrome/top-chrome.spec.ts`
- `spa/src/app/books/books-page-placeholder.ts`
- `spa/src/app/settings/settings-page-placeholder.ts`

**Modified:**
- `spa/src/app/app.routes.ts` — populated the five-route table.
- `spa/src/app/app.config.ts` — added `provideAppInitializer(() => inject(AuthService).loadMe())`.
- `spa/src/app/app.html` — replaced Story 1.8 smoke fragment with `<app-top-chrome />` + `<main class="app-content">` wrapping `<router-outlet />`.
- `spa/src/app/app.ts` — imported `TopChrome`.
- `spa/src/app/app.css` — added `.app-content` 720px column styling.
- `spa/src/app/app.spec.ts` — rewrote assertions to match the new `app.html` (smoke-fragment test removed per AC13).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `1-10-...: backlog → in-progress → review`.

## Change Log

| Date       | Change                                                            |
|------------|-------------------------------------------------------------------|
| 2026-05-15 | Story drafted from epic AC + dev context.                          |
| 2026-05-15 | Implementation complete; all gates green; status → review.         |
