---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/PRD.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
---

# BMAD_books - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for BMAD_books (Reading Time Estimator), decomposing the requirements from the PRD, UX Design Specification, and Architecture document into implementable stories.

## Requirements Inventory

### Functional Requirements

- **FR1 (FR-AUTH-01):** Users can authenticate via the authorization server (Keycloak) and obtain a browser session managed by the BFF, using the Authorization Code flow authenticated by the BFF's confidential `client_secret`. The SPA never sees credentials or tokens; the login is initiated from a single button on `/login`. *Source journey: J1.*
- **FR2 (FR-BOOK-01):** Users can perform full CRUD operations on their personal book list. A book consists of a title (text), a page count (positive integer), and a reading status (`to-read` | `reading` | `finished`). Books are owned by the BFF, keyed by the `sub` claim. *Source journey: J2.*
- **FR3 (FR-SPEED-01):** Users can view and update a personal reading speed (pages-per-hour, positive integer) stored on the Resource Server, keyed by `sub`. The view at `/settings` shows the current value (or empty if unset) and persists changes via an explicit "Save" action. *Source journey: J4.*
- **FR4 (FR-ESTIMATE-01):** Users can request a reading-time estimate for any book in their list. The estimate is computed by the Resource Server from the user's reading speed and the book's page count, returned as both `minutes` (integer) and a formatted string (e.g., "≈ 4 h 20 m"). *Source journey: J3.*
- **FR5 (FR-LOGOUT-01):** Users can log out from a persistent control in the top chrome, terminating both the browser session and the refresh token at the authorization server. After logout, attempting to access protected views redirects back to login. *Source journey: J5.*
- **FR6 (FR-ERROR-01):** When the Resource Server is unavailable, the SPA renders a distinct, named error state ("Service unavailable — try again shortly") at the site of the action; the BFF surfaces a 503 with `errorCode: resource_server_unavailable` rather than fabricating a result. *Source journey: J6.*

### NonFunctional Requirements

- **NFR1 — Token isolation:** Access and refresh tokens must never be transmitted to, stored in, or accessible from the SPA or any browser-accessible storage.
- **NFR2 — BFF as confidential OAuth client:** The BFF is the OAuth client. Login uses the Authorization Code flow; the BFF authenticates to the AS with `client_secret_basic`. PKCE is intentionally not used (confidential client). The BFF holds tokens server-side, keyed by session.
- **NFR3 — Transparent token refresh:** The BFF refreshes expired access tokens using the refresh token and retries the in-flight request once, without involving the SPA.
- **NFR4 — Stateless Resource Server:** The Resource Server maintains no session state, shares no database with the BFF, and authenticates every request solely by the JWT it carries.
- **NFR5 — JWKS-based JWT validation:** The Resource Server validates JWTs by fetching and caching the authorization server's JWKS. Public keys are not hardcoded.
- **NFR6 — Identity source of truth:** No service other than the authorization server stores user account records. User-owned data on the BFF and Resource Server is keyed by the `sub` claim.
- **NFR7 — Scope-enforced computation:** Access to the Resource Server's endpoints is gated by OAuth scopes — `reading-speed:read` for retrieving the reading speed and computing estimates, `reading-speed:write` for modifying the reading speed. Scope enforcement happens at the Resource Server, not at the BFF.
- **NFR8 — No BFF bypass of the Resource Server:** When the Resource Server is unavailable, the BFF surfaces an error rather than computing a fallback locally.
- **NFR9 — Reproducible authorization server configuration:** The Keycloak realm, clients, and scopes are version-controlled and imported at container startup. No manual configuration after `docker-compose up`.
- **NFR10 — Containerized deployment:** Every component (SPA, BFF, RS, Keycloak, databases) runs in Docker. The full system is brought up by `docker-compose up` with no further setup. Health checks gate inter-service dependency ordering.
- **NFR11 — Test coverage:** ≥70% meaningful code coverage across services (the backend archetype targets >90% by default). At least 5 end-to-end tests covering primary user journeys J1–J6, with the OAuth flow exercised end-to-end (not mocked).
- **NFR12 — Security posture:** A documented security review covering at minimum token storage and transport, session cookie attributes, CSRF posture, JWT validation correctness, scope enforcement, and standard SPA concerns (XSS, injection). At-rest token storage in the BFF SQLite file is an accepted risk that must be explicitly called out.
- **NFR13 — Environment configuration:** Development and test configurations are selectable via environment variables and compose profiles. Secrets are not committed; a single `.env.example` at repo root documents all required vars.

### Additional Requirements

**Backend archetype & stack (locked by user mandate):**

- **AR1 — Backend archetype:** Both the BFF and the Resource Server MUST be scaffolded from `github.com/tommaso-meledina/fastapi-archetype` (Python 3.14 + FastAPI + SQLModel + uv + Ruff + ty + pytest). The archetype is cloned into `tools/fastapi-archetype/` (gitignored) and `scripts/build_template.py` is used to scaffold each service. The archetype's OTEL/Prometheus wiring, if scaffolded into the output, is treated as inert — BMAD_books does not deploy a collector or dashboards (see NFR10 / PRD §12).
- **AR2 — BFF cookie-session OIDC plugin:** A new archetype auth plugin (`keycloak_cookie_session.py`) on the BFF implements the Authorization Code flow using Authlib (async/httpx integration), alongside the archetype's existing `none`/`entra` modes. The BFF authenticates to Keycloak's `/token` endpoint with `client_secret_basic`; PKCE is not used (confidential client). The BFF requests scopes `openid reading-speed:read reading-speed:write` at `/authorize`.
- **AR3 — Resource Server OIDC bearer plugin:** Generalize the archetype's `entra` mode into a `keycloak`/`oidc_bearer` mode using PyJWT (`pyjwt[crypto]`) + `PyJWKClient`, parameterized for Keycloak (issuer, JWKS URL, audience). Scope enforcement uses the archetype's `RoleMappingProvider` extension point.

**Frontend stack:**

- **AR4 — SPA framework:** Angular v21 (zoneless change detection by default; signals + computed/effect; standalone components — no NgModule; new `@if`/`@for`/`@switch` control flow; `inject()` over constructor DI; `input()`/`output()` signal-based component IO; Vitest test runner replacing Karma/Jasmine). Scaffolded via `npx -p @angular/cli@21 ng new spa --routing --style=css --ssr=false --skip-git --package-manager=npm --strict`.
- **AR5 — Styling:** Tailwind CSS v4 via `@tailwindcss/postcss` with CSS-first config (no `tailwind.config.js`). Design tokens declared in `spa/src/styles.css` under Tailwind's `@theme` block.

**Data architecture:**

- **AR6 — Database engines:** SQLite (file-backed, WAL mode) for both BFF and RS, in separate files in separate named Docker volumes (`bff_data`, `rs_data`) mounted at `/data`. The PRD's "no shared DB" boundary is preserved because each service owns its own file. Alembic migrations run on container startup before uvicorn boots (`uv run alembic upgrade head && exec uv run uvicorn …`).
- **AR7 — BFF schema:** Three tables — `books` (CRUD per user, keyed by `sub`), `sessions` (server-side session store: `sub`, `access_token`, `refresh_token`, `id_token`, `expires_at`, `csrf_secret`, `created_at`), `auth_states` (OAuth state: `state`, `nonce`, `return_to`, `expires_at`; legacy `code_verifier` column survives as nullable dead schema after the PKCE removal). Indexes on `books.sub`, `auth_states.expires_at`, `sessions.expires_at`.
- **AR8 — RS schema:** Single `reading_speeds` table keyed by `sub` (indexed), with `pages_per_hour`, `created_at`, `updated_at`.

**Auth, session, and security:**

- **AR9 — OAuth state/nonce storage:** Server-side `auth_states` row holds `state`, `nonce`, `return_to`; a short-lived signed state-id cookie carries the row id (`HttpOnly`, `Max-Age=300`). Row is deleted on callback. `state` defends against CSRF on the callback; `nonce` defends against id_token replay.
- **AR10 — Session cookie attributes:** `HttpOnly; Secure (prod); SameSite=Lax; Path=/; opaque 256-bit value` (not a JWT).
- **AR11 — CSRF strategy:** Double-submit cookie (non-HttpOnly `csrf_token`) + `X-CSRF-Token` header on state-changing requests + Origin/Referer check as defense in depth. BFF middleware validates header == cookie.
- **AR12 — Token refresh strategy:** Reactive — on 401 from RS, BFF refreshes via Keycloak token endpoint and retries the in-flight request exactly once. Persisted failure → 401 to SPA → SPA navigates to `/login?return_to=…`.
- **AR13 — Logout flow:** Revoke refresh token → call `end_session_endpoint` → clear local session row → clear cookie. If revocation fails, BFF still clears local session and returns 204 (no half-logged-out states).
- **AR14 — CSP header:** BFF emits `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'` as a response header on SPA-serving routes.

**API contracts & inter-service communication:**

- **AR15 — API path layout:** Non-versioned (mechanics): `/auth/login`, `/auth/callback`, `/auth/logout`, `/api/me`, `/health`, `/docs`, `/redoc`. Versioned (domain APIs): `/v1/books`, `/v1/books/{id}`, `/v1/books/{id}/estimate` on BFF; `/v1/reading-speed`, `/v1/estimate` on RS. BFF also exposes `GET/PUT /v1/reading-speed` as a thin same-origin proxy to RS.
- **AR16 — JSON contract:** Field names `snake_case` in both directions (no case-conversion layer). Success returns the resource directly (no wrapper); collections return a plain JSON array. Failure returns the archetype envelope `{errorCode, message, detail}`. Empty 204 responses have no body. Date/time ISO 8601 UTC with `Z`.
- **AR17 — ErrorCode enum extensions:** Each service extends the archetype's `ErrorCode` enum with the values: `RESOURCE_SERVER_UNAVAILABLE` (503), `READING_SPEED_UNSET` (412), `SESSION_EXPIRED` (401), `FORBIDDEN_SCOPE` (403), `INVALID_INPUT` (422), `BOOK_NOT_FOUND` (404), `AUTH_STATE_INVALID` (400), `CSRF_INVALID` (403).
- **AR18 — Inter-service auth:** BFF includes `Authorization: Bearer <user_access_token>` on every RS call via a single `ResourceServerClient` class. BFF never injects user identity into the body or path; RS reads `sub` from JWT only. Single 401-→-refresh-→-replay cycle.
- **AR19 — Timeouts:** BFF→RS: 5s connect / 10s read; zero retries on 5xx (per FR-ERROR-01). BFF→Keycloak: 5s/10s; no retries on token endpoint. RS→Keycloak JWKS: 5s timeout, in-process cache TTL 24h, key-rotation on `kid` miss (single re-fetch).
- **AR20 — Pydantic boundary models:** Distinct API models (`BookCreate`, `BookUpdate`, `BookOut`, `EstimateOut`, `ReadingSpeedOut`), not SQLModel ORM classes serialized directly.

**Frontend architecture patterns:**

- **AR21 — State management:** Signals + per-feature services. No global store, no NgRx, no BehaviorSubjects-as-state. `AuthService` (me/logout), `BooksService` (books signal + CRUD), `ReadingSpeedService` (pagesPerHour signal + get/set), `ErrorService` (parses error envelope into typed `AppError` discriminated union).
- **AR22 — HTTP interceptors:** Two interceptors registered via `provideHttpClient(withFetch())` — `withCredentialsInterceptor` (sets `withCredentials: true` so the session cookie is sent), `csrfInterceptor` (reads `csrf_token` cookie, sets `X-CSRF-Token` on POST/PUT/PATCH/DELETE). Global handling of 401: navigate to `/login?return_to=…`.
- **AR23 — Routing & guards:** Functional router config in `app.config.ts`. Routes: `/login`, `/books`, `/settings` (plus `''` → `books`, `**` → `books`). Functional `authGuard` on `/books` and `/settings` calls `GET /api/me` (with `withCredentials: true`) and redirects to `/login` on 401. Inverse `redirectIfAuthedGuard` on `/login` bounces to `/books` if already authenticated.
- **AR24 — SPA serving model:** Same-origin via BFF. In prod, BFF's multi-stage Dockerfile compiles SPA in a Node stage and copies `dist/spa/browser` into the BFF image; BFF mounts it at `/` with HTML5 history fallback (catch-all serves `index.html` only for `Accept: text/html`). In dev, `ng serve` on `:4200` with `proxy.conf.json` forwarding `/auth/*`, `/api/*`, `/v1/*` to BFF on `:8000`.

**Infrastructure & deployment:**

