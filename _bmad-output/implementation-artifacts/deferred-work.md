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

## Deferred from: code review of 2-1-bff-book-sqlmodel-migration-pydantic-boundary-models (2026-05-16)

- **W1 — `_strip_and_reject_blank` rejects only Python-`str.isspace` whitespace** — `services/bff/src/bff/api/schemas/book.py:14-17`. Zero-width / BOM characters (U+200B ZWSP, U+FEFF BOM, U+2060 WJ) are not whitespace by Python's definition, so a title consisting solely of those characters passes the validator and persists as a visually-empty book row. AC4 enumerates only `title="   "` (regular spaces); broader Unicode normalization is out of scope for the boundary-types-only story. Fix when needed: normalize via `unicodedata.category(c) in {"Cf", "Zs", ...}` filtering before the strip. **Belongs to:** future input-hardening pass (Story 5.2 security review or a dedicated 2.x hardening story). **Severity:** low (deferred; spec-compliant interpretation of "whitespace-only").
- **W2 — No test asserts `BookOut.model_validate(Book(status="archived", ...))` raises** — `services/bff/tests/api/schemas/test_book_schemas.py`. The Pydantic `Literal["to-read","reading","finished"]` would reject an out-of-set status flowing from an ORM instance into `BookOut`, but no test pins that contract. A future relaxation of the type (e.g., `BookStatus | str` to be "lenient") would silently pass model_validate and leak garbage status values into responses. AC9 did not enumerate this case. Fix: add a `test_book_out_rejects_unknown_status_from_orm` parameterized test. **Belongs to:** Story 2.2 (CRUD) test-coverage extension, or a defensive-coverage pass. **Severity:** low (deferred; spec-compliant; defensive only).

## Deferred from: code review of 2-2-bff-full-books-crud-v1-books-v1-books-id (2026-05-16)

- **W3 — No row-level lock on PATCH path (concurrent PATCH/DELETE race)** — `services/bff/src/bff/services/books_service.py:update`. The two-step `get_for_user → setattr → commit` is not wrapped in `SELECT FOR UPDATE`, so a concurrent DELETE between read and commit could leave the PATCH committing against a row that no longer exists in some engines. With SQLite (sole supported engine in 2.x) the BEGIN IMMEDIATE serializes the writers; on Postgres the race window is real. **Belongs to:** Epic 5 / a deployment-hardening story when Postgres or another concurrent-writer engine lands. **Severity:** low (deferred; no correctness impact in the current SQLite + single-process deployment).
- **W4 — `VALIDATION_ERROR` enum member retained as dead surface** — `services/bff/src/bff/core/errors.py:11`. AC11 mandates the member stays for "enum-surface stability", but no handler emits it on the wire after Story 2.2. A future contributor could mistakenly resurrect it and break the lower_snake_case wire-code convention. **Belongs to:** future cleanup story; remove `VALIDATION_ERROR` from the enum once no external surface asserts on it. **Severity:** nit (deferred; documented in the enum comment).
- **W5 — PATCH `{"title": null}` cascades to a 500 IntegrityError instead of a 422** — `services/bff/src/bff/api/schemas/book.py:BookUpdate` + `bff.services.books_service.update`. The `BookUpdate.title` validator returns `None` early when `v is None`, so explicit `null` passes Pydantic; the service then `setattr(book, "title", None)` and `commit` fails on the `nullable=False` column. AC7 / Dev Notes line 591 explicitly accepted this fall-through for Story 2.2's scope. **Belongs to:** future hardening — add validators on `BookUpdate` that reject explicit `null` at the boundary, or wire an IntegrityError handler that converts to 400 `invalid_input`. **Severity:** medium (deferred; documented; surfaces only on intentionally-malformed client input).
- **W6 — No pagination on `GET /v1/books`** — `services/bff/src/bff/services/books_service.py:list_for_user`. Returns every row matching `sub`; no LIMIT/OFFSET. Architecture §C8 line 420 explicitly defers pagination / sorting / search. **Belongs to:** future story when the per-user book list grows large enough to matter. **Severity:** low (deferred; explicit architecture deferral; demo-scale users will have ≤ a few dozen rows).

## Deferred from: code review of 2-4-spa-booksservice-types (2026-05-16)

