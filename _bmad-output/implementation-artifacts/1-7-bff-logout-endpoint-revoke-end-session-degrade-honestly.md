# Story 1.7: BFF logout endpoint (revoke + end-session + degrade honestly)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a signed-in user,
I want to click "Log out" and have my session terminated locally, my refresh token revoked at Keycloak, and the session cookie cleared,
so that no residual access remains after I log out — even when the authorization server is temporarily unreachable.

## Acceptance Criteria

**AC1 — Module surface.** `services/bff/src/bff/api/auth.py` (existing — Story 1.5) gains a single new route handler: `POST /auth/logout`. Two new functions are added to `services/bff/src/bff/auth/keycloak_cookie_session.py` (existing): `async def revoke_refresh_token(...) -> None` and `async def end_session(...) -> None`. `services/bff/src/bff/services/session_service.py` (existing) gains `async def delete_session(self, db, *, session_id: str) -> None`. NO new top-level modules; this story extends Story 1.5's surface. `bff/main.py` is unchanged — the `auth_router` it already registers (main.py:52) gains the new route automatically. [Source: epics.md#Story 1.7 lines 432–469; architecture.md#API & Communication Patterns C2 line 370; architecture.md#Cross-Cutting Concerns Mapping lines 1188–1189; services/bff/src/bff/main.py:52.]