- **AR25 — Repository structure:** Monorepo with `spa/`, `services/bff/`, `services/resource-server/`, `keycloak/`, `e2e/`, `compose/`, `tools/`, top-level `docker-compose.yml`, `.env.example`, `README.md`, `CLAUDE.md`.
- **AR26 — Compose composition:** Top-level `docker-compose.yml` uses Compose `include:` (v2.20+) to pull in `compose/infra.yml` (Keycloak) and `compose/app.yml` (BFF, RS, SPA in prod). Three profiles: `default` (full stack), `dev` (excludes SPA — `ng serve` runs on host), `e2e` (adds Playwright runner that depends on all healthchecks).
- **AR27 — Keycloak realm-as-code:** `keycloak/realm-bmad-books.json` defines: realm `bmad-books`; confidential client `bmad-books-bff` with Authorization Code enabled (no PKCE), `client_secret` from env; redirect URIs `http://localhost:8000/auth/callback` (+ configurable prod URL); client scopes `reading-speed:read` / `reading-speed:write` as `optional` granted to the BFF client by default; audience claim `bmad-books-resource-server` mapped onto the access token (so RS validates `aud`). Two pre-seeded users: `testuser`/`testpassword` (default reading speed seeded by first PUT or by test), `freshuser`/`freshpassword` (no reading speed — exercises the 412 precondition path in J3).
- **AR28 — Health checks & startup ordering:** Each container exposes a health probe; compose uses `depends_on: { condition: service_healthy }`. Keycloak: `/health/ready` after realm import. BFF: `GET /health` returns 200 once DB is reachable, Alembic at head, and the OIDC discovery doc is fetchable; depends on Keycloak. RS: `GET /health` returns 200 once DB reachable, Alembic at head, and JWKS fetchable; depends on Keycloak.
- **AR29 — Environment variables:** Single `.env.example` at repo root documenting all required vars (`KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`, `BFF_DATABASE_URL`, `RS_DATABASE_URL`, `BFF_BASE_URL`, `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `OIDC_CLIENT_ID`, `BFF_SESSION_COOKIE_NAME`, `BFF_CSRF_COOKIE_NAME`, `BFF_SESSION_COOKIE_SECURE`, `ENABLE_TEST_RESET`, `TEST_RESET_TOKEN`); per-service `.env` files gitignored; compose `env_file:` per service.

**Testing:**

- **AR31 — E2E framework:** Playwright in a separate `e2e/` npm project; one spec file per PRD journey (`j1-first-login.spec.ts`, `j2-manage-books.spec.ts`, `j3-estimate.spec.ts`, `j4-adjust-speed.spec.ts`, `j5-logout.spec.ts`, `j6-rs-unavailable.spec.ts`). Real Keycloak login (no mocks). Fixtures provide `logInAs(page, "testuser")`, `resetState()`, `killRs()` helpers.
- **AR32 — Test reset endpoint:** `POST /v1/test/reset` on BFF (truncates `books`, `sessions`, `auth_states`) and RS (truncates `reading_speeds`). Available only when `ENABLE_TEST_RESET=true`; requires shared bearer from `TEST_RESET_TOKEN`. Returns 204. Production builds do not register the route.
- **AR33 — Backend test patterns:** pytest (async); tests mirror `src/<svc>/` directory structure. Unit tests use in-memory SQLite + a `TestClient`. Auth tests use a synthetic IdP (test-generated RSA keypair, monkey-patched HTTP) extended for `oidc-bearer` mode. No mocking of internal layers in integration tests.
- **AR34 — Frontend test patterns:** Vitest + Angular TestBed. Components tested with `HttpTestingController` and signal assertions. Services tested against `HttpTestingController`. Spec files colocated next to source (`book-row.spec.ts` next to `book-row.ts`).

### UX Design Requirements

- **UX-DR1 — Design tokens:** Color tokens (`--color-surface` `#FFFFFF`, `--color-surface-muted` `#F5F5F5`, `--color-border` `#E5E5E5`, `--color-text` `#111111`, `--color-text-muted` `#666666`, `--color-accent` `#2563EB`, `--color-accent-hover` `#1D4ED8`, `--color-error` `#B91C1C`); type scale (`--text-page-title` 24/32 600, `--text-section` 18/24 600, `--text-body` 14/20 400, `--text-small` 12/16 400) with system-font stack only (no webfonts); spacing scale on a 4px base (`--space-1` 4, `--space-2` 8, `--space-3` 12, `--space-4` 16, `--space-6` 24, `--space-8` 32). Declared in `spa/src/styles.css` under Tailwind v4's `@theme` block. Single light mode only — no dark mode, no theming, no brand customization layer.
- **UX-DR2 — TopChrome component:** Persistent ~48px header on every authenticated view. Product name on left in `--text-page-title` weight; identity block on right rendering `Signed in as <preferred_username>` followed by `·` separator and a "Log out" text button. Between product name and identity, a contextual route link: `Settings` link when on `/books`; `Books` link when on `/settings`. Variants: authenticated (full chrome) and unauthenticated (product name only).
- **UX-DR3 — LoginView component:** Centered single-purpose view at `/login`. Contents: short headline ("Sign in to Reading Time Estimator"), one paragraph of copy ("You'll be redirected to authenticate, then returned here."), one "Log in" button (primary). Inline error message above the button when `?error=auth` is in URL ("Login didn't complete — try again."). Clicking "Log in" navigates the browser to `/auth/login`.
- **UX-DR4 — BookForm component:** Three stacked inputs: title (text input), page count (number input, min 1), status (StatusControl, default `to-read`). Submit row with primary button ("Add book" or "Save") and (in edit mode only) secondary text "Cancel" button. Two variants: `add` (permanent at top of `/books`, clears on success) and `edit` (temporarily replaces a row, dismisses on success). Submitting state relabels button to "Adding…"/"Saving…" + disables. Validation runs on submit (required fields + positive integer page count); on failure, fields preserve values and an inline error renders below the form.
- **UX-DR5 — BookList component:** Container with section heading "Books" (`--text-page-title`). Renders one of: (a) loading state — single `--text-small` `--color-text-muted` "Loading…" line during initial fetch; (b) empty state post-load — "No books yet. Add one above." (no illustration, no CTA button); (c) populated — vertical stack of `BookRow` instances separated by 1px borders; (d) load-error — inline "Couldn't load books — refresh to try again."
- **UX-DR6 — BookRow component:** Flex row containing title (left, primary text), page count (`<n> pages` in muted), `StatusControl`, `EstimateCell`, and a secondary action group with text buttons "Edit" and "Delete". Hover state uses `--color-surface-muted`. Edit toggles the row into a `BookForm[variant=edit]`. Delete fires native `confirm()` then DELETE; row is removed on 2xx, preserved with inline error on failure. Status changes are optimistic (see UX-DR7). A row-level inline error renders below normal row content on action failures.
- **UX-DR7 — StatusControl component:** Native `<select>` (or equivalent three-button segmented control built from `<button>`s) for values `to-read` / `reading` / `finished`. Change fires PATCH `/api/books/:id` with **optimistic UI update** (the only optimistic path in the app). On failure, control reverts to prior value and a row-level error renders below. Disabled during in-flight PATCH.
- **UX-DR8 — EstimateCell component:** Right-most cell of `BookRow`. Holds one of four mutually exclusive contents at a time: (1) idle — "Estimate" button (primary); (2) loading — "Estimating…" disabled button; (3) success — formatted duration text (`≈ 4 h 20 m`, `≈ 12 m`, `≈ 1 d 2 h` for very long books) plus a small "Re-estimate" affordance; (4) error — `ErrorMessage` with one of the failure copy variants (precondition 412, service-unavailable 503, generic). Failure cases restore the button beneath the error for retry. Pessimistic UI — no optimistic updates here.
- **UX-DR9 — SettingsView component:** Single view at `/settings`. Section heading "Reading speed" (`--text-page-title`). One labelled number input ("Pages per hour", helper text "e.g., 30") and one primary button ("Save"). Save success briefly relabels button to "Saved" for ~1s, then back to "Save". States: loading (initial GET), loaded with value, loaded empty (no value yet — helper text is the primary cue), saving, saved, validation-error (inline under input), load-error/save-error including J6 (inline under input in `--color-error`). Validation on submit: positive integer.
- **UX-DR10 — ErrorMessage component:** Stateless single-line inline component in `--text-small` `--color-error`. Optionally takes a trailing inline link (e.g., "Settings" linking to `/settings`). Reused by BookRow, EstimateCell, BookForm, BookList, SettingsView.
- **UX-DR11 — Feedback & loading conventions:** No success toasts anywhere. The only success acknowledgement permitted is `SettingsView`'s "Saved" button relabel. All failures render inline at the site of the action (no global toast, no banner, no notification center). Loading is local: button relabel + disable for actions; single `--text-small` `--color-text-muted` "Loading…" line for view-level fetches. No spinners, no skeleton loaders, no global progress.
- **UX-DR12 — Failure copy strings (named, specific):**
  - J6 (503 / resource-server-unavailable): `"Service unavailable — try again shortly"`
  - Generic estimate failure: `"Couldn't get an estimate — try again"`
  - 412 precondition (no reading speed): `"Set your reading speed in Settings to enable estimates"` (with "Settings" as link to `/settings`)
  - Auth round-trip failure: `"Login didn't complete — try again"`
  - Book list load failure: `"Couldn't load books — refresh to try again."`
- **UX-DR13 — Optimistic vs pessimistic UI rule:** Optimistic UI is permitted **only** for book status PATCH (same-service, low-stakes, BFF-only). All cross-service interactions (estimate, reading-speed read/save) are pessimistic — button stays disabled until the round-trip completes; failure reverts and renders inline error.
- **UX-DR14 — Button hierarchy:** Exactly one primary action per surface, rendered in `--color-accent`. Secondary actions render as plain text buttons (`Edit`, `Delete`, `Cancel`) with underline-on-hover and no surrounding fill. Destructive actions are **not** red — confirmation comes via native `confirm()`. Disabled state is 50% opacity of the active style. No icon-only buttons.
- **UX-DR15 — Form patterns:** Native HTML controls only (no icon library, no UI component library). Validation runs on submit, not on blur. Required fields required; positive integers must be positive integers; no validation of title length, character sets, or "reasonable" page counts. Inputs preserve values on submit failure. Every input has a `<label>`. Helper text in `--text-small` `--color-text-muted`.
- **UX-DR16 — Layout structure:** Single centered content column with max-width `720px`, horizontal padding `--space-4`, vertical padding `--space-8`. Top chrome ~48px full-width bar with mirrored horizontal padding. No multi-column layouts, no sidebars, no breadcrumbs, no tabs, no left-rail navigation, no hamburger menu.
- **UX-DR17 — No modals or overlays:** Confirmation for destructive actions uses the native browser `confirm()` dialog. No in-app modal component, no slide-over panel, no dialog system.
- **UX-DR18 — Duration formatting:** Reading-time durations rendered using the `formatted` string from the RS response (e.g., `≈ 4 h 20 m`, `≈ 12 m`, `≈ 1 d 2 h`). RS returns `{ minutes: int, formatted: string }`; SPA displays `formatted` directly. No raw minutes, no decimal hours, no unannotated numbers.
- **UX-DR19 — No animations or transitions:** No fade-ins, no slide-overs, no route transition animations. State changes are instantaneous. No motion design beyond functional state transitions inherent to native HTML controls.
- **UX-DR20 — Component implementation order:** Suggested order matching journey dependencies — (1) TopChrome + LoginView (unblocks J1/J5 testing); (2) BookList + BookRow + BookForm + StatusControl + ErrorMessage (J2); (3) EstimateCell (J3); (4) SettingsView (J4); (5) J6 refinement across EstimateCell and SettingsView.

### FR Coverage Map

- **FR1 (FR-AUTH-01)** → Epic 1 — OIDC login + BFF-managed session (paired with logout for the full auth lifecycle)
- **FR2 (FR-BOOK-01)** → Epic 2 — Book CRUD owned by the BFF
- **FR3 (FR-SPEED-01)** → Epic 3 — Reading speed on the Resource Server; introduces the JWT + scope cross-service path
- **FR4 (FR-ESTIMATE-01)** → Epic 4 — The defining cross-service estimate interaction
- **FR5 (FR-LOGOUT-01)** → Epic 1 — Logout + Keycloak revocation (paired with login)
- **FR6 (FR-ERROR-01)** → Epic 4 — Honest J6 failure surface, rendered in the same `EstimateCell` as the J3 success path

## Epic List

### Epic 1: Foundational Login & Identity (J1, J5)

**User outcome:** A user can `docker compose up`, navigate to the SPA, click "Log in", complete a real Keycloak OIDC round-trip, return signed in with their identity in the top chrome on a (placeholder) `/books` view, and click "Log out" to return to an unauthenticated state. Attempting to reach a protected route while unauthenticated bounces to `/login`. The refresh token is revoked at Keycloak on logout.

**FRs covered:** FR1, FR5

**Scope:**

- Monorepo scaffold (compose skeleton, top-level `docker-compose.yml` with `include:`, `.env.example`, gitignore, README stub).
- BFF scaffolded from `fastapi-archetype` (RS scaffold deferred to Epic 3 where it gets its first real endpoint).
- SPA scaffolded with Angular v21 + Tailwind v4 (design tokens declared under Tailwind's `@theme` block per UX-DR1).
- Keycloak realm-as-code with the `bmad-books-bff` client, scopes (`reading-speed:read`, `reading-speed:write`), audience claim, and the two pre-seeded users (`testuser`, `freshuser`).
- BFF: cookie-session OIDC plugin (Authlib, `client_secret_basic`), `sessions` + `auth_states` tables with Alembic migration, CSRF middleware (double-submit + `X-CSRF-Token` + Origin/Referer check), CSP response-header middleware, `/auth/login`, `/auth/callback`, `/auth/logout`, `/api/me` endpoints, synthetic-IdP test harness extended for Keycloak.
- SPA: `TopChrome` (authenticated + unauthenticated variants), `LoginView`, baseline `ErrorMessage`, `withCredentialsInterceptor` + `csrfInterceptor`, functional `authGuard` + `redirectIfAuthedGuard`, `AuthService`, baseline `ErrorService` parsing the archetype envelope, route table with `/login` + `/books` (placeholder) + `/settings` (placeholder).
- **QA harness from day one:** Playwright project (`e2e/`) with `playwright.config.ts`, fixtures (`logInAs`, `resetState`, `killRs` stub), `e2e` compose profile with a Playwright runner depending on healthchecks; BFF `POST /v1/test/reset` (ENABLE_TEST_RESET-gated, TEST_RESET_TOKEN-protected); J1 + J5 Playwright E2E specs running against real Keycloak.
- Compose `dev`, `default`, and `e2e` profiles wired up through Keycloak + BFF + SPA, with health-check-gated startup ordering.

### Epic 2: Personal Book List (J2)

**User outcome:** A signed-in user can see their book list, add books, advance reading status (to-read → reading → finished) directly from a row, edit a book inline, and delete a book (with native `confirm()`). All failures render inline at the action site; book-status changes are optimistic.

**FRs covered:** FR2

**Scope:**

- BFF: `Book` SQLModel + Alembic migration, `BookCreate` / `BookUpdate` / `BookOut` Pydantic models, `books_service` business logic, `BookNotFoundError` + `InvalidInputError` domain exceptions wired to the archetype error envelope, full CRUD endpoints at `/v1/books` and `/v1/books/{id}`.
- BFF: extend `POST /v1/test/reset` to truncate the new `books` table.
- SPA: `BookList`, `BookRow`, `BookForm` (add + edit variants), `StatusControl`, `BooksService` with the books signal + CRUD methods (including optimistic UI for status PATCH), `/books` route fully rendering the book domain.
- **J2 Playwright E2E spec** (`e2e/tests/j2-manage-books.spec.ts`) — covers add, status change with optimistic UI + revert on failure, edit, delete-with-confirm, inline-error rendering on failures.

### Epic 3: Reading Speed Settings (J4)

**User outcome:** A signed-in user can navigate to `/settings`, view their reading speed (or an empty input if unset), update it, and persist the change via Save. Updates exercise the `reading-speed:write` scope; reads exercise `reading-speed:read`.

**FRs covered:** FR3

**Scope:**

- Resource Server: **scaffolded from the archetype** (deferred from Epic 1), `oidc_bearer` auth plugin (PyJWT + `PyJWKClient`, parameterized for Keycloak issuer/JWKS/audience), scope enforcement via the archetype's `RoleMappingProvider`, `ReadingSpeed` SQLModel + Alembic migration, `reading_speed_service`, `/v1/reading-speed` GET + PUT (scope-gated), synthetic-IdP test harness for the RS (test-generated RSA keypair + monkey-patched JWKS).
- Resource Server: `POST /v1/test/reset` endpoint truncating `reading_speeds`.
- BFF: `ResourceServerClient` (bearer-forwarding HTTP client with the documented 5s/10s timeouts), `/v1/reading-speed` GET/PUT proxy router, `ErrorCode` extensions for `RESOURCE_SERVER_UNAVAILABLE` and `FORBIDDEN_SCOPE`, error-handler mapping for the 503 settings path.
- SPA: `SettingsView` + `/settings` route, `ReadingSpeedService`, `TopChrome` contextual route-toggle link (Settings ↔ Books).
- Compose: `default` and `e2e` profiles updated to bring up the RS with health-check-gated dependency on Keycloak; `resetState` helper extended to also reset the RS.
- **J4 Playwright E2E spec** (`e2e/tests/j4-adjust-speed.spec.ts`) — real `reading-speed:write` scope exercised end-to-end.

### Epic 4: Reading-Time Estimate & Honest Failure (J3, J6)

**User outcome:** A signed-in user can click "Estimate" on any book row and see a formatted duration (`≈ 4 h 20 m`) appear in the row. Updating reading speed in Settings and re-running the estimate yields a different number. When the Resource Server is unavailable, the user sees a distinct, named failure state ("Service unavailable — try again shortly") in the same cell — never a fabricated number, never a generic error.

**FRs covered:** FR4, FR6

**Scope:**

- Resource Server: `/v1/estimate` POST endpoint (scope-gated `reading-speed:read`), `estimate_service` (reads reading-speed by `sub`, computes minutes, formats the duration string), `EstimateOut` model returning `{ minutes, formatted }`.
- BFF: `/v1/books/{id}/estimate` endpoint, `ResourceServerClient.compute_estimate` method and the single 401-→-refresh-→-replay cycle on RS, `ResourceServerUnavailableError` + `ReadingSpeedUnsetError` mapping to 503/412.
- SPA: `EstimateCell` component (all four states — idle, loading, success with re-estimate, three error variants), `AppError` discriminated union extended with `resource_server_unavailable` + `reading_speed_unset`, BookRow integration of the cell.
- **J3 Playwright E2E spec** (`e2e/tests/j3-estimate.spec.ts`) — real cross-service estimate exercised, including the J4-driven "speed changes, estimate changes" assertion.
- **J6 Playwright E2E spec** (`e2e/tests/j6-rs-unavailable.spec.ts`) — uses the now-implemented `killRs()` helper to take down the RS container and asserts the named error renders in `EstimateCell` and `SettingsView`.

### Epic 5: End-to-End Verification & Security Review

**User outcome:** A reviewer running `docker compose --profile e2e up` sees all six PRD journeys exercised against the real running system (real Keycloak login, no mocks). They can read a documented security review covering the OAuth implementation, and confirm coverage thresholds are met (≥70% across services; backend archetype's >90% target). The repository is reviewable as a complete, working reference for the OAuth/OIDC + BFF + JWKS + scope-enforcement pattern.

**FRs covered:** None directly. Closes out NFR11 (test coverage push to thresholds — the journey E2Es and harness already exist), NFR12 (security posture), and the README / AI integration log deliverable.

**Scope:**

- Coverage push: identify and close any per-service coverage gaps surfaced after all features ship; the SPA target is ≥70% and the backend archetype target is >90%. Add tests where the threshold isn't met yet.
- `docs/security-review.md`: documented security review covering token storage/transport, cookie attributes, CSRF, JWT validation correctness, scope enforcement, XSS / injection — including the accepted-risk note on at-rest token storage in the BFF SQLite (per architecture's "Operational Details").
- README polish: setup instructions, architecture overview, AI integration log capturing BMAD/MCP agent usage throughout the build.
- Final `docker compose up` verification on the `default` profile (SPA baked into the BFF image, full topology end-to-end) — captured as a manual smoke story documented in the README.

Note on the QA work that **does NOT live in Epic 5**: the Playwright project, all six journey specs, `POST /v1/test/reset` endpoints, and the `e2e` compose profile all land in Epics 1–4 alongside the features they verify, per the "QA from day one" principle.

---

## Epic 1: Foundational Login & Identity (J1, J5)

Stand up the monorepo, Keycloak with realm-as-code, the BFF scaffolded from the archetype with cookie-session OAuth Code auth (confidential `client_secret`, no PKCE), and the Angular SPA with auth chrome — alongside the Playwright harness, test-reset endpoint, and J1+J5 E2E specs. Result: a real OIDC round-trip works end-to-end against the running compose stack, and both J1 and J5 are demonstrably correct in CI-style automated runs from day one.

### Story 1.1: Repo scaffold + compose skeleton

As a developer onboarding to the project,
I want a working monorepo skeleton with `docker compose config` validating cleanly,
So that I can extend each part (services, SPA, compose includes) without first inventing the structure.

**Acceptance Criteria:**

**Given** a fresh clone of the repo,
**When** the developer lists the repo root,
**Then** the following top-level files exist: `docker-compose.yml`, `.env.example`, `.gitignore`, `.dockerignore`, `README.md`, `CLAUDE.md`,
**And** the following directories exist: `spa/` (empty placeholder), `services/bff/` (empty placeholder), `services/resource-server/` (empty placeholder), `keycloak/` (empty placeholder), `e2e/` (empty placeholder), `compose/`, `tools/` (gitignored).

**Given** the compose subfolder is present,
**When** the developer inspects `compose/`,
**Then** `compose/infra.yml` and `compose/app.yml` exist as compose-include targets (scaffolds — no app services defined yet; those are added in later stories within this epic).

**Given** the top-level compose file,
**When** the developer inspects `docker-compose.yml`,
**Then** it uses Compose's `include:` directive (Compose v2.20+) to pull in both files under `compose/`,
**And** it defines three profiles `default`, `dev`, and `e2e` consistent with AR26.

**Given** the `.env.example`,
**When** the developer inspects it,
**Then** it documents every required env var from AR29 (`KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`, `BFF_DATABASE_URL`, `RS_DATABASE_URL`, `BFF_BASE_URL`, `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `OIDC_CLIENT_ID`, `BFF_SESSION_COOKIE_NAME`, `BFF_CSRF_COOKIE_NAME`, `BFF_SESSION_COOKIE_SECURE`, `ENABLE_TEST_RESET`, `TEST_RESET_TOKEN`) with placeholder or example values,
**And** `tools/fastapi-archetype/` is listed in `.gitignore`.

**Given** the scaffolded compose stack,
**When** the developer runs `docker compose config`,
**Then** the configuration validates without errors.

**Given** the README,
**When** the developer reads it,
**Then** it contains setup instructions (clone, archetype clone, env setup, compose-up), a stub for the architecture overview, and a stub for the AI integration log.

### Story 1.2: Keycloak realm-as-code + compose service

As a developer running the project,
I want Keycloak to boot with a pre-imported realm containing the BFF client, scopes, audience claim, and the two pre-seeded users,
So that authentication works on first `docker compose up` with zero manual configuration steps.

**Acceptance Criteria:**

**Given** the file `keycloak/realm-bmad-books.json` exists,
**When** the developer inspects it,
**Then** it defines realm `bmad-books`,
**And** it defines a confidential client `bmad-books-bff` with Authorization Code enabled (no PKCE) and `client_secret` sourced from the `BFF_CLIENT_SECRET` env var,
**And** the client's redirect URIs include `http://localhost:8000/auth/callback`,
**And** the realm defines client scopes `reading-speed:read` and `reading-speed:write` as `optional` and assigns them to the `bmad-books-bff` client by default,
**And** the access token has an audience claim mapper that adds `bmad-books-resource-server` to the `aud` claim,
**And** the user `testuser` with password `testpassword` is pre-seeded,
**And** the user `freshuser` with password `freshpassword` is pre-seeded (with no reading-speed value — this exercises the J3 precondition path in Epic 4).

**Given** the `keycloak/` folder,
**When** the developer inspects it,
**Then** `keycloak/Dockerfile` wraps the official Keycloak image and invokes `start --import-realm --optimized` (or `start-dev --import-realm` in dev), with the realm JSON mounted/copied at the documented path,
**And** `compose/infra.yml` defines the `keycloak` service with the realm JSON mounted and `HEALTHCHECK` curling `http://localhost:8080/health/ready` until ready.

**When** the developer runs `docker compose up keycloak`,
**Then** Keycloak's `/health/ready` returns 200 once realm import completes,
**And** the developer can authenticate as `testuser` or `freshuser` via the Keycloak admin console,
**And** a direct `POST /realms/bmad-books/protocol/openid-connect/token` with `grant_type=password` (purely for verification — the BFF will NOT use this grant) returns valid access/refresh/id tokens with the expected scopes and `aud` claim,
**And** no manual configuration is required after compose-up.

### Story 1.3: BFF scaffold from archetype + baseline health + lint/test gates

As a developer working on the BFF,
I want the BFF scaffolded from the `fastapi-archetype` with the archetype's lint/test/typecheck gates green and a working `/health` and `/api/me` (anonymous) endpoint,
So that I have a clean foundation that already meets the archetype's >90% coverage target.

**Acceptance Criteria:**

**Given** `tools/fastapi-archetype/` is cloned (gitignored),
**When** the developer runs `python tools/fastapi-archetype/scripts/build_template.py -n bff -o services/bff --description "BMAD_books Backend-for-Frontend (OAuth client, books domain)"`,
**Then** `services/bff/` contains the archetype's standard layout: `pyproject.toml`, `uv.lock`, `alembic.ini`, `alembic/`, `src/bff/`, `tests/`, `Dockerfile`, `.env.example`, ErrorCode enum, `log_io` AOP decorator.

**Given** the scaffolded BFF,
**When** the developer runs `uv sync --frozen` inside `services/bff/`,
**Then** dependency installation succeeds,
**And** `uv run ruff check` passes with no findings,
**And** `uv run ty` passes with no type errors,
**And** `uv run pytest --cov` passes with coverage above the archetype's configured threshold (>90%).

**Given** the BFF service container,
**When** the developer inspects `services/bff/Dockerfile`,
**Then** it is multi-stage on `python:3.14-slim` with an entrypoint script that runs `uv run alembic upgrade head` before `exec uv run uvicorn bff.app:app --host 0.0.0.0 --port 8000`,
**And** the container mounts the named volume `bff_data` at `/data` for its SQLite file (per AR6).

**Given** the BFF in compose,
**When** the developer inspects `compose/app.yml`,
**Then** the BFF service is defined with `depends_on: { keycloak: { condition: service_healthy } }`,
**And** the BFF service's `env_file:` references `services/bff/.env` (gitignored),
**And** the BFF healthcheck calls `GET /health`.

**Given** the running BFF,
**When** the developer calls `GET /health`,
**Then** it returns 200 once the DB is reachable, Alembic is at head, and the OIDC discovery doc at `${OIDC_ISSUER_URL}/.well-known/openid-configuration` is fetchable.

**When** the developer calls `GET /api/me` without a session cookie,
**Then** the BFF returns 401 with the envelope `{"errorCode": "session_expired", "message": "...", "detail": null}`.

### Story 1.4: BFF session and auth_state schema + Alembic migration

As a developer extending the BFF auth surface,
I want SQLModel models and an Alembic migration creating the `sessions` and `auth_states` tables with the documented columns and indexes,
So that the cookie-session OIDC plugin in the next story has the persistence surface it needs.

**Acceptance Criteria:**

**Given** the BFF db/models/ directory exists per archetype layout,
**When** the developer inspects `src/bff/db/models/session.py`,
**Then** a `Session` SQLModel exists with columns: `id` (PK, str, the opaque 256-bit session value), `sub` (str(255), indexed, NOT NULL), `access_token` (str), `refresh_token` (str), `id_token` (str), `expires_at` (datetime, indexed, NOT NULL), `csrf_secret` (str, NOT NULL), `created_at` (datetime, NOT NULL), `updated_at` (datetime, NOT NULL, `onupdate`).

**When** the developer inspects `src/bff/db/models/auth_state.py`,
**Then** an `AuthState` SQLModel exists with columns: `id` (PK, str), `state` (str, NOT NULL), `nonce` (str, NOT NULL), `return_to` (str, nullable), `expires_at` (datetime, indexed, NOT NULL), `created_at` (datetime, NOT NULL). *(The `code_verifier` column persisted in 0001_init survives the PKCE removal as nullable dead schema and is no longer required by the model — see Pattern Amendments in architecture.md.)*

**Given** the models exist,
**When** the developer runs `uv run alembic revision --autogenerate -m "init sessions and auth_states"`,
**Then** a migration file `alembic/versions/0001_init.py` is created that produces both tables with all columns, NOT NULL constraints, and the indexes `ix_sessions_sub`, `ix_sessions_expires_at`, `ix_auth_states_expires_at` (per architecture's Naming Patterns).

**When** the developer runs `uv run alembic upgrade head` against an empty SQLite file,
**Then** both tables are created at the head revision and `alembic current` reports `0001_init` as the head.

**When** the developer runs `uv run alembic downgrade base`,
**Then** both tables are removed cleanly.

**Given** the models and migration,
**When** the developer runs `uv run pytest tests/db/`,
**Then** tests cover model creation, read by id, read by sub, expiry-filter queries, `created_at`/`updated_at` auto-population, and the unique-constraint behaviors,
**And** coverage of `src/bff/db/models/` is ≥90%,
**And** `uv run ruff check && uv run ty` remains clean.

### Story 1.5: BFF cookie-session OIDC plugin (Authorization Code, no PKCE) + synthetic-IdP test harness  *(amended 2026-05-21 — PKCE removed; see sprint-change-proposal-2026-05-21.md)*

As an unauthenticated visitor,
I want to be able to complete an Authorization Code round-trip against Keycloak through the BFF (BFF authenticates with `client_secret_basic`; no PKCE),
So that I end up with an HttpOnly session cookie while the BFF holds my access/refresh/id tokens server-side.

**Acceptance Criteria:**

**Given** the BFF `auth/` directory contains `keycloak_cookie_session.py` (Authlib-based OIDC client plugin),  *(the previous `pkce.py` helper module was deleted on 2026-05-21 — see Group E of sprint-change-proposal-2026-05-21.md)*
**And** `tests/auth/synthetic_idp.py` provides a test-generated RSA keypair plus monkey-patched httpx routes for `/authorize`, `/token`, `/revocation`, `/end_session`, and a JWKS handler,

**When** an unauthenticated client hits `GET /auth/login?return_to=/books` with redirects disabled,
**Then** the BFF responds 302 to `${OIDC_ISSUER_URL}/realms/bmad-books/protocol/openid-connect/auth` with query parameters `client_id`, `response_type=code`, `scope=openid reading-speed:read reading-speed:write`, `state` (CSRF random ≥32 bytes), `nonce` (replay defense, ≥16 bytes), and `redirect_uri=${BFF_BASE_URL}/auth/callback`,
**And** the BFF persists an `auth_states` row with the fresh `state`, `nonce`, `return_to=/books`, and `expires_at = now + 5 min` (the legacy `code_verifier` column is left NULL / dead),
**And** the BFF sets a signed state-id cookie: `HttpOnly`, `Max-Age=300`, `SameSite=Lax`, `Path=/`, value = the `auth_states.id` signed with an HMAC over the BFF's session secret.

**Given** an `auth_states` row exists for state value `S` with `return_to=/books`,
**When** the BFF receives `GET /auth/callback?code=C&state=S` carrying the matching state-id cookie,
**And** the synthetic IdP exchanges code `C` + verifier `V` for access/refresh/id tokens,
**Then** the BFF persists a `sessions` row with `sub` (from the id_token claim), `access_token`, `refresh_token`, `id_token`, `expires_at` (derived from the access_token's `exp`), a freshly generated 32-byte `csrf_secret`, `created_at`, and `updated_at`,
**And** the BFF sets the session cookie (named per `BFF_SESSION_COOKIE_NAME`): `HttpOnly`, `Secure` (per `BFF_SESSION_COOKIE_SECURE`), `SameSite=Lax`, `Path=/`, value = `sessions.id` (opaque 256-bit value, not a JWT),
**And** the BFF sets the csrf_token cookie (named per `BFF_CSRF_COOKIE_NAME`): non-`HttpOnly`, `Secure` (per env), `SameSite=Lax`, `Path=/`, value = `sessions.csrf_secret`,
**And** the BFF deletes the consumed `auth_states` row,
**And** the BFF responds 302 to `/books`.

**When** the BFF receives `/auth/callback` with a `state` query value that does NOT match any `auth_states` row, OR with a state-id cookie whose row id does not match the row identified by the `state` query value,
**Then** the BFF responds 400 with envelope `{"errorCode": "auth_state_invalid", "message": "...", "detail": null}` and creates NO session.

**When** the BFF receives `/auth/callback` for an `auth_states` row whose `expires_at` is in the past,
**Then** the BFF responds 400 with `errorCode: "auth_state_invalid"` and deletes the expired row.

**When** the synthetic IdP's `/token` endpoint rejects the code exchange (invalid code, expired code, or client_secret mismatch),
**Then** the BFF responds 400 with `errorCode: "auth_state_invalid"` and does NOT create a session.

**Given** an authenticated session,
**When** `GET /api/me` is called with the session cookie,
**Then** the BFF returns 200 with body `{"sub": "...", "preferred_username": "..."}` (preferred_username read from the id_token claim).

**Given** the test suite,
**When** `uv run pytest tests/auth/` runs,
**Then** tests cover all of: happy path with synthetic IdP, state-cookie/state-param mismatch, token-exchange rejection by the AS (synthetic IdP returns 400), expired `auth_state` row, replay of consumed `auth_state` (already-deleted row), missing state-id cookie, missing `state` query param, id_token signature invalid (forged with the wrong key), JWKS-fetch failure on first /authorize hit,
**And** coverage of `src/bff/auth/keycloak_cookie_session.py` is ≥90%,
**And** `ruff check && ty` remains clean.

### Story 1.6: BFF CSRF middleware + CSP header

As a security-aware reviewer,
I want state-changing requests without a valid CSRF header to be rejected with a 403 and `csrf_invalid` envelope, and SPA-served responses to carry the documented Content-Security-Policy header,
So that the BFF's cookie-session surface meets the documented security posture even before any domain features exist.

**Acceptance Criteria:**

**Given** the BFF middleware stack includes the CSRF middleware (`src/bff/auth/csrf.py`),

**Given** a valid session cookie and a valid `csrf_token` cookie exist,
**When** a state-changing request (`POST`, `PUT`, `PATCH`, `DELETE`) is sent without the `X-CSRF-Token` header,
**Then** the BFF responds 403 with envelope `{"errorCode": "csrf_invalid", "message": "...", "detail": null}`.

**When** a state-changing request is sent with `X-CSRF-Token` header value that does NOT equal the `csrf_token` cookie value,
**Then** the BFF responds 403 with `errorCode: "csrf_invalid"`.

**When** a state-changing request is sent with `X-CSRF-Token` equal to the `csrf_token` cookie AND a same-origin `Origin` or `Referer` header (matching `BFF_BASE_URL`),
**Then** the request proceeds to the handler normally.

**When** a state-changing request is sent with a cross-origin `Origin`/`Referer` header (mismatched against `BFF_BASE_URL`),
**Then** the BFF responds 403 with `errorCode: "csrf_invalid"`,
**And** the failure is logged at WARN level (per AR12 logging conventions).

**When** a safe-method request (`GET`, `HEAD`, `OPTIONS`) is sent without an `X-CSRF-Token` header,
**Then** the request proceeds normally.

**Given** the SPA-serving routes are mounted (per the catch-all fallback at `/`),
**When** the BFF returns a response on an SPA-serving route,
**Then** the response includes the `Content-Security-Policy` header with the exact value: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.

**Given** the test suite,
**When** `uv run pytest tests/auth/test_csrf.py` runs,
**Then** tests cover: missing header, mismatched header, valid header same-origin, valid header cross-origin, safe-methods exemption, CSP header presence on SPA routes, CSP header absent on JSON API routes (per architecture pattern — CSP only on HTML responses),
**And** coverage of `src/bff/auth/csrf.py` is ≥90%.

### Story 1.7: BFF logout endpoint (revoke + end-session + degrade honestly)

As a signed-in user,
I want to click "Log out" and have my session terminated locally, my refresh token revoked at Keycloak, and the session cookie cleared,
So that no residual access remains after I log out — even when the authorization server is temporarily unreachable.

**Acceptance Criteria:**

**Given** an authenticated session with stored `access_token`, `refresh_token`, `id_token`,
**When** the SPA POSTs to `/auth/logout` with a valid session cookie and matching `X-CSRF-Token` header,
**Then** the BFF calls Keycloak's revocation endpoint with `token=<refresh_token>&token_type_hint=refresh_token`,
**And** the BFF calls Keycloak's `end_session_endpoint` with `id_token_hint=<id_token>`,
**And** the BFF deletes the `sessions` row for this session id,
**And** the BFF sets `Set-Cookie: <session_cookie>=; Max-Age=0; Path=/; ...` and `Set-Cookie: <csrf_token>=; Max-Age=0; Path=/; ...`,
**And** the BFF responds 204 with an empty body.

**Given** the revocation endpoint call to Keycloak fails (connection error, 5xx, or timeout),
**When** the logout flow continues,
**Then** the BFF still deletes the local `sessions` row, still clears both cookies, and still responds 204,
**And** the revocation failure is logged at WARN level.

**Given** the `end_session_endpoint` call to Keycloak fails,
**When** the logout flow continues,
**Then** the BFF still deletes the local `sessions` row, still clears both cookies, and still responds 204,
**And** the failure is logged at WARN level.

**When** `POST /auth/logout` is called without a session cookie,
**Then** the BFF responds 401 with `errorCode: "session_expired"`.

**When** `POST /auth/logout` is called without a valid `X-CSRF-Token`,
**Then** the BFF responds 403 with `errorCode: "csrf_invalid"`.

**Given** the test suite,
**When** `uv run pytest tests/api/test_auth.py::test_logout_*` runs,
**Then** tests cover: happy path (synthetic IdP receives revocation + end-session calls), revocation failure, end-session failure, both-fail, missing CSRF, missing session,
**And** an integration test confirms that the captured refresh token, replayed against the synthetic IdP's `/token` endpoint AFTER logout (the synthetic IdP simulates Keycloak's revocation list), is rejected,
**And** coverage of the logout code path is ≥90%.

### Story 1.8: SPA scaffold + Tailwind v4 + design tokens

As a developer working on the SPA,
I want Angular v21 + Tailwind v4 scaffolded with the UX-DR1 design tokens declared in `styles.css`, ESLint configured, and Vitest passing on a default test,
So that subsequent stories can build components against locked design tokens without re-establishing the foundation.

**Acceptance Criteria:**

**Given** the repo root is empty of an `spa/` directory,
**When** the developer runs `npx -p @angular/cli@21 ng new spa --routing --style=css --ssr=false --skip-git --package-manager=npm --strict`,
**And then** runs `cd spa && npm install -D tailwindcss @tailwindcss/postcss postcss`,
**Then** `spa/package.json` declares `@angular/cli` v21, `tailwindcss`, `@tailwindcss/postcss`, and `postcss` as devDependencies,
**And** `spa/.postcssrc.json` contains `{"plugins": {"@tailwindcss/postcss": {}}}`,
**And** `spa/tsconfig.json` has `strict: true`,
**And** the Angular workspace targets zoneless change detection (no `zone.js` in `polyfills`).

**Given** the styles file,
**When** the developer inspects `spa/src/styles.css`,
**Then** it begins with `@import "tailwindcss";` followed by an `@theme` block containing exactly the UX-DR1 tokens:
- `--color-surface: #FFFFFF;`, `--color-surface-muted: #F5F5F5;`, `--color-border: #E5E5E5;`,
- `--color-text: #111111;`, `--color-text-muted: #666666;`,
- `--color-accent: #2563EB;`, `--color-accent-hover: #1D4ED8;`,
- `--color-error: #B91C1C;`,
- `--text-page-title: 24px / 32px 600;`, `--text-section: 18px / 24px 600;`, `--text-body: 14px / 20px 400;`, `--text-small: 12px / 16px 400;`,
- `--spacing-1: 4px;` through `--spacing-8: 32px;` (values 4, 8, 12, 16, 24, 32 — matching UX-DR1's table).

**Given** the dev proxy is needed,
**When** the developer inspects `spa/proxy.conf.json`,
**Then** it forwards `/auth/*`, `/api/*`, and `/v1/*` to `http://localhost:8000`.

**Given** the linting config,
**When** the developer inspects `spa/.eslintrc.json`,
**Then** it extends `@angular-eslint/recommended`,
**And** adds project rules forbidding empty `catch` blocks and `console.log` outside `*.spec.ts` files (per architecture's "Enforcement Guidelines").

**Given** Vitest is wired,
**When** the developer runs `npm test` inside `spa/`,
**Then** the default scaffolded `app.spec.ts` test passes,
**And** the test runner exits 0.

**When** the developer runs `npm run build` inside `spa/`,
**Then** the build succeeds and produces `dist/spa/browser/`.

**When** the developer runs `ng serve` (with BFF + Keycloak running in compose) and visits `http://localhost:4200`,
**Then** the dev server starts and the proxy correctly forwards backend paths to the BFF on port 8000,
**And** a smoke component referencing classes derived from the tokens (e.g., `text-accent`, `bg-surface-muted`, `p-3`) renders with the expected styling.

### Story 1.9: SPA AuthService + interceptors + functional guards

As a signed-in user,
I want the SPA to attach my session cookie and CSRF header to every BFF call, to redirect me to `/login` if my session has expired, and to bounce me to `/books` if I visit `/login` while still authenticated,
So that auth state is enforced consistently across the entire SPA without leaking session-handling code into feature components.

**Acceptance Criteria:**

**Given** `spa/src/app/shared/http/` contains `with-credentials-interceptor.ts` and `csrf-interceptor.ts`,
**And** `spa/src/app/auth/` contains `auth-service.ts`, `auth-guard.ts`, `redirect-if-authed-guard.ts`, `auth.types.ts`,
**And** `spa/src/app/app.config.ts` wires `provideHttpClient(withFetch(), withInterceptors([withCredentialsInterceptor, csrfInterceptor]))`,

**When** `AuthService.loadMe()` is called,
**Then** it issues `GET /api/me`,
**And** on 200 it sets the `me` signal to `{ sub, preferred_username }`,
**And** on 401 it sets the `me` signal to `null`.

**When** any HTTP request originates from the SPA,
**Then** `withCredentialsInterceptor` sets `credentials: 'include'` on the request (so the session cookie is sent).

**When** a state-changing request (`POST`, `PUT`, `PATCH`, `DELETE`) originates from the SPA,
**Then** `csrfInterceptor` reads the `csrf_token` cookie and sets the `X-CSRF-Token` header on the request.

**When** a safe-method request (`GET`, `HEAD`, `OPTIONS`) originates from the SPA,
**Then** `csrfInterceptor` does NOT add the `X-CSRF-Token` header.

**When** the `authGuard` is invoked on activation of `/books` or `/settings`,
**Then** it issues `GET /api/me`,
**And** on 200 it allows the navigation,
**And** on 401 it returns a redirect to `/login?return_to=<the requested URL encoded>`.

**When** the `redirectIfAuthedGuard` is invoked on activation of `/login`,
**Then** it issues `GET /api/me`,
**And** on 200 it returns a redirect to `/books`,
**And** on 401 it allows the navigation.

**Given** any non-`/api/me` HTTP response returns 401,
**When** the global response handler fires,
**Then** the SPA clears the in-memory `me` signal and navigates to `/login?return_to=<current URL>`.

**Given** the test suite,
**When** `npm test` runs inside `spa/`,
**Then** spec files exist and pass for `auth-service`, `with-credentials-interceptor`, `csrf-interceptor`, `auth-guard`, `redirect-if-authed-guard`,
**And** tests use `HttpTestingController` + signal-getter assertions,
**And** Vitest coverage of `src/app/auth/` and `src/app/shared/http/` is ≥70%.

### Story 1.10: SPA LoginView + TopChrome + route table

As an unauthenticated visitor,
I want to land on `/login`, click a single "Log in" button, complete a real Keycloak round-trip, and return signed in to `/books` with my identity displayed in the top chrome and a clearly visible "Log out" affordance,
So that J1 and J5 work end-to-end in the running SPA.

**Acceptance Criteria:**

**Given** the SPA route table is configured in `app.config.ts` per AR23,
**When** the developer inspects the routes,
**Then** the routes are: `''` → redirect to `books`; `/login` → `LoginView` with `redirectIfAuthedGuard`; `/books` → `BooksPagePlaceholder` with `authGuard`; `/settings` → `SettingsPagePlaceholder` with `authGuard`; `**` → redirect to `books`.

**Given** `spa/src/app/login/login-view.{ts,html,css,spec.ts}` exists,
**When** a user navigates to `/login`,
**Then** `LoginView` renders centered in the 720px content column with:
- Headline text `"Sign in to Reading Time Estimator"` in `--text-page-title`,
- One paragraph `"You'll be redirected to authenticate, then returned here."` in `--text-body` / `--color-text-muted`,
- One primary button `"Log in"` styled in `--color-accent`.

**When** the user clicks `"Log in"` on `/login`,
**Then** the browser performs a full-page navigation to `/auth/login` (NOT an HttpClient call) so that the BFF can issue a 302 to Keycloak.

**When** a user navigates to `/login?error=auth`,
**Then** `LoginView` renders an inline `ErrorMessage` above the button containing the literal copy `"Login didn't complete — try again."` per UX-DR12.

**Given** `spa/src/app/shared/chrome/top-chrome.{ts,html,css,spec.ts}` exists,
**When** `TopChrome` renders in the unauthenticated variant,
**Then** it shows only the product name `"Reading Time Estimator"` on the left (in `--text-page-title`),
**And** no identity block or route link.

**When** `TopChrome` renders in the authenticated variant on `/books`,
**Then** it shows the product name on the left,
**And** a `"Settings"` route link in the middle,
**And** on the right: `"Signed in as "` (in `--color-text-muted`) followed by `<preferred_username>` (in `--color-text`) then `" · "` then a `"Log out"` text button.

**When** `TopChrome` renders in the authenticated variant on `/settings`,
**Then** the middle route link reads `"Books"` (instead of `"Settings"`).

**When** the user clicks `"Log out"`,
**Then** the SPA calls `POST /auth/logout` (the CSRF header is attached automatically by `csrfInterceptor`),
**And** on 2xx response, the in-memory user state is cleared and the SPA navigates to `/login`,
**And** `TopChrome` on `/login` renders the unauthenticated variant.

**Given** a placeholder `BooksPagePlaceholder` component is registered at `/books`,
**When** an authenticated user navigates to `/books` during Epic 1,
**Then** the page renders the literal text `"Books — coming in Epic 2"` (plain copy, no styling beyond default body text — this is intentional placeholder content, not a real loading state),
**And** the same placeholder pattern applies to `SettingsPagePlaceholder` at `/settings`.

**When** an unauthenticated user attempts to navigate directly to `/books` or `/settings`,
**Then** the `authGuard` redirects them to `/login?return_to=<the original URL>`,
**And** after a successful login round-trip, the BFF's callback honors `return_to` and the user returns to the original URL.

**Given** the test suite,
**When** `npm test` runs,
**Then** spec files pass for `login-view` (default + `?error=auth` states) and `top-chrome` (authenticated + unauthenticated variants), with assertions on rendered text, classes, route-link contextual swap, and click handlers.

### Story 1.11: Playwright project setup + fixtures + helpers

As a maintainer,
I want a Playwright project under `e2e/` with configuration, shared fixtures, and helper functions ready to drive real OAuth flows against the running compose stack,
So that journey-specific E2E specs (added in this epic and in every subsequent epic) can be written without re-doing the harness.

**Acceptance Criteria:**

**Given** the repo root has no `e2e/` content yet,
**When** the developer scaffolds the Playwright project,
**Then** `e2e/package.json` declares `@playwright/test` (latest stable as of May 2026) as a devDependency,
**And** `e2e/tsconfig.json` compiles cleanly,
**And** `e2e/.gitignore` excludes `node_modules/`, `test-results/`, `playwright-report/`.

**Given** the Playwright config,
**When** the developer inspects `e2e/playwright.config.ts`,
**Then** it sets: `testDir: './tests'`, `timeout: 60_000`, `workers: 1` (sequential, to avoid test-reset cross-talk), `use: { baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8000', trace: 'retain-on-failure', screenshot: 'only-on-failure', video: 'retain-on-failure' }`, `projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]`.

**Given** the fixtures,
**When** the developer inspects `e2e/fixtures/users.ts`,
**Then** it exports the two seeded user definitions: `testuser` (username, password, sub-pattern matcher) and `freshuser` (same shape).

**Given** the helpers,
**When** the developer inspects `e2e/fixtures/helpers.ts`,
**Then** it exports:
- `logInAs(page, user)` — navigates to `/login`, clicks `"Log in"`, fills the Keycloak username/password form on the redirected page, submits, waits for redirect back to `/books`, returns when the identity block in TopChrome is visible,
- `resetState(request, opts)` — calls `POST /v1/test/reset` on the BFF with `Authorization: Bearer ${process.env.TEST_RESET_TOKEN}`; signature accommodates the RS test-reset endpoint being added in Epic 3,
- `killRs()` and `startRs()` — stub functions that throw `"RS not yet present (Epic 3)"` so the helpers compile but loudly fail if called before they're real.

**Given** the e2e compose profile,
**When** the developer inspects `compose/app.yml`,
**Then** the `e2e` profile defines a `playwright` runner container with `depends_on: { bff: { condition: service_healthy }, keycloak: { condition: service_healthy } }`,
**And** the runner image is built from `e2e/Dockerfile` (Node 20+, only the chromium browser installed via `npx playwright install --with-deps chromium` to keep the image small),
**And** the runner mounts the e2e source folder at build time and `test-results/` as a host volume for trace/screenshot artifacts.

**When** the developer runs `cd e2e && npm ci && npx playwright install --with-deps chromium`,
**And then** runs `npx playwright test` against an empty `tests/` directory,
**Then** the runner discovers no tests and exits 0 with `"no tests found"` reported (acceptable baseline before Story 1.13).

**When** the developer runs `docker compose --profile e2e up --abort-on-container-exit`,
**Then** the Playwright runner container starts after BFF and Keycloak report healthy,
**And** if no specs are present, exits 0.

**Given** `e2e/README.md`,
**When** the developer reads it,
**Then** it documents how to run specs locally (`npm test` after `compose up dev`) and via compose (`docker compose --profile e2e up --abort-on-container-exit`).

### Story 1.12: BFF `POST /v1/test/reset` endpoint

As a maintainer running E2E tests,
I want the BFF to expose a guarded `POST /v1/test/reset` endpoint that truncates the auth-related tables,
So that each E2E test can start from a known clean state without manual cleanup or fragile inter-test ordering.

**Acceptance Criteria:**

**Given** `src/bff/api/test_reset.py` exists,
**When** the BFF starts and `ENABLE_TEST_RESET` is unset or any value other than `"true"`,
**Then** the `/v1/test/reset` route is NOT registered,
**And** any HTTP method against `/v1/test/reset` returns the standard 404 envelope (indistinguishable from any other missing route).

**When** the BFF starts with `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN` set,
**Then** `POST /v1/test/reset` is registered.

**When** `POST /v1/test/reset` is called without an `Authorization` header,
**Then** the BFF responds 401 with envelope `{"errorCode": "session_expired", ...}` (consistent with the archetype's unauthenticated default).

**When** `POST /v1/test/reset` is called with `Authorization: Bearer <wrong-token>`,
**Then** the BFF responds 401.

**When** `POST /v1/test/reset` is called with `Authorization: Bearer ${TEST_RESET_TOKEN}` (matching the env value),
**Then** the BFF truncates all rows in `sessions` and `auth_states`,
**And** responds 204 with an empty body.

**Given** the prod Dockerfile build (default profile in compose),
**When** the developer inspects the env values,
**Then** `ENABLE_TEST_RESET` is NOT set,
**And** the test_reset route is therefore not registered.

**Given** the e2e compose profile,
**When** the developer inspects `compose/app.yml`,
**Then** both `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN=<value>` are set on the BFF service for that profile only.

**Given** the test suite,
**When** `uv run pytest tests/api/test_reset.py` runs,
**Then** tests cover: route not registered when env is off (HTTP client gets 404), wrong bearer rejected, missing bearer rejected, correct bearer truncates `sessions` + `auth_states` (verified by row counts pre/post), correct bearer returns 204 with empty body,
**And** coverage of `src/bff/api/test_reset.py` is ≥90%.

### Story 1.13: E2E spec — J1 first-time login + J5 logout

As a reviewer of the OAuth/OIDC reference,
I want Playwright E2E specs that drive the J1 first-time-login and J5 logout journeys end-to-end against the real Keycloak and BFF,
So that the documented PRD success criteria for those journeys are demonstrably met on every CI-style run from the day Epic 1 ships.

**Acceptance Criteria:**

**Given** `e2e/tests/j1-first-login.spec.ts` exists,
**When** the developer inspects it,
**Then** it uses `test.describe('J1: first-time login', ...)` with a `beforeEach` that calls `resetState(request, { resetToken: process.env.TEST_RESET_TOKEN })`,
**And** contains at minimum these test cases:
- `unauthenticated user navigating to / is redirected to /login` — navigates `page.goto('/')`, asserts the resulting URL matches `/login`, asserts the `Log in` button is visible and the identity block is NOT visible in `TopChrome`,
- `clicking Log in completes the OAuth round-trip and returns the user to /books` — clicks `Log in`, asserts URL contains `/realms/bmad-books/protocol/openid-connect/auth`, fills `testuser` credentials, submits, asserts URL ends with `/books`, asserts `TopChrome` shows `"Signed in as testuser · Log out"`, asserts the placeholder `Books — coming in Epic 2` is visible,
- `protected route while unauthenticated redirects with return_to and returns user after login` — navigates directly to `/books`, asserts URL contains `/login?return_to=%2Fbooks`, completes login via `logInAs(page, testuser)`, asserts URL ends with `/books`.

**Given** `e2e/tests/j5-logout.spec.ts` exists,
**When** the developer inspects it,
**Then** it uses `test.describe('J5: logout and re-protection', ...)` with a `beforeEach` that calls `resetState` then `logInAs(page, testuser)`,
**And** contains at minimum these test cases:
- `clicking Log out terminates session and re-protects routes` — clicks `Log out` in `TopChrome`, asserts URL ends with `/login`, asserts `TopChrome` shows only the product name (no identity block), asserts the session cookie is no longer present in the browser context, then navigates to `/books`, asserts URL contains `/login?return_to=%2Fbooks`,
- `refresh token is revoked at Keycloak after logout` — captures the refresh_token via a mechanism appropriate to the implementation (e.g., a test-only debug helper that returns the stored refresh_token for the current session id when `ENABLE_TEST_RESET=true`), performs logout, then attempts to use the captured refresh_token directly against Keycloak's `/token` endpoint with `grant_type=refresh_token`, asserts Keycloak responds with `error=invalid_grant`.

**When** the developer runs `docker compose --profile e2e up --abort-on-container-exit`,
**Then** both spec files run inside the Playwright container against the live compose stack,
**And** all tests pass,
**And** the runner exits 0,
**And** on any failure, traces and screenshots are retained under `e2e/test-results/`.

**Given** the spec content,
**When** the developer reviews the spec files,
**Then** both specs use the helpers from Story 1.11 (`logInAs`, `resetState`),
**And** no spec inlines its own Keycloak credential-filling logic or token shenanigans — the helpers are the single source of truth.

---

## Epic 2: Personal Book List (J2)

Implement the books domain on the BFF and the SPA's book-list surface end-to-end: a signed-in user can add books, change status with optimistic UI, edit inline, and delete with native `confirm()`. Journey J2 is proven by a Playwright E2E spec running against the real running stack.

### Story 2.1: BFF — Book SQLModel + migration + Pydantic boundary models

As a developer extending the BFF to own the book domain,
I want a `Book` SQLModel and Alembic migration creating the `books` table, plus distinct API Pydantic models (`BookCreate`, `BookUpdate`, `BookOut`),
So that the next story can implement CRUD against a stable schema and a serialization layer that doesn't leak internal columns.

**Acceptance Criteria:**

**Given** `src/bff/db/models/book.py` exists,
**When** the developer inspects it,
**Then** a `Book` SQLModel exists with columns: `id` (PK, int, autoincrement), `sub` (str(255), indexed, NOT NULL), `title` (str(500), NOT NULL), `pages` (int, NOT NULL, constrained to ≥1 at the DB level via a CHECK constraint or at the application level via Pydantic), `status` (str, NOT NULL, default `"to-read"`, constrained to `{"to-read", "reading", "finished"}` via SQLAlchemy enum or string with check), `created_at` (datetime, NOT NULL), `updated_at` (datetime, NOT NULL, onupdate),
**And** the SQL table name is `books` (snake_case plural per architecture's Naming Patterns),
**And** the index `ix_books_sub` is declared on the `sub` column.

**Given** the API boundary models live at the archetype's conventional location (e.g., `src/bff/api/schemas/book.py`),
**When** the developer inspects them,
**Then** `BookCreate` has fields: `title: str` (min_length 1 after whitespace strip), `pages: int` (constrained `ge=1`), `status: Literal["to-read","reading","finished"]` (default `"to-read"`),
**And** `BookUpdate` has all three fields optional with the same constraints (partial update),
**And** `BookOut` has fields: `id`, `title`, `pages`, `status`, `created_at`, `updated_at` (explicitly excludes `sub` per AR20).

**When** the developer runs `uv run alembic revision --autogenerate -m "add books table"`,
**Then** a migration file `alembic/versions/0002_add_books.py` is created that produces the `books` table with all columns, NOT NULL constraints, the `ix_books_sub` index, and any check constraint chosen for `pages`/`status`.

**When** the developer runs `uv run alembic upgrade head` against the DB at revision `0001_init`,
**Then** the `books` table is created and `alembic current` reports `0002_add_books` as the head,
**And** the `sessions` and `auth_states` tables from `0001` remain untouched.

**When** the developer runs `uv run alembic downgrade -1`,
**Then** only the `books` table is removed; revision returns to `0001_init`.

**Given** the test suite,
**When** `uv run pytest tests/db/test_book_model.py tests/api/schemas/test_book_schemas.py` runs,
**Then** tests cover: Book creation, sub indexing, status enum validation (rejects invalid values), `BookCreate`/`BookUpdate` validation for invalid input (negative or zero pages, empty title, whitespace-only title, unknown status), `BookOut` round-trip serialization, `created_at`/`updated_at` auto-population,
**And** coverage of `src/bff/db/models/book.py` and the Pydantic schema modules is ≥90%,
**And** `uv run ruff check && uv run ty` remains clean.

### Story 2.2: BFF — full books CRUD (`/v1/books` + `/v1/books/{id}`)

As a signed-in user (via the SPA),
I want full CRUD endpoints at `/v1/books` and `/v1/books/{id}` scoped strictly to my own books by `sub`,
So that I can manage my personal book list without ever seeing or being able to access another user's books.

**Acceptance Criteria:**

**Given** `src/bff/api/books.py` exists registering an `APIRouter` mounted at `/v1/books`,
**And** `src/bff/services/books_service.py` exists exposing `list_for_user(session, sub)`, `get_for_user(session, sub, book_id)`, `create(session, sub, payload)`, `update(session, sub, book_id, payload)`, `delete(session, sub, book_id)`,
**And** `src/bff/core/exceptions.py` declares `BookNotFoundError(BFFError)` with `error_code = ErrorCode.BOOK_NOT_FOUND` (HTTP 404) and `InvalidInputError(BFFError)` with `error_code = ErrorCode.INVALID_INPUT` (HTTP 422),
**And** the BFF's `ErrorCode` enum includes `BOOK_NOT_FOUND` and `INVALID_INPUT`,
**And** the routes require a valid session cookie (return 401 `session_expired` on absence) and — for state-changing methods — a valid `X-CSRF-Token` (return 403 `csrf_invalid` on failure, per the Epic 1 middleware applied uniformly).

**Given** an authenticated session with `sub = S`,
**When** `GET /v1/books` is called with the session cookie,
**Then** the BFF returns 200 with a plain JSON array (no envelope) of `BookOut` objects containing only books where `books.sub == S`,
**And** the array is ordered by `created_at` ascending (insertion order per UX-DR5 default).

**When** `POST /v1/books` is called with body `{"title": "Dune", "pages": 688, "status": "reading"}` and a valid CSRF header,
**Then** the BFF persists a `books` row with `sub = S` and the given values,
**And** responds 201 with the created `BookOut` as the body,
**And** sets the `Location` header to `/v1/books/{id}` (per AR16 format patterns).

**When** `POST /v1/books` is called with body missing a required field, with `pages <= 0`, or with a title that is empty after whitespace strip,
**Then** the BFF responds 422 with envelope `{"errorCode": "invalid_input", "message": "...", "detail": <pydantic-detail>}`.

**When** `POST /v1/books` is called with a `status` value not in `{"to-read","reading","finished"}`,
**Then** the BFF responds 422 with `errorCode: "invalid_input"`.

**Given** an authenticated session with `sub = S` and an existing book `id = B` owned by `S`,
**When** `GET /v1/books/{B}` is called,
**Then** the BFF responds 200 with the `BookOut`.

**When** `GET /v1/books/{B}` is called for a book id that does NOT exist,
**Then** the BFF responds 404 with envelope `{"errorCode": "book_not_found", ...}`.

**Given** an authenticated session with `sub = S'` (a different user) and a book `id = B` owned by `sub = S`,
**When** `GET /v1/books/{B}` is called,
**Then** the BFF responds 404 with `errorCode: "book_not_found"` (NOT 403 — existence is not leaked across users).

**When** `PATCH /v1/books/{B}` is called with body `{"status": "finished"}` and valid CSRF,
**Then** the BFF updates only the `status` column on the row (title and pages remain unchanged),
**And** responds 200 with the updated `BookOut`,
**And** `books.updated_at` is bumped via the SQLModel `onupdate` factory.

**When** `PATCH /v1/books/{B}` is called with a body containing an invalid value (e.g., `pages=0`, unknown status, empty title),
**Then** the BFF responds 422 with `errorCode: "invalid_input"` and the row is unchanged.

**When** `PATCH /v1/books/{B}` is called against a non-existent book OR a book owned by a different `sub`,
**Then** the BFF responds 404 `book_not_found`.

**When** `DELETE /v1/books/{B}` is called with valid CSRF,
**Then** the BFF deletes the `books` row,
**And** responds 204 with no body.

**When** `DELETE /v1/books/{B}` is called for a non-existent book OR a book owned by a different `sub`,
**Then** the BFF responds 404 `book_not_found`.

**When** any state-changing `/v1/books` request is sent without the `X-CSRF-Token` header (or with a mismatched value),
**Then** the BFF responds 403 with `errorCode: "csrf_invalid"`.

**When** any `/v1/books` request is sent without a session cookie,
**Then** the BFF responds 401 with `errorCode: "session_expired"`.

**Given** the test suite,
**When** `uv run pytest tests/api/test_books.py tests/services/test_books_service.py` runs,
**Then** tests cover for each of LIST, CREATE, READ, UPDATE, DELETE: happy path, missing session (401), missing CSRF on state-changing methods (403), cross-user isolation (404 on access to other-user resources), invalid input (422), not-found (404),
**And** at least one test confirms that two distinct sessions for two distinct `sub` values produce fully isolated lists and per-id lookups,
**And** coverage of `src/bff/api/books.py` and `src/bff/services/books_service.py` is ≥90%,
**And** `ruff check && ty` remain clean.

### Story 2.3: BFF — extend `/v1/test/reset` to truncate `books`

As a maintainer running E2E tests,
I want the BFF's `POST /v1/test/reset` endpoint (introduced in Story 1.12) to also truncate the `books` table,
So that J2 Playwright specs can rely on a deterministic empty list at the start of each test.

**Acceptance Criteria:**

**Given** the test-reset endpoint from Story 1.12 already truncates `sessions` and `auth_states`,
**When** the developer extends `src/bff/api/test_reset.py`,
**Then** the endpoint truncates `books` in addition to `sessions` and `auth_states`.

**When** `POST /v1/test/reset` is called with the correct bearer token after some books have been created,
**Then** all rows in `books`, `sessions`, and `auth_states` are deleted,
**And** the BFF responds 204 with empty body,
**And** subsequent `GET /v1/books` calls return an empty array.

**Given** the existing test-reset gating from Story 1.12,
**When** `POST /v1/test/reset` is called without `ENABLE_TEST_RESET=true`, with a missing bearer, or with a wrong bearer,
**Then** all the gating behaviors from Story 1.12 continue to apply (404 / 401 respectively).

**Given** the test suite,
**When** `uv run pytest tests/api/test_reset.py` runs,
**Then** the existing tests are updated to seed a few `books` rows alongside `sessions`/`auth_states` rows and assert all three tables are truncated by the correct-bearer call,
**And** coverage of `src/bff/api/test_reset.py` remains ≥90%.

### Story 2.4: SPA — BooksService + types

As a developer wiring SPA components to the books API,
I want a `BooksService` that owns the books signal and exposes typed CRUD methods — including optimistic status updates with revert-on-failure — plus a `book.types.ts` mirroring the wire shape,
So that components subscribe to the signal and call methods without dealing with HTTP state themselves.

**Acceptance Criteria:**

**Given** `spa/src/app/books/book.types.ts` exists,
**When** the developer inspects it,
**Then** it exports:
- `type BookStatus = 'to-read' | 'reading' | 'finished'`,
- `interface Book { id: number; title: string; pages: number; status: BookStatus; created_at: string; updated_at: string }` (snake_case field names per AR16 — no case-conversion layer),
- `interface BookCreate { title: string; pages: number; status: BookStatus }`,
- `type BookUpdate = Partial<{ title: string; pages: number; status: BookStatus }>`.

**Given** `spa/src/app/books/books-service.ts` exists and is decorated `@Injectable({ providedIn: 'root' })`,
**When** the developer inspects it,
**Then** it declares:
- `readonly books = signal<Book[]>([])`,
- `readonly loading = signal<boolean>(false)`,
- `readonly loadError = signal<AppError | null>(null)`,
**And** methods: `load(): Promise<void>`, `create(payload: BookCreate): Promise<Book>`, `update(id: number, payload: BookUpdate): Promise<Book>`, `setStatus(id: number, next: BookStatus): Promise<void>` (the OPTIMISTIC method per UX-DR7), `delete(id: number): Promise<void>`,
**And** all dependencies are acquired via `inject(...)` (not constructor DI), per AR4 / AR23.

**When** `BooksService.load()` is called,
**Then** it sets `loading.set(true)` and `loadError.set(null)`,
**And** fires `GET /v1/books`,
**And** on 200 sets `books.set(response)` and `loading.set(false)`,
**And** on error sets `loadError.set(ErrorService.parse(err))` and `loading.set(false)`.

**When** `BooksService.create(payload)` is called,
**Then** it fires `POST /v1/books` with the payload,
**And** on 201 prepends the created book to the books signal via `books.update(prev => [created, ...prev])` (immutable update per AR23) and returns the created `Book`,
**And** on error throws an `AppError` parsed via `ErrorService`.

**When** `BooksService.update(id, payload)` is called,
**Then** it fires `PATCH /v1/books/{id}`,
**And** on 200 replaces the matching row in the books signal via `books.update(prev => prev.map(b => b.id === id ? updated : b))`,
**And** on error throws an `AppError`.

**When** `BooksService.setStatus(id, next)` is called (the OPTIMISTIC path per UX-DR7),
**Then** the books signal is updated immediately with the new status (optimistic update),
**And** `PATCH /v1/books/{id}` is fired with body `{ status: next }`,
**And** on 2xx the optimistic value is confirmed (the server's authoritative row replaces the optimistic one),
**And** on 4xx/5xx the books signal is reverted to the prior status value,
**And** the original `AppError` is thrown so the calling component can render a row-level error.

**When** `BooksService.delete(id)` is called,
**Then** it fires `DELETE /v1/books/{id}`,
**And** on 204 removes the matching row from the books signal via `books.update(prev => prev.filter(b => b.id !== id))`,
**And** on error throws an `AppError`.

**Given** the test suite,
**When** `npm test` runs,
**Then** `books-service.spec.ts` exists and uses `HttpTestingController` plus signal-getter assertions,
**And** covers for each method: happy path, error path, and (for `setStatus`) the optimistic-then-revert path,
**And** all updates are verified to be immutable (no in-place mutation of arrays),
**And** Vitest coverage of `src/app/books/books-service.ts` + `book.types.ts` is ≥70%.

### Story 2.5: SPA — BookList page + BookForm (add variant) + states

As a signed-in user,
I want the `/books` view to render the add-book form at the top and a list of my books below it, with explicit loading, empty, populated, and load-error states,
So that I can see my list and add new books from a single screen without modal stacks.

**Acceptance Criteria:**

**Given** the following components exist:
- `spa/src/app/books/book-list-page.{ts,html,css,spec.ts}` (the route's page component, replacing the placeholder from Story 1.10),
- `spa/src/app/books/book-list.{ts,html,css,spec.ts}` (the list container),
- `spa/src/app/books/book-form.{ts,html,css,spec.ts}` with an `input()` signal `variant: 'add' | 'edit'`,
**And** the `/books` route in `app.config.ts` is updated from the Epic 1 placeholder to load `BookListPage`,

**Given** an authenticated user navigates to `/books`,
**When** `BookListPage` is activated,
**Then** it calls `BooksService.load()` on init,
**And** renders `TopChrome` (authenticated variant) with the `Settings` link in the middle,
**And** below `TopChrome`, in the centered 720px content column, renders: a section heading `"Books"` in `--text-page-title`, a `BookForm` with `variant="add"` at the top (per UX-DR4), and the `BookList` container below.

**Given** `BooksService.loading()` returns `true` and `books()` is empty,
**When** `BookList` renders,
**Then** it shows a single line `"Loading…"` in `--text-small` / `--color-text-muted` (per UX-DR5).

**Given** `BooksService.loadError()` is non-null,
**When** `BookList` renders,
**Then** it renders an `ErrorMessage` with the literal copy `"Couldn't load books — refresh to try again."` (per UX-DR12).

**Given** `BooksService.books()` is empty after a successful load,
**When** `BookList` renders,
**Then** it shows the empty-state line `"No books yet. Add one above."` in `--color-text-muted` (per UX-DR5),
**And** no illustration, no CTA button beyond the existing add form.

**Given** `BooksService.books()` has entries,
**When** `BookList` renders,
**Then** it renders a vertical stack of `BookRow` instances (the row component is fully implemented in Story 2.6 — for this story, a placeholder row showing just the title is acceptable and updated in 2.6) separated by 1px borders using `--color-border`.

**Given** `BookForm` is rendered with `variant="add"`,
**When** the user inspects the rendered form,
**Then** it contains three stacked inputs:
- A native `<input type="text">` for title with an associated `<label>Title</label>`,
- A native `<input type="number" min="1">` for pages with an associated `<label>Page count</label>`,
- A native `<select>` for status with options `to-read`, `reading`, `finished` (default `to-read`) with an associated `<label>Status</label>` — the full `StatusControl` component lands in Story 2.6,
**And** below the inputs a primary button reading `"Add book"` in `--color-accent` (per UX-DR14),
**And** no `Cancel` button is rendered in the `add` variant (Cancel is `edit`-only).

**When** the user submits the add form with valid input,
**Then** the button relabels to `"Adding…"` and is disabled (per UX-DR4),
**And** `BooksService.create(payload)` is called,
**And** on success: the form clears (inputs reset to empty + default status), the button restores to `"Add book"`, and the new book appears at the top of the list (the books signal already prepended it in Story 2.4).

**When** the user submits the add form and the BFF responds 422,
**Then** an `ErrorMessage` renders below the form (in `--text-small` / `--color-error`),
**And** the inputs preserve their entered values (per UX-DR15),
**And** the user can correct and resubmit.

**When** the user submits the form with missing title, with empty/whitespace-only title, or with `pages <= 0`,
**Then** validation runs on submit only (NOT on blur, per UX-DR15),
**And** an `ErrorMessage` renders below the form with appropriate copy,
**And** the inputs preserve their entered values.

**Given** the test suite,
**When** `npm test` runs,
**Then** specs exist and pass for:
- `BookListPage` (init calls load; renders TopChrome with Settings link),
- `BookList` (all four states: loading, empty, populated, load-error),
- `BookForm[variant=add]` (default state, submitting state, validation-error state, server-error state),
**And** tests use `HttpTestingController` and signal getters,
**And** Vitest coverage of the components touched in this story is ≥70%.

### Story 2.6: SPA — BookRow + StatusControl with optimistic UI + Edit/Delete

As a signed-in user,
I want each book in my list to display as a row with title, page count, a status control, an estimate cell placeholder (until Epic 4), and Edit / Delete secondary controls — with status changes being immediate (optimistic) and edits opening an inline form that replaces the row,
So that I can manage my books fluidly without page navigations or modals.

**Acceptance Criteria:**

**Given** the following components exist:
- `spa/src/app/books/book-row.{ts,html,css,spec.ts}`,
- `spa/src/app/books/status-control.{ts,html,css,spec.ts}`,
- `spa/src/app/books/estimate-cell.{ts,html,css,spec.ts}` as a **stub** that renders only a disabled `<button>` with text `"Estimate"` and a `title="Available in Epic 4"` attribute (no click behavior — the full component lands in Epic 4),

**Given** a Book row in the books signal,
**When** `BookRow` renders,
**Then** it renders as a flex container in the documented order:
- Title (left, primary text in `--text-body` / `--color-text`),
- `<n> pages` (in `--text-body` / `--color-text-muted`),
- `StatusControl`,
- `EstimateCell` stub,
- A secondary action group containing two text buttons: `Edit` and `Delete` (each in `--color-text`, underlined-on-hover, no surrounding fill, per UX-DR14),
**And** on hover, the row's background uses `--color-surface-muted` (per UX-DR6).

**Given** `StatusControl` is rendered with the book's current status,
**When** the user changes the value (a native `<select>` with the three options, or — at the implementer's discretion per UX-DR7 — a three-button segmented control built from `<button>` elements),
**Then** `BooksService.setStatus(book.id, newValue)` is called immediately,
**And** the UI reflects the new status optimistically (the books signal updates BEFORE the network round-trip completes),
**And** the `StatusControl` is disabled during the in-flight PATCH (per UX-DR7).

**When** the BFF responds 2xx to the status PATCH,
**Then** the `StatusControl` re-enables and the optimistic value persists.

**When** the BFF responds 4xx/5xx to the status PATCH,
**Then** the books signal is reverted to the prior status value (the `BooksService.setStatus` revert path from Story 2.4),
**And** the `StatusControl` re-enables (now showing the reverted value),
**And** a row-level `ErrorMessage` renders below the row's normal content with appropriate copy (e.g., `"Couldn't change status — try again"`).

**Given** a `BookRow` in display mode,
**When** the user clicks `Edit`,
**Then** the row is replaced in-place by a `BookForm` with `variant="edit"` pre-filled with the book's current title, pages, and status,
**And** the form's primary button reads `"Save"` (in `--color-accent`),
**And** a secondary `Cancel` text button is present.

**When** the user submits the edit form with valid input,
**Then** `BooksService.update(book.id, payload)` is called,
**And** the button relabels to `"Saving…"` and is disabled during the in-flight PATCH (per UX-DR4),
**And** on 2xx the form is dismissed and the row returns to display mode with the updated fields.

**When** the user clicks `Cancel` in the edit form,
**Then** the form is dismissed and the row returns to display mode unchanged.

**When** the edit submission fails (422 invalid, or 4xx/5xx server error),
**Then** an `ErrorMessage` renders below the form,
**And** the inputs preserve their entered values,
**And** the user can correct and resubmit.

**Given** a `BookRow` in display mode,
**When** the user clicks `Delete`,
**Then** a native `window.confirm("Delete this book?")` dialog is invoked (per UX-DR17 — no in-app modal),
**And** the Delete button styling is neutral (NOT red, per UX-DR14).

**When** the user clicks `Cancel` in the confirm dialog,
**Then** nothing further happens (no network call, row unchanged).

**When** the user clicks `OK` in the confirm dialog,
**Then** `BooksService.delete(book.id)` is called,
**And** on 204 the row is removed from the list (the books signal already filtered it in Story 2.4),
**And** on 4xx/5xx an inline `ErrorMessage` renders on the row, the row is preserved, and the user can retry.

**Given** the test suite,
**When** `npm test` runs,
**Then** specs exist and pass for `BookRow` (display mode, edit-mode swap, hover state assertion via class), `StatusControl` (default, optimistic update, optimistic-then-revert), and the `EstimateCell` stub (renders disabled button with the documented title attribute),
**And** tests mock `window.confirm` via a spy/override to verify delete behavior under both Cancel and OK paths,
**And** Vitest coverage of `book-row.ts`, `status-control.ts`, and `estimate-cell.ts` is ≥70%.

### Story 2.7: E2E spec — J2 manage books

As a reviewer of the OAuth/OIDC reference,
I want a Playwright E2E spec that exercises the full J2 journey against the running compose stack — add, optimistic status change, edit, delete with confirm, inline-error rendering, and cross-user isolation,
So that the second user journey is demonstrably correct on every CI-style run from the day Epic 2 ships.

**Acceptance Criteria:**

**Given** `e2e/tests/j2-manage-books.spec.ts` exists,
**When** the developer inspects it,
**Then** it uses `test.describe('J2: manage books', ...)` with a `beforeEach` that calls `resetState(request, { resetToken: process.env.TEST_RESET_TOKEN })` then `logInAs(page, testuser)`,
**And** contains at minimum these test cases:
- `adding a book makes it appear at the top of the list` — fills the add form (title `"Dune"`, pages `688`, status `"to-read"`), submits, asserts a row appears at the top of the list with those values, asserts the form clears,
- `status change is optimistic and persists on success` — changes a row's status from `"to-read"` to `"reading"` via the `StatusControl`, asserts the select's selected value updates immediately (before any network round-trip resolves), reloads the page after the PATCH completes and asserts the status is still `"reading"`,
- `editing a book replaces the row with a form and saves successfully` — clicks `Edit`, asserts the row is replaced by a form pre-filled with the current values, modifies the title to `"Dune Messiah"`, clicks `Save`, asserts the row returns to display mode with the new title,
- `cancelling an edit restores the original row` — opens edit, modifies a field, clicks `Cancel`, asserts the row returns unchanged,
- `deleting a book via native confirm removes the row` — registers `page.on('dialog', d => d.accept())`, clicks `Delete`, asserts the row is removed from the list,
- `cancelling delete in native confirm preserves the row` — registers `page.on('dialog', d => d.dismiss())`, clicks `Delete`, asserts the row remains,
- `invalid input (pages=0) shows inline error and preserves values` — submits the add form with `pages=0`, asserts an inline `ErrorMessage` is visible, asserts the input still holds the value `0`,
- `cross-user isolation: testuser does not see freshuser's books` — adds a book as `testuser`, calls `logOut` (a helper that clicks Log out), logs in as `freshuser` via `logInAs(page, freshuser)`, asserts the rendered book list is empty (the empty-state copy is visible),

**And** the specs use the helpers from `e2e/fixtures/helpers.ts` (`logInAs`, `resetState`); no inlined Keycloak credential filling or cookie shenanigans.

**When** the developer runs `docker compose --profile e2e up --abort-on-container-exit`,
**Then** all J2 specs pass alongside the J1 + J5 specs from Epic 1,
**And** the runner exits 0,
**And** on any failure, traces and screenshots are retained under `e2e/test-results/`.

---

## Epic 3: Reading Speed Settings (J4)

Stand up the Resource Server (scaffolded from the archetype), the JWKS-validated `oidc_bearer` plugin with scope enforcement, the `reading_speeds` table and scope-gated `/v1/reading-speed` GET/PUT endpoints, the BFF's `ResourceServerClient` with the 401-→-refresh-→-replay cycle, and the SPA's `SettingsView`. Result: J4 (adjust reading speed) is demonstrable end-to-end against the real running stack, the architectural NFRs around JWKS-based stateless RS authentication and OAuth scope enforcement are met, and the BFF's transparent token-refresh behavior is provable in tests.

### Story 3.1: RS scaffold from archetype + baseline health + RS in compose (default/dev)

As a developer working on the Resource Server,
I want the RS scaffolded from the `fastapi-archetype` with archetype gates green, a baseline `/health` endpoint, and the RS running in the compose `default` and `dev` profiles,
So that subsequent stories can build the auth and reading-speed surfaces against a working RS service.

**Acceptance Criteria:**

**Given** `tools/fastapi-archetype/` is cloned (gitignored),
**When** the developer runs `python tools/fastapi-archetype/scripts/build_template.py -n resource-server -o services/resource-server --description "BMAD_books Resource Server (reading speed, estimate)"`,
**Then** `services/resource-server/` contains the archetype's standard layout (`pyproject.toml`, `uv.lock`, `alembic.ini`, `alembic/`, `src/resource_server/`, `tests/`, `Dockerfile`, `.env.example`, `ErrorCode` enum, `log_io` AOP decorator).

**Given** the scaffolded RS,
**When** the developer runs `uv sync --frozen` inside `services/resource-server/`,
**Then** dependency installation succeeds,
**And** `uv run ruff check` passes with no findings,
**And** `uv run ty` passes with no type errors,
**And** `uv run pytest --cov` passes with coverage above the archetype's configured threshold (>90%).

**Given** the RS service container,
**When** the developer inspects `services/resource-server/Dockerfile`,
**Then** it is multi-stage on `python:3.14-slim` with an entrypoint that runs `uv run alembic upgrade head` before `exec uv run uvicorn resource_server.app:app --host 0.0.0.0 --port 8000`,
**And** the container mounts the named volume `rs_data` at `/data` for its SQLite file (per AR6).

**Given** the RS in compose,
**When** the developer inspects `compose/app.yml`,
**Then** the `resource-server` service is defined with `depends_on: { keycloak: { condition: service_healthy } }`,
**And** `env_file:` references `services/resource-server/.env` (gitignored),
**And** the service is included in the `default` and `dev` compose profiles (the `e2e` profile additions land in Story 3.6),
**And** the BFF's existing `depends_on` configuration is NOT changed to add the RS (the BFF still depends only on Keycloak, per the architecture's startup-ordering plan).

**Given** the running RS,
**When** the developer calls `GET /health` on the RS,
**Then** it returns 200 once the DB is reachable, Alembic is at head, AND the JWKS endpoint at `OIDC_JWKS_URL` is fetchable.

### Story 3.2: RS — `oidc_bearer` auth plugin (JWKS) + scope enforcement + synthetic-IdP test harness

As a developer enforcing the architectural NFRs (NFR4, NFR5, NFR7),
I want the RS to validate JWTs against the cached Keycloak JWKS, enforce required OAuth scopes per endpoint, and have a synthetic-IdP test harness so unit tests don't need a live Keycloak,
So that subsequent RS stories can register scope-gated dependencies (`require_scope("reading-speed:read")` / `require_scope("reading-speed:write")`) with confidence the validation and enforcement are correct.

**Acceptance Criteria:**

**Given** `src/resource_server/auth/oidc_bearer.py` exists,
**When** the developer inspects it,
**Then** it uses `PyJWT` (`pyjwt[crypto]`) + `PyJWKClient`,
**And** it is parameterized via env vars `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE` (consumed via the archetype's pydantic-settings config),
**And** it exposes a FastAPI dependency `get_authenticated_principal` that parses the `Authorization: Bearer <token>` header, validates the JWT (issuer, audience, expiry, signature against the cached JWKS), and returns a `Principal` object containing `sub`, `scopes` (parsed from the JWT `scope` space-delimited claim into a `set[str]`), and other claims of interest,
**And** it exposes `require_scope(scope: str)` — a dependency factory returning a FastAPI dependency that raises `InsufficientScopeError(error_code=ErrorCode.FORBIDDEN_SCOPE, http_status=403)` when the JWT lacks the requested scope.

**Given** the implementation reuses the archetype's `RoleMappingProvider` extension point (per architecture's "Cross-Cutting Concerns Mapping"),
**When** the developer inspects the diff against the archetype,
**Then** the new `oidc_bearer` mode is added as a sibling to `none`/`entra` and the existing modes are NOT broken (archetype's `tests/auth/` continues to pass).

**Given** `tests/auth/synthetic_idp.py` exists,
**When** the developer inspects it,
**Then** it generates a test RSA keypair at module load,
**And** monkey-patches the HTTP client used by `PyJWKClient` to serve a JWKS document containing the public key,
**And** exposes helpers to mint signed JWTs with arbitrary claims (`sub`, `scope`, `aud`, `iss`, `exp`),
**And** extends (rather than reinvents) the archetype's existing `entra`-mode synthetic-IdP pattern.

**Given** an endpoint declared with `Depends(require_scope("reading-speed:read"))` (a test fixture endpoint is sufficient for this story's tests),
**When** the endpoint is called with a JWT carrying `scope = "openid reading-speed:read"`,
**Then** the request reaches the handler and the `Principal` is populated with `sub` from the JWT.

**When** the endpoint is called with a JWT carrying `scope = "openid"` (no `reading-speed:read`),
**Then** the RS responds 403 with envelope `{"errorCode": "forbidden_scope", "message": "...", "detail": null}`.

**When** the endpoint is called with a JWT whose `exp` is in the past,
**Then** the RS responds 401 with envelope `{"errorCode": "session_expired", ...}`.

**When** the endpoint is called with a JWT whose `aud` does NOT include `OIDC_AUDIENCE`,
**Then** the RS responds 401 `session_expired`.

**When** the endpoint is called with a JWT whose `iss` does not match `OIDC_ISSUER_URL`,
**Then** the RS responds 401 `session_expired`.

**When** the endpoint is called with a malformed JWT (not three base64 segments, or non-JWT garbage),
**Then** the RS responds 401 `session_expired`.

**When** the endpoint is called with a JWT signed by a key whose `kid` is NOT in the JWKS cache,
**Then** the JWKS endpoint is re-fetched exactly once (key rotation handling),
**And** if the key is found, validation proceeds normally,
**And** if the key is still not found, the request is rejected 401.

**When** the endpoint is called without any `Authorization` header,
**Then** the RS responds 401 `session_expired`.

**Given** the test suite,
**When** `uv run pytest tests/auth/` runs,
**Then** tests cover every path enumerated above plus: JWKS cache hit avoids re-fetch (`PyJWKClient` HTTP mock asserted called once across N repeated valid requests),
**And** coverage of `src/resource_server/auth/oidc_bearer.py` is ≥90%,
**And** the archetype's existing auth tests continue to pass.

### Story 3.3: RS — `ReadingSpeed` model + migration + `/v1/reading-speed` GET/PUT (scope-gated)

As a signed-in user (eventually, via the SPA),
I want the RS to expose GET and PUT on `/v1/reading-speed` strictly scoped to my `sub` (read from the JWT) and gated by the appropriate OAuth scopes,
So that my reading speed is stored on the RS and cannot be read or modified by anyone else's session, and the architectural scope-split is enforced where the PRD requires (at the RS, not the BFF).

**Acceptance Criteria:**

**Given** `src/resource_server/db/models/reading_speed.py` exists,
**When** the developer inspects it,
**Then** a `ReadingSpeed` SQLModel exists with columns: `id` (PK, int, autoincrement), `sub` (str(255), NOT NULL, UNIQUE, indexed), `pages_per_hour` (int, NOT NULL, application-enforced `ge=1`), `created_at` (datetime, NOT NULL), `updated_at` (datetime, NOT NULL, onupdate),
**And** the table name is `reading_speeds`,
**And** the UNIQUE+index on `sub` is declared.

**Given** `src/resource_server/api/schemas/reading_speed.py` exists,
**When** the developer inspects it,
**Then** `ReadingSpeedOut` has `pages_per_hour: int`,
**And** `ReadingSpeedUpsert` (the request body type for PUT) has `pages_per_hour: int` (constrained `ge=1`),
**And** these are distinct from the SQLModel (per AR20).

**Given** the migration file `alembic/versions/0001_init.py` exists in the RS's `alembic/versions/`,
**When** the developer runs `uv run alembic upgrade head`,
**Then** the `reading_speeds` table is created with all columns, constraints, and the UNIQUE/index on `sub`.

**Given** `src/resource_server/api/reading_speed.py` registers an `APIRouter` mounted at `/v1/reading-speed`,
**And** `src/resource_server/services/reading_speed_service.py` exposes `get_for_user(session, sub)` and `upsert(session, sub, pages_per_hour)`,
**And** `src/resource_server/core/exceptions.py` declares `ReadingSpeedUnsetError` with `error_code = ErrorCode.READING_SPEED_UNSET` (HTTP 412),
**And** the RS `ErrorCode` enum includes `READING_SPEED_UNSET`.

**Given** a valid JWT with scope `reading-speed:read` and `sub = S`,
**When** `GET /v1/reading-speed` is called with `Authorization: Bearer <token>`,
**Then** if a `reading_speeds` row exists for `sub = S`, the RS responds 200 with body `{"pages_per_hour": <n>}`.

**When** `GET /v1/reading-speed` is called for a JWT whose `sub` has no `reading_speeds` row,
**Then** the RS responds 412 with envelope `{"errorCode": "reading_speed_unset", "message": "...", "detail": null}` (NOT 404 — per architecture's "Format Patterns" footnote).

**When** `GET /v1/reading-speed` is called with a JWT carrying ONLY `reading-speed:write` (no read scope),
**Then** the RS responds 403 `forbidden_scope`.

**Given** a valid JWT with scope `reading-speed:write` and `sub = S`,
**When** `PUT /v1/reading-speed` is called with body `{"pages_per_hour": 30}`,
**Then** the RS upserts the row for `sub = S` (insert if missing, update if exists),
**And** responds 200 with body `{"pages_per_hour": 30}`,
**And** `updated_at` is bumped.

**When** `PUT /v1/reading-speed` is called with a JWT carrying ONLY `reading-speed:read` (no write scope),
**Then** the RS responds 403 `forbidden_scope`.

**When** `PUT /v1/reading-speed` is called with body `{"pages_per_hour": 0}` or any non-positive integer,
**Then** the RS responds 422 with envelope `{"errorCode": "invalid_input", ...}`.

**When** `PUT /v1/reading-speed` is called with body missing `pages_per_hour`, or with the field as a non-integer string,
**Then** the RS responds 422 `invalid_input`.

**When** any `/v1/reading-speed` request is called WITHOUT a valid JWT (missing `Authorization`, expired, wrong audience, wrong issuer, malformed),
**Then** the RS responds 401 `session_expired` (the Story 3.2 plumbing applies uniformly).

**Given** two distinct users with subs `S1` and `S2` each having `reading_speeds` rows,
**When** the JWT for `S1` is used to `GET /v1/reading-speed`,
**Then** only `S1`'s row is returned (cross-user isolation enforced by reading sub from the JWT — never from a body or path).

**When** the JWT for `S1` is used to PUT a new value,
**Then** only `S1`'s row is updated; `S2`'s row is unchanged.

**Given** the test suite,
**When** `uv run pytest tests/api/test_reading_speed.py tests/services/test_reading_speed_service.py` runs,
**Then** tests cover (using the synthetic-IdP harness from Story 3.2 to mint JWTs with the necessary scope/sub combinations): GET happy with row, GET 412 without row, GET wrong-scope 403, GET no-JWT 401, PUT happy (insert path + update path via upsert), PUT wrong-scope 403, PUT invalid-input 422, PUT no-JWT 401, cross-user isolation on GET and PUT,
**And** coverage of `reading_speed.py` (API) and `reading_speed_service.py` (service) is ≥90%.

### Story 3.4: RS — `POST /v1/test/reset` endpoint

As a maintainer running E2E tests,
I want the RS to expose a guarded `POST /v1/test/reset` endpoint truncating the `reading_speeds` table, with the same `ENABLE_TEST_RESET` + `TEST_RESET_TOKEN` gating as the BFF's,
So that the J4 (and Epic 4's J3/J6) Playwright specs can rely on a deterministic empty reading-speed state.

**Acceptance Criteria:**

**Given** the RS starts with `ENABLE_TEST_RESET` unset or any value other than `"true"`,
**When** any HTTP method hits `/v1/test/reset` on the RS,
**Then** the response is the standard 404 envelope (the route is not registered, matching Story 1.12's pattern on the BFF).

**Given** the RS starts with `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN` set,
**When** `POST /v1/test/reset` is called without `Authorization` or with the wrong bearer,
**Then** the RS responds 401.

**When** `POST /v1/test/reset` is called with the correct `Authorization: Bearer ${TEST_RESET_TOKEN}`,
**Then** the RS truncates all rows in `reading_speeds`,
**And** responds 204 with empty body.

**Given** the `e2e` compose profile,
**When** the developer inspects `compose/app.yml` (the changes land here as part of Story 3.6, but the endpoint exists from this story),
**Then** the RS service in the `e2e` profile will have `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN=<value>` set (the value matches the BFF's so the same env var works for both).

**Given** the prod build (`default` profile),
**When** the developer inspects the env values,
**Then** `ENABLE_TEST_RESET` is NOT set on the RS,
**And** the route is not registered.

**Given** the test suite,
**When** `uv run pytest tests/api/test_reset.py` (on the RS) runs,
**Then** tests cover: route-not-registered when env off (404), missing bearer rejected, wrong bearer rejected, correct bearer truncates `reading_speeds`, response 204 with empty body,
**And** coverage of `src/resource_server/api/test_reset.py` is ≥90%.

### Story 3.5: BFF `ResourceServerClient` (with refresh-and-replay) + `/v1/reading-speed` GET/PUT proxy + SPA `SettingsView` + `ReadingSpeedService` + `/settings` route

As a signed-in user,
I want to navigate to `/settings`, view my current reading speed (or an empty input if I haven't set one yet), save a new value, see a brief `"Saved"` acknowledgement on success, and see a distinct named error if the Resource Server is unavailable — all without ever knowing about access tokens, refresh tokens, or scope strings,
So that the J4 user surface works end-to-end and the BFF's transparent token-refresh behavior (NFR3) is exercised on cross-service calls.

**Acceptance Criteria:**

#### BFF side: `ResourceServerClient` and `/v1/reading-speed` proxy

**Given** `src/bff/services/resource_server_client.py` exists with a `ResourceServerClient` class,
**When** the developer inspects it,
**Then** it wraps a plain `httpx.AsyncClient`,
**And** it is configured with `connect=5s, read=10s` timeouts (per AR19),
**And** it exposes methods `get_reading_speed(session: Session)` and `put_reading_speed(session: Session, payload)` (each accepting the session record so they can read and update the access_token / refresh_token),
**And** `compute_estimate` is NOT yet implemented (deferred to Epic 4 Story 4.2).

**Given** `src/bff/api/reading_speed.py` registers an `APIRouter` mounted at `/v1/reading-speed`,
**And** the routes require a valid session cookie (return 401 `session_expired` if absent) and — on PUT — a valid `X-CSRF-Token` (return 403 `csrf_invalid` if invalid),

**Given** an authenticated session with a fresh, valid access_token,
**When** the SPA calls `GET /v1/reading-speed` with the session cookie,
**Then** the BFF retrieves the access_token from the session, calls `GET /v1/reading-speed` on the RS with `Authorization: Bearer <access_token>`,
**And** on RS 200, the BFF responds 200 with the same body (resource passes through unchanged),
**And** on RS 412, the BFF responds 412 with the envelope `{"errorCode": "reading_speed_unset", ...}` (forwarded directly),
**And** on RS 403, the BFF responds 403 with `errorCode: "forbidden_scope"`.

**When** the SPA calls `PUT /v1/reading-speed` with body `{"pages_per_hour": 30}` and a valid CSRF header,
**Then** the BFF calls `PUT /v1/reading-speed` on the RS with `Authorization: Bearer <access_token>` and the same body,
**And** on RS 2xx, the BFF responds with the RS body,
**And** on RS 422, the BFF responds 422 with `errorCode: "invalid_input"`,
**And** on RS 403, the BFF responds 403 `forbidden_scope`.

**Given** the refresh-and-replay path (the architectural NFR3 demonstration on this epic),
**When** the SPA calls GET or PUT `/v1/reading-speed`,
**And** the RS returns 401 on the first attempt (access token expired or invalidated),
**Then** the BFF calls Keycloak's `/token` endpoint with `grant_type=refresh_token` using the session's refresh_token,
**And** on successful refresh, the BFF stores the new access_token (and any rotated refresh_token) on the `sessions` row,
**And** the BFF retries the RS call exactly ONCE with the new access_token,
**And** the retry's response is forwarded to the SPA normally,
**And** no further retries are attempted regardless of the retry's outcome (per AR19 — "single refresh-and-replay cycle only").

**When** the Keycloak refresh call itself fails (Keycloak rejects the refresh_token, network error, or 4xx/5xx),
**Then** the BFF deletes the `sessions` row, clears both the session cookie and the `csrf_token` cookie (Max-Age=0), and responds 401 with `errorCode: "session_expired"`,
**And** the SPA's global 401 handler (Story 1.9) routes the user to `/login?return_to=<current_url>`.

**When** the refresh succeeds but the retry STILL returns 401 from the RS (an unusual condition that could indicate a scope/audience configuration drift),
**Then** the BFF responds 401 `session_expired` to the SPA without further retries,
**And** the `sessions` row is left in place (the SPA's redirect to `/login` will produce a new session that overwrites it on next login).

**Given** the RS is unreachable from the BFF (connection refused, DNS failure, read timeout, or RS returns any 5xx),
**When** the SPA calls `GET` or `PUT /v1/reading-speed`,
**Then** the BFF responds 503 with envelope `{"errorCode": "resource_server_unavailable", ...}` (per FR-ERROR-01 / AR17),
**And** the BFF does NOT retry the request (no silent cross-service retries per AR19).

**Given** identity propagation (NFR6),
**When** the BFF makes any RS call,
**Then** the BFF never adds `sub` to the request body or path; the RS reads `sub` from the JWT only.

#### SPA side: `ReadingSpeedService`, `SettingsPage`, `/settings` route

**Given** the following SPA pieces exist:
- `spa/src/app/settings/settings-page.{ts,html,css,spec.ts}` (replaces the placeholder from Story 1.10),
- `spa/src/app/settings/reading-speed-service.{ts,spec.ts}` (`@Injectable({providedIn: 'root'})`),
- `spa/src/app/settings/reading-speed.types.ts` exporting `interface ReadingSpeedOut { pages_per_hour: number }`,
- The `/settings` route in `app.config.ts` is updated to load `SettingsPage` (replacing the placeholder),

**Given** `ReadingSpeedService` exposes the following reactive state:
- `readonly pagesPerHour = signal<number | null>(null)` — `null` means "unset" (the legitimate 412 condition),
- `readonly loading = signal<boolean>(false)`,
- `readonly loadError = signal<AppError | null>(null)`,
- `readonly saving = signal<boolean>(false)`,
- `readonly saveError = signal<AppError | null>(null)`,
- `readonly justSaved = signal<boolean>(false)` — toggled true for ~1s after a successful save,
**And** methods `load(): Promise<void>` and `save(value: number): Promise<void>`.

**When** `ReadingSpeedService.load()` is called,
**Then** it sets `loading.set(true)` and `loadError.set(null)`, fires `GET /v1/reading-speed`,
**And** on 200 sets `pagesPerHour.set(response.pages_per_hour)`, `loading.set(false)`,
**And** on 412 sets `pagesPerHour.set(null)` and `loadError.set(null)` (412 is the legitimate unset state for first-time users — NOT a load error),
**And** on 503 sets `loadError` to an `AppError { kind: 'resource_server_unavailable' }`,
**And** on 401 the global handler (Story 1.9) takes over (no SPA-level error state needed).

**When** `ReadingSpeedService.save(value)` is called,
**Then** it sets `saving.set(true)` and `saveError.set(null)`, fires `PUT /v1/reading-speed` with body `{"pages_per_hour": value}`,
**And** on 2xx sets `pagesPerHour.set(response.pages_per_hour)`, toggles `justSaved` to `true` for ~1s then back to `false`, sets `saving.set(false)`,
**And** on 422 sets `saveError` to `AppError { kind: 'invalid_input', ... }`, `saving.set(false)`,
**And** on 503 sets `saveError` to `AppError { kind: 'resource_server_unavailable' }`, `saving.set(false)`,
**And** on 401 the global handler takes over.

**Given** the user navigates to `/settings`,
**When** `SettingsPage` is activated,
**Then** it calls `ReadingSpeedService.load()` on init,
**And** renders `TopChrome` (authenticated variant) — `TopChrome` from Story 1.10 already swaps its contextual route link to "Books" when on `/settings`,
**And** below `TopChrome`, in the centered 720px column:
- A section heading `"Reading speed"` in `--text-page-title`,
- One labelled native `<input type="number" min="1">` with `<label>Pages per hour</label>` and helper text below in `--text-small` / `--color-text-muted` reading `"e.g., 30"`,
- One primary button `"Save"` in `--color-accent`.

**Given** `loading()` is true on first navigation,
**When** `SettingsPage` renders,
**Then** the input is disabled and the button is disabled (or a single `"Loading…"` line is rendered nearby per UX-DR11 — implementer's choice consistent with UX patterns).

**Given** `pagesPerHour()` resolves to a number `n` and `loadError()` is null,
**When** `SettingsPage` renders,
**Then** the input is populated with `n`,
**And** the helper text `"e.g., 30"` remains visible (it is a stable cue, not an error).

**Given** `pagesPerHour()` resolves to `null` (the unset state from 412) and `loadError()` is null,
**When** `SettingsPage` renders,
**Then** the input is rendered empty,
**And** the helper text `"e.g., 30"` is the only visual cue (per UX-DR9: "loaded with no value yet — input is empty, helper text is the primary cue"),
**And** NO `ErrorMessage` is rendered (412 is not an error from the user's perspective).

**Given** `loadError()` is `{ kind: 'resource_server_unavailable' }`,
**When** `SettingsPage` renders,
**Then** an inline `ErrorMessage` renders near the input with literal copy `"Service unavailable — try again shortly"` in `--color-error` (per UX-DR12).

**When** the user types a value and clicks `"Save"`,
**Then** validation runs ON SUBMIT only (NOT on blur, per UX-DR15),
**And** if the value is not a positive integer (zero, negative, empty, non-numeric), an inline `ErrorMessage` renders below the input with copy `"Enter a positive number"` (per UX-DR9), the input preserves its entered value, the button is NOT relabeled, and no network call is made,
**And** if the value is a positive integer, the button relabels to `"Saving…"` and disables, and `ReadingSpeedService.save(value)` is called.

**When** the save succeeds,
**Then** the button briefly relabels to `"Saved"` for ~1s (the `justSaved` signal is bound to this), then back to `"Save"` (per UX-DR9),
**And** the new value persists in the input.

**When** the save fails with 503,
**Then** an inline `ErrorMessage` renders below the input with literal copy `"Service unavailable — try again shortly"` in `--color-error`,
**And** the button restores to `"Save"`,
**And** the input preserves its entered value.

**When** the save fails with 422,
**Then** an inline `ErrorMessage` renders with the validation copy (`"Enter a positive number"` for the obvious positive-integer case, or a derived message for other invalid-input shapes),
**And** the button restores,
**And** the input preserves its entered value.

#### Tests

**Given** the BFF test suite,
**When** `uv run pytest tests/api/test_reading_speed_proxy.py tests/services/test_resource_server_client.py` runs,
**Then** proxy tests cover: happy GET, happy PUT, missing session 401, missing CSRF on PUT 403, RS 412 forwarded, RS 403 forwarded, RS 422 forwarded, RS connection error → 503, RS read timeout → 503 (verified by simulating a slow response), RS 5xx → 503, no-retry behavior on 5xx (assert mock called exactly once),
**And** `ResourceServerClient` tests cover (using the synthetic-IdP harness from Stories 1.5/3.2 to mint expired and fresh tokens, and to simulate Keycloak's refresh-token responses): refresh-and-replay happy path (RS 401 → refresh succeeds → retry → 2xx), refresh succeeds but retry still 401 (no second retry, BFF returns 401), refresh itself fails (BFF clears session + cookies, responds 401), `sub` never injected into request body or path,
**And** coverage of `src/bff/services/resource_server_client.py` and `src/bff/api/reading_speed.py` is ≥90%.

**Given** the SPA test suite,
**When** `npm test` runs,
**Then** `reading-speed-service.spec.ts` covers each branch: load happy with value, load 412 (sets `pagesPerHour` to null, sets `loadError` to null), load 503 (sets `loadError`), save happy (with `justSaved` toggle observed across the ~1s window), save 422, save 503,
**And** `settings-page.spec.ts` covers: loading state, value state, unset state (412 — input empty, helper visible, no error), load-error state (503), validation-error path on submit, successful save with `"Saved"` pulse, save-error states,
**And** the `TopChrome` test from Story 1.10 is re-verified (or extended) to assert the contextual route link reads `"Books"` when the active route is `/settings`,
**And** Vitest coverage of `src/app/settings/` is ≥70%.

### Story 3.6: E2E spec — J4 adjust reading speed + compose `e2e` profile updates + `killRs`/`startRs`/`resetState` helpers

As a reviewer of the OAuth/OIDC reference,
I want a Playwright E2E spec that drives the full J4 journey against the running stack — including the freshuser unset state, a successful save with the "Saved" pulse, persistence across page reload, validation rejection, and a 503-on-save when the RS is down — AND the compose `e2e` profile + helpers updated so `killRs`/`startRs` actually work (preparing Epic 4's J6 spec),
So that the fourth journey is demonstrably correct on every CI-style run and the harness is ready for J6 the moment Epic 4 ships.

**Acceptance Criteria:**

#### Compose `e2e` profile updates

**Given** the `e2e` compose profile from Story 1.11,
**When** the developer inspects `compose/app.yml` after this story's changes,
**Then** the Playwright runner's `depends_on` now includes `resource-server: { condition: service_healthy }` in addition to `bff` and `keycloak`,
**And** the `resource-server` service in the `e2e` profile has `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN=<matching the BFF's value>` set.

#### Helpers go from stub to real

**Given** `e2e/fixtures/helpers.ts` had `killRs`/`startRs` stubs from Story 1.11 (throwing `"RS not yet present (Epic 3)"`),
**When** the developer implements them in this story,
**Then** `killRs()` stops the `resource-server` container (e.g., by calling `docker compose stop resource-server` via the docker-socket binding into the Playwright runner container, OR via a small REST shim — implementer's choice),
**And** `startRs()` restarts the RS and `await`s its `/health` reporting 200 (with a sensible upper-bound timeout),
**And** both helpers are idempotent (calling `startRs` when RS is already running is a no-op; calling `killRs` when already stopped is a no-op).

**Given** the `resetState(request, opts)` helper from Story 1.11/2.3,
**When** the developer extends it in this story,
**Then** it now ALSO calls `POST /v1/test/reset` on the RS with the same bearer token,
**And** the helper's call signature is unchanged (the J1/J5/J2 specs continue to work without edits).

#### J4 spec

**Given** `e2e/tests/j4-adjust-speed.spec.ts` exists,
**When** the developer inspects it,
**Then** it uses `test.describe('J4: adjust reading speed', ...)` with a default `beforeEach` that calls `resetState` then `logInAs(page, testuser)`,
**And** an `afterEach` that calls `startRs()` to guard against a previous test having left the RS stopped,
**And** contains at minimum these test cases:
- `freshuser sees the unset state on first /settings visit` — overrides `beforeEach` to log in as `freshuser` (whose `reading_speeds` row was truncated by `resetState`), navigates to `/settings`, asserts the pages-per-hour input is empty, asserts the helper text `"e.g., 30"` is visible, asserts NO `ErrorMessage` is shown (412 is the legitimate unset state, not an error),
- `setting a value shows the Saved pulse and persists across reload` — navigates to `/settings`, fills `30`, clicks `Save`, asserts the button briefly shows `"Saved"` within 2s (use `expect(button).toHaveText('Saved', { timeout: 2000 })`), reloads the page, asserts the input shows `30` after load,
- `validation rejects pages_per_hour = 0 and preserves the typed value` — types `0`, clicks `Save`, asserts an inline error renders with positive-number copy, asserts the input still shows `0`, asserts no network call to `/v1/reading-speed` PUT happened (`page.route` interception verification),
- `save while RS is down renders the named 503 error` — calls `killRs()`, navigates to `/settings`, fills `30`, clicks `Save`, asserts the error `"Service unavailable — try again shortly"` is visible in the error color, then calls `startRs()` to restore state,
- `load while RS is down renders the named 503 error` — calls `killRs()`, navigates to `/settings` (a fresh page that triggers `load()`), asserts the error `"Service unavailable — try again shortly"` is visible, then calls `startRs()` to restore state,

**And** the specs use the helpers from `e2e/fixtures/helpers.ts`; no inlined credential filling, docker-stop commands, or token shenanigans.

**When** the developer runs `docker compose --profile e2e up --abort-on-container-exit`,
**Then** all J4 specs pass alongside the J1, J5, and J2 specs from earlier epics,
**And** the runner exits 0,
**And** on any failure, traces and screenshots are retained under `e2e/test-results/`.

---

## Epic 4: Reading-Time Estimate & Honest Failure (J3, J6)

Layer the defining cross-service interaction onto the foundation built by Epic 3: the RS exposes a scope-gated `/v1/estimate` returning a formatted duration string, the BFF exposes `/v1/books/{id}/estimate` looking up the book by `(sub, id)` and brokering the RS call, and the SPA's `EstimateCell` (replacing the Epic 2 stub) renders all four UX-spec'd states inline in the book row. The honest-failure surface for J6 (`"Service unavailable — try again shortly"`) is the same component's error variant, demonstrated by killing the RS container in a Playwright spec.

### Story 4.1: RS — `POST /v1/estimate` endpoint + `estimate_service` + `format_duration` helper

As a developer enabling the marquee architectural interaction,
I want the RS to expose `POST /v1/estimate` that computes a user's reading time from their stored reading speed and the request's book pages, scope-gated by `reading-speed:read`, returning a formatted duration string the SPA can render directly,
So that the BFF can broker estimates without the SPA ever needing to format durations or know about the cross-service split.

**Acceptance Criteria:**

**Given** `src/resource_server/api/estimate.py` registers an `APIRouter` mounted at `/v1/estimate`,
**And** `src/resource_server/services/estimate_service.py` exposes `compute_for_user(session, sub, pages)`,
**And** `src/resource_server/api/schemas/estimate.py` exports:
- `EstimateIn` with `pages: int` (constrained `ge=1`),
- `EstimateOut` with `minutes: int` and `formatted: str`,

**Given** a duration-formatting helper at `src/resource_server/services/duration.py` exposes `format_duration(minutes: int) -> str`,
**When** the helper is tested with boundary inputs,
**Then** the following outputs hold (with `≈` as the leading character per UX-DR18 examples):
- `format_duration(1)` → `"≈ 1 m"`,
- `format_duration(12)` → `"≈ 12 m"`,
- `format_duration(60)` → `"≈ 1 h"`,
- `format_duration(61)` → `"≈ 1 h 1 m"`,
- `format_duration(260)` → `"≈ 4 h 20 m"`,
- `format_duration(1440)` → `"≈ 1 d"`,
- `format_duration(1441)` → `"≈ 1 d 1 m"`,
- `format_duration(1500)` → `"≈ 1 d 1 h"`,
- `format_duration(2780)` → `"≈ 1 d 22 h 20 m"` (or `"≈ 1 d 22 h"` if the implementer chooses to omit minutes when days are present — pick one rule and pin it in the tests).

**Given** a valid JWT with scope `reading-speed:read` and `sub = S`,
**And** a `reading_speeds` row exists for `sub = S` with `pages_per_hour = p`,
**When** `POST /v1/estimate` is called with body `{"pages": n}` (and a valid `Authorization: Bearer <token>`),
**Then** `estimate_service.compute_for_user(session, S, n)` computes `minutes` deterministically from `(p, n)` using a pinned rounding rule (e.g., `math.ceil(n * 60 / p)`),
**And** the RS responds 200 with body `{"minutes": <minutes>, "formatted": format_duration(minutes)}`.

**When** `POST /v1/estimate` is called with a JWT carrying only `reading-speed:write` (no read scope),
**Then** the RS responds 403 with `errorCode: "forbidden_scope"`.

**When** `POST /v1/estimate` is called for a JWT whose `sub` has no `reading_speeds` row (the J3 precondition path exercised by `freshuser`),
**Then** the RS responds 412 with envelope `{"errorCode": "reading_speed_unset", ...}`.

**When** `POST /v1/estimate` is called with body `{"pages": 0}` or any non-positive integer,
**Then** the RS responds 422 with `errorCode: "invalid_input"`.

**When** `POST /v1/estimate` is called with body missing `pages`, or with `pages` as a non-integer,
**Then** the RS responds 422 `invalid_input`.

**When** `POST /v1/estimate` is called without a valid `Authorization` header (missing, malformed, expired, wrong audience, wrong issuer),
**Then** the RS responds 401 with `errorCode: "session_expired"` (the Story 3.2 plumbing applies uniformly).

**Given** identity propagation (NFR6),
**When** `POST /v1/estimate` is called with a body containing additional fields like `"sub": "<spoof>"`,
**Then** any such `sub`-injection attempt is ignored; the estimate is always computed against the JWT's `sub` claim only (the body is validated against `EstimateIn` which has only `pages` — extra fields are either ignored or rejected, consistent with the project's choice in Story 2.2).

**Given** the test suite,
**When** `uv run pytest tests/api/test_estimate.py tests/services/test_estimate_service.py tests/services/test_duration.py` runs,
**Then** tests cover: happy path (with synthetic IdP minting a `reading-speed:read` JWT), 412 unset, 403 wrong scope, 422 invalid input, 401 no JWT, sub-injection-via-body ignored, and the full `format_duration` boundary table above,
**And** coverage of `estimate.py`, `estimate_service.py`, and `duration.py` is ≥90%.

### Story 4.2: BFF — `POST /v1/books/{id}/estimate` + `ResourceServerClient.compute_estimate`

As a signed-in user (via the SPA),
I want the BFF to expose `POST /v1/books/{id}/estimate` that looks up my book by `(sub, id)`, brokers the RS estimate call with my bearer token, and returns the formatted duration — or an honest named failure if the RS is down,
So that the SPA can request estimates without ever talking to the RS directly and without needing to know my access token, scopes, or reading-speed value.

**Acceptance Criteria:**

**Given** `src/bff/api/books.py` registers a new endpoint `POST /v1/books/{id}/estimate` on the existing books router,
**And** `src/bff/services/resource_server_client.py` adds a method `compute_estimate(session: Session, pages: int) -> EstimateOut` alongside Epic 3's `get_reading_speed` / `put_reading_speed`,
**And** the endpoint requires a valid session cookie (returns 401 `session_expired` if absent) and a valid `X-CSRF-Token` (returns 403 `csrf_invalid` if invalid).

**Given** an authenticated session with `sub = S` and an existing book `id = B` owned by `S` (with `pages = 688`),
**When** `POST /v1/books/{B}/estimate` is called with valid session + CSRF,
**Then** the BFF looks up the book by `(sub=S, id=B)` via `books_service.get_for_user(session, S, B)` BEFORE making any RS call,
**And** calls `ResourceServerClient.compute_estimate(session, pages=688)`,
**And** when the RS responds 200 with body `{"minutes": 1376, "formatted": "≈ 22 h 56 m"}`, the BFF responds 200 with the same body (resource passes through unchanged).

**When** `POST /v1/books/{B}/estimate` is called for a book id that does not exist OR is owned by a different `sub`,
**Then** the BFF responds 404 with `errorCode: "book_not_found"` (the existence-check happens BEFORE the RS call — we don't leak book existence to other users, and we don't fan a useless RS call out for missing books).

**When** the RS responds 412 (`reading_speed_unset`),
**Then** the BFF responds 412 with `errorCode: "reading_speed_unset"` (forwarded directly).

**When** the RS responds 403 (`forbidden_scope`),
**Then** the BFF responds 403 with `errorCode: "forbidden_scope"` (forwarded directly).

**When** the RS responds with a connection error, DNS failure, read timeout (>10s), or any 5xx,
**Then** the BFF responds 503 with envelope `{"errorCode": "resource_server_unavailable", ...}` (per FR-ERROR-01 / AR17),
**And** the BFF does NOT retry the request (no silent retries on 5xx per AR19).

**When** the RS responds 401 on the first attempt (access token expired),
**Then** the BFF's existing refresh-and-replay cycle from Story 3.5 kicks in: refresh the access token at Keycloak, retry the RS call exactly once with the new token,
**And** the retry's outcome is forwarded per the rules above,
**And** if the Keycloak refresh itself fails, the BFF deletes the session row, clears cookies, and responds 401 `session_expired`.

**Given** identity propagation (NFR6),
**When** the BFF calls the RS,
**Then** the BFF never adds `sub` to the request body or path; the RS reads `sub` from the JWT only.

**When** `POST /v1/books/{B}/estimate` is called without a session cookie,
**Then** the BFF responds 401 `session_expired`.

**When** `POST /v1/books/{B}/estimate` is called without a valid `X-CSRF-Token`,
**Then** the BFF responds 403 `csrf_invalid`.

**Given** the test suite,
**When** `uv run pytest tests/api/test_books.py::test_estimate_* tests/services/test_resource_server_client.py::test_compute_estimate_*` runs,
**Then** tests cover (using the synthetic-IdP harness from Stories 1.5/3.2 + httpx-mock for the RS): happy path (RS 200), 412 forwarded, 403 forwarded, 422 forwarded, RS connection error → 503, RS 10s+ timeout → 503, RS 5xx → 503 (assert RS called exactly once — no retry), refresh-and-replay happy (RS 401 → refresh → retry → 2xx), refresh fails → BFF 401 + session cleared, book-not-found 404 (asserted to short-circuit before RS is called via httpx-mock call-count assertion), cross-user 404 (same short-circuit), no session 401, no CSRF 403, `sub`-never-injected (test inspects the actual outgoing httpx request body and path),
**And** coverage of the new endpoint code and `compute_estimate` method is ≥90%.

### Story 4.3: SPA — `EstimateCell` (real component) + `AppError` extensions + BookRow integration

As a signed-in user,
I want each book row to expose an "Estimate" button that, when clicked, briefly disables and relabels itself, then returns either a formatted reading-time duration with a "Re-estimate" affordance, or a distinct named error rendered in the same cell,
So that the cross-service estimate works inline in the row exactly as the UX spec describes — no modal, no toast, no fabricated values.

**Acceptance Criteria:**

**Given** the Epic 2 stub at `spa/src/app/books/estimate-cell.ts` is REPLACED in this story by a fully implemented standalone component (the disabled `<button title="Available in Epic 4">` is removed),
**And** `spa/src/app/shared/errors/app-error.types.ts` is extended so the `AppError` discriminated union includes the variant `{ kind: 'reading_speed_unset' }` (the `resource_server_unavailable` variant was added in Epic 3 Story 3.5; this story adds the new variant only),
**And** `spa/src/app/shared/errors/error-service.ts` is updated to map the BFF's `reading_speed_unset` envelope to that new `AppError` kind,
**And** `spa/src/app/books/books-service.ts` gains `requestEstimate(bookId: number): Promise<EstimateOut>` firing `POST /v1/books/{id}/estimate`,
**And** `spa/src/app/books/estimate.types.ts` exports `interface EstimateOut { minutes: number; formatted: string }`.

**Given** `EstimateCell` is a standalone Angular component accepting `bookId` (number) and `pages` (number) via `input()` signals — or accepting the full `Book` object if cleaner,
**When** `EstimateCell` first renders (its initial / idle state),
**Then** it shows a single primary button labeled `"Estimate"` styled in `--color-accent` (per UX-DR8 idle state / UX-DR14 button hierarchy).

**When** the user clicks `"Estimate"`,
**Then** the component fires `BooksService.requestEstimate(bookId)`,
**And** transitions immediately to the loading state per UX-DR8 / UX-DR13 (pessimistic UI): the button is disabled and relabels to `"Estimating…"`,
**And** no other state on the page is mutated (no spinner overlay, no skeleton — per UX-DR11).

**Given** the request succeeds with body `{ minutes, formatted }`,
**When** `EstimateCell` re-renders,
**Then** the button is replaced in-place by the formatted text directly (e.g., `"≈ 4 h 20 m"`) rendered in `--text-body` / `--color-text` (per UX-DR18 — the SPA renders `response.formatted` verbatim, NOT a number formatted on the client),
**And** adjacent to the formatted text, a small `"Re-estimate"` text button is rendered (`--color-text`, underlined-on-hover, no surrounding fill, per UX-DR14).

**When** the user clicks `"Re-estimate"`,
**Then** the component returns to the loading state and fires the same request,
**And** on success, the new formatted value REPLACES the old one in-place (no animation, no `"previously…"` callout, no fade — per UX-DR19 and UX §"Defining Experience: Detailed Mechanics").

**Given** the request fails with `AppError { kind: 'reading_speed_unset' }` (HTTP 412),
**When** `EstimateCell` re-renders,
**Then** it shows an inline `ErrorMessage` with the literal copy `"Set your reading speed in Settings to enable estimates"` per UX-DR12,
**And** the word `"Settings"` is rendered as an Angular `RouterLink` to `/settings` (in `--color-accent`),
**And** below the error message, the `"Estimate"` button is restored so the user can return from `/settings` and click again.

**Given** the request fails with `AppError { kind: 'resource_server_unavailable' }` (HTTP 503 — the J6 marquee failure),
**When** `EstimateCell` re-renders,
**Then** it shows an inline `ErrorMessage` with the literal copy `"Service unavailable — try again shortly"` in `--color-error` per UX-DR12,
**And** below the error message, the `"Estimate"` button is restored so the user can retry by clicking again,
**And** no auto-retry, no auto-poll, no silent retry happens (UX §"Failure recovery" — manual retry only).

**Given** the request fails with any other 4xx/5xx that is NOT `reading_speed_unset`, NOT `resource_server_unavailable`, and NOT `session_expired` (the generic-error case),
**When** `EstimateCell` re-renders,
**Then** it shows an inline `ErrorMessage` with the literal copy `"Couldn't get an estimate — try again"` in `--color-error` per UX-DR12,
**And** the `"Estimate"` button is restored.

**Given** the request fails with `AppError { kind: 'session_expired' }` (HTTP 401),
**When** the global handler from Story 1.9 fires,
**Then** the SPA navigates to `/login?return_to=<current_url>` — `EstimateCell` does NOT render a local error for this case (session_expired is always handled globally).

**Given** the BookRow component from Epic 2 Story 2.6 currently uses the disabled stub,
**When** the developer updates `book-row.html`,
**Then** the stub `<app-estimate-cell />` is REPLACED by the real component bound to the row's `book.id` and `book.pages`,
**And** the `EstimateCell` stub file from Epic 2 is removed (no dead stub left in the repo).

**Given** the test suite (Vitest),
**When** `npm test` runs,
**Then** `estimate-cell.spec.ts` covers each state explicitly — idle / loading / success-with-re-estimate / `reading_speed_unset` error with link / `resource_server_unavailable` error / generic error — using `HttpTestingController` to mock the BFF responses,
**And** `books-service.spec.ts` is extended with tests for `requestEstimate` (happy + each error mapping),
**And** `book-row.spec.ts` is updated to assert the real `EstimateCell` is rendered (the stub assertion from Epic 2 is removed),
**And** `error-service.spec.ts` is extended to verify the `reading_speed_unset` envelope → `AppError` mapping,
**And** Vitest coverage of the touched files is ≥70%.

### Story 4.4: E2E specs — J3 estimate + J6 RS unavailable

As a reviewer of the OAuth/OIDC reference,
I want Playwright E2E specs driving J3 (the defining cross-service estimate interaction including the speed-changes-estimate-changes assertion and the freshuser 412 precondition) and J6 (the honest-failure surface when the RS is unavailable) against the real running stack,
So that the marquee architectural interaction and its honest-failure variant are demonstrably correct on every CI-style run.

**Acceptance Criteria:**

#### J3 spec

**Given** `e2e/tests/j3-estimate.spec.ts` exists,
**When** the developer inspects it,
**Then** it uses `test.describe('J3: reading-time estimate', ...)` with a default `beforeEach` that calls `resetState` then `logInAs(page, testuser)`,
**And** contains at minimum these test cases:

- **`estimate happy path with default speed`** — navigates to `/settings`, sets reading speed to `30`, navigates to `/books`, adds a book with `pages = 600`, clicks `"Estimate"` on the row, asserts the loading state (button disabled with text `"Estimating…"`) is observably reached, then asserts a formatted duration appears in the row matching `/≈\s*\d+\s*[hm]/` (so `"≈ 20 h"`, `"≈ 20 h 0 m"`, or similar shapes are accepted depending on the rounding rule pinned in Story 4.1),

- **`speed change yields different estimate (J4↔J3 coupling)`** — adds a book (`pages = 600`), sets speed to `30`, clicks `"Estimate"`, captures the rendered formatted string `r1`; navigates to `/settings`, changes speed to `60`, navigates back to `/books`, clicks `"Re-estimate"` on the same book, captures the new rendered string `r2`, asserts `r1 !== r2`, asserts `r2`'s implied minutes are strictly less than `r1`'s (parse the formatted string in the test for the assertion),

- **`freshuser sees the 412 precondition with a link to Settings`** — overrides the per-test `beforeEach` to log in as `freshuser` (whose `reading_speeds` row was truncated by `resetState`), adds a book, clicks `"Estimate"`, asserts the inline message `"Set your reading speed in Settings to enable estimates"` is visible, asserts the word `"Settings"` is a clickable link (`<a>` with `href` ending in `/settings`), clicks it, asserts the URL ends with `/settings`,

- **`re-estimate replaces value in-place without navigation`** — completes a successful estimate, captures the SPA's URL, clicks `"Re-estimate"`, asserts URL is unchanged (no navigation), asserts a new duration eventually replaces the previous one in the same cell,

- **`generic non-J6 failure renders the generic copy`** — registers `page.route('**/v1/books/*/estimate', route => route.fulfill({ status: 500, body: JSON.stringify({errorCode: 'unknown', message: 'boom'}), contentType: 'application/json' }))` BEFORE clicking, clicks `"Estimate"`, asserts the inline message `"Couldn't get an estimate — try again"` is visible (NOT the J6 copy — this test pins the rule that the J6-specific copy is reserved for the `resource_server_unavailable` envelope).

#### J6 spec

**Given** `e2e/tests/j6-rs-unavailable.spec.ts` exists,
**When** the developer inspects it,
**Then** it uses `test.describe('J6: resource server unavailable', ...)` with a `beforeEach` that calls `resetState` then `logInAs(page, testuser)`,
**And** an `afterEach` that calls `startRs()` to guard against a previous test having left the RS stopped (the same safety pattern as Story 3.6's J4 spec),
**And** contains at minimum these test cases:

- **`estimate while RS is down renders the named J6 error`** — with the RS up, sets reading speed to `30` and adds a book; calls `killRs()`; navigates to `/books` (the books list itself remains visible — books are owned by the BFF, not the RS); clicks `"Estimate"` on the row; asserts the inline message `"Service unavailable — try again shortly"` is visible in the row's estimate cell; asserts the message is rendered in the error color (assert via the resolved CSS color matching `--color-error`'s `#B91C1C`, or via an `aria`/class marker the implementer chooses); asserts NO fabricated duration appears anywhere in the row,

- **`retry succeeds after RS recovery`** — performs the prior test's setup (RS down, error rendered), calls `startRs()` and waits for the RS health endpoint to report 200, clicks `"Estimate"` again, asserts a real formatted duration now renders, proving that the SPA retries by user action only (no silent retry),

- **`settings save while RS is down also renders the named J6 error`** — calls `killRs()`, navigates to `/settings`, attempts to save a new value, asserts the inline message `"Service unavailable — try again shortly"` is visible (this re-verifies Story 3.6's coverage and pins the SAME copy/component is used across both estimate and settings 503s),

**And** both specs use the helpers from `e2e/fixtures/helpers.ts` (`logInAs`, `resetState`, `killRs`, `startRs` — all real after Story 3.6); no inlined credential filling or docker commands.

**When** the developer runs `docker compose --profile e2e up --abort-on-container-exit`,
**Then** the J3 and J6 specs pass alongside all earlier specs (J1, J5, J2, J4),
**And** the runner exits 0,
**And** on any failure, traces and screenshots are retained under `e2e/test-results/`.

---

## Epic 5: Final Coverage Push & Security Review

Close out the project as a reviewable reference. With QA-from-day-one, this epic is intentionally slim: identify and fill any late-emerging coverage gaps, write the security review document, polish the README plus AI integration log, and run the final `default` profile smoke against the SPA-in-BFF production build.

### Story 5.1: Coverage audit + gap-fill

As a maintainer preparing the project for review,
I want a coverage audit across all four code surfaces (BFF, RS, SPA, E2E) with any gaps below threshold filled by targeted tests,
So that NFR11 (≥70% SPA / archetype's >90% backend / ≥5 E2E covering J1–J6) is provably met at handoff.

**Acceptance Criteria:**

**Given** the maintainer is at the repo root after Epics 1–4 have shipped,
**When** the developer runs the per-surface coverage commands:
- `cd services/bff && uv run pytest --cov=src/bff --cov-report=term-missing --cov-report=html`,
- `cd services/resource-server && uv run pytest --cov=src/resource_server --cov-report=term-missing --cov-report=html`,
- `cd spa && npm test -- --coverage`,
**Then** each command runs to completion and produces both a terminal summary and an HTML report.

**Given** the gap report file `docs/coverage-report.md` exists,
**When** the developer inspects it,
**Then** it contains one section per surface (BFF, RS, SPA) summarizing the overall coverage percentage and listing any files below threshold with their current score and the reason (gap to close vs. justified exclusion),
**And** it records the date of the run and the commit SHA the run was made against,
**And** the report is referenced from the README.

**Given** the gap report identifies files below threshold,
**When** the developer adds targeted tests in the source-mirroring location per architecture's Naming Patterns,
**Then** re-running the relevant coverage command shows all files at or above threshold,
**And** the gap report is regenerated with no remaining unaddressed gaps,
**And** any deliberate exclusions (e.g., a generated migration file, pydantic-settings bootstrap glue) are listed with justification and reflected in the relevant tool config (`[tool.coverage.report] omit` for Python; Vitest config `coverage.exclude` for SPA).

**Given** the SPA coverage target is ≥70%,
**When** `npm test -- --coverage` is run,
**Then** the summary reports ≥70% on statements, branches, functions, AND lines (the four standard metrics),
**And** no per-file score is below 50% (hard floor: a single 0-coverage file is a process failure surface).

**Given** the BFF coverage target is >90% (per archetype),
**When** `uv run pytest --cov` is run inside `services/bff/`,
**Then** the summary reports >90% line coverage,
**And** no per-file score is below 70%.

**Given** the RS coverage target is >90% (per archetype),
**When** `uv run pytest --cov` is run inside `services/resource-server/`,
**Then** the summary reports >90% line coverage,
**And** no per-file score is below 70%.

**Given** the E2E project at `e2e/`,
**When** the maintainer reviews `e2e/tests/`,
**Then** spec files exist covering every PRD journey: `j1-first-login.spec.ts`, `j2-manage-books.spec.ts`, `j3-estimate.spec.ts`, `j4-adjust-speed.spec.ts`, `j5-logout.spec.ts`, `j6-rs-unavailable.spec.ts` (all 6 files present from Epics 1–4),
**And** `docker compose --profile e2e up --abort-on-container-exit` passes the full suite with exit code 0,
**And** `playwright.config.ts` preserves `workers: 1` (sequential — `resetState` requires this).

**Given** every gate is green,
**When** the developer commits the gap report,
**Then** the report's "Status" line reads `"All thresholds met"` (or names any documented exclusions).

### Story 5.2: Security review document

As a reviewer evaluating the OAuth/OIDC reference,
I want a written security review at `docs/security-review.md` covering the six topics PRD §9 enumerates plus an explicit accepted-risk note for at-rest token storage,
So that the security posture is verifiable from the document and traceable to the implementing code paths and tests.

**Acceptance Criteria:**

**Given** `docs/security-review.md` exists,
**When** the developer inspects it,
**Then** it contains a section for each of the six PRD §9 topics:

1. **Token storage and transport** — where access, refresh, and id tokens live (BFF sessions table), the transport (HttpOnly session cookie between SPA and BFF; `Authorization: Bearer` between BFF and RS; never in browser-accessible storage); names the implementing code paths (`services/bff/src/bff/auth/keycloak_cookie_session.py`, `services/bff/src/bff/db/models/session.py`).

2. **Session cookie attributes** — `HttpOnly`, `Secure` (per env), `SameSite=Lax`, `Path=/`, opaque 256-bit value (not a JWT), cookie names from `BFF_SESSION_COOKIE_NAME` and `BFF_CSRF_COOKIE_NAME`; rationale for `Lax` (post-Keycloak callback redirect must carry the cookie — `Strict` would not); references `services/bff/src/bff/auth/keycloak_cookie_session.py` and `tests/auth/test_keycloak_cookie_session.py`.

3. **CSRF posture** — double-submit cookie + `X-CSRF-Token` header on state-changing requests + Origin/Referer check as defense in depth; references `services/bff/src/bff/auth/csrf.py` and `tests/auth/test_csrf.py`.

4. **JWT validation correctness** — PyJWT + `PyJWKClient`; validates `iss`, `aud`, `exp`, signature against the cached JWKS; JWKS cache TTL ~24h with `kid`-rotation single-re-fetch; no hardcoded public keys; references `services/resource-server/src/resource_server/auth/oidc_bearer.py` and `tests/auth/test_oidc_bearer.py`.

5. **Scope enforcement** — enforced at the RS (not the BFF) via `require_scope("reading-speed:read")` and `require_scope("reading-speed:write")` dependencies extending the archetype's `RoleMappingProvider`; per-endpoint scope table; references `tests/api/test_reading_speed.py::test_*_scope_*` and `tests/api/test_estimate.py::test_*_scope_*`.

6. **Standard SPA concerns** — CSP response header from BFF (`default-src 'self'; …`); no tokens reachable from JavaScript; output escaping default in Angular templates; no `innerHTML` usage; dependency hygiene (Angular 21 + Tailwind 4 + their transitive deps reviewed at the date of the report); references `services/bff/src/bff/auth/csrf.py` (CSP middleware) and a one-line statement on the Angular template auto-escaping default.

**Given** a dedicated "Accepted Risks" subsection,
**When** the developer inspects it,
**Then** it explicitly calls out:
- The BFF's `sessions` table storing `access_token`, `refresh_token`, `id_token` columns in plaintext within the SQLite file (per architecture's "Operational Details" → "Token storage at rest"),
- Mitigation (named Docker volume not exposed to the network, BFF-process-only consumer),
- Production-deployment alternatives (application-level KEK encrypting the columns, or moving sessions to a dedicated encrypted store),
- That this is out-of-scope per PRD §4 ("Production hardening beyond what the course's success criteria require").

**Given** a "Threat Model Summary" subsection,
**When** the developer inspects it,
**Then** it enumerates the threats considered with a one-paragraph mitigation each:
- XSS in the SPA → token exfiltration (mitigation: no tokens in browser; HttpOnly cookies; CSP),
- CSRF on BFF state-changing endpoints (mitigation: double-submit + Origin check),
- Token replay (mitigation: short access-token lifetime + refresh-token revocation on logout),
- Direct RS access bypassing the SPA flow (mitigation: RS requires bearer JWT with the correct `aud` and scopes — anyone holding a valid bearer can call it, which is intentional),
- Scope escalation (mitigation: enforced at the RS layer; tested per Story 3.2),
- Replay-after-logout (mitigation: refresh-token revocation at Keycloak; verified by Story 1.13's J5 E2E spec),
- Confused-deputy / sub-injection (mitigation: BFF never injects sub into body/path; RS reads sub only from the JWT; pinned by Story 4.2 tests).

**Given** a "Known Gaps / Future Work" subsection,
**When** the developer inspects it,
**Then** it lists any items flagged during the build that were considered acceptable for the educational reference but would matter for production (e.g., tighter idle-session timeouts, encrypted session store, GitHub Actions CI workflow).

**Given** the document is complete,
**When** the README is updated,
**Then** the README references `docs/security-review.md` under the appropriate section.

### Story 5.3: README polish + AI integration log

As a developer or reviewer arriving at the repo for the first time,
I want a complete README with setup, architecture overview, dev/E2E/prod workflows, per-surface test commands, project structure, and an AI integration log capturing BMAD/MCP agent usage throughout the build,
So that I can clone and run the repo end-to-end without hunting through files, and I can audit how the AI-native build was conducted.

**Acceptance Criteria:**

**Given** `README.md` exists at the repo root (replacing the Story 1.1 stub),
**When** the developer reads it top-to-bottom,
**Then** it contains the following sections in order:

1. **Title + one-paragraph summary** — names the project, names the architectural goal (Auth Code + confidential client BFF + JWKS + scope + sub-keyed identity propagation), names the educational context (BMAD capstone, AI-native engineering course).

2. **Prerequisites** — Node ≥20 LTS, Python 3.14, `uv`, Docker + Compose v2.20+, `npx`, optional `ng` CLI for SPA development.

3. **Setup** — clone the archetype into `tools/fastapi-archetype/` (gitignored), copy `.env.example` to `.env`, fill placeholder secrets, run `docker compose up` for first-time bring-up; one-paragraph troubleshooting note for common first-run issues.

4. **Architecture overview** — short prose summary of the four-component topology (SPA, BFF, Resource Server, Keycloak) with the boundary diagram from `architecture.md` either inlined as ASCII or referenced via link; calls out the load-bearing OAuth + JWT + scope concepts.

5. **Dev workflow** — `docker compose --profile dev up` for backend + Keycloak, `cd spa && ng serve` for HMR'd frontend; ports table (SPA :4200, BFF :8000, Keycloak :8080); credentials for the two seeded users (`testuser`/`testpassword`, `freshuser`/`freshpassword`).

6. **E2E workflow** — `docker compose --profile e2e up --abort-on-container-exit` runs the full Playwright suite against the compose stack; `cd e2e && npm test` runs locally against `--profile dev`; where to find traces/screenshots on failure.

7. **Prod-shaped workflow** — `docker compose up` (default profile) brings up the full topology with the SPA baked into the BFF image; references the smoke checklist (`docs/smoke-run.md`) from Story 5.4.

8. **Per-surface test commands** — quick reference: `cd services/bff && uv run pytest`, `cd services/resource-server && uv run pytest`, `cd spa && npm test`, `cd e2e && npm test`; plus the coverage variants.

9. **Project structure** — top-level tree showing `spa/`, `services/`, `keycloak/`, `e2e/`, `compose/`, `tools/`, `docs/`, `_bmad-output/` — sufficient for repo navigation.

10. **AI Integration Log** — a chronological log of AI-agent / MCP usage during the build, with the following requirements:
    - At least 5 entries,
    - Each entry has a date and a one-line summary,
    - Entries cover, at minimum: the BMAD skills used (`bmad-create-prd`, `bmad-create-architecture`, `bmad-create-ux-design`, `bmad-create-epics-and-stories`, `bmad-check-implementation-readiness`, `bmad-dev-story`, etc.), at least one notable AI-assisted decision (e.g., "Angular v21 chosen after AI-assisted technical research", "Coverage threshold calibration against archetype defaults"), and which Claude model(s) were used across the date range (per the build's actual usage).

11. **References** — links to `_bmad-output/planning-artifacts/PRD.md`, `_bmad-output/planning-artifacts/architecture.md`, `_bmad-output/planning-artifacts/ux-design-specification.md`, `_bmad-output/planning-artifacts/epics.md`, `docs/security-review.md`, `docs/coverage-report.md`, `docs/smoke-run.md`.

**Given** the README is complete,
**When** a developer follows the Setup section starting from a fresh clone,
**Then** they reach a working app via `docker compose up` without needing to read any other file (this is implicitly verified by Story 5.4's smoke checklist running against a clean state).

### Story 5.4: Final `docker compose up` smoke (default profile)

As a reviewer running the project for the first time,
I want a documented smoke run of the `default` compose profile (SPA baked into the BFF image) confirming all six journeys work, with the run output captured in the repo as evidence of the submission state,
So that the production-shaped deployment is verifiable beyond the `e2e` profile (which uses Playwright-rendered SPA flow, not the SPA-in-BFF prod build path).

**Acceptance Criteria:**

**Given** `docs/smoke-run.md` exists,
**When** the developer inspects it,
**Then** it contains a smoke checklist with the following ordered steps, each with a checkbox `[ ]`:

1. Fresh clone of the repo,
2. Setup per README (archetype clone, `.env` from `.env.example`),
3. `docker compose down -v` to clear any prior volumes,
4. `docker compose up --build` (default profile),
5. Wait for all healthchecks — verify all services healthy via `docker compose ps`,
6. Open `http://localhost:8000` in a desktop browser,
7. **J1**: click "Log in" → complete OAuth round-trip with `testuser` / `testpassword` → returns to `/books` with identity in chrome,
8. **J2**: add a book ("Dune", 688 pages, to-read) → row appears at top; change status to "reading" → optimistic update visible; edit title to "Dune Messiah" → row updates; delete via native confirm → row removed,
9. **J4**: navigate to `/settings` → set pages-per-hour to 30 → click Save → "Saved" pulse visible → reload page → value still shows 30,
10. **J3 happy**: add a 600-page book → click "Estimate" → formatted duration appears (≈ 20 h with speed=30); navigate to `/settings`, change speed to 60, return to `/books`, click "Re-estimate" → result is smaller (≈ 10 h),
11. **J3 precondition**: log out → log in as `freshuser` / `freshpassword` → add a book → click "Estimate" → see `"Set your reading speed in Settings to enable estimates"` with a clickable "Settings" link → clicking it navigates to `/settings`,
12. **J5**: click "Log out" → identity chrome empties → URL ends with `/login` → attempt to navigate to `/books` → bounces back to `/login?return_to=%2Fbooks`,
13. **J6**: log in again as `testuser` → `docker compose stop resource-server` → click "Estimate" on a book → see `"Service unavailable — try again shortly"` in the row in the error color → `docker compose start resource-server` → wait for healthcheck → click "Estimate" again → real duration appears.

**Given** the document also has a "Run Record" section,
**When** the developer completes the smoke against the submission state,
**Then** they fill in:
- The date of the run,
- The commit SHA the run was performed against,
- Each checkbox marked `[x]`,
- Any anomalies observed (none expected; field present for honesty),
- Optional screenshots if useful for the reviewer.

**Given** the smoke run completes successfully,
**When** the developer commits the filled-out `docs/smoke-run.md`,
**Then** the repo carries a record of the submission state passing the manual smoke against the production-shaped deployment.

**Given** the README's "Prod-shaped workflow" section,
**When** a reviewer follows it,
**Then** it points at this document as the verification artifact.

## Epic 6: Frontend Split & SSR Edge

Introduced 2026-05-19 via `bmad-correct-course` after Epic 5 closed. The Sprint Change Proposal at `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` is the scope authority. Epic 6 extracts the SPA out of the BFF image into its own Angular SSR container, makes the BFF API-only, moves the browser-facing host port from `:8000` (BFF) to `:4000` (SPA SSR edge), and moves CSP attachment from the BFF's Starlette middleware to the SPA edge's Express middleware (architecture A8 amendment). Same-origin model preserved through the SPA edge's transparent in-network reverse-proxy mount. The four stories below close the epic; Story 6.4 is the canonical close and flips `epic-6: in-progress → done` in `sprint-status.yaml`.

### Story 6.1: SPA Angular SSR scaffold + proxy mount + cookie forwarding

As the SPA application,
I want to run as an Angular SSR Express server with `http-proxy-middleware` reverse-proxying `/auth /api /v1` to the BFF over compose DNS, plus SSR-time HTTP interceptors that rewrite relative API URLs to the absolute `BFF_INTERNAL_URL` and forward the inbound browser's cookies on the bootstrap `/api/me` call,
so that the SPA can be deployed as its own container with the BFF internal-only on the compose network while preserving the same-origin browser experience.

**Acceptance Criteria:**

**Given** `ng add @angular/ssr` has been applied to the `spa/` workspace,
**When** the SSR build runs,
**Then** `spa/dist/spa/server/server.mjs` exists and `node dist/spa/server/server.mjs` listens on `PORT=4000` and SSR-renders `<app-root>` with `ng-server-context="ssr"` on the response HTML.

**Given** `spa/src/server.ts` exists,
**When** a browser request hits `/auth /api /v1` paths,
**Then** the Express server reverse-proxies the request to `${BFF_INTERNAL_URL}` (default `http://bff:8000`) via `http-proxy-middleware` v3 with `changeOrigin: true` + `xfwd: true`, byte-for-byte forwarding all browser headers including `Cookie`, `Origin`, `X-CSRF-Token`.

**Given** the Angular bootstrap requests `/api/me` from the server platform,
**When** the SSR HttpClient issues the call,
**Then** the `ssrApiUrlInterceptor` rewrites the relative URL to `${BFF_INTERNAL_URL}/api/me` (no-op in the browser platform) AND the `ssrCookieForwardInterceptor` attaches the inbound browser's `Cookie` header onto the outbound SSR-time request (no-op in the browser platform).

**Given** `/_health` is registered before the proxy mount,
**When** a `GET /_health` request hits the SPA edge,
**Then** the response is `{ ok: true }` HTTP 200 — used by compose's `spa.healthcheck`.

**Source:** Sprint Change Proposal 2026-05-19 §4 Story 6.1.

### Story 6.2: SPA Dockerfile + compose service + Keycloak realm port pin

As the deployment configuration,
I want a `spa/Dockerfile` (Node multi-stage `deps → build → runtime`) packaged as the `spa` compose service taking host port `${SPA_HOST_PORT:-4000}`, AND a Keycloak realm port pin that flips the BFF client's `redirectUris` / `webOrigins` / `attributes.post.logout.redirect.uris` from `http://localhost:8000` to `http://localhost:${SPA_HOST_PORT:4000}`,
so that bare `docker compose up` brings up the full baseline including the SPA SSR edge as the only browser-facing port and the OAuth callback round-trip lands at the SPA edge instead of the BFF.

**Acceptance Criteria:**

**Given** `spa/Dockerfile` exists,
**When** `docker compose build spa` runs,
**Then** the image is built in three stages (`deps → build → runtime`) and the runtime entrypoint is `node dist/spa/server/server.mjs`.

**Given** `compose/app.yml` defines a `spa` service,
**When** bare `docker compose up` runs,
**Then** the `spa` container starts unconditionally (no `profiles:` filter), publishes host port `${SPA_HOST_PORT:-4000}:4000`, depends on `bff: { condition: service_healthy }`, runs with `init: true`, and the healthcheck on `/_health` flips green within the start-period envelope.

**Given** the BFF service block in `compose/app.yml`,
**When** post-Story-6.2 `docker compose ps` is inspected,
**Then** the `bff` row carries NO host-published port — the BFF is internal-only on the compose network at `http://bff:8000`. Probe: `curl http://localhost:8000/health` returns `connection_refused`.

**Given** `keycloak/realm-bmad-books.json`,
**When** the realm is imported at Keycloak container start,
**Then** the BFF client carries `redirectUris=["http://localhost:${SPA_HOST_PORT:4000}/auth/callback"]`, `webOrigins=["http://localhost:${SPA_HOST_PORT:4000}"]`, and `attributes.post.logout.redirect.uris="http://localhost:${SPA_HOST_PORT:4000}/*"` — the bare `:` substitution form is Quarkus MicroProfile syntax; the Keycloak service in `compose/infra.yml` passes `SPA_HOST_PORT` as an env pass-through so the substitution resolves at boot.

**Source:** Sprint Change Proposal 2026-05-19 §4 Story 6.2.

### Story 6.3: BFF cleanup — supersede Story 1.14

As the BFF service,
I want the Story-1.14 SPA-in-BFF code surface removed (the `node-builder` Dockerfile stage, the `_register_spa` / `_SPA_DIR` / `_spa_or_404` glue in `services/bff/src/bff/main.py`, the static-mount test at `services/bff/tests/api/test_static.py`, and the BFF's host-port mapping in `compose/app.yml`),
so that the BFF is API-only and the supersession of Story 1.14 by Epic 6 is reflected in the code surface (not just the planning artefacts).

**Acceptance Criteria:**

**Given** `services/bff/Dockerfile`,
**When** the post-Story-6.3 file is inspected,
**Then** the multi-stage `node-builder` stage that compiled the SPA is removed; the final image carries no `/app/static` directory and no Node toolchain.

**Given** `services/bff/src/bff/main.py`,
**When** the post-Story-6.3 file is inspected,
**Then** `git grep -nE '_register_spa|_SPA_DIR|_spa_or_404|StaticFiles' services/bff/src/bff/main.py` returns zero matches; the file mounts only the JSON API surface.

**Given** `services/bff/tests/api/`,
**When** the post-Story-6.3 directory is inspected,
**Then** `test_static.py` is deleted via `git rm`; no test in the BFF suite depends on the static-serve path.

**Given** Story 1.14's implementation artefact `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md`,
**When** the post-Story-6.3 frontmatter is inspected,
**Then** it carries a `superseded_by: "Epic 6 (stories 6.1–6.4) — Sprint Change Proposal 2026-05-19"` field and a top-of-document banner pointing readers to the SCP.

**Source:** Sprint Change Proposal 2026-05-19 §4 Story 6.3.

### Story 6.4: Re-validation — e2e + smoke + docs sweep (Epic 6 close)

As Epic 6 itself,
I want the e2e harness to run J1–J6 green against the new `:4000` SPA-edge origin, the smoke artefact to gain a new Epic-6 Run Record (preserving the 2026-05-18 record byte-identical), the security review's §2 + §3 + §6 attestations to cite the SPA-edge as the HTML / CSP source, the coverage report to acknowledge the SSR Express server's test surface, the README's Setup / Architecture / Dev / Prod-shaped sections to describe the split topology, the architecture document's F3 / I6 / A8 to update + F7 / I9 to land, the PRD §6 SPA bullet to gain a one-line SSR clarification, this epics.md to append the Epic 6 four-story block, and the BFF's `security_headers.py` CSP middleware to move to the SPA edge (closing the A8 amendment),
so that the project's submission state reflects Epic 6's frontend-split reality end-to-end — code surface, e2e contract, security attestation, coverage attestation, smoke attestation, README onboarding, architecture decisions, and PRD/epic planning artefacts.

**Acceptance Criteria:**

**Given** the e2e config flips: `e2e/playwright.config.ts` `baseURL` `http://localhost:8000` → `http://localhost:4000`; `--host-resolver-rules` add `MAP localhost:4000 spa:4000`, remove `MAP localhost:8000 bff:8000`; `compose/app.yml` `playwright:` service `E2E_BASE_URL` flip + `depends_on: spa` add,
**When** `just e2e-up` runs from the repo root,
**Then** the runner exits 0 with 26/26 specs green (J1×3, J2×8, J3×5, J4×5, J5×2, J6×3 — same per-journey breakdown as Story 5.1's audit).

**Given** the CSP middleware moves from BFF → SPA edge per A8 amendment,
**When** the post-Story-6.4 file tree is inspected,
**Then** `services/bff/src/bff/middleware/security_headers.py` is deleted, `services/bff/src/bff/main.py` does not import or register the middleware, `services/bff/tests/middleware/test_security_headers.py` is deleted, AND `spa/src/server/csp.middleware.ts` exists with a Vitest spec asserting the byte-for-byte CSP value. Live attestation: `curl -sSI http://localhost:4000/login | grep -i 'content-security-policy'` returns the CSP byte string; `curl -sSI http://localhost:4000/api/me | grep -ic 'content-security-policy'` returns 0 (proxied BFF responses are not CSP-stamped).

**Given** `docs/smoke-run.md` is the smoke-run artefact,
**When** the post-Story-6.4 file is inspected,
**Then** the historical 2026-05-18 Run Record (Story 5.4 close, lines 54–143) is byte-identical to its pre-6.4 state, AND a new "Run Record — Epic 6 close (2026-05-19)" section is appended with the Mode-B HTTP-probe transcript (5 probes + J6 surrogate) at the post-Epic-6 SPA-SSR-edge topology.

**Given** the planning artefacts `architecture.md` / `PRD.md` / `epics.md`,
**When** the post-Story-6.4 files are inspected,
**Then** `architecture.md` carries F3 / I6 / A8 amendments + new F7 + new I9 + §"Architectural Boundaries" diagram refresh; `PRD.md` §6 SPA bullet carries the one-line SSR clarification (no other PRD edits); `epics.md` carries this Epic 6 section appended after Epic 5.

**Source:** Sprint Change Proposal 2026-05-19 §4 Story 6.4.

### Epic 6 close

Story 6.4 is the canonical close. Once Story 6.4 lands as `review` → `done`, `sprint-status.yaml` flips `epic-6: in-progress → done`. The epic-retrospective entry stays at `optional` — Epic 6 is short enough that a formal retro is not load-bearing; if a future session wants one, flip `epic-6-retrospective: optional → backlog`.
