# Story 7.2: OIDC discovery bootstrap (no more hardcoded endpoint URLs)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer promoting the POC between environments,
I want the BFF and Resource Server to read all OIDC endpoint URLs from `${OIDC_ISSUER_URL}/.well-known/openid-configuration` at startup,
so that environment promotion requires changing only the ISSUER base URL — matching the ACME-TS "discovery over hardcoding" principle (P6).

## Acceptance Criteria

**AC1 — Single env var per service.** After this story, BFF requires only `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `BFF_CLIENT_SECRET`, and the new `OIDC_PUBLIC_BASE_URL` (the front-channel-host split — see AC4). RS requires only `OIDC_ISSUER_URL` and `OIDC_AUDIENCE`. The previously-required `OIDC_JWKS_URL` and `OIDC_AUTHORIZE_URL_BROWSER` are **removed** from the BFF/RS settings classes, their fail-fast validators, `.env.example`, and from `compose/app.yml`. Removal is hard (this is a POC — no deprecation grace period); pydantic-settings' `extra="ignore"` already drops unknown env vars cleanly.

**AC2 — Discovery happens at startup.** On BFF startup (FastAPI `lifespan` startup hook, in `services/bff/src/bff/main.py`), the service GETs `${OIDC_ISSUER_URL}/.well-known/openid-configuration` once, parses the response, and caches the resolved URLs (`authorization_endpoint`, `token_endpoint`, `jwks_uri`, `end_session_endpoint`, `revocation_endpoint`, `issuer`) into an `OidcDiscovery` frozen dataclass stored on `app.state.oidc_discovery`. Same pattern on the Resource Server (`services/resource-server/src/resource_server/main.py`) — the RS only needs `jwks_uri` and `issuer`, but the rest of the doc is cached for parity. Expose `OidcDiscovery` as a FastAPI dependency on each service (e.g. `get_oidc_discovery(request: Request) -> OidcDiscovery`) so route handlers and downstream clients can read it via `Depends(...)` rather than via the module-level `settings` singleton.

**AC3 — Fail-fast on unreachable AS.** If the startup discovery fetch fails (connection error, non-2xx, malformed JSON, missing any of the six required fields), the lifespan startup raises and the process exits non-zero with a `discovery_unreachable: <classifier>` log line at ERROR. No silent fallback, no retry. The existing `/health` probe continues to report runtime discovery reachability (it currently re-fetches the doc on every probe — Story 7.2 reroutes it to a stale-tolerant read from `app.state.oidc_discovery`, eliminating the per-probe outbound HTTP call and closing security-review §14 finding D25 incidentally).

**AC4 — Browser-facing authorize URL split preserved via `OIDC_PUBLIC_BASE_URL`.** The compose dev topology splits the BFF's front-channel (browser → localhost:8080) and back-channel (BFF container → keycloak:8080) hostnames for Keycloak — see deferred-work D2/D8, currently bridged by the removed `OIDC_AUTHORIZE_URL_BROWSER` env var. After Story 7.2: introduce `OIDC_PUBLIC_BASE_URL` on the BFF settings class (no RS equivalent; the RS only does back-channel calls). It defaults to `${OIDC_ISSUER_URL}` (the production case where front-channel = back-channel) and is overridden to the browser-facing base URL in compose dev. When constructing the `/auth/login` 302 target, the BFF takes the **path** from discovery's `authorization_endpoint` and the **scheme+authority** from `OIDC_PUBLIC_BASE_URL`. Same rule for `expected_issuer` in id_token validation (browser-facing host = the `iss` value Keycloak signs into tokens when KC_HOSTNAME=localhost). All other URLs (token, revocation, end-session, JWKS) are taken from discovery as-is — they are back-channel.

**AC5 — Tests.** Unit tests for the discovery loader in both services covering: (a) happy path returns a populated `OidcDiscovery`; (b) connection refused / `httpx.ConnectError` → lifespan startup raises; (c) HTTP 404 → lifespan startup raises; (d) HTTP 200 with malformed JSON body → lifespan startup raises; (e) HTTP 200 with missing `jwks_uri` (or any other required field) → lifespan startup raises; (f) HTTP 200 with extra unknown fields → succeeds, unknown fields preserved as nothing (ignored). Integration tests verify `/auth/login` 302 Location, `/auth/callback` token exchange POST URL, and `/auth/logout` revocation + end-session POSTs all use the discovered URLs (not string-concatenated from `OIDC_ISSUER_URL`). The synthetic IdP fixture in `services/bff/tests/auth/synthetic_idp.py` and `services/resource-server/tests/auth/conftest.py` already exposes `discovery_doc` (`_build_discovery_doc`, lines 146–165) — no harness API changes needed; existing tests pass through the new discovery indirection unchanged because the synthetic IdP already mocks `/.well-known/openid-configuration` (line 200–202). `tests/conftest.py` placeholders for `OIDC_JWKS_URL` and `OIDC_AUTHORIZE_URL_BROWSER` are deleted in both services.

**AC6 — Config + docs cleanup.** `.env.example` (repo root) is unchanged in env-var shape because no OIDC URL fields live there today (they live in `compose/app.yml`'s `environment:` blocks per D141). `compose/app.yml`: remove `OIDC_JWKS_URL` and `OIDC_AUTHORIZE_URL_BROWSER` from both the BFF and RS services; add `OIDC_PUBLIC_BASE_URL: http://localhost:8080/realms/bmad-books` to the BFF service. Both services' `OIDC_ISSUER_URL` becomes the unified back-channel value `http://keycloak:8080/realms/bmad-books` (the RS's current host-facing value `http://localhost:8080/...` is replaced). `services/bff/src/bff/core/config.py` and `services/resource-server/src/resource_server/core/config.py`: remove `oidc_jwks_url` field + its validator (RS only) and `oidc_authorize_url_browser` field + its validator (BFF only); add `oidc_public_base_url` field on BFF with a `_validate_oidc_public_base_url` validator (mirror the existing `_validate_oidc_issuer_url` shape — non-empty, http/https prefix, urlparse netloc non-empty). README — section "Environment variables" — and `docs/security-review.md` — `keycloak_cookie_session.py` implementing-code-paths line — updated to reflect the new env contract. Keycloak's `KC_HOSTNAME_BACKCHANNEL_DYNAMIC: "true"` is added to `compose/infra.yml` so discovery body URLs match the request's Host header (see Dev Notes §"The front-channel / back-channel hostname trap").

## Tasks / Subtasks