- **D54 — `BooksService.setStatus()` concurrent-call snapshot races** — `spa/src/app/books/books-service.ts:54-86`. If two `setStatus(id, ...)` calls fire concurrently against the same row, the second call's `prev` snapshot captures the first call's *optimistic* (not original) status. If the first call fails and the second succeeds, the revert restores an intermediate optimistic value rather than the true prior status. Story 2.4 explicitly out-of-scopes concurrent scenarios (story line 142: "Stories 2.5 / 2.6 do not test cross-tab scenarios"). UX-DR7 / J2 spec do not exercise concurrent clicks. **Belongs to:** a future UI-hardening pass — gate `setStatus` per-row with an `inFlight` set, or queue requests serially.
- **D55 — `BooksService.load()` concurrent-call last-wins** — `spa/src/app/books/books-service.ts:20-29`. Two concurrent `load()` calls both set `loading=true`, both fire `GET /v1/books`, and the last-resolved one wins `books.set(list)`. No AC requires de-duplication; the initial-load is a single entry-point per page from `BookListPage` (Story 2.5). **Belongs to:** future hardening if multiple subscribers ever trigger concurrent loads — track an in-flight promise and return it from re-entrant calls.
- **D56 — `BooksService.update()` against an unknown id triggers a "phantom" signal write** — `spa/src/app/books/books-service.ts:43-52`. `prev.map(b => b.id === id ? updated : b)` always returns a new array reference even when no row matched. Downstream `effect()` / `computed()` re-evaluate for a value-equal-but-reference-different signal. Acceptable per story line 152 ("`prev.map` is a no-op for that id — no `books` mutation occurs even on a 200"). **Belongs to:** future optimization — skip the `books.update(...)` call entirely when `prev.some(b => b.id === id)` is false.

## Deferred from: code review of 2-3-bff-extend-v1-test-reset-to-truncate-books (2026-05-16)

- **W7 — No scenario specifically exercises third-DELETE (books) rollback after first two succeed** — `services/bff/tests/api/test_test_reset.py::test_scenario_24_db_failure_returns_project_envelope`. Scenario 24 monkeypatches `_AsyncSession.execute` to raise `SQLAlchemyError` on every call, so the FIRST execute (sessions DELETE) trips the except branch — auth_states and books DELETEs never run. The new books DELETE inherits the same `try/except (SQLAlchemyError, OSError)` wrapper, so structurally identical to sessions/auth_states (Story 1.12 Dev Notes line 332–334 explicitly accepted this for the 2.3 addition). **Belongs to:** future test-hardening pass — add a parameterized fixture that fails the Nth execute (N ∈ {0, 1, 2}) to prove rollback symmetry for each table. **Severity:** nice-to-have (deferred; spec explicitly accepted structural equivalence).
- **W8 — No scenario covers all three counters with positive values simultaneously** — `services/bff/tests/api/test_test_reset.py`. Story 2.3 Task 6 listed an optional `test_scenario_14c_correct_bearer_all_three_tables_populated` (e.g., 2 sessions + 3 auth_states + 5 books → log `2 3 5`) for full counter-matrix symmetry. Scenarios 14 (5/3/0) + 14b (0/0/4) together exercise every counter slot independently; the all-three-non-zero combinator is the missing cell. AC3's wire contract is structurally covered, so this is a coverage-symmetry nit, not a behavior gap. **Belongs to:** future test-coverage pass when the matrix-completeness backlog comes around. **Severity:** nice-to-have (deferred; spec author explicitly skipped per Task 6 "pick one approach" guidance).

## Deferred from: code review of 2-5-spa-booklist-page-bookform-add-variant-states (2026-05-16)

