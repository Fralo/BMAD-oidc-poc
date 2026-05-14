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

## Deferred from: code review of 1-8-spa-scaffold-tailwind-v4-design-tokens (2026-05-14)

### D6 — Dev proxy glob `/auth/*`, `/api/*`, `/v1/*` may not match bare segment or deeply nested paths

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `spa/proxy.conf.json`
**Issue:** AC3 mandates exactly these three glob patterns. Under modern http-proxy-middleware (webpack-dev-server v5 lineage), `/auth/*` matches `/auth/<one-segment>` but not the bare `/auth` (no trailing slash) and not deep paths like `/auth/realms/master/.well-known/openid-configuration`. Story 1.8 verifies the proxy by configuration only, not by live BFF roundtrip, so this is invisible at this story. When Story 1.5 (BFF OIDC plugin) or Story 1.9 (SPA AuthService) exercises the proxy end-to-end and discovers a route silently falling through to `index.html`, broaden the patterns (likely `/auth/**` or `**/auth/**`) — or replace with explicit path arrays.
**Belongs to:** Story 1.5 (BFF cookie/OIDC plugin — first to exercise `/auth/*` for real) or Story 1.9 (SPA AuthService — first to issue cross-proxy XHR from the SPA).
**Severity:** important (deferred; will cause silent SPA-fallback misroutes during integration).

### D7 — Smoke-fragment test asserts class names only, not computed styles

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `spa/src/app/app.spec.ts`
**Issue:** The test asserts `smoke.classList.contains('bg-surface-muted')` etc. — a string presence check against the literal class attribute. It does NOT verify that Tailwind v4 actually compiled `--color-surface-muted` into a working utility. If a future PR mistypes the `@theme` token (e.g., `--color-surface-mute`), the utility silently fails to materialize (resolves to an unset CSS var) while `app.spec.ts` continues to pass because the class literal in `app.html` still matches the assertion. Mitigate later with a computed-style assertion in a real component's spec — Story 1.10 (`TopChrome`) is the first real candidate.
**Belongs to:** Story 1.10 (first real component spec) or whichever story formalizes a "design-token utility" test helper.
**Severity:** nit (deferred; the smoke fragment is throwaway and will be replaced in Story 1.10 anyway).

### D8 — `*.test.ts` files would be discovered by Vitest at runtime but excluded from `tsconfig.spec.json`

**Surfaced by:** Edge-case hunter
**Files:** `spa/tsconfig.spec.json`
**Issue:** Vitest's default discovery glob accepts both `*.spec.ts` and `*.test.ts`. The TS spec project's `include: ["src/**/*.d.ts", "src/**/*.spec.ts"]` covers only the former. A developer who follows Vitest convention and writes `foo.test.ts` will see it run at runtime with no type-checking and no `vitest/globals` types in scope. The diff does not standardize on one suffix. Settle the convention in a downstream story — either widen the include to `**/*.{spec,test}.ts` or document that `.spec.ts` is the project's required suffix.
**Belongs to:** Whichever story first introduces a non-default test file (likely Story 1.9 AuthService spec, or Story 2.4 BooksService spec).
**Severity:** nit (deferred; only bites if a contributor uses the `.test.ts` suffix).

### D9 — `lintFilePatterns` excludes root-level TS files

**Surfaced by:** Edge-case hunter
**Files:** `spa/angular.json`
**Issue:** `angular.json`'s lint builder uses `lintFilePatterns: ["src/**/*.ts", "src/**/*.html"]`. Any TS at the SPA workspace root (a future `vitest.config.ts`, `playwright.config.ts`, etc.) is silently outside lint scope, so the project's `no-console`/`no-empty` rules do not apply there. Broaden the pattern when a root-level TS file is reintroduced — likely Story 1.11 (Playwright project setup) for the SPA-side or Story 2.x for a custom Vitest config.
**Belongs to:** Story 1.11 (Playwright project setup) — first plausible reintroducer of a root-level config TS file in the SPA workspace; or any story that adds a root TS config.
**Severity:** nit (deferred; only bites when a root TS file is added).