- [x] **Task 1 — Author `OidcDiscovery` dataclass and discovery loader (BFF + RS shared shape).** (AC1, AC2, AC3)
  - [x] Add `services/bff/src/bff/auth/oidc_discovery.py` with a frozen `@dataclass OidcDiscovery` carrying the six string fields (`issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `end_session_endpoint`, `revocation_endpoint`) plus an async `fetch_discovery(issuer_url, *, connect_timeout, read_timeout, client_factory=httpx.AsyncClient) -> OidcDiscovery` function. The function GETs `${issuer_url.rstrip("/")}/.well-known/openid-configuration` honoring §C6 timeouts (5s connect / 10s read), follows 3xx redirects (mirror `_check_oidc_discovery` lines 134), parses the JSON, asserts each of the six required fields is a non-empty `str`, and returns the dataclass. Any failure (httpx.HTTPError, JSON parse failure, non-2xx, missing/empty required field) raises a `DiscoveryFetchError(classifier: str)` whose message is a one-token classifier safe for ERROR logging (no URL, no response body).
  - [x] Add `services/resource-server/src/resource_server/auth/oidc_discovery.py` with the same `OidcDiscovery` dataclass + `fetch_discovery` function. RS uses its own `oidc_jwks_connect_timeout` / `oidc_jwks_read_timeout` settings (currently consumed by `_check_jwks`) — repurpose those (rename to `oidc_discovery_connect_timeout` / `oidc_discovery_read_timeout` to mirror the BFF; OK, see Task 6).
  - [x] No retries on either loader. The lifespan call site catches `DiscoveryFetchError` and re-raises with the classifier embedded in the message so uvicorn's startup error surface carries it.

- [x] **Task 2 — Wire the lifespan hook on both services.** (AC2, AC3)
  - [x] In `services/bff/src/bff/main.py`'s `lifespan(app)`: after `configure_logging(settings)`, await `fetch_discovery(settings.oidc_issuer_url, ...)`. On success, stash on `app.state.oidc_discovery = discovery`. On `DiscoveryFetchError as exc`, log at ERROR (`logger.error("discovery_unreachable: %s", exc.classifier)`) and re-raise — uvicorn aborts startup with a non-zero exit code.
  - [x] Add `def get_oidc_discovery(request: Request) -> OidcDiscovery: return request.app.state.oidc_discovery` next to `_settings_dep` in `services/bff/src/bff/api/auth.py` (or in a new `services/bff/src/bff/core/deps.py` if you'd prefer a central location — but the existing pattern is "dependency providers next to their consumers", so per-router placement is acceptable).
  - [x] Mirror on RS: lifespan call in `services/resource-server/src/resource_server/main.py` after `configure_logging(settings)`. The RS lifespan also runs `SQLModel.metadata.create_all` for local dev (line 41); place discovery fetch BEFORE the create_all so a discovery failure aborts startup before any DB work happens. Expose `get_oidc_discovery` for RS dependency injection (consumers land in Task 4).

- [x] **Task 3 — BFF: replace hardcoded URL construction with discovery reads.** (AC4)
  - [x] `services/bff/src/bff/api/auth.py` line 144 (`/auth/login`): replace `authorize_url_browser=cfg.oidc_authorize_url_browser` with the discovery-driven derivation — take the **path** (and query, if any) from `discovery.authorization_endpoint` and the **scheme+authority** from `cfg.oidc_public_base_url`. Either inline a small helper (e.g. `_browser_authorize_base(discovery, public_base) -> str`) or extend `build_authorize_url` to take a `browser_base: str` parameter and split the URL inside the function. Whichever shape: ALL URL parsing must use `urllib.parse.urlparse`/`urlunparse` (not string slicing) — Python's `http://localhost:8080/realms/bmad-books` does not have a trailing slash but the test fixtures sometimes do.
  - [x] `services/bff/src/bff/api/auth.py` line 223 (`/auth/callback` token exchange): replace `token_url = cfg.oidc_issuer_url.rstrip("/") + "/protocol/openid-connect/token"` with `token_url = discovery.token_endpoint`.
  - [x] `services/bff/src/bff/api/auth.py` line 248 (`/auth/callback` id_token verification): replace `jwks_url=cfg.oidc_jwks_url` with `jwks_url=discovery.jwks_uri`. Replace `expected_issuer=cfg.oidc_authorize_url_browser` with `expected_issuer=cfg.oidc_public_base_url` derived to match — actually, the correct value is the `iss` claim Keycloak signs into the id_token. Under `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` (see Task 7 / Dev Notes), that becomes the back-channel issuer (== `discovery.issuer`). Set `expected_issuer=discovery.issuer`.
  - [x] `services/bff/src/bff/api/auth.py` lines 430–432 (`/auth/logout`): replace the `revocation_url` and `end_session_url` derivations with `discovery.revocation_endpoint` and `discovery.end_session_endpoint` respectively.
  - [x] `services/bff/src/bff/services/resource_server_client.py` line 370 (refresh token flow): replace `self._settings.oidc_issuer_url.rstrip("/") + _TOKEN_PATH_SUFFIX` with `discovery.token_endpoint`. The `ResourceServerClient` is constructed once at app startup so it can hold a reference to `discovery` — add a constructor parameter and inject it from the dependency tree. Delete the `_TOKEN_PATH_SUFFIX` module-level constant if it becomes unused.
  - [x] Delete the `oidc_jwks_url` and `oidc_authorize_url_browser` fields from `services/bff/src/bff/core/config.py` (lines 82 + 91). Delete the `_validate_oidc_authorize_url_browser` validator (lines 146–166). Add `oidc_public_base_url: str = ""` field with a `_validate_oidc_public_base_url` validator mirroring `_validate_oidc_issuer_url` (lines 120–144).

- [x] **Task 4 — RS: replace hardcoded URL reads with discovery reads.** (AC4)
  - [x] `services/resource-server/src/resource_server/auth/oidc_bearer.py` line 78: replace `_get_jwks_client(settings.oidc_jwks_url)` with `_get_jwks_client(discovery.jwks_uri)`. The simplest path is to read `discovery` from a module-level cache populated by the lifespan hook, or thread it via the auth-functions factory (`make_oidc_bearer_auth(settings_arg, discovery)`). The module-level approach matches the existing `_jwks_clients: dict[str, jwt.PyJWKClient]` pattern; consult the dev notes before choosing.
  - [x] `services/resource-server/src/resource_server/auth/oidc_bearer.py` line 85: replace `issuer=settings.oidc_issuer_url` with `issuer=discovery.issuer`.
  - [x] Delete the `oidc_jwks_url` field from `services/resource-server/src/resource_server/core/config.py` (line 91). Update `_validate_oidc_required_fail_fast` (lines 114–139) to no longer enumerate `OIDC_JWKS_URL`.
  - [x] Rename `oidc_jwks_connect_timeout` / `oidc_jwks_read_timeout` → `oidc_discovery_connect_timeout` / `oidc_discovery_read_timeout` for consistency with the BFF (lines 96–100). Update the only consumer (`_check_jwks` in `services/resource-server/src/resource_server/api/health.py` line 126) — actually `_check_jwks` is going to be replaced entirely (Task 5), so the timeouts become `_check_oidc_discovery`'s.

- [x] **Task 5 — Re-route `/health` to read from cached discovery instead of re-fetching.** (AC3, security-review §14 D25)
  - [x] BFF `services/bff/src/bff/api/health.py`: the existing `_check_oidc_discovery` function (lines 97–154) currently makes an outbound httpx request on every health probe. Replace its body with a read of `app.state.oidc_discovery` — if the lifespan hook completed, the cached doc is present and we return `(True, "")`. The probe becomes a presence check; runtime AS reachability is no longer a /health concern (it was already a stale signal — the doc rarely changes). Update `_check_oidc_discovery`'s signature to take `app: FastAPI` (or read from a passed-in `OidcDiscovery | None`) rather than `cfg: AppSettings`.
  - [x] RS `services/resource-server/src/resource_server/api/health.py`: replace `_check_jwks` (lines 105–155) with `_check_oidc_discovery` reading from `app.state.oidc_discovery`. Mirror the BFF's shape exactly. The response body key changes from `"jwks"` to `"oidc_discovery"` to match the BFF. Update the `_health` handler's logging line + the response detail dict accordingly. Note: this is a small `/health` response-shape change — surface it in the Change Log and the security-review.md update.

- [x] **Task 6 — Update test conftest + synthetic IdP fixtures.** (AC5)
  - [x] `services/bff/tests/conftest.py`: delete the `OIDC_AUTHORIZE_URL_BROWSER` placeholder (line 22) — the field no longer exists. Add `OIDC_PUBLIC_BASE_URL` placeholder pointing to the synthetic IdP's `DEFAULT_ISSUER` (the synthetic IdP's discovery doc emits matching URLs, so front-channel = back-channel in tests). The synthetic IdP's `mock.get(f"{DEFAULT_ISSUER}/.well-known/openid-configuration")` route (line 200) already covers the lifespan discovery fetch — no harness API change needed.
  - [x] `services/resource-server/tests/conftest.py`: delete the `OIDC_JWKS_URL` placeholder (lines 21–24). The RS conftest doesn't currently mount a synthetic-IdP fixture — but the RS's lifespan now needs a discovery endpoint to fetch. Mount a `respx` route in the RS conftest that returns a minimal discovery doc keyed off `OIDC_ISSUER_URL` (mirror the BFF synthetic IdP's `_build_discovery_doc` shape). Pattern: an autouse session-scoped fixture that registers the route before `resource_server.main.app` is imported.
  - [x] `services/bff/tests/auth/synthetic_idp.py`: no changes — the existing `discovery_doc` and mock route satisfy the new code path.
  - [x] Any test that currently sets `oidc_jwks_url` or `oidc_authorize_url_browser` via `monkeypatch.setattr(settings, ...)` — search-and-replace; remove the setattr. Specifically: `services/bff/tests/api/test_auth.py:48–50`, `services/bff/tests/core/test_config.py:171–197` (rewrite the `test_oidc_authorize_url_browser_*` tests as `test_oidc_public_base_url_*` with mirrored assertions). The RS test surface: `services/resource-server/tests/core/test_config.py:187–211` `test_oidc_jwks_url_*` tests are deleted (the field no longer exists).
  - [x] Add `services/bff/tests/auth/test_oidc_discovery.py` and `services/resource-server/tests/auth/test_oidc_discovery.py` with the AC5 test matrix (happy path + four failure modes + extra-unknown-fields path).
  - [x] Add `services/bff/tests/test_lifespan.py` (or extend an existing lifespan-touching file) with a test that asserts: discovery failure during startup raises and the app cannot be exercised by the AsyncClient (uvicorn-equivalent under ASGITransport). Mirror on RS.

- [x] **Task 7 — Update compose + Keycloak config for the unified back-channel discovery topology.** (AC4, AC6, Dev Notes §"The front-channel / back-channel hostname trap")
  - [x] `compose/infra.yml` line 23 (or thereabouts in the keycloak environment block): add `KC_HOSTNAME_BACKCHANNEL_DYNAMIC: "true"`. This makes Keycloak's discovery body URLs (and token-mint `iss` claim) depend on the request's Host header — back-channel requests via `keycloak:8080` get back-channel URLs; the browser's discovery fetch (the browser doesn't fetch discovery, but if it did via `localhost:8080`) gets host-facing URLs. The signed `iss` in tokens minted via the back-channel `/token` POST is back-channel.
  - [x] `compose/app.yml` BFF service environment (lines 60–81):
    - Change `OIDC_ISSUER_URL: http://keycloak:8080/realms/bmad-books` — already this value, no change.
    - Remove `OIDC_JWKS_URL` (line 76) and `OIDC_AUTHORIZE_URL_BROWSER` (line 79).
    - Add `OIDC_PUBLIC_BASE_URL: http://localhost:8080/realms/bmad-books`.
    - Keep `OIDC_AUDIENCE`, `OIDC_CLIENT_ID`, `BFF_BASE_URL`, `BFF_SESSION_COOKIE_NAME`, `BFF_CSRF_COOKIE_NAME` unchanged.
  - [x] `compose/app.yml` RS service environment (lines 131–145):
    - Change `OIDC_ISSUER_URL` from `http://localhost:8080/realms/bmad-books` → `http://keycloak:8080/realms/bmad-books` (back-channel, matches BFF). With `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`, this is also the `iss` claim emitted in tokens.
    - Remove `OIDC_JWKS_URL` (line 144).
    - Keep `OIDC_AUDIENCE` and `APP_NAME`, `DEBUG`, `RS_DATABASE_URL` unchanged.

