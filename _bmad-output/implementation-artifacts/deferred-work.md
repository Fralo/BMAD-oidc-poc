# Deferred Work

Findings surfaced during step-04 review that are not in scope for the originating story but worth tracking so a later story owner can address them.

## From Story 1.1 review (2026-05-14)

### D1 — `.env.example` SQLite paths assume in-container `/data` mount

**Surfaced by:** Edge-case hunter, blind hunter
**Files:** `.env.example` (BFF_DATABASE_URL, RS_DATABASE_URL)
**Issue:** The placeholder URLs `sqlite+aiosqlite:////data/bff.db` and `…/rs.db` use the 4-slash absolute-path form pointing at `/data`. That path exists inside the BFF/RS containers (named volumes mounted at `/data`, per architecture I5), but not on a developer's host. A dev who runs the BFF on the host under the `dev` profile (per `docker-compose.yml` header comment) will hit `unable to open database file`.
**Belongs to:** Story 1.3 (BFF scaffold) and Story 3.1 (RS scaffold) — both will introduce per-profile env overrides (or document a host-side `data/` directory + per-host `.env` override). Story 1.1's job was only to enumerate AR29 vars; value-vs-perspective is a downstream concern.
**Severity:** important (deferred, not a Story 1.1 defect).

### D2 — OIDC URLs use container-internal hostname; browser-facing redirects will fail without a host alias

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `.env.example` (OIDC_ISSUER_URL, OIDC_JWKS_URL, OIDC_AUDIENCE, OIDC_CLIENT_ID)
**Issue 1:** `OIDC_ISSUER_URL` and `OIDC_JWKS_URL` resolve `keycloak:8080` via Docker DNS — fine for in-cluster traffic (BFF → Keycloak token exchange, RS → JWKS fetch). But the OIDC redirect step happens in the **browser** on the host, which cannot resolve `keycloak`. Stories 1.4–1.5 (BFF cookie/OIDC plugin) will need either a published port + `127.0.0.1 keycloak` `/etc/hosts` entry, or a split issuer (e.g., `KEYCLOAK_EXTERNAL_URL` for browser redirects, `OIDC_ISSUER_URL` for back-channel) reconciled by Keycloak's `frontendUrl` setting.
**Issue 2:** `OIDC_AUDIENCE == OIDC_CLIENT_ID == bff-client`. Keycloak does not put the client ID in the `aud` claim by default; without an audience mapper on the `bff-client` (or with token-introspection rather than local JWT validation in the RS), audience validation will fail.
**Belongs to:** Story 1.2 (Keycloak realm-as-code — owns the audience mapper) and Stories 1.4/1.5 (BFF OIDC plugin — owns the browser-facing redirect topology).
**Severity:** important (deferred; will cause real failures in Stories 1.4/1.5/3.2 if not handled there).

## Deferred from: code review of 1-1-repo-scaffold-compose-skeleton (second pass, 2026-05-14)

### D3 — `change-me` placeholder credentials are silently accepted at runtime