**AC2 — Happy path (`POST /auth/logout` with valid session + valid CSRF).** Given an authenticated session with stored `access_token`, `refresh_token`, `id_token` in the `sessions` row keyed by the session-cookie value, when the SPA POSTs to `/auth/logout` with the session cookie present AND a matching `X-CSRF-Token` header (validated by Story 1.6's middleware — see Dependencies below) AND a same-origin `Origin`/`Referer` header, then the BFF:
1. Reads `refresh_token` and `id_token` from the `sessions` row.
2. POSTs to Keycloak's revocation endpoint (`OIDC_ISSUER_URL/protocol/openid-connect/revoke`) with `application/x-www-form-urlencoded` body `token=<refresh_token>&token_type_hint=refresh_token`, using HTTP Basic auth `client_id:client_secret` per RFC 7009 §2.1. Honors architecture §C6 (5s connect / 10s read; **zero retries**).
3. POSTs to Keycloak's end-session endpoint (`OIDC_ISSUER_URL/protocol/openid-connect/logout`) with form body `id_token_hint=<id_token>&client_id=<client_id>&client_secret=<client_secret>`. Honors §C6 timeouts; zero retries.
4. Deletes the `sessions` row for this session id (single `await db.delete(row); await db.commit()` — symmetric with `consume_auth_state`'s pattern in `session_service.py:130–131`).
5. Sets `Set-Cookie` clearing the session cookie (`bff_session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/`; `Secure` per `bff_session_cookie_secure`) AND the CSRF cookie (`bff_csrf=; Max-Age=0; SameSite=Lax; Path=/`; non-HttpOnly to match the original `set_cookie` attributes — Story 1.5's review-findings P3 established that clear-cookie attribute mismatch breaks RFC 6265bis browsers; use `set_cookie(value="", max_age=0, ...)`, NOT `delete_cookie(...)`).
6. Responds **204 No Content with an empty body** (per architecture §Format Patterns line 680 + §C2 line 370).

[Source: epics.md#Story 1.7 lines 438–446; architecture.md#Authentication & Security A7 line 353; architecture.md#API & Communication Patterns C2 line 370; architecture.md#API & Communication Patterns C6 lines 411–416; architecture.md#Format Patterns lines 672, 680; 1-5 story Review Findings (Patch — cookie-clearing attribute mismatch).]

**AC3 — Revocation failure degrades honestly (Architecture A7, J5 UX contract).** Given an authenticated session, when `POST /auth/logout` is processed AND the revocation endpoint call to Keycloak fails (any of: `httpx.ConnectError`, `httpx.ReadTimeout`, `httpx.ConnectTimeout`, non-2xx HTTP response including 5xx, or any other `httpx` transport exception), then the BFF **still** proceeds with steps 3–6 of AC2 (end-session attempt → delete `sessions` row → clear cookies → 204). The revocation failure is logged at **WARN** with classifier `auth_logout_revocation_failed: <type-of-failure>` (never include token material in the log — per architecture lines 783–788; first-8-chars+ellipsis pattern from Story 1.5's `_safe_session_id_log` applies to `session_id` and `sub`). The response is still 204; the SPA must not be able to distinguish revocation success from revocation failure from the wire (per UX §J5 "honest over flattering" principle). [Source: epics.md#Story 1.7 lines 448–451; architecture.md#Authentication & Security A7 line 353; ux-design-specification.md#J5 lines 536–538; architecture.md#Logging conventions lines 781–788.]

**AC4 — End-session failure degrades honestly.** Given an authenticated session, when `POST /auth/logout` is processed AND the `end_session_endpoint` call to Keycloak fails (same failure modes as AC3), then the BFF **still** proceeds with steps 4–6 of AC2 (delete `sessions` row → clear cookies → 204). The failure is logged at **WARN** with classifier `auth_logout_end_session_failed: <type-of-failure>`. Response is still 204. The order matters: revocation is attempted BEFORE end-session per architecture A7 ("revoke refresh token → call `end_session_endpoint` → clear local session → clear cookie"). If revocation fails AND end-session also fails, both WARN logs are emitted; the row is still deleted; cookies are still cleared; response is 204. [Source: epics.md#Story 1.7 lines 453–456; architecture.md#Authentication & Security A7 line 353.]

**AC5 — Missing session cookie → 401 `session_expired`.** When `POST /auth/logout` is called without a session cookie OR with a session cookie value that matches NO `sessions` row OR matches a row whose `expires_at` is in the past, then the BFF responds **401** with the canonical envelope `{"errorCode": "session_expired", "message": "Session expired or not present", "detail": null}` AND clears the session + CSRF cookies (defensive cookie-clear: the stale cookie is now useless and a fresh login won't override `Path=/` cookies that were never set). Mirrors `/api/me`'s missing-session behavior at `services/bff/src/bff/api/me.py:57–68`. Expired rows are deleted lazily in the same handler (single `delete_expired_session` call, reuse Story 1.5's existing method at `session_service.py:193–210`). [Source: epics.md#Story 1.7 lines 458–459; services/bff/src/bff/api/me.py:57–68; architecture.md#API & Communication Patterns table line 365 (Auth: "Session cookie").]

**AC6 — Missing/invalid CSRF → 403 `csrf_invalid` (delegated to Story 1.6's middleware).** When `POST /auth/logout` is called without a valid `X-CSRF-Token` header (header absent, header value not equal to `bff_csrf` cookie value, cross-origin `Origin`/`Referer`), then the BFF responds **403** with envelope `{"errorCode": "csrf_invalid", "message": "...", "detail": null}`. **Implementation note:** this response is produced by the CSRF middleware introduced in Story 1.6 (`src/bff/auth/csrf.py`), NOT by the `/auth/logout` handler itself. This story does NOT add CSRF enforcement code; it relies on the middleware being installed by Story 1.6 to intercept POSTs to `/auth/logout`. If Story 1.6 is not yet merged when this story is implemented, this AC's test (Task 5, scenario "missing CSRF → 403") will require either (a) Story 1.6 to land first, OR (b) a thin stub middleware in this story that is replaced by Story 1.6's real implementation. **Recommended:** implement Story 1.6 first (it's the prior story in the epic sequence — sprint-status.yaml has `1-6` ahead of `1-7`). See Dependencies section in Dev Notes. [Source: epics.md#Story 1.6 lines 396–430; epics.md#Story 1.7 lines 461–462.]

**AC7 — Synthetic-IdP revocation enforcement (integration test).** `services/bff/tests/auth/synthetic_idp.py` is extended so its `/token` handler (existing — `_token_handler` at synthetic_idp.py:196–223) checks a new `revoked_refresh_tokens: set[str]` field on the `SyntheticIdp` dataclass (initialized empty). The `_revocation_handler` (synthetic_idp.py:227–229) is extended to add the captured `token` form field into `idp.revoked_refresh_tokens`. A new integration test in `tests/api/test_auth.py` (extend existing) drives the full happy-path login → logout → refresh-replay sequence: (1) login a synthetic user via the existing `_complete_login` helper to obtain a session row carrying `refresh_token=synthetic-refresh-token`, (2) POST `/auth/logout` with the session + CSRF cookies, (3) capture the form body sent to `/revocation` (via `idp.captured_revocations`), (4) verify the captured `token` value equals `synthetic-refresh-token`, (5) attempt a follow-up `/token` POST (refresh_token grant) using the same `synthetic-refresh-token` AND assert the synthetic IdP returns 400 `{"error": "invalid_grant"}` because the token is now in `revoked_refresh_tokens`. The synthetic IdP's `/token` handler must reject refresh_token-grant requests when `body["refresh_token"]` is in `revoked_refresh_tokens` (current handler only checks `code_verifier`; refresh-grant path needs adding). [Source: epics.md#Story 1.7 lines 464–468; tests/auth/synthetic_idp.py:196–237; tests/api/test_auth.py (existing harness).]

**AC8 — Test coverage matrix.** Tests under `services/bff/tests/api/test_auth.py` (extend) AND `services/bff/tests/services/test_session_service.py` (extend) AND `services/bff/tests/auth/test_keycloak_cookie_session.py` (extend) cover the scenarios enumerated in epic line 466, expanded to:

| # | Scenario | Asserted |
|---|---|---|
| 1 | Happy path (login + logout + IdP receives both calls) | 204 empty body; `idp.captured_revocations[0]["token"] == "synthetic-refresh-token"`; `idp.captured_revocations[0]["token_type_hint"] == "refresh_token"`; `idp.captured_end_sessions[0]["id_token_hint"]` equals the stored id_token; sessions row deleted; cookies cleared (Set-Cookie max_age=0 on both) |
| 2 | Revocation failure (synthetic IdP `/revocation` returns 500) | 204; end-session still called; row deleted; cookies cleared; WARN log `auth_logout_revocation_failed: HTTPStatusError` (or equivalent classifier) |
| 3 | Revocation failure — connection refused (respx returns `ConnectError`) | 204; same downstream behavior as #2; WARN log `auth_logout_revocation_failed: ConnectError` |
| 4 | Revocation failure — timeout (respx returns `httpx.ReadTimeout`) | 204; same; WARN log `auth_logout_revocation_failed: ReadTimeout` |
| 5 | End-session failure (synthetic IdP `/logout` returns 500) | 204; row deleted; cookies cleared; WARN log `auth_logout_end_session_failed: ...`; revocation captured normally |
| 6 | End-session failure — connection refused | 204; same; WARN log; revocation captured normally |
| 7 | Both revocation AND end-session fail (both return 500) | 204; row STILL deleted; cookies STILL cleared; both WARN logs emitted |
| 8 | Missing session cookie | 401 `session_expired`; no calls to revocation/end-session captured; no row delete attempted; defensive Set-Cookie clears both cookies |
| 9 | Session cookie matches no row (stale value) | 401 `session_expired`; same as #8 |
| 10 | Expired session row | 401 `session_expired`; expired row deleted lazily; no revocation/end-session calls |
| 11 | Refresh-replay rejection after revocation | `synthetic-refresh-token` posted to `/token` with `grant_type=refresh_token` returns 400 `invalid_grant` (AC7's integration test) |
| 12 | Cookie attributes on clear | `Set-Cookie` for both `bff_session` and `bff_csrf` carries `Max-Age=0`, `Path=/`, `SameSite=Lax`. Session cookie carries `HttpOnly`; CSRF cookie does NOT carry `HttpOnly` (mirror the original set attributes — Story 1.5 P3 lesson). `Secure` is asserted under `bff_session_cookie_secure=True` AND its absence under `False` (one test each). |
| 13 | Response body is empty on 204 | `response.content == b""`; `response.headers["content-length"] == "0"` (FastAPI default for 204). |
| 14 | HTTP Basic auth on `/revocation` POST (RFC 7009 §2.1) | The captured request to `/revocation` carries `Authorization: Basic <base64(client_id:client_secret)>`. |
| 15 | Missing CSRF → 403 (Story 1.6 middleware) | 403 `csrf_invalid`. **Marked `@pytest.mark.skipif(not _has_csrf_middleware(), reason="CSRF middleware (Story 1.6) not yet installed")`** — unskipped once 1.6 lands. See Dependencies in Dev Notes. |

Coverage of `src/bff/api/auth.py` (with the new handler) AND the new functions in `src/bff/auth/keycloak_cookie_session.py` (`revoke_refresh_token`, `end_session`) AND `SessionService.delete_session` is **≥90%** per `[tool.coverage.report] fail_under = 90` (pyproject.toml:82). Project-wide gate is total `fail_under = 90`; per-module coverage of the logout code path is the epic's explicit ask (epics line 468: "coverage of the logout code path is ≥90%"). [Source: epics.md#Story 1.7 lines 464–468; services/bff/pyproject.toml:82.]

**AC9 — Gates remain green.** No new runtime or dev dependencies required (Authlib's `AsyncOAuth2Client` and `httpx` are already pinned by Story 1.5 — see pyproject.toml:23,11). From `services/bff/`:
- `uv sync --frozen` → exit 0 (lock untouched).
- `uv run ruff check` → clean.
- `uv run ruff format --check` → clean.
- `uv run ty check` → clean.
- `uv run pytest --cov` → all 223 prior tests + new logout tests pass; total coverage ≥ 90%.
- From repo root: `docker compose --profile default config` → valid; `docker compose build bff` → succeeds.

[Source: epics.md#Story 1.7 line 466; services/bff/pyproject.toml.]

## Tasks / Subtasks

- [ ] **Task 1: Add OIDC helpers — `revoke_refresh_token` + `end_session`** (AC: #2, #3, #4, #14)
  - [ ] In `services/bff/src/bff/auth/keycloak_cookie_session.py`, add `async def revoke_refresh_token(*, refresh_token: str, revocation_url: str, client_id: str, client_secret: str) -> None`:
    - Constructs a fresh `httpx.AsyncClient(timeout=_TOKEN_EXCHANGE_TIMEOUT)` (5s connect / 10s read — reuse the existing module constant at keycloak_cookie_session.py:34).
    - POSTs to `revocation_url` with `data={"token": refresh_token, "token_type_hint": "refresh_token"}` AND `auth=(client_id, client_secret)` (httpx auto-base64s for `Authorization: Basic` per RFC 7009 §2.1).
    - Calls `response.raise_for_status()` so any non-2xx raises `httpx.HTTPStatusError`.
    - Does NOT swallow exceptions — caller (`/auth/logout` handler) wraps in try/except and degrades.
    - **Authlib note:** `AsyncOAuth2Client` does NOT expose a clean revocation method (it's primarily for token-fetching). Use bare `httpx.AsyncClient` here — simpler than constructing an Authlib client.
  - [ ] Add `async def end_session(*, id_token: str, end_session_url: str, client_id: str, client_secret: str) -> None`:
    - Same `httpx.AsyncClient(timeout=_TOKEN_EXCHANGE_TIMEOUT)` pattern.
    - POSTs to `end_session_url` with form body `data={"id_token_hint": id_token, "client_id": client_id, "client_secret": client_secret}`. **Important:** Keycloak's RP-Initiated Logout (OIDC) accepts the `client_id`/`client_secret` form fields for confidential clients; the `id_token_hint` value comes from the `sessions.id_token` column.
    - `raise_for_status()`; caller handles the exception.
  - [ ] Both helpers MUST NOT log the token values; log at INFO level on entry/exit with first-8-chars of the relevant id (e.g., `auth_logout_revocation_call session_id=<first-8>...`); rely on the caller to log the failure classifier at WARN.
  - [ ] Create `services/bff/tests/auth/test_keycloak_cookie_session.py` test cases (extend existing file):
    - `test_revoke_refresh_token_posts_form_body_and_basic_auth` — uses `respx.mock` to assert the URL, method, form fields, and `Authorization: Basic` header.
    - `test_revoke_refresh_token_raises_on_5xx` — asserts `httpx.HTTPStatusError` propagates.
    - `test_revoke_refresh_token_raises_on_connect_error` — asserts `httpx.ConnectError` propagates.
    - `test_end_session_posts_form_body_with_id_token_hint` — same shape as revocation tests.
    - `test_end_session_raises_on_5xx` and `test_end_session_raises_on_connect_error`.
  - [ ] Run `uv run pytest tests/auth/test_keycloak_cookie_session.py -v` — all new + existing tests pass.

- [ ] **Task 2: Add `SessionService.delete_session`** (AC: #2 step 4, #5)
  - [ ] In `services/bff/src/bff/services/session_service.py`, add `async def delete_session(self, db: AsyncSession, *, session_id: str) -> None`:
    - Single indexed `delete(entities.Session).where(Session.id == session_id)` — symmetric with `delete_expired_session` at session_service.py:193–210 but without the `expires_at < now` predicate (this is the explicit logout case, not the lazy-cleanup case).
    - `synchronize_session=False` for the same D31 reason as `delete_expired_session` (SQLite naive datetime / ORM evaluator mismatch).
    - `await db.commit()` after the execute.
    - One-line INFO log `session_deleted id=<first-8>...` per architecture lines 783–788.
  - [ ] In `services/bff/tests/services/test_session_service.py` (extend existing), add:
    - `test_delete_session_removes_row` — seed a `sessions` row, call `delete_session`, query confirms `None`.
    - `test_delete_session_is_idempotent_when_missing` — call `delete_session` against a non-existent id; no exception; row count unchanged.
  - [ ] Run `uv run pytest tests/services/test_session_service.py -v` — all new + existing tests pass.

- [ ] **Task 3: Author `POST /auth/logout` handler** (AC: #1, #2, #3, #4, #5)
  - [ ] In `services/bff/src/bff/api/auth.py`, add a new handler `@router.post("/auth/logout", status_code=204)`:
    - Signature: `async def auth_logout(request: Request, db: Annotated[AsyncSession, Depends(get_session)], cfg: Annotated[AppSettings, Depends(_settings_dep)]) -> Response` (return `from fastapi import Response`; FastAPI emits 204 with empty body when `Response(status_code=204)` is returned).
    - Step 1 (session resolution): Read `request.cookies.get(cfg.bff_session_cookie_name)` → `session_id`. If absent → call `_clear_cookies_and_session_expired(cfg)` (new helper in same file) which returns `JSONResponse(status_code=401, content={errorCode:"session_expired", ...})` with `Set-Cookie` clearing both `bff_session` and `bff_csrf` (defensive).
    - Step 2: `row = await _session_service.get_session(db, session_id=session_id)`. If `None` OR `_as_utc_aware(row.expires_at) < datetime.now(UTC)` → call `_session_service.delete_expired_session(...)` (only if `row is not None`) → return the 401 envelope as in Step 1.
    - Step 3 (revoke): `revocation_url = cfg.oidc_issuer_url.rstrip("/") + "/protocol/openid-connect/revoke"`. Wrap `await revoke_refresh_token(refresh_token=row.refresh_token, revocation_url=..., client_id=cfg.oidc_client_id, client_secret=cfg.bff_client_secret)` in `try / except (httpx.HTTPError, httpx.HTTPStatusError, OSError) as exc:` — catch `httpx.HTTPError` (parent of ConnectError, ReadTimeout, ConnectTimeout, etc.) AND `httpx.HTTPStatusError` (raised by `raise_for_status()` on 4xx/5xx). Log `logger.warning("auth_logout_revocation_failed: %s", type(exc).__name__)`. Continue.
    - Step 4 (end-session): `end_session_url = cfg.oidc_issuer_url.rstrip("/") + "/protocol/openid-connect/logout"`. Same try/except shape; on failure log `auth_logout_end_session_failed: <type>`. Continue.
    - Step 5 (delete row): `await _session_service.delete_session(db, session_id=session_id)`.
    - Step 6 (build response): Construct `response = Response(status_code=204)`. Apply Set-Cookie clearing for `bff_session` and `bff_csrf` via two `response.set_cookie(...)` calls — see "cookie-clearing helper" below.
    - Final INFO log: `auth_logout_complete sub=<first-8>... session_id=<first-8>...` (reuse the existing `_safe_session_id_log` helper at auth.py:68).
  - [ ] Add a helper `_clear_session_cookies(response: Response, cfg: AppSettings) -> None` at module scope (auth.py):
    - Encapsulates the two `set_cookie(value="", max_age=0, ...)` calls so the success and the AC5 401-path share one implementation.
    - Session cookie clear: `key=cfg.bff_session_cookie_name, value="", max_age=0, httponly=True, samesite="lax", secure=cfg.bff_session_cookie_secure, path="/"`.
    - CSRF cookie clear: `key=cfg.bff_csrf_cookie_name, value="", max_age=0, httponly=False, samesite="lax", secure=cfg.bff_session_cookie_secure, path="/"` (non-HttpOnly to mirror the original `httponly=False` at auth.py:282).
    - **Do NOT** use `response.delete_cookie(...)` — Story 1.5 Review Findings established that `delete_cookie` omits `secure`/`samesite` args and breaks RFC 6265bis browsers under `BFF_SESSION_COOKIE_SECURE=True`. Use `set_cookie` with `max_age=0` explicitly.
  - [ ] Add a helper `_session_expired_with_cookie_clear(cfg: AppSettings) -> JSONResponse`:
    - Returns the 401 `session_expired` envelope with both cookies cleared (calls `_clear_session_cookies` on the JSONResponse).
    - Defensive: even though the cookie is stale, clearing it prevents browser-side replay.
  - [ ] Imports to add at the top of auth.py: `from fastapi import APIRouter, Depends, Request, Response`; ensure `httpx` is imported for the exception types in the try/except (`import httpx`). `from bff.auth.keycloak_cookie_session import (... revoke_refresh_token, end_session, ...)` extends the existing import block.

- [ ] **Task 4: Extend synthetic IdP for revocation enforcement** (AC: #7, #11)
  - [ ] In `services/bff/tests/auth/synthetic_idp.py`:
    - Add `revoked_refresh_tokens: set[str] = field(default_factory=set)` to the `SyntheticIdp` dataclass (after `pending_claims` at line 88).
    - Modify `_revocation_handler` (line 227–229): parse the form body, extract the `token` field, add to `idp.revoked_refresh_tokens`, return 200. The captured-revocations list is still appended for assertion access.
    - Modify `_token_handler` (line 196–223): add a new branch BEFORE the existing PKCE-verifier check — if `body.get("grant_type") == "refresh_token"`, then check `body.get("refresh_token") in idp.revoked_refresh_tokens`. If yes → return `httpx.Response(400, json={"error": "invalid_grant"})`. If the token is NOT revoked AND the request is otherwise valid, return a fresh token bundle (reuse the existing claims-stash pattern — for refresh-grant, mint a new access/id-token with the same `sub` from the original session; for the AC11 test, the refresh attempt is EXPECTED to fail so the "happy-path refresh" branch doesn't need to be fully implemented — a `400 invalid_request` for unknown `refresh_token` is acceptable as a fallthrough).
    - **Backward compatibility:** existing Story 1.5 tests call `/token` only with `grant_type=authorization_code`; the new `grant_type=refresh_token` branch is additive and doesn't break them.
  - [ ] Run `uv run pytest tests/auth/ -v` — Story 1.5's auth tests still pass.

- [ ] **Task 5: Route-level tests for `/auth/logout`** (AC: #2, #3, #4, #5, #7, #8 — scenarios 1–14)
  - [ ] In `services/bff/tests/api/test_auth.py` (extend), add a `class TestAuthLogout` (or top-level test functions following the existing style — Story 1.5 used top-level `async def test_...` functions; match the same style).
  - [ ] Add a helper `async def _seed_session(client, session, idp) -> tuple[str, str, entities.Session]` that runs `_complete_login` and returns `(session_cookie_value, csrf_cookie_value, sessions_row)` for use by logout tests. This avoids each test re-doing the full login round-trip.
  - [ ] Implement scenarios 1–10 from AC8 matrix (#11 is below):
    - **Scenario 1 (happy path):** Seed via login. POST `/auth/logout` with cookies + `X-CSRF-Token` header. Assert 204; assert empty body (`response.content == b""`); assert `idp.captured_revocations[0]["token"] == "synthetic-refresh-token"` AND `idp.captured_revocations[0]["token_type_hint"] == "refresh_token"`; assert `idp.captured_end_sessions[0]["id_token_hint"]` equals the seeded id_token; query confirms the `sessions` row is gone; both Set-Cookie headers carry `Max-Age=0`.
    - **Scenario 2 (revocation 5xx):** Use `respx_mock.post(DEFAULT_REVOCATION_URL).mock(return_value=httpx.Response(500))` to override the default 200. Assert 204; assert end-session was still called; assert `sessions` row deleted; assert cookies cleared; assert WARN log present (capture via `caplog`).
    - **Scenarios 3–4 (revocation ConnectError / ReadTimeout):** Use `respx_mock.post(DEFAULT_REVOCATION_URL).mock(side_effect=httpx.ConnectError("boom"))` and `httpx.ReadTimeout("slow")`. Same assertions as #2.
    - **Scenarios 5–6 (end-session 5xx / ConnectError):** Same shape against `DEFAULT_END_SESSION_URL`.
    - **Scenario 7 (both fail):** Override BOTH endpoints to fail. Assert 204; row deleted; cookies cleared; BOTH warn logs present.
    - **Scenario 8 (no session cookie):** POST `/auth/logout` from a fresh client (no cookies set). Assert 401 `session_expired`; assert no IdP calls captured; assert both Set-Cookie clears present (defensive).
    - **Scenario 9 (unknown session cookie):** POST with `bff_session=does-not-exist`. Assert 401; no IdP calls; clears emitted.
    - **Scenario 10 (expired session):** Seed a `sessions` row directly via the `session` fixture with `expires_at=datetime.now(UTC) - timedelta(hours=1)` (UTC-aware; `_as_utc_aware` normalization handles roundtrip in handler). POST with that cookie. Assert 401; assert row was deleted (lazy cleanup); no IdP calls.
    - **Scenarios 12 + 14 (cookie attributes + Basic auth):** Pull the raw Set-Cookie headers via `response.headers.get_list("set-cookie")` and parse with the `http.cookies` stdlib OR regex; assert each attribute. For Basic auth, intercept the `_revocation_handler` to capture the request and assert `request.headers.get("authorization", "").startswith("Basic ")` AND decode the base64 to assert `"<client_id>:<client_secret>"` is the decoded value.
    - **Scenario 13 (empty 204 body):** assert `response.content == b""` AND `response.headers.get("content-length") == "0"` (FastAPI emits 0 for 204).
    - **Scenarios 28-style cookie-secure test (variant from Story 1.5's harness):** Run scenarios 1 with `monkeypatch.setattr(settings, "bff_session_cookie_secure", True)` to assert the clear Set-Cookies carry `Secure`; rerun with `False` to assert absence.
  - [ ] **Scenario 11 (refresh-replay rejection — AC7 integration test):** A dedicated test `test_logout_revokes_refresh_token_at_idp`:
    - Seed a session via login. Assert `idp.revoked_refresh_tokens` is empty before logout.
    - Logout. Assert `"synthetic-refresh-token" in idp.revoked_refresh_tokens`.
    - Build a follow-up POST to `DEFAULT_TOKEN_URL` with `data={"grant_type": "refresh_token", "refresh_token": "synthetic-refresh-token", "client_id": ..., "client_secret": ...}` via a raw `httpx.AsyncClient` inside the respx scope.
    - Assert the response is 400 with body `{"error": "invalid_grant"}`.
  - [ ] **Scenario 15 (missing CSRF — Story 1.6 dependency):** Add a marker `pytest.mark.skipif(not _csrf_middleware_installed(), reason="depends on Story 1.6 CSRF middleware")` where `_csrf_middleware_installed()` introspects `app.user_middleware` (or imports `bff.auth.csrf` and catches `ImportError`). When the test runs, omit the `X-CSRF-Token` header and assert 403 `csrf_invalid`. Once Story 1.6 lands, the marker auto-unskips.
  - [ ] Run `uv run pytest tests/api/test_auth.py -v --cov=src/bff/api/auth` — all new + existing tests pass; coverage of `auth.py` ≥ 90%.

- [ ] **Task 6: Run the full BFF gate matrix** (AC: #9)
  - [ ] From `services/bff/`:
    - `uv sync --frozen` → exit 0 (no dep changes).
    - `uv run ruff check` → clean (if I001 import-order trips, `uv run ruff check --fix`).
    - `uv run ruff format --check` → clean (if format trips, `uv run ruff format`).
    - `uv run ty check` → clean. New helpers should not need `# ty: ignore`.
    - `uv run pytest --cov` → all 223 prior tests + new logout tests pass; total coverage ≥ 90%.
  - [ ] From repo root:
    - `docker compose --profile default config` → valid.
    - `docker compose build bff` → succeeds.
  - [ ] Capture command output excerpts in **Debug Log References**.

- [ ] **Task 7: Update sprint-status + deferred-work**
  - [ ] On story start: flip `_bmad-output/implementation-artifacts/sprint-status.yaml` development_status `1-7-bff-logout-endpoint-revoke-end-session-degrade-honestly: ready-for-dev` → `in-progress`. Bump `last_updated`.
  - [ ] On story complete (before `code-review`): flip to `review`. Bump `last_updated`.
  - [ ] If any new defects surface during implementation, append them as D45+ in `deferred-work.md` with severity / owner-story / rationale.

## Dev Notes

### What this story is — and is not

**This story implements the BFF's logout endpoint: `POST /auth/logout`. It tears down a server-side session (revoke refresh token at Keycloak → call end_session_endpoint → delete `sessions` row → clear both cookies → 204) and degrades honestly when the AS is unreachable (the local session is destroyed regardless).**

**Explicitly NOT in scope (each is a downstream story OR Story 1.6's responsibility):**

- **No CSRF middleware.** Story 1.6 owns `src/bff/auth/csrf.py` AND the `CSRF_INVALID` ErrorCode. This story RELIES on 1.6's middleware to enforce the AC6 `403 csrf_invalid` response on missing/mismatched `X-CSRF-Token`. The route is in the path namespace where 1.6's middleware applies (`/auth/*` is a state-changing path for POST per architecture A5). See **Dependencies** below.
- **No `ErrorCode.CSRF_INVALID` addition.** Story 1.6 adds the enum member; this story consumes it indirectly via the middleware.
- **No SPA changes.** Pure backend story. Story 1.10 (SPA LoginView + TopChrome) adds the "Log out" button that POSTs here; that story is also separately backlog.
- **No `/v1/test/reset` extension.** Story 1.12 owns the test-reset endpoint; logout has no shared code path with reset.
- **No SPA `AuthService.logout()` method.** Already exists per Story 1.9 (done). It POSTs to `/auth/logout`; this story makes that POST succeed.
- **No E2E (J5 spec).** Story 1.13 writes the Playwright spec; this story only provides BFF-side unit/integration tests.
- **No silent retries.** Architecture §C6: zero retries on `/token`-class Keycloak endpoints (revocation and end-session are in the same budget); the user can simply click "Log out" again if Keycloak is flaky. But — per A7 — the local session is destroyed BEFORE we'd retry anyway, so a retry would be meaningless.
- **No idle-timeout enforcement** beyond Story 1.5's `expires_at` semantics. Architecture §Operational Details lines 1369–1373: idle timeout = refresh-token lifetime; not explicitly enforced beyond the existing chain.
- **No `BookService`, `BooksService`, `/v1/books` routes** (Epic 2).
- **No `ResourceServerClient` (BFF → RS).** Story 3.5.

### Dependencies (CRITICAL — read before starting)

**Story 1.6 (BFF CSRF middleware + CSP header) is a prerequisite for this story's AC6 (the `403 csrf_invalid` response on missing/mismatched `X-CSRF-Token`).** Currently `sprint-status.yaml` shows BOTH 1-6 and 1-7 in `backlog`, but 1-6 is listed FIRST in epic order. **Recommended sequencing:** implement 1-6 first, then 1-7. If you implement 1-7 first:

1. **Scenario 15 (missing CSRF → 403)** in AC8's test matrix is `@pytest.mark.skipif(...)` until 1.6 lands.
2. **All other scenarios** (1–14) are independent of CSRF middleware and SHOULD all pass. The happy-path test (#1) sends `X-CSRF-Token` matching `bff_csrf` cookie; if 1.6's middleware isn't installed yet, the header is simply ignored and the route still works.
3. **When 1.6 lands later**, run `uv run pytest tests/api/test_auth.py::test_logout_missing_csrf -v` to confirm the unskipped scenario passes.

**Story 1.5 (cookie-session OIDC plugin) is the foundation.** It is `done`. This story extends `auth.py`, `keycloak_cookie_session.py`, `session_service.py`, and `synthetic_idp.py` — all created by 1.5. Story 1.4 (session + auth_state schema + migration) is also `done`; this story uses the existing `sessions` table with no schema changes.

**Story 1.9 (SPA AuthService + interceptors + functional guards) is `done`.** It already has an `AuthService.logout()` method that POSTs to `/auth/logout`. This story makes the BFF respond correctly.

### Previous story intelligence (from 1.1–1.5, 1.8, 1.9)

**Patterns established that this story must follow:**

- **`UTC` datetime everywhere.** `from datetime import UTC, datetime`. Never `datetime.utcnow()` (deprecated 3.12+). [Source: Story 1.4 dev notes; observability/logging.py:6; session_service.py:13.]
- **`secrets.token_urlsafe(32)` for opaque ids — but NOT in this story.** This story has no new opaque-id generation; it consumes existing values. Do NOT scatter `secrets` calls.
- **`AppException(ErrorCode, detail)` for envelope errors — but NOT for this story's 401.** Story 1.5 established that `/auth/callback`'s 4xx-with-cookie-clear needed a manual `JSONResponse` (rather than `AppException`) so it could carry `Set-Cookie`. The SAME pattern applies here: AC5's 401 carries `Set-Cookie` clearing both cookies, so use `JSONResponse` directly (mirror auth.py:75–101's `_auth_state_invalid_response` shape — see `_session_expired_with_cookie_clear` helper in Task 3).
- **`response.set_cookie(..., value="", max_age=0, ...)`, NOT `response.delete_cookie(...)`.** Story 1.5 Review Findings P3: `delete_cookie` omits `secure`/`samesite` and breaks RFC 6265bis browsers under `BFF_SESSION_COOKIE_SECURE=True`. [Source: 1-5 story Review Findings.]
- **Mirror the original `set_cookie` attributes when clearing.** Session cookie clear: `httponly=True`. CSRF cookie clear: `httponly=False` (mirrors auth.py:282 — the SPA reads it via `document.cookie`, so the original was non-HttpOnly).
- **`from bff.models import entities` then `entities.Session`.** Avoids shadowing `sqlalchemy.ext.asyncio.AsyncSession`. [Source: Story 1.4 anti-patterns; session_service.py:22.]
- **Logging via `logger = logging.getLogger(__name__)`.** Never `print`. Lifecycle = INFO; expected-but-interesting = WARN; unhandled = ERROR. First-8-chars + ellipsis for any session/cookie/token correlation id. **Critical for this story:** the WARN log on revocation/end-session failure MUST include a classifier (the exception type name) but MUST NOT include the token value, the session id beyond first-8-chars, or any URL fragment that includes secrets. Architecture lines 783–788 are explicit. [Source: architecture; Story 1.3, 1.5.]
- **Module-level `_session_service = SessionService()` singleton.** Story 1.5 established this pattern (auth.py:61, me.py:29). D44 flagged it as a code-quality concern (bypasses FastAPI DI) but DEFERRED. **Do NOT refactor to `Depends(SessionService)` in this story** — out of scope; future story can address. [Source: Story 1.5 deferred D44.]
- **The `client_no_redirects` fixture exists** at `tests/conftest.py:90–106` for inspecting 302s. POST `/auth/logout` returns 204, not a 302, so use the standard `client` fixture for happy-path tests; `client_no_redirects` may still be useful for the AC5 401-path if you want to confirm `Set-Cookie` headers without follow-redirect interference.
- **Synthetic IdP fixture pattern.** The `configured_idp` fixture in `tests/api/test_auth.py:38–56` is the established setup: monkeypatches `settings.oidc_*` to test URLs, mounts the IdP via `respx.mock(assert_all_called=False)`. **Reuse this fixture** for the logout tests — don't author a parallel one.
- **`monkeypatch.setattr(settings, "bff_session_cookie_secure", True)` to test the Secure attribute branch.** Story 1.5's test matrix did this via `configured_idp` fixture parameterization; the same pattern applies here.
- **`SQLite DB roundtrip strips tzinfo` — re-attach UTC.** `session_service.py:49–56` has `_as_utc_aware()` helper; the `/api/me` handler uses an inline copy. **This story should NOT re-implement** — import or inline the same helper for the AC5 expired-session check.
- **Coverage gate is total 90%** — `pyproject.toml:82`. Run from `services/bff/`.

**Deferred items relevant to this story:**

- **D43 (Zero leeway in PyJWT `exp` validation)** — orthogonal to logout. Not closed here.
- **D44 (Module-level `_session_service` singleton)** — relevant code quality concern but explicitly deferred. Do NOT refactor in this story.

**No new deferred items expected** unless implementation surfaces a new race condition or edge case (e.g., concurrent logout calls for the same session).

### Cookie-clearing — exact attribute table

Mirror Story 1.5's set attributes on the clear:

| Cookie | HttpOnly | Secure | SameSite | Path | Max-Age | Value | Source line(s) in 1.5 |
|---|---|---|---|---|---|---|---|
| `bff_session` (set at /auth/callback) | yes | `cfg.bff_session_cookie_secure` | Lax | `/` | (none — session) | `sessions.id` | auth.py:270–277 |
| `bff_session` (CLEAR on /auth/logout) | yes | `cfg.bff_session_cookie_secure` | Lax | `/` | **0** | `""` | this story |
| `bff_csrf` (set at /auth/callback) | **no** | `cfg.bff_session_cookie_secure` | Lax | `/` | (none — session) | `sessions.csrf_secret` | auth.py:279–286 |
| `bff_csrf` (CLEAR on /auth/logout) | **no** | `cfg.bff_session_cookie_secure` | Lax | `/` | **0** | `""` | this story |

**Why both cookies clear together:** the CSRF cookie's secret only has meaning paired with the session row's `csrf_secret`; once the row is gone, the cookie is dead weight. Clearing it on logout (a) avoids confusing the SPA's `csrfInterceptor` (it will read a stale value and send a header that no longer matches any row), and (b) leaves the browser in a clean unauthenticated state for the next login.

### Revocation endpoint shape (RFC 7009 + Keycloak)

**URL:** `<OIDC_ISSUER_URL>/protocol/openid-connect/revoke` (Keycloak standard suffix; same shape as `/token` and `/auth`).

**Method:** POST.

**Auth:** HTTP Basic with `client_id:client_secret` per RFC 7009 §2.1. httpx auto-base64s when you pass `auth=(client_id, client_secret)`. The synthetic IdP captures the request and assertions verify the header (AC8 #14).

**Body (form-encoded, `application/x-www-form-urlencoded`):**
- `token=<refresh_token>` (required)
- `token_type_hint=refresh_token` (RFC 7009 §2.1 — optional but signals which endpoint variant we're hitting; Keycloak respects it)

**Expected response:** 200 OK with empty body. RFC 7009 §2.2 mandates the AS MUST return 200 even if the token is unknown (idempotent revocation).

**Failure modes we handle:** non-2xx (Keycloak down or misconfigured), `httpx.ConnectError` (network unreachable), `httpx.ReadTimeout` (slow Keycloak), `httpx.ConnectTimeout` (DNS hang). All map to a single WARN log; downstream flow continues per A7.

**Why not Authlib?** Authlib's `AsyncOAuth2Client` is designed for token-fetching, not revocation. There is a `revoke_token` method on the OAuth2 client class but its API is awkward (sync-only in some Authlib versions, requires reconstruction of internal state). Bare `httpx.AsyncClient` is simpler — 5 lines vs 15.

### End-session endpoint shape (OIDC RP-Initiated Logout + Keycloak)

**URL:** `<OIDC_ISSUER_URL>/protocol/openid-connect/logout` (Keycloak standard; per the discovery doc's `end_session_endpoint`).

**Method:** POST (Keycloak supports both GET with redirect AND POST without redirect; we use POST so the response doesn't try to redirect the BFF process).

**Auth:** form fields `client_id` + `client_secret` (Keycloak's confidential-client variant — the form-field auth is documented for the `/logout` POST flavor specifically).

**Body (form-encoded):**
- `id_token_hint=<id_token>` (required — tells Keycloak which user's session to terminate)
- `client_id=<client_id>` (required for confidential clients in POST flavor)
- `client_secret=<client_secret>` (required for confidential clients in POST flavor)

**Expected response:** 200 OK (Keycloak emits a small HTML body on success; we ignore the body — `response.raise_for_status()` only checks the status code).

**Failure modes:** same as revocation; same WARN-and-continue policy.

### Honest-degradation contract (Architecture A7 + UX J5)

**The contract: NO half-logged-out states. EVER.**

The local session row IS deleted and the cookies ARE cleared, regardless of upstream success. The SPA receives 204. The user perceives a successful logout. This is by design:

1. **UX (J5, lines 536–538):** "If logout leaves residual access, the whole demo fails." A half-logged-out state would violate the "honest over flattering" principle.
2. **Security:** The local session is the only credential the BFF process needs to forge requests on the user's behalf. Once the row is gone, the BFF cannot impersonate the user even if it tries. Keycloak-side state (active refresh token) is best-effort cleanup; the user's effective session ends when the BFF row is destroyed.
3. **Operational reality:** Keycloak being briefly unreachable shouldn't trap users in a "you're still logged in" state. The educational reference must demonstrate graceful degradation.

**Logging contract:** the WARN log MUST allow operations to trace "did revocation succeed?" without exposing tokens. Format: `auth_logout_revocation_failed: <exception-type-name>` (e.g., `auth_logout_revocation_failed: HTTPStatusError`). Do NOT include the exception's `args` if those might contain URLs with tokens. Use `type(exc).__name__` only.

### Architecture-mandated contract details

#### HTTP status code (architecture §Format Patterns line 680 + C2 line 370)

`POST /auth/logout` returns **204 No Content** with an empty body. Not 200, not 302, not 204-with-body. FastAPI emits content-length: 0 for 204; `Response(status_code=204)` is the idiomatic way.

#### Path layout (architecture §C1 lines 358–361)

`/auth/logout` is **non-versioned** (mechanics, not domain). Lives alongside `/auth/login` and `/auth/callback` in `bff/api/auth.py`. Per architecture §"BFF routing precedence" lines 1343–1349, `/auth/*` matches in the BFF's routing stack BEFORE the static SPA fallback — so the new POST handler will be reached correctly.

#### Auth requirement (architecture §C2 line 370)

`POST /auth/logout` requires **session cookie auth** (no CSRF column in the original C2 table for this row — but architecture §A5 + §C2 line 371–378 establish that ALL state-changing requests use the double-submit CSRF pattern). Story 1.6 enforces this via middleware uniformly across `POST/PUT/PATCH/DELETE` on `/auth/*` and `/v1/*`.

#### Logging conventions (architecture lines 781–788)

- INFO on entry/exit: `auth_logout_start session_id=<8>...`, `auth_logout_complete sub=<8>... session_id=<8>...`.
- WARN on each upstream failure: `auth_logout_revocation_failed: <type>`, `auth_logout_end_session_failed: <type>`.
- ERROR on unhandled exceptions (e.g., DB unavailable mid-delete) — let FastAPI's `app_exception_handler` chain take over OR raise `AppException(ErrorCode.SERVICE_UNAVAILABLE)`.
- **Never** log: `refresh_token`, `id_token`, `access_token`, full session id, full sub, full cookie values, full URLs containing tokens.

#### Timeouts (architecture §C6 lines 411–416)

BFF → Keycloak budget is 5s connect / 10s read; **zero retries**. Reuse the existing `_TOKEN_EXCHANGE_TIMEOUT` constant at `keycloak_cookie_session.py:34` — it already encodes this budget for the `/token` exchange. The revocation and end-session calls have the same budget per §C6.

### Open questions to verify in implementation

1. **Keycloak's logout endpoint accepts `id_token_hint` in form body?** OIDC RP-Initiated Logout spec allows both query params (for GET) and form fields (for POST). Keycloak 26 supports both. Confirm by inspecting the Keycloak realm config (already done — `bmad-books-bff` is confidential client; POST with form body is the documented path). If the IdP rejects this shape with 400, fall back to GET with query params — but POST is preferred to avoid the redirect-response issue.
2. **`token_type_hint` value — `refresh_token` or `refresh`?** RFC 7009 §2.1 specifies `refresh_token` (with underscore). Keycloak follows the RFC. Use `refresh_token`.
3. **Does the synthetic IdP's `_token_handler` need to handle `grant_type=refresh_token` for non-revoked tokens too?** AC11 only requires that REVOKED tokens are rejected. For an unrecognized refresh token (not in `pending_codes`, not in `revoked_refresh_tokens`), returning 400 `invalid_request` is fine — Story 1.7 doesn't exercise the BFF's refresh-replay path (that's Story 3.5's `ResourceServerClient` job). Keep the synthetic IdP changes minimal.

### Path discrepancy: no synthetic IdP layout changes needed

The synthetic IdP fixture lives at `tests/auth/synthetic_idp.py` (Story 1.5 binding precedent; documented in 1-5 dev notes). This story extends it in place — no path discrepancy to resolve.

### Anti-patterns to avoid

- **Do NOT add `ErrorCode.CSRF_INVALID`.** Story 1.6 owns it.
- **Do NOT introduce CSRF enforcement code in this story.** Story 1.6's middleware is the single source. If you find yourself writing `request.headers.get("X-CSRF-Token")` in `auth.py`, stop — that's middleware territory.
- **Do NOT swallow exceptions silently.** Each upstream failure logs at WARN with a classifier. Naked `except: pass` would mask operational issues.
- **Do NOT use `response.delete_cookie(...)`.** Use `set_cookie(value="", max_age=0, ...)` with full attribute mirror. Story 1.5 Review Findings P3 is explicit.
- **Do NOT log token values, refresh tokens, id_tokens, access tokens, or full session ids.** First-8-chars + ellipsis. Architecture line 787.
- **Do NOT add `Path=` other than `/`.** Story 1.5's cookies are scoped to `/`; the clear must match or browsers won't recognize it.
- **Do NOT retry on revocation/end-session failure.** §C6 zero-retry budget; A7 says destroy local state and return 204.
- **Do NOT add a 200 response variant.** §C2 + §Format Patterns mandate 204.
- **Do NOT return a JSON body on 204.** `Response(status_code=204)` (no `JSONResponse`). FastAPI auto-emits empty body + `content-length: 0`.
- **Do NOT call Keycloak from inside the DB transaction.** Order: read row → call Keycloak (both) → delete row. The `await db.delete(row); await db.commit()` MUST come after the upstream calls — even though revocation might "succeed" before the local delete, the BFF's local session is what matters for re-protection; deleting it after the Keycloak calls means a concurrent `/api/me` during the upstream call still sees the session (acceptable race; SQLite's deferred locking helps anyway).
- **Do NOT preemptively refresh the access token before logout.** The refresh token is what we revoke; refreshing before logout would invalidate the very token we want to revoke (sometimes — depending on rotation policy). Just use the stored `refresh_token`.
- **Do NOT bypass the `_session_service` singleton.** Use the existing instance at `auth.py:61`. Don't instantiate a new `SessionService()` inside the handler.
- **Do NOT use `datetime.utcnow()`** (deprecated).
- **Do NOT log full URLs that may include client_secret in query params.** httpx Basic auth puts the secret in the Authorization header, not the URL — so this is moot for the calls we make, but worth a vigilance check.
- **Do NOT use `python3`.** Project convention (`CLAUDE.md`): always `python`.
- **Do NOT introduce `from __future__ import annotations` if the existing project does not use it** (Story 1.4 confirmed it does not; the existing `auth.py` uses PEP 604 / 484 types directly).
- **Do NOT scatter `httpx.AsyncClient(...)` instantiations.** Two helpers in `keycloak_cookie_session.py` each construct their own client; that's fine (each is short-lived, no pool to share). Do NOT add a third place where an httpx client is constructed inside the route handler.

### Naming and pattern compliance (architecture §"Implementation Patterns & Consistency Rules")

- **Python files:** `snake_case.py`. No new top-level files in this story (extensions of `auth.py`, `keycloak_cookie_session.py`, `session_service.py`, `synthetic_idp.py`).
- **Classes:** none new in this story.
- **Functions / methods:** `snake_case` — `revoke_refresh_token`, `end_session`, `delete_session`, `auth_logout`, `_clear_session_cookies`, `_session_expired_with_cookie_clear`.
- **Wire values:** `lower_snake_case` — `session_expired` (already in errors.py), `csrf_invalid` (Story 1.6).
- **Tests mirror source paths.** `src/bff/api/auth.py` → `tests/api/test_auth.py` (extend). `src/bff/services/session_service.py` → `tests/services/test_session_service.py` (extend). `src/bff/auth/keycloak_cookie_session.py` → `tests/auth/test_keycloak_cookie_session.py` (extend).

### Latest tech information

- **Authlib 1.6+ / httpx 0.28+** — both are already pinned via Story 1.5's deps (pyproject.toml). No version bumps required.
- **PyJWT 2.10+** — not used by this story (logout doesn't decode tokens; it just sends them to Keycloak).
- **respx 0.21+** — extended for this story's `/revocation` and `/logout` route mocks, including `side_effect=httpx.ConnectError(...)` for transport-failure simulation. respx supports `side_effect` with exception classes (raises in the route call) — used in AC8 scenarios 3, 4, 6.
- **Keycloak 26+** (compose/infra.yml) — supports OAuth 2.0 Token Revocation (RFC 7009) and OIDC RP-Initiated Logout in the realm's standard endpoint config. The realm-bmad-books.json at `keycloak/realm-bmad-books.json` does NOT need changes; revocation and end-session are realm-default capabilities for confidential clients.

### Git intelligence (recent commits)

```
2c2a86c feat: implement story 1.5
6550fa4 feat: implement story 1.4
ba784f8 Merge branch 'story-1-3'
295ed48 feat: 1-3 scaffold bffe
60aa25b feat: completed bff scaffolding
```

- Story 1.5 (the immediately-prior BFF story) just landed on `main` (2c2a86c). The `_session_service` singleton pattern, the `_safe_session_id_log` helper, and the synthetic-IdP fixture all date from that commit.
- Stories 1.8 (SPA scaffold) and 1.9 (SPA AuthService) are merged. The SPA already has an `AuthService.logout()` that POSTs to `/auth/logout`; this story is the BFF-side answer.
- Story 1.6 (CSRF middleware) is `backlog` — see Dependencies section. **Recommended:** do 1.6 first.
- Branch convention from prior stories: `story-1-7`. Create from `main`.
- No conflicts expected: stories 1.10–1.13 are downstream (backlog), Epic 2+ haven't started.

### Project Structure Notes

**Modified files (all under `services/bff/`):**

- `src/bff/api/auth.py` — add `POST /auth/logout` handler + `_clear_session_cookies` + `_session_expired_with_cookie_clear` helpers; extend imports for `Response` and `httpx`.
- `src/bff/auth/keycloak_cookie_session.py` — add `revoke_refresh_token` and `end_session` async helpers.
- `src/bff/services/session_service.py` — add `delete_session(self, db, *, session_id)` method.
- `tests/auth/synthetic_idp.py` — add `revoked_refresh_tokens: set[str]` field; extend `_revocation_handler` to populate it; extend `_token_handler` to reject revoked refresh-tokens on `grant_type=refresh_token`.
- `tests/api/test_auth.py` — add ~14 new test functions for logout scenarios (1–14 of AC8); add the `@skipif` for scenario 15 (CSRF — Story 1.6 dependency).
- `tests/auth/test_keycloak_cookie_session.py` — add 6 new tests for the two new helpers (request shape, 5xx propagation, ConnectError propagation).
- `tests/services/test_session_service.py` — add 2 new tests for `delete_session` (happy path + idempotent missing-row).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status flips + `last_updated`.

**New files:** NONE. This is a pure extension story.

**Untouched (verified):**

- `services/bff/pyproject.toml` / `uv.lock` — no dep changes.
- `services/bff/src/bff/main.py` — router registration unchanged (the existing `app.include_router(auth_router)` at main.py:52 picks up the new POST route automatically).
- `services/bff/src/bff/core/{config.py, errors.py, database.py}` — unchanged.
- `services/bff/src/bff/api/{me.py, health.py, v1/}` — unchanged.
- `services/bff/src/bff/models/entities/{session.py, auth_state.py}` — unchanged; the existing `sessions` table is the data source.
- `services/bff/alembic/` — no new migration (no schema changes).
- `services/bff/tests/conftest.py` — fixtures `client`, `client_no_redirects`, `session`, `engine` all reused as-is.
- `compose/`, `keycloak/`, `docker-compose.yml`, `keycloak/realm-bmad-books.json` — unchanged.
- `spa/`, `e2e/` — not in scope.
- `services/resource-server/` — does not exist yet (Epic 3).

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.7` lines 432–469] — canonical story spec (Given/When/Then ACs, revocation/end-session order, cookie clearing, degrade-honestly contract).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security A7` line 353] — "Revoke refresh token → call `end_session_endpoint` → clear local session → clear cookie." Plus: "If revocation fails: BFF still clears local session and returns 204 (UX forbids half-logged-out states)."
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns C2` line 370] — `POST /auth/logout` row in the BFF endpoints table; Auth = "Session cookie".
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns C6` lines 411–416] — BFF → Keycloak 5s connect / 10s read; zero retries on `/token`-class endpoints (revocation + end-session inherit this budget).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Format Patterns` lines 672, 680] — empty 204 responses ("no body, ever"); `POST /auth/logout` → 204.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Operational Details "BFF routing precedence"` lines 1343–1349] — `/auth/*` matches before SPA static fallback.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Logging conventions` lines 781–788] — INFO/WARN/ERROR levels; never log secrets/tokens; first-8-chars + ellipsis.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Requirements to Structure Mapping FR-LOGOUT-01` lines 1172–1176] — file-location contract: `src/bff/api/auth.py` + `src/bff/auth/keycloak_cookie_session.py` + `src/bff/services/session_service.py`.
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#J5` lines 509–538] — sequence diagram; success state = unauthenticated chrome; "honest over flattering" rationale.
- [Source: `_bmad-output/planning-artifacts/PRD.md#FR-LOGOUT-01` line 69] — "Users can log out, terminating both the browser session and the refresh token at the authorization server."
- [Source: `_bmad-output/implementation-artifacts/1-5-bff-cookie-session-oidc-plugin-pkce-synthetic-idp-test-harness.md`] — established patterns: `_safe_session_id_log`, `_auth_state_invalid_response` cookie-clear shape, synthetic IdP fixture (`configured_idp`), `client_no_redirects` fixture, `_complete_login` helper, Review Findings P3 (don't use `delete_cookie`).
- [Source: `_bmad-output/implementation-artifacts/1-4-bff-session-and-auth-state-schema-alembic-migration.md`] — `Session` / `AuthState` SQLModel contract; `_as_utc_aware` rationale for SQLite naive-datetime roundtrip.
- [Source: `services/bff/src/bff/api/auth.py:46–293`] — existing handlers; cookie-clear pattern (lines 75–101); router registration; `_safe_session_id_log` helper (line 68).
- [Source: `services/bff/src/bff/auth/keycloak_cookie_session.py:34`] — `_TOKEN_EXCHANGE_TIMEOUT` constant to reuse.
- [Source: `services/bff/src/bff/services/session_service.py:193–210`] — `delete_expired_session` as the pattern for `delete_session` (without the `expires_at < now` predicate).
- [Source: `services/bff/src/bff/api/me.py:51–87`] — `/api/me` handler shape for session-cookie reads + lazy-cleanup of expired rows; mirror for the AC5 path.
- [Source: `services/bff/src/bff/core/errors.py:20`] — `ErrorCode.SESSION_EXPIRED` (already exists; AC5 reuses it). `ErrorCode.CSRF_INVALID` is NOT added here (Story 1.6 owns it).
- [Source: `services/bff/tests/auth/synthetic_idp.py:196–237`] — `_token_handler`, `_revocation_handler`, `_end_session_handler` — the three handlers this story extends.
- [Source: `services/bff/tests/conftest.py:90–106`] — `client_no_redirects` fixture for 302 inspection.
- [Source: `services/bff/tests/api/test_auth.py:38–56`] — `configured_idp` fixture; reuse for logout tests.
- [Source: `keycloak/realm-bmad-books.json`] — realm config; `bmad-books-bff` confidential client; revocation + end-session enabled by default.
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.6` lines 396–430] — CSRF middleware story; AC6 dependency.
- [Source: RFC 7009 §2.1, §2.2] — OAuth 2.0 Token Revocation: Basic auth, form body, idempotent 200 even for unknown tokens.
- [Source: OpenID Connect RP-Initiated Logout 1.0 §2] — `id_token_hint` requirement on end-session; POST with form fields supported by Keycloak 26+.
- [Source: `CLAUDE.md`] — `python` (not `python3`).
- [Source: `[[project-bmad-books-backend-archetype]]` — user memory] — Python 3.14 + FastAPI + SQLModel + uv + OTEL archetype mandate.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
