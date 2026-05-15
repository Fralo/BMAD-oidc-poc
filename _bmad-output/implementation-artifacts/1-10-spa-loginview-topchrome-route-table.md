---
status: ready-for-dev
story_key: 1-10-spa-loginview-topchrome-route-table
created: 2026-05-15
---

# Story 1.10: SPA LoginView + TopChrome + route table

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an unauthenticated visitor,
I want to land on `/login`, click a single "Log in" button, complete a real Keycloak round-trip, and return signed in to `/books` with my identity displayed in the top chrome and a clearly visible "Log out" affordance,
so that J1 and J5 work end-to-end in the running SPA.

## Acceptance Criteria

**AC1 — Route table in `app.routes.ts` (per AR23 / architecture F5):**
- `spa/src/app/app.routes.ts` exports `routes: Routes` containing exactly five entries, in this order:
  1. `{ path: '', pathMatch: 'full', redirectTo: 'books' }`
  2. `{ path: 'login', loadComponent: () => import('./login/login-view').then(m => m.LoginView), canActivate: [redirectIfAuthedGuard] }`
  3. `{ path: 'books', loadComponent: () => import('./books/book-list-page-placeholder').then(m => m.BookListPagePlaceholder), canActivate: [authGuard] }`
  4. `{ path: 'settings', loadComponent: () => import('./settings/settings-page-placeholder').then(m => m.SettingsPagePlaceholder), canActivate: [authGuard] }`
  5. `{ path: '**', redirectTo: 'books' }`
- The two guards (`authGuard`, `redirectIfAuthedGuard`) come from `./auth/auth-guard` and `./auth/redirect-if-authed-guard` respectively — both already exist from Story 1.9. Do NOT re-implement them.
- `loadComponent` is used (lazy loading) — not `component:` direct references.

**AC2 — `LoginView` component (`spa/src/app/login/login-view.{ts,html,css,spec.ts}`):**
- Standalone component, selector `app-login-view`.
- Renders centered in the 720px content column with vertical padding from `--spacing-8`.
- Template structure (in document order, all literal copy exact):
  - `<h1>` with text `"Sign in to Reading Time Estimator"`, styled via the `text-page-title` Tailwind utility (materialized from `--text-page-title` token).
  - `<p>` with text `"You'll be redirected to authenticate, then returned here."`, styled via `text-body` utility + `text-text-muted` color utility (materialized from `--color-text-muted` token).
  - (Conditional, only when `?error=auth` query param is present) an inline `<p>` (or `<div>`) with class identifying it as the error message and the literal text `"Login didn't complete — try again."` styled `text-small` + `text-error` (materialized from `--color-error` token), rendered ABOVE the button per UX-DR12.
  - Primary `<button>` element with text `"Log in"`, styled in `--color-accent` (Tailwind: `bg-accent text-surface` or equivalent — must visually present as the primary action), `type="button"` (NOT `type="submit"` — there is no form).
- Clicking `"Log in"` triggers a **full-page navigation** to `/auth/login` via `window.location.href = '/auth/login'` (or `window.location.assign('/auth/login')`). It MUST NOT use `HttpClient`, MUST NOT use `Router.navigate(...)`, and MUST NOT issue an `XHR/fetch` — the BFF must receive a top-level browser navigation so it can respond with a `302` to Keycloak and the browser follows that redirect cross-origin. (Calling `/auth/login` via `HttpClient` would receive the redirect as a `302` body inside the SPA, breaking J1.)
- The component reads `?error=auth` from the activated route's `queryParamMap` — use `inject(ActivatedRoute)` + `route.snapshot.queryParamMap.get('error') === 'auth'` (snapshot is sufficient; this view is not re-entered without a full reload). Expose the boolean as a `readonly hasAuthError: boolean` (or via a `computed`/`signal` if you prefer signal semantics — both pass the AC).
- The component does NOT inject `AuthService`, does NOT call `loadMe()`, does NOT touch routing programmatically beyond reading the query param.

**AC3 — `TopChrome` component (`spa/src/app/shared/chrome/top-chrome.{ts,html,css,spec.ts}`):**
- Standalone component, selector `app-top-chrome`.
- Has two variants determined at render time by reading `AuthService.me()`:
  - **Unauthenticated variant** (`me() === null`): renders ONLY the product name `"Reading Time Estimator"` on the left in `text-page-title` styling. No identity block, no route link, no logout button.
  - **Authenticated variant** (`me() !== null`): renders three regions on a single horizontal bar (~48px tall, see UX §"Spacing & Layout Foundation"):
    - **Left:** product name `"Reading Time Estimator"` in `text-page-title`.
    - **Middle:** a single contextual route `<a>` link that reads `"Settings"` and points to `/settings` when the current URL path is `/books`, and reads `"Books"` and points to `/books` when the current URL path is `/settings`. (Use `Router.url` or `inject(Router).events` + a computed/signal — see Dev Notes for the recommended pattern.)
    - **Right:** identity block, exactly: a `<span>` `"Signed in as "` in `text-text-muted`, then a `<span>` with `me()?.preferred_username` in `text-text`, then a literal `<span>` `" · "` separator, then a `<button>` (NOT `<a>`) with text `"Log out"`, type `"button"`, plain text styling (no primary-accent background — `Log out` is a secondary action; visually styled as a text button per UX §"Component Strategy / TopChrome").
- Reads `preferred_username` (not `sub`) from `AuthService.me()`. The UX spec mentions both `<sub or preferred_username>` historically, but `Me.preferred_username` is the authoritative field per `auth.types.ts` and the architecture's `GET /api/me` contract.

**AC4 — Logout interaction (per J5 + UX-DR2):**
- Clicking `"Log out"` in `TopChrome` calls `POST /auth/logout` via the SPA's `HttpClient` (so `withCredentialsInterceptor` sends the session cookie and `csrfInterceptor` attaches `X-CSRF-Token` — both from Story 1.9).
- On any 2xx response (the BFF returns `204` per architecture line 680; the SPA does not care about the body):
  - Clears the SPA's in-memory user state by calling `AuthService.clear()`.
  - Navigates to `/login` via `inject(Router).navigateByUrl('/login')`. Do NOT include `return_to` on this navigation (the user explicitly logged out — there is no destination to return to).
- On non-2xx response: the global 401 handler in `withCredentialsInterceptor` (Story 1.9) already covers a 401 case by navigating to `/login?return_to=…`. For other failures (e.g., 5xx), this story does NOT add local error UI to `TopChrome` — the user can click `"Log out"` again. (The `Log out` button MAY be briefly disabled while the POST is in flight; that is implementation polish, not an AC requirement.)
- The `"Log out"` button is interactive: it has a click handler that calls a `TopChrome` method (e.g., `onLogoutClick()`); the method MUST NOT swallow the HTTP error — let the error propagate or use `try/finally` only for re-enabling the button. (The interceptor handles the 401 case; everything else surfaces as an unhandled promise rejection, which is acceptable for this story per "no local error UI on logout failure".)

**AC5 — Placeholder pages (`books/book-list-page-placeholder.{ts,html,spec.ts}` and `settings/settings-page-placeholder.{ts,html,spec.ts}`):**
- Both are standalone components. Selectors `app-book-list-page-placeholder` and `app-settings-page-placeholder` respectively.
- `BookListPagePlaceholder` template: renders `<app-top-chrome />` followed by the literal text `"Books — coming in Epic 2"` inside a `<p>` (no heading, no styling beyond default body text — this is intentional placeholder content, NOT a loading state). The text appears INSIDE the 720px centered content column (use the same column wrapping as `LoginView` — see Dev Notes for the shared layout pattern).
- `SettingsPagePlaceholder` template: same structure but the placeholder text is `"Settings — coming in Epic 3"` (verbatim — the epic spec only writes `"Books — coming in Epic 2"`; the analogous Settings copy must use Epic 3, which is where reading-speed settings land per `epics.md`).
- Each component has a matching `*.spec.ts` that renders the component and asserts both the literal placeholder text and the presence of an `<app-top-chrome>` element in the rendered DOM.
- These placeholders exist to make the route table activatable end-to-end (so the guards apply, `TopChrome` renders the authenticated variant, and Stories 1.13 / 2.5 / 3.5 can replace each placeholder with a real page in turn).

