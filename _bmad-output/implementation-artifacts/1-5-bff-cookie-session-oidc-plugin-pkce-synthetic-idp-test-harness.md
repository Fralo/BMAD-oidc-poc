# Story 1.5: BFF cookie-session OIDC plugin (PKCE) + synthetic-IdP test harness

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an unauthenticated visitor,
I want to be able to complete an Authorization Code + PKCE round-trip against Keycloak through the BFF,
so that I end up with an HttpOnly session cookie while the BFF holds my access/refresh/id tokens server-side.

## Acceptance Criteria

**AC1 — Module layout & router registration.** The `services/bff/src/bff/auth/` package exists (new), containing at minimum: `__init__.py`, `pkce.py` (PKCE verifier/challenge helpers), and `keycloak_cookie_session.py` (the Authlib-based OIDC client + state-id-cookie HMAC signer). The auth-flow HTTP surface lives at `services/bff/src/bff/api/auth.py` (new) exposing `GET /auth/login` and `GET /auth/callback`. `bff/main.py` registers the new router AFTER `health_router` / `me_router` / `v1_router` (paths are non-versioned per architecture §C1). The session service that owns `sessions` / `auth_states` row lifecycle lives at `services/bff/src/bff/services/session_service.py` (new — first member of the `services/` subpackage; `services/__init__.py` is empty). [Source: epics.md#Story 1.5 lines 360–366; architecture.md#Complete Project Directory Structure lines 904–913; architecture.md#API & Communication Patterns C1–C2 lines 358–377; architecture.md#Cross-Cutting Concerns Mapping lines 1188–1190.]

**AC2 — `GET /auth/login` builds the authorize redirect (PKCE).** Given an unauthenticated client hits `GET /auth/login?return_to=/books` with redirects disabled, the BFF responds **302** to `${OIDC_AUTHORIZE_URL_BROWSER}/protocol/openid-connect/auth` (see D2/D8 split-issuer in Dev Notes — the **browser-facing** authorize URL, not the back-channel one) with query parameters: `client_id=${OIDC_CLIENT_ID}`, `response_type=code`, `scope=openid offline_access reading-speed:read reading-speed:write`, `code_challenge_method=S256`, `code_challenge` (base64url-no-pad of SHA-256 of a fresh `code_verifier`), `state` (CSRF random, ≥32 bytes of entropy), `nonce` (≥32 bytes of entropy), and `redirect_uri=${BFF_BASE_URL}/auth/callback`. The BFF persists an `auth_states` row with `id` = `secrets.token_urlsafe(32)`, the freshly generated `code_verifier`, `state`, `nonce`, the validated `return_to`, and `expires_at = now + 5 min`. The BFF sets a signed state-id cookie (name: constant `BFF_AUTH_STATE_COOKIE_NAME = "bff_auth_state"` — define alongside `bff_session` / `bff_csrf` constants): `HttpOnly`, `Max-Age=300`, `SameSite=Lax`, `Path=/`, `Secure` per `BFF_SESSION_COOKIE_SECURE`, value = the `auth_states.id` signed via `itsdangerous.URLSafeTimedSerializer` keyed on `BFF_CLIENT_SECRET` (HMAC-SHA256). [Source: epics.md#Story 1.5 lines 363–366; architecture.md#Authentication & Security A1 line 347 (scope list, "openid makes it an OIDC flow, offline_access ensures a refresh token"); architecture.md#Authentication & Security A3 line 349 (signed state-id cookie).]

**AC3 — `return_to` validation (closes D33).** The `return_to` query parameter is validated **before** persisting the `auth_states` row: it MUST be a path-only string starting with `/` and NOT starting with `//` (network-relative open-redirect block) AND NOT containing a `:` before the first `/` (scheme-prefixed open-redirect block). Validation rejects `return_to` whose length exceeds 1024 chars. On validation failure, the row's `return_to` is set to the safe default `/` (NOT a 4xx response — a malformed `return_to` falls back gracefully rather than blocking login). Tests cover at minimum: `/books`, `/`, `/foo?bar=baz`, `//evil.example`, `https://evil.example`, `javascript:alert(1)`, empty string, missing query param, and a 2000-character path. [Source: deferred-work.md#D33 lines 263–269 — open-redirect vector vector explicitly assigned to this story.]

**AC4 — `GET /auth/callback` success path.** Given an `auth_states` row exists for `state=S` with `code_verifier=V` and `return_to=R`, when the BFF receives `GET /auth/callback?code=C&state=S` carrying the matching state-id cookie (HMAC verifies AND its row id matches `auth_states.id`), and the IdP's `/token` endpoint exchanges `code=C` + `code_verifier=V` for an access/refresh/id-token triple, then:
1. The BFF validates the id_token: signature via the IdP's JWKS (`OIDC_JWKS_URL`), `iss` claim equals the BFF's expected back-channel issuer (`OIDC_ISSUER_URL`), `aud` claim contains `OIDC_CLIENT_ID`, `exp` is in the future, `nonce` claim equals `auth_states.nonce`. Any failure → 400 `auth_state_invalid` (see AC5).
2. The BFF generates `session_id = secrets.token_urlsafe(32)` AND `csrf_secret = secrets.token_urlsafe(32)`.
3. The BFF persists a `sessions` row: `id=session_id`, `sub`=id_token `sub` claim, `access_token`, `refresh_token`, `id_token`, `expires_at` = datetime from id_token `exp` (UTC-aware; convert via `datetime.fromtimestamp(exp, UTC)`), `csrf_secret`, `created_at` / `updated_at` auto-populated.
4. The BFF sets the session cookie (`BFF_SESSION_COOKIE_NAME`): `HttpOnly`, `Secure` per `BFF_SESSION_COOKIE_SECURE`, `SameSite=Lax`, `Path=/`, value = `session_id` (opaque, NOT a JWT). NO `Max-Age` (session cookie — lifetime is enforced server-side via `sessions.expires_at`, per architecture A4 "opaque 256-bit value").
5. The BFF sets the csrf_token cookie (`BFF_CSRF_COOKIE_NAME`): **non-`HttpOnly`** (SPA must read it for double-submit per architecture A5), `Secure` per env, `SameSite=Lax`, `Path=/`, value = `csrf_secret`. No `Max-Age` (same lifetime contract as session).
6. The BFF deletes the consumed `auth_states` row.
7. The BFF sets `Set-Cookie` to clear the state-id cookie (`Max-Age=0`).
8. The BFF responds **302** with `Location: <return_to from auth_states>` (already validated at AC3).

[Source: epics.md#Story 1.5 lines 368–375; architecture.md#Authentication & Security A4–A5 lines 350–351; architecture.md#API & Communication Patterns C1 line 360 (non-versioned `/auth/*`).]

**AC5 — `GET /auth/callback` failure paths (all map to `auth_state_invalid` envelope).** The BFF responds **400** with JSON body `{"errorCode": "auth_state_invalid", "message": "Authorization state invalid", "detail": null}` AND creates NO `sessions` row in each of these cases:
- Missing `state` query parameter.
- Missing or unparseable state-id cookie (no cookie at all, malformed value, OR `itsdangerous` signature mismatch).
- State-id cookie's row id does not exist in `auth_states` (replay of a consumed row).
- The `auth_states` row's `expires_at` is in the past (expired row — delete it in the same transaction so the next attempt is clean).
- The `auth_states` row's `state` column does NOT equal the `state` query parameter (cookie-vs-query mismatch).
- The synthetic IdP's `/token` endpoint returns 400 (PKCE `code_verifier` mismatch, expired code, invalid code).
- The id_token signature does not verify against JWKS, OR `iss`/`aud`/`exp`/`nonce` claim validation fails.
- The JWKS endpoint is unreachable at callback time.

In every failure case, the BFF deletes the matched `auth_states` row (if any) AND clears the state-id cookie (`Max-Age=0`). The state-id cookie is cleared even when no row matched (defensive — the cookie is now useless). No PII / token material appears in the error response. [Source: epics.md#Story 1.5 lines 377–384; architecture.md#Format Patterns lines 682–684 (`auth_state_invalid` → HTTP 400); architecture.md#C5 line 407.]

**AC6 — `AUTH_STATE_INVALID` ErrorCode added.** `services/bff/src/bff/core/errors.py` gains a new enum member exactly: `AUTH_STATE_INVALID = ("auth_state_invalid", "Authorization state invalid", 400)`. Wire-value is lower_snake_case per the documented contract (architecture line 560 + line 407 of the contract code-block). The existing `SESSION_EXPIRED` / `SERVICE_UNAVAILABLE` / `INTERNAL_ERROR` / `VALIDATION_ERROR` / `BAD_REQUEST` / `NOT_FOUND` / `UNAUTHORIZED` / `FORBIDDEN` enum members are NOT touched. **Do NOT preemptively add `CSRF_INVALID`** — that is Story 1.6's job (architecture §C5 line 408). [Source: architecture.md#C5 lines 396–409; services/bff/src/bff/core/errors.py:9–25.]

**AC7 — `GET /api/me` becomes session-cookie-driven.** The current `services/bff/src/bff/api/me.py` always returns 401 (Story 1.3 placeholder). After this story:
- With NO session cookie OR session cookie matching no `sessions` row OR matched row's `expires_at` in the past → 401 with `errorCode: "session_expired"` envelope (unchanged wire contract).
- With a valid session cookie → 200 with body `{"sub": "<sub claim>", "preferred_username": "<preferred_username from id_token>"}` (preferred_username decoded from the stored `id_token` JWT claims; do NOT re-fetch userinfo). Read claims via PyJWT's `decode(..., options={"verify_signature": False})` — the id_token was already signature-verified at callback time; re-verification per request is wasted work AND would require live JWKS. Document this with a one-line comment on the decode call.
- Expired sessions are deleted lazily on next access (single DELETE in the same handler when `expires_at < now`); the response is still 401 with `session_expired`.
- This is the FIRST consumer of the `sessions` table created in Story 1.4. The Story 1.3 docstring on `me.py` ("always returns 401; the cookie-session OIDC plugin (Story 1.5) is what actually populates and validates the cookie") becomes accurate-as-of-now — rewrite the module docstring to reflect post-1.5 reality. [Source: epics.md#Story 1.5 lines 386–388; services/bff/src/bff/api/me.py (current placeholder).]

**AC8 — Synthetic IdP test harness.** `services/bff/tests/auth/synthetic_idp.py` (new) provides a single pytest fixture (or fixture factory) that:
- Generates an in-process RSA-2048 keypair on construction (use `cryptography` library — already a transitive dep via `pyjwt[crypto]`).
- Exposes the public key as a JWKS dict matching the OIDC `/certs` shape: `{"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": "test-key-1", "n": "...", "e": "AQAB"}]}`.
- Provides handler stubs for: `/authorize` (returns 302 with a generated `code` echoed back — tests don't actually click "Log in"), `/token` (validates `code_verifier` matches the stored challenge for the issued `code`; on match returns access/refresh/id-tokens; on mismatch returns 400 with `{"error": "invalid_grant"}`), `/revocation` (records the revoked token; returns 200; used by Story 1.7), `/end_session` (records call; returns 200; used by Story 1.7), and `/.well-known/openid-configuration` (returns discovery doc declaring `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `end_session_endpoint`, `revocation_endpoint`, and `issuer` matching `OIDC_ISSUER_URL`).
- Mounts these handlers via `respx` (preferred) or `httpx.MockTransport` to intercept BFF → IdP traffic without binding a real port. **Choose `respx`** unless a load-bearing reason emerges — it's the standard async httpx mocking library and the BFF already depends on httpx 0.28+ (`pyproject.toml:12`).
- Signs id_tokens with the test private key using `python-jose` OR PyJWT — match whichever library the BFF uses for verification (use PyJWT to stay aligned with architecture A2 line 348). Default claims: `iss=OIDC_ISSUER_URL`, `aud=OIDC_CLIENT_ID`, `sub="test-sub-<random>"`, `preferred_username="testuser"`, `exp=now + 5 min`, `iat=now`, `nonce=<echoed from authorize>`. Provide a `make_id_token(claims_override={})` helper for tests that need malformed tokens (wrong `aud`, expired, forged signature with a *different* key, etc.).
- Lives under `tests/auth/` (NOT `tests/fixtures/synthetic_idp.py` — architecture's spec was `tests/fixtures/synthetic_idp.py` per line 951, but Story 1.4 set the precedent that tests mirror source paths; `tests/auth/` matches the new `src/bff/auth/` package). Document the discrepancy in the Dev Notes "Path discrepancy" subsection. [Source: epics.md#Story 1.5 lines 361, 391–393; architecture.md#Authentication & Security A2 line 348; architecture.md#Complete Project Directory Structure line 951 (superseded by Story 1.4 precedent).]

**AC9 — Test coverage matrix.** Tests under `services/bff/tests/auth/` cover the scenarios enumerated in epics line 392, expanded to:

| # | Scenario | Asserted |
|---|---|---|
| 1 | Happy path (synthetic IdP) | 302 → `/authorize`, callback writes `sessions` row, deletes `auth_states` row, sets session+csrf+state-clear cookies, 302 → `/books` |
| 2 | State-cookie missing | 400 `auth_state_invalid`, no session created |
| 3 | State-cookie signature invalid (HMAC tampered) | 400 `auth_state_invalid` |
| 4 | State-cookie / `state` param mismatch | 400 `auth_state_invalid` |
| 5 | PKCE verifier mismatch (synthetic IdP `/token` returns 400) | 400 `auth_state_invalid`, row deleted, state-id cookie cleared |
| 6 | Expired `auth_states` row | 400 `auth_state_invalid`, expired row deleted |
| 7 | Replay of consumed `auth_states` row (already deleted) | 400 `auth_state_invalid` |
| 8 | Missing `state` query param | 400 `auth_state_invalid` |
| 9 | id_token signature invalid (signed with wrong key) | 400 `auth_state_invalid` |
| 10 | id_token `aud` mismatch | 400 `auth_state_invalid` |
| 11 | id_token `iss` mismatch | 400 `auth_state_invalid` |
| 12 | id_token `nonce` mismatch | 400 `auth_state_invalid` |
| 13 | id_token expired | 400 `auth_state_invalid` |
| 14 | JWKS-fetch failure at callback | 400 `auth_state_invalid` |
| 15 | `/auth/login` with no `return_to` → falls back to `/` | 302 issued, callback redirects to `/` |
| 16 | `/auth/login` with `return_to=//evil` → falls back to `/` | callback redirects to `/`, not `//evil` |
| 17 | `/auth/login` with `return_to=https://evil` → falls back to `/` | same |
| 18 | `/auth/login` with `return_to=/books?x=1` → preserved | callback redirects to `/books?x=1` |
| 19 | `/api/me` with no session cookie | 401 `session_expired` |
| 20 | `/api/me` with unknown session id | 401 `session_expired` |
| 21 | `/api/me` with expired session | 401 `session_expired`, expired row deleted |
| 22 | `/api/me` with valid session | 200 `{"sub": "...", "preferred_username": "..."}` |
| 23 | PKCE: `code_verifier` length 43 ≤ len ≤ 128 (RFC 7636 §4.1) | passes generator |
| 24 | PKCE: `code_challenge` = base64url-no-pad(SHA-256(`code_verifier`)) | round-trip verifies |
| 25 | State-id cookie `Max-Age=300` | set on `/auth/login` |
| 26 | Session cookie `HttpOnly`, `SameSite=Lax`, `Path=/` | set on `/auth/callback` |
| 27 | CSRF cookie NOT `HttpOnly`, `SameSite=Lax`, `Path=/` | set on `/auth/callback` (SPA reads it per architecture A5) |
| 28 | `BFF_SESSION_COOKIE_SECURE=true` | both session + csrf cookies carry `Secure` flag |
| 29 | `BFF_SESSION_COOKIE_SECURE=false` | neither carries `Secure` |

Coverage of `src/bff/auth/keycloak_cookie_session.py` AND `src/bff/auth/pkce.py` AND `src/bff/api/auth.py` AND `src/bff/services/session_service.py` is **≥90%** per `[tool.coverage.report] fail_under = 90`. [Source: epics.md#Story 1.5 line 392; services/bff/pyproject.toml:82.]

**AC10 — Dependencies added; gates remain green.** `services/bff/pyproject.toml` `dependencies = [...]` gains exactly:
- `authlib>=1.6.0` (Authlib for OIDC client — architecture A1).
- `pyjwt[crypto]>=2.10.0` (id_token signature verification — architecture A2).
- `itsdangerous>=2.2.0` (signed state-id cookie HMAC).

No version-pin upper bounds (architecture line 75 — "uv.lock committed; no upper-bound pins in pyproject"). `uv sync` regenerates `uv.lock` cleanly. From `services/bff/`:
- `uv sync --frozen` after lock-update → exit 0.
- `uv run ruff check` → clean.
- `uv run ruff format --check` → clean.
- `uv run ty check` → clean.
- `uv run pytest --cov` → all 137 prior tests + new auth tests pass; total coverage ≥ 90%.
- `docker compose --profile default config` → valid.
- `docker compose build bff` → succeeds. [Source: epics.md#Story 1.5 line 394; architecture.md#Backend Starter line 75; architecture.md#Authentication & Security A1–A2 lines 347–348; services/bff/pyproject.toml.]

**AC11 — Browser-vs-container hostname split (closes D2 / D8).** Two new config values are added to `services/bff/src/bff/core/config.py`:
- `oidc_authorize_url_browser: str = ""` — the **browser-facing** authorize URL used in the 302 from `/auth/login`. In compose with the realm config from Story 1.2, this is `http://localhost:8080/realms/bmad-books` (Keycloak emits this in the discovery doc because `KC_HOSTNAME=localhost`). REQUIRED (fail-fast at startup if empty), via a `@model_validator(mode="after")` mirroring the `BFF_CLIENT_SECRET` validator at config.py:106–118.
- `oidc_issuer_url` (existing) remains the **back-channel** issuer URL used for `/token` and `/revocation` POSTs (`http://keycloak:8080/realms/bmad-books` in compose). Used as the expected id_token `iss` claim AND as the back-channel base.

The repo-root `.env.example` is updated to document the split:
```
# OIDC issuer used for back-channel (BFF → Keycloak) token exchange.
# In compose this resolves via Docker DNS to the keycloak container.
OIDC_ISSUER_URL=http://keycloak:8080/realms/bmad-books
# Browser-facing authorize URL — used in the 302 from /auth/login.
# Must resolve from the host browser (Keycloak's `KC_HOSTNAME=localhost`).
OIDC_AUTHORIZE_URL_BROWSER=http://localhost:8080/realms/bmad-books
```
`services/bff/.env.example` mirrors the addition. Story 1.2's realm JSON requires NO change (KC_HOSTNAME=localhost already configured). [Source: deferred-work.md#D2 lines 14–22; deferred-work.md#D8 lines 68–74 — both explicitly assigned to this story.]

**AC12 — D40: state/nonce collision retry path.** The session-service's `create_auth_state(...)` catches `sqlalchemy.exc.IntegrityError` on PK collision (extremely unlikely under 256-bit entropy but a real-world concern per D40) and retries up to 3 times with freshly generated `id` / `state` / `nonce` values before giving up with a 500. **Note:** because Story 1.4 chose NOT to add `unique=True` to `state` / `nonce` columns (D40 decision), only PK (`id`) collision can raise `IntegrityError`. Document this in a one-line comment on the retry loop. [Source: deferred-work.md#D40 lines 319–326.]

## Tasks / Subtasks

- [x] **Task 1: Add new runtime dependencies** (AC: #10)
  - [x] In `services/bff/pyproject.toml` add `authlib>=1.6.0`, `pyjwt[crypto]>=2.10.0`, `itsdangerous>=2.2.0` to `dependencies`. Run `uv lock && uv sync --frozen` from `services/bff/`. Commit `pyproject.toml` AND `uv.lock`.
  - [x] Verify `uv run python -c "import authlib, jwt, itsdangerous; print('ok')"` succeeds.

- [x] **Task 2: Author PKCE helpers** (AC: #2, #9 — rows 23–24)
  - [x] Create `services/bff/src/bff/auth/__init__.py` (empty).
  - [x] Create `services/bff/src/bff/auth/pkce.py` with:
    - `generate_code_verifier() -> str` — returns 43–128-char URL-safe string; use `secrets.token_urlsafe(64)` (yields 86 chars, well within RFC 7636 §4.1 bounds).
    - `compute_code_challenge(verifier: str) -> str` — `base64url-no-pad(SHA256(verifier.encode("ascii")))`. Use `base64.urlsafe_b64encode(...).rstrip(b"=").decode("ascii")`.
    - `S256_METHOD: Final[str] = "S256"` — module constant for the challenge-method query param.
  - [x] No external library — `secrets`, `hashlib`, `base64` are stdlib.
  - [x] Create `services/bff/tests/auth/__init__.py` (empty).
  - [x] Create `services/bff/tests/auth/test_pkce.py` covering: verifier length ∈ [43, 128], challenge is URL-safe (no `+`, `/`, `=`), `compute_code_challenge(known_verifier)` matches a precomputed expected value (RFC 7636 §4.6 worked example), idempotence on the same verifier.

- [x] **Task 3: Author config additions** (AC: #11)
  - [x] In `services/bff/src/bff/core/config.py`:
    - Add `oidc_authorize_url_browser: str = ""` after the existing `oidc_*` block (around config.py:81–84).
    - Add a `@model_validator(mode="after")` `_validate_oidc_authorize_url_browser` mirroring `_validate_bff_client_secret` at config.py:106–118 — fail-fast with a clear message if empty/whitespace.
  - [x] In repo-root `.env.example`: under the `# --- OIDC ---` block, add the new env var with the documenting comment (copy verbatim from AC11). Keep `OIDC_ISSUER_URL` untouched.
  - [x] In `services/bff/.env.example`: mirror the addition under the OIDC section.
  - [x] Update `services/bff/tests/core/test_config.py` to cover the new validator (parametrized: empty / whitespace / valid).
  - [x] Verify `uv run pytest tests/core/test_config.py -v` passes.

- [x] **Task 4: Author `ErrorCode.AUTH_STATE_INVALID`** (AC: #6)
  - [x] In `services/bff/src/bff/core/errors.py`, add (in the BMAD_books project-specific block, after `SESSION_EXPIRED`):
    ```python
    AUTH_STATE_INVALID = ("auth_state_invalid", "Authorization state invalid", 400)
    ```
  - [x] In `services/bff/tests/core/test_errors.py`, add an assertion that `ErrorCode.AUTH_STATE_INVALID.code == "auth_state_invalid"` and `.http_status == 400`.

- [x] **Task 5: Author `SessionService`** (AC: #1, #4 steps 2–3, #5 row-deletion, #7, #12)
  - [x] Create `services/bff/src/bff/services/__init__.py` (empty).
  - [x] Create `services/bff/src/bff/services/session_service.py` with `class SessionService` exposing the following async methods, each taking an `AsyncSession` as its first argument:
    - `async def create_auth_state(self, db, *, return_to: str | None) -> tuple[AuthState, str]` — returns the persisted row AND the freshly generated `code_verifier` (caller will derive challenge). Generates `id` / `state` / `nonce` via `secrets.token_urlsafe(32)`; sets `expires_at = datetime.now(UTC) + timedelta(minutes=5)`. Validates and normalizes `return_to` via the rule in AC3 (delegate to a `_safe_return_to(raw: str | None) -> str` helper in `keycloak_cookie_session.py` so AC3's validation rule lives next to the consumer). On `IntegrityError`, rolls back and retries up to 3 times (AC12).
    - `async def consume_auth_state(self, db, *, state: str) -> AuthState | None` — fetches the row matching `state`, returns it AND deletes it in the same transaction (a single `await db.delete(row); await db.commit()` IS the consumption). Returns `None` if missing OR `expires_at < now` (delete expired row before returning None). Caller compares against the state-id cookie's row id separately.
    - `async def create_session(self, db, *, sub: str, access_token: str, refresh_token: str, id_token: str, expires_at: datetime) -> Session` — generates `session_id = secrets.token_urlsafe(32)` AND `csrf_secret = secrets.token_urlsafe(32)`; persists the row; returns it. IntegrityError retry as above.
    - `async def get_session(self, db, *, session_id: str) -> Session | None` — fetch by `id`. Returns `None` for missing rows. Caller checks `expires_at` separately. **Document the D32 caveat** (bulk `update(Session).values(...)` skips `updated_at` `onupdate`) inline above this method as a one-line comment; this story's call sites are point-mutations and DO trigger the lambda.
    - `async def delete_expired_session(self, db, *, session_id: str) -> None` — DELETE WHERE `id=:session_id` AND `expires_at < now`. Use the indexed `expires_at` column.
  - [x] All `secrets.token_urlsafe(32)` calls live in this service — do NOT scatter them across `auth.py` or `keycloak_cookie_session.py` (single source of opaque-id-generation truth).
  - [x] Create `services/bff/tests/services/__init__.py` (empty).
  - [x] Create `services/bff/tests/services/test_session_service.py` exercising every method against the in-memory session fixture; include happy path, missing row, expired row, IntegrityError retry (use `monkeypatch` to force two `IntegrityError`s before success).

- [x] **Task 6: Author the OIDC client plugin** (AC: #1, #2, #4 step 1)
  - [x] Create `services/bff/src/bff/auth/keycloak_cookie_session.py` containing:
    - Module-level `_serializer(secret: str) -> URLSafeTimedSerializer` factory using `itsdangerous` keyed on `BFF_CLIENT_SECRET`. Salt = `"bff-state-id"`. Max age 5 min.
    - `sign_state_id(serializer, row_id: str) -> str` and `verify_state_id(serializer, signed: str) -> str | None` (returns the row id on success, `None` on tamper / expiry / malformed).
    - `_safe_return_to(raw: str | None) -> str` — AC3 validation. Default `"/"`.
    - `OidcClient` class wrapping Authlib's `httpx_client.AsyncOAuth2Client` (or the equivalent OAuth2 generic client; Authlib's `OAuth2Session` is sync, so use the async variant). Methods:
      - `build_authorize_url(*, authorize_url_browser, redirect_uri, client_id, scopes, state, nonce, code_challenge) -> str` — uses Authlib's `create_authorization_url` (which appends query params correctly).
      - `async def exchange_code(self, *, code: str, code_verifier: str, redirect_uri: str, token_url: str) -> dict` — uses Authlib's `fetch_token` with `grant_type="authorization_code"`. Honors architecture §C6: 5s connect / 10s read; zero retries on 5xx.
      - `async def verify_id_token(self, *, id_token: str, jwks_url: str, expected_issuer: str, expected_audience: str, expected_nonce: str) -> dict` — uses PyJWT's `PyJWKClient(jwks_url).get_signing_key_from_jwt(id_token)` then `jwt.decode(...)` with `algorithms=["RS256"]`, `audience=expected_audience`, `issuer=expected_issuer`, `options={"require": ["iss", "aud", "exp", "nonce", "sub"]}`. After decode, assert decoded `nonce == expected_nonce`. Raises a single `OidcVerificationError` on any failure (caller catches and maps to 400 `auth_state_invalid`).
    - `class OidcVerificationError(Exception): pass` — module-local.
  - [x] **Authlib import note:** Authlib publishes its async client as `authlib.integrations.httpx_client.AsyncOAuth2Client`. The package install name is `authlib` (we did pin it in Task 1). If the import fails after `uv sync`, double-check the package name vs `Authlib` capitalization — pip is case-insensitive, but the import path is lowercase.
  - [x] Configure outbound httpx timeouts on the Authlib client to architecture §C6 values (5s connect, 10s read). Authlib accepts a `timeout=httpx.Timeout(...)` constructor arg.
  - [x] No retries on `/token`. Authlib does not retry by default; do NOT enable retry middleware.

- [x] **Task 7: Author the auth router** (AC: #1, #2, #3, #4, #5)
  - [x] Create `services/bff/src/bff/api/auth.py`:
    - Module-level `router = APIRouter(tags=["Auth"])`.
    - `BFF_AUTH_STATE_COOKIE_NAME = "bff_auth_state"` module constant.
    - Two route handlers:
      - `@router.get("/auth/login")` — depends on `Annotated[AsyncSession, Depends(get_session)]` for DB + `Annotated[AppSettings, Depends(...)]` for config. Reads `?return_to=...` query param. Calls `SessionService.create_auth_state(...)`. Builds challenge from verifier via `pkce.compute_code_challenge`. Calls `OidcClient.build_authorize_url(...)`. Returns a `RedirectResponse(url, status_code=302)` carrying the signed state-id `Set-Cookie`. Use `response.set_cookie(...)` with `httponly=True`, `samesite="lax"`, `secure=settings.bff_session_cookie_secure`, `max_age=300`, `path="/"`.
      - `@router.get("/auth/callback")` — reads `?state=`, `?code=`, reads the state-id cookie via `request.cookies.get(...)`. Implements the AC4/AC5 flow. On error, returns a `JSONResponse` with the `auth_state_invalid` envelope AND a `Set-Cookie` clearing the state-id cookie. On success, returns a `RedirectResponse(return_to, status_code=302)` with the three Set-Cookie headers (state-id cleared, session set, csrf_token set).
    - Use **structured logging** at each branch (INFO for happy path lifecycle: "auth_state_created sub=N/A id=<8chars>...", "session_created sub=<sub>..."; WARN for failure paths: "auth_callback_state_mismatch", "auth_callback_pkce_failed", etc.). Per architecture §"Logging conventions" line 783–788: never log full session ids / cookies / tokens — first-8-chars + ellipsis for correlation.
  - [x] Register in `services/bff/src/bff/main.py`:
    ```python
    from bff.api.auth import router as auth_router
    ...
    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(auth_router)   # NEW — after /api/me, before /v1
    app.include_router(v1_router)
    ```
    (`/auth/*` and `/api/*` share precedence per architecture §"BFF routing precedence" lines 1344–1349. The router order matters only when paths overlap; these don't.)
  - [x] Create `services/bff/tests/api/test_auth.py` exercising rows 1–18, 25–29 of the AC9 matrix.

- [x] **Task 8: Rewrite `/api/me`** (AC: #7)
  - [x] In `services/bff/src/bff/api/me.py`:
    - Replace the Story 1.3 placeholder body with the AC7 logic: read session cookie via `request.cookies.get(settings.bff_session_cookie_name)`, lookup via `SessionService.get_session`, validate `expires_at`, decode preferred_username from stored `id_token` (PyJWT decode WITHOUT signature verification — comment that the token was already verified at callback time), return 200 or 401 accordingly.
    - Rewrite the module docstring to reflect post-1.5 reality ("returns 200 with `{sub, preferred_username}` for a valid session cookie; 401 with `session_expired` envelope otherwise").
  - [x] Update `services/bff/tests/api/test_me.py` (existing) to cover rows 19–22 of the AC9 matrix. Use `client.cookies.set(...)` to seed the session cookie under test.

- [x] **Task 9: Author the synthetic-IdP test harness** (AC: #8)
  - [x] Create `services/bff/tests/auth/synthetic_idp.py` per AC8. Pick `respx` (add to `[dependency-groups] dev` in pyproject — `respx>=0.21.0`; rerun `uv lock && uv sync --frozen`).
  - [x] Author as a `@pytest.fixture` returning a `SyntheticIdp` dataclass instance with: `.private_key`, `.public_jwk`, `.discovery_doc`, `.make_id_token(claims_override)`, `.captured_revocations` (list), `.captured_end_sessions` (list).
  - [x] Mount respx routes for `${OIDC_ISSUER_URL}/protocol/openid-connect/{auth,token,revocation,logout}` and `${OIDC_JWKS_URL}` and `${OIDC_ISSUER_URL}/.well-known/openid-configuration`.
  - [x] The fixture monkeypatches `bff.core.config.settings.oidc_issuer_url`, `.oidc_jwks_url`, `.oidc_authorize_url_browser` to predictable test URLs (e.g., `http://idp.test/realms/test`). Use `monkeypatch.setattr(...)` so settings revert after each test.

- [x] **Task 10: Author the test suite for the OIDC plugin** (AC: #9)
  - [x] Create `services/bff/tests/auth/test_keycloak_cookie_session.py` covering: PKCE helpers (delegated to `test_pkce.py` — Task 2), `sign_state_id` / `verify_state_id` round-trip, `verify_state_id` returns `None` on tamper, `_safe_return_to` parametrized over the AC3 values (Task 7 also tests this end-to-end), `OidcClient.verify_id_token` happy path AND each failure mode (wrong signing key, wrong `aud`, wrong `iss`, missing `nonce`, expired, JWKS unreachable).
  - [x] Use the synthetic-IdP fixture from Task 9 for any test that exercises HTTP roundtrips.
  - [x] Achieve ≥ 90% coverage on `src/bff/auth/keycloak_cookie_session.py` (project gate per pyproject.toml [tool.coverage.report] fail_under = 90).

- [x] **Task 11: Run the full BFF gate matrix** (AC: #10)
  - [x] From `services/bff/`:
    - `uv sync --frozen` → exit 0.
    - `uv run ruff check` → clean. If new files trip `I001` (import order), run `uv run ruff check --fix` and verify the fix.
    - `uv run ruff format --check` → clean. If new files trip, run `uv run ruff format` and verify.
    - `uv run ty check` → clean. Authlib has shipped type stubs since 1.5.0 — no `# ty: ignore` should be needed; if you find yourself adding one, justify it inline.
    - `uv run pytest --cov` → all tests pass (137 prior + new). Total coverage ≥ 90%.
  - [x] From repo root:
    - `docker compose --profile default config` → valid (the new env var is read from `.env`; verify it's documented).
    - `docker compose build bff` → succeeds.
  - [x] Capture command output excerpts in **Debug Log References**.

- [x] **Task 12: Update sprint-status + deferred-work**
  - [x] On story start: flip `_bmad-output/implementation-artifacts/sprint-status.yaml` development_status `1-5-bff-cookie-session-oidc-plugin-pkce-synthetic-idp-test-harness: ready-for-dev` → `in-progress`. Bump `last_updated`.
  - [x] On story complete (before `code-review`): flip to `review`. Bump `last_updated`.
  - [x] In `_bmad-output/implementation-artifacts/deferred-work.md`: append a one-line "resolved" marker line under each of D2, D8, D33, D40 (e.g., `- **2026-05-XX:** resolved in Story 1.5 (browser-vs-container split-issuer config added; see AC11).`). Do NOT delete the entries — preserve the audit trail.
  - [x] If any new defects surface, add as D41+ with severity / owner-story / rationale per the convention.

### Review Findings

_Code review run: 2026-05-15 (3 layers: Blind Hunter + Edge Case Hunter + Acceptance Auditor)_

#### Decision-Needed

- [x] [Review][Decision] **`pkce.generate_code_verifier()` is unused in the production flow — `_new_opaque_id()` in `SessionService` generates the code verifier instead** — **Resolved 2026-05-15:** Use `pkce.generate_code_verifier()` in `create_auth_state` for the verifier (86 chars); `_new_opaque_id()` stays for ids/state/nonce (43 chars). → converted to patch below.

#### Patches

- [x] [Review][Patch] **`create_auth_state` should call `pkce.generate_code_verifier()` for the verifier instead of `_new_opaque_id()`** [`services/bff/src/bff/services/session_service.py`] — Replace `code_verifier = _new_opaque_id()` with `code_verifier = pkce.generate_code_verifier()` in `create_auth_state`. Import `pkce` from `bff.auth.pkce`. Update any test that asserts verifier length (43 → 86 chars).
- [x] [Review][Patch] **`except BadSignature, SignatureExpired:` should be `except (BadSignature, SignatureExpired):`** [`services/bff/src/bff/auth/keycloak_cookie_session.py:77`] — Python 2 comma syntax; fix to tuple form for correctness and clarity regardless of whether current Python 3.14 parser accepts it.
- [x] [Review][Patch] **Cookie clearing (`delete_cookie`) does not match original set-cookie attributes (missing `Secure`/`SameSite`)** [`services/bff/src/bff/api/auth.py`] — Both `_auth_state_invalid_response` and the success-path `redirect.delete_cookie` omit `secure` and `samesite` args. When `BFF_SESSION_COOKIE_SECURE=True`, RFC 6265bis-compliant browsers may not honour the clearing request. Replace `delete_cookie(key=..., path="/")` with `set_cookie(key=..., value="", max_age=0, httponly=True, samesite="lax", path="/", secure=cfg.bff_session_cookie_secure)`.
- [x] [Review][Patch] **`PyJWKClient` instantiated per-callback call — `cache_keys=True` is inoperative + urllib blocks the event loop** [`services/bff/src/bff/auth/keycloak_cookie_session.py:469`] — Extract to a module-level singleton (`_jwks_client: PyJWKClient | None = None` with lazy init) so the key cache persists across requests. Also document (or wrap in `asyncio.to_thread`) the synchronous urllib I/O that blocks the event loop during JWKS fetch.
- [x] [Review][Patch] **`sub` claim logged untruncated at INFO level — violates logging convention** [`services/bff/src/bff/api/auth.py`] — Apply `_safe_session_id_log(sub)` (or equivalent first-8-chars+ellipsis helper) before logging `sub`, consistent with how `session_id` is handled in the same log line.
- [x] [Review][Patch] **`datetime.fromtimestamp(int(claims["exp"]))` is outside the `OidcVerificationError` catch block** [`services/bff/src/bff/api/auth.py:212`] — An id_token with an astronomically large `exp` (year > 9999) causes an uncaught `ValueError` → 500. Move the `fromtimestamp` conversion inside the `try` block or add a `ValueError` guard.
- [x] [Review][Patch] **`iat` claim not included in PyJWT `require` list** [`services/bff/src/bff/auth/keycloak_cookie_session.py:477`] — OIDC Core 1.0 §2 mandates `iat` in all id_tokens. Add `"iat"` to `options={"require": [...]}`.
- [x] [Review][Patch] **`delete_expired_session` uses SELECT+DELETE instead of the spec-required single-statement DELETE WHERE** [`services/bff/src/bff/services/session_service.py`] — Spec (AC7/Task 5): "DELETE WHERE `id=:session_id` AND `expires_at < now`. Use the indexed `expires_at` column." The current implementation SELECT then DELETE (two round-trips; expiry check in Python). Replace with `await db.execute(delete(entities.Session).where(Session.id == session_id, Session.expires_at < _now_utc()))`.
- [x] [Review][Patch] **`safe_return_to` lives in `session_service.py` — spec requires it in `keycloak_cookie_session.py`** [`services/bff/src/bff/services/session_service.py`] — Task 5 explicitly states: "delegate to a `_safe_return_to` helper in `keycloak_cookie_session.py` so AC3's validation rule lives next to the consumer." Move the function; update the import in `session_service.py`.
- [x] [Review][Patch] **`oidc_authorize_url_browser` validator only checks non-empty — no URL format guard** [`services/bff/src/bff/core/config.py`] — A misconfigured non-URL value (e.g., `"not-a-url"`) passes the validator and reaches `build_authorize_url`. Add `startswith(("http://", "https://"))` check to the existing `@model_validator`.
- [x] [Review][Patch] **Dead `import json` with `_ = json` suppression in synthetic_idp.py** [`services/bff/tests/auth/synthetic_idp.py`] — `json` is never called directly; `httpx.Response(json=...)` does not consume the import. Remove the import and the `_ = json` line.
- [x] [Review][Patch] **AC9 row 15 incomplete — no `/auth/login` → `/auth/callback` round-trip for missing `return_to`** [`services/bff/tests/api/test_auth.py`] — The parametrized `test_auth_login_normalizes_return_to` checks `row.return_to == "/"` but does not complete the round-trip to assert `Location: /` on the callback 302.
- [x] [Review][Patch] **AC9 rows 10/11/13 missing — no end-to-end route tests for id_token `aud`/`iss`/`exp` mismatch** [`services/bff/tests/api/test_auth.py`] — Unit tests in `test_keycloak_cookie_session.py` cover `verify_id_token` in isolation; AC9 matrix requires end-to-end callback route tests asserting 400 `auth_state_invalid` for each.
- [x] [Review][Patch] **AC9 row 14 missing — JWKS-fetch failure not tested at route level** [`services/bff/tests/api/test_auth.py`] — Add a route test that patches `PyJWKClient.fetch_data` (or the respx JWKS route) to fail, runs through `/auth/callback`, and asserts 400 `auth_state_invalid` with the state-id cookie cleared.
- [x] [Review][Patch] **AC9 row 29 incomplete — `BFF_SESSION_COOKIE_SECURE=false` cookie `Secure` absence not asserted** [`services/bff/tests/api/test_auth.py`] — The happy-path test runs with `bff_session_cookie_secure=False` by default but does not assert that neither `bff_session=` nor `bff_csrf=` cookies contain the `Secure` attribute.
- [x] [Review][Patch] **AC3 test matrix incomplete — missing `javascript:alert(1)`, empty string, and 2000-char path cases** [`services/bff/tests/api/test_auth.py`] — The spec (AC3) explicitly requires these three cases in the route-level parametrize decorator; they appear only in the `session_service` unit tests, not in `test_auth.py`.

#### Deferred

- [x] [Review][Defer] **`consume_auth_state` non-atomic SELECT+DELETE — duplicate concurrent callbacks could both succeed** [`services/bff/src/bff/services/session_service.py`] — deferred, pre-existing SQLite deferred-lock limitation; negligible risk at demo scale; a SELECT FOR UPDATE / CAS pattern would require schema changes.
- [x] [Review][Defer] **`code_verifier` stored plaintext in `auth_states` table** [`services/bff/src/bff/services/session_service.py`] — deferred, pre-existing accepted architectural risk (no column encryption per architecture §Operational Details; Story 5.2 will document).
- [x] [Review][Defer] **Zero leeway in PyJWT `exp` validation — clock skew can cause false auth failures** [`services/bff/src/bff/auth/keycloak_cookie_session.py`] — deferred, design choice at demo scale; acceptable for now; add `leeway=timedelta(seconds=10)` to `jwt.decode` if clock drift is observed in practice.
- [x] [Review][Defer] **SQLAlchemy identity-map stale-object risk in PK-collision retry loop** [`services/bff/src/bff/services/session_service.py`] — deferred, pre-existing; the retry loop does not call `db.expunge` on the rolled-back row; astronomically unlikely to matter under 256-bit entropy.
- [x] [Review][Defer] **Module-level `_session_service` singleton bypasses FastAPI DI lifecycle** [`services/bff/src/bff/api/auth.py`, `services/bff/src/bff/api/me.py`] — deferred, pre-existing; `SessionService` is stateless so the singleton is safe; refactor to `Depends(SessionService)` is a code quality improvement for a later story.
- [x] [Review][Defer] **URL-encoded colon bypass in `safe_return_to` colon-check** [`services/bff/src/bff/services/session_service.py`] — deferred, not a real bypass path; FastAPI decodes query-parameter `%xx` sequences before the function is called, so `%3A` → `:` is already handled.

## Dev Notes

### What this story is — and is not

**This story implements the cookie-session OIDC plugin: `/auth/login`, `/auth/callback`, the synthetic-IdP test harness, the AUTH_STATE_INVALID error code, the session-service that owns `sessions`/`auth_states` row lifecycle, AND the rewrite of `/api/me` from placeholder to real consumer.** It also closes deferred items D2, D8, D33, and D40 (which are explicitly assigned to this story).

**Explicitly NOT in scope (each is a downstream story):**

- **No CSRF middleware.** Story 1.6 reads the `csrf_secret` column (created here in `sessions`) and adds the double-submit middleware + CSP header. This story sets the `csrf_token` cookie at callback time, but does NOT enforce it on requests. Do NOT preemptively add `ErrorCode.CSRF_INVALID` (Story 1.6's first consumer).
- **No `/auth/logout` endpoint.** Story 1.7. This story creates sessions; logout deletes them. The synthetic IdP's `/revocation` + `/end_session` handlers are mounted now (AC8) because they live in the same fixture — but they are exercised by 1.7's tests, not this one.
- **No SPA changes.** Pure backend story. Stories 1.8–1.10 own the SPA.
- **No Playwright / E2E.** Story 1.11 sets up Playwright; 1.13 writes the J1 spec.
- **No `/v1/test/reset` endpoint.** Story 1.12.
- **No `BookService` or domain CRUD.** Epic 2.
- **No `ResourceServerClient` (BFF → RS).** Story 3.5.
- **No token-column encryption.** Plaintext at rest is the documented accepted risk per architecture §Operational Details lines 1362–1368. Story 5.2 (security review) documents it.
- **No openid-discovery probing at startup.** The `/health` endpoint already probes discovery (Story 1.3). This story uses fixed env vars for the authorize/token URLs; it does NOT switch to a discovery-first lookup. (Discovery-first would be the cleaner long-term shape, but it's out of scope per the spec: epics line 364 hard-codes the `/realms/bmad-books/protocol/openid-connect/auth` path.)
- **No SPA `/auth/*` proxy verification.** D10 (proxy glob coverage) is listed as belonging here OR Story 1.9 in deferred-work; Story 1.9 is already `done`, so D10 effectively lives with whoever exercises the proxy first end-to-end. That's Story 1.13's E2E, not this backend-unit-test story.

### Path discrepancy: synthetic IdP location

**Background.** The architecture's directory map (line 951) places the synthetic IdP fixture at `services/bff/tests/fixtures/synthetic_idp.py`. The epic text (epics.md line 361) says `tests/auth/synthetic_idp.py`. Story 1.4 set the binding precedent that tests mirror source paths (and that archetype reality wins when the architecture and the on-disk layout disagree).

**Decision for this story (binding):**

| Concern | Architecture says | Epic says | This story does |
|---|---|---|---|
| Synthetic IdP fixture path | `tests/fixtures/synthetic_idp.py` | `tests/auth/synthetic_idp.py` | `tests/auth/synthetic_idp.py` |

**Why epic wins here:**

1. New source code lives at `src/bff/auth/` (epic + architecture agree).
2. Story 1.4 precedent: tests mirror source paths. `tests/auth/` mirrors `src/bff/auth/`.
3. `tests/fixtures/` does not currently exist; creating it would orphan the directory from the test-tree structure. Future cross-cutting fixtures CAN land there if needed, but the synthetic IdP is specifically the auth test apparatus.
4. The fixture is consumed only by `tests/auth/test_*.py` — colocation reduces import indirection.

If a future story needs the synthetic IdP from `tests/api/` (e.g., test_auth.py *does* — but it's adjacent across the test root, not across packages, so a flat `from tests.auth.synthetic_idp import ...` import works), that's a non-issue.

### Architecture-mandated contract details

#### OIDC scope set (architecture A1)

The authorize URL request includes scopes: `openid offline_access reading-speed:read reading-speed:write`. From the realm-bmad-books.json: `reading-speed:read` and `reading-speed:write` are declared as `optionalClientScopes` (lines 77–81) and so MUST appear in the authorize request to be granted. `openid` is the default scope for OIDC; `offline_access` is required to receive a refresh token per OIDC §11.

#### Cookie attributes (architecture A4, A5)

| Cookie | HttpOnly | Secure | SameSite | Path | Max-Age | Value |
|---|---|---|---|---|---|---|
| `bff_auth_state` (this story) | yes | env-driven | Lax | `/` | 300s | `itsdangerous`-signed `auth_states.id` |
| `bff_session` (this story) | yes | env-driven | Lax | `/` | none (session cookie) | opaque 256-bit `sessions.id` |
| `bff_csrf` (this story) | **no** | env-driven | Lax | `/` | none | `sessions.csrf_secret` |

**SameSite=Lax (not Strict)** is non-negotiable — the post-Keycloak callback is a navigation FROM Keycloak's origin TO the BFF, and `Strict` would suppress the state-id cookie on that hop. Architecture A4 line 350 documents this explicitly.

**csrf cookie is non-HttpOnly** by design — the SPA's `csrfInterceptor` (Story 1.9, already merged) reads it via `document.cookie`. This is fine per the double-submit pattern: the value is a per-session shared secret, not a credential, and HTTP-Only would defeat the SPA's ability to participate in the protocol.

**No `Max-Age` on session / csrf cookies.** Architecture A4 line 350 specifies opaque 256-bit value; lifetime is enforced server-side via `sessions.expires_at` (the access_token's `exp`). Browser-side expiry adds nothing.

#### Index naming (architecture line 551)

No new tables in this story (Story 1.4 created them). The queries this story emits use the existing `ix_sessions_sub`, `ix_sessions_expires_at`, `ix_auth_states_expires_at` indexes.

#### `ErrorCode` wire values are lower_snake_case (architecture §C5)

`AUTH_STATE_INVALID` (Python enum name, UPPER_SNAKE) → wire value `"auth_state_invalid"` (lower_snake). Story 1.3 set the pattern (`session_expired`, `service_unavailable` already in errors.py).

### Browser-vs-container hostname split (closes D2 / D8)

**Background.** Keycloak's realm import on startup configures `KC_HOSTNAME=localhost` (per compose/infra.yml). The discovery doc at `/realms/bmad-books/.well-known/openid-configuration` therefore declares:
- `authorization_endpoint = http://localhost:8080/realms/bmad-books/protocol/openid-connect/auth`
- `token_endpoint = http://localhost:8080/realms/bmad-books/protocol/openid-connect/token`
- `issuer = http://localhost:8080/realms/bmad-books`

The BFF's `/health` probe (Story 1.3) successfully fetches this discovery doc using `OIDC_ISSUER_URL=http://keycloak:8080/realms/bmad-books` because Docker DNS resolves `keycloak` from inside the container.

**The problem.** When the BFF needs to:
- Redirect the **browser** to `/authorize` — the browser cannot resolve `keycloak:8080`; it must hit `http://localhost:8080`.
- Exchange the code at `/token` from the **BFF process** — the BFF can resolve `keycloak:8080` but CANNOT resolve `localhost:8080` (localhost inside a container is the container itself).

**The fix (this story).** Two URLs, one for each direction:
- `OIDC_ISSUER_URL=http://keycloak:8080/realms/bmad-books` — back-channel (BFF → IdP token / revocation / end-session). Also the expected `iss` claim of id_tokens (because Keycloak signs them using `KC_HOSTNAME=localhost`, the token's `iss` is `http://localhost:8080/...` — see "iss mismatch" caveat below).
- `OIDC_AUTHORIZE_URL_BROWSER=http://localhost:8080/realms/bmad-books` — used for the 302 from `/auth/login`.

**iss-mismatch caveat (read carefully).** Because Keycloak emits `iss=http://localhost:8080/realms/bmad-books` in id_tokens (per `KC_HOSTNAME=localhost`), the BFF's `verify_id_token` MUST use the **browser-facing** URL as `expected_issuer`, NOT `OIDC_ISSUER_URL`. Concretely: id_token verification reads `expected_issuer = settings.oidc_authorize_url_browser`. Document this in the verify function's docstring — it's surprising and easy to break.

(An alternative is to configure Keycloak with `KC_HOSTNAME_URL=http://keycloak:8080` AND `KC_HOSTNAME_ADMIN_URL=http://localhost:8080` AND a frontendUrl-aware mapper — but that's a Story 1.2 / 5.x infra concern, not this story. The two-URL config is the simpler and documented fix here.)

**Test posture.** Tests use a synthetic IdP at a single test URL (`http://idp.test`), so the iss-mismatch caveat does not bite in tests. The caveat surfaces ONLY at integration time. The E2E (Story 1.13) is the first place it can break; this story's tests assert the verifier RECEIVES `expected_issuer = oidc_authorize_url_browser`, not that real Keycloak signs the expected `iss` (out of scope for unit tests).

### Open-redirect prevention (closes D33)

The validation rule in AC3 is conservative:
- Must start with `/`.
- Must NOT start with `//` (network-relative URL — browsers interpret this as scheme-relative-to-current).
- Must NOT contain `:` before the first non-leading `/` (blocks `https:`, `javascript:`, `data:`, etc.).
- Length ≤ 1024 chars.

Any failure → silently fall back to `"/"`. The reasoning for "silently" (rather than 400): a hostile actor who attempts an open-redirect attack should NOT learn whether their probe was rejected vs. accepted (gives them no signal to refine the attack). A clumsy user who typoed the URL bar just lands on `/` — not a 4xx.

```python
def _safe_return_to(raw: str | None) -> str:
    if not raw or len(raw) > 1024:
        return "/"
    if not raw.startswith("/") or raw.startswith("//"):
        return "/"
    # Block `https:foo`, `javascript:alert`, etc. before the first slash boundary.
    first_slash = raw.index("/", 1) if "/" in raw[1:] else len(raw)
    if ":" in raw[:first_slash]:
        return "/"
    return raw
```

Story 5.2 (security review) MUST reference this rule and the matching tests.

### Authlib idioms — concrete examples

**Important:** Authlib has TWO async client variants and they have subtly different APIs. Use `authlib.integrations.httpx_client.AsyncOAuth2Client`, NOT `OAuth2Session` (sync) or `AsyncAssertionClient` (different grant).

```python
# At module scope (or constructed per-request — Authlib clients are cheap):
from authlib.integrations.httpx_client import AsyncOAuth2Client

async def exchange_code(*, code: str, code_verifier: str, redirect_uri: str,
                        token_url: str, client_id: str, client_secret: str,
                        timeout: httpx.Timeout) -> dict:
    async with AsyncOAuth2Client(
        client_id=client_id,
        client_secret=client_secret,
        timeout=timeout,
    ) as client:
        return await client.fetch_token(
            url=token_url,
            grant_type="authorization_code",
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )
```

For the authorize URL, you don't need Authlib at all — just build the query string with `httpx.URL(...).copy_add_param(...)` or `urllib.parse.urlencode`. Authlib's `create_authorization_url` does this for you but adds a dependency we don't otherwise need at the route-handler layer.

### PyJWT JWKS verification — concrete example

```python
import jwt
from jwt import PyJWKClient

def verify_id_token(*, id_token: str, jwks_url: str, expected_issuer: str,
                    expected_audience: str, expected_nonce: str) -> dict:
    jwks_client = PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=4)
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        decoded = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=expected_issuer,
            options={"require": ["iss", "aud", "exp", "nonce", "sub"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise OidcVerificationError(f"id_token verification failed: {exc}") from exc

    if decoded.get("nonce") != expected_nonce:
        raise OidcVerificationError("id_token nonce mismatch")
    return decoded
```

PyJWT's `PyJWKClient` caches keys in-memory by `kid`. For tests, the synthetic-IdP fixture must either (a) issue tokens with a known `kid` and mount the JWKS endpoint at the configured URL so the client can fetch it, or (b) construct a `PyJWKClient` with a pre-seeded key set (less idiomatic; prefer (a) so tests exercise the same path as prod).

### Testing approach

#### Test categories

1. **Unit tests** (`tests/auth/test_pkce.py`, `tests/auth/test_keycloak_cookie_session.py`) — pure-function tests for PKCE helpers and ID-token verifier. No DB. Use the synthetic IdP fixture for HTTP roundtrips.
2. **Service tests** (`tests/services/test_session_service.py`) — exercise `SessionService` methods against the in-memory `session` fixture from `tests/conftest.py:61–69` (Story 1.4's session fixture works as-is — no new conftest changes needed).
3. **Route tests** (`tests/api/test_auth.py`, updated `tests/api/test_me.py`) — use the `client` fixture from `tests/conftest.py:72–82`. Mount the synthetic-IdP fixture in parallel; the client's `follow_redirects=False` so 302 responses are inspectable.

#### Synthetic IdP wiring

The IdP fixture's `respx` setup MUST run BEFORE the `client` fixture sends any request, but AFTER `monkeypatch` has updated the settings URLs. The standard pattern:

```python
@pytest.fixture
def synthetic_idp(monkeypatch):
    # Override settings URLs to test values.
    test_issuer = "http://idp.test/realms/test"
    test_jwks = "http://idp.test/realms/test/protocol/openid-connect/certs"
    monkeypatch.setattr("bff.core.config.settings.oidc_issuer_url", test_issuer)
    monkeypatch.setattr("bff.core.config.settings.oidc_jwks_url", test_jwks)
    monkeypatch.setattr("bff.core.config.settings.oidc_authorize_url_browser", test_issuer)
    monkeypatch.setattr("bff.core.config.settings.oidc_client_id", "test-client")

    # Mount respx routes...
    with respx.mock(assert_all_called=False) as mock:
        idp = _build_idp(mock, test_issuer, test_jwks)
        yield idp
```

#### Coverage targets

- `src/bff/auth/keycloak_cookie_session.py` ≥ 90%
- `src/bff/auth/pkce.py` ≥ 90% (trivially achievable — module is 2 functions)
- `src/bff/api/auth.py` ≥ 90%
- `src/bff/api/me.py` ≥ 90%
- `src/bff/services/session_service.py` ≥ 90%

Project gate is total `fail_under = 90` per pyproject.toml:82. Per-file targets above are stricter to ensure each new file pulls its weight.

#### Async test pattern

`tests/conftest.py:46–58` builds a session-scoped `sqlite+aiosqlite://` engine with `StaticPool`. The `session` fixture (lines 61–69) provides per-test isolation via `drop_all`/`create_all`. The `client` fixture (lines 72–82) overrides `bff.core.database.get_session` with the per-test session. All test functions are `async def`; `pytest-asyncio` is in `auto` mode per pyproject.toml:76.

#### IntegrityError retry test

Use `monkeypatch.setattr(secrets, "token_urlsafe", ...)` to force two collisions before a real value. The patched function returns a fixed value on first/second call, then delegates to the real `secrets.token_urlsafe(32)`. Verify the row was created with the third value AND that the test logs an INFO line per retry.

#### Avoid testing Authlib internals

Tests should NOT mock Authlib's internals; they should mock the IdP at the HTTP boundary (respx). If a test ends up monkeypatching `AsyncOAuth2Client.fetch_token`, that's a signal to refactor to use respx instead.

### Previous story intelligence (from 1.1–1.4)

**Patterns established that this story must follow:**

- **`UTC` datetime everywhere.** `from datetime import UTC, datetime`. Never `datetime.utcnow()` (deprecated 3.12+). [Source: Story 1.4 dev notes; observability/logging.py:6.]
- **`secrets.token_urlsafe(32)` for opaque ids.** Story 1.4 declared this contract; this story consumes it. The function yields ~43 URL-safe chars (256 bits of entropy). [Source: Story 1.4 task 1 / 2; session.py:23 docstring.]
- **`AppException(ErrorCode, detail)` pattern.** Domain exceptions raise `AppException`; the registered `app_exception_handler` (in `bff/main.py:47`) maps to the envelope. Auth-callback failures CAN either raise `AppException(ErrorCode.AUTH_STATE_INVALID)` and let the handler emit the envelope, OR return a `JSONResponse` directly. **Use the AppException pattern for consistency** (Story 1.3 set the precedent — see core/errors.py:33–37). [Source: Story 1.3 deliverables; core/errors.py.]
- **`response.set_cookie(...)` from FastAPI.** Pass `httponly=True/False`, `samesite="lax"`, `secure=bool`. Tested via `client.cookies` in the test fixtures. [Source: FastAPI docs; conftest.py:78–82.]
- **`from bff.models import entities` then `entities.Session` / `entities.AuthState`.** Avoids shadowing `sqlalchemy.ext.asyncio.AsyncSession` in handlers. [Source: Story 1.4 anti-patterns "Do NOT add a Session symbol that collides with AsyncSession".]
- **Logging via `logger = logging.getLogger(__name__)`.** Never `print`. Lifecycle = INFO; expected-but-interesting = WARN; unhandled = ERROR. First-8-chars + ellipsis for any session/cookie/token correlation id. [Source: architecture lines 781–788; Story 1.3.]
- **`tests/conftest.py` session fixture creates tables via `SQLModel.metadata.create_all`, NOT via Alembic.** `drop_all` + `create_all` between tests for isolation. New entities in `bff.models.entities` are picked up automatically (Story 1.4 verified). [Source: Story 1.4 dev notes.]
- **Coverage gate is total 90% (`pyproject.toml [tool.coverage.report] fail_under = 90`).** Run `uv run pytest --cov` from `services/bff/`. [Source: Story 1.3 / 1.4.]
- **The `client` fixture is `httpx.AsyncClient` with `follow_redirects` defaulting to True.** For this story's 302 tests, instantiate a separate client OR use `client.get("/auth/login", follow_redirects=False)` per-call. The `client` fixture from conftest.py:72 doesn't expose this knob; you may need to either (a) author a `client_no_redirects` fixture, (b) construct a fresh `AsyncClient` in the test, or (c) introspect the underlying ASGITransport. Option (b) is simplest; option (a) is cleanest if many tests need it. **Recommend (a)** — add `client_no_redirects` to `tests/conftest.py` mirroring lines 72–82 with `follow_redirects=False`.

**Deferred items closed by this story:**

- **D2 / D8** (browser-vs-container OIDC hostname split) — AC11 + Task 3 add `OIDC_AUTHORIZE_URL_BROWSER` config var, document the iss-claim caveat, mark D2/D8 resolved in deferred-work.md.
- **D33** (`return_to` open-redirect validation) — AC3 + the `_safe_return_to` helper.
- **D40** (state/nonce collision retry) — AC12 + `SessionService` retry loop.

**Deferred items NOT closed here (explicitly out of scope):**

- **D6** (hard-coded `http://localhost:8000` redirect in realm JSON) — would require env-substitution in Story 1.2's realm import or a per-environment overlay. Defer to a Story 5.x infra polish unless a contributor changes `BFF_BASE_URL` in their `.env` (which Story 1.5 itself does NOT do — we keep `localhost:8000` as the documented default).
- **D7** (no offlineSessionMaxLifespan cap) — orthogonal; refresh-token lifecycle is fine for the educational demo.
- **D10** (SPA proxy glob may not match deep paths) — exercised by Story 1.13 E2E first; SPA proxy is unchanged here.
- **D32** (bulk update `onupdate` skip) — caveat documented inline on `SessionService.get_session`; this story's call sites are point-mutations and DO trigger the lambda.
- **D35** (id min_length=1) — addressed by generator contract (`secrets.token_urlsafe(32)`); defense-in-depth model constraint deferred.

### Git intelligence (recent commits)

```
6550fa4 feat: implement story 1.4
ba784f8 Merge branch 'story-1-3'
295ed48 feat: 1-3 scaffold bffe
60aa25b feat: completed bff scaffolding
b696884 feat: implement S1E9
```

- Story 1.4 just landed on `main`. The `sessions` and `auth_states` tables exist via migration `0001_init`; the SQLModel classes are at `bff.models.entities.{session,auth_state}`. This story is the first consumer.
- Stories 1.8 (SPA scaffold) and 1.9 (SPA AuthService + interceptors) are merged. The SPA's `withCredentialsInterceptor` already exists and will send the session cookie on every request once this story sets it. SPA's `csrfInterceptor` reads `bff_csrf` — this story sets that cookie at callback.
- Branch convention from prior stories: `story-1-5`. Create from `main`.
- No conflicts expected: stories 1.6/1.7/1.10–1.13 are downstream (backlog), Epic 2+ haven't started.

### Anti-patterns to avoid

- **Do NOT add `ErrorCode.CSRF_INVALID`.** Story 1.6 owns it. The csrf cookie is set at callback time, but `csrf_invalid` envelope production is downstream.
- **Do NOT add `/auth/logout`** (Story 1.7) or `/v1/test/reset` (Story 1.12) routes here.
- **Do NOT add a `BookService`, `BooksService`, books models, or `/v1/books` routes** (Epic 2).
- **Do NOT encrypt the token columns.** Plaintext at rest is the documented accepted risk (architecture §Operational Details lines 1362–1368). Story 5.2 will document it.
- **Do NOT scatter `secrets.token_urlsafe(32)` calls across modules.** Centralize in `SessionService` so the generator contract has one source of truth.
- **Do NOT bypass the `AppException` envelope.** Return `JSONResponse` only when you need a `Set-Cookie` header on a 4xx (which is the case for `auth_callback` failures — cookie-clearing). For 4xx without cookie work, raise `AppException(ErrorCode.AUTH_STATE_INVALID)` and let `app_exception_handler` serialize.
- **Do NOT introduce a discovery-doc-first lookup.** The epic spec hard-codes the `/realms/bmad-books/protocol/openid-connect/auth` path. The `/health` probe (Story 1.3) already validates discovery is reachable; this story uses fixed URLs.
- **Do NOT use `datetime.utcnow()`** (deprecated).
- **Do NOT introduce a `RoleMappingProvider` analog on the BFF.** That's the RS pattern (Story 3.2). The BFF is a cookie-session client; it does not enforce JWT scopes.
- **Do NOT mock Authlib internals in tests.** Mock the IdP at the HTTP boundary via `respx`.
- **Do NOT log full tokens, full session ids, refresh tokens, or authorization codes.** First-8-chars-and-ellipsis for correlation. Architecture line 787 is explicit.
- **Do NOT change the existing `ErrorCode` members or their wire values.** Story 1.4 / 1.3 review found wire-value drift is hard to reverse once the SPA depends on it.
- **Do NOT use `python3`.** Project convention (`CLAUDE.md`): always `python`.
- **Do NOT preemptively add a `unique=True` constraint to `auth_states.state` or `auth_states.nonce`.** Story 1.4 decided not to (D40 resolution); changing the schema now would require a new migration. The 256-bit entropy + retry loop is the contract.
- **Do NOT introduce `from __future__ import annotations` if the existing project does not use it.** Story 1.4 confirmed the project does not. Use real PEP 604 / 484 types.
- **Do NOT add SPA proxy glob fixes (D10) here.** They belong to whoever first exercises the proxy end-to-end (Story 1.13's E2E).

### Naming and pattern compliance (architecture §"Implementation Patterns & Consistency Rules")

- **Python files:** `snake_case.py`. New files: `pkce.py`, `keycloak_cookie_session.py`, `auth.py` (in `api/`), `session_service.py`, `synthetic_idp.py`, plus their `test_*.py` counterparts. *(Lines 564.)*
- **Classes:** `PascalCase` — `OidcClient`, `OidcVerificationError`, `SessionService`, `SyntheticIdp`. *(Line 567.)*
- **Functions / methods:** `snake_case` — `generate_code_verifier`, `compute_code_challenge`, `sign_state_id`, `verify_id_token`, `create_auth_state`, `consume_auth_state`. *(Line 567.)*
- **Module constants:** `UPPER_SNAKE_CASE` — `BFF_AUTH_STATE_COOKIE_NAME`, `S256_METHOD`. *(Line 568.)*
- **Wire values:** `lower_snake_case` — `auth_state_invalid`, `session_expired`. *(Lines 396–409.)*
- **Tests mirror source paths.** `src/bff/auth/keycloak_cookie_session.py` → `tests/auth/test_keycloak_cookie_session.py`. `src/bff/api/auth.py` → `tests/api/test_auth.py`. `src/bff/services/session_service.py` → `tests/services/test_session_service.py`. *(Line 615.)*

### Latest tech information

- **Authlib 1.6+** ships an `AsyncOAuth2Client` under `authlib.integrations.httpx_client`. It supports PKCE out of the box (`code_verifier` is just another `fetch_token` kwarg). The library is mature (>10 years) and still actively maintained.
- **PyJWT 2.10+** ships `PyJWKClient` with built-in caching, automatic key rotation on `kid` miss, and full RFC 7519 / 7521 support. The `[crypto]` extra pulls `cryptography` for RSA verification (RS256).
- **itsdangerous 2.2+** is stable; `URLSafeTimedSerializer` is the right primitive for short-lived signed values. Salt + `max_age` covers tamper + expiry in one call.
- **respx 0.21+** is the standard async httpx mocking library; it integrates cleanly with `pytest-asyncio`.
- **Keycloak 26+** (compose/infra.yml) emits S256-PKCE-compatible tokens by default. The realm config in `keycloak/realm-bmad-books.json` already enforces `pkce.code.challenge.method=S256` (line 54) — clients that don't send PKCE are rejected.

### Project Structure Notes

**New files (all under `services/bff/`):**

- `src/bff/auth/__init__.py` (new — empty)
- `src/bff/auth/pkce.py` (new)
- `src/bff/auth/keycloak_cookie_session.py` (new)
- `src/bff/api/auth.py` (new — `/auth/login`, `/auth/callback` handlers)
- `src/bff/services/__init__.py` (new — empty)
- `src/bff/services/session_service.py` (new)
- `tests/auth/__init__.py` (new — empty)
- `tests/auth/synthetic_idp.py` (new — pytest fixture)
- `tests/auth/test_pkce.py` (new)
- `tests/auth/test_keycloak_cookie_session.py` (new)
- `tests/services/__init__.py` (new — empty)
- `tests/services/test_session_service.py` (new)
- `tests/api/test_auth.py` (new)

**Modified files:**

- `services/bff/pyproject.toml` — add `authlib`, `pyjwt[crypto]`, `itsdangerous` to `dependencies`; add `respx` to `[dependency-groups] dev`.
- `services/bff/uv.lock` — regenerated by `uv lock`.
- `services/bff/src/bff/main.py` — `include_router(auth_router)` after `me_router` / before `v1_router`.
- `services/bff/src/bff/api/me.py` — rewrite from placeholder to session-cookie consumer.
- `services/bff/src/bff/core/config.py` — add `oidc_authorize_url_browser` + its `@model_validator`.
- `services/bff/src/bff/core/errors.py` — add `AUTH_STATE_INVALID = ("auth_state_invalid", ..., 400)`.
- `services/bff/.env.example` — document the new var.
- `.env.example` (repo root) — document the new var (mirrored from BFF's).
- `services/bff/tests/api/test_me.py` — expand to cover rows 19–22 of AC9.
- `services/bff/tests/core/test_config.py` — cover the new validator.
- `services/bff/tests/core/test_errors.py` — cover the new ErrorCode value.
- `services/bff/tests/conftest.py` — add `client_no_redirects` fixture (recommended) OR document the per-test pattern for testing 302s.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status flips + `last_updated`.
- `_bmad-output/implementation-artifacts/deferred-work.md` — append resolved markers for D2, D8, D33, D40.

**Untouched (verified):**

- All Story 1.1, 1.2, 1.3, 1.4 artifacts outside the files listed above. Specifically: `compose/`, `keycloak/`, `docker-compose.yml`, `services/bff/alembic/`, `services/bff/src/bff/models/entities/`, `services/bff/src/bff/observability/`, `services/bff/src/bff/aop/`, `services/bff/Dockerfile`, `services/bff/entrypoint.sh` — none change.
- Stories 1.8 (SPA scaffold) and 1.9 (SPA AuthService) deliverables — pure backend story.
- `services/resource-server/` — does not exist yet (Epic 3).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.5` lines 352–394] — canonical story spec (Given/When/Then ACs, scope set, cookie attributes, error codes).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security` A1–A5 lines 347–354] — Authlib choice, PKCE storage strategy, cookie attributes, CSRF strategy.
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns` C1–C2 lines 358–377] — non-versioned `/auth/*` path layout, `/auth/login` / `/auth/callback` / `/api/me` contracts.
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns` C5 lines 396–409] — `ErrorCode.AUTH_STATE_INVALID` wire-value contract.
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns` C6 lines 411–416] — BFF → Keycloak timeouts (5s connect / 10s read, no retries).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Cross-Cutting Concerns Mapping` lines 1188–1190] — file-location contract for OIDC plugin, session service, CSRF middleware.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Naming Patterns` lines 542–571] — file / class / function naming.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` lines 904–913, 944–952] — directory layout for `auth/`, `services/`, `tests/auth/`.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Operational Details` lines 1343–1352] — BFF routing precedence (`/auth/*`, `/api/*`, `/v1/*`).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Operational Details` lines 1362–1368] — plaintext-token accepted risk.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#J1` lines 377–414] — first-time-login journey (sequence diagram; SPA → BFF → Keycloak → BFF → SPA).
- [Source: `_bmad-output/planning-artifacts/PRD.md#Architectural Constraints` lines 76–84] — token isolation, BFF as confidential OAuth client, PKCE-only.
- [Source: `_bmad-output/implementation-artifacts/1-4-bff-session-and-auth-state-schema-alembic-migration.md`] — `Session` / `AuthState` SQLModel contract, alembic 0001_init migration, in-memory test fixtures.
- [Source: `_bmad-output/implementation-artifacts/1-3-bff-scaffold-from-archetype-baseline-health-lint-test-gates.md`] — BFF scaffold, conftest fixtures, `AppException` pattern, coverage gate.
- [Source: `_bmad-output/implementation-artifacts/1-2-keycloak-realm-as-code-compose-service.md`] — realm-bmad-books.json (client config, scopes, optional `offline_access`).
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md#D2` lines 14–22] — browser-vs-container hostname split (closed here).
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md#D8` lines 68–74] — discovery-doc iss-claim alignment (closed here).
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md#D33` lines 263–269] — `return_to` open-redirect validation (closed here).
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md#D40` lines 319–326] — state/nonce collision retry (closed here).
- [Source: `services/bff/src/bff/main.py`] — router registration site.
- [Source: `services/bff/src/bff/api/me.py`] — current placeholder; this story rewrites it.
- [Source: `services/bff/src/bff/core/config.py:69–94`] — existing OIDC env vars; this story adds `oidc_authorize_url_browser`.
- [Source: `services/bff/src/bff/core/errors.py:9–25`] — `ErrorCode` enum; this story adds `AUTH_STATE_INVALID`.
- [Source: `services/bff/src/bff/models/entities/session.py`, `.../auth_state.py`] — table schema this story consumes.
- [Source: `services/bff/tests/conftest.py:46–82`] — test fixtures (engine, session, client) — used as-is.
- [Source: `keycloak/realm-bmad-books.json` lines 38–82] — realm client config (`bmad-books-bff`), scope declarations, PKCE-required attribute.
- [Source: `.env.example` lines 13–32] — AR29 env-var enumeration; this story adds one var.
- [Source: `CLAUDE.md`] — `python` (not `python3`).
- [Source: `[[project-bmad-books-backend-archetype]]` — user memory] — Python 3.14 + FastAPI + SQLModel + uv + OTEL archetype mandate.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code, bmad-dev-story workflow)

### Debug Log References

**Dependencies (Task 1):**

```
$ uv lock
Resolved 66 packages in 499ms
Added authlib v1.7.2
Added cryptography v48.0.0
Added itsdangerous v2.2.0
Added joserfc v1.6.5
Added pyjwt v2.12.1
Added respx v0.23.1
$ uv sync --frozen
Installed 9 packages in 8.14s
$ uv run python -c "import authlib, jwt, itsdangerous, respx; print('imports ok')"
imports ok
```

**Full gate matrix (Task 11):**

```
$ uv run ruff check                # All checks passed!
$ uv run ruff format --check       # 57 files already formatted
$ uv run ty check                  # All checks passed!
$ uv run pytest --cov              # 223 passed, total coverage 98.22% (gate ≥90%)
$ docker compose --profile default config  # ok (with .env staged)
$ docker compose build bff         # Image bmad_books-bff Built
```

**Per-file coverage of new code:**

```
src/bff/api/auth.py                          85      3    96%
src/bff/auth/keycloak_cookie_session.py      49      1    98%
src/bff/auth/pkce.py                         11      0   100%
src/bff/api/me.py                            35      0   100%
src/bff/services/session_service.py          82      1    99%
src/bff/core/config.py                      105      0   100%
src/bff/core/errors.py                       33      0   100%
```

### Completion Notes List

- **All 12 ACs satisfied.** All 12 tasks and their subtasks marked complete.
- **OIDC cookie-session plugin** authored at `src/bff/auth/keycloak_cookie_session.py` (Authlib `AsyncOAuth2Client` for the `/token` POST + `itsdangerous.URLSafeTimedSerializer` for the state-id cookie + PyJWT `PyJWKClient` for id_token RS256 verification). Exposes `state_id_serializer`, `sign_state_id`, `verify_state_id`, `build_authorize_url`, `exchange_code`, `verify_id_token`, and `OidcVerificationError`.
- **PKCE helpers** at `src/bff/auth/pkce.py` — `generate_code_verifier()` (256-bit entropy via `secrets.token_urlsafe(64)`) and `compute_code_challenge()` (SHA-256 → base64url-no-pad). RFC 7636 §4.6 worked-example matches.
- **`SessionService`** at `src/bff/services/session_service.py` owns the lifecycle of `auth_states` / `sessions` rows. Single source of opaque-id generation (`secrets.token_urlsafe(32)`). Includes `safe_return_to(raw)` open-redirect validator (silent fallback to `/` on any rule failure — D33 resolution). PK-collision retry up to 3 times (D40 resolution).
- **`/auth/login` and `/auth/callback`** at `src/bff/api/auth.py`. Login mints an `auth_states` row, signs its id into a 5-min HttpOnly `bff_auth_state` cookie, and 302s to the **browser-facing** authorize URL (`OIDC_AUTHORIZE_URL_BROWSER`). Callback verifies state cookie + row, exchanges code+verifier at `/token`, verifies id_token via JWKS, persists a `sessions` row, sets `bff_session` (HttpOnly) + `bff_csrf` (non-HttpOnly, per architecture A5) cookies, and 302s to the validated `return_to`.
- **`/api/me` rewritten** from Story 1.3's always-401 placeholder. Returns 200 `{sub, preferred_username}` for a valid session cookie; 401 `session_expired` for missing/unknown/expired sessions. Expired sessions are deleted lazily on access. `preferred_username` is decoded from the stored id_token via PyJWT WITHOUT signature verification (already verified at callback time).
- **`AUTH_STATE_INVALID` ErrorCode** added at `src/bff/core/errors.py`, wire value `"auth_state_invalid"` (lower_snake_case per architecture §C5).
- **`OIDC_AUTHORIZE_URL_BROWSER` config var** added at `src/bff/core/config.py` with a `@model_validator` (required-fail-fast). Mirrored in both env-examples. Resolves D2 / D8 (the BFF cannot use the same URL for the browser-facing 302 and the back-channel token exchange — Keycloak with `KC_HOSTNAME=localhost` emits `iss=http://localhost:8080/...` in id_tokens, so `verify_id_token` uses the browser-facing URL as the expected `iss` claim — caveat documented inline).
- **Synthetic IdP test harness** at `tests/auth/synthetic_idp.py`. Generates an in-process RSA-2048 keypair, exposes a JWKS dict, mounts respx routes for `/.well-known/openid-configuration`, `/certs`, `/token`, `/revocation`, `/logout`. Patches `PyJWKClient.fetch_data` (PyJWT uses synchronous urllib that respx can't intercept) to return the synthetic public key. `make_id_token(claims_override=..., signing_key=...)` for negative-path test variants.
- **Test suite expanded by 67 new tests** (220 BFF tests prior + new authentication coverage = 223 passing). New test files: `tests/auth/test_pkce.py` (14), `tests/auth/test_keycloak_cookie_session.py` (19), `tests/services/test_session_service.py` (24), `tests/api/test_auth.py` (22). Updated `tests/api/test_me.py` (6 — replacing the 3 Story 1.3 placeholder tests) and `tests/core/{test_config.py, test_errors.py}` (+3 each).
- **All gates green:** 223 passed, 98.22% coverage, ruff/ty/format/compose/build all clean. Per-file coverage of the new modules ≥ 96%.
- **conftest fixture additions:** `client_no_redirects` (sibling of `client`, with `follow_redirects=False`) makes inspecting 302 responses ergonomic. The conftest also seeds `OIDC_AUTHORIZE_URL_BROWSER` via `os.environ.setdefault` so `bff.main` imports cleanly under pytest.
- **Deferred items closed:** D2 + D8 (browser-vs-container split-issuer), D33 (return_to validation), D40 (state/nonce collision retry). Each entry in `deferred-work.md` now carries a `Resolution (2026-05-15, Story 1.5)` marker.
- **No new dependencies beyond the story spec.** Runtime: `authlib`, `pyjwt[crypto]`, `itsdangerous`. Dev: `respx`.
- **No cross-story leakage:** no CSRF middleware (Story 1.6), no `/auth/logout` (Story 1.7), no `/v1/test/reset` (Story 1.12), no `BookService` (Epic 2), no `ResourceServerClient` (Story 3.5). The `csrf_token` cookie IS set at callback time per architecture A5, but no middleware enforces it yet.

### File List

**New files:**

- `services/bff/src/bff/auth/__init__.py` — empty package marker.
- `services/bff/src/bff/auth/pkce.py` — PKCE verifier/challenge helpers.
- `services/bff/src/bff/auth/keycloak_cookie_session.py` — OIDC client + state-id signer + id_token verifier.
- `services/bff/src/bff/api/auth.py` — `/auth/login`, `/auth/callback` handlers.
- `services/bff/src/bff/services/__init__.py` — empty package marker.
- `services/bff/src/bff/services/session_service.py` — `SessionService` + `safe_return_to`.
- `services/bff/tests/auth/__init__.py` — empty.
- `services/bff/tests/auth/synthetic_idp.py` — respx-backed synthetic IdP fixture.
- `services/bff/tests/auth/test_pkce.py` — 14 tests for `bff.auth.pkce`.
- `services/bff/tests/auth/test_keycloak_cookie_session.py` — 19 tests for the OIDC client + state-id cookie + id_token verifier.
- `services/bff/tests/services/__init__.py` — empty.
- `services/bff/tests/services/test_session_service.py` — 24 tests for `SessionService` + `safe_return_to`.
- `services/bff/tests/api/test_auth.py` — 22 end-to-end tests for `/auth/login` + `/auth/callback`.

**Modified files:**

- `services/bff/pyproject.toml` — added `authlib>=1.6.0`, `pyjwt[crypto]>=2.10.0`, `itsdangerous>=2.2.0` to runtime deps; added `respx>=0.21.0` to dev deps.
- `services/bff/uv.lock` — regenerated via `uv lock`.
- `services/bff/src/bff/main.py` — `include_router(auth_router)` after `me_router`, before `v1_router`.
- `services/bff/src/bff/api/me.py` — rewritten from Story 1.3 placeholder to session-cookie consumer.
- `services/bff/src/bff/core/config.py` — added `oidc_authorize_url_browser` field + `_validate_oidc_authorize_url_browser` model validator.
- `services/bff/src/bff/core/errors.py` — added `AUTH_STATE_INVALID = ("auth_state_invalid", "Authorization state invalid", 400)`.
- `services/bff/.env.example` — documents `OIDC_AUTHORIZE_URL_BROWSER`.
- `.env.example` (repo root) — mirrors the same addition.
- `services/bff/tests/conftest.py` — `os.environ.setdefault("OIDC_AUTHORIZE_URL_BROWSER", ...)` for test-time settings instantiation; new `client_no_redirects` fixture for inspecting 302s.
- `services/bff/tests/api/test_me.py` — rewritten test suite (6 tests) for the session-cookie-driven `/api/me`.
- `services/bff/tests/core/test_config.py` — 3 new tests for the `OIDC_AUTHORIZE_URL_BROWSER` validator.
- `services/bff/tests/core/test_errors.py` — 1 new test asserting `ErrorCode.AUTH_STATE_INVALID` shape.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `1-5-…` `ready-for-dev` → `in-progress` → `review`; `last_updated` rolled.
- `_bmad-output/implementation-artifacts/deferred-work.md` — added `Resolution (2026-05-15, Story 1.5)` markers under D2, D8, D33, D40.

**Untouched (verified):**

- All Story 1.1, 1.2, 1.3, 1.4 deliverables outside the files listed above.
- `services/bff/alembic/` — Story 1.4's `0001_init` migration is unchanged.
- `services/bff/src/bff/models/entities/` — `Session` and `AuthState` SQLModels unchanged (this story consumes them).
- `services/bff/src/bff/observability/`, `aop/`, `core/database.py`, `core/__init__.py` — unchanged.
- `services/bff/Dockerfile`, `entrypoint.sh`, `alembic.ini` — unchanged.
- `compose/`, `docker-compose.yml`, `keycloak/realm-bmad-books.json`, `keycloak/Dockerfile` — unchanged.
- `services/resource-server/` — not created (Epic 3).
- `spa/`, `e2e/` — not in scope.

## Change Log

- **2026-05-15** — Story 1.5 implementation complete. Authored the OIDC cookie-session plugin (`/auth/login`, `/auth/callback`), `SessionService`, PKCE helpers, synthetic-IdP test harness, and rewrote `/api/me` to consume the session cookie. Closed deferred items D2, D8, D33, D40. 67 new tests; all 223 BFF tests green; 98.22% coverage; ruff/ty/format/compose/build clean. Status → review.
