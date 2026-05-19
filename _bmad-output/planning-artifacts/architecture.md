---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: complete
completedAt: 2026-05-14
inputDocuments:
  - _bmad-output/planning-artifacts/PRD.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
workflowType: architecture
project_name: BMAD_books
user_name: Nearformer
date: 2026-05-14
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements (PRD §7):**

Six capabilities, deliberately minimal so the OAuth/OIDC topology is the focus:

- **FR-AUTH-01** — OIDC login establishing a BFF-managed browser session (J1).
- **FR-BOOK-01** — Full CRUD on the user's books (title, page count, status `{to-read, reading, finished}`). Owned by the BFF, persisted in the BFF database keyed by `sub` (J2).
- **FR-SPEED-01** — Read/update a personal reading speed in pages-per-hour, owned by the Resource Server, keyed by `sub` (J4).
- **FR-ESTIMATE-01** — Per-book reading-time estimate computed on the Resource Server from the user's reading speed and the book's page count (J3). **The defining architectural interaction.**
- **FR-LOGOUT-01** — Terminate the browser session and revoke the refresh token at the Authorization Server (J5).
- **FR-ERROR-01** — Honest, named failure when the Resource Server is unavailable; the BFF must not fabricate a result (J6).

**Non-Functional Requirements (PRD §§8–9 — load-bearing):**

- **Token isolation.** Access/refresh tokens never leave the server side; the browser holds only an HttpOnly session cookie.
- **BFF as confidential OAuth client.** Authorization Code flow with PKCE; tokens held server-side keyed by session.
- **Transparent token refresh.** BFF refreshes expired access tokens and replays the in-flight request without SPA involvement.
- **Stateless Resource Server.** No session state, no shared database with the BFF; every request authenticated solely by its JWT.
- **JWKS-based JWT validation.** Public keys fetched and cached from the Authorization Server; no hardcoded keys.
- **`sub` as the only identity key.** No user records on the BFF or Resource Server beyond `sub`-keyed data.
- **Scope-enforced computation at the Resource Server.** `reading-speed:read` gates retrieval and estimate computation; `reading-speed:write` gates updates. Enforcement is at the RS, not the BFF.
- **BFF does not bypass the RS.** No local fallback computation when the RS is unavailable.
- **Reproducible Authorization Server configuration.** Realm, clients, and scopes are version-controlled and imported at container startup.
- **Deployment.** Full topology runnable via `docker-compose up`, with health checks gating inter-service dependency ordering.
- **Test coverage.** ≥70% meaningful coverage (PRD floor); the backend archetype tightens this to **>90%**. ≥5 E2E tests covering J1–J6, with the OAuth flow exercised end-to-end (not mocked).
- **Security posture.** Documented security review covering token storage/transport, cookie attributes, CSRF, JWT validation correctness, scope enforcement, XSS, and injection.
- **Configuration.** Environment-variable selectable; compose profiles for dev/test; secrets not committed.

**Scale & Complexity:**

- Product complexity is **low** (6 FRs, ~10 UI components, single role, desktop only).
- Architectural complexity is **medium** — five containerized services in disciplined cooperation, OAuth2/OIDC with no shortcuts, scope-aware authorization, and an E2E bar that includes the real auth flow.
- Primary domain: full-stack web + API backend with strong AuthN/AuthZ emphasis (`web_app` + `api_backend`).
- Estimated architectural components: **5 services** (SPA, BFF, Resource Server, Authorization Server, BFF database) + **1 orchestration layer** (`docker-compose`) + **1 E2E test harness**.

### Technical Constraints & Dependencies

**Locked by PRD (not architect-relaxable):**

- Authorization Server is **Keycloak**, configured via realm-style import on container startup.
- Auth Code + PKCE flow is mandatory; implicit flow and password grant are forbidden by §8.
- Resource Server must validate JWTs via JWKS — no shared secret with the Authorization Server.
- BFF database is owned exclusively by the BFF; the Resource Server has its own storage for reading-speed.
- All components containerized and orchestrated by `docker-compose`.

**Locked by user mandate — backend archetype** (`github.com/tommaso-meledina/fastapi-archetype`):

Both the BFF and the Resource Server MUST be built from this archetype. This pre-decides:

- **Language/framework:** Python 3.14 + FastAPI.
- **ORM/validation:** SQLModel (unified Pydantic + SQLAlchemy).
- **Database:** SQLite (default / tests), MariaDB via `DATABASE_URL`.
- **Config:** pydantic-settings + `.env`, fail-fast on missing values.
- **Packaging:** `uv` with `uv.lock` committed.
- **Lint / format / types:** Ruff + Astral's `ty`.
- **Tests:** pytest (async), coverage target >90%.
- **Container:** multi-stage `python:3.14-slim`.
- **API versioning:** URL-prefix (`/v1/`, `/v2/`); infra routes (`/health`, `/docs`, `/redoc`) unversioned.
- **Error contract:** enum `ErrorCode` → JSON `{errorCode, message, detail}`.
- **Auth scaffolding:** pluggable; ships `none` + `entra` (bearer + JWKS + `RoleMappingProvider`); FastAPI deps `require_auth`, `require_role`.
- **Logging:** AOP-based `log_io` applied at module import.
- **Project scaffolding:** `python scripts/build_template.py -n <name> -o <dir>`.

**Locked by UX (not architect-relaxable):**

- SPA targets desktop browsers only; no responsive layout, no mobile.
- No accessibility hardening (no WCAG conformance target).
- No opinionated component library; utility CSS (Tailwind) or vanilla CSS with tokens.
- Inline error rendering at the action site; no global toasts. Specific HTTP-status-driven UX states (`412` precondition, `503` for J6, `401` for session expiry).
- Optimistic UI only for same-service, low-stakes changes (book-row status PATCH); pessimistic for cross-service requests (estimate).

**Open architectural choices (to decide in later steps):**

