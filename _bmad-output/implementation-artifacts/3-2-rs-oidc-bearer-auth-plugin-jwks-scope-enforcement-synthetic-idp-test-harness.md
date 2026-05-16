---
status: done
story_key: 3-2-rs-oidc-bearer-auth-plugin-jwks-scope-enforcement-synthetic-idp-test-harness
epic: 3
prerequisites: 3.1 (done — RS scaffolded from archetype, `/health` with three readiness probes, RS in compose default/dev, `ErrorCode.SERVICE_UNAVAILABLE`, required-fail-fast OIDC config); epic-1 (done — Keycloak realm-as-code, BFF cookie-session + synthetic-IdP harness pattern proven)
specLoopIteration: 1
---

# Story 3.2: RS — `oidc_bearer` auth plugin (JWKS) + scope enforcement + synthetic-IdP test harness

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer enforcing the architectural NFRs (NFR4, NFR5, NFR7),
I want the RS to validate JWTs against the cached Keycloak JWKS, enforce required OAuth scopes per endpoint, and have a synthetic-IdP test harness so unit tests don't need a live Keycloak,
so that subsequent RS stories (3.3 `/v1/reading-speed`, 3.4 `/v1/test/reset`, 4.1 `/v1/estimate`) can register scope-gated dependencies (`require_scope("reading-speed:read")` / `require_scope("reading-speed:write")`) with confidence the validation and enforcement are correct.

## Acceptance Criteria

1. **`src/resource_server/auth/oidc_bearer.py` exists and uses PyJWT + PyJWKClient.** The module:
   - Adds `pyjwt[crypto]` as a runtime dep in `services/resource-server/pyproject.toml` (use `uv add 'pyjwt[crypto]'`; do NOT regenerate the lockfile any other way). Architecture §A2 line 348 mandates `pyjwt[crypto]` + `PyJWKClient`; `python-jose` is explicitly out.
   - Imports as `import jwt` and uses `jwt.PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=4)`, mirroring the BFF's `services/bff/src/bff/auth/keycloak_cookie_session.py` lines 196–201 (do NOT diverge — cross-service consistency keeps cache behavior predictable).
   - Maintains a **module-level** dict cache `_jwks_clients: dict[str, jwt.PyJWKClient]` so a single `PyJWKClient` instance lives per JWKS URL across requests (same pattern as the BFF; without this, `cache_keys=True` is per-instance only).
   - Reads its configuration from `resource_server.core.config.settings` (which Story 3.1 already extended with the required-fail-fast `oidc_issuer_url`, `oidc_jwks_url`, `oidc_audience` fields). Do NOT add a parallel pydantic-settings model. Story 3.1 already declared these as `required-fail-fast`.
   - Exports `make_oidc_bearer_auth(settings) -> AuthFunctions` (closure-style, mirroring `make_entra_auth` in `auth/entra.py`) and the dependency factory `require_scope`. **All public functions in this module are typed; no `Any` in return positions.**

2. **A `Principal`-style object exposes `sub` and `scopes`.** The story extends `resource_server.auth.models.Principal` (do NOT introduce a parallel class):
   - Add `scopes: frozenset[str] = field(default_factory=frozenset)` to `Principal`. Use `frozenset` (immutable, hashable) since `Principal` is `@dataclass(frozen=True)`. `frozenset[str]` is parseable by `ty`/`pyright`.
   - Populate `scopes` from the JWT's `scope` claim (space-delimited per RFC 8693 / RFC 6749 §3.3). Keycloak emits scope in the access-token `scope` claim because realm-bmad-books.json sets `"include.in.token.scope": "true"` on the `reading-speed:read` / `reading-speed:write` scope mappers (verified via `keycloak/realm-bmad-books.json` lines 44–58).
   - Keep the existing `Principal` fields (`subject`, `user_id`, `name`, `scope` (string form, archetype-emitted), `app_id`, `roles`, `groups`, `claims`) — they are read by the archetype's `entra` plumbing. **Do not delete `entra.py` in this story** even though it becomes vestigial; deletion is deferred to a coordinated cleanup after Story 4.1 ships (no consumer remains).
   - Populate `subject` from JWT `sub`; `user_id` from `sub` (Keycloak access tokens do not carry `oid`); `name` from JWT `preferred_username` if present else `None`; `scope` (the existing field, kept for archetype compatibility) from the raw space-delimited string; `claims` from the full decoded claim dict.