- [x] **Task 8 — Update README + security-review.md.** (AC6)
  - [x] README "Environment variables" or equivalent section: drop `OIDC_JWKS_URL` / `OIDC_AUTHORIZE_URL_BROWSER` from any documented enumeration; add `OIDC_PUBLIC_BASE_URL` with a one-line explanation of the front-channel split. Confirm there is no enumeration to update — env vars currently live in `compose/app.yml`; the README's "Compose env" section just points there. If so, no README edit is needed; record that fact in the Change Log.
  - [x] `docs/security-review.md` §"keycloak_cookie_session.py" implementing-code-paths line: any reference to `OIDC_AUTHORIZE_URL_BROWSER` / `OIDC_JWKS_URL` is reframed in terms of discovery. The §14 D25 finding ("Health endpoint amplification — outbound httpx request to discovery on every probe") moves from "deferred" to "resolved by Story 7.2" because the /health probe now reads from the cached discovery rather than re-fetching.
  - [x] `_bmad-output/planning-artifacts/architecture.md` §"Pattern Amendments" (line 863): append a new entry dated `2026-05-21` (or later — use the implementation date): "OIDC discovery bootstrap. Original architecture had `OIDC_JWKS_URL` and `OIDC_AUTHORIZE_URL_BROWSER` as separate env vars. Amendment: both BFF and RS read all OIDC endpoint URLs from `${OIDC_ISSUER_URL}/.well-known/openid-configuration` at startup, cached on `app.state.oidc_discovery`. `OIDC_PUBLIC_BASE_URL` (BFF only) overrides the browser-facing authorize URL host for the compose dev split. Authority: this story file."