- **D57 — `<input type="number">` for `pages` accepts decimals** — `spa/src/app/books/book-form.html`. The native number input has no `step="1"` and the FormControl uses `Validators.min(1)` only. A user typing `1.5` passes client-side validation and is sent to the BFF; Pydantic's `int` field rejects it as `invalid_input` and the form renders the generic server-error copy. Functionally correct but the round-trip is wasteful and the error copy is less precise than a client-side "Page count must be a whole number." would be. **Belongs to:** a future UX-polish pass — add `step="1"` to the input and/or a `Validators.pattern(/^\d+$/)` client validator with a dedicated copy string. **Severity:** nit (deferred; round-trip cost is one request per malformed entry).
- **D58 — `BookForm.onSubmit` has no synchronous double-submit guard beyond the `[disabled]` attribute** — `spa/src/app/books/book-form.ts:onSubmit`. The button disables on `submitting()`, but a programmatic caller (e.g., a test, an a11y tool that bypasses `disabled`, or a future `(keyup.enter)` handler) could invoke `onSubmit()` twice before the first awaited `create()` resolves. Both calls would set `submitting=true` and both `await create()` — two POST requests against the BFF, two rows persisted. The DOM-level disabled gate covers the realistic user paths but not the programmatic ones. **Belongs to:** a future hardening pass — add an early `if (this.submitting()) return;` at the top of `onSubmit`. **Severity:** low (deferred; no observed user path triggers the race).
- **D59 — `BookList`'s loading state never shows during a re-fetch when `books` is already populated** — `spa/src/app/books/book-list.ts` + `book-list.html`. The loading template branch requires `books().length === 0` (per AC4 precedence: "loading wins over empty so the first paint isn't 'No books yet.' flashing"). A re-`load()` after the initial fetch (e.g., a future pull-to-refresh or a router navigation that triggers re-init) won't surface the spinner if rows are already on screen. Story 2.5 explicitly out-of-scopes re-fetch UX (story AC4 note: "a `load()` re-fetch with existing data is not in scope"). **Belongs to:** Story 5.x / a UX-polish pass when re-fetch becomes a feature. **Severity:** nit (deferred; explicit AC out-of-scope).
- **D60 — `BookListPage` does not guard against `load()` rejection** — `spa/src/app/books/book-list-page.ts:ngOnInit`. The `void this.booksService.load()` intentionally discards the Promise. `BooksService.load()` is documented (Story 2.4 AC5) to swallow all errors into the `loadError` signal and resolve `void` — but if a future contributor changes `load()` to re-throw, the unhandled Promise rejection would surface only in the browser console (not as an in-app failure state). **Belongs to:** future defensive-coding pass — add a `.catch(() => undefined)` to the discarded Promise, or convert `load()` into a `Promise<void>` that is always-resolving and document the contract more loudly. **Severity:** nit (deferred; depends on a Story 2.4 contract holding).
- **D61 — `BookForm` re-uses `LoginView`'s button styling via a duplicated CSS rule, not a shared token** — `spa/src/app/books/book-form.css:.book-form-submit` (vs `spa/src/app/login/login-view.css:.login-button`). Both buttons share `background: var(--color-accent)`, hover state, disabled `opacity: 0.5`, and `padding: var(--spacing-2) var(--spacing-4)`. The visual contract is identical; the CSS is copy-paste. A `--button-primary` mixin or a shared `Button` component would consolidate. UX-DR14 mandates the styling, and the duplication is two rules. **Belongs to:** Story 5.3 (UI polish / README) or an Epic-5 UI-component-extraction pass. **Severity:** nit (deferred; pure duplication, no behavior drift).

## Deferred from: code review of 2-6-spa-bookrow-statuscontrol-with-optimistic-ui-edit-delete (2026-05-17)

- **D62 — Concurrent `BookRow.onDeleteClick()` double-click dispatches two DELETE requests** — `spa/src/app/books/book-row.ts:69-82`. There is no synchronous in-flight guard on `onDeleteClick`. A user double-clicking "Delete" gets two `window.confirm` dialogs in sequence; if they OK both, two `BooksService.delete(id)` calls fire. The first 204s and removes the row; the second 404s (`book_not_found`) and surfaces a misleading inline "Couldn't delete this book — try again." on a row that is, in fact, already gone. Structurally identical to Story 2.5 D58 (synchronous double-submit guard on `BookForm.onSubmit`) which is also deferred. **Belongs to:** a future UI-hardening pass — add an `if (this.deleting()) return;` early guard or reuse a `busy` signal. **Severity:** low (deferred; not observed during normal use; the browser modal serializes confirms, so the racing window is small).
- **D63 — `BookList`'s populated-state test stub lacks `delete` / `update` / `setStatus` methods on the `BooksService` mock** — `spa/src/app/books/book-list.spec.ts:32-38` (the `makeBooksServiceStub()` helper). After Story 2.6, `BookRow` (the new populated-state child) injects `BooksService` and calls those three methods. The current test only renders — never clicks — so the stub is sufficient today. A future test that adds a click would crash with `stub.delete is not a function`. **Belongs to:** a future test-hardening pass — extend `makeBooksServiceStub()` with no-op async stubs, or switch the suite to the real-`BooksService` + `HttpTestingController` pattern used in `book-form.spec.ts` / `book-row.spec.ts`. **Severity:** nit (deferred; defensive hardening, not a current-test bug).

