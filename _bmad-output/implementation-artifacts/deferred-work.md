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
**Resolution (2026-05-15, Story 1.5):** Closed. Added `OIDC_AUTHORIZE_URL_BROWSER` env var (required-fail-fast) for the browser-facing 302 from `/auth/login`; `OIDC_ISSUER_URL` remains the back-channel value. Issue 2 (audience mapper) was already closed by Story 1.2's realm-as-code (`aud-resource-server` mapper).

## Deferred from: code review of 1-1-repo-scaffold-compose-skeleton (second pass, 2026-05-14)

### D3 — `change-me` placeholder credentials are silently accepted at runtime

**Surfaced by:** Blind hunter, edge-case hunter (second pass)
**Files:** `.env.example` (`KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`, `TEST_RESET_TOKEN`)
**Issue:** AC #5 explicitly endorses `change-me` placeholders in `.env.example`, so this is not a Story 1.1 defect. The runtime risk is that a developer who literally copies `.env.example` → `.env` and runs `docker compose up` will boot Keycloak and the BFF with `change-me` as a real admin password / client secret / test-reset token. No downstream "you forgot to override this" guard exists. The "never enable in prod" comment for `ENABLE_TEST_RESET` is documentation, not enforcement.
**Belongs to:** Story 1.2 (Keycloak realm-as-code) — refuse boot if `KEYCLOAK_ADMIN_PASSWORD == change-me` outside the `dev` profile. Story 1.4 (BFF auth-state schema) or Story 1.5 (BFF cookie/OIDC plugin) — refuse boot if `BFF_CLIENT_SECRET == change-me` outside `dev`. Story 1.12 (BFF `/v1/test/reset`) — refuse boot if `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN == change-me`.
**Severity:** important (deferred; would not affect Story 1.1's AC but will cause silent misconfiguration once services exist).
**Partial resolution (2026-05-15, Story 1.12):** Closed for `TEST_RESET_TOKEN` — the `e2e` profile override (`compose/app.e2e.yml`) wires `TEST_RESET_TOKEN: "${TEST_RESET_TOKEN:?TEST_RESET_TOKEN is required when the e2e profile is up}"` so `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up` fails fast with a clear error message when `TEST_RESET_TOKEN` is unset in both shell env and the repo-root `.env`. Defense-in-depth at the app layer: `bff.api.test_reset.register_test_reset_router` treats an empty/whitespace-only token as gate-off and emits `test_reset_route_skipped reason=test_reset_token_empty` at WARN. Note: the `:?` form does NOT reject the literal value `change-me` — only unset/empty. That is acceptable because (a) the route is only mounted with `ENABLE_TEST_RESET=true` (off by default), (b) the e2e profile is operator-opt-in and the README will document the secret-rotation step. The `KEYCLOAK_ADMIN_PASSWORD` and `BFF_CLIENT_SECRET` halves of D3 remain deferred to their respective stories.

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
**Resolution (2026-05-15, Story 1.5):** Closed via the two-URL config (D2 resolution). `verify_id_token` uses `OIDC_AUTHORIZE_URL_BROWSER` as the expected `iss` claim — matching what Keycloak signs under `KC_HOSTNAME=localhost`. Documented as a load-bearing caveat in the auth router (`src/bff/api/auth.py`) and the story file Dev Notes.

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

## Deferred from: code review of 1-3-bff-scaffold-from-archetype-baseline-health-lint-test-gates (2026-05-15)

> Note: items below were authored as D5–D21 on branch `story-1-3` before stories 1.2/1.8 added D5–D13. Renumbered to D14–D30 on merge to preserve unique identifiers across the file.

### D14 — Log redaction regex false-positives mangle legitimate prose

**Surfaced by:** Edge Case Hunter
**Files:** `services/bff/src/bff/observability/logging.py:18-26`
**Issue:** `_AUTH_HEADER_RE` and `_SECRET_KEY_RE` redact any non-whitespace token following the words "bearer", "authorization", "password", "token", "secret", "api_key", "credential" — including when those words appear in legitimate prose. Verified: `"reset token expired at 12:00"` becomes `"reset token *** at 12:00"`; `"user is bearer of message foo"` becomes `"user is bearer *** foo"`.
**Belongs to:** Archetype upstream or a dedicated observability pass.

### D15 — CORS middleware install and `configure_logging` are both frozen at module import / lifespan-start

**Surfaced by:** Blind Hunter + Edge Case Hunter
**Files:** `services/bff/src/bff/main.py:21-45`
**Issue:** `if settings.cors_enabled: app.add_middleware(...)` runs once at module import; the existing `tests/api/test_cors.py` works around this with `importlib.reload`. Separately, `configure_logging(settings)` only runs after lifespan starts, so uvicorn startup logs and any exception during `FastAPI(...)` instantiation use unstructured stdout.
**Belongs to:** Later observability/configuration refactor.

### D16 — 404 / 405 responses don't follow the documented error envelope

**Surfaced by:** Edge Case Hunter
**Files:** `services/bff/src/bff/main.py:47-51`
**Issue:** Architecture §C5 envelope is `{errorCode, message, detail}`. Starlette's default for unknown routes / wrong methods is `{"detail": "Not Found"}` / `{"detail": "Method Not Allowed"}`. No global Starlette HTTPException handler is registered.
**Belongs to:** Story 1.10 (SPA AppError extensions) or sooner if the SPA's authGuard catch-all path needs the envelope earlier.

### D17 — Test stubs are welded onto the live `bff.main:app` singleton at conftest import

**Surfaced by:** Blind Hunter
**Files:** `services/bff/tests/conftest.py:25-37`
**Issue:** `tests/conftest.py` does `app.include_router(_test_router)` at module import. If anything imports `tests.conftest` outside pytest, these stub routes get welded onto the shared app. Pytest-only invariant today; refactor to a separate test app or per-test mount in a later pass.

### D18 — `.githooks/pre-commit` is unwired dead weight

**Surfaced by:** Blind Hunter + Edge Case Hunter
**Files:** `services/bff/.githooks/pre-commit`
**Issue:** Requires `git config core.hooksPath .githooks` to activate (not done anywhere in the diff). Runs `npx --yes node-autochglog` (network) and `git add RELEASE_NOTES.md`. Either delete the hook or wire it up explicitly in a tooling pass.

### D19 — `alembic/env.py` imports private `_to_async_url`

**Surfaced by:** Blind Hunter
**Files:** `services/bff/alembic/env.py:23`
**Issue:** `from bff.core.database import _to_async_url` reaches into a `_`-prefixed helper. Promote `_to_async_url` to public API or duplicate the URL-rewriting logic in `env.py`.

### D20 — `AppSettings.profile` Literal collides with compose `profiles:` vocabulary

**Surfaced by:** Blind Hunter
**Files:** `services/bff/src/bff/core/config.py:32`, `compose/app.yml:44`
**Issue:** BFF settings declare `profile: Literal["default", "mock"]` (archetype's backend-mock-vs-real concept); compose declares `profiles: [default, dev, e2e]` (service activation). Two unrelated concepts sharing the name will confuse future contributors. Rename one (e.g. `AppSettings.backend_mode`).

### D21 — `_format_arg` AOP truncates any repr starting with `<`

**Surfaced by:** Blind Hunter
**Files:** `services/bff/src/bff/aop/logging_decorator.py:74-76`
**Issue:** `if len(r) > 80 or r.startswith("<")` collapses any repr beginning with `<` to `<TypeName>`. That includes legitimate values like XML/HTML payloads. Tighten the heuristic in an archetype-upstream pass.

### D22 — No `.gitattributes` enforcing LF for `*.sh`

**Surfaced by:** Blind Hunter
**Files:** `services/bff/` (entrypoint.sh)
**Issue:** Windows hosts running buildkit can produce CRLF endpoints. `#!/bin/sh\r` is a classic broken-shebang failure. Add `.gitattributes` with `*.sh text eol=lf`.

### D23 — Engine fixture drop_all / create_all between tests with session-scoped engine

**Surfaced by:** Blind Hunter
**Files:** `services/bff/tests/conftest.py:63-86`
**Issue:** `session` fixture's teardown runs `drop_all` then `create_all` on every test. SQLModel.metadata is empty in Story 1.3, so no-op today; Story 1.4 lands the first tables and every test will pay full schema rebuild. Entangles fixture scope (session) with schema lifecycle (per-test).
**Belongs to:** Story 1.4 (session table migration) or sooner.

### D24 — BFF README documents capabilities the code does not have

**Surfaced by:** Blind Hunter + Edge Case Hunter
**Files:** `services/bff/README.md`
**Issue:** Lists `/metrics`, OTEL OTLP export, bearer-token RBAC, `DB_DRIVER=mysql+pymysql` — all removed during cleanup or never wired. Archetype-shipped doc drift.
**Belongs to:** Story 5.3 (README polish + AI integration log).

### D25 — `/health` is an unauthenticated DoS surface

**Surfaced by:** Edge Case Hunter
**Files:** `services/bff/src/bff/api/health.py:116-135`
**Issue:** Per-request engine setup + alembic config parse + outbound httpx to OIDC + no rate limit. Compose's 30s × 5s × 30 retries window allows ~5 outbound discovery requests / sec from a single source.
**Belongs to:** Story 5.2 (security review).

### D26 — `alembic upgrade head` in `entrypoint.sh` is not SIGTERM-safe

**Surfaced by:** Edge Case Hunter
**Files:** `services/bff/entrypoint.sh:15-19`
**Issue:** `set -e; alembic upgrade head; exec uvicorn ...`. No `trap` forwarding SIGTERM to the alembic child. Benign in Story 1.3 (zero migrations); multi-step migrations in 1.4+ could land partial schema if `docker stop` arrives mid-upgrade.
**Belongs to:** Story 1.4 (first migration).

### D27 — `Justfile` in-tree but `.dockerignore` excludes it

**Surfaced by:** Acceptance Auditor (out-of-AC observation)
**Files:** `services/bff/Justfile`, `services/bff/.dockerignore`
**Issue:** Cleanup left Justfile present but the .dockerignore excludes it from build context. Either decide it's a dev-host helper (current state: explicit) or remove it.

### D28 — `auth/`, `db/`, `services/` subpackages absent

**Surfaced by:** Acceptance Auditor
**Files:** `services/bff/src/bff/`
**Issue:** Cleanup removed these as empty placeholders. AC2 enumerates them as part of the archetype layout. Tracks the post-decision option of leaving them absent permanently.
**Belongs to:** Tied to AC2 decision-needed (whether to update the spec or restore the directories).

### D29 — `CORSMiddleware` typed with `# ty: ignore`

**Surfaced by:** Blind Hunter
**Files:** `services/bff/src/bff/main.py:39`
**Issue:** Inline ignore explains starlette's `add_middleware` signature isn't typed per-middleware. Refactor when a typed wrapper exists upstream.

### D30 — Test stubs / stale `.dockerignore` entries / vestigial `.gitignore` rule

**Surfaced by:** Acceptance Auditor (out-of-AC observations)
**Files:** `services/bff/.dockerignore`, `services/bff/.gitignore`
**Issue:** Cleanup left stale archetype references that are tracked separately as Patch items P8–P10 in the story file. Listed here for cross-reference.

## Deferred from: code review of 1-4-bff-session-and-auth-state-schema-alembic-migration (2026-05-15)

### D31 — Migration `sa.DateTime()` is timezone-naive while model uses tz-aware `datetime.now(UTC)`

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `services/bff/alembic/versions/0001_init_init_sessions_and_auth_states.py`, `services/bff/src/bff/models/entities/{session,auth_state}.py`
**Issue:** The autogenerated migration emits `sa.DateTime()` (no `timezone=True`) for `expires_at` / `created_at` / `updated_at`. The model populates with `datetime.now(UTC)` (tz-aware). SQLite silently drops tzinfo on storage; the tests work around this via `_as_utc()` helpers. Project is SQLite-committed today, so this is functionally invisible — but a future port to Postgres would surface comparison errors (`can't compare offset-naive and offset-aware datetimes`).
**Belongs to:** Epic 5 (if a Postgres path is ever opened) or a follow-up alembic revision that switches to `sa.DateTime(timezone=True)` once the project commits to a backend that honors it.
**Severity:** minor (no immediate impact under SQLite-only commitment).

### D32 — `onupdate` lambda is skipped by bulk `update(Session).values(...)` queries

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `services/bff/src/bff/models/entities/session.py` (`updated_at` column)
**Issue:** `sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)}` only fires on ORM-emitted UPDATE statements that include the row's loaded attributes. SQLAlchemy `Query.update(...)` / `update(Session).values(...)` bulk paths skip it. SQLite cannot back this with `server_onupdate`, so the only mitigation is convention (Story 1.5 must explicitly set `updated_at` when issuing bulk token rotations).
**Belongs to:** Story 1.5 (OIDC plugin / token-rotation path).
**Severity:** minor (downstream contract; document in 1.5's session-service layer when authored).

### D33 — `AuthState.return_to` has no length cap or path validation

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `services/bff/src/bff/models/entities/auth_state.py`
**Issue:** `return_to: str | None = Field(default=None, nullable=True)` accepts arbitrary unbounded strings. The OIDC plugin (Story 1.5) writes the SPA-supplied post-login redirect path into this column — a classic open-redirect vector if not validated upstream. Model layer makes no claim either way.
**Belongs to:** Story 1.5 (OIDC plugin — owns `/auth/login` query-param validation) and Story 1.6 (CSRF middleware — orthogonal but related). A model-level `Field(max_length=2048)` could also land defensively.
**Severity:** important (security boundary, but not in 1.4's scope per "What this story is — and is not").
**Resolution (2026-05-15, Story 1.5):** Closed. `safe_return_to(raw)` in `bff/services/session_service.py` validates: must start with `/`, must NOT start with `//`, must NOT contain `:` before the first slash boundary, max length 1024. Falls back silently to `/` on any failure (no signal to attackers). 13 parametrized test cases cover the rule.

### D34 — Token / verifier columns are unbounded `AutoString` (`max_length` only on `sub`)

**Surfaced by:** Blind hunter, edge-case hunter
**Files:** `services/bff/src/bff/models/entities/{session,auth_state}.py`, `0001_init_*.py`
**Issue:** Only `sessions.sub` has `max_length=255`. `access_token`, `refresh_token`, `id_token`, `csrf_secret`, `code_verifier`, `state`, `nonce`, `return_to`, and both `id` columns emit unbounded `AutoString` (VARCHAR without size). On SQLite this is irrelevant. On MySQL/MariaDB this would either be rejected at DDL or default to `VARCHAR(255)` and silently truncate JWT-sized tokens. Tracked alongside D31 — both are SQLite-portability concerns.
**Belongs to:** Same as D31 (Postgres/MySQL portability story, if ever opened).
**Severity:** minor.

### D35 — `id` columns accept empty string

**Surfaced by:** Edge-case hunter
**Files:** `services/bff/src/bff/models/entities/{session,auth_state}.py`
**Issue:** No `min_length=1` on PK `id` columns. Story 1.5 generates ids via `secrets.token_urlsafe(32)` (43 chars), so an empty `id` cannot reach the DB in production. Defense-in-depth model constraint could land with 1.5 if desired.
**Belongs to:** Story 1.5.
**Severity:** nit.

### D36 — No autoloader for `bff.models.entities` submodules — new entities silently miss autogenerate

**Surfaced by:** Edge-case hunter
**Files:** `services/bff/src/bff/models/entities/__init__.py`
**Issue:** Future entity files must be added to `__init__.py`'s explicit re-exports or `SQLModel.metadata` won't see them at autogenerate time. Already documented in the module docstring (Story 1.4's deliverable), but a `pkgutil.iter_modules` autoloader or a CI lint check could catch the omission earlier. Each new entity-bearing story (2.1 onwards) must remember.
**Belongs to:** Epic 5 polish (Story 5.1 / 5.3) — a docs reminder + optional autoloader.
**Severity:** nit.

### D37 — No PK-uniqueness regression test on the new entities

**Surfaced by:** Edge-case hunter
**Files:** `services/bff/tests/models/entities/test_{session,auth_state}.py`
**Issue:** Inserting two rows with the same `id` is not exercised. AC8 didn't require it. A future migration that loses the PK constraint would slip past these tests.
**Belongs to:** Test debt — can land in any future story that touches these entities.
**Severity:** nit.

### D38 — `expires_at == now` boundary not exercised in expiry-filter tests

**Surfaced by:** Edge-case hunter
**Files:** `services/bff/tests/models/entities/test_{session,auth_state}.py`
**Issue:** Tests use `expires_at` clearly in the past (`now - 1 hour`) or clearly in the future (`now + 1 hour`). The exact-equality boundary (`expires_at == now`) is not tested. The semantic is the consumer's call (Stories 1.5 / 1.7 own the actual expiry-sweep queries), but documenting it as a test would prevent off-by-one regressions.
**Belongs to:** Stories 1.5 / 1.7 (whichever first writes the expiry-sweep query).
**Severity:** nit.

### D39 — Concurrent insert race for duplicate `id` not exercised

**Surfaced by:** Edge-case hunter
**Files:** `services/bff/src/bff/models/entities/{session,auth_state}.py`
**Issue:** Two concurrent `/auth/login` requests that happen to generate the same `secrets.token_urlsafe(32)` value collide at INSERT. 256-bit entropy makes this astronomically unlikely; consumer (Story 1.5) owns the catch-and-retry semantic if it ever matters.
**Belongs to:** Story 1.5.
**Severity:** nit.

### D40 — No DB-level `unique=True` on `AuthState.state` / `AuthState.nonce`

**Surfaced by:** Blind hunter (resolved from a decision-needed during 1.4 code review)
**Files:** `services/bff/src/bff/models/entities/auth_state.py`, `services/bff/alembic/versions/0001_init_*.py`
**Issue:** OAuth `state` and OIDC `nonce` are defense-in-depth single-use values, but the columns carry no DB-level unique constraint. Spec did not mandate uniqueness; the row is short-lived (deleted on `/auth/callback`).
**Decision (2026-05-15 code review):** Defer. 256-bit entropy from `secrets.token_urlsafe(32)` makes collisions astronomically unlikely; consumer (Story 1.5) owns the catch-and-retry semantic if it ever surfaces.
**Belongs to:** Story 1.5 (OIDC plugin) — generator contract + consumer retry path.
**Severity:** nit (entropy-bounded; no real-world collision risk under the planned generator).
**Resolution (2026-05-15, Story 1.5):** Closed. `SessionService.create_auth_state` / `create_session` retry up to 3 times on `IntegrityError` (PK collision) before raising `RuntimeError`. Generator is `secrets.token_urlsafe(32)` (256 bits). Tests force collisions via `monkeypatch` to exercise both retry-then-succeed and retry-exhaust paths.

## Deferred from: code review of 1-5-bff-cookie-session-oidc-plugin-pkce-synthetic-idp-test-harness (2026-05-15)

### D41 — `consume_auth_state` non-atomic SELECT+DELETE — duplicate concurrent callbacks could both succeed

**Surfaced by:** Edge-case hunter
**Files:** `services/bff/src/bff/services/session_service.py`
**Issue:** Two concurrent `/auth/callback` requests for the same `state` can both SELECT the row before either DELETE commits. Both proceed past `consume_auth_state` with the same Python row object. Keycloak's single-use code semantics prevents a duplicate session, but the auth_state "atomic consume" invariant is violated. A SELECT FOR UPDATE or an UPDATE-based CAS pattern would close this race.
**Belongs to:** Future story (Epic 2+ or Story 5.x) if the DB is ever switched to PostgreSQL, which supports `SELECT … FOR UPDATE`.
**Severity:** low (SQLite's deferred locking + Keycloak's code single-use provides practical protection at demo scale).

### D42 — `code_verifier` stored plaintext in `auth_states` table

**Surfaced by:** Blind hunter
**Files:** `services/bff/src/bff/services/session_service.py`, `services/bff/src/bff/models/entities/auth_state.py`
**Issue:** The PKCE `code_verifier` is the high-value secret of the login flow. Storing it plaintext means any process with DB read access can impersonate the BFF at Keycloak's `/token` endpoint if they also intercept the authorization code. Acceptable accepted risk for SQLite dev context; becomes a real concern if the DB backend is shared.
**Belongs to:** Story 5.2 (security review document).
**Severity:** low (accepted risk per architecture §Operational Details lines 1362–1368; same accepted-risk envelope as token-column plaintext storage).

### D43 — Zero leeway in PyJWT `exp` validation — clock skew causes false auth failures

**Surfaced by:** Edge-case hunter
**Files:** `services/bff/src/bff/auth/keycloak_cookie_session.py`
**Issue:** `jwt.decode(…)` with no `leeway` parameter uses 0-second leeway. A BFF clock skewed by even 1–2 seconds behind Keycloak's clock will reject valid id_tokens with `ExpiredSignatureError → OidcVerificationError → 400 auth_state_invalid`. Fix: add `leeway=timedelta(seconds=10)` to `jwt.decode`.
**Belongs to:** Story 5.x infra hardening, or can be patched in this story.
**Severity:** low (not an issue in dev with co-located processes; surfaces in production with NTP drift).

### D44 — Module-level `_session_service` singleton bypasses FastAPI DI lifecycle

**Surfaced by:** Blind hunter
**Files:** `services/bff/src/bff/api/auth.py`, `services/bff/src/bff/api/me.py`
**Issue:** `_session_service = SessionService()` at module scope bypasses FastAPI's dependency injection and makes it impossible to swap the service in tests without `monkeypatch`. Both files should inject via `Depends(SessionService)`. Currently harmless (stateless service) but will become an obstacle if `SessionService` ever acquires constructor dependencies.
**Belongs to:** Any future story that touches these files or refactors the service layer.
**Severity:** nit (no correctness impact; code quality / testability improvement).

## Deferred from: code review of 1-6-bff-csrf-middleware-csp-header (2026-05-15)

- **CSP attachment driven by request `Accept` header instead of response `Content-Type`** — `services/bff/src/bff/middleware/security_headers.py:38-40`. Two real defects flagged by Blind + Edge-Case hunters: (a) HTML responses to `Accept: */*` clients miss CSP; (b) non-HTML JSON responses to clients that send `Accept: text/html` get spurious CSP. AC8 of Story 1.6 explicitly mandates the request-`Accept`-driven design and the scenario tests depend on it. Revisit when the SPA introduces SSR responses or richer content-negotiation paths — at that point the response-Content-Type-driven approach becomes strictly better and the AC8 scenarios should be re-written.
- **`BaseHTTPMiddleware` buffers streams + drops `BackgroundTasks`** — `services/bff/src/bff/auth/csrf.py:31`, `services/bff/src/bff/middleware/security_headers.py:26`. Both new middlewares subclass `BaseHTTPMiddleware`, which Starlette docs flag as a footgun for streaming responses, `BackgroundTasks` propagation, and exception handling after `call_next`. AC1 explicitly mandates this base class; revisit when the BFF proxies resource-server streams or SSE.
- **CSP value lacks hardening directives** — `services/bff/src/bff/middleware/security_headers.py:17-21`. No `object-src 'none'`, `upgrade-insecure-requests`, `report-uri`/`report-to`, no nonce-or-hash for scripts, and `style-src 'unsafe-inline'` is permanent. The exact string is mandated by architecture A8 and a byte-for-byte test calcifies it. **Belongs to:** Story 5.2 (security review).
- **No other security headers attached** — `services/bff/src/bff/middleware/security_headers.py`. Missing `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Strict-Transport-Security`, `X-Frame-Options` (legacy fallback for `frame-ancestors`), `Permissions-Policy`, COOP/CORP/COEP. **Belongs to:** Story 5.2.
- **Test log-message substring matching is fragile** — `services/bff/tests/auth/test_csrf.py` multiple sites use `"csrf_header_missing" in r.message`. Re-formatting any log line breaks these assertions silently. Pre-existing pattern across the BFF test suite. **Belongs to:** future structured-logging adoption pass.
- **`monkeypatch.setattr(settings, ...)` mutates global Pydantic settings singleton** — `services/bff/tests/conftest.py:1843` and `tests/auth/test_csrf.py` multiple sites. Parallel test execution (pytest-xdist) would interleave; current suite runs serial. Pre-existing pattern. Safer alternative is `app.dependency_overrides` on a settings getter.
- **`# ty: ignore[invalid-argument-type]` proliferation on `add_middleware`** — `services/bff/src/bff/main.py:42, 55, 56`. Pre-existing pattern inherited from the CORS install. Cross-cutting `ty` plugin or typed middleware wrapper would remove the need for inline suppressions.
- **No startup validation of `settings.bff_base_url` / `settings.bff_csrf_cookie_name`** — `services/bff/src/bff/core/config.py`. Misconfigured empty / malformed values surface as request-time 500s rather than startup failures. Belongs in a centralized config-validation pass.
- **Referer fallback lacks fail-closed mode** — `services/bff/src/bff/auth/csrf.py:74-75`. The middleware accepts `Referer` as a fallback when `Origin` is missing. Spec design intent. Policy review when `Referrer-Policy: no-referrer` adoption broadens.
- **No runtime length-assert before `hmac.compare_digest`** — `services/bff/src/bff/auth/csrf.py:58-60`. Code comment accepts the length-leak as a planted-attacker signal. Defense-in-depth refactor — not a bug.
- **No IDN/punycode normalization on Origin/Referer hostnames** — `services/bff/src/bff/auth/csrf.py:107-115`. Single-deployment ASCII hostnames make this a non-issue today; defer until multi-tenant / IDN domains.

## Deferred from: code review of 1-7-bff-logout-endpoint-revoke-end-session-degrade-honestly (2026-05-15)

- **RFC 6749 §2.3.1 client-credential URL-encoding** — `services/bff/src/bff/auth/keycloak_cookie_session.py:264-269` (revoke) + Story 1.5 `exchange_code` (same pattern). httpx's `auth=(client_id, client_secret)` tuple base64s the raw bytes without RFC 6749 §2.3.1 form-urlencoding. A `client_secret` containing `:`, `+`, `%`, or any non-form-safe byte produces a malformed Basic auth header. Test secret `test-bff-secret` is ASCII-safe, so the issue is masked in CI. Fix needs a cross-cutting helper applied at every OIDC client-credential call site.
- **No DB-operation timeout on `SessionService.delete_session`** — `services/bff/src/bff/services/session_service.py:226-232`. A wedged Postgres connection (pool exhaustion, network partition) hangs the handler indefinitely. The user perceives a hung logout, contradicting UX §J5 ("forbids half-logged-out states"). Not exercised today because dev uses SQLite in-memory; real concern for prod cutover.
- **Hardcoded Keycloak topology in revoke / end_session URLs** — `services/bff/src/bff/api/auth.py:415-417`. `cfg.oidc_issuer_url.rstrip("/") + "/protocol/openid-connect/{revoke,logout}"` couples the BFF to Keycloak's URL shape. OIDC has `.well-known/openid-configuration` advertising both `revocation_endpoint` and `end_session_endpoint`. Refactor to discovery in a future story (also applies to `auth_callback`'s token endpoint construction at `auth.py:207`).
- **Manual 401 envelope duplication** — `services/bff/src/bff/api/auth.py:347-364` (`_session_expired_with_cookie_clear`) duplicates the envelope shape from `/api/me`. Risks drift if `ErrorCode.SESSION_EXPIRED` shape changes. Small refactor candidate.
- **INFO log retention policy for `auth_logout_start` / `auth_logout_complete`** — every logout emits an INFO line carrying `sub` first-8-chars + `session_id` first-8-chars. Per-user audit trail by design, but operational retention policy decision deferred to the security review (Story 5.2).
- **`end_session` does not pass `post_logout_redirect_uri`** — `services/bff/src/bff/auth/keycloak_cookie_session.py:286-296`. KC deployments with a `Valid Post Logout Redirect URIs` allowlist will return 400; the local session is still destroyed (degrade-honestly contract holds at the BFF), but the KC SSO session survives so the next `/auth/login` re-authenticates silently — UX §J5 contradiction. **Deferred — spec design intent: no new settings or realm changes.** Re-evaluate when the demo is pointed at a hardened KC.

## Surfaced during Story 1.11 implementation (2026-05-15)

### D45 — `/health` OIDC discovery probe enforces back-channel-URL `issuer` match, which Keycloak cannot satisfy under `KC_HOSTNAME=localhost`

**Surfaced by:** Story 1.11 dev agent (blocked AC8 — `docker compose --profile e2e up --abort-on-container-exit`)
**Files:** `services/bff/src/bff/api/health.py:99-138` (specifically the `declared_issuer != canonical_issuer` check at lines 132-137)
**Issue:** The `/health` endpoint's `_check_oidc_discovery` requires the discovery document's `issuer` field to equal `OIDC_ISSUER_URL` (the back-channel URL `http://keycloak:8080/realms/bmad-books`). But with `KC_HOSTNAME=localhost` + `KC_HOSTNAME_STRICT=false` set in `compose/infra.yml` (the browser-correct setting from D2/D8's resolution), Keycloak emits `iss=http://localhost:8080/realms/bmad-books` in its discovery doc. The probe rejects this as a mismatch, `/health` returns 503, the compose health check fails, and any `docker compose up --abort-on-container-exit` invocation that depends on a healthy BFF exits non-zero.
**Why D8's resolution doesn't cover this:** Story 1.5 introduced the two-URL split (`OIDC_ISSUER_URL` for back-channel token validation, `OIDC_AUTHORIZE_URL_BROWSER` for browser redirects) and reconciled the issuer mismatch *inside `verify_id_token`* (which uses the browser-facing URL as the expected `iss`). The `/health` probe, written in Story 1.3 before the split existed, was not updated to participate in this reconciliation — it still uses `OIDC_ISSUER_URL` for both the discovery URL it fetches and the issuer string it compares.
**Belongs to:** A bugfix in Story 1.3's `/health` ownership, or a small story in Epic 5 (Story 5.4 final smoke). Concrete fix options:
  (a) Compare against `cfg.oidc_authorize_url_browser` rstripped of `/protocol/openid-connect/auth` (matches what `verify_id_token` does today);
  (b) Drop the issuer-string check entirely from the health probe — a 2xx JSON response with a non-empty `issuer` field is sufficient to prove Keycloak is up and serving the realm;
  (c) Fetch discovery via the browser URL `oidc_authorize_url_browser` and compare against that.
Option (b) is the most defensible: the health probe's job is liveness, not configuration correctness — configuration-correctness checks belong at boot.
**Severity:** important (deferred — blocks E2E orchestration in 1.11/1.13 and any compose-driven smoke. Will block Story 5.4 final smoke if not handled first).
**Blocks:** Story 1.11 AC8 (compose `--profile e2e up --abort-on-container-exit` exits 0), Story 1.13 (E2E J1+J5 require a healthy BFF), Story 5.4 final smoke.

**Resolution (2026-05-15, D45 fix):** Option (b) implemented. `services/bff/src/bff/api/health.py:_check_oidc_discovery` no longer compares the discovery doc's `issuer` field byte-for-byte against `OIDC_ISSUER_URL`. New contract: 2xx response, JSON-parseable, body is a JSON object, body has an `issuer` field that is a non-empty string. This still rejects a generic reverse-proxy 200 (no `issuer` key) without coupling /health to Keycloak's `KC_HOSTNAME` setting. Tests updated in `services/bff/tests/api/test_health.py` — the old "issuer mismatch returns False" test was repurposed to assert the mismatch case now returns `True` (the bug fix), plus four new edge-case tests (missing `issuer`, empty string, null, JSON array body). End-to-end smoke verified: `docker compose --profile dev up -d keycloak bff` + `curl http://localhost:8000/health` returns `200 {"status":"ok"}` under `KC_HOSTNAME=localhost` (Keycloak emitted `iss=http://localhost:8080/realms/bmad-books` while BFF had `OIDC_ISSUER_URL=http://keycloak:8080/realms/bmad-books`). Commit on branch `fix/d45-health-oidc-issuer-probe`. Closes D45.

## Surfaced during Story 1.13 implementation (2026-05-15)

### D46 — SPA is not served by any compose service — blocks live J1/J5 E2E run

**Surfaced by:** Story 1.13 dev agent (`docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit` produced 5 spec failures, all at `getByRole('button', { name: 'Log in' })` because `http://bff:8000/login` is not a route the BFF serves)
**Files:** `services/bff/Dockerfile` (no node-build stage, no SPA bundle copied), `services/bff/src/bff/main.py` (no `StaticFiles` mount, no HTML5 history-fallback catch-all), `compose/app.yml` (no `spa` static-server service)
**Issue:** Architecture **AR24 (`_bmad-output/planning-artifacts/architecture.md:84`)** mandates the SPA serving model:
> Same-origin via BFF. In prod, BFF's multi-stage Dockerfile compiles SPA in a Node stage and copies `dist/spa/browser` into the BFF image; BFF mounts it at `/` with HTML5 history fallback (catch-all serves `index.html` only for `Accept: text/html`).

The `compose/app.yml` file header (line 4) says "Story 1.3 lands the BFF; the Resource Server arrives in Story 3.1 and the SPA (prod build) in Story 1.8." But Story 1.8 was scoped to scaffold-only (`spa scaffold tailwind v4 design tokens`) and did NOT integrate the SPA into the BFF Dockerfile or add an SPA service to compose. Stories 1.9 and 1.10 added SPA code (`AuthService`, `LoginView`, `TopChrome`, route table) but the prod-serving path remained un-implemented. The dev workflow has always relied on `ng serve` at `:4200` with a proxy to the BFF at `:8000`; the compose `default` / `e2e` profiles assumed an SPA service that doesn't exist.

**Story 1.13's specs are correct and complete** (`e2e/tests/j1-first-login.spec.ts`, `e2e/tests/j5-logout.spec.ts`); they fail end-to-end ONLY because Playwright navigates to `http://bff:8000/login` and the BFF returns 404 (no SPA bundle mounted).

**Concrete fix options:**
  (a) **AR24 canonical path:** Add a multi-stage section to `services/bff/Dockerfile` that builds the SPA in a Node stage and copies `spa/dist/spa/browser` into the BFF image; extend `bff.main` with a `StaticFiles` mount at `/` plus an HTML5 history-fallback handler. This is the architectural intent and the same-origin design that AR24 specifies.
  (b) **Sibling service:** Add an `spa` service to `compose/app.yml` that runs nginx (or another static server) serving the SPA bundle at `:8000` (or another port) with `/auth`, `/api`, `/v1` proxied to the BFF. Requires routing logic in nginx and either renames the BFF port or fronts both services behind a third hostname.
  (c) **e2e-only stub:** Inject the SPA bundle into the existing BFF image as part of the e2e compose overlay only. Pragmatic but contradicts AR24's same-origin "in prod" stance.

Option (a) is the architecturally clean answer and is the smallest deviation from AR24.

**Belongs to:** A new story in the current sprint, likely scoped between Story 1.10 (SPA chrome) and Story 1.13 (E2E specs). Suggested key: `1-14-bff-multi-stage-build-serves-spa-bundle`. Without this, Story 1.13's live AC6 (`just e2e-up` exits 0 with both specs passing) cannot be verified; Story 5.4 (final smoke) is also blocked.

**Severity:** important (deferred — blocks E2E orchestration in 1.13 and any compose-driven smoke; blocks Story 5.4). The static / unit gates (BFF pytest, ruff, ty, e2e tsc, playwright --list, compose config) all pass cleanly; only the dynamic compose-up run is affected.

**Blocks:** Story 1.13 AC6 (live e2e run via `just e2e-up` — both specs pass), Story 5.4 final smoke.

**Resolution (2026-05-16, Story 1.14):** Closed. Implemented Option (a) — the AR24 canonical path. `services/bff/Dockerfile` now has a `node:22-slim AS node-builder` stage that runs `npm ci --prefer-offline && npm run build` against `spa/` and copies `dist/spa/browser` into the final image at `/app/static`. `services/bff/src/bff/main.py` adds a `_register_spa(application, static_dir)` helper that mounts `/assets` (StaticFiles) and registers a `GET+HEAD /{full_path:path}` catch-all with file resolve → Accept-header gating (`text/html` clients get `index.html`; non-HTML clients hitting unknown paths get the `{errorCode,message,detail}` 404 envelope per D16). The mount is guarded by `_SPA_DIR.is_dir()` so dev runs (no built bundle) start cleanly. Build context switched to repo root (`compose/app.yml: context: .., dockerfile: services/bff/Dockerfile`) so the Node stage can see `spa/`. AC6 (manual `docker build` + `curl http://localhost:18000/login` → 200 text/html + `<app-root>` body) verified by the dev agent. Path-traversal defence added in CR: catch-all resolves the candidate path and rejects anything outside `static_root` (test in `services/bff/tests/api/test_static.py`). Story 1.13 AC6 live e2e run (AC8 in Story 1.14) remains as an operator-driven smoke — covered transitively by Story 5.4. Closes D46.

## Deferred from: code review of 1-13-e2e-spec-j1-first-time-login-j5-logout (2026-05-15)

- **`BFF_CLIENT_SECRET` shared between production confidential client and Playwright runner** — `compose/app.yml:87` plumbs the real `bmad-books-bff` client secret into the e2e runner container. Test artifacts (traces, screenshots, videos under `e2e/test-results/`) could capture the credential. PRD §4 out-of-scopes operator-self-harm. Clean fix: add a separate `bmad-books-bff-test` confidential client to the realm, used only under the `e2e` profile. **Belongs to:** Story 5.2 (security review).
- **`_safe_session_id_log` duplicated between `bff.api.auth` and `bff.api.test_reset`** — `services/bff/src/bff/api/test_reset.py:97-108` re-implements the helper inline rather than importing from `bff.api.auth`. Documented as intentional in the diff (keeps the dependency direction one-way: `api/test_reset.py` must not depend on `api/auth.py`). Cleaner: extract to a shared `bff.core.logging` helper module. **Belongs to:** future refactor pass.
- **`assert auth_header is not None` for type-narrowing — stripped under `python -O`** — `services/bff/src/bff/api/test_reset.py:325` (also Story 1.12's POST handler). Promote `_classify_auth_failure` to a discriminated return signature so the type-narrowing is statically provable. **Belongs to:** code-quality cleanup pass.
- **`_safe_session_id_log` does not sanitize newlines/control chars in `sub`** — `services/bff/src/bff/api/test_reset.py:106` mirrors `bff.api.auth._safe_session_id_log:78` limitation. A maliciously-shaped `sub` claim (RFC 7519 forbids; BFF doesn't validate) could log-split. **Belongs to:** Story 5.2 (security review log-sanitization audit).
- **`_session_not_found_response` envelope is shape-distinct from gate-off 404 — minor probe side-channel** — `services/bff/src/bff/api/test_reset.py:115-127`. The auth-failure 401 reuses `/api/me`'s envelope verbatim to minimize the existence-leak; the new `session_not_found` 404 emits a custom envelope. A probe must already pass bearer auth to distinguish, so the side-channel assumes deeper compromise. **Belongs to:** Story 5.2 (security review).
- **caplog substring assertions are brittle to log-format refactors** — `services/bff/tests/api/test_test_reset.py` multiple sites (e.g., `"test_session_debug_unauthorized: missing_header" in r.message`). Pre-existing project-wide pattern across the BFF test suite. **Belongs to:** future structured-logging adoption pass.

## Deferred from: code review of 1-10-spa-loginview-topchrome-route-table (2026-05-15)

- **D47 — Logout button has no double-click guard** — `spa/src/app/shared/chrome/top-chrome.ts:logout()`. A rapid double-click fires two concurrent `POST /auth/logout` requests. The second likely gets a BFF 401/404 (session already deleted) but the `catch` swallows it, so `authService.clear()` and `router.navigateByUrl('/login')` run twice. Angular de-dupes navigation; the user lands on `/login` correctly. No correctness impact at demo scale — the race is only observable under artificial double-click load. **Belongs to:** a future UI-hardening story (Epic 5). Fix: disable the button for the duration of the logout async or track an `isLoggingOut` signal. **Severity:** nit (deferred; no correctness impact).
- **D48 — `provideAppInitializer` re-throws on non-401 `/api/me` errors, crashing bootstrap** — `spa/src/app/app.config.ts`. `AuthService.loadMe()` (Story 1.9 contract) re-throws any non-401 error. `provideAppInitializer(() => inject(AuthService).loadMe())` propagates that rejection, which in Angular causes the app to fail to bootstrap entirely. A 500 or network error from `/api/me` on first load will show a blank page. No spec exercises this path. Pre-existing Story 1.9 behavior, not introduced by Story 1.10. **Belongs to:** a future resilience story. Fix: wrap in `catch` inside the initializer factory, or add a try/catch inside `loadMe` for all errors. **Severity:** low (deferred; only surfaces under `/api/me` 500/network-error during cold load).

## Deferred from: code review of 1-11-playwright-project-setup-fixtures-helpers (2026-05-15)

- **`e2e/package.json` `test` script carries `--pass-with-no-tests` flag** — AC1 mandates "no extra flags beyond what `playwright.config.ts` carries", but `--pass-with-no-tests` is a CLI-only flag (not settable in config). Deviation is intentional and documented in the Dev Agent Record: Playwright >=1.49 exits 1 on an empty `tests/` directory; the flag flips that to exit 0 for the Story 1.11 baseline. Once Story 1.13's spec files are present the flag is a no-op. **Belongs to:** Story 1.13 completion — confirm the flag is still needed after real specs land; remove if not. (`e2e/package.json:8`, `e2e/Dockerfile:26`)
- **`logInAs` `waitForURL(/\/books$/)` regex matches any URL ending in `/books`** — `e2e/fixtures/helpers.ts:19`. The pattern does not anchor to the path root, so a redirect to e.g. `/admin/books` or `/some/nested/books` would satisfy the wait. In this project's URL structure there is only one `/books` route, so the probability of a false match is negligible. If the route table grows, tighten to `/^.*\/books$/` or `'**/books'`. **Belongs to:** Story 3.x or whichever story introduces nested routes. (`e2e/fixtures/helpers.ts:19`)

## Deferred from: code review of 1-12-bff-post-v1-test-reset-endpoint (2026-05-15)

- **Non-idiomatic `except ValueError, TypeError:` style in `csrf.py`** — `services/bff/src/bff/auth/csrf.py:103`. Python 3 parses `except E1, E2:` as `except (E1, E2):` (a tuple), so both exceptions are caught correctly. However the Python 2-compatible form is non-idiomatic; the canonical Python 3 form is `except (ValueError, TypeError):`. Pre-existing from Story 1.6; ruff does not flag it under current rules. **Belongs to:** future code-style cleanup pass (Story 5.3 README/polish).
- **`_build_app` test helper mutates global `settings` without rollback guarantee** — `services/bff/tests/api/test_test_reset.py:75-76`. The helper sets `settings.enable_test_reset` and `settings.test_reset_token` directly before each `monkeypatch.setattr`. If the test body throws before `monkeypatch` has a chance to restore, the global singleton is left dirty for subsequent tests. In practice, `monkeypatch` restores before teardown, so this is only a risk under unusual pytest-plugin failures. Safer: gate the mutation entirely inside the `monkeypatch` block at call sites. **Belongs to:** test-quality cleanup pass.

## Deferred from: code review of 1-14-bff-multi-stage-build-serves-spa-bundle (2026-05-16)

- **D49 — `_register_spa` catch-all hardcodes the 404 JSON envelope instead of raising `AppException`** — `services/bff/src/bff/main.py:90-93`. The non-HTML 404 branch builds the `{errorCode,message,detail}` body inline; the rest of the BFF raises `AppException(ErrorCode.NOT_FOUND, ...)` and lets the registered `app_exception_handler` render the envelope. The shape matches by construction today, but drift risk is real — if `ErrorCode.NOT_FOUND` ever gains a new field, the catch-all silently keeps the old shape. **Belongs to:** Story 5.3 (README polish + AI integration log) or a follow-up cleanup pass.
- **D50 — `.angular/` Angular build cache not in `.dockerignore`** — `.dockerignore` (repo root). A contributor who has run `ng serve` or `ng build` locally has `spa/.angular/` populated. With the new repo-root build context (Story 1.14), that directory is sent to the Docker daemon at build time — wasted bandwidth and a confusing layer-cache invalidation. Add `**/.angular` to `.dockerignore`. **Severity:** nit (only affects local builds, not CI which builds from a clean checkout).
- **D51 — Catch-all uses `accept == ""` as the HTML-fallback signal, conflating "header absent" with "header present but empty"** — `services/bff/src/bff/main.py:85`. The current code reads `request.headers.get("accept", "")` and falls into the HTML branch for empty string. Some HTTP clients (e.g., `curl` with `-H "Accept:"`) explicitly emit `Accept:` (empty value) to signal "no preference" — which today serves them `index.html`. RFC 7231 says missing `Accept` means "any media type"; an explicit empty value is technically undefined. Tighten the heuristic if the wire-level distinction ever matters. **Belongs to:** content-negotiation hardening pass.
- **D52 — No test for `HEAD /login`** — `services/bff/tests/api/test_static.py`. The catch-all registers both `GET` and `HEAD`, but the test suite only exercises `GET`. A future regression that drops `HEAD` from the decorator would pass tests but break browsers that issue `HEAD` probes (e.g., link-preview crawlers, some CDNs). Add a `HEAD /login` test that asserts 200 + `Content-Type: text/html` + empty body. **Belongs to:** test-coverage cleanup pass.
- **D53 — `static_dir.resolve()` called once at `_register_spa` time but `static_dir` may be a symlink chain that changes between registration and request** — `services/bff/src/bff/main.py:63`. The path-traversal guard caches `static_root = static_dir.resolve()` at startup. In production this never matters (the image bakes `/app/static` and there are no symlinks). In tests with `tmp_path`, the value is stable. But if a future deployment uses a Kubernetes `configMap` or atomic-symlink-swap deploy pattern, the resolved path could drift. **Belongs to:** deferred until a non-Docker deployment model is on the table.

## Deferred from: code review of 3-1-rs-scaffold-from-archetype-baseline-health-rs-in-compose-default-dev (2026-05-16)

- **D54 — RS `/health` runs the three probes sequentially, not in parallel** — `services/resource-server/src/resource_server/api/health.py:160-164`. Worst-case latency is `DB + Alembic + JWKS_connect_timeout (5s) + JWKS_read_timeout (10s)` ≈ 15-17s when JWKS is genuinely unreachable. `asyncio.gather` over the three probes would cap latency at the slowest single probe. Story 3.1 spec explicitly endorses sequential ("for code symmetry / simpler debugging") and the BFF analog is also sequential, so this is intentional drift-free design — but the latency profile is worth revisiting when the platform sees real outage traffic against `/health`. **Belongs to:** Story 5.x performance pass, or a coordinated BFF+RS update. **Severity:** nit (probe-timing only; correctness unaffected).
- **D55 — OTEL + Prometheus runtime deps remain in `pyproject.toml` despite the observability stack being inert** — `services/resource-server/pyproject.toml:13-17`. `opentelemetry-api`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-sdk`, `prometheus-fastapi-instrumentator` are all installed at runtime but never imported by `main.py` (per the 2026-05-14 sprint-change cut). Image size + supply-chain surface area both grow for code that is never executed. Mirrors the same posture on the BFF (Story 1.3 + 1.14 left the same deps untouched). **Belongs to:** a coordinated archetype-upstream pass that excises the observability surface from `fastapi-archetype` master, then re-scaffolds both backend services. **Severity:** nit (image bloat, not a functional concern).
- **D56 — `tests/observability/test_otel.py::test_setup_otel_with_export_disabled_logs_and_sets_provider` tests dead code** — `services/resource-server/tests/observability/test_otel.py`. `otel.setup_otel(settings)` is never called from `main.py` (the wiring was excised per the 2026-05-14 sprint-change cut). The test still passes because `observability/otel.py` is on disk and importable, but it asserts on dead-code behavior. Two cleanup options: (a) drop the test entirely (already omitted from coverage), (b) flip it to a "guardrail" asserting that `main.py` does NOT import `setup_otel` so a future re-introduction is visible. **Belongs to:** test-quality cleanup pass, or the same coordinated archetype-upstream pass as D55. **Severity:** nit.
- **D57 — `_validate_external_auth_requirements` has dead `if/pass / else:` branch** — `services/resource-server/src/resource_server/core/config.py:142-144`. The archetype emits `if self.auth_type != "entra": pass else: ...` instead of the equivalent `if self.auth_type == "entra": ...`. Functionally identical, but flake8-simplify (SIM rule `SIM103` family) would normally flag this. Pre-existing archetype emission; the BFF inherits the same pattern. **Belongs to:** coordinated archetype-upstream pass. **Severity:** nit (code-style only).
- **D58 — `_check_jwks` does not allow `verify=False` for self-signed dev IdPs** — `services/resource-server/src/resource_server/api/health.py:135-138`. The `httpx.AsyncClient` is built with default TLS verification (`verify=True`). Story 3.1 only probes Keycloak over plain HTTP inside the compose network, so this is correct today. But Story 3.2's `oidc_bearer` will share the JWKS URL with the JWT-validation surface; when a developer points the RS at a self-signed local IdP (per AR33's synthetic-IdP territory), the /health probe will fail with a TLS-cert error while the actual JWT validation works fine via PyJWKClient's own client. **Belongs to:** Story 3.2 — likely surfaces as a CR-deferred item again. **Severity:** nit (development ergonomics only; production correctness unaffected — Keycloak is reached over HTTP in-cluster).

## Deferred from: code review of 3-2-rs-oidc-bearer-... (2026-05-16)

- **D59 — `make_oidc_bearer_auth(settings_arg)` ignores its `settings_arg` argument** — `services/resource-server/src/resource_server/auth/oidc_bearer.py:131-139`. Real factory-contract weakness: `get_auth(test_settings)` with per-call OIDC values silently falls back to the module-level `settings` singleton because the inner `authenticate_bearer_token` calls `_validate_access_token` which reads the global. Story 3.2's text explicitly documented this design choice ("test fixtures can monkeypatch them without rebuilding the AuthFunctions closure"). Fixing it properly requires threading `settings_arg` through `_validate_access_token` + the `get_authenticated_principal` request dep, which broadens the surface beyond what this story committed to. **Belongs to:** a follow-up that aligns both archetype seams (entra + oidc_bearer) on a single settings-injection pattern. **Severity:** medium (real but not user-facing; tests pass by accident, but the test harness's monkeypatch happens to align the globals).

- **D60 — `_jwks_clients` module cache never evicts on JWKS-URL reconfiguration** — `services/resource-server/src/resource_server/auth/oidc_bearer.py:49,52-57`. The dict is keyed by URL string and grows indefinitely. In production the `oidc_jwks_url` value is set once at boot via required-fail-fast config, so this never triggers; in tests `synthetic_idp.py:194` resets the cache per fixture. Real concern only in a hypothetical config-reload scenario; the BFF has the same pattern. **Belongs to:** a coordinated BFF+RS JWKS-cache pass. **Severity:** nit (production safety only theoretical).

- **D61 — `oidc_jwks_connect_timeout` / `oidc_jwks_read_timeout` settings unread by JWT-validation surface** — `services/resource-server/src/resource_server/core/config.py:99-100`. The two timeout fields land in Story 3.1's `AppSettings` and are read by `/health`'s JWKS probe but NOT by PyJWKClient's signing-key fetch (PyJWKClient uses `urllib.request.urlopen` with no timeout knob — see D62). They appear dead-config for the JWT-validation surface specifically. Pre-existing from Story 3.1; reviewing here because Story 3.2's mention of them re-surfaces the question. **Belongs to:** D62's resolution. **Severity:** nit (config hygiene).

- **D62 — PyJWKClient's signing-key HTTP fetch has no timeout** — `services/resource-server/src/resource_server/auth/oidc_bearer.py:54-55,69-77`. Architecture line 415 calls for 5s connect / 10s read on the RS→Keycloak JWKS fetch. PyJWKClient does not expose a timeout argument; its internal `urllib.request.urlopen` call has no default timeout. A hung Keycloak JWKS endpoint at first-request-after-cache-miss would block the event loop. Story 3.2 explicitly documented this trade-off in AC #8 (the `/health` JWKS probe from Story 3.1 is the operational guard). Real fix: subclass `PyJWKClient` or wrap `get_signing_key_from_jwt` in `asyncio.wait_for(..., timeout=settings.oidc_jwks_read_timeout)`. The BFF's `keycloak_cookie_session.py` has the same issue. **Belongs to:** a coordinated BFF+RS hardening pass. **Severity:** medium (real production risk under a Keycloak outage; `/health` mitigates).

- **D63 — 401 responses don't include `WWW-Authenticate: Bearer` per RFC 6750 §3** — `services/resource-server/src/resource_server/auth/oidc_bearer.py:106-111`. The error envelope from `AppException` does not add the `WWW-Authenticate` header. RFC 6750 §3 mandates this on 401 responses from OAuth-protected resources so that clients know which scheme to retry with. Real RFC-compliance gap; not user-visible because the BFF's `ResourceServerClient` (Story 3.5) won't inspect the header. **Belongs to:** Story 5.2 (security review document) — the security review will surface this as a documented accepted-or-fixed item. **Severity:** nit (RFC compliance only; no behavioral impact on the current consumer set).

- **D64 — No `leeway` / `nbf` / `iat`-future test coverage for clock-skew handling** — `services/resource-server/src/resource_server/auth/oidc_bearer.py:69-77`. `jwt.decode` is called without `leeway=...`. PyJWT validates `nbf` when present (raises `ImmatureSignatureError`, caught correctly) but the test suite doesn't pin this. In production, clock drift between Keycloak and the RS host at deploy-rollout windows could cause spurious 401s without leeway. Story 3.2 did not require a leeway config field; introducing one is out of scope. **Belongs to:** a future hardening pass (likely Story 5.2 security review). **Severity:** medium (real production behavior, but with strict-NTP clocks it's rarely hit; Keycloak's default 60s leeway is the upstream norm).

- **D65 — No test pinning `aud`-as-list (Keycloak's native shape)** — `services/resource-server/tests/auth/test_oidc_bearer.py`. PyJWT's `jwt.decode(audience="bmad-books-resource-server")` does the right thing when the token's `aud` claim is a list (Keycloak's `"aud": ["bmad-books-resource-server", "account"]`) — it checks membership. But the test suite mints tokens with `aud=<string>` only, so the list-shaped path is unverified. A future PyJWT change could regress without our tests noticing. **Belongs to:** a small test addition; not blocking. **Severity:** nit (defensive testing).

## Deferred from: code review of 3-3-rs-reading-speed-... (2026-05-17)

- **D66 — No upper bound on `pages_per_hour`** — `services/resource-server/src/resource_server/api/schemas/reading_speed.py`. `Field(ge=1)` allows arbitrary positives up to int64. A malicious or buggy client posting `pages_per_hour=999999999999` is persisted and later read back; downstream Story 4.1 estimate math (`pages / pages_per_hour * 60`) would yield a tiny "minutes" value (~0) and the formatted-duration helper would return `"≈ 0 m"`. Real fix: `Field(ge=1, le=10000)` — 10000 pages/hour is well above any plausible human reading speed (elite skim ceiling is ~600 pages/hour). **Belongs to:** Story 4.1 (where degenerate inputs become user-visible) or a security-review pass. **Severity:** medium (no current consumer; first real-world exposure is Story 4.1's POST /v1/estimate).

- **D67 — Empty `sub` (RFC-permitted) yields 412 not 401** — `services/resource-server/src/resource_server/auth/oidc_bearer.py:89-90` + `services/resource-server/src/resource_server/api/reading_speed.py`. Story 3.2's defensive `claims.get("sub", "")` means a JWT with `sub: ""` (RFC 7519 permits the literal empty string but Keycloak doesn't emit it) passes `_validate_access_token`'s `require=["sub"]` check (which validates presence not non-emptiness), then `get_for_user(session, "")` returns 412 `reading_speed_unset`. Architecturally an empty `sub` should fail authentication (401), not surface as a not-set business state. Real fix: reject empty `sub` in `_principal_from_claims` and emit `SESSION_EXPIRED`. **Belongs to:** Story 5.2 (security review document) — the security review will surface this as a documented accepted-or-fixed item alongside D63 (WWW-Authenticate header). **Severity:** low (theoretical attack surface; no real-world hit since Keycloak doesn't emit empty subs).

- **D68 — `validation_exception_handler` defensiveness gaps** — `services/resource-server/src/resource_server/core/errors.py:77-97`. Two related concerns. (a) Only one direct-handler test (`tests/core/test_errors.py::test_validation_error_via_http`) covers handler registration; a future story registering a different `RequestValidationError` handler later in app setup would silently replace this one without test failure. (b) Sanitization uses a denylist (`if k != "input"`) — a future Pydantic version adding a sensitive field (e.g., `ctx` already exists and can echo input fragments in some error subclasses) would leak through. Real fix: assert handler registration in `tests/core/test_errors.py` via `app.exception_handlers[RequestValidationError]` introspection, and switch the sanitization to an allowlist of safe keys (`{"loc", "msg", "type", "url"}`). **Belongs to:** a test-quality + security-review pass. **Severity:** low (defensive coding; current Pydantic version is sanitized correctly per the existing tests).

- **D69 — `sa.DateTime()` not `timezone=True` + ORM-only `onupdate` callable** — `services/resource-server/alembic/versions/0001_init_init_reading_speeds.py:14-15` + `services/resource-server/src/resource_server/models/entities/reading_speed.py:30-33`. Two related concerns. (a) The migration uses `sa.DateTime()` without `timezone=True` — the model stores `datetime.now(UTC)` (timezone-aware), SQLite stores ISO string and naïvely round-trips, but a future PostgreSQL/MariaDB deployment would mis-convert (TIMESTAMPTZ vs TIMESTAMP semantics differ across engines). (b) `sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)}` only fires when SQLAlchemy issues an UPDATE through the ORM — raw `session.execute(update(...))` statements or future Alembic data-migrations would NOT bump `updated_at`. Real fix: `sa.DateTime(timezone=True)` + `server_default=func.now(), onupdate=func.now()`. **Belongs to:** a cross-database-portability pass (coordinated with the BFF, which has the same pattern). **Severity:** low (SQLite is fine today; this story's surface is ORM-only via SQLModel).

- **D70 — Upsert race condition is documented but not behaviorally tested** — `services/resource-server/src/resource_server/services/reading_speed_service.py:23-46`. The SELECT-then-INSERT pattern is not atomic; two concurrent PUTs for the same `sub` (legitimate scenario: SPA double-click, mobile retry, etc.) can both pass the SELECT, both attempt INSERT, the second raises `IntegrityError` → 500. The service docstring explicitly endorses this stance ("500 is preferable to silent data loss") per the spec's design choice (architecture line 1140 vs. line 1141 trade-off), but no test exercises the path. A future refactor (e.g., upgrading to PostgreSQL and adopting `INSERT … ON CONFLICT(sub) DO UPDATE`) would need to verify behavior at the boundary. Real fix: add a test that triggers `IntegrityError` (e.g., `session.add` two rows with same `sub` directly + commit) and asserts the surfaced 500 envelope, OR switch to dialect-aware UPSERT via SQLAlchemy's `dialect.insert()`. **Belongs to:** a test-quality / hardening pass, coordinated with Story 5.x cross-DB portability work. **Severity:** medium (real race exists; current SPA single-click pattern + small load makes it rare).

## Deferred from: dev-story of 3-4-rs-post-v1-test-reset-endpoint (2026-05-17)

- **D71 — BFF could adopt the `change-me` placeholder reject for cross-service parity** — `services/bff/src/bff/api/test_reset.py` (BFF Story 1.12 module) vs. `services/resource-server/src/resource_server/api/test_reset.py` (this story). The RS's `register_test_reset_router` rejects the literal `"change-me"` placeholder as a third gate (after enable-flag and non-empty checks) — closes the "operator copies `.env.example` and forgets to rotate" hole for the RS surface. The BFF Story 1.12 enforces only the first two gates; it would silently accept `TEST_RESET_TOKEN=change-me` and mount the route with the publicly-known placeholder as the auth secret. **Real fix:** mirror the RS's `_PLACEHOLDER_TOKEN` check in `services/bff/src/bff/api/test_reset.py`'s `register_test_reset_router`. Story 3.4 chose to make this an RS-only decision rather than back-port to a `done` BFF surface — the BFF half is owned by Story 5.2 (security review document) so the defense-in-depth parity lands alongside the broader security pass. **Belongs to:** Story 5.2 (security review document). **Severity:** nit (defense-in-depth parity; the BFF's current single-source `.env` template + operator awareness mitigates).

- **D72 — `test_reset.py` lacks a 405-via-wrong-method positive test when the route IS registered** — `services/resource-server/tests/api/test_test_reset.py`. Scenarios 1–4 (gate-off / token misconfigured) assert that GET/PUT/DELETE/PATCH against `/v1/test/reset` return 404 because the route is not mounted. Scenarios 5–25 (gate ON) only exercise POST. **Not tested:** when the route IS registered and an attacker sends GET/PUT/DELETE/PATCH at `/v1/test/reset`, FastAPI returns 405 Method Not Allowed (not 401 — the auth check sits inside the POST handler, never reached). This is a minor coverage gap because the 405 path is FastAPI default behavior with no project-specific envelope; adding a dedicated parametrized test would pin the 405 emission so a future maintainer can't accidentally turn one of these methods into a side-channel. **Belongs to:** test-quality cleanup pass. **Severity:** nit (defensive testing; no current attack surface — FastAPI's default 405 doesn't leak business state).

- **D73 — `_classify_auth_failure` is case-sensitive on the `Bearer ` prefix** — `services/resource-server/src/resource_server/api/test_reset.py:111`. RFC 6750 §2.1 makes the `Bearer` scheme name case-insensitive; the project's convention (per BFF Story 1.12 dev log line 504 and this story's AC5) is to require the literal capitalized `Bearer ` for simplicity. Real-world clients (curl, httpx, Python requests) emit exactly `Bearer`, so the simplification is safe today. A future Playwright fixture or shell test using `BEARER` or `bearer` would silently 401 with `wrong_scheme`. **Real fix:** lowercase-compare the scheme — `if auth_header.split(" ", 1)[0].lower() != "bearer": return "wrong_scheme"`. **Belongs to:** Story 5.2 (security review document) — RFC-compliance pass alongside D63 (WWW-Authenticate header). **Severity:** nit (RFC compliance; no current consumer hit).

## Deferred from: code review of 3-4-rs-post-v1-test-reset-endpoint (2026-05-17)

- **D74 — `_classify_auth_failure` does not detect multi-bearer concat per RFC 9110 §5.3** — `services/resource-server/src/resource_server/api/test_reset.py:127-132`. HTTP allows multiple `Authorization` headers; a reverse-proxy that concatenates duplicates emits `Authorization: Bearer secret-xyz, Bearer evil`. `_classify_auth_failure` returns `None` (the header starts with `Bearer `), then the constant-time compare against `"secret-xyz, Bearer evil"` fails as `token_mismatch`. No security loss (still 401), but a legitimate caller routed through such a proxy would see every request silently fail. **Real fix:** split on `,` before stripping the prefix, reject when more than one comma-separated value contains `Bearer `. **Belongs to:** Story 5.2 (security review document); BFF Story 1.12 has the same pattern — coordinated fix. **Severity:** medium (real protocol scenario; no current consumer hits it because all callers are first-party).

- **D75 — Module-level `router` exposed via `__all__` enables gate bypass** — `services/resource-server/src/resource_server/api/test_reset.py:69,76` AND `services/bff/src/bff/api/test_reset.py` (same pattern). Both services declare the test-reset `APIRouter` at module scope with the POST handler attached, and export it in `__all__`. A future contributor mirroring the v1/v2 pattern in `main.py` who writes `from resource_server.api.test_reset import router; app.include_router(router)` (instead of calling the gate helper) silently mounts the endpoint with no env-flag check at registration — the handler still requires the env-bearer at runtime, but on a default-profile build with `TEST_RESET_TOKEN=change-me` the public template value becomes the auth secret. **Real fix:** rename `router` → `_router` (private) and drop from `__all__`; OR construct the `APIRouter` lazily inside `register_test_reset_router` so the route never exists outside the gate. **Belongs to:** Story 5.2 (security review document) — coordinated BFF + RS hardening. **Severity:** medium (footgun pattern; depends on a future maintainer's mistake to materialize).

- **D76 — `assert auth_header is not None` could be stripped under `PYTHONOPTIMIZE=1`** — `services/resource-server/src/resource_server/api/test_reset.py:138`. Python's `assert` is removed when the interpreter runs with `-O` / `PYTHONOPTIMIZE=1`. The subsequent `auth_header[len(_BEARER_PREFIX):]` would then raise `TypeError: 'NoneType' object is not subscriptable` on the missing-header path (`_classify_auth_failure` already returns `"missing_header"` for `None`, so the assert never fires at runtime — but if a future maintainer reorders the checks, the safety net is gone). No project Dockerfile or CI invocation uses `PYTHONOPTIMIZE` today. **Real fix:** replace the assert with an explicit `if auth_header is None: return _unauthorized_response()` to make the narrowing branch unconditional. **Belongs to:** a code-quality cleanup pass. **Severity:** low (deployed image does not strip asserts; defensive against future config changes).

- **D77 — `# type: ignore[arg-type]` on `**_OIDC_STUBS` hides typo signal** — `services/resource-server/tests/api/test_test_reset.py:84`. The test helper unpacks `_OIDC_STUBS` (a `dict[str, str]`) into `AppSettings(...)` kwargs with a blanket `type: ignore`. A typo in any of the dict keys (e.g., `oidc_audeince`) would silently no-op against AppSettings — pydantic-settings with `extra="ignore"` (the project's setting at `core/config.py:25`) drops unknown keys, so the test would pass while `AppSettings.oidc_audience` falls back to its default `""` and triggers the required-fail-fast validator. The `type: ignore` masks the signal that would otherwise catch this. **Real fix:** type `_OIDC_STUBS` as a `TypedDict` matching the `AppSettings` field names, OR pass kwargs explicitly. **Belongs to:** test-quality cleanup pass. **Severity:** low (no current typos; defensive against future typos).

- **D78 — `register_test_reset_router` is not idempotent — double-call would mount the route twice** — `services/resource-server/src/resource_server/api/test_reset.py:181-194`. `app.include_router(router)` does not deduplicate; calling the helper twice on the same `app` (e.g., a future test infrastructure refactor) appends a second copy of the POST handler to the routing table. Starlette's `Router` is first-match-wins so behavior is unchanged, but the INFO log fires twice and OpenAPI emits two identical path entries. No current call site invokes the helper more than once per app instance. **Real fix:** guard with `if any(route.path == _TEST_RESET_PATH for route in app.routes): return` before `app.include_router(router)`. **Belongs to:** defensive coding pass. **Severity:** low (no current call site triggers it).

- **D79 — Non-`AppException` exceptions (e.g., DB driver `OperationalError`) bypass the project envelope** — `services/resource-server/src/resource_server/api/test_reset.py:157-166` AND project-wide via `services/resource-server/src/resource_server/main.py:65-66`. The RS registers handlers only for `AppException` and `RequestValidationError`. A raw DB-driver exception (`sqlalchemy.exc.OperationalError`, `aiosqlite.OperationalError`, etc.) raised during `db.execute(...)` or `db.commit()` propagates as the bare ASGI default 500 (`text/plain "Internal Server Error"`) — NOT the project's `{errorCode: "internal_error", ...}` envelope. Story 3.4 scenario 24 documented this in dev log: the test accepts either bubbled-exception or `>=500`, intentionally not pinning the envelope shape. **Real fix:** register a catch-all `Exception` handler in `main.py` that emits `ErrorCode.INTERNAL_ERROR` (already declared at `core/errors.py:10`). **Belongs to:** Story 5.2 (security review document) — project-wide concern; the BFF has the same gap. **Severity:** low (the route's blast radius is e2e-only; the gap exists across every RS endpoint, not just this story's).