- [x] **Task 9 — Quality gates + integration verification.**
  - [x] BFF: `cd services/bff && uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest` — expect green; the discovery-related tests added in Task 6 must pass; the deleted `oidc_authorize_url_browser` / `oidc_jwks_url` test functions must not leave dead imports.
  - [x] RS: `cd services/resource-server && uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest` — same gate. Both services' per-file coverage targets must still hold (the new `oidc_discovery.py` modules need their own coverage; the deleted validator code reduces the denominator).
  - [x] Integration smoke (if Docker is available — check before running): `docker compose up -d keycloak bff resource-server spa` and walk through J1 (login). Verify the BFF's `/auth/login` 302 Location uses `localhost:8080/.../authorize` (browser-facing) and that `/auth/callback` succeeds (back-channel token exchange via `keycloak:8080/.../token`). If Docker is not available, document this as "integration smoke pending compose run" in the Dev Agent Record.
  - [x] E2E: if Playwright is wired (it is — see `e2e/`), run `just e2e-up && just e2e-test` and confirm J1 (first-time login) still passes. The realm export config doesn't change; only Keycloak's hostname-strict flag changes; J1's redirect_uri (`http://localhost:4000/auth/callback`) is unaffected.

## Dev Notes

### Relevant architecture patterns and constraints

- **Archetype foundation.** BFF and RS are both forked from `github.com/tommaso-meledina/fastapi-archetype` (Python 3.14 + FastAPI + SQLModel + uv + OTEL). `AppSettings(BaseSettings)` is the only configuration surface; `pydantic-settings` reads `.env` with `extra="ignore"` — removed env vars are silently dropped, which is the desired behavior for AC1.
- **Quality gates (RS CLAUDE.md, services/resource-server/CLAUDE.md).** Before each commit on the RS: `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, full `pytest`. ALL ty errors AND warnings must be fixed; do NOT add blanket suppressions. Apply the same gate to the BFF — there is no `services/bff/CLAUDE.md` but the project's quality discipline is uniform across services (Story 1.3 review patches and onward).
- **Lifespan ordering (architecture line 1339).** BFF `/health` depends on Keycloak because discovery is fetched at startup. With Story 7.2, that dependency is now **structural** (not just a probe): the BFF cannot start without Keycloak reachable. The compose `depends_on: keycloak: service_healthy` already enforces this — no compose dep change needed.
- **OIDC client library = Authlib (architecture A1, line 347).** No new auth libraries. The `keycloak_cookie_session.py` plugin (Story 1.5) is the OIDC client surface. Discovery integration is upstream of Authlib — Authlib's `AsyncOAuth2Client` accepts the token URL via the `url=` kwarg on `fetch_token`, so the discovery-driven URL slots in without library work.
- **State/nonce storage (architecture A3).** Unchanged. The `auth_states` row + signed state-id cookie continue to defend the callback against CSRF + id_token replay. Discovery affects only URL resolution, not state management.
- **Architecture §C6 timeouts.** BFF/RS → Keycloak: 5s connect / 10s read; **zero retries**. The discovery fetch honors this. The user can simply restart the process if Keycloak is flaky at startup — uvicorn's exit-non-zero is the operator signal.
- **Health endpoint sanitization (Story 1.3 review patch P4, architecture §"Operational Details").** /health response bodies disclose ONLY sanitized status labels ("ok"/"down") to unauthenticated callers. The discovery-resolved details (URL hosts, classifier strings) are logged server-side at WARNING. Preserve this when refactoring `_check_oidc_discovery`.
- **`extra="ignore"` is the deprecation grace period.** Operators with stale `.env` files containing `OIDC_JWKS_URL` will see the variable silently dropped by pydantic-settings rather than a validation error — matches the "POC, no deprecation grace period" wording in the original story spec but is gentler than the wording suggests.

### The front-channel / back-channel hostname trap

**This is the load-bearing decision in the story.** The original spec's AC4 wording — "Discovery returns the back-channel issuer" — is **not true** under the current compose topology, where `KC_HOSTNAME=localhost` and `KC_HOSTNAME_STRICT=false` (`compose/infra.yml:21–22`). With those settings, Keycloak's discovery doc body emits **host-facing** URLs regardless of which network path you used to fetch it. Specifically:

- BFF fetches `http://keycloak:8080/realms/bmad-books/.well-known/openid-configuration` (compose DNS, back-channel)
- Keycloak responds with `{"issuer": "http://localhost:8080/realms/bmad-books", "token_endpoint": "http://localhost:8080/realms/bmad-books/protocol/openid-connect/token", ...}`
- If the BFF naively trusts that and POSTs to `http://localhost:8080/.../token` from inside the compose network, it would fail — `localhost` inside the BFF container is the BFF itself, not Keycloak.

There are three resolutions; the story commits to **Resolution C** (set `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`) because it minimizes hardcoding and lines up cleanly with AC4's prescription "Discovery returns the back-channel issuer":