## Surfaced during Story 2.7 implementation (2026-05-17)

### W9 — `just e2e-up` (compose-runner path) hangs because the runner-internal Chromium cannot reach `http://localhost:8080` for Keycloak

**Surfaced by:** Story 2.7 dev agent (`COMPOSE_PROJECT_NAME=bmad-2-7-e2e docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit` → 1 passed / 12 timed out at 60s each; total 12.5 minutes).
**Files:** `compose/infra.yml:19` (`KC_HOSTNAME: localhost`), `compose/app.yml:60-103` (`playwright` service; no `extra_hosts` wiring), `services/bff/.env.example:38` (`OIDC_AUTHORIZE_URL_BROWSER=http://localhost:8080/...`).
**Issue:** Keycloak emits browser-facing URLs anchored on `KC_HOSTNAME=localhost` — `http://localhost:8080/realms/bmad-books/protocol/openid-connect/auth?...`. When the BFF 302s a browser navigation to `/auth/login`, it returns this localhost-anchored URL to whatever browser is driving the test. On the **host-side** local-dev workflow that URL is correct (Keycloak's `:8080` is published to the host). But on the **compose-runner** path, the browser lives inside the `playwright` container where `localhost` resolves to the runner's own loopback — Keycloak is unreachable. Every J1/J2/J5 test that performs the OAuth round-trip times out at 60s waiting for the Keycloak login form to load.
**Why Story 1.13 / 1.14 didn't catch this:** Story 1.14's Completion Notes explicitly state "AC8 (Task 6 live `just e2e-up`): Live `just e2e-up` skipped — requires running Keycloak + full compose stack. Deferred to reviewer." No subsequent story closed that loop. Story 2.7's spec was wholly testable via the local-dev workflow (`docker compose up -d keycloak bff` + `npm test` from the host), so the compose-runner path was not on the critical path for Story 2.7's correctness — but it remains broken for AC13's "13 passed via `just e2e-up`" requirement.

**Concrete fix options:**
  (a) **`extra_hosts: ["localhost:host-gateway"]`** on the `playwright` service in `compose/app.yml`. Maps `localhost` inside the runner container to the host machine, which then has Keycloak's `:8080` published to it. Requires Docker Engine 20.10+ for `host-gateway` magic (already a prereq). Smallest delta to compose YAML; no env-var plumbing changes.
  (b) **Separate browser-URL for the in-compose runner**: introduce `OIDC_AUTHORIZE_URL_BROWSER_FROM_E2E_RUNNER=http://keycloak:8080/...` and inject it into the `playwright` service's environment so the SPA (served from BFF) is aware that requests from the runner-side browser should go through the compose network. Requires SPA-side awareness of which-browser-am-I, which is architecturally ugly.
  (c) **Front Keycloak with a reverse proxy** (e.g., Traefik) that bridges container-network and host-network names. Heavier and out of proportion for the demo project.

Option (a) is the smallest correct fix; (b)/(c) are documented for completeness only.

**Attempted on 2026-05-17 (post-Story 2.7 follow-up) — both option (a) and a host.docker.internal variant were tried and reverted. Lessons learned:**

- **Option (a) does NOT work**: `extra_hosts: ["localhost:host-gateway"]` was applied; same 1 passed / 12 timed-out result. Root cause: **Chromium hard-codes `localhost` to its own loopback** (the hostname is special-cased as a "secure context" for security/performance — `chrome://flags#allow-insecure-localhost` and the localhost-loopback CL are the documented basis). The browser ignores `/etc/hosts` entries for `localhost` regardless of `extra_hosts`.

- **Option (a)-variant via `host.docker.internal` also incomplete**: a second attempt rewired the compose stack to anchor browser-facing URLs on `host.docker.internal` (which Chromium does NOT special-case):
  - `extra_hosts: ["host.docker.internal:host-gateway"]` on the playwright service (Linux CI compat; no-op on Docker Desktop).
  - `KC_HOSTNAME: host.docker.internal` override on keycloak in `compose/app.e2e.yml`.
  - `OIDC_AUTHORIZE_URL_BROWSER: http://host.docker.internal:8080/realms/bmad-books` override on bff in `compose/app.e2e.yml`.

  This got the browser past the initial KC redirect (KC's login form rendered and the password was submitted — confirmed by KC's `Non-secure context detected` cookie warning in the logs), but **every test still failed** at the next step: the post-login redirect from KC back to the BFF callback landed on `chrome-error://chromewebdata/`. Diagnosis: the OAuth flow has **four** URLs that need to anchor on the same browser-reachable host, and the partial fix only covered two of them.

- **The full URL-chain that must be browser-reachable from inside the runner container:**
  1. KC authorize endpoint (`OIDC_AUTHORIZE_URL_BROWSER`) — set in `.env`, BFF emits in 302. ✅ covered by the partial fix.
  2. KC login form action + session cookies (`KC_HOSTNAME`-based) — KC's own response Set-Cookies + form-submit URL. ✅ covered by the partial fix.
  3. **BFF callback URL** (`BFF_BASE_URL` → `/auth/callback`) — KC redirects browser back here after login. ❌ still `localhost:8000` after the partial fix → chrome-error.
  4. **Playwright `baseURL`** (`E2E_BASE_URL` in `compose/app.yml`) — currently `http://bff:8000`; would need to match (3) for origin / SameSite-cookie consistency with the callback.
  5. **KC realm `redirectUris` + `webOrigins`** (`keycloak/realm-bmad-books.json:82-87`) — currently hardcoded to `http://localhost:8000/auth/callback` / `http://localhost:8000`. KC rejects any redirect_uri not in the registered list; would need an additional `http://host.docker.internal:8000/...` entry (keeping the localhost entries so host-side dev still works).

- **Validation cost so far**: two ~13-minute runs (each fails after 12 × 60s test timeouts). Each iteration is expensive — debug it with a single-test invocation (`npx playwright test j1-first-login.spec.ts:53 --reporter=line`) once a full hypothesis is wired, not on the full suite.

**Recommended next attempt (a comprehensive option (a)-variant):**
  1. Add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `playwright` service in `compose/app.yml`.
  2. In `compose/app.e2e.yml`, override on the `bff` service: `BFF_BASE_URL=http://host.docker.internal:8000`, `OIDC_AUTHORIZE_URL_BROWSER=http://host.docker.internal:8080/realms/bmad-books`.
  3. In `compose/app.e2e.yml`, override on the `keycloak` service: `KC_HOSTNAME=host.docker.internal`.
  4. In `compose/app.yml` playwright service env: change `E2E_BASE_URL` to `http://host.docker.internal:8000`.
  5. In `keycloak/realm-bmad-books.json`, append `http://host.docker.internal:8000/auth/callback` to `redirectUris` and `http://host.docker.internal:8000` to `webOrigins` (do NOT remove the existing localhost entries — they're still needed for host-side dev).
  6. Verify the J5 refresh-token revocation assertion still works: it uses `KEYCLOAK_INTERNAL_URL=http://keycloak:8080` for a runner-process back-channel POST (not a browser call), so it should be unaffected by the browser-URL rewiring — but worth confirming once the OAuth chain is green.

**Belongs to:** Epic 5 / a compose-hardening story, OR a dedicated Story 1.14 follow-up. Given the wider-than-expected blast radius (touches realm JSON + 3 compose files + an env override) this is no longer "one-line follow-up" territory — it deserves its own story with a clean AC list.
**Severity:** medium (deferred — the local-dev workflow is fully verified-green for J2; the compose-runner path is the canonical-CI path and is broken, but no production behavior depends on it).
**Blocks:** Story 1.13 AC6 (originally "deferred to reviewer"), Story 1.14 AC8 ("skipped"), Story 2.7 AC13 (compose-runner half), Story 5.4 final smoke (almost certainly).