- **Frontend framework** for the SPA (e.g., React, Vue, Svelte, plain TS).
- **How the SPA is served** (BFF static-serving the bundle vs. a separate static container vs. dev-only Vite proxy).
- **BFF session-store backing** (in-memory dict, Redis, MariaDB row, file).
- **BFF database engine** (SQLite acceptable per archetype default; MariaDB for "production credible" demo).
- **Resource-Server storage engine** for reading-speed records (SQLite or MariaDB; can be different from BFF).
- **OIDC client library** on the BFF (e.g., `authlib`, `python-jose` + manual flow, `httpx-oauth`).
- **JWT validation library** on the RS (`python-jose`, `pyjwt`, or extending the archetype's `entra` plumbing).
- **E2E framework** and how it drives the Keycloak login (Playwright with real browser interaction vs. scripted token exchange).
- **Route layout under `/v1/`** — domain APIs (`/v1/books`, `/v1/reading-speed`, `/v1/estimate`) vs. cross-cutting paths (`/auth/login`, `/auth/callback`, `/auth/logout`, `/api/me`) that may live outside the versioning prefix.

### Cross-Cutting Concerns Identified

1. **OAuth/OIDC plumbing** — Auth Code + PKCE, server-side token storage on the BFF, transparent refresh + request replay, end-session at logout. *Note: archetype does not ship this — it is net-new work on top of the archetype.*
2. **Session management** — HttpOnly cookie ↔ server-side session record holding the token bundle; cookie attributes (`Secure`, `HttpOnly`, `SameSite`), session lifetime, idle/absolute timeouts.
3. **JWKS caching** — Resource Server caches Keycloak's JWKS with a TTL and handles key rotation. Likely reusable from the archetype's `entra` plumbing.
4. **Scope enforcement** — Resource-Server middleware maps endpoints to required scopes; the archetype's `RoleMappingProvider` is the natural extension point.
5. **CSRF posture** — state-changing SPA→BFF endpoints are cookie-authenticated; CSRF protection required (double-submit, origin checks, or `SameSite=Lax/Strict` with care).
6. **SPA security** — CSP, output escaping, dependency hygiene, no token-handling code paths.
7. **Container orchestration** — single `docker-compose.yml` orchestrating Keycloak, SPA, BFF, RS, and the BFF DB; health-check-gated dependency ordering; dev/test compose profiles; secrets not committed.
8. **Realm-as-code** — version-controlled Keycloak realm JSON imported at startup; no manual post-`up` configuration.
9. **E2E test harness** — drives the real OAuth round-trip including Keycloak login.
10. **Honest error mapping** — RS-downtime → BFF 503 (`ErrorCode.resource_server_unavailable`) → SPA-rendered named failure; precondition (no reading speed) → 412 (`ErrorCode.reading_speed_unset`); session-expiry → 401.
11. **Identity propagation** — `sub` claim is the only user identifier crossing service boundaries; both BFF and RS key their data on it.

## Starter Template Evaluation

### Primary Technology Domains

This is a **full-stack project with three distinct codebases**, each with its own starter story:

- **Backend services** (BFF + Resource Server) — Python/FastAPI, locked to the `fastapi-archetype`.
- **SPA** — Angular v21 web application.
- **Authorization Server** — Keycloak (PRD-locked; no "starter," configured via realm import).

Because the three are independent codebases sharing a single `docker-compose` orchestration, there is no monolithic starter. We treat each as a sub-project and use the appropriate starter for each.

### Backend Starter — Locked (no evaluation)

Per project mandate (see Project Context Analysis, "Locked by user mandate — backend archetype"), both backend services are scaffolded from **`github.com/tommaso-meledina/fastapi-archetype`**.

**Initialization commands:**

```bash
# Clone the archetype once into a workspace location
git clone https://github.com/tommaso-meledina/fastapi-archetype.git tools/fastapi-archetype

# Scaffold the BFF
python tools/fastapi-archetype/scripts/build_template.py \
  -n bff \
  -o services/bff \
  --description "BMAD_books Backend-for-Frontend (OAuth client, books domain)"

# Scaffold the Resource Server
python tools/fastapi-archetype/scripts/build_template.py \
  -n resource-server \
  -o services/resource-server \
  --description "BMAD_books Resource Server (reading speed, estimate)"
```

Architectural decisions provided by the archetype are listed in step 2 ("Locked by user mandate — backend archetype"). The two key gaps to fill on top of it are recorded there as well: (1) the BFF needs a new cookie-session + Authorization-Code-with-PKCE auth plugin alongside `none`/`entra`, and (2) the Resource Server reuses the archetype's `entra`-style JWKS bearer validation against Keycloak (either via a new `keycloak` mode or by parameterizing the issuer/JWKS URL).

### SPA Starter — Angular v21 + Tailwind CSS v4

**Frameworks considered:** React, Vue 3, SvelteKit, plain Vite + TS, **Angular v21 (chosen)**.

**Rationale for Angular v21:**

- User-selected for its 2026 feature set: zoneless change detection by default, signals as the primary reactivity model, the new Vitest test runner, the stable Angular MCP server, and the 2025 file-naming style guide.
- Strong fit for a small, opinionated app: standalone components (no `NgModule`), functional router config, `inject()` over constructor injection, and the new `@if` / `@for` control-flow syntax produce a clean codebase even for the 10-component UI specified in the UX spec.
- HttpClient with `withCredentials: true` directly supports the BFF's cookie-session model.
- Familiarity at Nearform (presumed).

**Initialization commands:**

```bash
# Pre-flight (verify Node ≥20 LTS for Angular 21)
node --version
npm --version

# 1) Scaffold the Angular workspace into spa/ at repo root
npx -p @angular/cli@21 ng new spa \
  --routing \
  --style=css \
  --ssr=true \
  --skip-git \
  --package-manager=npm \
  --strict

# 2) Add Tailwind CSS v4 (CSS-first config)
cd spa
npm install -D tailwindcss @tailwindcss/postcss postcss
```

**`.postcssrc.json`** in `spa/`:

```json
{
  "plugins": {
    "@tailwindcss/postcss": {}
  }
}
```

**`src/styles.css`** — single Tailwind import plus the UX-spec design tokens declared inline using Tailwind v4's `@theme` block:

```css
@import "tailwindcss";

@theme {
  --color-surface: #FFFFFF;
  --color-surface-muted: #F5F5F5;
  --color-border: #E5E5E5;
  --color-text: #111111;
  --color-text-muted: #666666;
  --color-accent: #2563EB;
  --color-accent-hover: #1D4ED8;
  --color-error: #B91C1C;

  --text-page-title: 24px / 32px 600;
  --text-body: 14px / 20px 400;
  --text-small: 12px / 16px 400;

  --spacing-1: 4px;
  --spacing-2: 8px;
  --spacing-3: 12px;
  --spacing-4: 16px;
  --spacing-6: 24px;
  --spacing-8: 32px;
}
```

**Architectural Decisions Provided by the Angular v21 Starter:**

**Language & Runtime:**

- TypeScript with `strict` mode on; targets the latest ECMAScript that Angular 21 supports.
- Node ≥ 20 LTS expected at build time.

**Component Model:**

- **Standalone components by default** (no `NgModule`). The 10 UX components (`TopChrome`, `LoginView`, `BookForm`, `BookList`, `BookRow`, `StatusControl`, `EstimateCell`, `SettingsView`, `ErrorMessage`) are each one standalone component.
- **Zoneless change detection by default** — `zone.js` is not bundled; reactivity is driven entirely by signals and the new control flow primitives.
- **Signals (`signal`, `computed`, `effect`)** as the default state primitive — sufficient for this UI, no NgRx or other store needed.
- **New control flow (`@if`, `@for`, `@switch`)** for templates; legacy `*ngIf`/`*ngFor` are not used in new code.
- **`inject()` over constructor DI** for services, routes, and HTTP clients.
- **`input()` / `output()` signal-based component IO** instead of `@Input` / `@Output` decorators.

**Routing:**

- Functional router config via `provideRouter(routes)` in `app.config.ts`.
- Three top-level routes: `/login`, `/books`, `/settings`. A canActivate-style functional guard (`authGuard`) on `/books` and `/settings` calls `GET /api/me` (with `withCredentials: true`) and redirects to `/login` on 401.
- Standard browser history; no hash routing.

**Forms:**

- Reactive Forms (`@angular/forms` `FormGroup`/`FormControl`) for the two forms in scope (`BookForm`, `SettingsView`). Validation runs on submit per UX spec; not switching to experimental Signal Forms for production-credible code.

**HTTP:**

- `provideHttpClient(withFetch())` for fetch-based HTTP, with a global interceptor that sets `withCredentials: true` so the HttpOnly session cookie is sent to the BFF.

**Styling Solution:**

- **Tailwind CSS v4** via `@tailwindcss/postcss`, CSS-first config (no `tailwind.config.js`).
- UX design tokens declared in `src/styles.css` under Tailwind's `@theme` block so they are usable as utility classes (`text-accent`, `bg-surface-muted`, `p-3`).
- No external UI component library (per UX spec).
- Component-scoped CSS (`styles.ts` per component) used sparingly; most styling via Tailwind utilities.

**Build Tooling:**

- Angular CLI 21 + esbuild-based application builder (default).
- Hot Module Reloading enabled in `ng serve`.

**Testing Framework:**

- **Vitest** as the unit/component test runner (Angular 21 default — replaces Karma + Jasmine).
- Component testing via Angular's `TestBed` integrated with Vitest.
- Coverage target: ≥70% per PRD floor (no archetype-style 90% target on the frontend, but achievable).

**Code Organization (2025 style guide):**

- Concise file naming: `app.ts`, `app.html`, `app.css` (no `.component.` suffix).
- Feature-folder layout: `src/app/books/`, `src/app/settings/`, `src/app/login/`, `src/app/auth/`, `src/app/shared/`.
- Services live alongside their consumers (`books.service.ts` in `books/`), shared across features only when actually shared.

**Development Experience:**

- Angular DevTools browser extension supported.
- Stable Angular MCP server available locally (`ng mcp`) — gives AI coding assistants accurate, project-aware context. Worth wiring up given this is a BMAD/AI-native project.
- Linting via the Angular ESLint defaults; format with Prettier (added separately if desired).

**Out of scope for the starter** (decided elsewhere or deliberately excluded):

- Angular Aria (Dev Preview) — not used; a11y is out of scope per PRD §4.
- Server-side rendering (`--ssr=true`, applied in Story 6.1 via `ng add @angular/ssr`) — the SPA's Angular SSR Express server is the browser-facing edge and reverse-proxies `/auth /api /v1` to the BFF over compose DNS. See F3 + I6 below for the runtime model, F7 + I9 for SSR-time cookie forwarding and Keycloak realm port pin.
- Storybook / mock-service-worker / i18n — none required by the UX or PRD.

**E2E framework (orthogonal to the Angular starter):**

- **Playwright** is the recommended E2E framework given the PRD's "real OAuth flow exercised end-to-end" requirement; it can drive a real Keycloak login page from a real browser. Not part of the Angular scaffold; added as a separate `e2e/` project alongside `spa/`, `services/bff/`, and `services/resource-server/`. (Step-4 decision; flagged here.)

**Note:** Project initialization using these commands should be the first implementation story (one story per starter — backend `bff`, backend `resource-server`, frontend `spa`).

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (block implementation):**

- BFF OIDC client library (Authlib) and the new cookie-session/PKCE auth plugin on top of the archetype.
- Resource-Server JWT validation library (PyJWT) and scope-enforcement seam (via archetype's `RoleMappingProvider`).
- BFF session store backing.
- Inter-service auth pattern (BFF forwards user access token to RS; refresh-and-replay on 401).
- Database engines for BFF and RS, plus migration tooling.
- Repository structure and compose composition.
- Keycloak realm-as-code shape.
- CSRF strategy and cookie attributes.
- SPA serving model (same-origin via SPA SSR edge; reverse-proxies to the BFF on the compose network).

**Important Decisions (shape architecture):**

- Path layout: `/auth/*` and `/api/me` non-versioned; domain APIs under `/v1/*` per archetype convention.
- BFF and RS endpoint surfaces.
- Token refresh strategy (reactive on 401).
- Timeouts, retries, and JWKS caching.
- `ErrorCode` enum additions to cover UX-spec'd failure surfaces.
- API Pydantic models distinct from ORM models.
- Logout flow (revoke + end-session + clear session, with degrade-honestly behavior).
- Angular signals + per-feature services (no global store); feature-folder layout; functional auth guard.
- E2E framework: Playwright.

**Deferred / Out-of-Scope:**

- CI/CD pipeline (not a PRD requirement; flag as future work).
- Caching, rate limiting, pagination, search, sorting (PRD §4 / §12 out-of-scope).
- Production hardening beyond `docker-compose up` reproducibility.
- Multi-tenancy, admin roles (PRD §4).

### Data Architecture

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | **BFF database engine** | **SQLite** (file-backed, WAL mode) | Workload is tiny (single user, ~10 books, low write rate). Adding a MariaDB container would buy "production-credible feel" but add nothing to the OAuth demo this project exists to demonstrate. Same engine as RS for symmetry; PRD §8 satisfied because each service owns its own file. SQLModel + Alembic are engine-agnostic so this is a config-only difference. |
| D2 | **RS storage engine** | **SQLite** (embedded, file-backed) | RS owns a single tiny table (`reading_speed` keyed by `sub`). Matches D1 — both services use SQLite, each owns its own file. PRD §8 forbids a *shared* DB; separate files keep the data-isolation boundary intact. |
| D3 | **BFF session store backing** | **BFF DB table** (`sessions`) | One more table keyed by random session id, columns: `sub`, `access_token`, `refresh_token`, `id_token`, `expires_at`, `csrf_secret`, `created_at`. Survives restarts. No extra container. |
| D4 | **Migrations** | **Alembic** | Standard SQLModel pairing; matches the archetype's production-credible tone. No `metadata.create_all()` at startup. |
| D5 | **Caching** | **None** beyond the RS's in-process JWKS cache (handled by PyJWT). |

### Authentication & Security

| # | Decision | Choice | Rationale |
|---|---|---|---|
| A1 | **BFF OIDC client library** | **Authlib** (async/httpx integration) | Most mature Python OIDC library, explicit PKCE support. Implemented as a new archetype auth plugin (`keycloak-cookie-session`) alongside `none`/`entra`. The BFF requests scopes `openid offline_access reading-speed:read reading-speed:write` at `/authorize`; `openid` makes it an OIDC flow, `offline_access` ensures a refresh token, and the two domain scopes are the ones the RS will enforce. |
| A2 | **RS JWT validation library** | **PyJWT** (`pyjwt[crypto]`) with `PyJWKClient` | FastAPI-recommended; `python-jose` is effectively abandoned. Genericize the archetype's `entra` mode to accept `(issuer, jwks_url, audience)` and expose it as a `keycloak` / `oidc-bearer` mode. |
| A3 | **PKCE verifier/state storage** | **Server-side `auth_state` row + short-lived state-id cookie** | Transient row holds `code_verifier`, `state`, `nonce`, `return_to`. State-id cookie is signed, `HttpOnly`, `Max-Age=300`. Row deleted on callback. Avoids putting the verifier in a cookie. |
| A4 | **Session cookie attributes** | `HttpOnly; Secure (prod); SameSite=Lax; Path=/; opaque 256-bit value` | `Lax` allows the post-Keycloak callback redirect to carry the cookie; `Strict` would not. Opaque value (not a JWT). |
| A5 | **CSRF strategy** | **Double-submit cookie + custom header + Origin/Referer check** | BFF sets a non-HttpOnly `csrf_token` cookie on session creation; SPA reads it and sends `X-CSRF-Token` on state-changing requests; BFF middleware validates header == cookie. Origin/Referer check as defense in depth. |
| A6 | **Token refresh strategy** | **Reactive — refresh on 401 from RS, single replay** | Simpler than pre-emptive; no clock-skew logic. Bounded: one retry per request. Refresh failure → 401 to SPA → SPA redirects to `/login`. |
| A7 | **Logout flow** | **Revoke refresh token → call `end_session_endpoint` → clear local session → clear cookie** | If revocation fails: BFF still clears local session and returns 204 (UX forbids half-logged-out states). |
| A8 | **SPA CSP** | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'` (served via response header from the SPA SSR edge's Express middleware on every SSR-rendered HTML response; BFF responses are JSON and do not carry CSP — Story 6.4 / Epic 6 amendment) | `'unsafe-inline'` on styles accommodates Tailwind without nonce-injection complexity. |

### API & Communication Patterns

**C1. Path layout**

- **Non-versioned** (mechanics, not domain): `/auth/login`, `/auth/callback`, `/auth/logout`, `/api/me`, `/health`, `/docs`, `/redoc`.
- **Versioned** (domain APIs, per archetype): `/v1/books`, `/v1/books/:id`, `/v1/books/:id/estimate` on BFF; `/v1/reading-speed`, `/v1/estimate` on RS.

**C2. BFF endpoints**

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/api/me` | Return `{ sub, preferred_username }` or 401 | Session cookie |
| GET | `/auth/login?return_to=…` | 302 to Keycloak `/authorize` (with PKCE) | None |
| GET | `/auth/callback?code=…&state=…` | Exchange code, set session cookie, redirect | Auth state cookie |
| POST | `/auth/logout` | Revoke + end-session + clear cookie | Session cookie |
| GET | `/v1/books` | List user's books | Session + CSRF |
| POST | `/v1/books` | Create a book | Session + CSRF |
| GET | `/v1/books/:id` | Read a book | Session + CSRF |
| PATCH | `/v1/books/:id` | Partial update (status / title / pages) | Session + CSRF |
| DELETE | `/v1/books/:id` | Delete | Session + CSRF |
| POST | `/v1/books/:id/estimate` | Forward to RS `/v1/estimate` with the book's pages | Session + CSRF |
| GET | `/v1/reading-speed` | Thin proxy → RS `GET /v1/reading-speed` (BFF adds Authorization header) | Session + CSRF |
| PUT | `/v1/reading-speed` | Thin proxy → RS `PUT /v1/reading-speed` | Session + CSRF |

**C3. Resource Server endpoints**

| Method | Path | Purpose | Required scope |
|---|---|---|---|
| GET | `/v1/reading-speed` | `{ pages_per_hour }` or 404 if unset | `reading-speed:read` |
| PUT | `/v1/reading-speed` | Upsert `{ pages_per_hour }` | `reading-speed:write` |
| POST | `/v1/estimate` | Body `{ pages }`, returns `{ minutes, formatted }` | `reading-speed:read` |

All RS endpoints read user identity from the JWT `sub` claim — no path or body identifier accepted for user.

**C4. Inter-service auth (BFF → RS)**

- BFF includes `Authorization: Bearer <access_token>` on every RS call.
- On RS 401: BFF refreshes via Keycloak token endpoint, retries once. Persisted failure → 401 to SPA.
- BFF never injects user identity into the body or path; the RS reads `sub` from the JWT only.

**C5. `ErrorCode` enum additions** (extend archetype's enum)

```python
class ErrorCode(str, Enum):
    # archetype defaults...
    RESOURCE_SERVER_UNAVAILABLE = "resource_server_unavailable"  # HTTP 503
    READING_SPEED_UNSET         = "reading_speed_unset"          # HTTP 412
    SESSION_EXPIRED             = "session_expired"              # HTTP 401
    FORBIDDEN_SCOPE             = "forbidden_scope"              # HTTP 403
    INVALID_INPUT               = "invalid_input"                # HTTP 422
    BOOK_NOT_FOUND              = "book_not_found"               # HTTP 404
    AUTH_STATE_INVALID          = "auth_state_invalid"           # HTTP 400 (PKCE/state mismatch)
    CSRF_INVALID                = "csrf_invalid"                 # HTTP 403
```

**C6. Timeouts and retries**

- **BFF → RS:** 5s connect, 10s read; **zero retries** on 5xx (per PRD §FR-ERROR-01); single 401-→-refresh-→-replay only.
- **BFF → Keycloak:** 5s/10s; no retries on token endpoint.
- **RS → Keycloak (JWKS):** 5s timeout, in-process cache TTL 24h, key-rotation on `kid` miss (single re-fetch).
- **Health endpoints:** unauthenticated, always-on; readiness depends on DB + (for RS) JWKS reachability.

**C7. JSON serialization** — Distinct API Pydantic models (`BookCreate`, `BookUpdate`, `BookOut`, `EstimateOut`, `ReadingSpeedOut`), not SQLModel ORM classes serialized directly. Keeps internal columns (`created_at`, `sub`) out of responses by construction.

**C8. Pagination / Sorting / Search** — Deferred (PRD §4 / §12).

### Frontend Architecture

**F1. State management** — Signals + one service per feature; no global store.

- `AuthService` (`me`, `logout` signals/methods)
- `BooksService` (`books` signal + CRUD methods)
- `ReadingSpeedService` (`pagesPerHour` signal + get/set methods)
- `ErrorService` — utility for parsing `{errorCode, message, detail}` responses into typed `AppError` discriminated unions

**F2. HTTP interceptors** — Two interceptors:

- `withCredentialsInterceptor` — sets `withCredentials: true` on every request.
- `csrfInterceptor` — reads the `csrf_token` cookie, sets `X-CSRF-Token` header on `POST`/`PUT`/`PATCH`/`DELETE`.

**F3. SPA serving model** — **Same-origin via dedicated SPA edge** (Epic 6 amendment, 2026-05-19). A separate `spa` compose service runs Angular SSR (`@angular/ssr` Express server) on host port `${SPA_HOST_PORT:-4000}`. The Express server SSR-renders HTML, serves the browser bundle, AND reverse-proxies `/auth/*`, `/api/*`, `/v1/*` to `http://bff:8000` over compose DNS via `http-proxy-middleware` v3 (`changeOrigin: true, xfwd: true`). The browser only ever talks to the SPA origin; no Caddy/nginx/Traefik layer involved. Same-origin model preserved — the SPA edge IS the browser-facing origin.

- Dev: bare `docker compose up` brings up the SPA SSR edge alongside the backend; HMR iteration via the containerized SSR dev server (Story 6.1 AC3 + README "Containerized SPA development").
- Prod: same compose service definition; `node dist/spa/server/server.mjs` is the runtime entrypoint.

**F7. SSR cookie forwarding** (Epic 6 amendment, 2026-05-19). Angular SSR's HttpClient issues an outbound `/api/me` during the bootstrap render to populate the auth state. The SPA edge attaches a Node-only HTTP interceptor (`ssrCookieForwardInterceptor`) that reads the incoming browser's `bff_session` + `csrf_token` cookies from the Express `REQUEST` token and threads them into the SSR-time outbound call. Companion: `ssrApiUrlInterceptor` rewrites the relative `/api/me` URL to `${BFF_INTERNAL_URL}/api/me` on the server platform only (no-op in the browser). Bootstrap `/api/me` deduplicated across SSR → hydration via `provideClientHydration(withEventReplay())` + the HttpClient TransferState cache. See `spa/src/app/shared/http/ssr-*.interceptor.ts` (Story 6.1) for the implementation and `spa/src/app/shared/http/ssr-cookie-forward.interceptor.spec.ts` for the pin-test.

**F4. Auth guard** — Functional `authGuard` calling `GET /api/me`. On 401, navigates to `/login?return_to=<original_url>`. Applied to `/books` and `/settings`. `/login` carries an inverse `redirectIfAuthedGuard` that bounces to `/books` if `/api/me` succeeds.

**F5. Routes** (in `app.config.ts` via `provideRouter`):

```ts
[
  { path: '',         pathMatch: 'full', redirectTo: 'books' },
  { path: 'login',    loadComponent: () => import('./login/login-view').then(m => m.LoginView),
                      canActivate: [redirectIfAuthedGuard] },
  { path: 'books',    loadComponent: () => import('./books/book-list-page').then(m => m.BookListPage),
                      canActivate: [authGuard] },
  { path: 'settings', loadComponent: () => import('./settings/settings-page').then(m => m.SettingsPage),
                      canActivate: [authGuard] },
  { path: '**',       redirectTo: 'books' }
]
```

**F6. Performance** — Defaults are fine: zoneless + signals + OnPush by default; lazy-loaded routes via `loadComponent`. No service worker, no PWA.

### Infrastructure & Deployment

**I1. Repo structure** — Monorepo:

```
.
├── spa/                                # Angular v21 app
├── services/
│   ├── bff/                            # FastAPI BFF (from archetype)
│   └── resource-server/                # FastAPI RS (from archetype)
├── keycloak/
│   └── realm-bmad-books.json           # version-controlled realm
├── e2e/                                # Playwright project (separate package)
├── compose/
│   ├── infra.yml                       # Keycloak
│   └── app.yml                         # BFF, RS, SPA (prod build only)
├── tools/
│   └── fastapi-archetype/              # cloned archetype (gitignored)
├── docker-compose.yml                  # top-level glue via `include:` + profiles
├── .env.example
└── README.md
```

**I2. Compose composition** — Top-level `docker-compose.yml` uses Compose's `include:` directive (Compose v2.20+) to pull in the two sub-files.

**Compose profile model (post-Epic-6).** One unconditional baseline stack (Keycloak + BFF + RS + SPA SSR edge); one optional profile `e2e` that scopes the Playwright runner container. Bare `docker compose up` brings up the baseline stack; `just e2e-up` brings up the e2e profile with the `compose/app.e2e.yml` overlay activating `ENABLE_TEST_RESET=true` + `AUTH_TYPE=oidc_bearer`. The historical `default` / `dev` profile names were retired by the D140/D141 follow-up at baseline `5f9b0f7`; Story 6.2 added the `spa` service to the unconditional baseline; Story 6.3 removed the BFF's host-published port so the BFF is internal-only on the compose network.

**I3. Keycloak realm-as-code** — `keycloak/realm-bmad-books.json`:

- Realm `bmad-books`, mode `start-dev --import-realm` for dev, `start --import-realm --optimized` for prod-mode demo.
- Client `bmad-books-bff` — confidential, Auth Code + PKCE enabled, `client_secret` from env, redirect URIs `http://localhost:${SPA_HOST_PORT:4000}/auth/callback` (+ configurable prod URL); Story 6.2 flipped the host from `:8000` (BFF, retired) to `:${SPA_HOST_PORT:4000}` (SPA SSR edge — the browser-facing origin) via Keycloak / Quarkus MicroProfile substitution. See I9 for the substitution semantics.
- Client scopes `reading-speed:read`, `reading-speed:write` defined as `optional` and granted to the BFF client by default — the client requests them in the `scope` param.
- Audience claim `bmad-books-resource-server` mapped onto the access token (so the RS validates `aud`).
- Pre-seeded users (see I4).

**I4. Test users** — Two pre-seeded users in the realm:

- `testuser` / `testpassword` — normal user; gets a default reading speed seeded by the RS on first `/v1/reading-speed` PUT call (or starts unset and is set by the test).
- `freshuser` / `freshpassword` — second user with **no reading-speed value**; exercises the `412` precondition path in J3.

**I5. Env vars** — Single `.env.example` at repo root documenting all required vars; per-service `.env` files gitignored; compose `env_file:` per service.

Required vars (illustrative):
`KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`, `BFF_DATABASE_URL` (e.g., `sqlite+aiosqlite:////data/bff.db`), `RS_DATABASE_URL` (e.g., `sqlite+aiosqlite:////data/rs.db`), `BFF_BASE_URL`, `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `OIDC_CLIENT_ID`, `BFF_SESSION_COOKIE_NAME`, `BFF_CSRF_COOKIE_NAME`, `BFF_SESSION_COOKIE_SECURE`.

**Persistence:** each backend service mounts a named Docker volume at `/data` (e.g., `bff_data`, `rs_data`), and its SQLite file lives there. The volumes survive container recreation but are removed on `docker compose down -v`.

**I6. SPA serving in compose** (Epic 6 amendment, 2026-05-19) — Both dev and prod-shaped: the `spa` compose service (built from `spa/Dockerfile`, Node multi-stage `deps → build → runtime`) runs Angular SSR (`@angular/ssr` Express server) on host port `${SPA_HOST_PORT:-4000}`. The BFF has no host-published port; it is internal-only on the compose network. Bare `docker compose up` brings up the full baseline stack including the SPA edge (Story 6.2). Dev iteration on the SPA happens inside the `spa` container — no host Node toolchain required.

**I9. Keycloak realm port pin** (Epic 6 amendment, 2026-05-19). `keycloak/realm-bmad-books.json` registers `http://localhost:${SPA_HOST_PORT:4000}` for the BFF client's `redirectUris`, `webOrigins`, and `attributes.post.logout.redirect.uris` via Keycloak / Quarkus MicroProfile substitution (bare `:` form, NOT POSIX `:-`). The Keycloak service in `compose/infra.yml` receives `SPA_HOST_PORT` as an env pass-through so the substitution resolves at boot. Default is `4000`; configurable via the repo-root `.env` `SPA_HOST_PORT` override (Story 6.2). The two substitution forms in the repo are NOT interchangeable: the bare `:` form (Quarkus) is used inside the realm JSON only; the POSIX `:-` form (Bash-style) is used inside compose YAML files.

**I7. CI/CD** — Out of scope for this educational project; the PRD only requires `docker-compose up` reproducibility. (A small GitHub Actions workflow could be added later: lint + tests + docker build + Playwright run.)

**I8. Production deployment** — Out of scope (PRD §4); success criterion is `docker-compose up` end-to-end.

### Decision Impact Analysis

**Implementation Sequence:**

1. Repo scaffold + Keycloak realm + compose skeleton (boots Keycloak).
2. BFF scaffolded from archetype; baseline `/health` + `/api/me` (anonymous-only) running.
3. BFF cookie-session OIDC plugin (`/auth/login` / `/auth/callback` / `/auth/logout`); J1 verified end-to-end with `curl` + a hardcoded SPA stub.
4. SPA scaffolded with Angular v21 + Tailwind; `LoginView` + `TopChrome` + `authGuard` complete J1 from the SPA side.
5. BFF books domain + Alembic migration + CRUD endpoints; SPA `BookList` + `BookForm` + `BookRow` + `StatusControl` complete J2.
6. RS scaffolded from archetype; JWKS-validated `/v1/reading-speed` GET/PUT with scope enforcement.
7. RS `/v1/estimate` + BFF `/v1/books/:id/estimate` forwarding; SPA `EstimateCell` + `SettingsView` complete J3 + J4.
8. J5 logout end-to-end (revoke + end-session); J6 error rendering verified by killing the RS container.
9. Playwright E2E covering J1–J6 against the running compose.
10. Security review documentation; coverage push.

**Cross-Component Dependencies:**

- The BFF cookie-session plugin (A1) gates everything frontend-visible — build it first.
- `ErrorCode` enum (C5) is shared in intent between BFF and RS; copy the values verbatim into each service's enum (no shared library).
- JWKS validation (A2) on RS is the foundation for scope enforcement; reuses archetype `entra` plumbing.
- Compose `include:` requires Compose v2.20+; document in README.
- The BFF→RS audience claim mapping (I3) must be in place before the RS can validate `aud`.

## Implementation Patterns & Consistency Rules

These rules exist to prevent AI agents working in parallel from making divergent, conflicting choices about the same problem. They are **mandatory for all generated code** in this project, on both the backend (BFF + RS) and the frontend (SPA).

### Naming Patterns

**Database (BFF + RS — SQLModel + Alembic):**

- Tables: **plural, `snake_case`** — `books`, `sessions`, `auth_states`, `reading_speeds`.
- Columns: `snake_case` — `id`, `sub`, `pages_per_hour`, `created_at`, `updated_at`.
- Primary key: a column literally named `id`; integer auto-increment is the default; switch to UUID only if there is an external-stability reason.
- `sub` column: VARCHAR(255), indexed; never use it as a primary key.
- Foreign keys: `<referenced_table_singular>_id` (e.g., `book_id` — not used in v1 because the schema has no FKs, but the convention is set).
- Indexes: `ix_<table>_<columns_joined_by_underscore>` (Alembic's autogenerate default). One explicit index on `books.sub`, `auth_states.expires_at`, `sessions.expires_at`, `reading_speeds.sub`.
- Timestamps: every persisted entity has `created_at TIMESTAMP NOT NULL` and `updated_at TIMESTAMP NOT NULL` columns; UTC; managed by SQLModel default factories and `onupdate`.

**HTTP API (BFF + RS):**

- Resource paths: `kebab-case`, plural for collections — `/v1/books`, `/v1/reading-speed` (singular because it's a singleton per user, not a collection), `/v1/estimate` (action endpoint).
- Path parameters: `{id}` (FastAPI brace syntax); type-annotated in the handler signature.
- Query parameters: `snake_case` — `return_to`, `state`, `code`.
- Headers (custom): `X-CSRF-Token`, `X-Request-Id` (the latter set by a simple UUID middleware in the request pipeline; used for log correlation).
- JSON field names in **both directions: `snake_case`**. The BFF does not transform field names for the SPA. The SPA's TypeScript models also use `snake_case` field names to keep wire and model identical. *(This is the deliberate boring choice — no case conversion layer.)*

**Python code (backend services):**

- Files: `snake_case.py`. Test files: `test_<name>.py`.
- Modules / packages: `snake_case`.
- Functions, methods, variables: `snake_case` (PEP 8).
- Classes (including Pydantic models, SQLModels, Exception classes): `PascalCase` — `Book`, `BookCreate`, `BookOut`, `ReadingSpeedUnsetError`.
- Constants: `UPPER_SNAKE_CASE` at module scope.
- Enum members: `UPPER_SNAKE_CASE` (matches archetype's `ErrorCode` style).
- Private internals: leading underscore `_func()`, `_var`.
- Type hints: required everywhere; `from __future__ import annotations` permitted but not required.

**TypeScript / Angular code (SPA):**

- Files: `kebab-case` per Angular 2025 style guide — `book-row.ts`, `book-row.html`, `book-row.css`, `books-service.ts`, `auth-guard.ts`. **No `.component.` / `.service.` infix**; the role is the export name, not the file suffix.
- Tests: `<name>.spec.ts` colocated with the source.
- Variables, functions, methods, signals: `camelCase`.
- Classes, components, types, interfaces: `PascalCase` — `BookRow`, `BooksService`, `Book`.
- Constants: `UPPER_SNAKE_CASE` for true compile-time constants; `camelCase` for runtime config values.
- Angular component selectors: prefix `app-` + kebab-case — `<app-book-row>`, `<app-top-chrome>`.
- Pipe selectors: `camelCase` — `{{ duration | formatMinutes }}`. (No pipes in v1; convention recorded.)
- File names mirror the export they primarily export — `book-row.ts` exports class `BookRow`.

### Structural Patterns

**Repository layout** (recap from Core Decisions §I1):

```
spa/                  services/bff/         services/resource-server/
keycloak/             e2e/                  compose/
tools/                docker-compose.yml    .env.example
```

**Backend services (archetype layout, preserved):**

```
services/<svc>/
├── src/<svc>/
│   ├── api/                # FastAPI routers, one file per resource
│   ├── services/           # business logic, one file per domain concept
│   ├── auth/               # auth plugins (`keycloak_cookie_session.py` on BFF; `oidc_bearer.py` on RS)
│   ├── core/               # config (pydantic-settings), DI, exceptions
│   ├── aop/                # logging decorator wiring
│   └── db/                 # SQLModel models, session helpers, Alembic env
├── tests/                  # mirrors src/<svc>/ structure: api/, services/, auth/, core/, aop/
├── alembic/                # migrations
├── pyproject.toml
├── uv.lock
└── Dockerfile
```

- **Per-resource router file.** `api/books.py` on BFF contains exactly one `APIRouter` for `/v1/books`. `api/auth.py` contains `/auth/*`. No "god routers."
- **One service module per domain concept.** `services/books_service.py`, `services/reading_speed_service.py`, `services/estimate_service.py`.
- **Exceptions live in `core/exceptions.py`** as domain-specific exception classes (e.g., `BookNotFoundError`). Handlers in `core/error_handlers.py` map them to `ErrorCode` + HTTP status.
- **Tests mirror source paths** — a function in `src/bff/services/books_service.py` is tested by `tests/services/test_books_service.py`.

**Frontend (Angular feature-folder layout):**

```
spa/src/app/
├── books/                  # BookListPage, BookRow, BookForm, StatusControl, EstimateCell, books-service.ts
├── settings/               # SettingsPage, reading-speed-service.ts
├── login/                  # LoginView
├── auth/                   # auth-guard.ts, redirect-if-authed-guard.ts, auth-service.ts
├── shared/
│   ├── http/               # interceptors (with-credentials, csrf)
│   ├── errors/             # error types, error-service.ts, AppError discriminated union
│   ├── chrome/             # TopChrome component
│   └── ui/                 # ErrorMessage component (cross-feature)
├── app.config.ts           # provideRouter, provideHttpClient, providers
├── app.routes.ts           # route table
├── app.ts                  # root component (App)
└── app.html
```

- **Feature folders own their state.** A feature's signals and services live in the folder; cross-feature shared state lives in `shared/`.
- **No barrel files** (`index.ts` re-exports) unless a folder has 4+ external consumers. Avoids accidental dependency cycles.
- **Tests colocated** — `book-row.spec.ts` sits next to `book-row.ts`.

**E2E (`e2e/`):**

- `tests/journey-1-login.spec.ts`, `tests/journey-2-books.spec.ts`, etc. — one file per PRD journey J1–J6.
- `fixtures/` for seeded test users and helpers (`logInAs(page, "testuser")`).

### Format Patterns

**API response shapes:**

- **Success:** return the resource directly (FastAPI/Pydantic default). No `{data: ...}` wrapper.

  ```json
  // GET /v1/books/123
  { "id": 123, "title": "Dune", "pages": 688, "status": "reading",
    "created_at": "2026-05-14T12:34:56Z", "updated_at": "2026-05-14T12:34:56Z" }
  ```

- **Failure (archetype envelope, mandatory):**

  ```json
  { "errorCode": "reading_speed_unset",
    "message": "Reading speed has not been set for this user",
    "detail": null }
  ```

- **Collection success:** plain JSON array (no envelope, no pagination metadata since pagination is deferred).

  ```json
  // GET /v1/books
  [{ "id": 1, ... }, { "id": 2, ... }]
  ```

- **Empty 204 responses:** no body, ever.

**HTTP status codes (binding rules):**

| Status | When | `ErrorCode` |
|---|---|---|
| 200 | Read or non-creating update success with body | — |
| 201 | Create success; body is the created resource; `Location` header set | — |
| 204 | DELETE success; `POST /auth/logout` | — |
| 302 | OAuth redirects from `/auth/login` and `/auth/callback` | — |
| 400 | PKCE state / nonce / `code` parameter invalid | `auth_state_invalid` |
| 401 | No session, expired session, JWT invalid | `session_expired` |
| 403 | CSRF token missing/mismatch; scope insufficient | `csrf_invalid` / `forbidden_scope` |
| 404 | Resource not found (book) | `book_not_found` |
| 412 | Precondition unmet (reading speed unset, on estimate) | `reading_speed_unset` |
| 422 | Pydantic validation failure | `invalid_input` |
| 503 | Resource Server unreachable from BFF (FR-ERROR-01 / J6) | `resource_server_unavailable` |

- **404 on `GET /v1/reading-speed` is not an error** in the same sense as a missing book — it carries `errorCode: "reading_speed_unset"` so the SPA can distinguish from a transport-level 404.

**Date/time:**

- All timestamps in JSON: **ISO 8601 with `Z`** (UTC). `2026-05-14T12:34:56Z`.
- All timestamps in the DB: UTC, naive `DATETIME` (no timezone column) — services convert at the edge.
- Durations (estimate output): two fields side by side — `minutes: 260` (integer, for tests) and `formatted: "≈ 4 h 20 m"` (string, what the UI renders).

**Booleans / Nulls:**

- JSON booleans use `true`/`false`. Never `1`/`0`.
- Nullable fields are present and null, not omitted: `"updated_at": null`. The SPA's TypeScript models declare `T | null` explicitly.

### Communication Patterns

**State management (SPA):**

- **All state lives in signals.** `signal()`, `computed()`, `effect()`. No NgRx, no behavior subjects, no global event bus.
- **Immutable updates:** never mutate the inner value of a signal. Use `mySignal.set(newValue)` or `mySignal.update(prev => [...prev, x])`. ESLint rule recommended but not blocking.
- **Service methods are the only write paths.** Components never call `signal.set()` directly on someone else's signal; they call `booksService.addBook(...)` which writes to the service-owned signal.
- **Loading state is local.** Each component or service method that fires a request owns its own `loading = signal(false)`. No global "isLoading" flag.

**Error handling (SPA):**

- All HTTP calls go through services that return `Promise<T> | Observable<T>` and **always parse error responses via `ErrorService.parse(httpError)`** into a typed `AppError` discriminated union:

  ```ts
  type AppError =
    | { kind: 'reading_speed_unset' }
    | { kind: 'resource_server_unavailable' }
    | { kind: 'session_expired' }
    | { kind: 'forbidden_scope' }
    | { kind: 'invalid_input';  detail?: unknown }
    | { kind: 'book_not_found' }
    | { kind: 'csrf_invalid' }
    | { kind: 'auth_state_invalid' }
    | { kind: 'network' }
    | { kind: 'unknown';         status: number };
  ```

- Components handle `AppError` via `switch` on `kind`. **A component MUST handle the error case before rendering "success" UI.** ESLint rule: forbid bare `.catch(() => {})`.
- The `session_expired` kind is special — the global HTTP interceptor reroutes to `/login?return_to=…` automatically. Components do not handle it locally.

**Error handling (backend services):**

- Business code raises **domain exceptions** from `core/exceptions.py`, never `HTTPException`:

  ```python
  class BFFError(Exception):
      error_code: ErrorCode
      http_status: int

  class BookNotFoundError(BFFError):
      error_code = ErrorCode.BOOK_NOT_FOUND
      http_status = 404

  class ReadingSpeedUnsetError(BFFError):
      error_code = ErrorCode.READING_SPEED_UNSET
      http_status = 412
  ```

- A single exception handler in `core/error_handlers.py` catches `BFFError` and emits the archetype envelope. Validation errors from Pydantic are caught by FastAPI and mapped to `invalid_input` via a small adapter.
- **No `print()`.** Logging via `logger = logging.getLogger(__name__)`; the archetype's AOP `log_io` decorator covers service-method I/O at DEBUG. Exceptions log at ERROR with full traceback. INFO is for service-lifecycle events; WARN for "expected but interesting" (e.g., the 401-from-RS that triggers a refresh attempt).

**Inter-service communication:**

- BFF → RS calls go through a single client class `ResourceServerClient` (in `services/`) that:
  - Adds `Authorization: Bearer <access_token>` from the current session,
  - Catches httpx connection errors / timeouts and raises `ResourceServerUnavailableError`,
  - Catches RS-401 and performs the single refresh-and-replay cycle.
- Components/handlers never call the RS directly; they always go through this client.

### Process Patterns

**Validation:**

- **Backend:** Pydantic models validate at the boundary. Required fields are required; positive-integer fields use `conint(gt=0)` or `Field(ge=1)`. Business invariants beyond schema (e.g., "title not all whitespace") are validated in services and raise `InvalidInputError` mapping to `invalid_input` / 422.
- **Frontend:** Reactive Forms validators run on submit (per UX). On submit failure, inputs preserve their values, an `ErrorMessage` renders below the form, focus does not jump. Validation never blocks typing.

**Loading state UI** (codifies UX patterns into a rule for agents):

- A button in flight relabels (`"Estimate"` → `"Estimating…"`) and disables. No spinner overlay, no skeleton.
- A list loading from scratch shows a single line: `Loading…` in `--color-text-muted`.
- Optimistic UI is permitted **only** for same-service, low-stakes mutations — currently only the book-row status PATCH. Cross-service operations are always pessimistic.

**Retry & failure:**

- The SPA **does not retry on its own**. If the user wants to retry, they click again. (Exception: the global interceptor that follows `401 + return_to` redirect is a navigation, not a retry.)
- The BFF retries **exactly once** on a `401` from the RS, after refreshing the access token. No other retries on the BFF.
- The RS does not retry on its own.

**Logging conventions:**

- **DEBUG:** AOP-decorated service method I/O (handled by archetype). Verbose detail.
- **INFO:** Service lifecycle (`"BFF started, listening on :8000"`), session lifecycle (`"session_created sub=<sub>"`), shutdown.
- **WARN:** Expected-but-noteworthy paths — 401-from-RS triggering refresh, JWKS key rotation re-fetch, settle/retry interactions.
- **ERROR:** Unhandled exceptions, RS unreachable surfaced as 503, configuration failures at startup.
- **No PII in any log.** `sub` is acceptable (it's an opaque UUID-like identifier). Never log tokens, access codes, refresh tokens, JWT bodies, full session ids — log first 8 chars + ellipsis when correlation is needed.
- All logs structured (JSON output via the archetype's logging config). The per-request `X-Request-Id` (set by the request-id middleware) is included in each log line so requests can be correlated across services.

**Testing patterns:**

- **Backend unit tests:** pytest. One test class per service module. Fixtures in `conftest.py` provide the in-memory SQLite engine and a `TestClient`. Auth tests use the archetype's synthetic IdP pattern (test-generated RSA keypair, monkey-patched HTTP) — extended for our `oidc-bearer` mode.
- **Backend integration tests:** same harness, but exercise full request → handler → service → DB. No mocking of internal layers.
- **Frontend unit/component tests:** Vitest + Angular TestBed. Components are tested with HTTP mocked (`HttpTestingController`) and signals asserted via their getter. Services are tested with a real `HttpClient` against `HttpTestingController`.
- **E2E tests:** Playwright. **No mocks of any layer.** Real Keycloak, real BFF, real RS, real DB. Each test starts from a known seed state (test user, no books) and tears down between tests via a fixture that hits a hidden `POST /v1/test/reset` endpoint enabled only in the E2E compose profile.

### Enforcement Guidelines

**All AI agents MUST:**

- Match the file/folder layout above. New files go where the convention dictates; never create top-level `utils/` or `lib/` dumping grounds.
- Use `snake_case` for JSON field names on both BFF and RS; do not introduce case conversion at the SPA boundary.
- Use the `ErrorCode` enum for every non-success response. **Never** return `{"detail": "..."}` from FastAPI's default `HTTPException` without first mapping it through `core/error_handlers.py`.
- Use domain exceptions on the backend; never raise bare `HTTPException` in business code.
- Use `signal()` for SPA state; never introduce a parallel store (BehaviorSubject, RxJS subject for state, NgRx) without explicit architectural amendment.
- Add tests in the mirroring location for every new module.
- Never log secrets, tokens, codes, or full session/cookie values.
- Never silently retry a cross-service call.

**Pattern verification:**

- Ruff enforces Python naming/format conventions (the archetype already configures the relevant rules).
- ESLint with `@angular-eslint/recommended` enforces Angular conventions and the file-naming style guide. Custom ESLint rule recommended: forbid empty `catch` blocks and `console.log` outside test files.
- A simple pre-commit script (or CI step, if added) runs `ruff check`, `ty`, `pytest`, `npm run lint`, `npm run test`.
- New `ErrorCode` values require an entry in the table in §"Format Patterns / HTTP status codes" — code-review-enforced, not automated.

**Updating patterns:**

- This document is the source of truth. Pattern changes are appended to a "Pattern Amendments" subsection (to be added on first amendment), not made by silent edit.

### Pattern Examples

**Good (book listing endpoint on BFF):**

```python
# src/bff/api/books.py
@router.get("/v1/books", response_model=list[BookOut])
async def list_books(
    session: SessionDep,
    sub: AuthenticatedSubDep,
) -> list[BookOut]:
    books = await books_service.list_for_user(session, sub)
    return [BookOut.from_orm(b) for b in books]
```

```ts
// spa/src/app/books/books-service.ts
@Injectable({ providedIn: 'root' })
export class BooksService {
  private readonly http = inject(HttpClient);
  readonly books = signal<Book[]>([]);

  async load(): Promise<void> {
    const list = await firstValueFrom(this.http.get<Book[]>('/v1/books'));
    this.books.set(list);
  }
}
```

**Anti-patterns (will be rejected in review):**

- A FastAPI handler that returns `{"data": ..., "error": null}` — wrong shape.
- A handler that raises `HTTPException(status_code=404, detail="not found")` — bypasses `ErrorCode` envelope.
- A component that mutates `this.booksService.books().push(newBook)` — mutating a signal's inner value.
- An interceptor or service that silently retries a `503` — violates FR-ERROR-01 / UX J6.
- A new file named `BookRow.component.ts` — wrong; Angular 2025 style guide is `book-row.ts`.
- A SPA model with `pagesPerHour` — wrong; the wire is `pages_per_hour`, the SPA mirrors it.
- A backend test under `tests/utils/` for code that lives in `src/<svc>/services/` — must mirror source path.
- Logging `logger.debug(f"access_token={token}")` — secrets in logs.

## Project Structure & Boundaries

### Complete Project Directory Structure

```
bmad-books/                                      # repo root (monorepo)
├── docker-compose.yml                           # top-level glue: `include:` + profiles
├── .env.example                                 # all required env vars documented
├── .gitignore
├── .dockerignore
├── README.md                                    # setup, arch overview, AI integration log
├── CLAUDE.md                                    # project conventions (already in repo)
│
├── compose/
│   ├── infra.yml                                # Keycloak
│   └── app.yml                                  # BFF + Resource Server + SPA (prod build only)
│
├── keycloak/
│   ├── realm-bmad-books.json                    # version-controlled realm: client, scopes, users
│   └── Dockerfile                               # thin wrapper for realm import on startup
│
├── services/
│   ├── bff/                                     # Backend-for-Frontend (FastAPI; from archetype)
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   ├── Dockerfile                           # multi-stage: SPA build → Python build → final
│   │   ├── .env.example
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   ├── script.py.mako
│   │   │   └── versions/                        # migration files (0001_init.py, ...)
│   │   ├── src/bff/
│   │   │   ├── __init__.py
│   │   │   ├── __main__.py                      # uvicorn entry point
│   │   │   ├── app.py                           # FastAPI factory, router registration, middleware
│   │   │   ├── api/                             # one router file per resource family
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py                      # /auth/login, /auth/callback, /auth/logout
│   │   │   │   ├── me.py                        # /api/me
│   │   │   │   ├── books.py                     # /v1/books CRUD + /v1/books/{id}/estimate
│   │   │   │   ├── reading_speed.py             # /v1/reading-speed proxy → RS
│   │   │   │   └── test_reset.py                # /v1/test/reset (e2e profile only)
│   │   │   ├── services/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── books_service.py
│   │   │   │   ├── session_service.py
│   │   │   │   └── resource_server_client.py    # BFF → RS HTTP client w/ refresh-replay
│   │   │   ├── auth/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── keycloak_cookie_session.py   # NEW: cookie-session OIDC client plugin
│   │   │   │   ├── pkce.py                      # PKCE verifier/challenge helpers
│   │   │   │   └── csrf.py                      # CSRF middleware (double-submit + Origin)
│   │   │   ├── core/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── config.py                    # pydantic-settings; required vars validated
│   │   │   │   ├── exceptions.py                # BFFError + domain subclasses
│   │   │   │   ├── error_codes.py               # ErrorCode enum
│   │   │   │   ├── error_handlers.py            # FastAPI exception → envelope mapping
│   │   │   │   └── di.py                        # FastAPI Depends() providers
│   │   │   ├── aop/
│   │   │   │   ├── __init__.py
│   │   │   │   └── logging.py                   # apply_logging + log_io decorator
│   │   │   ├── db/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── session_factory.py           # async engine + session (sqlite+aiosqlite)
│   │   │   │   └── models/
│   │   │   │       ├── __init__.py
│   │   │   │       ├── book.py
│   │   │   │       ├── session.py
│   │   │   │       └── auth_state.py
│   │   │   └── static/                          # SPA dist mounted here in prod image
│   │   └── tests/                               # mirrors src/bff/ structure
│   │       ├── conftest.py
│   │       ├── api/
│   │       │   ├── test_auth.py
│   │       │   ├── test_me.py
│   │       │   ├── test_books.py
│   │       │   └── test_reading_speed_proxy.py
│   │       ├── services/
│   │       │   ├── test_books_service.py
│   │       │   ├── test_session_service.py
│   │       │   └── test_resource_server_client.py
│   │       ├── auth/
│   │       │   ├── test_keycloak_cookie_session.py
│   │       │   ├── test_pkce.py
│   │       │   └── test_csrf.py
│   │       ├── core/
│   │       │   └── test_error_handlers.py
│   │       └── fixtures/
│   │           ├── synthetic_idp.py             # test RSA keypair + monkeypatched HTTP
│   │           └── seed.py
│   │
│   └── resource-server/                         # Resource Server (FastAPI; from archetype)
│       ├── pyproject.toml
│       ├── uv.lock
│       ├── Dockerfile
│       ├── .env.example
│       ├── alembic.ini
│       ├── alembic/
│       │   ├── env.py
│       │   ├── script.py.mako
│       │   └── versions/
│       ├── src/resource_server/
│       │   ├── __init__.py
│       │   ├── __main__.py
│       │   ├── app.py
│       │   ├── api/
│       │   │   ├── __init__.py
│       │   │   ├── reading_speed.py             # /v1/reading-speed GET/PUT
│       │   │   ├── estimate.py                  # /v1/estimate POST
│       │   │   └── test_reset.py                # /v1/test/reset (e2e profile)
│       │   ├── services/
│       │   │   ├── __init__.py
│       │   │   ├── reading_speed_service.py
│       │   │   └── estimate_service.py
│       │   ├── auth/
│       │   │   ├── __init__.py
│       │   │   └── oidc_bearer.py               # NEW: genericized JWKS bearer for Keycloak
│       │   ├── core/
│       │   │   ├── __init__.py
│       │   │   ├── config.py
│       │   │   ├── exceptions.py
│       │   │   ├── error_codes.py
│       │   │   ├── error_handlers.py
│       │   │   └── di.py
│       │   ├── aop/
│       │   │   ├── __init__.py
│       │   │   └── logging.py
│       │   └── db/
│       │       ├── __init__.py
│       │       ├── session_factory.py           # async engine + session (sqlite+aiosqlite)
│       │       └── models/
│       │           ├── __init__.py
│       │           └── reading_speed.py
│       └── tests/
│           ├── conftest.py
│           ├── api/
│           │   ├── test_reading_speed.py
│           │   └── test_estimate.py
│           ├── services/
│           │   ├── test_reading_speed_service.py
│           │   └── test_estimate_service.py
│           ├── auth/
│           │   └── test_oidc_bearer.py
│           └── fixtures/
│               └── synthetic_idp.py
│
├── spa/                                         # Angular v21 SPA
│   ├── package.json
│   ├── package-lock.json
│   ├── angular.json
│   ├── tsconfig.json
│   ├── tsconfig.app.json
│   ├── tsconfig.spec.json
│   ├── .postcssrc.json                          # { "plugins": { "@tailwindcss/postcss": {} } }
│   ├── .eslintrc.json                           # @angular-eslint/recommended + project rules
│   ├── src/server.ts                            # Angular SSR Express edge + http-proxy-middleware mount (Story 6.1)
│   ├── vitest.config.ts
│   ├── public/
│   │   └── favicon.ico
│   ├── src/
│   │   ├── main.ts
│   │   ├── index.html
│   │   ├── styles.css                           # @import "tailwindcss"; @theme tokens (UX-spec'd)
│   │   └── app/
│   │       ├── app.config.ts                    # providers (router, http, interceptors)
│   │       ├── app.routes.ts                    # functional route table
│   │       ├── app.ts                           # root App component (TopChrome + <router-outlet>)
│   │       ├── app.html
│   │       ├── app.css
│   │       ├── app.spec.ts
│   │       ├── books/
│   │       │   ├── book-list-page.{ts,html,css,spec.ts}
│   │       │   ├── book-row.{ts,html,css,spec.ts}
│   │       │   ├── book-form.{ts,html,css,spec.ts}
│   │       │   ├── status-control.{ts,html,css,spec.ts}
│   │       │   ├── estimate-cell.{ts,html,css,spec.ts}
│   │       │   ├── books-service.{ts,spec.ts}
│   │       │   └── book.types.ts                # Book, BookStatus, BookCreate, BookOut
│   │       ├── settings/
│   │       │   ├── settings-page.{ts,html,css,spec.ts}
│   │       │   ├── reading-speed-service.{ts,spec.ts}
│   │       │   └── reading-speed.types.ts
│   │       ├── login/
│   │       │   └── login-view.{ts,html,css,spec.ts}
│   │       ├── auth/
│   │       │   ├── auth-guard.{ts,spec.ts}
│   │       │   ├── redirect-if-authed-guard.{ts,spec.ts}
│   │       │   ├── auth-service.{ts,spec.ts}
│   │       │   └── auth.types.ts                # Me, AuthStatus
│   │       └── shared/
│   │           ├── http/
│   │           │   ├── with-credentials-interceptor.{ts,spec.ts}
│   │           │   └── csrf-interceptor.{ts,spec.ts}
│   │           ├── errors/
│   │           │   ├── app-error.types.ts       # AppError discriminated union
│   │           │   └── error-service.{ts,spec.ts}
│   │           ├── chrome/
│   │           │   └── top-chrome.{ts,html,css,spec.ts}
│   │           └── ui/
│   │               └── error-message.{ts,html,css,spec.ts}
│   └── Dockerfile.build                         # only used by BFF's multi-stage to produce dist/
│
├── e2e/                                         # Playwright (separate npm project)
│   ├── package.json
│   ├── playwright.config.ts
│   ├── tsconfig.json
│   ├── tests/
│   │   ├── j1-first-login.spec.ts
│   │   ├── j2-manage-books.spec.ts
│   │   ├── j3-estimate.spec.ts
│   │   ├── j4-adjust-speed.spec.ts
│   │   ├── j5-logout.spec.ts
│   │   └── j6-rs-unavailable.spec.ts
│   └── fixtures/
│       ├── users.ts                             # testuser / freshuser credentials
│       └── helpers.ts                           # logInAs, resetState, killRs
│
├── tools/
│   └── fastapi-archetype/                       # cloned archetype (gitignored)
│
└── _bmad-output/                                # planning + implementation artifacts
    ├── planning-artifacts/
    │   ├── PRD.md
    │   ├── PRD-validation-report.md
    │   ├── ux-design-specification.md
    │   └── architecture.md
    └── implementation-artifacts/
```

### Architectural Boundaries

**API boundaries (who talks to whom):**

```
┌──────────────┐  HTML + assets (SSR)  ┌────────────────────┐  reverse-proxy   ┌──────────────────────────┐
│              │ ◄───────────────────  │                    │ ───────────────► │                          │
│   Browser    │   (HttpOnly cookies,  │  SPA SSR edge      │  /auth /api /v1  │           BFF            │
│              │ ───────────────────►  │  (Angular SSR Node │ ◄─────────────── │     (FastAPI, books)     │
│              │   X-CSRF-Token hdr)   │   + Express proxy) │  JSON snake_case │                          │
└──────────────┘                       └────────────────────┘                  │  ┌─────────────────────┐ │
                                                                               │  │  cookie-session     │ │
                                                                               │  │  OIDC client        │ │
                                                                               │  │  (Authlib)          │ │
                                                                               │  └─────────────────────┘ │
                                                                               └────┬─────────────┬────────┘
                                                                                    │             │
                                                                 Auth Code + PKCE   │             │ Bearer JWT
                                                                 refresh, end-sess  │             │ (forward user
                                                                 (Authlib)          │             │  access token)
                                                                                    ▼             ▼
                                                                          ┌──────────────┐  ┌──────────────────┐
                                                                          │              │  │                  │
                                                                          │   Keycloak   │  │  Resource Server │
                                                                          │   (realm     │  │  (FastAPI; JWKS  │
                                                                          │   imported)  │◄─┤   validation;    │
                                                                          │              │  │   scope enforce) │
                                                                          └──────────────┘  └──────────────────┘
                                                                              JWKS fetch (RS → Keycloak, cached 24h)
```

- **Browser ↔ SPA edge ↔ BFF:** the only authenticated channel from the browser. Cookie auth (HttpOnly session cookie), CSRF via double-submit (`X-CSRF-Token` header). Same-origin from the browser's perspective — the SPA SSR edge is the browser-facing origin and reverse-proxies cookies + CSRF headers byte-for-byte to the BFF over compose DNS (Story 6.1's `http-proxy-middleware` mount in `spa/src/server.ts`).
- **SPA ↔ Resource Server:** **never**. The SPA does not call the RS directly.
- **BFF ↔ Keycloak:** OAuth Code + PKCE round-trip (`/authorize`, `/token`, `/end_session`, `/revocation`). Tokens stay server-side.
- **BFF ↔ Resource Server:** REST with `Authorization: Bearer <user_access_token>`. Single 401-→-refresh-→-replay cycle.
- **Resource Server ↔ Keycloak:** JWKS endpoint only, periodically cached. No session, no token exchange, no admin API.

**Component boundaries:**

- **Each backend service is its own deployable.** Its `pyproject.toml`, `Dockerfile`, and `tests/` are self-contained; no cross-service Python imports.
- **Each Angular feature folder owns its state.** `books/` owns `BooksService` and the books signal; nothing imports books state from another feature.
- **`shared/` is a hub for cross-feature primitives** (interceptors, error types, `TopChrome`, `ErrorMessage`). It must not import from feature folders.
- **`core/` (backend, per archetype) is the cross-cutting hub** for config, exceptions, error handlers. Other modules may import from `core/`, but `core/` never imports from `api/` or `services/`.

**Data boundaries:**

- **BFF database** (SQLite file, WAL mode, in a named Docker volume) — owns `books`, `sessions`, `auth_states`. Keyed by `sub` where applicable. The RS never reads this DB.
- **Resource Server storage** (SQLite file, in a separate named volume) — owns `reading_speeds`. Keyed by `sub`. The BFF never reads this DB; it always asks the RS via HTTP.
- **Keycloak DB** (internal H2 or embedded; outside our concern) — owns users, refresh tokens, sessions. No other service reads it.
- **`sub`** is the only identifier that crosses service boundaries. It originates in the JWT `sub` claim, is passed to the BFF session row, and is read directly from the JWT on the RS.

### Requirements to Structure Mapping

**FR-AUTH-01 — OIDC login + BFF session (J1)**

- BFF: `src/bff/auth/keycloak_cookie_session.py` (OIDC client plugin), `src/bff/auth/pkce.py`, `src/bff/api/auth.py` (`/auth/login`, `/auth/callback`), `src/bff/services/session_service.py`, `src/bff/db/models/session.py`, `src/bff/db/models/auth_state.py`
- SPA: `src/app/login/login-view.{ts,html}` (the "Log in" button), `src/app/auth/auth-service.ts`, `src/app/auth/auth-guard.ts`, `src/app/auth/redirect-if-authed-guard.ts`
- Keycloak: realm definition in `keycloak/realm-bmad-books.json`
- Tests: `services/bff/tests/auth/test_keycloak_cookie_session.py`, `services/bff/tests/api/test_auth.py`, `spa/src/app/auth/*.spec.ts`, `e2e/tests/j1-first-login.spec.ts`

**FR-BOOK-01 — Book CRUD (J2)**

- BFF: `src/bff/api/books.py` (CRUD handlers excluding the estimate), `src/bff/services/books_service.py`, `src/bff/db/models/book.py`, Alembic migration `alembic/versions/0001_init.py`
- SPA: `src/app/books/book-list-page.ts`, `book-row.ts`, `book-form.ts`, `status-control.ts`, `books-service.ts`, `book.types.ts`
- Tests: `services/bff/tests/api/test_books.py`, `services/bff/tests/services/test_books_service.py`, `spa/src/app/books/*.spec.ts`, `e2e/tests/j2-manage-books.spec.ts`

**FR-SPEED-01 — Read/update reading speed (J4)**

- Resource Server: `src/resource_server/api/reading_speed.py` (GET/PUT, scope-enforced), `src/resource_server/services/reading_speed_service.py`, `src/resource_server/db/models/reading_speed.py`, Alembic migration
- BFF: `src/bff/api/reading_speed.py` — thin proxy router so the SPA's same-origin call lands on the BFF, which forwards to the RS with the bearer token via `ResourceServerClient`
- SPA: `src/app/settings/settings-page.ts`, `reading-speed-service.ts`, `reading-speed.types.ts`
- Tests: `services/resource-server/tests/api/test_reading_speed.py`, `services/resource-server/tests/services/test_reading_speed_service.py`, `services/bff/tests/api/test_reading_speed_proxy.py`, `spa/src/app/settings/*.spec.ts`, `e2e/tests/j4-adjust-speed.spec.ts`

**FR-ESTIMATE-01 — Reading-time estimate (J3)**

- Resource Server: `src/resource_server/api/estimate.py`, `src/resource_server/services/estimate_service.py`
- BFF: `src/bff/api/books.py` exposes `POST /v1/books/{id}/estimate`; `src/bff/services/resource_server_client.py` does the BFF→RS call
- SPA: `src/app/books/estimate-cell.ts` (button → request → render)
- Tests: `services/resource-server/tests/api/test_estimate.py`, `services/resource-server/tests/services/test_estimate_service.py`, `services/bff/tests/services/test_resource_server_client.py`, `spa/src/app/books/estimate-cell.spec.ts`, `e2e/tests/j3-estimate.spec.ts`

**FR-LOGOUT-01 — Logout + AS revocation (J5)**

- BFF: `src/bff/api/auth.py` (`/auth/logout`), `src/bff/auth/keycloak_cookie_session.py` (revocation + end-session calls), `src/bff/services/session_service.py` (delete session row)
- SPA: `src/app/shared/chrome/top-chrome.ts` (logout button), `src/app/auth/auth-service.ts` (logout method)
- Tests: `services/bff/tests/api/test_auth.py::test_logout_*`, `spa/src/app/auth/auth-service.spec.ts`, `e2e/tests/j5-logout.spec.ts`

**FR-ERROR-01 — Honest J6 error surface**

- BFF: `src/bff/services/resource_server_client.py` (maps httpx errors / 5xx to `ResourceServerUnavailableError`), `src/bff/core/error_handlers.py` (maps to 503 + `ErrorCode.RESOURCE_SERVER_UNAVAILABLE`)
- SPA: `src/app/books/estimate-cell.ts` and `src/app/settings/settings-page.ts` render the dedicated J6 state; `src/app/shared/errors/error-service.ts` parses the error envelope
- Tests: `services/bff/tests/services/test_resource_server_client.py::test_*_unavailable`, `spa/src/app/books/estimate-cell.spec.ts::test_renders_j6_state`, `e2e/tests/j6-rs-unavailable.spec.ts`

### Cross-Cutting Concerns Mapping

| Concern | Location |
|---|---|
| OAuth/OIDC client plumbing | `services/bff/src/bff/auth/keycloak_cookie_session.py`, `.../auth/pkce.py` |
| Session management | `services/bff/src/bff/services/session_service.py`, `.../db/models/session.py` |
| JWKS validation + caching | `services/resource-server/src/resource_server/auth/oidc_bearer.py` |
| Scope enforcement | `services/resource-server/src/resource_server/auth/oidc_bearer.py` (via archetype's `RoleMappingProvider`) |
| CSRF protection | `services/bff/src/bff/auth/csrf.py` (middleware), `spa/src/app/shared/http/csrf-interceptor.ts` (client) |
| SPA security (CSP, cookies) | `services/bff/src/bff/app.py` (response-header middleware) |
| Identity propagation (`sub`) | Read from JWT in `oidc_bearer.py`; written into session in `session_service.py`; never injected into bodies |
| Error mapping | `services/{bff,resource-server}/src/.../core/error_handlers.py`; `spa/src/app/shared/errors/error-service.ts` |
| Container orchestration | `docker-compose.yml`, `compose/*.yml` |
| Realm-as-code | `keycloak/realm-bmad-books.json` |
| E2E harness | `e2e/` |

### Integration Points

**Internal communication (in order of call):**

1. **SPA → BFF (HTTP, cookie+CSRF).** Same-origin. JSON snake_case in both directions. CSP served from BFF.
2. **BFF → Keycloak (HTTP, OAuth flows).** `/authorize` (redirect), `/token` (POST), `/end_session` (POST), `/revocation` (POST). PKCE on every authorize.
3. **BFF → Resource Server (HTTP, bearer JWT).** Forwards the user's access token. Single 401-refresh-replay cycle. Honest timeouts: 5s connect / 10s read.
4. **Resource Server → Keycloak (HTTP, JWKS).** Cached 24h, re-fetched on `kid` miss.

**External integrations:**

- **Keycloak** — only external dependency; bundled in compose, configured by `realm-bmad-books.json`. No real OIDC provider needed.
- **No third-party SaaS.** No payment, analytics, error reporting, feature flags, etc.

**Data flow — J3 (estimate request) end-to-end:**

```
1. User clicks "Estimate" on book row (SPA)
2. EstimateCell → BooksService.requestEstimate(bookId)
3. SPA HTTP POST /v1/books/{id}/estimate
   - cookie: session_id=…
   - header: X-CSRF-Token: …
4. BFF /v1/books/{id}/estimate handler:
   - validates session cookie + CSRF
   - looks up book by (sub, id) in BFF SQLite → gets pages
   - calls ResourceServerClient.compute_estimate(access_token, pages)
5. BFF → RS HTTP POST /v1/estimate
   - header: Authorization: Bearer <access_token>
   - body: { "pages": 688 }
6. RS /v1/estimate handler:
   - validates JWT (signature via JWKS, iss, aud, exp)
   - enforces `reading-speed:read` scope
   - calls estimate_service.compute(sub, pages)
   - service reads reading_speeds row by sub → 30 pages/hour
   - returns { "minutes": 1376, "formatted": "≈ 22 h 56 m" }
7. Response: RS → BFF → SPA
8. EstimateCell.estimate signal set → button replaced with formatted duration in the row
```

**Failure path — J6 (RS unavailable):**

```
5'. BFF → RS POST /v1/estimate (httpx)
    - ConnectError or 5xx or timeout
6'. ResourceServerClient.compute_estimate raises ResourceServerUnavailableError
7'. BFF error_handlers maps to:
    - HTTP 503
    - body: { "errorCode": "resource_server_unavailable", "message": "...", "detail": null }
8'. SPA HTTP interceptor → ErrorService.parse → AppError { kind: "resource_server_unavailable" }
9'. EstimateCell renders "Service unavailable — try again shortly" in the row's estimate cell
```

### File Organization Patterns

**Configuration:**

- Root: `docker-compose.yml`, `.env.example`, `.gitignore`, `.dockerignore`, `README.md`, `CLAUDE.md`.
- Per backend service: `pyproject.toml`, `uv.lock`, `Dockerfile`, `.env.example`, `alembic.ini`.
- Per frontend: `package.json`, `angular.json`, `tsconfig*.json`, `.postcssrc.json`, `.eslintrc.json`, `proxy.conf.json`, `vitest.config.ts`.
- Per service env: per-service `.env` files (gitignored), loaded via compose `env_file:`.

**Source:**

- Backend: feature-by-layer (`api/`, `services/`, `auth/`, `core/`, `db/`, `aop/`) per archetype.
- Frontend: feature-folder (`books/`, `settings/`, `login/`, `auth/`, `shared/`) per Angular 2025 style guide.

**Tests:**

- Backend: under `tests/` mirroring `src/<svc>/` structure (`tests/api/...`, `tests/services/...`).
- Frontend: `*.spec.ts` colocated next to source.
- E2E: separate `e2e/` package with one `j<N>-...spec.ts` per PRD journey.

**Assets:**

- SPA static assets: `spa/public/`. In production they end up in `spa/dist/spa/browser/` and are served directly by the SPA SSR edge's Express static-asset middleware (Story 6.1 `server.ts`). The Story-1.14 BFF-static-mount path (`src/bff/static/`) was retired by Story 6.3.
- No backend static assets (`/health`, `/docs`, `/redoc` are dynamic).

### Development Workflow Integration

**Dev (single-terminal, post-Epic-6):**

```bash
# Full stack including the SPA SSR edge — bare docker compose up.
docker compose up
```

`docker compose up` brings up Keycloak + BFF + RS + SPA SSR edge (the unconditional baseline stack — Story 6.2 added the `spa` service; the D140/D141 follow-up at baseline `5f9b0f7` retired the `dev` / `default` profile names). Each backend service mounts a named volume at `/data` for its SQLite file, so state survives container recreation; the SPA service holds no on-disk state.

**Containerized SPA dev (HMR-style iteration):**

```bash
# One-shot the SPA container with a volume mount + the SSR dev entrypoint.
docker compose run --rm --service-ports -v "$(pwd)/spa:/workspace" spa npm run serve:ssr:spa
```

See Story 6.1 AC3 + README "Containerized SPA development" for the variant `npm run watch` invocation. No host Node toolchain is required beyond what `docker compose` provides — the legacy `ng serve` on `:4200` workflow was retired by Story 6.1.

**Full stack (production-shaped):**

```bash
docker compose up   # full stack — Keycloak + BFF + RS + SPA SSR edge
```

Same as the dev workflow above. The SPA SSR edge's multi-stage `spa/Dockerfile` (`deps → build → runtime`) compiles the Angular SSR bundle and runs `node dist/spa/server/server.mjs` at container start. Only the SPA edge container exposes a user-facing host port (`${SPA_HOST_PORT:-4000}`); the BFF is internal-only on the compose network.

**E2E:**

```bash
docker compose --profile e2e up    # full stack + Playwright runner depending on health checks
```

The Playwright container reads seeded users from the realm import, runs the six journey specs, and tears down state between tests via `POST /v1/test/reset` (enabled only in the e2e profile).

**Build process:**

- Backend services: `uv build` → wheel; Dockerfile multi-stage `uv sync --frozen` → `python:3.14-slim` runtime stage.
- SPA: `npm ci && npm run build` → `dist/spa/browser/`. In the BFF's multi-stage Dockerfile, this happens in a `node:20-alpine` stage that copies dist into the final BFF image.

**Deployment shape:**

- Out of scope for production beyond `docker compose up` reproducibility (PRD §4).
- The single `docker-compose.yml` (with `include:` of `compose/*.yml`) is the deployment artifact for the educational reference.

### Operational Details

These pin down a few cross-cutting operational concerns that earlier sections referenced but did not specify:

**Health checks and `depends_on` ordering:**

Every container exposes a health probe. Compose `depends_on: { condition: service_healthy }` gates start order so PRD §9's ordering requirement is met.

- **Keycloak** — `HEALTHCHECK` curls `http://localhost:8080/health/ready`; ready when realm import has completed.
- **BFF** — `GET /health` returns 200 once the DB is reachable, Alembic migrations are at head, and the OIDC discovery doc (`OIDC_ISSUER_URL/.well-known/openid-configuration`) is fetchable. Depends on Keycloak (because discovery is fetched at startup).
- **Resource Server** — `GET /health` returns 200 once the DB is reachable, Alembic migrations are at head, and the JWKS endpoint is fetchable. Depends on Keycloak.
- **SPA prod container** — n/a (the SPA is baked into the BFF image; no separate container in prod). In the `e2e` profile the Playwright runner depends on BFF + RS + Keycloak healthchecks.

**Migrations on startup:**

Each backend service runs `alembic upgrade head` as the container entrypoint's first step, before starting `uvicorn`. The Dockerfile's `CMD` is wrapped in a small shell entrypoint (`entrypoint.sh`) that:

```bash
#!/bin/sh
set -e
uv run alembic upgrade head
exec uv run uvicorn <pkg>.app:app --host 0.0.0.0 --port 8000
```

This makes the container's "ready" state coincide with "schema at head," which the `/health` probe then reports.

**BFF routing precedence (when serving SPA static):**

The BFF mounts routes in this order — first match wins:

1. `/health`, `/docs`, `/redoc`
2. `/auth/*`, `/api/*`
3. `/v1/*`
4. Static SPA bundle at `/` — falls back to `index.html` for any unmatched path that does not match (1)–(3) so HTML5 history routing works on direct URL visits (e.g., reloading `/settings`).

The fallback is implemented as a catch-all route that serves `index.html` only for requests with `Accept: text/html`; for other content types it returns 404 with the standard envelope.

**`POST /v1/test/reset` (e2e profile only):**

- Available only when `ENABLE_TEST_RESET=true` is set; production builds must omit this env var.
- On the BFF: truncates `books`, `sessions`, `auth_states` (not Keycloak data).
- On the RS: truncates `reading_speeds`.
- Both endpoints require a shared bearer token from `TEST_RESET_TOKEN` env var to prevent accidental invocation. The Playwright fixture sets this header.
- Returns 204 on success. No-ops in production builds (returns 404 if the env flag is off, so the route doesn't exist at all).

**Token storage at rest (accepted risk):**

- The BFF's `sessions` table stores `access_token`, `refresh_token`, and `id_token` columns in plaintext within the SQLite file.
- Mitigation: the SQLite file lives in a named Docker volume not exposed to the network; the BFF process is the only consumer.
- This is an **accepted risk for the educational reference** — out of scope per PRD §4 ("Production hardening beyond what the course's success criteria require"). A production deployment would either encrypt the columns (e.g., via an application-level KEK) or move sessions to a dedicated encrypted store.
- The documented security review (`docs/security-review.md`, PRD §9 deliverable) must call this out explicitly.

**Idle / absolute session timeout:**

- Absolute timeout: equal to Keycloak's refresh-token lifetime (default 30 days; configurable in the realm). When `expires_at` on the session row is reached, the next request gets 401 and the SPA bounces to login.
- Idle timeout: not explicitly enforced beyond the access-token + refresh-token expiry chain. If a session is unused for longer than the refresh-token lifetime, refresh fails on next request → 401 → re-login.
- This is sufficient for the educational reference; production deployments would typically set tighter timeouts and add explicit idle tracking.

## Architecture Validation Results

### Coherence Validation ✅

**Decision compatibility:**

- Stack is internally consistent: Python 3.14 + FastAPI + SQLModel (archetype) + Authlib (BFF OIDC) + PyJWT (RS JWKS) — all are current, maintained, and supported together. Angular v21 + Tailwind v4 + Vitest is internally consistent and current as of May 2026.
- No cross-decision conflicts: SQLite for both services satisfies PRD §8's "no shared DB" by giving each service its own file; the cookie-session BFF model is compatible with same-origin SPA serving; reactive token refresh fits the BFF's request-per-call model.
- Versions verified by web search where it mattered (Angular 21, Tailwind v4, Python OIDC/JWT library landscape).

**Pattern consistency:**

- Naming: `snake_case` everywhere on the wire and in Python; `kebab-case` files + `camelCase` symbols on the SPA per Angular 2025 style guide. No case-conversion layer.
- Error contract: `{errorCode, message, detail}` is honored end-to-end — emitted by both backends, parsed by the SPA's `ErrorService` into a typed `AppError` discriminated union.
- Loading-state rules in §"Process Patterns" match the UX spec's "button relabel + disable, no global spinner."
- Inline-error-at-action rendering (UX) is enforced by component placement (`EstimateCell` renders the J6 state in its own slot) and by the SPA convention "no global toasts."

**Structure alignment:**

- Repository layout maps cleanly to the boundaries: backend services are independent deployables with no Python cross-imports; SPA features are isolated folders that import only from `shared/`.
- Every FR has a concrete file path in §"Requirements to Structure Mapping."
- The added BFF `/v1/reading-speed` proxy endpoints (post-validation fix) close the structure-vs-decisions inconsistency that existed in the draft.

### Requirements Coverage Validation ✅

**Functional requirements:**

| FR | Architectural support |
|---|---|
| FR-AUTH-01 | `keycloak_cookie_session.py` plugin + `/auth/*` routes + Authlib + Keycloak realm; J1 covered. |
| FR-BOOK-01 | BFF `/v1/books` CRUD + SQLModel `Book` + Alembic + SPA `books/` feature folder; J2 covered. |
| FR-SPEED-01 | RS `/v1/reading-speed` GET/PUT (scope-gated) + BFF proxy at `/v1/reading-speed` + SPA `settings/`; J4 covered. |
| FR-ESTIMATE-01 | RS `/v1/estimate` (scope-gated) + BFF `/v1/books/:id/estimate` + `ResourceServerClient` + SPA `EstimateCell`; J3 covered. |
| FR-LOGOUT-01 | BFF `/auth/logout` with revocation + end-session + local clear; SPA `TopChrome` logout button; J5 covered. |
| FR-ERROR-01 | `ResourceServerClient` maps httpx/5xx → `ResourceServerUnavailableError` → 503 + `ErrorCode.RESOURCE_SERVER_UNAVAILABLE` → SPA `AppError`; J6 covered. |

**Non-functional requirements (PRD §§8–9):**

- **All 9 PRD §8 constraints have explicit implementing decisions** (token isolation, BFF as confidential client, transparent refresh, stateless RS, JWKS-based validation, `sub` as identity, scope at RS, no BFF bypass, reproducible realm).
- **`docker-compose up` reproducibility:** addressed by the Compose `include:` + profiles model with health-check-gated dependency ordering.
- **Test coverage ≥70%:** the backend archetype targets >90% by default (stricter); the SPA aims at 70% via Vitest. Both above floor.
- **≥5 E2E tests with real OAuth flow:** six Playwright specs (J1–J6), each driving the real Keycloak login.
- **Security review document:** flagged as a separate `docs/security-review.md` deliverable; covers the topics PRD §9 enumerates (token storage/transport, cookie attrs, CSRF, JWT validation, scope enforcement, XSS/injection) plus the explicit accepted-risk note on at-rest token storage.
- **Env vars / compose profiles / secrets not committed:** all addressed in §I5 / §"Operational Details."

**UX journeys J1–J6:** each journey has a named flow in the UX spec, a named E2E spec file (`e2e/tests/j<N>-...spec.ts`), and component-level support in the SPA structure.

### Implementation Readiness Validation ✅

**Decision completeness:**

- All critical decisions documented with rationale and (where relevant) library/version. The two ambiguities found during validation (BFF reading-speed proxy, OAuth scope string) have been closed inline.
- The "open architectural choices" list from step 2 was fully resolved in step 4 — nothing left unspecified.

**Structure completeness:**

- Project tree enumerates every file path an implementing agent would create, including tests, fixtures, Alembic versions, and per-service Dockerfiles.
- The repository layout, archetype-derived service layout, and Angular feature-folder layout are all spelled out with intent.

**Pattern completeness:**

- Naming, structure, format, communication, and process patterns each have rules + concrete examples + anti-patterns.
- Enforcement story: Ruff + `ty` + ESLint + pytest + Vitest catch most divergences automatically; code-review captures the rest.

### Gap Analysis Results

**Critical gaps (resolved):**

- ✅ BFF `/v1/reading-speed` proxy endpoints added to Core Decisions §C2.
- ✅ OAuth scope request string (`openid offline_access reading-speed:read reading-speed:write`) added to §A1.

**Important gaps (resolved):**

- ✅ Health-check semantics + compose `depends_on` ordering specified in "Operational Details."
- ✅ Alembic-on-startup wrapper script specified.
- ✅ BFF route precedence (API → SPA static fallback for HTML5 history routing) specified.
- ✅ `POST /v1/test/reset` semantics + env-flag gating specified.

**Minor gaps (accepted / noted):**

- 🔶 Tokens stored unencrypted in BFF SQLite — accepted risk for the educational reference (PRD §4 out-of-scope production hardening); must be called out in `docs/security-review.md`.
- 🔶 Multi-stage BFF Dockerfile combines Node + Python build stages — accepted trade-off (single image, single container at runtime).
- 🔶 Session idle vs absolute timeout policy — accepted as implementation detail; absolute timeout follows Keycloak's refresh-token lifetime.

**Items deferred (out-of-scope per PRD):**

- CI/CD pipeline.
- Token revocation propagation beyond standard refresh invalidation on logout.
- Caching, rate limiting, pagination, search/sorting.
- Multi-tenancy / admin roles / production hardening.

### Architecture Completeness Checklist

**Requirements Analysis**

- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**

- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed (defaults from frameworks; no perf NFR beyond UX latency targets in J3)

**Implementation Patterns**

- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**

- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** **READY FOR IMPLEMENTATION**

All 16 checklist items are `[x]`; no critical or important gaps remain open. The two minor accepted-risk items are explicitly documented and assigned to the future `docs/security-review.md` deliverable.

**Confidence Level:** **high**

- The decisions are all grounded in the PRD, the UX spec, the user-mandated backend archetype, and current (May 2026) versions of the chosen libraries.
- The cookie-session BFF + bearer-JWT RS + Keycloak topology is a textbook OAuth/OIDC pattern with abundant reference material — implementation risk is implementation-effort, not architectural uncertainty.
- The Angular v21 + Tailwind v4 SPA surface is small enough (~10 components, 3 routes) that the framework choice cannot dominate the work.

**Key Strengths:**

- The defining architectural interaction (J3 estimate) is fully traced end-to-end at every layer — diagram, sequence flow, file paths, error path.
- Service-ownership boundaries are unambiguous: BFF owns books + sessions; RS owns reading-speed; Keycloak owns users + tokens. No service trespasses.
- The backend archetype eliminates an entire category of bike-shedding (lint config, error envelope shape, pydantic-settings config, AOP logging wiring) by mandate.
- Honest-failure behavior (J6) is enforced by both a coded rule (`ResourceServerClient` raises `ResourceServerUnavailableError`; SPA renders the named state) and a Playwright spec that asserts it by killing the RS container.

**Areas for Future Enhancement:**

- At-rest encryption for tokens in the BFF SQLite (production hardening).
- Tighter session idle timeouts with explicit tracking (production hardening).
- Move the BFF session store to a dedicated, encrypted store if the deployment scales beyond a single BFF instance.
- A GitHub Actions CI workflow (lint + test + build + Playwright) is a small follow-up that the architecture explicitly accommodates but does not require.

### Implementation Handoff

**AI Agent Guidelines:**

- Follow all architectural decisions in §"Core Architectural Decisions" exactly as documented.
- Apply implementation patterns from §"Implementation Patterns & Consistency Rules" without deviation. Pattern amendments go in a new "Pattern Amendments" subsection of this document, never silently in code.
- Respect the project structure in §"Project Structure & Boundaries." New files go where the convention dictates.
- For any architectural question not resolved by this document, **stop and ask** rather than improvise — silent improvisation across parallel agents is the failure mode this document exists to prevent.

**First implementation priority:**

The implementation sequence in §"Decision Impact Analysis" begins with:

```bash
# 1. Clone the archetype
git clone https://github.com/tommaso-meledina/fastapi-archetype.git tools/fastapi-archetype

# 2. Scaffold the BFF
python tools/fastapi-archetype/scripts/build_template.py \
  -n bff -o services/bff \
  --description "BMAD_books Backend-for-Frontend (OAuth client, books domain)"

# 3. Scaffold the Resource Server
python tools/fastapi-archetype/scripts/build_template.py \
  -n resource-server -o services/resource-server \
  --description "BMAD_books Resource Server (reading speed, estimate)"

# 4. Scaffold the SPA
npx -p @angular/cli@21 ng new spa \
  --routing --style=css --ssr=true --skip-git \
  --package-manager=npm --strict
cd spa && npm install -D tailwindcss @tailwindcss/postcss postcss
```

These three commands should be the first three implementation stories. The Keycloak realm + compose skeleton (implementation-sequence step 1) and the BFF baseline `/health` + `/api/me` (step 2) follow immediately.