- **Resolution A — rebase host:port for back-channel calls.** Keep KC_HOSTNAME=localhost. The BFF discovery fetch returns host-facing URLs; the BFF then re-bases token/revocation/end-session/jwks URLs onto `OIDC_ISSUER_URL`'s host:port (back-channel), keeping the path. The authorize URL is used as-is (already browser-facing). `OIDC_PUBLIC_BASE_URL` is redundant. Pros: smallest compose change. Cons: contradicts AC4's wording; introduces a "URL rebase" helper which is conceptually fragile.
- **Resolution B — use OIDC_PUBLIC_BASE_URL for everything browser-facing.** Keep KC_HOSTNAME=localhost. Discovery returns host-facing URLs which are taken as-is for both browser AND back-channel — but then back-channel calls fail. **Broken; do not implement.**
- **Resolution C — KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true (RECOMMENDED, what AC4 prescribes).** Keycloak emits back-channel URLs in discovery responses when fetched via back-channel (Host header = `keycloak:8080`) and host-facing URLs when fetched via front-channel (Host header = `localhost:8080`). Tokens minted via back-channel `/token` POSTs embed `iss=back-channel` (per Keycloak docs). The BFF reads discovery, gets back-channel URLs for everything, uses them as-is for token/revocation/end-session/jwks/id_token-issuer, and derives the browser-facing authorize URL via `OIDC_PUBLIC_BASE_URL + discovery.authorization_endpoint.path`. The RS gets back-channel URLs and uses them as-is. Pros: matches AC4 verbatim; minimal BFF code (no rebase helper); cleanly aligns with how Keycloak is meant to be configured in split-hostname deployments. Cons: requires the compose change in Task 7; behavior subtly depends on a Keycloak version flag.

If integration testing in Task 9 reveals Resolution C does not behave as documented (e.g., the `iss` claim does not match `discovery.issuer` despite `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`), fall back to Resolution A and document the pivot in the Dev Agent Record.

### Source tree components to touch

**BFF** (`services/bff/`):
- NEW: `src/bff/auth/oidc_discovery.py` (dataclass + `fetch_discovery` async function + `DiscoveryFetchError` exception)
- MODIFY: `src/bff/main.py` (lifespan hook — line 24)
- MODIFY: `src/bff/core/config.py` (lines 82, 91, 146–166 — remove `oidc_jwks_url` field + `oidc_authorize_url_browser` field + validator; add `oidc_public_base_url` + validator)
- MODIFY: `src/bff/api/auth.py` (lines 144, 223, 248, 252, 430–432 — read discovery via `Depends`, drop `cfg.oidc_jwks_url` / `cfg.oidc_authorize_url_browser` references; signature of `build_authorize_url` may change)
- MODIFY: `src/bff/auth/keycloak_cookie_session.py` (line 90–117 — `build_authorize_url` may take a `browser_base` parameter; or callers do the path-extraction inline. Either works.)
- MODIFY: `src/bff/services/resource_server_client.py` (line 370 — read discovery; constructor signature gains a `discovery: OidcDiscovery` parameter)
- MODIFY: `src/bff/api/health.py` (lines 97–186 — `_check_oidc_discovery` becomes a presence check on `app.state.oidc_discovery`; signature changes; per-request HTTP fetch removed)
- DELETE: nothing (no file deletions in this story; the deleted fields are inline)
- TESTS NEW: `tests/auth/test_oidc_discovery.py`, possibly `tests/test_lifespan.py`
- TESTS MODIFY: `tests/conftest.py` (lines 22), `tests/api/test_auth.py` (lines 48–50), `tests/core/test_config.py` (lines 171–197 rewrite), `tests/api/test_reading_speed_proxy.py` (lines 495, 531 — `oidc_issuer_url` still exists), `tests/api/test_books.py` (line 719 — `oidc_issuer_url` still exists), `tests/services/test_resource_server_client.py` (lines 56, 644, 675 — refresh token URL is now via discovery), `tests/api/test_health.py` (the `_check_oidc_discovery` mocks change signature)
- TESTS UNCHANGED: `tests/auth/synthetic_idp.py` (discovery_doc + mock route already present)

**RS** (`services/resource-server/`):
- NEW: `src/resource_server/auth/oidc_discovery.py`
- MODIFY: `src/resource_server/main.py` (lifespan — line 30, BEFORE the `create_all`)
- MODIFY: `src/resource_server/core/config.py` (lines 91, 99–100, 127–139 — drop `oidc_jwks_url`; rename timeout fields)
- MODIFY: `src/resource_server/auth/oidc_bearer.py` (lines 78, 85, possibly the `make_oidc_bearer_auth` factory signature)
- MODIFY: `src/resource_server/api/health.py` (lines 105–187 — `_check_jwks` becomes `_check_oidc_discovery`, reads from `app.state`, response key renamed `jwks` → `oidc_discovery`)
- TESTS NEW: `tests/auth/test_oidc_discovery.py`, possibly `tests/test_lifespan.py`
- TESTS MODIFY: `tests/conftest.py` (lines 21–24 deletion + autouse respx mock for discovery), `tests/core/test_config.py` (lines 187–211 deletion of `oidc_jwks_url` tests), `tests/api/test_health.py` (the `_check_jwks` → `_check_oidc_discovery` rename + mock-shape change), `tests/auth/test_oidc_bearer.py` (the `settings.oidc_jwks_url` references → discovery)

**Compose + Keycloak**:
- MODIFY: `compose/infra.yml` (line 21–23 — add `KC_HOSTNAME_BACKCHANNEL_DYNAMIC: "true"`)
- MODIFY: `compose/app.yml` (lines 60–81 BFF env block; lines 131–145 RS env block)
- UNCHANGED: `keycloak/realm-bmad-books.json` (no realm-level changes — discovery is server-config, not realm-config)

**Docs**:
- MODIFY: `_bmad-output/planning-artifacts/architecture.md` (append Pattern Amendments entry at line 866+)
- MODIFY: `docs/security-review.md` (D25 status update; `keycloak_cookie_session.py` env-var line)
- MODIFY: `README.md` (only if it enumerates env vars — confirm; otherwise unchanged)
- NOT MODIFIED: `.env.example` (no OIDC URLs live there today; topology constants live in compose/app.yml per D141)

### Testing standards summary