**Surfaced by:** Blind hunter, edge-case hunter (second pass)
**Files:** `.env.example` (`KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`, `TEST_RESET_TOKEN`)
**Issue:** AC #5 explicitly endorses `change-me` placeholders in `.env.example`, so this is not a Story 1.1 defect. The runtime risk is that a developer who literally copies `.env.example` → `.env` and runs `docker compose up` will boot Keycloak and the BFF with `change-me` as a real admin password / client secret / test-reset token. No downstream "you forgot to override this" guard exists. The "never enable in prod" comment for `ENABLE_TEST_RESET` is documentation, not enforcement.
**Belongs to:** Story 1.2 (Keycloak realm-as-code) — refuse boot if `KEYCLOAK_ADMIN_PASSWORD == change-me` outside the `dev` profile. Story 1.4 (BFF auth-state schema) or Story 1.5 (BFF cookie/OIDC plugin) — refuse boot if `BFF_CLIENT_SECRET == change-me` outside `dev`. Story 1.12 (BFF `/v1/test/reset`) — refuse boot if `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN == change-me`.
**Severity:** important (deferred; would not affect Story 1.1's AC but will cause silent misconfiguration once services exist).

### D4 — Per-service `.dockerignore` strategy is implicit

**Surfaced by:** Edge-case hunter (second pass)
**Files:** `.dockerignore` (repo root)
**Issue:** The repo-root `.dockerignore` is implicitly written for the case where `docker build` uses the repo root as its context. If Stories 1.3 / 3.1 instead use per-service contexts (`context: services/bff`, `context: services/resource-server`), the repo-root `.dockerignore` will not apply at all and a fresh per-service `.dockerignore` is needed. Conversely, if those stories use root context for per-service builds, the build context will over-include unrelated services. The architectural decision is not made by Story 1.1 and is not documented anywhere.
**Belongs to:** Story 1.3 (BFF scaffold) and Story 3.1 (RS scaffold) — must explicitly choose context strategy (root vs. service) and either rely on root `.dockerignore` or author per-service `.dockerignore` files.
**Severity:** important (architectural decision deferred; not a Story 1.1 defect).

### D5 — `.gitignore` `**/.env` whitelist is overly narrow

**Surfaced by:** Edge-case hunter (second pass)
**Files:** `.gitignore`
**Issue:** The pattern `**/.env` followed by only `!.env.example` whitelisting means any future per-service env template that is not named exactly `.env.example` (e.g., `services/bff/.env.dev`, `services/bff/.env.test`, `services/bff/.env.local.template`) is silently ignored. A contributor adds such a file, commits, and it does not get tracked; `git status` does not surface it. CI on a fresh clone breaks.
**Belongs to:** Whichever later story introduces per-service env templates (likely Stories 1.3 / 3.1 / 1.8). When that story lands, broaden the whitelist (e.g., `!**/.env.*.example`, `!**/.env.template`) and document the convention.
**Severity:** nit (deferred; only bites if a contributor introduces a non-`.env.example` template).

## Deferred from: code review of 1-2-keycloak-realm-as-code-compose-service (2026-05-14)

### D6 — Hard-coded `http://localhost:8000` redirect / post-logout URIs in realm JSON

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `keycloak/realm-bmad-books.json` (`redirectUris`, `attributes.post.logout.redirect.uris`)
**Issue:** The realm hard-codes `http://localhost:8000` for the BFF's redirect and post-logout URIs. `.env.example` exposes `BFF_BASE_URL` (currently the same value), so a contributor who points the BFF at a different host/port silently breaks the login redirect — Keycloak returns an opaque "Invalid redirect URI" with no link back to the source of truth.
**Belongs to:** Whichever later story introduces env substitution in the realm import (or per-environment realm overlays) — most likely Story 1.5 (BFF cookie/OIDC plugin), where the browser-facing redirect topology is finalized alongside D2's hostname split.
**Severity:** nit (deferred; only bites contributors who change `BFF_BASE_URL`).

### D7 — `offline_access` optional scope without an explicit refresh-token max lifespan

**Surfaced by:** Blind hunter
**Files:** `keycloak/realm-bmad-books.json` (`optionalClientScopes`, `offlineSessionIdleTimeout`)
**Issue:** The BFF client lists `offline_access` in `optionalClientScopes` and the realm sets `offlineSessionIdleTimeout: 2592000` (30 days) but does not set `offlineSessionMaxLifespan`. If a future BFF story ever requests `offline_access`, refresh tokens could live indefinitely (rolling 30-day idle) with no hard cap.
**Belongs to:** Whichever story actually exercises refresh-token / offline-session behavior — earliest plausible owner is Story 1.5 (BFF OIDC plugin). If that story does NOT request `offline_access`, drop the scope from the client to avoid dead config.
**Severity:** nit (deferred; no current consumer of the scope).

### D8 — Browser↔container hostname split for OIDC discovery (re-flag of D2)

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `compose/infra.yml` (`KC_HOSTNAME`), `.env.example` (`OIDC_ISSUER_URL`)
**Issue:** This story closes the realm side of D2 (audience mapper + `.env.example` alignment) but explicitly leaves the browser-vs-container hostname split open per its own Dev Notes ("Closing D2 (deferred from Story 1.1)"). `KC_HOSTNAME=localhost` + `KC_HOSTNAME_STRICT=false` makes Keycloak emit `http://localhost:8080` in discovery — browser-correct — but the BFF's back-channel `OIDC_ISSUER_URL=http://keycloak:8080/...` will see a JWT `iss` of `http://localhost:8080/...`, an issuer-mismatch that must be reconciled before Story 1.5's token validation can succeed.
**Belongs to:** Stories 1.4/1.5 (BFF auth-state schema + cookie/OIDC plugin) — they own the actual back-channel OIDC discovery + token exchange, and therefore own the choice of how to reconcile internal vs external issuer.
**Severity:** important (deferred; will block Story 1.5 if not handled there).

### D9 — No build-time validation of `realm-bmad-books.json`

**Surfaced by:** Edge-case hunter
**Files:** `keycloak/Dockerfile`
**Issue:** A malformed `realm-bmad-books.json` (typo, trailing comma, missing brace) is only caught at container start, after the image has been built and pulled into the dev's compose stack. A cheap `jq .` validation step in the Dockerfile (or in CI later) would fail-fast at build time.
**Belongs to:** A later infra-hardening / CI story — most likely Story 5.x in the final-coverage epic. Not blocking for Story 1.2.
**Severity:** nit (deferred; defensive polish).

## Deferred from: code review of 1-8-spa-scaffold-tailwind-v4-design-tokens (2026-05-14)

### D10 — Dev proxy glob `/auth/*`, `/api/*`, `/v1/*` may not match bare segment or deeply nested paths

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `spa/proxy.conf.json`
**Issue:** AC3 mandates exactly these three glob patterns. Under modern http-proxy-middleware (webpack-dev-server v5 lineage), `/auth/*` matches `/auth/<one-segment>` but not the bare `/auth` (no trailing slash) and not deep paths like `/auth/realms/master/.well-known/openid-configuration`. Story 1.8 verifies the proxy by configuration only, not by live BFF roundtrip, so this is invisible at this story. When Story 1.5 (BFF OIDC plugin) or Story 1.9 (SPA AuthService) exercises the proxy end-to-end and discovers a route silently falling through to `index.html`, broaden the patterns (likely `/auth/**` or `**/auth/**`) — or replace with explicit path arrays.
**Belongs to:** Story 1.5 (BFF cookie/OIDC plugin — first to exercise `/auth/*` for real) or Story 1.9 (SPA AuthService — first to issue cross-proxy XHR from the SPA).
**Severity:** important (deferred; will cause silent SPA-fallback misroutes during integration).

### D11 — Smoke-fragment test asserts class names only, not computed styles

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `spa/src/app/app.spec.ts`
**Issue:** The test asserts `smoke.classList.contains('bg-surface-muted')` etc. — a string presence check against the literal class attribute. It does NOT verify that Tailwind v4 actually compiled `--color-surface-muted` into a working utility. If a future PR mistypes the `@theme` token (e.g., `--color-surface-mute`), the utility silently fails to materialize (resolves to an unset CSS var) while `app.spec.ts` continues to pass because the class literal in `app.html` still matches the assertion. Mitigate later with a computed-style assertion in a real component's spec — Story 1.10 (`TopChrome`) is the first real candidate.
**Belongs to:** Story 1.10 (first real component spec) or whichever story formalizes a "design-token utility" test helper.
**Severity:** nit (deferred; the smoke fragment is throwaway and will be replaced in Story 1.10 anyway).

### D12 — `*.test.ts` files would be discovered by Vitest at runtime but excluded from `tsconfig.spec.json`

**Surfaced by:** Edge-case hunter
**Files:** `spa/tsconfig.spec.json`
**Issue:** Vitest's default discovery glob accepts both `*.spec.ts` and `*.test.ts`. The TS spec project's `include: ["src/**/*.d.ts", "src/**/*.spec.ts"]` covers only the former. A developer who follows Vitest convention and writes `foo.test.ts` will see it run at runtime with no type-checking and no `vitest/globals` types in scope. The diff does not standardize on one suffix. Settle the convention in a downstream story — either widen the include to `**/*.{spec,test}.ts` or document that `.spec.ts` is the project's required suffix.
**Belongs to:** Whichever story first introduces a non-default test file (likely Story 1.9 AuthService spec, or Story 2.4 BooksService spec).
**Severity:** nit (deferred; only bites if a contributor uses the `.test.ts` suffix).

### D13 — `lintFilePatterns` excludes root-level TS files

**Surfaced by:** Edge-case hunter
**Files:** `spa/angular.json`
**Issue:** `angular.json`'s lint builder uses `lintFilePatterns: ["src/**/*.ts", "src/**/*.html"]`. Any TS at the SPA workspace root (a future `vitest.config.ts`, `playwright.config.ts`, etc.) is silently outside lint scope, so the project's `no-console`/`no-empty` rules do not apply there. Broaden the pattern when a root-level TS file is reintroduced — likely Story 1.11 (Playwright project setup) for the SPA-side or Story 2.x for a custom Vitest config.
**Belongs to:** Story 1.11 (Playwright project setup) — first plausible reintroducer of a root-level config TS file in the SPA workspace; or any story that adds a root TS config.
**Severity:** nit (deferred; only bites when a root TS file is added).

## Deferred from: code review of 1-9-spa-authservice-interceptors-functional-guards (2026-05-14)

- **`router.url` captured at error-time can be stale during in-flight navigation** — `with-credentials-interceptor.ts:20` reads `router.url` inside `catchError`; if a navigation is mid-flight when a parallel 401 fires, the captured URL points at the page the user is leaving, not the one they were trying to reach. AC7 explicitly mandates the current implementation, so this would require a re-spec (use `router.getCurrentNavigation()?.finalUrl` or capture the URL at request time).
- **`pathOf` exemption is exact-match `/api/me`** — `with-credentials-interceptor.ts:18`. Future sibling endpoints like `/api/me/preferences` would trip the global 401 redirect even though they are semantically session-check traffic. Revisit if/when a `/api/me/*` sub-endpoint is introduced.
- **`AuthService.loadMe()` has no in-flight de-duplication** — `auth-service.ts:13-24`. Two concurrent callers issue two parallel `GET /api/me` requests; last-writer-wins on the `_me` signal. Not currently exercised but a UX-hardening opportunity once `TopChrome` (Story 1.10) calls `loadMe()` alongside the guards.
- **`authGuard` does not clear `me()` on non-401 errors** — `auth-guard.ts:22`. A stale `me` survives a transient 500/network failure even though the user has been redirected to `/login`. Components reading `me()` (e.g., `TopChrome`) would show the previous identity until the next successful `loadMe`.
- **`router.url` is `'/'` during very-early bootstrap** — `with-credentials-interceptor.ts:20`. No `APP_INITIALIZER` exists in Story 1.9, but if a future story adds one that fires HTTP before Router initialization, a 401 there would produce `return_to=%2F` instead of the user's actual landing URL.
- **Multiple concurrent 401s trigger N redundant `router.navigateByUrl('/login')` calls** — `with-credentials-interceptor.ts:21`. Angular cancels earlier navigations so the user lands on `/login` correctly, but `authService.clear()` is called N times. Could be hardened with a `if (router.url.startsWith('/login')) return;` short-circuit.
- **AC3 "non-401: set null AND rethrow" contract not test-locked** — `auth-service.spec.ts`. Implementation at `auth-service.ts:18-22` is correct, but no spec exercises a 5xx error. AC9 enumeration was met (init/200/401/clear); locking AC3's rethrow contract would require a 5th `loadMe` test.
- **AC6 non-401 fallback to `parseUrl('/login')` (no `return_to`) not test-locked** — `auth-guard.spec.ts`. Implementation at `auth-guard.ts:22` is correct; AC9 enumeration only required 200 and 401 tests.
- **`withCredentialsInterceptor` non-HttpErrorResponse branch not test-locked** — `with-credentials-interceptor.spec.ts`. The 5xx test covers `HttpErrorResponse with status !== 401`; a thrown non-HttpErrorResponse (e.g., a downstream interceptor `Error`) takes the same `throwError` path but is not asserted.
- **Minor `csrfInterceptor` test gaps** — `csrf-interceptor.spec.ts`. Case-insensitive method matching (AC5 contract), `pathOf` with query-string `/api/me?ts=1`, multi-cookie ordering when `csrf_token` is not first, `=` in cookie value (base64 padding), and absent-vs-empty cookie distinction (the current "missing cookie" test sets `csrf_token=` empty rather than truly deleting). All hygiene; implementation is correct.