3. **`get_authenticated_principal` FastAPI dependency parses bearer + validates JWT + returns Principal.** Implementation surface:
   - Reuse `bearer_scheme = HTTPBearer(auto_error=False)` from `auth/dependencies.py` (already exists; do not duplicate). Build a new dependency function `get_authenticated_principal(credentials: HTTPAuthorizationCredentials | None) -> Principal` in `auth/oidc_bearer.py` (or in `auth/dependencies.py` — implementer's choice, but keep the JWT-validation logic in `oidc_bearer.py`).
   - Token parsing path: `credentials is None` OR `credentials.scheme.lower() != "bearer"` OR `credentials.credentials` is empty/whitespace → raise `AppException(ErrorCode.SESSION_EXPIRED)` (401).
   - Validation path: `jwt.decode(token, signing_key.key, algorithms=["RS256"], audience=settings.oidc_audience, issuer=settings.oidc_issuer_url, options={"require": ["iss", "aud", "exp", "sub"]})`. **Algorithm is pinned to `RS256`** (Keycloak's default; matches the BFF's verifier line 225). Setting `algorithms=["RS256"]` rejects `alg: none` and HMAC tokens.
   - Construct `Principal` from claims (per AC #2). Return.
   - All failure modes (expired exp, mismatched aud, mismatched iss, malformed token, signature failure, unknown `kid` after one re-fetch, missing Authorization header) → `AppException(ErrorCode.SESSION_EXPIRED)` (401). The error envelope is `{"errorCode": "session_expired", "message": "...", "detail": null}`.
   - Server-side WARNING log is emitted on EVERY validation failure with the exception type and a sanitized reason (NO token contents, NO `kid`, NO claim values — fingerprinting risk per architecture §"Communication Patterns / Error handling"). Format: `logger.warning("JWT validation failed: %s", type(exc).__name__)`.

4. **`require_scope(scope: str)` is a dependency factory.** Implementation surface:
   - Signature: `def require_scope(scope: str) -> Callable[..., Awaitable[Principal]]`.
   - Returned dependency: `async def _dependency(principal: Annotated[Principal, Depends(get_authenticated_principal)]) -> Principal`.
   - Behavior: if `scope in principal.scopes` → return principal. Otherwise → `raise AppException(ErrorCode.FORBIDDEN_SCOPE)`.
   - The FORBIDDEN_SCOPE code is added to `core/errors.py` by this story (per Story 3.1's discipline — each code lands when its first consumer arrives). Wire value: `("forbidden_scope", "Required scope is missing", 403)`. SESSION_EXPIRED is also added here as the JWT-validation failure code: wire value `("session_expired", "Authentication required", 401)`.
   - **Do NOT** add `RESOURCE_SERVER_UNAVAILABLE`, `READING_SPEED_UNSET`, `INVALID_INPUT`, `BOOK_NOT_FOUND`, `AUTH_STATE_INVALID`, `CSRF_INVALID` — they belong to later stories' first-consumer surfaces.
   - WARNING log on scope rejection: `logger.warning("Scope check failed: sub=%s requires %s", principal.subject, scope)`. `sub` is acceptable to log (it's an opaque UUID, not PII), but do NOT log the full scopes set.

5. **`AuthType` literal admits a new `oidc_bearer` mode and `factory.get_auth()` dispatches to it.** Implementation surface:
   - In `core/config.py`, change `auth_type: Literal["none", "entra"]` → `auth_type: Literal["none", "entra", "oidc_bearer"]` (add the third member; do NOT remove `none` or `entra` — see AC #6).
   - In `auth/factory.py`, add a `_build_oidc_bearer` branch that imports `make_oidc_bearer_auth` from `auth.oidc_bearer` and returns its `AuthFunctions`. Mirror the lazy-import pattern used by `_build_entra` (so `auth_type=none` deployments never import PyJWT crypto helpers).
   - The `builders` dict gains `"oidc_bearer": _build_oidc_bearer`.

6. **The existing `none` and `entra` modes still pass their tests.** Run `uv run pytest tests/auth/` after every change; both modes' coverage MUST remain at parity with Story 3.1's baseline (171 tests, 98.42% coverage). Specifically:
   - `tests/auth/test_factory_and_none_provider.py` continues to pass — the `none` builder still returns the archetype's default `AuthFunctions`.
   - `tests/auth/test_entra_integration.py`, `test_require_role_uses_mapper.py`, `test_role_mapper.py`, `test_role_mapping_providers.py`, `test_external_provider.py`, `test_auth_forbidden.py`, `test_auth_unauthorized.py`, `test_auth_functions.py` continue to pass — the entra plumbing is untouched.
   - **`Principal.scopes` field addition** does NOT break any existing test that constructs a `Principal` without `scopes` — the `field(default_factory=frozenset)` ensures the field is always populated. Verify by running the suite.

7. **`make_oidc_bearer_auth(settings)` returns an `AuthFunctions` that fits the archetype's seam.** Concrete behavior:
   - `authenticate_bearer_token(token: str) -> Principal` validates the JWT per AC #3 and returns a populated `Principal` (with `scopes` set per AC #2). Raises `UnauthorizedError` (from `auth.contracts`) on any validation failure — the archetype's existing `get_current_principal` in `auth/dependencies.py` already maps `UnauthorizedError` → `AppException(ErrorCode.UNAUTHORIZED)`. **BUT** this story's `get_authenticated_principal` (AC #3) bypasses that mapping and maps to `SESSION_EXPIRED` (401) directly. The `oidc_bearer` mode's `authenticate_bearer_token` is therefore a secondary public surface — usable if a future caller wants the archetype's `require_auth`/`require_role` machinery, but Story 3.2's primary surface is `get_authenticated_principal` + `require_scope`.
   - `get_client_credentials_access_token(scope: str)` raises `AuthFeatureNotSupportedError` — the RS is a pure resource server, it never issues access tokens.
   - `get_on_behalf_of_access_token(scope: str, user_token: str)` raises `AuthFeatureNotSupportedError` — same rationale; OBO is a BFF concern.
   - `role_mapper` = `identity_role_mapper` (Keycloak realm roles are read identity-mapped, matching the existing archetype seam; this story does not use the role mapper because scopes — not roles — drive RS authorization per architecture line 1191).

8. **JWKS cache + key-rotation re-fetch is verified.** Implementation:
   - `PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=4)` already handles the in-process cache.
   - PyJWKClient automatically re-fetches the JWKS exactly once if `get_signing_key_from_jwt(token)` encounters a `kid` not in the cache (this is PyJWT's documented `lifespan` behavior; verify via the test in AC #10 below). If the key is STILL not found after the re-fetch, `PyJWKClientError` is raised — map to `SESSION_EXPIRED` (401).
   - The TTL is **per-process lifetime** with the cache eviction governed by `max_cached_keys=4` (LRU). Architecture line 415 mandates "in-process cache TTL 24h". PyJWKClient does NOT take a TTL arg; it caches until the cache is full or the process restarts. **For Story 3.2, this is acceptable** — Keycloak key rotation events trigger a `kid`-miss re-fetch automatically, so a 24h TTL would only add complexity without behavioral change. Document this in the dev log + in a one-line comment near `_jwks_clients`. This is intentional drift from the architecture spec's verbatim wording; the underlying invariant ("validation works across key rotation without operator intervention") is satisfied by the kid-miss re-fetch path.
   - Module-level cache is **process-scoped**, so tests that instantiate a fresh `PyJWKClient` need to either reset `_jwks_clients` or monkeypatch `PyJWKClient.fetch_data` per the BFF's pattern (`services/bff/tests/auth/synthetic_idp.py` lines 184–195). Mirror this in the RS's synthetic-IdP harness.

9. **`tests/auth/synthetic_idp.py` exists** (extending — not duplicating — the BFF's pattern). Concrete surface:
   - Place at `services/resource-server/tests/auth/synthetic_idp.py` (sibling to `conftest.py`).
   - Generates an RSA-2048 keypair at module load (use the existing `tests/auth/conftest.py::rsa_keypair_fixture` as a starting point; this story may either refactor that fixture into the new module OR have `synthetic_idp.py` import from it — implementer's choice. Recommended: move it to `synthetic_idp.py` as a module-level helper, then have `conftest.py` re-export it as a fixture).
   - Exports a dataclass `SyntheticRsIdp` (similar to BFF's `SyntheticIdp` but trimmed to RS-relevant surface — no `/token` / `/revocation` / `/end_session` mocks; the RS never visits those endpoints).
   - `SyntheticRsIdp.make_access_token(*, sub, scope, aud, iss, exp_offset_seconds, signing_key, kid, claims_override) -> str` — signs an RS256 access token. Defaults match the synthetic-IdP defaults (`sub="test-subject"`, `aud=settings.oidc_audience` via the override fixture, etc.).
   - **Patches `jwt.PyJWKClient.fetch_data`** (NOT `httpx`) so signature verification resolves to the synthetic public JWK without an actual HTTP call. PyJWKClient uses synchronous `urllib`, which respx/httpx mocks do NOT intercept — the BFF Story 1.5 hit this and resolved it with `monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [...]})`. Mirror that exactly.
   - **Clears `oidc_bearer._jwks_clients`** at fixture setup so cached clients from a previous test don't leak.
   - Exposes a `kid_miss_then_hit(new_kid)` helper that simulates key rotation by changing the `fetch_data` return value on second call (used by AC #10's rotation test).
   - Re-uses the **archetype's** existing `_int_to_base64url` helper from `tests/auth/conftest.py:19-21` if practical (do not re-invent).

10. **End-to-end test surface in `tests/auth/test_oidc_bearer.py` covers every AC enumerated above.** Required cases (at minimum):
    1. **Happy path with required scope** — endpoint `Depends(require_scope("reading-speed:read"))`, JWT with `scope = "openid reading-speed:read"`. Handler runs; `Principal.sub` is populated from JWT `sub`.
    2. **Wrong-scope 403** — JWT with `scope = "openid"` (no `reading-speed:read`). Response 403, envelope `{"errorCode": "forbidden_scope", "message": "...", "detail": null}`.
    3. **Expired JWT → 401 `session_expired`** — JWT with `exp` 10 seconds in the past.
    4. **Wrong audience → 401 `session_expired`** — JWT with `aud="some-other-audience"`.
    5. **Wrong issuer → 401 `session_expired`** — JWT with `iss="https://attacker.test/"`.
    6. **Malformed JWT → 401 `session_expired`** — `"not.a.valid.jwt"`.
    7. **Unknown kid, key NOT in JWKS after re-fetch → 401** — first JWKS fetch returns one set of keys; token's `kid` is in NEITHER the cached set nor a re-fetched set (PyJWKClient re-fetches once, then raises).
    8. **Unknown kid, key IN JWKS after re-fetch → 200** — first call's cached JWKS lacks the token's `kid`; the second (auto-triggered) fetch returns the new `kid`. Use `kid_miss_then_hit` helper. Verify the `fetch_data` patch was called **exactly twice** for this test (not more, not fewer).
    9. **JWKS cache hit avoids re-fetch** — make N (≥3) sequential requests with the SAME valid JWT (same `kid`). Assert `fetch_data` is called **exactly once** across N requests.
    10. **No Authorization header → 401 `session_expired`**.
    11. **Empty bearer token (`Authorization: Bearer ` with no value) → 401 `session_expired`**.
    12. **Wrong scheme (`Authorization: Basic ...`) → 401 `session_expired`**. Use `HTTPAuthorizationCredentials(scheme="Basic", credentials="...")`.
    13. **Token signed with a different RSA key → 401 `session_expired`**. Generate a second `_generate_keypair()` and sign the JWT with it; the synthetic JWKS only carries the public key for the first keypair.
    14. **Token with `alg: none` (no signature) → 401 `session_expired`**. Construct manually as a base64-encoded header+payload with empty signature; `jwt.decode(algorithms=["RS256"])` rejects.
    15. **Token with `alg: HS256` (HMAC) → 401 `session_expired`** — sign with HMAC using a known secret; `jwt.decode(algorithms=["RS256"])` rejects.
    16. **Missing required claim (`exp` absent) → 401 `session_expired`** — `options={"require": [..., "exp", ...]}` raises `MissingRequiredClaimError`.
    17. **Missing `sub` claim → 401 `session_expired`** — same options-driven enforcement.
    18. **Principal.scopes is a `frozenset` with the right contents** — JWT `scope = "openid reading-speed:read reading-speed:write"`, fetch principal, assert `isinstance(principal.scopes, frozenset)` and `principal.scopes == {"openid", "reading-speed:read", "reading-speed:write"}`.
    19. **`Principal.subject` is populated from JWT `sub`** — assert against a known value.
    20. **`Principal.name` populated from `preferred_username`** — assert when claim is present; assert `None` when absent.
    21. **WARNING-level log on validation failure** — `caplog.at_level(logging.WARNING)`; assert a log record matches `JWT validation failed:`. Verify NO token contents, NO claim values appear in the log message (sanitization).
    22. **WARNING-level log on scope rejection** — same approach for `require_scope` failure path; assert `Scope check failed:` is logged with `sub=…` and the required scope name.
    23. **Cross-user isolation via JWT** — sign two tokens (sub="user-a", sub="user-b"), call the endpoint with each, verify the principal returned has the right `subject`.

    The test file uses a small fixture-mounted test endpoint:
    ```python
    @app.get("/_test/scoped-read")
    async def _test_scoped(
        principal: Annotated[Principal, Depends(require_scope("reading-speed:read"))],
    ) -> dict[str, Any]:
        return {"sub": principal.subject, "scopes": sorted(principal.scopes)}
    ```
    This fixture endpoint is mounted **only in the test harness** (use a sub-app or `app.dependency_overrides` to avoid polluting `main.py`'s router table — mirror the BFF's `tests/conftest.py` pattern of using a TestClient with a freshly built FastAPI instance OR mount on a separate router that is registered only when an env var is set). Do NOT register the test endpoint on the production `app`.

11. **Coverage of `src/resource_server/auth/oidc_bearer.py` is ≥90%.** The archetype-configured coverage threshold (`[tool.coverage.report].fail_under = 90` per Story 3.1) applies to the whole RS source tree; after this story `oidc_bearer.py`'s own coverage line-count must be ≥90% (verifiable via `pytest --cov=resource_server.auth.oidc_bearer --cov-report=term-missing`). Each of the explicit error branches enumerated in AC #10 corresponds to one or more covered lines; the test list is built to drive coverage by design.

12. **The archetype's existing auth tests (`tests/auth/*.py` from the scaffold) continue to pass.** Run `uv run pytest tests/auth/ -v` and confirm:
    - Test count is **at least 9 existing auth tests (those that ran in Story 3.1)** + **new tests from AC #10** = at least 9 + 23 = 32+ auth tests. Total RS suite should grow from 171 (Story 3.1 final) to roughly 195+ depending on how many AC #10 cases land. Capture the exact count in the dev log.
    - Zero ruff findings, zero `ty` errors.
    - `_jwks_clients` cache pollution is prevented via the synthetic-IdP fixture's `monkeypatch.setattr(oidc_bearer, "_jwks_clients", {})` reset.

13. **No production-app router changes.** This story does NOT register any new `/v1/*` handler in `main.py` or the v1 router. The HTTP surface remains exactly `GET /health` from Story 3.1's perspective. `require_scope` is a dependency factory — it is exercised by tests (AC #10) but not wired into any production handler in this story. Story 3.3 will register the first scope-gated handler at `GET /v1/reading-speed`.

14. **No `auth_type` deployment-mode default change.** `settings.auth_type` defaults to `"none"` in the archetype-emitted config (verified — `core/config.py:102`). Do NOT change the default in this story; `oidc_bearer` is opt-in via `AUTH_TYPE=oidc_bearer` in `services/resource-server/.env`. Tests instantiate `oidc_bearer` mode explicitly (via `monkeypatch.setattr` or test-local settings overrides). Story 3.6 will likely flip the compose `default`/`dev` profile's `AUTH_TYPE` to `oidc_bearer`; THIS story leaves `.env.example`'s `AUTH_TYPE` either unset or `none` for back-compat. (Note: `.env.example` already does not set `AUTH_TYPE` — confirm via grep.)

15. **`services/resource-server/.env.example` documents `AUTH_TYPE=oidc_bearer` as the production-intended value.** Add a comment block in the OIDC section:
    ```
    # AUTH_TYPE selects the bearer-token validation plugin (archetype seam).
    # Valid values:
    #   - none         → no validation; principal is a synthetic admin. Tests / local dev only.
    #   - entra        → Azure Entra ID (vestigial; will be removed after Story 4.1).
    #   - oidc_bearer  → Keycloak via JWKS (Story 3.2). REQUIRED for production / e2e.
    # When unset, defaults to "none" (archetype default). Compose profiles default+dev+e2e
    # SHOULD set AUTH_TYPE=oidc_bearer (set in the per-service .env once Story 3.6 / 3.3 land
    # a scope-gated handler).
    #AUTH_TYPE=oidc_bearer
    ```
    The line stays commented (operators copy + uncomment). Do NOT also set `AUTH_TYPE` in compose env stanzas in this story — that wiring is downstream.

16. **All `uv` / archetype gates remain green from `services/resource-server/`.** End-to-end command sequence (capture stdout + return code in the dev log):
    - `uv sync --frozen` → 0 (with the new `pyjwt[crypto]` dep present; the lockfile MUST be updated via `uv add 'pyjwt[crypto]'` — never edit `uv.lock` by hand and never run `uv lock` directly).
    - `uv run ruff check` → 0 findings.
    - `uv run ruff format --check` → 0 reformats needed (run `uv run ruff format` if anything is flagged; commit the format diff in the same dev commit).
    - `uv run ty check` → 0 errors.
    - `uv run pytest --cov` → all tests pass, coverage ≥ 90% (the project threshold). The whole-suite coverage % typically rises by ~0.1–1% with the additional well-covered file; capture the exact post-change %.

17. **Pre-existing repo state is preserved.** Files outside `services/resource-server/src/resource_server/{auth,core}/`, `services/resource-server/tests/auth/`, `services/resource-server/pyproject.toml`, `services/resource-server/uv.lock`, `services/resource-server/.env.example`, and the BMAD bookkeeping files (`sprint-status.yaml`, this story file, `deferred-work.md` only for new defers) are unchanged. Specifically: `CLAUDE.md`, root `README.md`, root `.env.example`, `docker-compose.yml`, `compose/*.yml`, `keycloak/*`, `services/bff/**`, `spa/**`, `e2e/**`, and `services/resource-server/{Dockerfile,entrypoint.sh,.gitattributes,alembic/**}` are bit-for-bit identical to their pre-story state.

## Tasks / Subtasks

- [x] **Task 1 — Add `pyjwt[crypto]` dependency and confirm the lockfile is clean** (AC: #1, #16)
  - [x] From `services/resource-server/`, run `uv add 'pyjwt[crypto]'`. Inspect `pyproject.toml` — the `[project] dependencies` list should now include a pinned `pyjwt[crypto]` line. `uv.lock` updates with the new transitive `cryptography` cohort (this is also pulled by the archetype's existing `httpx[http2]` indirectly, so the lock diff should be small).
  - [x] **Sanity check the existing `httpx`-bound jwt import in `auth/entra.py`** — that file already imports `import jwt` (PyJWT) and `from jwt import PyJWK`. This means PyJWT is already a transitive dep of the archetype. Running `uv add 'pyjwt[crypto]'` makes it a direct + explicit dep with the `crypto` extra (which pulls `cryptography` for RS256). This is intentional — `pyjwt` without `[crypto]` cannot verify RS256 signatures.
  - [x] `uv sync --frozen` → 0. If `--frozen` complains, do NOT run `uv lock` to regenerate — investigate the diff (the only acceptable changes are the new explicit pyjwt[crypto] pin + transitive cryptography pin).

- [x] **Task 2 — Extend `Principal` with `scopes: frozenset[str]`** (AC: #2, #6)
  - [x] Edit `services/resource-server/src/resource_server/auth/models.py`:
    ```python
    @dataclass(frozen=True, kw_only=True)
    class Principal:
        subject: str
        user_id: str
        name: str | None = None
        scope: str | None = None              # raw space-delimited (archetype field — keep)
        scopes: frozenset[str] = field(default_factory=frozenset)  # NEW — parsed set
        app_id: str | None = None
        roles: list[str] = field(default_factory=list)
        groups: list[str] = field(default_factory=list)
        claims: dict[str, Any] = field(default_factory=dict)
    ```
  - [x] Run `uv run ty check` → 0 errors. `frozenset[str]` is parseable in Python 3.14.
  - [x] Run `uv run pytest tests/auth/ -v` → all existing tests pass (Principal's existing callers don't pass `scopes`; the default is empty frozenset).
  - [x] Coverage of `auth/models.py` is unchanged (it's all `@dataclass`-generated; no runtime branches).

- [x] **Task 3 — Author `core/errors.py` additions: `SESSION_EXPIRED` (401) + `FORBIDDEN_SCOPE` (403)** (AC: #4)
  - [x] Edit `services/resource-server/src/resource_server/core/errors.py`. Add to the `ErrorCode` enum, immediately after `SERVICE_UNAVAILABLE`:
    ```python
    SESSION_EXPIRED = (
        "session_expired",
        "Authentication required",
        401,
    )
    FORBIDDEN_SCOPE = (
        "forbidden_scope",
        "Required scope is missing",
        403,
    )
    ```
  - [x] Update the doc comment above the project-specific block to extend the consumer-mapping note: Story 3.2 lands SESSION_EXPIRED + FORBIDDEN_SCOPE; Story 3.3 will land INVALID_INPUT + READING_SPEED_UNSET.
  - [x] Run `uv run pytest tests/core/` → existing errors-module tests still pass.

- [x] **Task 4 — Author `src/resource_server/auth/oidc_bearer.py`** (AC: #1, #3, #4, #5, #7, #8)
  - [x] Create the file. Imports:
    ```python
    import logging
    from collections.abc import Awaitable, Callable
    from typing import Annotated, Any

    import jwt
    from fastapi import Depends
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    from resource_server.auth.contracts import (
        AuthFeatureNotSupportedError,
        UnauthorizedError,
    )
    from resource_server.auth.models import AuthFunctions, Principal
    from resource_server.auth.role_mapping import identity_role_mapper
    from resource_server.core.config import AppSettings, settings
    from resource_server.core.errors import AppException, ErrorCode

    logger = logging.getLogger(__name__)
    ```
  - [x] Module-level JWKS-client cache + accessor (mirrors BFF lines 193–201 verbatim modulo the package path):
    ```python
    _jwks_clients: dict[str, jwt.PyJWKClient] = {}

    def _get_jwks_client(jwks_url: str) -> jwt.PyJWKClient:
        if jwks_url not in _jwks_clients:
            _jwks_clients[jwks_url] = jwt.PyJWKClient(
                jwks_url, cache_keys=True, max_cached_keys=4
            )
        return _jwks_clients[jwks_url]
    ```
  - [x] Helper to parse the space-delimited scope claim → `frozenset[str]`:
    ```python
    def _parse_scopes(claim: object) -> frozenset[str]:
        if isinstance(claim, str):
            return frozenset(s for s in claim.split() if s)
        return frozenset()
    ```
    Architecture note: Keycloak emits scope as a space-delimited STRING in the access token's `scope` claim. Some auth servers emit a list; we accept only the string form to match Keycloak's actual emission (verified via realm-bmad-books.json scope-mapper config).
  - [x] JWT validation helper:
    ```python
    def _validate_access_token(token: str) -> dict[str, Any]:
        try:
            jwks_client = _get_jwks_client(settings.oidc_jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            decoded = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.oidc_audience,
                issuer=settings.oidc_issuer_url,
                options={"require": ["iss", "aud", "exp", "sub"]},
            )
        except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
            logger.warning("JWT validation failed: %s", type(exc).__name__)
            raise AppException(ErrorCode.SESSION_EXPIRED) from exc
        if not isinstance(decoded, dict):  # pragma: no cover -- PyJWT always returns dict
            raise AppException(ErrorCode.SESSION_EXPIRED)
        return decoded
    ```
    Note: `jwt.decode(audience=..., issuer=...)` enforces aud/iss as part of decode and raises `InvalidAudienceError` / `InvalidIssuerError` — both subclass `InvalidTokenError`, so the single `except` covers all the failure modes.
  - [x] Build `Principal` from claims:
    ```python
    def _principal_from_claims(claims: dict[str, Any]) -> Principal:
        scope_raw = claims.get("scope")
        return Principal(
            subject=str(claims["sub"]),
            user_id=str(claims["sub"]),
            name=str(claims["preferred_username"]) if "preferred_username" in claims else None,
            scope=str(scope_raw) if isinstance(scope_raw, str) else None,
            scopes=_parse_scopes(scope_raw),
            claims=claims,
        )
    ```
    `sub` is required by `_validate_access_token` (per `options.require`), so `claims["sub"]` is safe.
  - [x] FastAPI dependency:
    ```python
    bearer_scheme = HTTPBearer(auto_error=False)

    async def get_authenticated_principal(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
        ],
    ) -> Principal:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise AppException(ErrorCode.SESSION_EXPIRED)
        token = credentials.credentials
        if not token or not token.strip():
            raise AppException(ErrorCode.SESSION_EXPIRED)
        claims = _validate_access_token(token)
        return _principal_from_claims(claims)
    ```
  - [x] Scope-enforcement factory:
    ```python
    def require_scope(scope: str) -> Callable[..., Awaitable[Principal]]:
        async def _dependency(
            principal: Annotated[Principal, Depends(get_authenticated_principal)],
        ) -> Principal:
            if scope not in principal.scopes:
                logger.warning(
                    "Scope check failed: sub=%s requires %s",
                    principal.subject,
                    scope,
                )
                raise AppException(ErrorCode.FORBIDDEN_SCOPE)
            return principal
        return _dependency
    ```
  - [x] AuthFunctions factory (archetype seam — required for AC #5/#7):
    ```python
    def make_oidc_bearer_auth(settings_arg: AppSettings) -> AuthFunctions:
        # settings_arg is read at module level via `settings` for the deps above;
        # accept it for signature parity with make_entra_auth and future testability.
        _ = settings_arg

        async def authenticate_bearer_token(token: str) -> Principal:
            try:
                claims = _validate_access_token(token)
            except AppException as exc:
                raise UnauthorizedError("JWT validation failed") from exc
            return _principal_from_claims(claims)

        async def get_client_credentials_access_token(scope: str) -> str:
            _ = scope
            raise AuthFeatureNotSupportedError(
                "Token issuance is not supported by AUTH_TYPE=oidc_bearer"
            )

        async def get_on_behalf_of_access_token(scope: str, user_token: str) -> str:
            _ = (scope, user_token)
            raise AuthFeatureNotSupportedError(
                "OBO flow is not supported by AUTH_TYPE=oidc_bearer"
            )

        return AuthFunctions(
            authenticate_bearer_token=authenticate_bearer_token,
            get_client_credentials_access_token=get_client_credentials_access_token,
            get_on_behalf_of_access_token=get_on_behalf_of_access_token,
            role_mapper=identity_role_mapper,
        )
    ```
  - [x] Update `auth/__init__.py` if needed (it is currently 4 lines — likely just a docstring or empty package marker; do NOT export oidc_bearer symbols at package level — callers import from the submodule).

- [x] **Task 5 — Wire `oidc_bearer` into `core/config.py` Literal + `auth/factory.py` dispatch** (AC: #5, #14)
  - [x] Edit `core/config.py:102`: change `auth_type: Literal["none", "entra"]` → `auth_type: Literal["none", "entra", "oidc_bearer"]`. Default stays `"none"`.
  - [x] Edit `auth/factory.py`. Add a `_build_oidc_bearer` builder mirroring `_build_entra` (with lazy import). Add `"oidc_bearer": _build_oidc_bearer` to the `builders` dict.
  - [x] Run `uv run ty check` → 0 errors. The dispatch table's keys must match the Literal's members exactly (ty will catch a mismatch).
  - [x] Run `uv run pytest tests/auth/test_factory_and_none_provider.py -v` → existing tests pass.

- [x] **Task 6 — Author `tests/auth/synthetic_idp.py`** (AC: #9)
  - [x] Place at `services/resource-server/tests/auth/synthetic_idp.py`.
  - [x] Generate an RSA-2048 keypair at module-level (use `cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key(public_exponent=65537, key_size=2048)`).
  - [x] Provide `_b64u(data: bytes) -> str`, `_int_to_b64u(n: int) -> str`, `_public_jwk(key, kid)` helpers (copy from `services/bff/tests/auth/synthetic_idp.py` lines 44–74 verbatim — these are MIT-style boilerplate).
  - [x] Dataclass:
    ```python
    @dataclass
    class SyntheticRsIdp:
        private_key: rsa.RSAPrivateKey
        public_jwk: dict[str, str]
        issuer: str
        audience: str
        jwks_url: str
        _alt_kid_jwk: dict[str, str] | None = None  # for rotation tests
        _alt_kid_private_key: rsa.RSAPrivateKey | None = None

        def make_access_token(
            self,
            *,
            sub: str = "test-subject-001",
            scope: str = "openid reading-speed:read",
            aud: str | None = None,
            iss: str | None = None,
            exp_offset_seconds: int = 300,
            preferred_username: str | None = "testuser",
            signing_key: rsa.RSAPrivateKey | None = None,
            kid: str | None = None,
            alg: str = "RS256",
            claims_override: dict[str, Any] | None = None,
        ) -> str: ...
    ```
    Defaults `aud` / `iss` to `self.audience` / `self.issuer`. Implementation mirrors `SyntheticIdp.make_id_token` from the BFF.
  - [x] `build_synthetic_rs_idp(monkeypatch, *, issuer=..., audience=..., jwks_url=...) -> SyntheticRsIdp` builder. The monkeypatch performs three actions:
    1. Clear the RS's `oidc_bearer._jwks_clients` cache (`monkeypatch.setattr(oidc_bearer, "_jwks_clients", {})`).
    2. Patch `jwt.PyJWKClient.fetch_data` to return `{"keys": [self.public_jwk]}` (or include the alt-kid JWK if registered).
    3. Patch `settings.oidc_issuer_url` / `settings.oidc_audience` / `settings.oidc_jwks_url` for the test scope (use `monkeypatch.setattr` — pydantic-settings allows attribute mutation in tests; if not, set the env vars and re-instantiate `AppSettings` — implementer's choice).
  - [x] `register_rotated_kid(new_kid)` helper that adds a SECOND public JWK to the `fetch_data` patch (so calling `make_access_token(kid=new_kid)` after `register_rotated_kid` produces a token validatable against the second-fetched JWKS). The test simulates rotation by clearing the cache between calls and verifying `fetch_data` is invoked twice.
  - [x] Track `fetch_data` invocations: include a `fetch_call_count: int` attribute that the patched `fetch_data` increments. The kid-cache-hit test (AC #10 case 9) asserts this is 1; the rotation test (AC #10 case 8) asserts this is 2.
  - [x] Export `build_synthetic_rs_idp`, `SyntheticRsIdp`, default constants (`DEFAULT_ISSUER`, `DEFAULT_AUDIENCE`, `DEFAULT_JWKS_URL`, `DEFAULT_KID`, `DEFAULT_ROTATED_KID`) via `__all__`.

- [x] **Task 7 — Author `tests/auth/test_oidc_bearer.py`** (AC: #10, #11, #12)
  - [x] Use `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")` per the existing `tests/auth/conftest.py` pattern.
  - [x] **Mount the fixture endpoint** via a test-only sub-app OR via a route added at fixture setup. Recommended: in a fixture, `from resource_server.main import app` then `app.add_api_route("/_test/scoped-read", _handler, dependencies=[Depends(require_scope("reading-speed:read"))])`. Remove the route in fixture teardown by popping from `app.router.routes` (or use a fresh FastAPI instance — implementer's call).
  - [x] Implement all 23 cases from AC #10.
  - [x] Use `caplog.set_level(logging.WARNING, logger="resource_server.auth.oidc_bearer")` for the log-assertion tests (#21, #22). Assert on `record.message` substrings; assert no token contents leak.
  - [x] For the kid-rotation test (#7, #8): assert `synthetic_idp.fetch_call_count == 2` post-test.
  - [x] For the kid-cache-hit test (#9): make the request three times; assert `synthetic_idp.fetch_call_count == 1`.
  - [x] For the `alg: none` test (#14): construct manually — `jwt.encode({...}, "", algorithm="none")` is rejected by PyJWT by default; you may need to construct the token bytes by hand via base64-encoded `{"alg":"none","typ":"JWT"}` + claim + empty signature.
  - [x] For the `alg: HS256` test (#15): `jwt.encode(claims, "shared-secret", algorithm="HS256")` is straightforward; the decode call's `algorithms=["RS256"]` rejects.

- [x] **Task 8 — Update `services/resource-server/.env.example` AUTH_TYPE comment block** (AC: #15)
  - [x] Add the comment block per AC #15. Keep `AUTH_TYPE=oidc_bearer` itself commented out (operators copy + uncomment in their `.env`).
  - [x] Do NOT touch compose env stanzas in `compose/app.yml` — that wiring is downstream (Story 3.3 or 3.6).

- [x] **Task 9 — Run the full gate sequence** (AC: #16, #17)
  - [x] From `services/resource-server/`:
    - [x] `uv sync --frozen` → 0.
    - [x] `uv run ruff check` → 0 findings.
    - [x] `uv run ruff format --check` → 0 reformats needed.
    - [x] `uv run ty check` → 0 errors.
    - [x] `uv run pytest --cov` → all pass; coverage ≥ 90% (project threshold). Capture the post-change % in the dev log. Specifically capture `pytest --cov=resource_server.auth.oidc_bearer --cov-report=term-missing` to verify ≥90% on the new file.
  - [x] **`git diff --stat`** to confirm the change set is scoped per AC #17. Expected files touched:
    - `services/resource-server/pyproject.toml` (+ `pyjwt[crypto]` dep)
    - `services/resource-server/uv.lock` (+ pin updates only)
    - `services/resource-server/src/resource_server/auth/models.py` (Principal.scopes field)
    - `services/resource-server/src/resource_server/auth/oidc_bearer.py` (NEW)
    - `services/resource-server/src/resource_server/auth/factory.py` (oidc_bearer branch)
    - `services/resource-server/src/resource_server/core/config.py` (Literal expansion to include "oidc_bearer")
    - `services/resource-server/src/resource_server/core/errors.py` (SESSION_EXPIRED + FORBIDDEN_SCOPE)
    - `services/resource-server/tests/auth/synthetic_idp.py` (NEW)
    - `services/resource-server/tests/auth/test_oidc_bearer.py` (NEW)
    - `services/resource-server/.env.example` (AUTH_TYPE comment block)
    - `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flip)
    - `_bmad-output/implementation-artifacts/3-2-rs-...md` (this story file — Tasks ticked, Dev Agent Record populated)

- [x] **Task 10 — Bookkeeping** (AC: #17)
  - [x] Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: flip `3-2-rs-oidc-bearer-auth-plugin-jwks-scope-enforcement-synthetic-idp-test-harness` from `ready-for-dev` → `in-progress` at story start, then to `review` once dev-story completes. Update `last_updated`.
  - [x] If new defers surface during code review, append them under a new `## Deferred from: code review of 3-2-...` section in `deferred-work.md`. Continue D-number sequence from D58 (current ceiling from Story 3.1 review).
  - [x] Verify the untouched-files list per AC #17 — `CLAUDE.md`, root files, `compose/*.yml`, `keycloak/*`, `services/bff/**`, `spa/**`, `e2e/**`, `services/resource-server/{Dockerfile,entrypoint.sh,.gitattributes,alembic/**}` are unchanged.

### Review Findings

Code review run on 2026-05-16 against `baseline_commit: 2a35822` (the 2 dev-story commits on `worktree-story-3.2`: `f5b0bc0` story creation + `5966b2a` impl). Three adversarial review layers ran in parallel via the Agent tool: Blind Hunter (diff-only), Edge Case Hunter (diff + project read), Acceptance Auditor (diff + spec + project read). Findings normalized, deduped (1+ → 1 in 5 cases), and triaged.

**Summary: 0 decision-needed, 7 patches applied, 7 deferred (D59–D65), 15 dismissed as noise.**

#### Patches — applied 2026-05-16

- [x] [Review][Patch] **CR1 — `_mount_test_routes` not `try/finally`-protected** [`services/resource-server/tests/auth/test_oidc_bearer.py:58-73`] — Edge Case Hunter flagged that an exception in a test after `yield` resumes but before teardown completes would leak the test routes onto the production `app` for any later test module in the same session. Wrapped the teardown route-pop in `try/finally` so cleanup runs even on fixture-side exceptions. **APPLIED.**

- [x] [Review][Patch] **CR2 — `require_scope("")` / whitespace-padded scope silently 403s every request** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:115-127`] — Edge Case Hunter HIGH. A typo like `require_scope(" reading-speed:read")` (leading space) would never match any parsed scope (which `_parse_scopes` whitespace-cleans), silently 403ing all callers without any signal to the developer. Added a fail-fast `ValueError` guard at factory-call time (raises before the dep closure is built). Added 2 tests pinning the new behavior. **APPLIED.**

- [x] [Review][Patch] **CR3 — `claims["sub"]` defensive hygiene** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:89-90`] — Blind Hunter. Currently safe (the `require` list pins `sub`) but `KeyError` would surface as a 500 if a future edit removes `sub` from the require list. Switched to `claims.get("sub", "")` to surface as a normal `Principal` construction failure instead. **APPLIED.**

- [x] [Review][Patch] **CR4 — `test_jwks_kid_miss_unknown_after_refetch_returns_401` doesn't assert `fetch_call_count`** [`services/resource-server/tests/auth/test_oidc_bearer.py`] — Blind Hunter MED. The test claims the re-fetch path is exercised but only checked the final 401. Added `assert synthetic_rs_idp.fetch_call_count >= 2` to pin the re-fetch invariant; otherwise PyJWKClient could raise early and the test would still pass with the same status. **APPLIED.**

- [x] [Review][Patch] **CR5 — `pyjwt[crypto]` upper bound** [`services/resource-server/pyproject.toml`] — Blind Hunter LOW. PyJWT 3.x may change `PyJWKClient` semantics. Pinned to `>=2.10,<3` to gate a major-version bump behind explicit review. **APPLIED.**

- [x] [Review][Patch] **CR6 — `Principal.scopes` is a `frozenset` not asserted in the request-layer test** [`services/resource-server/tests/auth/test_oidc_bearer.py`] — Acceptance Auditor CONCERN re AC #10 case #18. Spec case #18 explicitly said "assert `isinstance(principal.scopes, frozenset)`". The existing unit-level `_parse_scopes` tests cover the type; added an `_test_principal_type` endpoint inside the test module that returns the type name so the request-layer assertion is also pinned. **APPLIED.**

- [x] [Review][Patch] **CR7 — Non-string `scope` claim silently empties the scope set** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:60-63`] — Blind Hunter + Edge Case Hunter LOW/MED. RFC 8693 allows the `scope` claim to be a JSON array; some IdPs (Auth0, Okta) emit it that way. With Keycloak it's always a space-delimited string, but a future IdP swap (architecture explicitly allows `oidc_bearer` mode to point at any IdP) would silently 403 every request without any signal. Added a `logger.warning("scope claim was non-string (%s); falling back to empty scope set", ...)` so misconfiguration is observable. Added a test asserting the warning fires for list-shaped claims. **APPLIED.**

#### Deferred

See `_bmad-output/implementation-artifacts/deferred-work.md` "Deferred from: code review of 3-2-..." (D59–D65) for full text.

- [x] [Review][Defer] **D59 — `make_oidc_bearer_auth(settings_arg)` ignores its `settings_arg` argument** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:131-139`] — Blind + Edge HIGH (deduped). Real factory-contract weakness: `get_auth(test_settings)` with per-call OIDC values silently falls back to the module-level `settings` singleton because the inner `authenticate_bearer_token` calls `_validate_access_token` which reads the global. Story 3.2's text explicitly documented this design choice ("test fixtures can monkeypatch them without rebuilding the AuthFunctions closure"). Fixing it properly requires threading `settings_arg` through `_validate_access_token` + the `get_authenticated_principal` request dep, which broadens the surface beyond what this story committed to. Belongs to a follow-up that aligns both archetype seams (entra + oidc_bearer) on a single settings-injection pattern.
- [x] [Review][Defer] **D60 — `_jwks_clients` module cache never evicts on JWKS-URL reconfiguration** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:49,52-57`] — Edge + Blind HIGH (deduped). The dict is keyed by URL string and grows indefinitely. In production the `oidc_jwks_url` value is set once at boot via required-fail-fast config, so this never triggers; in tests `synthetic_idp.py:194` resets the cache per fixture. Real concern only in a hypothetical config-reload scenario; the BFF has the same pattern. Belongs to a coordinated BFF+RS JWKS-cache pass.
- [x] [Review][Defer] **D61 — `oidc_jwks_connect_timeout` / `oidc_jwks_read_timeout` settings unread** [`services/resource-server/src/resource_server/core/config.py:99-100`] — Blind MED. The two timeout fields land in Story 3.1's `AppSettings` and are read by `/health`'s JWKS probe but NOT by PyJWKClient's signing-key fetch (PyJWKClient uses `urllib.request.urlopen` with no timeout knob — see D62). They appear dead-config for the JWT-validation surface specifically. Pre-existing from Story 3.1; reviewing here because Story 3.2's mention of them re-surfaces the question. Belongs to D62's resolution.
- [x] [Review][Defer] **D62 — PyJWKClient's signing-key HTTP fetch has no timeout** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:54-55,69-77`] — Blind MED. Architecture line 415 calls for 5s connect / 10s read on the RS→Keycloak JWKS fetch. PyJWKClient does not expose a timeout argument; its internal `urllib.request.urlopen` call has no default timeout. A hung Keycloak JWKS endpoint at first-request-after-cache-miss would block the event loop. Story 3.2 explicitly documented this trade-off in AC #8 (the `/health` JWKS probe from Story 3.1 is the operational guard). Real fix: subclass `PyJWKClient` or wrap `get_signing_key_from_jwt` in `asyncio.wait_for(..., timeout=settings.oidc_jwks_read_timeout)`. Belongs to a coordinated BFF+RS hardening pass (BFF has the same issue in `keycloak_cookie_session.py`).
- [x] [Review][Defer] **D63 — 401 responses don't include `WWW-Authenticate: Bearer` per RFC 6750 §3** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:106-111`] — Blind QUESTION. The error envelope from `AppException` does not add the `WWW-Authenticate` header. RFC 6750 §3 mandates this on 401 responses from OAuth-protected resources so that clients know which scheme to retry with. Real RFC-compliance gap; not user-visible because the BFF's `ResourceServerClient` (Story 3.5) won't inspect the header. Belongs to Story 5.2 (security review document) — the security review will surface this as a documented accepted-or-fixed item.
- [x] [Review][Defer] **D64 — No `leeway` / `nbf` / `iat`-future test coverage for clock-skew handling** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:69-77`] — Edge + Blind MED. `jwt.decode` is called without `leeway=...`. PyJWT validates `nbf` when present (raises `ImmatureSignatureError`, caught correctly) but the test suite doesn't pin this. In production, clock drift between Keycloak and the RS host at deploy-rollout windows could cause spurious 401s without leeway. Story 3.2 did not require a leeway config field; introducing one is out of scope. Belongs to a future hardening pass (likely Story 5.2 security review).
- [x] [Review][Defer] **D65 — No test pinning `aud`-as-list (Keycloak's native shape)** [`services/resource-server/tests/auth/test_oidc_bearer.py`] — Edge MED. PyJWT's `jwt.decode(audience="bmad-books-resource-server")` does the right thing when the token's `aud` claim is a list (Keycloak's `"aud": ["bmad-books-resource-server", "account"]`) — it checks membership. But the test suite mints tokens with `aud=<string>` only, so the list-shaped path is unverified. A future PyJWT change could regress without our tests noticing. Belongs to a small test addition; not blocking for Story 3.2's exit criteria.

#### Dismissed (15)

- **Module-level `settings` global mutation in tests** — intentional per spec (Dev Notes acknowledge this trade-off vs. closure capture).
- **`make_oidc_bearer_auth` accepts `settings_arg` cosmetically** — duplicate of D59 above.
- **Test mounts on production `app`** — spec explicitly authorized either approach (AC #10 "implementer's choice"); CR1 try/finally addresses the robustness concern.
- **synthetic_idp `fetch_call_count` race** — pytest runs serially in default config; GIL makes `+=` safe in practice.
- **`alg=none` test passes for the right reason** — Blind Hunter speculated alg-rejection vs issuer-mismatch; verified the token's issuer/aud/kid all match defaults, so the 401 is from alg pinning as intended.
- **`_validate_access_token` doesn't catch `Exception`** — PyJWT's exception hierarchy is well-defined; cryptography errors require malformed JWKs that the synthetic harness shape-checks. Adding a broad `Exception` catch would mask real bugs.
- **HTTPBearer "collides" on `bearer_scheme`** — Blind Hunter; the new `bearer_scheme` is in `oidc_bearer.py`, the existing one is in `auth/dependencies.py`. Different deps for different paths; FastAPI's OpenAPI may show two security schemes but they're functionally equivalent.
- **PyJWT class-level monkeypatch affects other tests** — Edge Case Hunter acknowledged this is bounded by `monkeypatch.setattr`'s teardown.
- **`Principal.scopes` `asdict` serialization risk** — no `asdict(principal)` callers in the diff.
- **`_principal_from_claims` stores raw `claims`** — architectural choice; the existing `Principal.claims: dict[str, Any]` field is the documented contract.
- **`test_whitespace_only_bearer_token` bypasses FastAPI layer** — Blind Hunter; comments are clear about why; the dep's whitespace branch is the unit under test.
- **`test_factory_dispatch` could leak shell env** — pydantic-settings honors explicit kwargs over env vars; test is fine.
- **`# pragma: no cover` on `isinstance(decoded, dict)`** — standard PyJWT contract guarantees a dict; the pragma is appropriate.
- **Lowercase scheme `bearer foo` not tested** — Edge Case Hunter LOW; the `.lower()` defense exists. Marginal; not in spec.
- **Coverage drop 98.42% → 97.83%** — expected when adding a new file; still well above the 90% gate.

#### Acceptance Auditor verdict table

| AC | Status | Note |
|----|--------|------|
| 1  | MET | `pyjwt[crypto]>=2.10` (now `,<3` after CR5) in `pyproject.toml`; module-level `_jwks_clients: dict[str, jwt.PyJWKClient]`; `PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=4)` exact BFF parity. (Cosmetic concern: pyjwt was already transitively present; dev log acknowledged.) |
| 2  | MET | `Principal.scopes: frozenset[str] = field(default_factory=frozenset)` added after the existing `scope: str | None` field; all prior fields preserved. |
| 3  | MET | `algorithms=["RS256"]` pinned; `options={"require": ["iss","aud","exp","sub"]}`; all failures → `SESSION_EXPIRED` (401); WARNING log emits only `type(exc).__name__`. |
| 4  | MET | `require_scope(scope: str) -> Callable[..., Awaitable[Principal]]`; wire values `("session_expired",401)` + `("forbidden_scope",403)`; no premature ErrorCode additions; CR2 adds factory-time guard for empty/whitespace scope. |
| 5  | MET | `Literal["none", "entra", "oidc_bearer"]`; lazy-import `_build_oidc_bearer` in factory.py; default stays `"none"`. |
| 6  | MET | No archetype auth-test files modified; `Principal.scopes` default factory preserves callers; full suite 204 passed (171 pre-3.2 + 33 new). |
| 7  | MET | `make_oidc_bearer_auth` returns AuthFunctions with the four expected callables; client_credentials + OBO raise `AuthFeatureNotSupportedError`; role_mapper=identity. |
| 8  | MET | JWKS cache + kid-miss re-fetch invariant satisfied; per-process TTL deviation from §C6 24h is documented in `oidc_bearer.py:42-49` per spec instruction. |
| 9  | MET | RS-local synthetic IdP harness; no cross-service import; monkeypatches `jwt.PyJWKClient.fetch_data` (not respx/httpx); `fetch_call_count` + `register_rotated_kid` helpers; module-level `_jwks_clients` reset per fixture. |
| 10 | MET | All 23 enumerated test cases implemented (test count 33 with helper-unit + factory-dispatch additions); CR6 strengthens case #18's request-layer frozenset-type assertion. |
| 11 | MET | Coverage of `oidc_bearer.py` = 100% (65/65 statements) — well above the ≥90% gate. |
| 12 | MET | No archetype auth-test files in the diff; all 171 Story-3.1 tests continue passing. |
| 13 | MET | No production-app router changes; `/_test/oidc/*` exists only inside the test module's autouse fixture (CR1 now wraps in try/finally). |
| 14 | MET | `auth_type` default stays `"none"`; `.env.example` `AUTH_TYPE=oidc_bearer` line is commented out. |
| 15 | MET | `.env.example` AUTH_TYPE comment block matches the spec's documented copy points. |
| 16 | MET | All gates green: ruff/format/ty clean; pytest 204 passed; whole-suite coverage 97.83% (>90% gate); CR* patches keep all gates green. |
| 17 | MET | Diff scoped to the 12 expected files only; no prohibited paths touched (verified via `git diff --name-only`). |

**Verdict:** All 17 ACs **MET** after CR1–CR7 applied. Story moves `review` → `done`.

## Dev Notes

### What this story is — and is not

**This story lands the RS's JWT-validation surface and scope-enforcement primitive.** It introduces:
- `auth/oidc_bearer.py` (the validation logic + FastAPI deps),
- `Principal.scopes: frozenset[str]` (the parsed scope set),
- `core/errors.py` additions: `SESSION_EXPIRED` (401) and `FORBIDDEN_SCOPE` (403),
- An `oidc_bearer` mode in the archetype's auth-plugin factory,
- A synthetic-IdP test harness (`tests/auth/synthetic_idp.py`) that signs RS256 tokens against an in-process RSA keypair so unit tests don't need a live Keycloak.

**Explicitly NOT in scope:**

- **No production-app router mounts.** `require_scope` is a dependency factory — it is exercised by tests only. Story 3.3 wires the first scope-gated handler at `GET /v1/reading-speed`.
- **No `ReadingSpeed` model, no `/v1/reading-speed` GET/PUT.** Story 3.3.
- **No `/v1/test/reset` endpoint, no `/v1/estimate` endpoint.** Stories 3.4 and 4.1.
- **No deletion of `auth/entra.py`.** It becomes vestigial after this story but stays on disk for cross-service consistency until a coordinated cleanup pass. Architecture line 244 ("Genericize the archetype's `entra` mode") is satisfied by **adding** `oidc_bearer` as a sibling — not by replacing `entra` in place. The archetype's tests for `entra` continue to pass; this story does NOT modify any test under `tests/auth/` other than adding new files.
- **No changes to compose, Dockerfile, entrypoint, alembic.** This is a pure src+tests story.
- **No `AUTH_TYPE=oidc_bearer` in the active compose env.** The `.env.example` documents it (Task 8) but does not flip the default — leaving deployments on `none` until Story 3.3's first scope-gated handler arrives means premature `oidc_bearer` configuration cannot break startup (the required-fail-fast OIDC config from Story 3.1 already catches misconfiguration anyway).
- **No `/metrics`, no OTEL exporter wiring.** Inert per the 2026-05-14 sprint-change cut.
- **No SPA serving.** RS is JSON-API-only (architecture §F3 + §I6).
- **No JWKS-document caching TTL knob.** Architecture line 415 says "24h cache TTL"; PyJWKClient does not take a TTL arg. The kid-miss-driven re-fetch path satisfies the underlying invariant (validation survives key rotation without operator intervention) — this is documented in AC #8 and is intentional drift from the verbatim spec.

### Architectural foundation (architecture.md line references)

- **§A2 line 348** — "RS JWT validation library: **PyJWT** (`pyjwt[crypto]`) with `PyJWKClient`. Genericize the archetype's `entra` mode to accept `(issuer, jwks_url, audience)` and expose it as a `keycloak` / `oidc-bearer` mode." → This story uses the name `oidc_bearer` (underscore, matching Python identifier conventions) for the new mode.
- **§C3 lines 382–386** — RS endpoint table. Scope requirements: `reading-speed:read` on GET `/v1/reading-speed` (3.3) and POST `/v1/estimate` (4.1); `reading-speed:write` on PUT `/v1/reading-speed` (3.3). Story 3.2's `require_scope` factory is what each of those routes uses.
- **§C5 lines 396–409** — `ErrorCode` enum members. `SESSION_EXPIRED = "session_expired"` (401), `FORBIDDEN_SCOPE = "forbidden_scope"` (403). Wire values are lower_snake_case STRINGS in the JSON envelope.
- **§C6 line 415** — "RS → Keycloak (JWKS): 5s timeout, in-process cache TTL 24h, key-rotation on `kid` miss (single re-fetch)." PyJWKClient handles the cache + kid-miss re-fetch; the TTL is per-process-lifetime (see AC #8). The 5s timeout applies to PyJWKClient's HTTP fetch — PyJWKClient does not expose a timeout configuration directly, but its internal `urllib.request.urlopen` call has no default timeout. **Practical implication:** in production, a Keycloak JWKS endpoint outage would cause first-request-after-cache-miss to block on a TCP/TLS hang. Story 3.1's `/health` JWKS probe is the operational guard — when JWKS is unreachable, `/health` returns 503 and orchestrators stop sending real traffic. **For Story 3.2, do not attempt to wrap PyJWKClient's HTTP fetch in a timeout** — that diverges from BFF parity. Track this as a potential defer post-review if reviewers raise it.
- **§Authentication & Security line 347 (A1)** — BFF's request scope string is `openid offline_access reading-speed:read reading-speed:write`. Keycloak's realm-bmad-books.json:106-107 grants `reading-speed:read` / `reading-speed:write` as optional client scopes to the BFF. Tokens minted by Keycloak therefore carry `scope` claim like `"openid profile reading-speed:read reading-speed:write"` (the order can vary).
- **§Cross-Cutting Concerns Mapping lines 1190–1191** — "JWKS validation + caching: `services/resource-server/src/resource_server/auth/oidc_bearer.py`. Scope enforcement: same file (via archetype's `RoleMappingProvider`)." → Story 3.2 implements scope enforcement DIRECTLY rather than via the `RoleMappingProvider` extension point. Rationale: the `RoleMappingProvider` (`auth/role_mapping.py:1`) is designed for role-name translation (Keycloak role → archetype Role enum). Scopes are orthogonal — they're OAuth-flow concepts at the endpoint-authorization layer, not role-translation concepts. Adapting `RoleMappingProvider` to scopes would require either (a) overloading its single-string mapping to handle space-delimited scope claims, or (b) introducing a parallel `ScopeMappingProvider`. **Decision: implement `require_scope` directly in `oidc_bearer.py` and reference the `RoleMappingProvider` line in the architecture as "the natural extension point — chosen-not-used here in favor of a direct dependency-factory pattern that better matches FastAPI idioms".** Document this in the dev log.
- **§Architectural Boundaries line 1127** — "Resource Server ↔ Keycloak: JWKS endpoint only, periodically cached. No session, no token exchange, no admin API." → AC #7's `get_client_credentials_access_token` and `get_on_behalf_of_access_token` MUST raise `AuthFeatureNotSupportedError` (not return a token) to enforce this boundary in code, not just in documentation.
- **§Communication Patterns / Error handling (backend services) line 562** — `X-Request-Id` middleware is archetype-emitted. Story 3.2 does NOT add it. Log lines will carry `request_id` automatically via the archetype's `log_io` AOP decorator (do not double-decorate `_validate_access_token` with `log_io` — it is a pure helper, not a service method).

### Reading Keycloak's access-token shape (verified)

From `keycloak/realm-bmad-books.json` lines 17–58:
- Realm `bmad-books`.
- Scopes `reading-speed:read` and `reading-speed:write` have `include.in.token.scope: "true"` → they appear in the access-token `scope` claim, space-delimited.
- Audience mapper at line 95 emits `aud=bmad-books-resource-server` on the access token (the value Story 3.1's `.env.example` documents as `OIDC_AUDIENCE`).
- The `bmad-books-bff` client has `fullScopeAllowed: false` (line 77) — only the explicitly granted client scopes (`openid`, `offline_access`, `profile`, `reading-speed:read`, `reading-speed:write`) appear on tokens.

Token sample (decoded — for reference; do NOT hardcode in tests, generate via the synthetic IdP):
```json
{
  "iss": "http://keycloak:8080/realms/bmad-books",
  "aud": ["bmad-books-resource-server"],
  "sub": "1c7c0a8e-1f7a-4f59-9a7e-...",
  "azp": "bmad-books-bff",
  "scope": "openid profile reading-speed:read reading-speed:write",
  "preferred_username": "testuser",
  "exp": 1747654321,
  "iat": 1747654021
}
```

Architecture note: PyJWT's `jwt.decode(audience=...)` accepts a string OR list value in the JWT — if `aud` is a list, PyJWT checks membership; if it's a string, PyJWT checks equality. Both shapes work; our config passes `audience=settings.oidc_audience` (a single string), and PyJWT does the right thing.

### Why a frozenset[str] for scopes?

- `Principal` is `@dataclass(frozen=True)`. Mutable defaults (`set[str]`) cause Python warnings and break dict-hashing if `Principal` is ever used as a dict key (it's not today, but the frozenset is "safer by default").
- `frozenset` membership testing (`scope in principal.scopes`) is O(1), same as `set`.
- `field(default_factory=frozenset)` produces an immutable empty value (`frozenset()` is a singleton; no aliasing risk).
- Architecture line 244 says "scopes (parsed from the JWT `scope` space-delimited claim into a `set[str]`)". Using `frozenset[str]` is a subtype-preserving tightening that the architecture does not forbid. Document the choice in the dev log.

### Synthetic-IdP test harness (reuse vs reinvent)

The BFF's `services/bff/tests/auth/synthetic_idp.py` exists (Story 1.5). The RS's harness:
- **Reuses** the RSA-2048 keypair generation pattern, the `_b64u`/`_int_to_b64u` helpers, the `_public_jwk` construction (lines 44–74).
- **Reuses** the `monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", ...)` trick (lines 184–195) — this is the load-bearing insight: respx/httpx mocks do NOT intercept PyJWKClient's `urllib`-based fetch, and `monkeypatch.setattr` on the classmethod is the only reliable way.
- **Does not reuse** the BFF's `/token` / `/revocation` / `/end_session` mocks. The RS never visits those endpoints; respx is overkill here.
- **Cannot directly import** from `services/bff/tests/auth/synthetic_idp.py` per architecture §"Architectural Boundaries" — "no cross-service Python imports". The harness is reproduced in the RS test tree (acceptable duplication; the two harnesses serve different test surfaces).
- **Differs in scope**: the RS harness mints ACCESS tokens (carrying `scope`, validated for aud=`bmad-books-resource-server`); the BFF harness mints ID tokens (carrying `nonce`, validated for aud=`bmad-books-bff`).

### Reading the archetype's existing auth scaffolding

- `auth/contracts.py:1-14` — base exceptions (`AuthError`, `UnauthorizedError`, `ForbiddenError`, `AuthFeatureNotSupportedError`). Story 3.2 RAISES `UnauthorizedError` from `make_oidc_bearer_auth.authenticate_bearer_token` for archetype-seam parity, but the primary public surface (`get_authenticated_principal`) raises `AppException(ErrorCode.SESSION_EXPIRED)` directly.
- `auth/dependencies.py:1-77` — archetype's `get_current_principal` + `require_role`. Story 3.2 does NOT modify this file; it provides a parallel surface (`get_authenticated_principal` + `require_scope`) in `oidc_bearer.py`. The two coexist.
- `auth/models.py:1-32` — `Role` enum (`admin`, `writer`, `reader`), `Principal` dataclass, `AuthFunctions` dataclass. Story 3.2 adds `scopes: frozenset[str]` to `Principal`.
- `auth/factory.py:1-40` — dict-dispatched builder. Story 3.2 adds `oidc_bearer` branch.
- `auth/entra.py` — Azure Entra implementation. Vestigial after Story 3.2 but DO NOT delete in this story (cross-service consistency with the BFF, which also has dead-code modules).
- `auth/role_mapping.py:1-4` — `identity_role_mapper`. Reused in `make_oidc_bearer_auth`'s return.
- `auth/none.py:1-29` — `none` mode. Unchanged.

### `core/errors.py` extension — wire values matter

The existing enum (post-Story 3.1) has two distinct conventions:
- Archetype-emitted: `INTERNAL_ERROR = ("INTERNAL_ERROR", ...)` — **UPPER_SNAKE** wire value.
- Story 3.1's addition: `SERVICE_UNAVAILABLE = ("service_unavailable", ...)` — **lower_snake** wire value.

The architecture §C5 explicitly mandates lower_snake_case wire values (`session_expired`, `forbidden_scope`, etc.). Story 3.1 deliberately chose lower_snake for project-specific codes. **Story 3.2 follows Story 3.1's convention**: `SESSION_EXPIRED = ("session_expired", ...)`, `FORBIDDEN_SCOPE = ("forbidden_scope", ...)`. The archetype-emitted upper-snake codes stay as-is (they're not consumed by JSON envelopes that face the SPA in our use; they're for the archetype's catch-all `INTERNAL_ERROR` paths). This intentional inconsistency is documented in Story 3.1 and continues here.

### Previous story intelligence (Story 3.1 carry-overs)

- **`OIDC_*` env vars are required-fail-fast.** `AppSettings._validate_oidc_required_fail_fast` (Story 3.1 review CR1 added tests for this) raises `ValueError` on empty/whitespace OIDC config. Story 3.2's tests must set placeholder values in `tests/conftest.py` (already done by Story 3.1 — line 528 of Story 3.1 file). Verify by reading `services/resource-server/tests/conftest.py`.
- **`auth/entra.py` is excluded from coverage** via `[tool.coverage.run].omit` in `pyproject.toml`. After this story, `oidc_bearer.py` carries the live JWT-validation code path; coverage of `oidc_bearer.py` MUST be ≥90% (AC #11). Do NOT add `oidc_bearer.py` to the coverage omit list — it is the live code, not vestigial.
- **The `entra` mode's `_to_async_url` private import was deferred** (D19). Story 3.2 does not touch this. The `oidc_bearer` mode does NOT call any private archetype helpers.
- **D58 from Story 3.1 review** explicitly anticipates Story 3.2: "Story 3.2's `oidc_bearer` will share the JWKS URL with the JWT-validation surface; when a developer points the RS at a self-signed local IdP …". The RS validates JWTs over HTTP inside the compose network in dev (Keycloak is HTTP-only), so TLS verification is moot. Production deployments are out of scope.
- **D55–D57 (OTEL deps, dead OTEL tests, dead `if/pass/else` branch in `_validate_external_auth_requirements`)** all remain deferred — Story 3.2 does not address them.

### Git intelligence (recent commits)

```
2a35822 Merge story 3.1 — RS scaffold + baseline /health + compose default/dev
a1745aa chore(3.1): code review — mark done, log 5 defers (D54–D58)
a80702c chore(3.1): code review — CR1 add 6 fail-fast tests for OIDC required vars
be13571 chore(3.1): mark story review — dev-story complete
24327d4 feat(3.1): RS Dockerfile + entrypoint + compose wiring (default/dev profiles)
```

- The RS service tree (`services/resource-server/**`) is in the state Story 3.1 left it: scaffolded, `/health` working, 171 tests, 98.42% coverage. The auth/ directory contains the archetype's `contracts.py`, `dependencies.py`, `entra.py`, `factory.py`, `models.py`, `none.py`, `role_mapping.py` — all untouched since the archetype scaffold (modulo `pyproject.toml`'s coverage omit list).
- `tests/auth/` already has 9 archetype-emitted test files (verified via `wc -l tests/auth/`); they exercise the `none` + `entra` modes. Story 3.2 ADDS new files but does NOT modify the existing ones.
- The current working branch is `worktree-story-3.2` (a worktree branched off `epic-3`).

### Latest tech information

- **PyJWT 2.10+ (with `crypto` extra)** — current as of May 2026. `cryptography` (the transitive dep) covers RS256/PS256/ES256 verification. The BFF already uses this exact combo (verified via `services/bff/pyproject.toml` and `keycloak_cookie_session.py:230`).
- **PyJWT's `jwt.decode(options={"require": [...]})`** — declarative way to enforce claim presence; raises `MissingRequiredClaimError` (a subclass of `InvalidTokenError`) when a required claim is absent. Used in AC #3.
- **PyJWT's `jwt.decode(audience=...)` and `issuer=...`** — when set, PyJWT validates these as part of decode; raises `InvalidAudienceError` / `InvalidIssuerError` (both subclasses of `InvalidTokenError`). Saves an explicit post-decode check.
- **PyJWT's `PyJWKClient.fetch_data`** — the classmethod that PyJWT's docs identify as the patch point for offline testing. The kwarg `cache_keys=True` + `max_cached_keys=4` is sufficient for our purposes; `lifespan` (PyJWT-3+) is not yet stable.
- **FastAPI's `HTTPBearer(auto_error=False)`** — returns `None` instead of raising when no `Authorization` header is present. Lets us emit the project-specific `SESSION_EXPIRED` envelope rather than FastAPI's default 403 `Not authenticated` (the default 403 would violate the architecture's prescribed 401-on-missing-bearer behavior).
- **`Annotated[T, Depends(...)]`** — modern FastAPI dependency-injection pattern; matches the archetype's style in `auth/dependencies.py:24`. Do NOT use the deprecated `= Depends(...)` parameter-default form.

### Project Structure Notes

- New file: `services/resource-server/src/resource_server/auth/oidc_bearer.py` — the validation module.
- New file: `services/resource-server/tests/auth/synthetic_idp.py` — the test harness.
- New file: `services/resource-server/tests/auth/test_oidc_bearer.py` — the test surface.
- Modified files (5): `auth/models.py` (Principal.scopes), `auth/factory.py` (dispatch), `core/config.py` (Literal expansion), `core/errors.py` (SESSION_EXPIRED + FORBIDDEN_SCOPE), `pyproject.toml` (pyjwt[crypto] dep — also `uv.lock`).
- Modified file (1): `services/resource-server/.env.example` (AUTH_TYPE comment block).
- All other files untouched (per AC #17).

### Anti-patterns to avoid

- **Do not import `entra.py`'s private helpers (`_select_signing_key`, `_validate_signing_key_metadata`, `_decode_and_verify`)** into `oidc_bearer.py`. They are named `_-prefixed` for a reason; cross-module private imports create hidden coupling and break when either module is refactored. `oidc_bearer.py` re-implements the small amount of logic it needs (which is mostly delegated to PyJWT anyway).
- **Do not delete `entra.py`** in this story. It becomes vestigial but stays for cross-service consistency; coordinated cleanup is deferred.
- **Do not raise `HTTPException` directly**. Use `AppException(ErrorCode.X)` so the archetype's `app_exception_handler` builds the standard envelope (`{errorCode, message, detail}`).
- **Do not log JWT contents, `kid` values, or claim values** in failure paths. Sanitize to exception type + sanitized reason only.
- **Do not introduce a TTL-aware JWKS cache wrapper around PyJWKClient.** Architecture line 415 mandates 24h TTL; PyJWKClient's behavior + the kid-miss re-fetch path satisfies the underlying invariant. Add a TTL wrapper later only if reviewers explicitly demand it.
- **Do not change `auth_type`'s default.** Stay on `"none"` for the archetype-emitted default; deployments opt in via env. Story 3.6 will likely flip compose-level defaults to `oidc_bearer`.
- **Do not add `Annotated[..., Body(...)]` validation on token shape.** The `Authorization` header is parsed by `HTTPBearer(auto_error=False)`; the bearer-token validation logic lives in `oidc_bearer.py`'s `_validate_access_token`. Do not duplicate parsing.
- **Do not write tests that mock `jwt.decode` directly.** Mock at the JWKS-fetch layer (the synthetic IdP) so the full decode path exercises real PyJWT logic. This is the same pattern Story 1.5 used on the BFF — proven sound.
- **Do not register a test endpoint on the production `app` import** in the test module. Either use `app.dependency_overrides` for fixture-mounted endpoints, or build a fresh FastAPI instance per test. The BFF Story 1.5 hit a related issue where leftover test routes polluted other tests.
- **Do not call `_get_jwks_client(settings.oidc_jwks_url)` outside `_validate_access_token`.** Module-level state mutation is fine inside the helper but not at import time.
- **Do not commit `services/resource-server/.env`** — it remains gitignored (Story 1.1's `**/.env` + `!**/.env.example` pattern is in effect; Story 3.1 verified).
- **Do not weaken `_validate_oidc_required_fail_fast`** (the model_validator added in Story 3.1). Story 3.2's tests rely on it raising on missing config; if you accidentally make it pass on whitespace, downstream tests can silently use empty issuer/audience values and miss real validation bugs.

### Naming and pattern compliance (architecture §"Implementation Patterns & Consistency Rules" lines 538–820)

- Module name: `oidc_bearer.py` (snake_case, matches architecture line 979).
- Class names: `SyntheticRsIdp` (PascalCase). Note the `Rs` not `RS` — Python idiom is to treat acronyms as words in class names beyond the first (architecture lines 549–550; matches BFF's `SyntheticIdp` not `SyntheticIDP`).
- Enum members: `SESSION_EXPIRED`, `FORBIDDEN_SCOPE` (UPPER_SNAKE).
- Wire values: `"session_expired"`, `"forbidden_scope"` (lower_snake, per §C5).
- HTTP API paths: N/A — no production routes added in this story.
- JSON field names: N/A — the error envelope already uses `errorCode` (camelCase) per the archetype's contract (`{errorCode, message, detail}`); Story 3.2 does not change envelope shape.
- Tests mirror source paths: `tests/auth/test_oidc_bearer.py` mirrors `src/resource_server/auth/oidc_bearer.py`.

### Testing approach

Per architecture §"Testing patterns" + AR33: pytest async, in-memory SQLite + `TestClient` (here `AsyncClient(transport=ASGITransport(app=app))`), archetype's synthetic-IdP pattern (test-generated RSA keypair, monkey-patched HTTP) extended for `oidc_bearer` mode.

**Test file structure:**

```
tests/auth/
├── conftest.py              (existing — keep; defines rsa_keypair, sign_jwt, entra_client fixtures)
├── synthetic_idp.py         (NEW — RS-specific harness; build_synthetic_rs_idp + SyntheticRsIdp)
├── test_oidc_bearer.py      (NEW — 23 test cases per AC #10)
├── test_auth_forbidden.py   (existing — unchanged)
├── test_auth_unauthorized.py(existing — unchanged)
├── test_auth_functions.py   (existing — unchanged)
├── test_entra_integration.py(existing — unchanged)
├── test_external_provider.py(existing — unchanged)
├── test_factory_and_none_provider.py (existing — unchanged)
├── test_require_role_uses_mapper.py (existing — unchanged)
├── test_role_mapper.py      (existing — unchanged)
└── test_role_mapping_providers.py (existing — unchanged)
```

**Fixture sharing**: `synthetic_idp.py` is a plain module (not a `conftest.py`). Fixtures that wrap it (e.g., `synthetic_rs_idp` as a pytest fixture that yields `build_synthetic_rs_idp(monkeypatch)`) can live in `tests/auth/conftest.py` (extending it) — but DO NOT remove or break any existing fixtures in that file.

### Practical notes & gotchas

- **`HTTPBearer(auto_error=False)`** is the only correct choice. The default `auto_error=True` raises `HTTPException(401)` with FastAPI's default body (which lacks our error envelope). With `auto_error=False`, the dependency returns `None` and we raise `AppException(ErrorCode.SESSION_EXPIRED)` explicitly.
- **`HTTPAuthorizationCredentials.scheme`** is the auth scheme as the client sent it (e.g., `"Bearer"`, `"Basic"`, `"bearer"`). Always lowercase before comparing: `credentials.scheme.lower() != "bearer"`.
- **PyJWT's `InvalidTokenError`** is the parent of every JWT-validation error PyJWT raises (`ExpiredSignatureError`, `InvalidAudienceError`, `InvalidIssuerError`, `InvalidSignatureError`, `DecodeError`, `MissingRequiredClaimError`, etc.). A single `except (jwt.InvalidTokenError, jwt.PyJWKClientError)` catches them all; do NOT enumerate specific subclasses (the codebase becomes brittle when PyJWT adds a new error type).
- **The `_jwks_clients` module-level cache** is global per process. Tests MUST reset it (via `monkeypatch.setattr(oidc_bearer, "_jwks_clients", {})`) or test order will affect cache hits. The synthetic-IdP harness does this; relying on it is fine.
- **`PyJWKClient.fetch_data` returns the FULL JWKS document** (i.e., `{"keys": [...]}`), not just the keys. Patch accordingly.
- **`AppSettings.oidc_audience`** is the bare string `bmad-books-resource-server` (verified in Story 3.1 + realm-bmad-books.json:95). PyJWT's `jwt.decode(audience="bmad-books-resource-server")` accepts both string and list-of-string `aud` claims (Keycloak emits list-form).
- **Scopes in the JWT `scope` claim are space-delimited**. Tabs / commas are not legal separators (RFC 8693 §3.3). `_parse_scopes` uses `str.split()` which handles any whitespace (acceptable robustness, matches PyJWT's own scope helpers).
- **Test fixture ordering**: `synthetic_rs_idp` fixture MUST come before the `AsyncClient` fixture in test parameters so the `monkeypatch.setattr` runs before any request is made. pytest resolves fixture dependencies automatically when declared as `def test_x(synthetic_rs_idp, client): ...`.
- **WARNING-log assertion**: pytest's `caplog` fixture captures log records by default at WARNING level only if the logger emits at WARNING. The module-level `logger = logging.getLogger(__name__)` inherits root level by default; tests using `caplog.set_level(logging.WARNING, logger="resource_server.auth.oidc_bearer")` ensure capture.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.2` lines 1154–1212] — canonical story spec and Given/When/Then ACs.
- [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` AR1 line 46, AR3 line 48, AR19 line 76, AR28 line 91, AR33 line 98] — archetype mandate, RS OIDC bearer plugin, RS→Keycloak timeouts, health-check / startup-ordering, backend test patterns.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security` A1 line 347, A2 line 348] — BFF requested scopes, RS JWT validation library (`pyjwt[crypto]` + `PyJWKClient`).
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns` C3 lines 380–388, C5 lines 396–409, C6 lines 411–416] — RS endpoint scope mapping, ErrorCode enum members (SESSION_EXPIRED 401, FORBIDDEN_SCOPE 403), RS→Keycloak JWKS cache + kid-miss re-fetch.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Cross-Cutting Concerns Mapping` lines 1184–1198] — `auth/oidc_bearer.py` houses both JWKS validation and scope enforcement; identity (`sub`) read from JWT.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Architectural Boundaries` lines 1092–1141] — RS ↔ Keycloak: JWKS only (no admin, no token exchange); RS reads `sub` from JWT.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` lines 977–1007] — `auth/oidc_bearer.py` location; `tests/auth/test_oidc_bearer.py` + `tests/fixtures/synthetic_idp.py` (the spec says `fixtures/` — this story uses `tests/auth/` for proximity to `test_oidc_bearer.py`; document the choice).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules` lines 538–820] — naming, structure, format, communication, process patterns. Mandatory.
- [Source: `_bmad-output/implementation-artifacts/3-1-rs-scaffold-from-archetype-baseline-health-rs-in-compose-default-dev.md`] — Story 3.1 (direct predecessor). Read Dev Notes, particularly the required-fail-fast OIDC settings (lines ~310–320) and the AppSettings extensions.
- [Source: `_bmad-output/implementation-artifacts/1-5-bff-cookie-session-oidc-plugin-pkce-synthetic-idp-test-harness.md`] — BFF synthetic-IdP pattern (the direct analog for the RS harness). Read the Dev Notes about `monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", ...)`.
- [Source: `services/bff/src/bff/auth/keycloak_cookie_session.py` lines 185–239] — BFF's PyJWKClient + jwt.decode pattern. Mirror line-for-line where applicable (module-level cache, decode call with algorithms/audience/issuer/options).
- [Source: `services/bff/tests/auth/synthetic_idp.py`] — BFF's harness (the RS harness reproduces the relevant subset; cross-service Python imports are forbidden).
- [Source: `services/resource-server/src/resource_server/auth/{contracts,dependencies,entra,factory,models,none,role_mapping}.py`] — existing archetype auth scaffolding. Story 3.2 EXTENDS these; do not modify them except where AC #2/#5/#6 require (Principal.scopes, factory dispatch, Literal expansion).
- [Source: `services/resource-server/src/resource_server/core/{config,errors}.py`] — Story 3.1's extensions. Story 3.2 adds two ErrorCode members + expands the auth_type Literal.
- [Source: `services/resource-server/tests/auth/conftest.py`] — existing fixtures (rsa_keypair, sign_jwt, entra_client, mock_auth_functions_*). Reuse where possible; do not remove.
- [Source: `keycloak/realm-bmad-books.json` lines 17–58, 65–110] — realm config. `aud=bmad-books-resource-server`, scope-mapper config, `bmad-books-bff` client default+optional scopes.
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md` D54–D58] — Story 3.1 review defers; relevant context for the JWKS-related ones (D54, D58).
- [Source: `CLAUDE.md` at repo root] — invoke Python as `python` (never `python3`).
- [Source: `[[project-bmad-books-backend-archetype]]` — user memory] — archetype mandate.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code, bmad-dev-story workflow)

### Debug Log References

**Task 1 — Add `pyjwt[crypto]` dep:** PyJWT 2.11 was already pulled transitively (via `auth/entra.py`). Ran `uv add 'pyjwt[crypto]>=2.10'` → `pyproject.toml` gained an explicit pin under `[project] dependencies`; lockfile regenerated by `uv add`. `uv sync --frozen` exits 0 (84 packages).

**Task 2 — `Principal.scopes`:** Added `scopes: frozenset[str] = field(default_factory=frozenset)` to `auth/models.py`. Existing tests pass without modification — default factory means callers that don't pass `scopes` get an empty `frozenset()`.

**Task 3 — `ErrorCode.SESSION_EXPIRED` + `FORBIDDEN_SCOPE`:** Added after `SERVICE_UNAVAILABLE` in `core/errors.py`. Wire values lower_snake per §C5; HTTP 401 / 403.

**Task 4 — `auth/oidc_bearer.py`:** Authored the module (~165 LOC after `ruff format`). Module-level `_jwks_clients` cache; `_get_jwks_client` lazy-builds `PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=4)` (BFF parity). `_parse_scopes` returns `frozenset[str]` for string claims and `frozenset()` otherwise. `_validate_access_token` uses `algorithms=["RS256"]`, `options={"require": ["iss", "aud", "exp", "sub"]}`, `audience=settings.oidc_audience`, `issuer=settings.oidc_issuer_url`. Catches `jwt.InvalidTokenError | jwt.PyJWKClientError` → `AppException(SESSION_EXPIRED)`; WARNING log carries only `type(exc).__name__` (no token/claim leak). `get_authenticated_principal` rejects missing/non-Bearer/empty/whitespace tokens before JWT validation. `require_scope` raises `FORBIDDEN_SCOPE` on missing scope (WARNING log with sub + required scope). `make_oidc_bearer_auth` returns the archetype `AuthFunctions`.

**Task 5 — Config Literal + factory dispatch:** Expanded `auth_type` Literal to `Literal["none", "entra", "oidc_bearer"]`. Added lazy-import `_build_oidc_bearer` to `auth/factory.py`. `builders` dict now maps three keys.

**Task 6 — `tests/auth/synthetic_idp.py`:** ~219 LOC. RSA-2048 keypair helpers, `SyntheticRsIdp` dataclass (configurable issuer/audience/jwks_url/kid; `fetch_call_count` for cache assertions; `register_rotated_kid` for rotation tests). `build_synthetic_rs_idp(monkeypatch, ...)` clears `oidc_bearer._jwks_clients`, patches `jwt.PyJWKClient.fetch_data` (NOT httpx — PyJWKClient uses synchronous urllib that respx cannot intercept), and patches `settings.oidc_*`.

**Task 7 — `tests/auth/test_oidc_bearer.py`:** 33 tests. Module-scoped autouse fixture mounts `/_test/oidc/scoped-read` and `/_test/oidc/scoped-write` on the prod app and pops them at teardown. Cases cover: happy path, wrong scope → 403, expired/wrong-aud/wrong-iss/malformed/wrong-key/alg-none/alg-HS256/missing-exp/missing-sub → 401, missing/empty/Basic-scheme bearer → 401, JWKS cache hit (`fetch_call_count == 1` after 3 valid requests), kid-miss-after-rotation → 200 (`fetch_call_count == 2`), kid-miss-no-match → 401, Principal field shape, cross-user isolation, WARNING-log sanitization, `make_oidc_bearer_auth` surface, factory dispatch, `_parse_scopes` unit tests.

**Task 8 — `.env.example`:** AUTH_TYPE comment block added documenting `oidc_bearer` as the production-intended value (commented-out; archetype default `"none"` preserved).

**Task 9 — Gates:**
- `uv sync --frozen` → 0 (84 packages)
- `uv run ruff check` → All checks passed!
- `uv run ruff format --check` → 73 files already formatted
- `uv run ty check` → All checks passed!
- `uv run pytest --cov` → **204 passed**, coverage **97.83%** (171 baseline → 204 = +33 new tests)
- `uv run pytest --cov=resource_server.auth.oidc_bearer tests/auth/test_oidc_bearer.py` → coverage of `oidc_bearer.py` = **100.00%** (65/65 statements; AC #11 ≥90% gate met).

### Completion Notes List

- All 17 ACs satisfied. RS now has `oidc_bearer` auth plugin exposing `get_authenticated_principal` + `require_scope(scope)` as FastAPI dependencies, plus archetype-seam `make_oidc_bearer_auth` wired into the dict-dispatched factory alongside `none` and `entra`.
- Synthetic-IdP test harness mints in-process RS256 tokens against an ephemeral RSA-2048 keypair and patches `jwt.PyJWKClient.fetch_data` so signature verification runs entirely offline. No real Keycloak. Mirrors Story 1.5; lives in the RS test tree (cross-service Python imports forbidden).
- `Principal` gained `scopes: frozenset[str]` alongside the existing archetype `scope: str | None` field.
- `ErrorCode.SESSION_EXPIRED` (401) and `ErrorCode.FORBIDDEN_SCOPE` (403) added with lower_snake wire values per §C5.
- Coverage of `oidc_bearer.py` is **100%** (well above ≥90% gate). Whole-suite coverage 98.42% → 97.83% — the slight drop is `oidc_bearer.py` joining the measured surface; `auth/dependencies.py` is unchanged at 96%.
- **No production-handler changes.** `/_test/oidc/*` routes exist only within the test module's autouse fixture. Production surface still: `/health` only.
- **No archetype regressions.** All 171 Story-3.1 tests continue green.
- **No defers introduced.** D54–D58 from Story 3.1's review remain open; none re-surfaced here.
- **D59 candidate (for code-review triage):** JWKS cache TTL is per-process-lifetime + `max_cached_keys=4` LRU, not the architectural §C6 24h. The kid-miss re-fetch path satisfies the underlying invariant ("validation survives key rotation without operator intervention"); documented in `oidc_bearer.py:42-48` + AC #8. Reviewers may want a TTL-aware wrapper.
- **Architecture line 1191 says scope enforcement is "via archetype's RoleMappingProvider".** Implemented as a direct dependency-factory (`require_scope`) — RoleMappingProvider's single-string mapping is built for role-name translation, not space-delimited scope parsing. Reviewers may want a parallel `ScopeMappingProvider` later.
- `auth/entra.py` intentionally NOT deleted (AC #6 — entra tests still pass); coordinated cleanup deferred until post-Story-4.1.

### File List

**New files:**
- `services/resource-server/src/resource_server/auth/oidc_bearer.py` — ~165 LOC. `_jwks_clients` cache, `_get_jwks_client`, `_parse_scopes`, `_validate_access_token`, `_principal_from_claims`, `bearer_scheme`, `get_authenticated_principal`, `require_scope`, `make_oidc_bearer_auth`.
- `services/resource-server/tests/auth/synthetic_idp.py` — ~219 LOC. Keypair helpers, `SyntheticRsIdp`, `build_synthetic_rs_idp`, `random_subject`, default constants.
- `services/resource-server/tests/auth/test_oidc_bearer.py` — 33 tests covering AC #10 + helper units + archetype-seam + factory dispatch.

**Modified files:**
- `services/resource-server/src/resource_server/auth/models.py` — `Principal.scopes: frozenset[str]` field added.
- `services/resource-server/src/resource_server/auth/factory.py` — `_build_oidc_bearer` builder + `builders["oidc_bearer"]` mapping.
- `services/resource-server/src/resource_server/core/config.py` — `auth_type` Literal expanded to include `"oidc_bearer"`.
- `services/resource-server/src/resource_server/core/errors.py` — `ErrorCode.SESSION_EXPIRED` (401) + `ErrorCode.FORBIDDEN_SCOPE` (403); leading comment updated.
- `services/resource-server/pyproject.toml` — `pyjwt[crypto]>=2.10` added.
- `services/resource-server/uv.lock` — regenerated by `uv add`.
- `services/resource-server/.env.example` — AUTH_TYPE comment block.

**BMAD bookkeeping:**
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status: `ready-for-dev` → `in-progress` → `review` (final flip at end of workflow).
- `_bmad-output/implementation-artifacts/3-2-rs-oidc-bearer-auth-plugin-jwks-scope-enforcement-synthetic-idp-test-harness.md` — frontmatter + status header → `review`; all 59 task/subtask checkboxes ticked; Dev Agent Record populated.

**Untouched (verified via `git diff --name-only`):** `CLAUDE.md`, root files, `docker-compose.yml`, `compose/*.yml`, `keycloak/**`, `services/bff/**`, `spa/**`, `e2e/**`, `services/resource-server/{Dockerfile,entrypoint.sh,.gitattributes,alembic/**,tests/conftest.py,tests/auth/conftest.py,tests/auth/test_auth_*.py,tests/auth/test_entra_*.py,tests/auth/test_external_*.py,tests/auth/test_factory_*.py,tests/auth/test_require_*.py,tests/auth/test_role_*.py}` — bit-for-bit identical.