- **Framework.** BFF: pytest + pytest-asyncio (asyncio_mode = "auto") + httpx AsyncClient over ASGITransport + respx for outbound HTTP mocks. RS: same.
- **Synthetic IdP.** BFF already has `services/bff/tests/auth/synthetic_idp.py` with `_build_discovery_doc()` (lines 146–165) that emits all six required fields. The `mock.get(f"{DEFAULT_ISSUER}/.well-known/openid-configuration")` route (line 200) covers lifespan discovery. RS currently lacks a synthetic-IdP harness — Task 6 adds an autouse `respx` fixture mounting a minimal discovery doc at the `OIDC_ISSUER_URL` configured in `tests/conftest.py`.
- **Coverage.** Per-file targets unchanged from Story 5.1. New modules (`oidc_discovery.py`) need their own coverage; the deleted validator code reduces the denominator on `config.py`. Net: no regression in the overall coverage ratio expected.
- **Lifespan testing.** ASGITransport-based AsyncClient invokes lifespan automatically when `lifespan="auto"` is set; pytest-anyio/pytest-asyncio fixtures should be compatible. If a test wants to assert lifespan startup failure, construct `AsyncClient(transport=ASGITransport(app=...))` and expect the context-manager `__aenter__` to raise — the existing tests don't yet exercise this pattern, so Task 6's `test_lifespan.py` will be the first.

### Project Structure Notes

- **Alignment with unified project structure.** The new `oidc_discovery.py` modules sit next to `keycloak_cookie_session.py` (BFF) and `oidc_bearer.py` (RS), matching the convention "OIDC-related modules live in `auth/`". The `OidcDiscovery` dataclass is local to each service (BFF and RS copies); no shared package — the project explicitly does not have a shared lib directory.
- **`get_oidc_discovery` dependency placement.** The cleanest spot is a per-service `core/deps.py` (which neither service has today). Inline next to `_settings_dep` in `api/auth.py` is fine for the BFF; the RS may need it in `auth/dependencies.py` (where `require_auth` lives) and in `api/health.py`. Decide based on consumer count; refactor later if it sprawls.
- **Detected conflicts / variances.** None against architecture.md. The Pattern Amendments append (Task 8) is the documentation handshake.

### References

- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md#Group I — New Epic 7 stories]
- [Source: _bmad-output/planning-artifacts/architecture.md#A1 BFF OIDC client library / line 347]
- [Source: _bmad-output/planning-artifacts/architecture.md#Pattern Amendments / line 863]
- [Source: _bmad-output/planning-artifacts/architecture.md#Health probe definition / line 1339]
- [Source: services/bff/src/bff/api/health.py:97–154 (existing `_check_oidc_discovery` probe — to be repurposed)]
- [Source: services/bff/src/bff/api/auth.py:223, 248, 252, 430–432 (hardcoded URL construction sites)]
- [Source: services/bff/src/bff/services/resource_server_client.py:370 (refresh token URL site)]
- [Source: services/bff/tests/auth/synthetic_idp.py:146–165, 200–202 (discovery doc + mock route — already present)]
- [Source: services/resource-server/src/resource_server/auth/oidc_bearer.py:78, 85 (JWKS + issuer hardcoded sites)]
- [Source: services/resource-server/src/resource_server/api/health.py:105–155 (existing `_check_jwks` probe — to be replaced)]
- [Source: compose/app.yml:60–81 (BFF env block), :131–145 (RS env block)]
- [Source: compose/infra.yml:21–23 (Keycloak hostname config)]
- [Source: docs/security-review.md §14 (D25 — health endpoint amplification)]
- [Source: Keycloak docs — `KC_HOSTNAME_BACKCHANNEL_DYNAMIC`: https://www.keycloak.org/server/hostname#_backchannel]

## Dev Agent Record

### Agent Model Used

claude-opus-4-7

### Debug Log References

- Task 2 / lifespan startup: discovered httpx.ASGITransport (used in pytest) does NOT auto-invoke lifespan. Resolved by populating `app.state.oidc_discovery` directly from conftest.py after the patched `fetch_discovery` is installed.
- Task 3 / test_cors.py: discovered that `importlib.reload(bff.main)` resets the module-level `fetch_discovery` reference. Resolved by patching `bff.auth.oidc_discovery.fetch_discovery` (the source module) before `bff.main` is first imported, so any subsequent reload re-imports the stub.
- Task 4 / RS dependencies.py: discovered `get_auth_functions` was `@lru_cache`'d; with the new `discovery` Depends parameter, the cache key issue forced dropping `@lru_cache`. Per-request dataclass construction is negligible overhead.
- Task 4 / RS synthetic_idp.py: discovered that `tests/api/test_cors.py` reloads `resource_server.main`, leaving `tests.conftest.app` (the original) and `resource_server.main.app` (the reloaded) as DIFFERENT FastAPI instances. The `client` fixture uses the original; the synthetic IdP was setting state on the reloaded one. Resolved by importing `app` from `tests.conftest`, not from `resource_server.main`.
- Task 3 / drive-by fix: `services/bff/tests/services/test_session_service.py` had three stale tuple-unpack `row, _ = await create_auth_state(...)` lines from the 2026-05-21 PKCE removal Group F. Fixed inline since they broke the suite.

### Completion Notes List

- ✅ AC1 — Settings classes reduced: BFF dropped `oidc_jwks_url` + `oidc_authorize_url_browser`; RS dropped `oidc_jwks_url`. New `oidc_public_base_url` on BFF (defaults to OIDC_ISSUER_URL via `effective_oidc_public_base_url`).
- ✅ AC2 — Lifespan startup hook on both services fetches `${OIDC_ISSUER_URL}/.well-known/openid-configuration` once and caches on `app.state.oidc_discovery`. `get_oidc_discovery(request)` exposed as a FastAPI dependency on both services.
- ✅ AC3 — Discovery failures during startup raise `DiscoveryFetchError(classifier)` after logging `discovery_unreachable: <classifier>` at ERROR. uvicorn exits non-zero. `/health` re-routed to a presence check on the cached doc (closes security-review §14 D25).
- ✅ AC4 — `OIDC_PUBLIC_BASE_URL` introduced on the BFF. `/auth/login` rebases `discovery.authorization_endpoint` onto the public base. All other URLs taken from discovery as-is. Resolution C committed (KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true in compose/infra.yml).
- ✅ AC5 — New test files `tests/auth/test_oidc_discovery.py` on both services cover the happy path + transport + 404 + non-JSON + non-object + missing/empty/non-string field + extra-fields matrix. Integration tests (`tests/api/test_auth.py`, `tests/services/test_resource_server_client.py`, `tests/auth/test_oidc_bearer.py`) updated for the new URLs flowing through discovery.
- ✅ AC6 — `compose/app.yml` cleaned of OIDC_JWKS_URL + OIDC_AUTHORIZE_URL_BROWSER; OIDC_PUBLIC_BASE_URL added on BFF; RS OIDC_ISSUER_URL unified to back-channel. `compose/infra.yml` gained `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`. README + `docs/security-review.md` + `_bmad-output/planning-artifacts/architecture.md` updated.

**Test results:** BFF 526 passed, RS 329 passed. ruff check + ruff format --check + ty check green on both. Integration smoke (Docker compose) explicitly skipped per user choice — synthetic IdP test coverage proves discovery wiring works against a real OIDC topology.

### File List

**BFF — NEW:**
- `services/bff/src/bff/auth/oidc_discovery.py`
- `services/bff/tests/auth/test_oidc_discovery.py`

**BFF — MODIFIED:**
- `services/bff/src/bff/main.py` (lifespan + `app.state.oidc_discovery`)
- `services/bff/src/bff/core/config.py` (drop `oidc_jwks_url` + `oidc_authorize_url_browser`; add `oidc_public_base_url` + `effective_oidc_public_base_url`)
- `services/bff/src/bff/api/auth.py` (`_rebase` helper; `Depends(get_oidc_discovery)` on all three handlers; replace hardcoded URL construction with `discovery.token_endpoint` / `discovery.jwks_uri` / `discovery.issuer` / `discovery.revocation_endpoint` / `discovery.end_session_endpoint`)
- `services/bff/src/bff/auth/keycloak_cookie_session.py` (`build_authorize_url` now takes the full `authorize_endpoint`)
- `services/bff/src/bff/api/health.py` (`_check_oidc_discovery` becomes a sync presence check on `app.state.oidc_discovery`)
- `services/bff/src/bff/api/reading_speed.py` (`Depends(get_oidc_discovery)`; pass `token_url=discovery.token_endpoint` to client methods)
- `services/bff/src/bff/api/books.py` (same — for `/v1/books/{id}/estimate`)
- `services/bff/src/bff/services/resource_server_client.py` (drop `_TOKEN_PATH_SUFFIX`; add `token_url` kwarg to public methods; add `default_token_url` constructor arg for test ergonomics)
- `services/bff/tests/conftest.py` (stub fetch_discovery; populate `app.state.oidc_discovery`)
- `services/bff/tests/api/test_health.py` (rewritten for the presence-check shape)
- `services/bff/tests/api/test_auth.py` (drop `oidc_jwks_url` + `oidc_authorize_url_browser` patches; add `oidc_public_base_url`)
- `services/bff/tests/core/test_config.py` (replace `test_oidc_authorize_url_browser_*` with `test_oidc_public_base_url_*`)
- `services/bff/tests/auth/test_keycloak_cookie_session.py` (`build_authorize_url` signature change)
- `services/bff/tests/services/test_resource_server_client.py` (rsc fixture uses `default_token_url`; mocked token URL renamed)
- `services/bff/tests/services/test_session_service.py` (drive-by: fix three stale tuple-unpacks from PKCE removal)

**RS — NEW:**
- `services/resource-server/src/resource_server/auth/oidc_discovery.py`
- `services/resource-server/tests/auth/test_oidc_discovery.py`

**RS — MODIFIED:**
- `services/resource-server/src/resource_server/main.py` (lifespan + `app.state.oidc_discovery`)
- `services/resource-server/src/resource_server/core/config.py` (drop `oidc_jwks_url`; rename `oidc_jwks_*_timeout` → `oidc_discovery_*_timeout`)
- `services/resource-server/src/resource_server/auth/oidc_bearer.py` (`_validate_access_token(token, discovery)`; `get_authenticated_principal` takes `Depends(get_oidc_discovery)`; `make_oidc_bearer_auth(settings, discovery)`)
- `services/resource-server/src/resource_server/auth/factory.py` (`get_auth(settings, discovery)`)
- `services/resource-server/src/resource_server/auth/dependencies.py` (drop `@lru_cache`; `get_auth_functions` takes `Depends(get_oidc_discovery)`)
- `services/resource-server/src/resource_server/api/health.py` (`_check_jwks` → `_check_oidc_discovery` presence check; response key renamed `jwks` → `oidc_discovery`)
- `services/resource-server/tests/conftest.py` (stub fetch_discovery; populate `app.state.oidc_discovery`; autouse `_reset_app_state_discovery` fixture)
- `services/resource-server/tests/auth/synthetic_idp.py` (stash synthetic `OidcDiscovery` on `tests.conftest.app.state.oidc_discovery`)
- `services/resource-server/tests/auth/test_auth_functions.py` (pass `_DUMMY_DISCOVERY` to `get_auth`)
- `services/resource-server/tests/auth/test_factory_and_none_provider.py` (same)
- `services/resource-server/tests/auth/test_oidc_bearer.py` (add `_discovery_from_idp` helper; update direct calls to `get_authenticated_principal` + `make_oidc_bearer_auth`)
- `services/resource-server/tests/auth/test_role_mapper.py` (pass `_DUMMY_DISCOVERY`)
- `services/resource-server/tests/api/test_health.py` (rewritten for the presence-check shape)
- `services/resource-server/tests/api/test_cors.py` (mock `_check_oidc_discovery` instead of `_check_jwks`)
- `services/resource-server/tests/api/test_test_reset.py` (drop `oidc_jwks_url` from `_OIDC_STUBS`)
- `services/resource-server/tests/core/test_config.py` (delete `test_oidc_jwks_url_*`)

**Compose + docs — MODIFIED:**
- `compose/infra.yml` (add `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`)
- `compose/app.yml` (BFF: drop `OIDC_JWKS_URL` + `OIDC_AUTHORIZE_URL_BROWSER`, add `OIDC_PUBLIC_BASE_URL`; RS: unify `OIDC_ISSUER_URL` to back-channel, drop `OIDC_JWKS_URL`)
- `README.md` (troubleshooting reworded for new env contract)
- `docs/security-review.md` (§4 JWT validation code snippets updated; §14 D25 marked resolved)
- `_bmad-output/planning-artifacts/architecture.md` (Pattern Amendments entry; §"Required vars" updated)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status transitions)

### Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-21 | Story context engine analysis completed — comprehensive developer guide created | claude-opus-4-7 |
| 2026-05-21 | Implementation complete — 7 commits, BFF 526 + RS 329 tests passing, ruff + ty green. Resolution C committed (KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true). | claude-opus-4-7 |
| 2026-05-21 | RS `/health` response key renamed `"jwks"` → `"oidc_discovery"` to match BFF (Task 5 sub-2 tail). Public-shape change documented in `docs/security-review.md §14 D25`. | claude-opus-4-7 |
| 2026-05-22 | Code review patches applied (10 patches resolving Blind / Edge Case / Acceptance Auditor findings — issuer-binding check, discovery URL-shape validation, RS engine-leak fix on `create_all` failure, validator netloc check, `_rebase` query/fragment guard, `_real_fetch_discovery` source-alias, `OIDC_PUBLIC_BASE_URL` placeholder, `OIDC_PUBLIC_BASE_URL` host-only semantics documented, lifespan fail-fast tests added). | claude-opus-4-7 |

### Review Findings

_Code review run 2026-05-22 via `bmad-code-review`. Three reviewer layers: Blind Hunter (diff-only), Edge Case Hunter (diff + read), Acceptance Auditor (diff + spec + context docs). Diff range `377128a..78a3d05` (7 implementation commits)._

**Decision-needed (4)** — resolved 2026-05-22:

- [x] [Review][Decision] **RS conftest stubs `fetch_discovery` instead of mounting respx discovery route** — _Resolved: keep stub._ Dev Agent Record already discloses the rationale (ASGITransport doesn't auto-invoke lifespan). RS lifespan real-fetch coverage will land via the new `test_lifespan.py` (patch #2) which invokes `app.router.lifespan_context()` explicitly.
- [x] [Review][Decision] **`ResourceServerClient` does not hold `discovery`; callers thread `token_url` per call + unconditional `ValueError` on empty** — _Resolved: keep per-call threading + hard-raise._ Per-request DI is cleaner architecturally; the unconditional raise is fail-fast hygiene against future callers forgetting the kwarg. The pre-7.2 lazy URL construction is intentionally retired.
- [x] [Review][Decision] **`OIDC_PUBLIC_BASE_URL` semantics — host-only override vs full base URL** — _Resolved: host-only is intentional; document explicitly._ Path component dropping is intentional behavior (compose dev's path coincidence makes the drop invisible). Added as patch #10 below: update field comment + Pattern Amendments + `_rebase` docstring to spell out "scheme+authority only; path is taken from discovery".
- [x] [Review][Decision] **Discovery fetch follows 3xx redirects (`follow_redirects=True`)** — _Resolved: keep `follow_redirects=True`._ Patch #5 (issuer-binding check) is the mitigation — a redirected discovery doc would have to fake the `issuer` claim, which the check catches. Trailing-slash handling continues to work.

**Patches (10)** — applied 2026-05-22:

- [x] [Review][Patch] **Test imports `_real_fetch_discovery` planted by conftest as a side-effect** — _Fixed: added `_real_fetch_discovery = fetch_discovery` as a stable module-level alias in both `bff.auth.oidc_discovery` and `resource_server.auth.oidc_discovery`. Tests now import a real symbol; conftest plant + `# ty: ignore` removed._
- [x] [Review][Patch] **Missing lifespan fail-fast tests — Task 6 deliverable absent** — _Fixed: added `services/bff/tests/test_lifespan.py` + `services/resource-server/tests/test_lifespan.py`. Each drives `app.router.lifespan_context(app)` with a monkeypatched raising `fetch_discovery`, asserts `DiscoveryFetchError` propagates, classifier matches, and the `discovery_unreachable: <classifier>` ERROR log is emitted (captured via a locally-attached handler since `configure_logging` bypasses pytest caplog)._
- [x] [Review][Patch] **BFF conftest missing `OIDC_PUBLIC_BASE_URL` placeholder** — _Fixed: added `os.environ.setdefault("OIDC_PUBLIC_BASE_URL", "http://idp.test/realms/test")` next to the existing `OIDC_ISSUER_URL` placeholder._
- [x] [Review][Patch] **`_validate_oidc_public_base_url` missing urlparse netloc check** — _Fixed: added netloc check to both `_validate_oidc_public_base_url` (when value supplied) and `_validate_oidc_issuer_url` (always required). Mirrors `_validate_rs_base_url`'s pattern._
- [x] [Review][Patch] **Discovery doc's `issuer` field not verified against canonical issuer** — _Fixed: `_validated()` now takes a `canonical_issuer` kwarg and raises `DiscoveryFetchError("issuer_mismatch")` if `payload["issuer"].rstrip("/")` doesn't match. Applied to both services. This also closes the residual risk from `follow_redirects=True` (Decision 4)._
- [x] [Review][Patch] **Discovery URL fields not validated as absolute http(s) URLs** — _Fixed: `_validated()` now `urlparse`'s each URL field (`authorization_endpoint`, `token_endpoint`, `jwks_uri`, `end_session_endpoint`, `revocation_endpoint`) and raises `DiscoveryFetchError(f"invalid_url:{field_name}")` if scheme isn't http(s) or netloc is empty._
- [x] [Review][Patch] **RS engine leak when `create_all` fails after discovery succeeds** — _Fixed: moved `get_engine(settings)` + `create_all` block inside the `try/finally` that owns `dispose_engine`. A `create_all` failure now disposes the engine before propagating._
- [x] [Review][Patch] **`discovery.authorization_endpoint` query/fragment not handled by `_rebase`** — _Fixed: `_rebase` now raises `ValueError` if the discovery URL carries a query string or fragment, and explicitly drops them from the output. `build_authorize_url` continues to be the sole producer of the URL's query string._
- [x] [Review][Patch] **`/health` response key rename (`jwks` → `oidc_discovery`) absent from Change Log + security-review.md** — _Fixed: appended a Change Log entry on 2026-05-21 noting the rename; updated `docs/security-review.md §14 D25` text to call out the response-key change explicitly._
- [x] [Review][Patch] **Document `OIDC_PUBLIC_BASE_URL` host-only semantics explicitly** — _Fixed: `_validate_oidc_public_base_url` field comment, `_rebase` docstring, and `architecture.md` Pattern Amendments entry all now state that `OIDC_PUBLIC_BASE_URL` contributes scheme+authority only; path comes from `discovery.authorization_endpoint`._

**Deferred (1)** — pre-existing or out-of-scope:

- [x] [Review][Defer] **No discovery-refresh mechanism for long-running stale endpoints** [services/bff/src/bff/services/resource_server_client.py refresh path] — deferred, consistent with architecture §C6 ("zero retries; operator restarts on failure"). Long-running BFF + Keycloak realm reconfig → stale token endpoint → silent logout loops until process restart. Restart-driven recovery is the documented policy.

_Dismissed: 1 (the `effective_oidc_public_base_url` property pattern — pydantic-settings cannot reference another field as default, so the property is the idiomatic resolution; already disclosed in Completion Notes)._