**AC6 — `App` root component wiring:**
- `spa/src/app/app.html` is replaced. New contents: `<router-outlet />` and NOTHING else above it. (Each route's own component is responsible for rendering `<app-top-chrome />` at the top of its template — see AC5 — because `LoginView`'s unauthenticated variant of `TopChrome` looks different from the authenticated variant on `/books` and `/settings`. Centralizing `TopChrome` in `app.html` would force every route to render the chrome, including `/login`, which is correct per UX-DR2 — the unauthenticated variant renders the product name only. **Implementer's call**: either render `<app-top-chrome />` in `app.html` ONCE for all routes (simpler), or in each route component. The AC requires that on every route the appropriate `TopChrome` variant renders. Pick the centralized approach unless test setup forces otherwise; see Dev Notes "Where does TopChrome live".)
- `spa/src/app/app.ts` imports and declares `TopChrome` if the centralized approach is used; otherwise `RouterOutlet` is the only import (besides what's already there).
- Story 1.8's `app.spec.ts` tests (`should create the app`, `should render the AC7 smoke fragment with token-derived utility classes`) WILL be modified or replaced in this story — the AC7 smoke fragment is deleted (it was explicitly throwaway per Story 1.8's notes and Story 1.9's forward-context). The replacement test asserts that `App` renders `<app-top-chrome />` and `<router-outlet />`. The "should create the app" test is preserved (or rewritten with the new template — the assertion `expect(app).toBeTruthy()` still works).

**AC7 — Bootstrap calls `AuthService.loadMe()` at app start:**
- Before any route activation can read `AuthService.me()` (which `TopChrome` does), the SPA must populate `me` from `/api/me`. Implement via an `APP_INITIALIZER`-style `provideAppInitializer` provider in `app.config.ts`:
  - Use Angular 21's `provideAppInitializer(() => inject(AuthService).loadMe())` (the v21 functional API; replaces the deprecated `APP_INITIALIZER` token).
  - `loadMe()` resolves on both 200 and 401 (Story 1.9 contract — 401 sets `me` to `null` and does not throw), so the initializer always resolves and bootstrap proceeds.
- This wiring ensures: (a) a returning authenticated user lands on `/books` and `TopChrome`'s authenticated variant renders without flicker; (b) `redirectIfAuthedGuard` on `/login` does not race the initializer (the initializer completes before any guard runs).
- Verify by reading the Story 1.9 implementation: `AuthService.loadMe()` does NOT throw on 401 and resolves to `void`. If the dev finds `loadMe()` rethrows in some edge case, wrap the initializer in `.catch(() => undefined)` — but expected behavior is no catch needed.

**AC8 — Test suite passes (4 new spec files, plus updated `app.spec.ts`):**
- New specs: `login-view.spec.ts`, `top-chrome.spec.ts`, `book-list-page-placeholder.spec.ts`, `settings-page-placeholder.spec.ts`.
- `login-view.spec.ts` asserts:
  - Default state (no `?error=auth`): renders the headline text `"Sign in to Reading Time Estimator"`, the paragraph text `"You'll be redirected to authenticate, then returned here."`, the `"Log in"` button, and does NOT render the error message.
  - With `?error=auth` (provide via `ActivatedRoute` mock — `{ snapshot: { queryParamMap: convertToParamMap({ error: 'auth' }) } }` or equivalent): renders the error message text `"Login didn't complete — try again."` ABOVE the button (assert DOM order — e.g., the error element's `compareDocumentPosition` is `Node.DOCUMENT_POSITION_PRECEDING` relative to the button).
  - Clicking the `"Log in"` button calls the `onLoginClick` method (which the component implements to call `window.location.assign('/auth/login')`); the test asserts the method was invoked OR spies on `window.location.assign` (the second approach is more brittle — see Dev Notes for the recommended pattern using a thin abstraction).
- `top-chrome.spec.ts` asserts:
  - **Unauthenticated variant** (`AuthService` mock with `me: signal(null)`): renders the product name `"Reading Time Estimator"` and renders NEITHER the identity block NOR the contextual route link NOR the `"Log out"` button.
  - **Authenticated variant on `/books`** (`AuthService.me` mock returning `{ sub: 's1', preferred_username: 'alice' }`, `Router.url` mock returning `'/books'`): renders product name, renders a `<a>` link with text `"Settings"` and `routerLink="/settings"` (or whose `href`/`routerLink` attribute is `/settings`), renders `"Signed in as "` + `"alice"` + `" · "` + a button labeled `"Log out"`.
  - **Authenticated variant on `/settings`** (same `me` mock, `Router.url` returns `'/settings'`): the contextual route link reads `"Books"` and points to `/books`.
  - **Click on `"Log out"`:** triggers `HttpClient.post('/auth/logout', null)` (use `HttpTestingController`; flush with status 204), then `AuthService.clear()` is called (assert via spy on the mock), then `Router.navigateByUrl('/login')` is called (assert via spy on the mock).
- `book-list-page-placeholder.spec.ts` asserts: the literal placeholder text `"Books — coming in Epic 2"` appears in the rendered template, AND an `<app-top-chrome>` element is present (use `nativeElement.querySelector('app-top-chrome')`).
- `settings-page-placeholder.spec.ts` asserts: the literal placeholder text `"Settings — coming in Epic 3"` appears, AND `<app-top-chrome>` is present.
- Updated `app.spec.ts` asserts: `App` renders `<router-outlet>` (and `<app-top-chrome>` IF the centralized approach is taken). The AC7 smoke fragment assertions are deleted.
- `npm test -- --no-watch` exits 0 with all of Story 1.9's 17 tests plus the new specs (~10–15 new tests) passing — a total of roughly 27–32 tests across 10 spec files (Story 1.9's 5 + Story 1.8's 1 modified + 4 new). The exact count depends on how many `it(...)` blocks the dev writes per spec; the AC is "all specs pass, no skips, no fails".

**AC9 — Coverage ≥70% over `login/`, `shared/chrome/`, `books/` (placeholder only), `settings/` (placeholder only):**
- `npm run test:coverage` (already wired by Story 1.9) reports line coverage ≥70% for `spa/src/app/login/**`, `spa/src/app/shared/chrome/**`, `spa/src/app/books/**`, and `spa/src/app/settings/**` taken as a union of source files (excluding `*.spec.ts`).
- The placeholder pages are trivial (one `<p>` + one `<app-top-chrome>`); their spec files cover them at 100%.
- The 70% floor applies to `login-view.ts` and `top-chrome.ts` — both are simple components with at most a click handler and a query-param read; the test suite above naturally hits ≥90%.
- Record per-folder line-coverage numbers in the Dev Agent Record's Debug Log References.

**AC10 — Existing gates still green:**
- `npm run lint` exits 0 with zero new ESLint violations (no `console.log` outside specs; no empty `catch` blocks; component selectors use `app-*` kebab-case per the existing eslint config).
- `npm run build` exits 0 with `dist/spa/browser/index.html` still produced; lazy-loaded chunks for the four route components appear in the build output (each `loadComponent` import becomes its own chunk — Angular's CLI does this automatically).
- `npm test -- --no-watch` exits 0 with all tests (Story 1.9's surviving 17 + Story 1.8's surviving 1 + the 4 new specs + the updated `app.spec.ts`) passing.
- `proxy.conf.json`, `eslint.config.js`, `styles.css` (UX-DR1 tokens), and `tsconfig*.json` are NOT modified. (D10 is acknowledged in Dev Notes; if Stage-13 integration testing later requires a proxy glob fix, that story can do it.)
- No new top-level dependencies in `package.json` (no new runtime deps; no new dev deps).

## Tasks / Subtasks

- [ ] **Task 1 — Create `LoginView` component files** (AC: #2)
  - [ ] Create `spa/src/app/login/login-view.ts`:
    - `@Component({ selector: 'app-login-view', standalone: true, templateUrl: './login-view.html', styleUrl: './login-view.css' })`.
    - Inject `ActivatedRoute` via `inject(ActivatedRoute)` (functional DI per AR21).
    - Compute `readonly hasAuthError: boolean = this.route.snapshot.queryParamMap.get('error') === 'auth'`. (Snapshot is correct here — `LoginView` is never reused across navigations to itself; the redirect after `?error=auth` is a fresh navigation.)
    - Method `onLoginClick(): void { window.location.assign('/auth/login'); }` — see Dev Notes "Why `window.location.assign` and not `Router.navigate`".
    - Do NOT inject `Router`, `AuthService`, or `HttpClient` — `LoginView` has no need for them.
  - [ ] Create `spa/src/app/login/login-view.html`:
    - Outermost wrapper: a `<main>` (or `<div>`) with Tailwind utilities for the 720px centered column: `mx-auto max-w-[720px] p-8` (or `px-4 py-8 max-w-[720px] mx-auto` — match the centered column convention from UX §"Spacing & Layout Foundation").
    - `<h1 class="text-page-title">Sign in to Reading Time Estimator</h1>`.
    - `<p class="text-body text-text-muted mt-3">You'll be redirected to authenticate, then returned here.</p>` (margin `mt-3` materializes `--spacing-3 = 12px`; adjust to taste within UX spacing tokens, but use ONLY the declared tokens).
    - `@if (hasAuthError) { <p class="text-small text-error mt-4">Login didn't complete — try again.</p> }` using Angular's `@if` block syntax (Angular 21's native control flow, not the legacy `*ngIf` structural directive — see Dev Notes "Control flow syntax in templates").
    - `<button type="button" class="bg-accent text-surface text-body px-4 py-2 mt-6" (click)="onLoginClick()">Log in</button>`. (Exact Tailwind utility classes are flexible as long as they materialize from declared tokens — see Dev Notes for the token-utility mapping.)
  - [ ] Create `spa/src/app/login/login-view.css` — empty (or `:host { display: block; }` only). UX §"Component Strategy" pushes back on per-component CSS in favor of Tailwind utilities; only add CSS here if a Tailwind utility cannot express what you need.
  - [ ] Verify selector matches the eslint rule (`@angular-eslint/component-selector` requires `app-` kebab-case prefix).

- [ ] **Task 2 — Create `LoginView` spec** (AC: #8)
  - [ ] Create `spa/src/app/login/login-view.spec.ts`:
    - Use `TestBed.configureTestingModule({ imports: [LoginView], providers: [{ provide: ActivatedRoute, useValue: <mockRoute> }] })`.
    - For default case, mock `ActivatedRoute` as `{ snapshot: { queryParamMap: convertToParamMap({}) } }` (import `convertToParamMap` from `@angular/router`).
    - For `?error=auth` case, mock with `convertToParamMap({ error: 'auth' })`.
    - Test 1: default state — assert headline text, paragraph text, button text all present; assert error message NOT in `nativeElement.textContent`.
    - Test 2: `?error=auth` state — assert error message text present; assert error element appears BEFORE button in document order (`element.compareDocumentPosition(buttonElement) & Node.DOCUMENT_POSITION_FOLLOWING` is truthy).
    - Test 3: click `"Log in"` button — assert the component's `onLoginClick` method was called (use `vi.spyOn(component, 'onLoginClick')` after `createComponent` and `fixture.detectChanges()`; then `buttonEl.click()`; then `expect(spy).toHaveBeenCalledOnce()`). Do NOT spy on `window.location.assign` directly — see Dev Notes for why.

- [ ] **Task 3 — Create `TopChrome` component files** (AC: #3)
  - [ ] Create `spa/src/app/shared/chrome/top-chrome.ts`:
    - `@Component({ selector: 'app-top-chrome', standalone: true, imports: [RouterLink], templateUrl: './top-chrome.html', styleUrl: './top-chrome.css' })`.
    - Inject `AuthService`, `Router`, `HttpClient` via `inject(...)`.
    - Expose `readonly me = this.authService.me` (re-export of the signal so the template can call `me()`).
    - Compute the contextual route via a signal:
      ```ts
      // toSignal converts router.events to a signal of the current URL path
      private readonly currentUrl = toSignal(
        this.router.events.pipe(
          filter((e): e is NavigationEnd => e instanceof NavigationEnd),
          map(e => e.urlAfterRedirects),
        ),
        { initialValue: this.router.url },
      );
      readonly contextLinkTarget = computed(() => this.currentUrl().startsWith('/settings') ? '/books' : '/settings');
      readonly contextLinkLabel = computed(() => this.currentUrl().startsWith('/settings') ? 'Books' : 'Settings');
      ```
      (Imports: `toSignal` from `@angular/core/rxjs-interop`; `filter`, `map` from `rxjs/operators`; `NavigationEnd` from `@angular/router`.)
    - Async method `onLogoutClick(): Promise<void>`:
      ```ts
      try {
        await firstValueFrom(this.http.post('/auth/logout', null));
      } finally {
        this.authService.clear();
        await this.router.navigateByUrl('/login');
      }
      ```
      **Critical:** the `finally` block runs on BOTH 2xx (where the try completes) AND non-2xx (where the try throws). On 2xx, the user logs out cleanly. On error, the SPA still clears local state and lands on `/login` — the user's session may still exist server-side, but the SPA's view of it is correct. (The global 401 handler in Story 1.9 would ALSO clear+navigate on 401, but the `finally` is idempotent and runs before the interceptor's error handler returns — so the net effect is the same: cleared signal, `/login` URL.) Acknowledge: this is slightly different from a strict reading of AC4 ("on 2xx response, clear and navigate"). The looser `finally` form is more robust — UX-wise, the user clicked `"Log out"`; honoring that intent regardless of network outcome is the right product behavior. The AC is satisfied because the 2xx path executes exactly the steps described.
  - [ ] Create `spa/src/app/shared/chrome/top-chrome.html`:
    - Outermost: a `<header>` element with Tailwind utilities for the 48px-tall full-width bar with the centered content column's padding mirrored (e.g., `flex items-center justify-between h-12 px-4 border-b border-border` — `h-12` materializes `--spacing-12` if declared, OR use an inline `style="height: 48px;"` since UX-DR1 only declares `--spacing-{1,2,3,4,6,8}`. Recommendation: use `style="height: 48px;"` to avoid expanding the UX-DR1 token set in this story; tokens are added by future stories if needed.).
    - Three children when `me()`:
      ```html
      @if (me()) {
        <span class="text-page-title">Reading Time Estimator</span>
        <a [routerLink]="contextLinkTarget()" class="text-body text-accent">{{ contextLinkLabel() }}</a>
        <div class="text-body">
          <span class="text-text-muted">Signed in as </span>
          <span class="text-text">{{ me()?.preferred_username }}</span>
          <span class="text-text-muted"> · </span>
          <button type="button" class="text-accent underline" (click)="onLogoutClick()">Log out</button>
        </div>
      } @else {
        <span class="text-page-title">Reading Time Estimator</span>
      }
      ```
    - Use `@if`/`@else` (Angular 21 native control flow). Do NOT use `*ngIf`.
  - [ ] Create `spa/src/app/shared/chrome/top-chrome.css` — empty or minimal.

- [ ] **Task 4 — Create `TopChrome` spec** (AC: #8)
  - [ ] Create `spa/src/app/shared/chrome/top-chrome.spec.ts`:
    - Imports: `TestBed`, `provideRouter`, `provideHttpClient(withFetch())`, `provideHttpClientTesting()`, the `TopChrome` component, the `AuthService` type.
    - For each test, configure `TestBed` with:
      - `providers: [provideRouter([{ path: '**', component: TopChrome /* placeholder */ }]), provideHttpClient(withFetch()), provideHttpClientTesting(), { provide: AuthService, useValue: <mockAuthService> }]`.
      - Provide a `mockAuthService` with `me: signal<Me | null>(null)`, `clear: vi.fn()`, `setMe: vi.fn()`, `loadMe: vi.fn().mockResolvedValue(undefined)`.
    - Test 1: unauthenticated — set `mockAuthService.me` to a signal of `null` (or just use `signal(null)` as the value). Create component, detect changes, assert `nativeElement.textContent.includes('Reading Time Estimator')` AND `!nativeElement.textContent.includes('Signed in as')` AND `!nativeElement.querySelector('button')`.
    - Test 2: authenticated on `/books` — set `mockAuthService.me` to `signal({ sub: 's1', preferred_username: 'alice' })`. Navigate the test `Router` to `/books` first (`await router.navigateByUrl('/books')` after `TestBed.inject(Router)`). Detect changes. Assert: textContent includes `"Reading Time Estimator"`, `"Settings"` (the link text), `"Signed in as "`, `"alice"`, `"Log out"`. Assert the route link's `href` (read via `nativeElement.querySelector('a').getAttribute('href')`) is `/settings`.
    - Test 3: authenticated on `/settings` — same setup, `await router.navigateByUrl('/settings')`. Assert link text is `"Books"` and `href` is `/books`.
    - Test 4: click `"Log out"` — set authenticated state, navigate to `/books`. Spy on `mockAuthService.clear` and on `Router.navigateByUrl`. Click the logout button. Use `HttpTestingController` to expect `POST /auth/logout` and `.flush(null, { status: 204, statusText: 'No Content' })`. Await microtask flushing (`await fixture.whenStable()`). Assert: `mockAuthService.clear` was called; `Router.navigateByUrl` was called with `'/login'` (the literal string, NOT a `UrlTree`).
    - For the route link `href` assertion: `RouterLink` directive renders an `href` attribute on `<a>` elements; you need to call `fixture.detectChanges()` after the router navigation completes. If the `href` is missing in tests, the most common cause is the `<a>` element doesn't have the `RouterLink` directive applied — verify `TopChrome` imports `RouterLink` and the template uses `[routerLink]`.

- [ ] **Task 5 — Create placeholder pages** (AC: #5)
  - [ ] Create `spa/src/app/books/book-list-page-placeholder.ts`:
    ```ts
    import { Component } from '@angular/core';
    import { TopChrome } from '../shared/chrome/top-chrome';

    @Component({
      selector: 'app-book-list-page-placeholder',
      standalone: true,
      imports: [TopChrome],
      templateUrl: './book-list-page-placeholder.html',
    })
    export class BookListPagePlaceholder {}
    ```
  - [ ] Create `spa/src/app/books/book-list-page-placeholder.html`:
    ```html
    <app-top-chrome />
    <main class="mx-auto max-w-[720px] p-8">
      <p class="text-body">Books — coming in Epic 2</p>
    </main>
    ```
  - [ ] Create `spa/src/app/books/book-list-page-placeholder.spec.ts` — assert placeholder text + `<app-top-chrome>` element presence. Mock `AuthService` minimally (placeholder doesn't read it, but `TopChrome` does — provide `{ me: signal(null), clear: vi.fn(), setMe: vi.fn(), loadMe: vi.fn().mockResolvedValue(undefined) }`); provide router + http testing as in Task 4.
  - [ ] Create `spa/src/app/settings/settings-page-placeholder.ts` — analogous structure, selector `app-settings-page-placeholder`, exports `SettingsPagePlaceholder`.
  - [ ] Create `spa/src/app/settings/settings-page-placeholder.html` — analogous; the `<p>` text is `Settings — coming in Epic 3`.
  - [ ] Create `spa/src/app/settings/settings-page-placeholder.spec.ts` — analogous to the books placeholder spec; assert `"Settings — coming in Epic 3"` text + `<app-top-chrome>`.
  - [ ] **Important:** do NOT create `books/book-list-page.ts` or `settings/settings-page.ts` in this story — those are the REAL pages owned by Stories 2.5 and 3.5 respectively. The `-placeholder` suffix in the file/class names is intentional: Story 2.5 will create `books/book-list-page.ts` and update `app.routes.ts` to point to it; the placeholder file can either be deleted by that story or renamed.

- [ ] **Task 6 — Wire the route table** (AC: #1)
  - [ ] Replace contents of `spa/src/app/app.routes.ts`:
    ```ts
    import { Routes } from '@angular/router';
    import { authGuard } from './auth/auth-guard';
    import { redirectIfAuthedGuard } from './auth/redirect-if-authed-guard';

    export const routes: Routes = [
      { path: '', pathMatch: 'full', redirectTo: 'books' },
      {
        path: 'login',
        loadComponent: () => import('./login/login-view').then(m => m.LoginView),
        canActivate: [redirectIfAuthedGuard],
      },
      {
        path: 'books',
        loadComponent: () => import('./books/book-list-page-placeholder').then(m => m.BookListPagePlaceholder),
        canActivate: [authGuard],
      },
      {
        path: 'settings',
        loadComponent: () => import('./settings/settings-page-placeholder').then(m => m.SettingsPagePlaceholder),
        canActivate: [authGuard],
      },
      { path: '**', redirectTo: 'books' },
    ];
    ```
  - [ ] Do NOT add a `useHash` or `withDebugTracing` option to `provideRouter` — defaults are correct.
  - [ ] The two guards are imported from the existing Story 1.9 files; do not touch those files.

- [ ] **Task 7 — Add `provideAppInitializer` for `loadMe()`** (AC: #7)
  - [ ] Edit `spa/src/app/app.config.ts`:
    - Import `provideAppInitializer` from `@angular/core` and `inject` (already imported elsewhere in your file, but verify).
    - Import `AuthService` from `./auth/auth-service`.
    - Add `provideAppInitializer(() => inject(AuthService).loadMe())` to the providers array. Order in providers array does NOT matter for app initializers; place it adjacent to the other functional providers (after `provideZonelessChangeDetection()` is a natural spot).
  - [ ] Do NOT touch `provideHttpClient` or its interceptors — they are correct from Story 1.9.
  - [ ] Do NOT touch `provideRouter(routes)` — the `routes` reference now points to the populated routes table (the same import).

- [ ] **Task 8 — Update `App` root component to render TopChrome + router-outlet** (AC: #6)
  - [ ] Replace contents of `spa/src/app/app.html`:
    ```html
    <app-top-chrome />
    <router-outlet />
    ```
    (Centralized approach: `TopChrome` renders for every route. On `/login`, the unauthenticated variant renders — product name only. On `/books` and `/settings`, the authenticated variant renders. This is correct per UX-DR2.)
  - [ ] Edit `spa/src/app/app.ts`:
    - Import `TopChrome` from `./shared/chrome/top-chrome`.
    - Add `TopChrome` to the component's `imports` array (alongside `RouterOutlet`).
    - **Remove** the unused `signal` import and the `protected readonly title = signal('spa');` field — neither is referenced by the new template. (Leave them if removing them would force you to also touch `app.css` or other unrelated files; the lint config does not error on unused fields, only unused imports.)
  - [ ] **NOTE on placeholders & centralized TopChrome:** when `TopChrome` is in `app.html` AND each placeholder page also renders `<app-top-chrome />` (Task 5 above), `TopChrome` will render TWICE on `/books` and `/settings`. Resolve by removing the `<app-top-chrome />` from the placeholders (Task 5's template becomes just the centered `<main>` block). The AC5 requirement is met because `TopChrome` IS rendered above the placeholder content — just from `app.html`, not from the placeholder template. Update the placeholder specs accordingly: instead of asserting `<app-top-chrome>` is in the placeholder's own template, the placeholder spec only asserts the placeholder text — and a NEW assertion in `app.spec.ts` covers the `<app-top-chrome>` + `<router-outlet>` rendering. (Alternative: keep `<app-top-chrome />` in each placeholder template and remove it from `app.html` — but then `/login` would have NO chrome unless `LoginView` also adds one. The centralized approach is simpler. **Adopt the centralized approach.**)
  - [ ] Update `spa/src/app/app.spec.ts`:
    - **Delete** the AC7 smoke-fragment test (`should render the AC7 smoke fragment with token-derived utility classes`) — the smoke fragment is gone.
    - Keep `should create the app` (the assertion still passes against the new template).
    - **Add** a test `renders TopChrome and router-outlet` that asserts both `nativeElement.querySelector('app-top-chrome')` and `nativeElement.querySelector('router-outlet')` are present after `fixture.detectChanges()` + `await fixture.whenStable()`.
    - Provide a minimal `AuthService` mock + router + http testing in the new `TestBed` config — `App` indirectly depends on `AuthService` via `TopChrome`.

- [ ] **Task 9 — Run gates and capture transcripts** (AC: #10)
  - [ ] `cd spa && npm run lint` — exits 0. If it fails, common causes: a forbidden `console.log` (use `console.warn`/`console.error` or remove); an empty `catch {}` (the `try/finally` in `onLogoutClick` is fine because it has no `catch` block — but if you wrote `try/catch`, the catch must have a non-empty body); a selector that doesn't start with `app-`.
  - [ ] `npm run build` — exits 0. Verify `dist/spa/browser/index.html` exists. The build output should show four lazy chunks (one per route component) — visually confirmable in the CLI output.
  - [ ] `npm test -- --no-watch` — exits 0. Verify total test count is roughly Story 1.9's 17 + Story 1.8's surviving 1 + the new ~10–15 = ~27–32 (the exact count is fine; the AC requires ALL tests pass).
  - [ ] `npm run test:coverage` — exits 0. Verify line coverage for `login/**`, `shared/chrome/**`, `books/**`, `settings/**` is ≥70%. Record exact percentages in Debug Log References.
  - [ ] Capture all four exit-0 transcripts (lint, build, test, coverage) in the Dev Agent Record's Debug Log References — same discipline as Story 1.9.

- [ ] **Task 10 — Verify no out-of-scope changes** (AC: #10)
  - [ ] Run `git status` and `git diff --stat` and verify the changed files are exactly:
    - **New:** `spa/src/app/login/login-view.{ts,html,css,spec.ts}`, `spa/src/app/shared/chrome/top-chrome.{ts,html,css,spec.ts}`, `spa/src/app/books/book-list-page-placeholder.{ts,html,spec.ts}`, `spa/src/app/settings/settings-page-placeholder.{ts,html,spec.ts}`.
    - **Modified:** `spa/src/app/app.routes.ts`, `spa/src/app/app.config.ts`, `spa/src/app/app.html`, `spa/src/app/app.ts`, `spa/src/app/app.spec.ts`.
    - **Untouched:** `spa/src/app/auth/**` (Story 1.9's files), `spa/src/app/shared/http/**` (Story 1.9's files), `spa/proxy.conf.json`, `spa/eslint.config.js`, `spa/src/styles.css`, `spa/package.json`, `spa/angular.json`, `spa/tsconfig*.json`.
    - **Not created:** `spa/src/app/books/book-list-page.{ts,html,css,spec.ts}` (Story 2.5's job), `spa/src/app/settings/settings-page.{ts,html,css,spec.ts}` (Story 3.5's job), `spa/src/app/shared/errors/**` (a feature-story's job), `spa/src/app/shared/ui/**` (an `ErrorMessage` story's job — likely Story 2.5 or 2.6).

## Dev Notes

### What this story is — and is not

This story produces **only** the SPA's visible auth chrome (`LoginView`, `TopChrome`), the route table that wires them up, and two thin placeholder pages so the route table is activatable end-to-end. It does **not** implement the real `BookListPage` (Story 2.5), real `SettingsPage` (Story 3.5), the `ErrorMessage` shared component (Story 2.5/2.6), the `AppError` discriminated union (Story 2.4 onward), or any E2E test (Story 1.13). It does **not** modify the auth/HTTP plumbing from Story 1.9. It does **not** require a running BFF or Keycloak — every assertion is unit-level via `HttpTestingController` and component DOM inspection. Story 1.13 (Playwright) will be the first story to exercise this code against a live stack.

What this story locks in for downstream stories:

1. `app.routes.ts` is populated. Stories 2.5 and 3.5 will replace the `*-placeholder` references with real `BookListPage` / `SettingsPage` components.
2. `TopChrome` reads `AuthService.me()` for its variant decision and uses `Router.url` for its contextual route link. Stories that change the URL structure (none planned) would also need to update `TopChrome`.
3. `App` root renders `<app-top-chrome /><router-outlet />`. The Story 1.8 smoke fragment is deleted. Future stories build inside `<router-outlet />`.
4. `provideAppInitializer(() => inject(AuthService).loadMe())` is added. This is the SPA's single auth-state initialization point. Other stories MUST NOT add competing initializers for `me`.
5. `POST /auth/logout` is exercised end-to-end (in the SPA — the BFF endpoint itself was built in Story 1.7). The CSRF interceptor and session cookie wiring from Story 1.9 are the first time exercised against a real handler call in this story (in unit tests, not live).

### Existing repo state at story start

Branch will likely be `E1S10` (Story 1.9 was on `E1S9`; pattern continues). Last merged stories: 1.1–1.9 all `done` per sprint-status.

Spa structure currently:
```
spa/src/app/
├── app.config.ts                    # has provideHttpClient + interceptors from Story 1.9
├── app.html                         # AC7 smoke fragment (to be replaced)
├── app.routes.ts                    # empty Routes array (to be populated)
├── app.spec.ts                      # 2 tests (smoke fragment test to be deleted)
├── app.ts                           # imports RouterOutlet; has unused `title = signal('spa')`
├── app.css                          # empty
├── auth/                            # 5 files from Story 1.9, all done — DO NOT MODIFY
└── shared/http/                     # 4 files from Story 1.9, all done — DO NOT MODIFY
```

Test counts at story start: 6 spec files, 19 tests (Story 1.8's `app.spec.ts` 2 + Story 1.9's 5 new specs with 17 tests).

`spa/styles.css` declares UX-DR1 tokens (`--color-surface`, `--color-text`, `--color-text-muted`, `--color-accent`, `--color-error`, `--text-page-title`, `--text-body`, `--text-small`, `--text-section`, `--spacing-1..8`). Tailwind v4 materializes these as utilities: `bg-surface`, `text-text`, `text-text-muted`, `bg-accent` / `text-accent`, `text-error`, `text-page-title`, `text-body`, `text-small`, `text-section`, `p-1..8`, `m-1..8`, `px-1..8`, `py-1..8`, `mx-1..8`, `my-1..8`, `gap-1..8`. **You do NOT need to add tokens or utilities** — use only the existing ones. If a needed utility doesn't materialize from the declared tokens, use an inline `style="..."` (e.g., `style="height: 48px;"` for the 48px chrome height, since `--spacing-12` is not declared) rather than expand the token set.

### Source-of-truth references

- **Story spec + ACs** (canonical, verbatim): [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.10: SPA LoginView + TopChrome + route table` lines 563–617].
- **AR21 — Signals + per-feature services** (`AuthService.me` is the source of truth): [Source: `_bmad-output/planning-artifacts/epics.md` line 81].
- **AR22 — Two HTTP interceptors registered in `app.config.ts`** (already done in Story 1.9; `TopChrome`'s `POST /auth/logout` automatically gets `withCredentials` + `X-CSRF-Token`): [Source: `_bmad-output/planning-artifacts/epics.md` line 82].
- **AR23 — Routing & guards** (functional router config in `app.config.ts`, the exact 5-route table this story implements): [Source: `_bmad-output/planning-artifacts/epics.md` line 83].
- **UX-DR2 — TopChrome component** (anatomy, both variants, contextual route link swap, `Signed in as <preferred_username> · Log out` literal copy): [Source: `_bmad-output/planning-artifacts/epics.md` line 104].
- **UX-DR3 — LoginView component** (centered, headline + paragraph + button, `?error=auth` inline message): [Source: `_bmad-output/planning-artifacts/epics.md` line 105].
- **UX-DR12 — Failure copy strings** (the literal `"Login didn't complete — try again."` text is locked here): [Source: `_bmad-output/planning-artifacts/epics.md` line 114].
- **Architecture F1 — `AuthService` exposes `me`** (the signal that `TopChrome` reads): [Source: `_bmad-output/planning-artifacts/architecture.md` lines 424–426].
- **Architecture F4 — `authGuard` on `/books` and `/settings`; `redirectIfAuthedGuard` on `/login`** (the route guards Story 1.9 created and this story consumes): [Source: `_bmad-output/planning-artifacts/architecture.md` line 441].
- **Architecture F5 — canonical 5-entry route table** (this is the table this story types out): [Source: `_bmad-output/planning-artifacts/architecture.md` lines 443–456].
- **Architecture C2 — `POST /auth/logout` returns 204 with `Set-Cookie clear`** (the contract `TopChrome.onLogoutClick` consumes): [Source: `_bmad-output/planning-artifacts/architecture.md` line 367 + line 680 (the 204 status row)].
- **Architecture §"Testing patterns" — Vitest + Angular TestBed, `HttpTestingController`, signal-getter assertions**: [Source: `_bmad-output/planning-artifacts/architecture.md` lines 790–796].
- **Architecture §"Enforcement Guidelines" — signal-only state, no parallel store, no empty catch, no `console.log`**: [Source: `_bmad-output/planning-artifacts/architecture.md` lines 797–815].
- **Architecture §"Complete Project Directory Structure" — target paths**: [Source: `_bmad-output/planning-artifacts/architecture.md` lines 1029–1062]. Note that the architecture lists `book-list-page.{ts,html,css,spec.ts}` and `settings-page.{ts,html,css,spec.ts}` — those are the REAL pages owned by Stories 2.5 and 3.5. This story creates `*-placeholder.{ts,html,spec.ts}` files (no `.css`, no real-page name).
- **UX §"Visual Design Foundation"** — design token semantics, color rules, type scale, spacing scale: [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 257–328].
- **UX §"Component Strategy — TopChrome"** (anatomy, 48px tall, identity + logout): [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 588–593].
- **UX §"Component Strategy — LoginView"** (anatomy: centered, headline + paragraph + one button): [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 595–600].
- **UX J1 — First-time login sequence** (the journey this story unblocks from the SPA side): [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 377–414].
- **UX J5 — Logout sequence** (the journey `TopChrome.onLogoutClick` realizes): [Source: `_bmad-output/planning-artifacts/ux-design-specification.md` lines 509–538].
- **Story 1.9 dev notes** (the auth/HTTP plumbing this story sits on top of): [Source: `_bmad-output/implementation-artifacts/1-9-spa-authservice-interceptors-functional-guards.md`].
- **Story 1.8 dev notes** (the Tailwind v4 + design-tokens scaffold; explains the utility classes available): [Source: `_bmad-output/implementation-artifacts/1-8-spa-scaffold-tailwind-v4-design-tokens.md`].

### Files this story creates

```
spa/src/app/login/
├── login-view.ts                                # Task 1 — standalone component
├── login-view.html                              # Task 1 — template
├── login-view.css                               # Task 1 — empty or minimal
└── login-view.spec.ts                           # Task 2 — 3 tests

spa/src/app/shared/chrome/
├── top-chrome.ts                                # Task 3 — standalone component
├── top-chrome.html                              # Task 3 — template
├── top-chrome.css                               # Task 3 — empty or minimal
└── top-chrome.spec.ts                           # Task 4 — 4 tests

spa/src/app/books/
├── book-list-page-placeholder.ts                # Task 5 — placeholder
├── book-list-page-placeholder.html              # Task 5 — placeholder template
└── book-list-page-placeholder.spec.ts           # Task 5 — 1 test

spa/src/app/settings/
├── settings-page-placeholder.ts                 # Task 5 — placeholder
├── settings-page-placeholder.html               # Task 5 — placeholder template
└── settings-page-placeholder.spec.ts            # Task 5 — 1 test
```

### Files this story modifies

```
spa/src/app/app.routes.ts                        # Task 6 — populate 5-entry route table
spa/src/app/app.config.ts                        # Task 7 — add provideAppInitializer
spa/src/app/app.html                             # Task 8 — replace smoke fragment with TopChrome + router-outlet
spa/src/app/app.ts                               # Task 8 — import TopChrome
spa/src/app/app.spec.ts                          # Task 8 — delete smoke test; add TopChrome+RouterOutlet test
```

### Files this story explicitly does NOT touch

- `spa/src/app/auth/**` — Story 1.9's 5 files. Read-only consumers.
- `spa/src/app/shared/http/**` — Story 1.9's 4 files. The interceptors handle every HTTP call this story makes.
- `spa/proxy.conf.json` — D10 from Story 1.1 is still acknowledged but not resolved. `POST /auth/logout` IS exercised by `TopChrome` in unit tests (via `HttpTestingController` — no live proxy needed) and will be exercised live in Story 1.13's Playwright run.
- `spa/eslint.config.js` — no rule changes required.
- `spa/src/styles.css` — UX-DR1 tokens are sufficient. Do not add new tokens.
- `spa/package.json` — no new dependencies. (`@angular/router` `RouterLink` and `RouterOutlet` are already imported transitively; `toSignal` is in `@angular/core/rxjs-interop` which is part of Angular's framework; `rxjs/operators` `filter`/`map` are in the existing `rxjs@~7.8.0` dep.)
- `spa/angular.json`, `spa/tsconfig*.json` — no config changes.
- Any file outside `spa/` (`services/`, `keycloak/`, `e2e/`, `compose/`, `_bmad-output/planning-artifacts/`) — untouched. The sprint-status flip is workflow-time, already done.

### Critical implementation details

#### 1. Why `window.location.assign('/auth/login')` and NOT `Router.navigate(...)`

`/auth/login` is a BFF endpoint, not an Angular route. The BFF responds with a `302` redirect to Keycloak's `/realms/.../authorize`. The browser must perform this navigation as a **top-level document navigation** so:

1. The `Set-Cookie` headers from the BFF can land in the browser cookie jar (the cookie attributes — `HttpOnly`, `SameSite=Lax`, `Secure` in prod — only set correctly when the browser, not `HttpClient`, owns the response).
2. The browser follows the `302` cross-origin to Keycloak, where the user enters credentials.
3. After Keycloak authenticates and redirects back to `/auth/callback`, the BFF redirects again to `/books` (or to `return_to`), and the browser arrives at `/books` with the freshly-set session cookie attached.

If you used `Router.navigate(['/auth/login'])`, Angular's router would treat `/auth/login` as a CLIENT-side route (which doesn't exist) and either match the `**` wildcard (redirecting to `/books`) or fall through to a 404 — never reaching the BFF.

If you used `HttpClient.get('/auth/login')`, the request would succeed (the BFF would return a 302 with the `Location` header pointing at Keycloak), but `HttpClient` follows redirects within the same origin only by default, and even if it did follow the cross-origin redirect, the resulting Keycloak HTML would be returned as a response body to JS — the user never sees the login page.

The correct primitive is `window.location.assign('/auth/login')` (or equivalently `window.location.href = '/auth/login'`). Both are top-level navigations.

**Testing this:** spying on `window.location.assign` is brittle (it's not configurable in JSDOM). The recommended pattern is to put the `window.location.assign(...)` call in a named method on the component (e.g., `onLoginClick()`) and spy on the method:

```ts
const spy = vi.spyOn(component, 'onLoginClick');
buttonEl.click();
expect(spy).toHaveBeenCalledOnce();
```

This proves the click invokes the handler; the handler's implementation is one line and visually verified.

#### 2. Why `TopChrome` does NOT call `Router.navigate(['/login'])` after `clear()`

It MAY look redundant since the global 401 handler in `withCredentialsInterceptor` already navigates on 401. But `POST /auth/logout` returns **204** on success, not 401. The 401 path only runs if the session already expired BEFORE the user clicked `"Log out"` — in which case the BFF's logout endpoint may return 204 anyway (logout is idempotent per architecture C2). To guarantee the user lands on `/login` regardless of HTTP outcome, `TopChrome.onLogoutClick` performs the navigation itself in a `finally` block. This is intentional duplication — and the duplication is safe: if both `withCredentialsInterceptor` and `TopChrome` schedule a `navigate('/login')`, the second is a no-op (the Angular router de-duplicates equivalent navigations).

#### 3. `Router.url` vs `Router.events` for the contextual route link

The contextual route link in `TopChrome` swaps text based on the current URL path:

- On `/books` → link shows `"Settings"` pointing at `/settings`.
- On `/settings` → link shows `"Books"` pointing at `/books`.

The naive implementation reads `this.router.url` at render time:

```ts
readonly contextLinkLabel = computed(() => this.router.url.startsWith('/settings') ? 'Books' : 'Settings');
```

But `this.router.url` is a plain property, not a signal — `computed(() => this.router.url...)` will not re-evaluate when the URL changes. **You need a signal of the URL.** The clean Angular 21 idiom is `toSignal(router.events.pipe(...))`:

```ts
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd } from '@angular/router';
import { filter, map } from 'rxjs/operators';

private readonly currentUrl = toSignal(
  this.router.events.pipe(
    filter((e): e is NavigationEnd => e instanceof NavigationEnd),
    map(e => e.urlAfterRedirects),
  ),
  { initialValue: this.router.url },
);
readonly contextLinkTarget = computed(() => this.currentUrl().startsWith('/settings') ? '/books' : '/settings');
readonly contextLinkLabel = computed(() => this.currentUrl().startsWith('/settings') ? 'Books' : 'Settings');
```

- The `initialValue: this.router.url` handles the first render (before any `NavigationEnd` fires).
- `urlAfterRedirects` is the post-redirect URL — important because `''` redirects to `/books` and the router emits the redirected URL.
- `filter(... instanceof NavigationEnd)` ignores `NavigationStart`/`NavigationCancel`/etc. so the signal only updates on completed navigations.

**In tests:** when you `await router.navigateByUrl('/books')` and then call `fixture.detectChanges()`, the `NavigationEnd` event fires synchronously (via the test Router's microtask queue), the signal updates, and the template reads the new value. If your test reads the link text before `await router.navigateByUrl(...)` resolves, the signal is at its initial value (`router.url` — which is `/` in the default test setup) and the assertion will fail. Always `await` the navigation.

#### 4. `RouterLink` vs `routerLink` in templates

Angular 21 syntax:

- `routerLink="/settings"` — static string.
- `[routerLink]="contextLinkTarget()"` — bound to an expression (signal getter).

This story uses the bound form because the target changes with the URL. The `<a>` element with `[routerLink]` MUST be inside a component whose `imports` array includes `RouterLink` from `@angular/router` (standalone-component requirement). The `TopChrome` component declares `imports: [RouterLink]` for this reason.

#### 5. Control flow syntax — `@if`, `@for`, `@switch`

Angular 21 ships native template control flow (the `@` syntax) as the preferred form over the structural directives (`*ngIf`, `*ngFor`, `*ngSwitch`). The `@if (cond) { ... } @else { ... }` form does NOT require an import (it's parsed by the Angular compiler directly), whereas `*ngIf` requires `CommonModule` or `NgIf` in the component's `imports` array. **Use the `@` syntax exclusively** in this story's templates — it's the architecture's idiom and avoids the `CommonModule` import.

#### 6. `provideAppInitializer` vs the legacy `APP_INITIALIZER` token

Angular 21 deprecates the `APP_INITIALIZER` `InjectionToken` + multi-provider pattern in favor of `provideAppInitializer(() => ...)`. The new API:

```ts
import { provideAppInitializer, inject } from '@angular/core';

provideAppInitializer(() => {
  return inject(AuthService).loadMe();   // returns Promise<void> — Angular awaits it before bootstrap completes
});
```

- The factory may return `void`, `Promise<void>`, or `Observable<void>`. Bootstrap awaits all returned promises/observables (a Promise resolution OR observable completion) before continuing.
- `inject(AuthService)` works because `provideAppInitializer`'s factory runs inside Angular's injection context.
- If `loadMe()` rejects, bootstrap fails. **Verify Story 1.9's `AuthService.loadMe()` does not rethrow on 401** — it does not (it sets `_me` to `null` and `return`s). If you want belt-and-suspenders behavior, you can write `provideAppInitializer(() => inject(AuthService).loadMe().catch(() => undefined))`, but the unconditional `.catch` is unnecessary given the existing contract.

#### 7. Tailwind utilities derived from UX-DR1 tokens

Tailwind v4 materializes utilities from the `@theme` block in `styles.css`. The full list of utilities available from Story 1.8's tokens:

- **Colors (background, text, border):** `bg-surface`, `bg-surface-muted`, `bg-border`, `bg-text`, `bg-text-muted`, `bg-accent`, `bg-accent-hover`, `bg-error`, and their `text-*` and `border-*` equivalents.
- **Text scale:** `text-page-title`, `text-section`, `text-body`, `text-small`. These set font-size + line-height + font-weight in a single utility (Tailwind v4 parses the `--text-{name}: <size> / <line-height> <weight>;` shorthand).
- **Spacing:** `p-{1,2,3,4,6,8}`, `m-{1,2,3,4,6,8}`, `px-`, `py-`, `mx-`, `my-`, `gap-`, `space-y-`, `space-x-` — all derived from `--spacing-{1..8}` (4, 8, 12, 16, 24, 32 px).

Utilities NOT derived from declared tokens (use sparingly, with inline `style="..."` or hard-coded Tailwind values via the `[...]` arbitrary-value syntax):

- Heights/widths: `--spacing-*` covers padding/margin/gap but not `h-{N}` / `w-{N}` directly. Use `style="height: 48px;"` for the chrome bar (alternative: `h-12` which is Tailwind's default = 48px and is independent of `--spacing-12`).
- Hover states: `hover:bg-accent-hover` works because `--color-accent-hover` is declared.

#### 8. Where does `TopChrome` live in the DOM?

Two valid options:

1. **Centralized** (recommended, this story uses this): `<app-top-chrome />` is rendered ONCE in `app.html`, above `<router-outlet />`. Every route inherits the chrome. The chrome reads `AuthService.me()` to decide its variant — so on `/login` it renders the unauthenticated variant (product name only), and on `/books`/`/settings` it renders the authenticated variant.

2. **Per-page** (architecture line 1029 says `app.ts` is the "root App component (TopChrome + `<router-outlet>`)" — which matches Option 1). Per-page rendering would mean each route component embeds `<app-top-chrome />` at the top of its template. This duplicates the import + template fragment in every route component and complicates the placeholder pages.

**Adopt Option 1** (centralized). The architecture documentation supports it ("root App component (TopChrome + `<router-outlet>`)" at line 1029). This implementation choice was already locked in by the architecture; this story just executes it.

Implication for `BookListPagePlaceholder` and `SettingsPagePlaceholder`: their templates do NOT include `<app-top-chrome />`. They render only their own `<main>` block. The placeholder specs assert their own text content; the `<app-top-chrome>` presence is asserted by `app.spec.ts` (it's `App`'s job, not the route's).

This is a refinement to Task 5 vs the initial AC5 reading — AC5 said the placeholder template includes `<app-top-chrome />`. The refinement chooses the centralized approach, which the architecture endorses and which avoids double-rendering. **Document this in Completion Notes as a refinement, not a deviation.**

#### 9. The `Me` type and `preferred_username`

`Me` is `{ sub: string; preferred_username: string }` per Story 1.9's `auth.types.ts`. The wire shape is snake_case in both directions — per AR16 the SPA mirrors `preferred_username` (NOT `preferredUsername`). `TopChrome` reads `me()?.preferred_username` directly in the template. Do NOT introduce a getter or computed for `preferredUsername`; the parity rule is non-negotiable.

The UX spec (line 305) says `"Signed in as <sub or preferred_username>"` — the OR was a historical hedge. The architecture's `GET /api/me` contract returns both `sub` and `preferred_username`, and the user-visible identity is `preferred_username`. Display `preferred_username`; `sub` is the opaque session identifier and is for logs/correlation only.

#### 10. Lazy-loaded chunks

Each `loadComponent: () => import('./...').then(m => m.X)` becomes its own webpack chunk. The Angular build output should show four extra chunks beyond `main.js`:

- `login-view.<hash>.js` — `LoginView`
- `book-list-page-placeholder.<hash>.js` — `BookListPagePlaceholder`
- `settings-page-placeholder.<hash>.js` — `SettingsPagePlaceholder`
- (`TopChrome` is NOT lazy-loaded — it's a direct import in `App` — so it lives in `main.js`.)

This is mostly cosmetic at this stage; the chunks are tiny. But it's the correct pattern for when stories 2.5 / 3.5 inflate `BookListPage` / `SettingsPage` to real page components — they remain lazy.

### Anti-patterns to avoid

- **Do NOT** use `Router.navigate(['/auth/login'])` or `HttpClient.get('/auth/login')` for the `"Log in"` click — see Detail #1.
- **Do NOT** use `*ngIf` / `*ngFor` / `*ngSwitch` — use `@if` / `@for` / `@switch` native control flow.
- **Do NOT** import `CommonModule` into any component in this story — none of the templates need it (no pipes, no structural directives via `*`).
- **Do NOT** add ARIA attributes, `role` attributes, focus-trap logic, or responsive media queries. Accessibility AND responsive design are explicitly out of scope per PRD §4 / project-memory `project_bmad_books_scope`. Use semantic HTML (`<header>`, `<main>`, `<button>`, `<a>`) and let the browser's defaults handle keyboard/focus behavior.
- **Do NOT** rename `Me.preferred_username` to `preferredUsername` or introduce a case-conversion layer — see Detail #9.
- **Do NOT** read `AuthService.me` via subscription or observable — it's a signal; call it via `me()` in templates and `this.authService.me()` in `.ts` code (or via `computed()` for derived state).
- **Do NOT** call `loadMe()` from `TopChrome` or any other component — `provideAppInitializer` handles the single load; guards refresh it via `setMe` on activation. Components are read-only consumers of `me()`.
- **Do NOT** add a `Logout` confirmation dialog or a "Are you sure?" step. The architecture and UX spec are unambiguous: one click logs out. Adding a confirmation is scope creep.
- **Do NOT** add icons. UX §"Component Strategy" says "No icon library. Text labels everywhere" (line 198). `Log out` is a text button; the `·` separator is the only "decoration."
- **Do NOT** add per-component CSS files with extensive rules. Tailwind utilities are the styling primitive. `login-view.css` and `top-chrome.css` can be empty.
- **Do NOT** create a `tailwind.config.{js,ts}` — Tailwind v4 is CSS-first, configured via the `@theme` block in `styles.css` (Story 1.8 locks this in).
- **Do NOT** add new tokens to `styles.css` — UX-DR1's token set is the entire palette. If you need a height/width that maps to no token, use an inline `style="..."` or Tailwind's built-in scale (`h-12` is fine — Tailwind's default `h-12` = 48px and doesn't need a token).
- **Do NOT** pre-create `shared/errors/`, `shared/ui/`, or any folder under `shared/` beyond `chrome/`. Story 2.5 / 2.6 create `shared/ui/error-message`; Story 2.4 creates `shared/errors/`. This story creates ONLY `shared/chrome/`.
- **Do NOT** create the real `book-list-page.{ts,...}` or `settings-page.{ts,...}` — those are Stories 2.5 and 3.5. Suffix is `-placeholder` for now.
- **Do NOT** modify any Story 1.9 file (`auth-service.ts`, `auth-guard.ts`, `redirect-if-authed-guard.ts`, `auth.types.ts`, `with-credentials-interceptor.ts`, `csrf-interceptor.ts`, or their specs). If you find a bug in Story 1.9's code while implementing this story, raise it as a deferred-work item; do not fix it inline.
- **Do NOT** add E2E tests, Playwright config, or any test that hits a live BFF. Story 1.11 sets up Playwright; Story 1.13 writes the J1+J5 E2E specs.
- **Do NOT** introduce `BehaviorSubject`, `Subject`, `ReplaySubject`, or any RxJS state primitive. AR21 mandates signals; the only RxJS primitive permitted is `Observable` for the (unavoidable) `HttpClient.get/post(...)` return types and the `Router.events` stream, both immediately converted to signals or awaited with `firstValueFrom(...)`.
- **Do NOT** add `withDebugTracing()` to `provideRouter` — it's a debug-time option and would pollute the console in production.
- **Do NOT** call `console.log` outside specs — ESLint's `no-console` rule blocks it. Use `console.warn`/`console.error` if you must log; or just don't.
- **Do NOT** write empty `catch {}` blocks — ESLint's `no-empty` with `allowEmptyCatch: false` blocks it. The `try/finally` in `onLogoutClick` is fine (no `catch`); if you write `try/catch`, the catch must do something.

### Previous story intelligence (from Story 1.9)

Story 1.9's review and dev notes surfaced patterns this story inherits:

1. **Functional everything.** Functional `inject(...)` (not constructor DI), functional `HttpInterceptorFn` (not class-based `HttpInterceptor`), functional `CanActivateFn` (not class-based `CanActivate`), functional `provideAppInitializer` (not the `APP_INITIALIZER` token). Maintain the discipline.
2. **`HttpTestingController` over mocking `HttpClient`.** The Story 1.9 pattern: configure `TestBed` with `provideHttpClient(withFetch())` + `provideHttpClientTesting()`, inject `HttpTestingController`, use `httpTesting.expectOne(url)` + `.flush(body, status)` in each test. Apply the same pattern to `TopChrome`'s logout test.
3. **`TestBed.runInInjectionContext` is needed for functional guards/interceptors** — but NOT for components (components are constructed by `TestBed.createComponent` which already provides the injection context). So `LoginView` and `TopChrome` specs do NOT need `runInInjectionContext`.
4. **`provideHttpClientTesting()` (functional)** replaces the deprecated `HttpClientTestingModule`. Use the functional form.
5. **Coverage is measured per-folder.** Story 1.9's `vitest.config.ts` was deferred (the Angular CLI `ng test --coverage` works without it). This story does NOT add a `vitest.config.ts` — the existing `test:coverage` script reports per-folder line coverage out of the box.
6. **`AuthService.setMe` exists** as the internal writer used by guards and (eventually) the auth-callback handler. `TopChrome` reads `me()` only — it does not need to write.
7. **The `Me` type is in `auth.types.ts`** — import via `import { Me } from '../auth/auth.types';` (one folder up from `chrome/`, into `auth/`).
8. **Story 1.9's review explicitly deferred** the `app.html` smoke-fragment test improvement (D11). The current story DELETES the smoke fragment entirely — that supersedes D11 (the test now asserts real component rendering, not class-name presence).
9. **Story 1.9 did NOT modify `app.routes.ts`** — this story is the first to populate the routes array. The guards (`authGuard`, `redirectIfAuthedGuard`) are exported and ready to consume.
10. **Story 1.9's interceptors handle every HTTP call this story makes** — `POST /auth/logout` automatically gets `withCredentials: true` (session cookie attached) and `X-CSRF-Token` header (from the `csrf_token` cookie). The dev does NOT need to set these per-call.

### Git intelligence

Recent commits (newest first):

```
d77c8d0 Merge branch 'E1S6'
cc0f532 feat: implement story 1.6
e90a34c feat: implement story 1.7
48f69b5 feat: implement story 1.6
2c2a86c feat: implement story 1.5
6550fa4 feat: implement story 1.4
ba784f8 Merge branch 'story-1-3'
295ed48 feat: 1-3 scaffold bffe
60aa25b feat: completed bff scaffolding
b696884 feat: implement S1E9
```

Story 1.10 will be on a branch named (by convention) `E1S10` or `story-1-10`. The merge base is `main` (or whatever the parent branch is at story start). The only files Story 1.10 modifies that were last touched by another story: `app.html`, `app.ts`, `app.routes.ts`, `app.spec.ts`, `app.config.ts` (last edited by Stories 1.8 + 1.9). No conflict expected — Story 1.9's edit to `app.config.ts` was additive (adding interceptors); this story's edit is also additive (adding `provideAppInitializer`).

### Latest tech specifics

- **Angular v21.2.x.** `provideAppInitializer` (the functional initializer API) is stable as of v19+. `toSignal` (the RxJS→Signal interop) is stable in `@angular/core/rxjs-interop`. Native control flow (`@if`/`@for`/`@switch`) is stable in v17+.
- **`RouterLink` is in `@angular/router`** — import directly (not via `RouterModule.forRoot`/`forChild`; those are NgModule-era APIs).
- **`provideHttpClient(withFetch())` materializes `withCredentials: true` as `credentials: 'include'`** in the Fetch API. Story 1.9 verified this in `with-credentials-interceptor.spec.ts`.
- **Tailwind v4.3.x** materializes utilities from the `@theme` block. No `tailwind.config.{js,ts}`. The plugin is `@tailwindcss/postcss` in `.postcssrc.json`.
- **Vitest 4.1.6** runs the test suite via `@angular/build:unit-test`. `ng test --no-watch` is the single-run invocation; `ng test --coverage` runs the coverage report.
- **Zoneless change detection** is on (`provideZonelessChangeDetection()`). Signals are the reactive primitive. Do NOT import `zone.js` or `polyfills` related to Zone.

### Project Structure Notes

- The two new feature folders (`login/`, `shared/chrome/`) are the first under their respective siblings. `login/` had no prior contents; `shared/` previously only had `http/` (from Story 1.9). Architecture §"Complete Project Directory Structure" lines 1045–1062 specifies the exact layout — adhere to it precisely.
- The two new placeholder folders (`books/`, `settings/`) are also fresh. Their REAL pages (per the architecture) are `book-list-page.{ts,html,css,spec.ts}` (Story 2.5) and `settings-page.{ts,html,css,spec.ts}` (Story 3.5). This story uses the `*-placeholder` suffix to distinguish them — a naming convention not in the architecture, but consistent with the AC1 references to `BookListPagePlaceholder` / `SettingsPagePlaceholder`. When Stories 2.5 / 3.5 land, they will either delete the placeholders or rename them to the canonical names.
- File names are kebab-case, mirroring their primary export (e.g., `login-view.ts` exports `LoginView`). Component selectors are `app-` + kebab-case (e.g., `<app-login-view>`, `<app-top-chrome>`, `<app-book-list-page-placeholder>`, `<app-settings-page-placeholder>`). All enforced by the ESLint rules from Story 1.8's `eslint.config.js`.
- No barrel files (`index.ts` re-exports). Each consumer imports directly from the target file. (`shared/chrome/top-chrome.ts` is imported by `app.ts`, `book-list-page-placeholder.ts`, `settings-page-placeholder.ts` — three consumers; still below the 4-consumer threshold the architecture sets for barrels.)
- Tests colocated — `login-view.spec.ts` next to `login-view.ts`, etc.
- No `.css` for placeholders (the placeholders are too thin to warrant per-component styles).

### Out-of-scope reminders (project-wide)

- **No accessibility hardening.** No ARIA labels, no focus traps, no skip links, no contrast audits, no screen-reader testing. UX §"Accessibility Considerations" lines 330–340 (and the auto-memory `project_bmad_books_scope`) explicitly exclude all of these from scope.
- **No responsive design.** No media queries, no breakpoints, no mobile-friendly variants. Desktop-only per PRD.
- **No animations.** No transitions, no fades, no hover-grow effects. UX §"Design Direction Decision / Chosen Direction" (line 359) explicitly excludes animations.
- **No backend changes.** This is a SPA-only story. The BFF endpoints (`/auth/login`, `/auth/logout`, `/api/me`) are owned by Stories 1.5 and 1.7 (already done).
- **No Python changes.** The `python` (not `python3`) convention from `CLAUDE.md` does not apply because this story is entirely TypeScript/HTML/CSS.
- **The backend archetype constraint (`fastapi-archetype` for BFF/RS)** does not apply because this story does not touch BFF or RS code.

### Deferred issues acknowledged but not resolved here

- **D10 — Dev proxy glob `/auth/*`, `/api/*`, `/v1/*`** (from `_bmad-output/implementation-artifacts/deferred-work.md`): `TopChrome.onLogoutClick` calls `POST /auth/logout` and `provideAppInitializer` calls `GET /api/me`. Both are single-segment paths under their respective globs (`/auth/logout` matches `/auth/*`; `/api/me` matches `/api/*`), so the proxy is fine for this story's runtime needs. The deferral stays — Story 1.13 (Playwright + live BFF) will be the first to exercise multi-segment paths and may need to broaden the glob.
- **D11 — Smoke-fragment test only asserts class names**: superseded by this story (the smoke fragment is deleted; the new `app.spec.ts` test asserts actual component rendering).
- **All D14–D44** are BFF/RS issues — none affect SPA code paths in this story.

### Testing standards for this story

Per architecture §"Testing patterns" lines 790–796:

- **Vitest + Angular `TestBed`.** Use `provideHttpClientTesting()` (functional, v21-blessed) — Story 1.9's pattern.
- **Components tested with HTTP mocked via `HttpTestingController`, signals asserted via their getter (`me()`).** Do NOT use `vi.fn()` to mock `HttpClient` itself.
- **Co-located:** every `.ts` has a `.spec.ts` next to it (except `.html` and `.css`).
- **Coverage ≥70% per-folder** for the new folders (`login/`, `shared/chrome/`, `books/`, `settings/`). The simple components naturally hit ≥90% with the spec coverage described in the tasks.

For mocking `AuthService` in component tests: provide a plain object with the shape `{ me: WritableSignal<Me | null>, clear: vi.fn(), setMe: vi.fn(), loadMe: vi.fn().mockResolvedValue(undefined) }`. Use `TestBed.configureTestingModule({ providers: [{ provide: AuthService, useValue: mock }] })` to inject the mock. **Do NOT** test the real `AuthService` indirectly from these component tests — Story 1.9 covers it; this story tests components in isolation.

For mocking `Router.url` and `Router.events`: the cleanest pattern is to use the real `provideRouter([])` (or `provideRouter([{ path: '**', component: SomeStub }])`) and call `await router.navigateByUrl('/books')` to set the URL state. This exercises the real `Router.events` stream and is more faithful than mocking. The `TopChrome.currentUrl` signal will pick up the navigation via the test Router's microtask queue.

### Forward-context for downstream stories (do not implement here)

Locked in this story so later stories can rely on them:

- **`app.routes.ts` has a 5-entry table.** Story 2.5 will replace `BookListPagePlaceholder` with `BookListPage`; Story 3.5 will replace `SettingsPagePlaceholder` with `SettingsPage`. Both stories will:
  1. Create the real component.
  2. Update the corresponding `loadComponent: () => import('./...').then(m => m.X)` import path.
  3. Delete (or supersede) the placeholder file.
- **`TopChrome` is rendered ONCE in `app.html`.** Stories 2.5 / 3.5 do NOT add `<app-top-chrome />` to their templates — the centralized rendering handles them.
- **`provideAppInitializer(() => inject(AuthService).loadMe())`** sets `AuthService.me` before any route activates. Components/services that need `me()` can read it synchronously after bootstrap.
- **`POST /auth/logout` is fired from `TopChrome.onLogoutClick`.** Stories that need to log out programmatically (none planned) should call `TopChrome`'s method indirectly via emitting a router navigation to `/login` after their own cleanup — they should NOT duplicate the `HttpClient.post('/auth/logout', null)` call.
- **The `?error=auth` query param** is the BFF's signal of a failed token exchange (Story 1.5's `/auth/callback` redirects to `/login?error=auth` on token-exchange failure). `LoginView` reads this param and renders the inline error message; no other component handles `?error=auth`.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.10: SPA LoginView + TopChrome + route table` lines 563–617] — canonical story spec + ACs.
- [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements — AR21, AR22, AR23, AR16` lines 81–83] — frontend state mgmt, interceptor, routing/guard contracts, wire-model parity.
- [Source: `_bmad-output/planning-artifacts/epics.md#UX Design Requirements — UX-DR2, UX-DR3, UX-DR12, UX-DR20` lines 104, 105, 114, 127] — TopChrome, LoginView, failure copy, implementation order.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Frontend Architecture — F1–F5` lines 422–459] — state, interceptors, serving, guards, the exact 5-entry route table.
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns — C2` line 367, line 680] — `POST /auth/logout` returns 204; `GET /api/me` returns `{sub, preferred_username}` or 401.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Naming Patterns / TypeScript / Angular code` lines 573–582] — file naming, selector convention, exports.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Communication Patterns — State management (SPA)` lines 705–711] — signal write paths, immutable updates.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Testing patterns` lines 790–796] — Vitest + TestBed + `HttpTestingController` + signal-getter assertions.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Enforcement Guidelines` lines 797–815] — signal-only state, no parallel store, no empty catch, no `console.log`, ESLint enforcement.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` lines 1018–1090] — exact target paths.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#Visual Design Foundation` lines 257–328] — design tokens, color rules, type scale, spacing.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#Component Strategy — TopChrome, LoginView` lines 588–600] — anatomies + interaction behaviors.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#J1. First-time login` lines 377–414] — the sequence diagram showing how `LoginView` + `/auth/login` + Keycloak + `/api/me` + `TopChrome` fit together.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#J5. Logout and re-protection` lines 509–538] — the sequence diagram for `POST /auth/logout` + `AuthService.clear()` + nav to `/login`.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#Accessibility Considerations` lines 330–340] — explicit out-of-scope statement for accessibility.
- [Source: `_bmad-output/implementation-artifacts/1-8-spa-scaffold-tailwind-v4-design-tokens.md`] — Tailwind v4 + UX-DR1 token scaffold; the utilities this story consumes.
- [Source: `_bmad-output/implementation-artifacts/1-9-spa-authservice-interceptors-functional-guards.md`] — `AuthService`, interceptors, functional guards; the plumbing this story sits on top of.
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md`] — D10 (proxy glob), D11 (smoke-fragment test) — both acknowledged in Dev Notes.
- [Source: `CLAUDE.md` at repo root] — `python` not `python3` convention (not invoked in this story).
- Memory: `project_bmad_books_scope` — accessibility AND responsive design are out of scope; do not pad templates with ARIA or media queries.
- Memory: `project_bmad_books_backend_archetype` — does not affect SPA; recorded for completeness.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code, bmad-dev-story workflow)

### Debug Log References

### Completion Notes List

### File List
