---
status: ready-for-dev
story_key: 3-5-bff-resourceserverclient-refresh-replay-reading-speed-proxy-spa-settingsview-route
epic: 3
prerequisites: 3.3 (done — RS `ReadingSpeed` model + `/v1/reading-speed` GET/PUT, scope-gated `reading-speed:read` / `reading-speed:write`, project-specific `invalid_input`/`reading_speed_unset`/`forbidden_scope`/`session_expired` lower_snake wire codes); 3.4 (done — RS `POST /v1/test/reset`; conftest patterns for fresh-app test contexts); 1.5 (done — BFF `keycloak_cookie_session.py` exchange_code/revoke/end_session pattern; `OidcVerificationError`; httpx Timeout idiom); 1.6 (done — `CsrfMiddleware`; `csrf_token` cookie + `X-CSRF-Token` header double-submit); 1.9 (done — SPA `AuthService`, `withCredentialsInterceptor` (global 401 handler skipping `/api/me`), `csrfInterceptor`, functional guards `authGuard` / `redirectIfAuthedGuard`); 1.10 (done — SPA `TopChrome` contextual link, `ErrorMessage` shared component, `/settings` route loading `SettingsPagePlaceholder` via `authGuard`)
specLoopIteration: 1
---

# Story 3.5: BFF `ResourceServerClient` (refresh-and-replay) + `/v1/reading-speed` GET/PUT proxy + SPA `SettingsView` + `ReadingSpeedService` + `/settings` route

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a signed-in user,
I want to navigate to `/settings`, view my current reading speed (or an empty input if I haven't set one yet), save a new value, see a brief `"Saved"` acknowledgement on success, and see a distinct named error if the Resource Server is unavailable — all without ever knowing about access tokens, refresh tokens, or scope strings,
so that the J4 user surface works end-to-end and the BFF's transparent token-refresh behavior (NFR3 / architecture A6) is exercised on cross-service calls.

## Acceptance Criteria

### BFF side: `ResourceServerClient` + `/v1/reading-speed` proxy

**AC1 — `ResourceServerClient` module surface.** A new module `services/bff/src/bff/services/resource_server_client.py` is created with a `ResourceServerClient` class that wraps a plain `httpx.AsyncClient`. The client is configured with `httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)` per AR19 (epics line 76 and architecture §C6 line 413 — "BFF → RS: 5s connect, 10s read; zero retries on 5xx"). The class exposes the following public surface (and ONLY this surface; `compute_estimate` is explicitly deferred to Epic 4 Story 4.2 per epic line 1331):
- `__init__(self, settings: AppSettings, session_service: SessionService | None = None)` — accepts the AppSettings instance so `oidc_issuer_url` (for the Keycloak `/token` endpoint construction) and `oidc_client_id` / `bff_client_secret` are resolvable. The `session_service` arg defaults to a fresh `SessionService()` instance (mirrors `api/me.py:29`'s module-singleton pattern, but DI-friendly so tests can pass a mock).
- `async def get_reading_speed(self, db: AsyncSession, session_row: Session) -> tuple[int, dict[str, Any] | None]` — issues `GET <rs_base_url>/v1/reading-speed` with `Authorization: Bearer <session_row.access_token>`. Returns `(http_status, parsed_json_body_or_None)`. Body is `None` for 204/transport-level failures.
- `async def put_reading_speed(self, db: AsyncSession, session_row: Session, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None]` — issues `PUT <rs_base_url>/v1/reading-speed` with `Authorization: Bearer <session_row.access_token>` and JSON-encoded `payload`. Returns `(http_status, parsed_json_body_or_None)`.
- A module-level singleton `resource_server_client = ResourceServerClient(settings)` so the proxy router imports a pre-built instance (mirrors `api/me.py:29`'s `_session_service = SessionService()`).

The client encapsulates the refresh-and-replay cycle (AC4) internally — callers never see "first RS-401, then refresh, then retry"; they receive the FINAL `(status, body)` after at most one refresh cycle. The two public methods are SHAPED for the proxy router (which forwards body verbatim per AC3); they MUST NOT add per-user identifier query/path/body fields (NFR6 / architecture line 1141 — "`sub` is the only identifier that crosses service boundaries; the RS reads it from the JWT").

[Source: epics.md#Story 3.5 lines 1326-1331; architecture.md#C6 line 413; architecture.md lines 756-759; architecture.md line 1141.]

**AC2 — `RS_BASE_URL` configuration knob.** `AppSettings` (`services/bff/src/bff/core/config.py`) gains a new field `rs_base_url: str = "http://resource-server:8000"` (the compose-internal default — matches the `resource-server` service name in `compose/app.yml`). The `services/bff/.env.example` is extended with a new section "AR29: BFF → Resource Server" containing the line `RS_BASE_URL=http://resource-server:8000` with an inline comment "Compose-internal hostname; in dev (host runs), override to http://localhost:8001 or similar." Required-fail-fast validation: the value MUST start with `http://` or `https://` (mirrors `_validate_oidc_authorize_url_browser` at `core/config.py:113-132`). Empty string → reject at startup. This avoids the BFF silently calling `localhost` (or worse, an attacker-controlled URL) when misconfigured. [Source: epics.md#AR29; `services/bff/src/bff/core/config.py:78-96`; `compose/app.yml` resource-server service block.]

**AC3 — `/v1/reading-speed` proxy router (BFF).** A new module `services/bff/src/bff/api/reading_speed.py` registers an `APIRouter` mounted at `/v1/reading-speed` (via `bff/api/v1/__init__.py`'s prefix `/v1`). Concretely:

- `router = APIRouter(tags=["reading-speed"])`.
- The router is registered in `bff/api/v1/__init__.py` via `from bff.api.reading_speed import router as reading_speed_router; router.include_router(reading_speed_router)`. (The BFF v1 wrapper at `bff/api/v1/__init__.py` is currently empty; this is the first story to populate it. Verify the wrapper is mounted on `app` in `main.py:137` — it already is, no `main.py` edits beyond AC8 are required.)
- GET handler:
  ```python
  @router.get("/reading-speed")
  async def get_reading_speed(
      request: Request,
      db: Annotated[AsyncSession, Depends(get_session)],
      cfg: Annotated[AppSettings, Depends(_settings_dep)],
  ) -> JSONResponse:
      session_row = await _require_session(request, db, cfg)
      status, body = await resource_server_client.get_reading_speed(db, session_row)
      return JSONResponse(status_code=status, content=body)
  ```
- PUT handler:
  ```python
  @router.put("/reading-speed")
  async def put_reading_speed(
      request: Request,
      payload: dict[str, Any],
      db: Annotated[AsyncSession, Depends(get_session)],
      cfg: Annotated[AppSettings, Depends(_settings_dep)],
  ) -> JSONResponse:
      session_row = await _require_session(request, db, cfg)
      status, body = await resource_server_client.put_reading_speed(db, session_row, payload)
      return JSONResponse(status_code=status, content=body)
  ```
- `_require_session(request, db, cfg)` helper: reads the session cookie name from `cfg.bff_session_cookie_name`, looks the row up via `SessionService.get_session`, verifies `expires_at`. Returns the row OR raises `AppException(ErrorCode.SESSION_EXPIRED)` (which the existing `app_exception_handler` maps to 401 `session_expired`). The helper is a copy of the `api/me.py:51-69` pattern; do NOT extract a shared helper in this story (Story 3.5 is the first second-consumer of the pattern; extracting after only one consumer was Story 1.9's pre-mature-abstraction lesson — wait for a third consumer like Story 2.2's books CRUD).
- PUT accepts the body as `payload: dict[str, Any]` (NOT a typed Pydantic model). Rationale: the BFF proxy is transport-transparent for the body — typing on the BFF side would require maintaining a parallel `ReadingSpeedUpsert` DTO that drifts when the RS schema evolves. The RS validates the body via its own `ReadingSpeedUpsert(BaseModel)` with `extra="forbid"` + `Field(ge=1)`; the BFF MUST forward the body verbatim and surface the RS's 422 envelope as its own 422 response (AC5). FastAPI accepts `dict[str, Any]` as a request body and decodes the JSON without schema enforcement.
- Both handlers forward the RS's response body verbatim via `JSONResponse(status_code=status, content=body)`. They do NOT rewrap errorCodes, do NOT add fields, do NOT translate status codes — the BFF is a thin proxy. The single exception is AC6 (RS unavailable → 503 with project-owned envelope).

The proxy router is mounted at `/v1/reading-speed` and is wrapped by the BFF's standard middleware chain: `SecurityHeadersMiddleware` (innermost) → `CsrfMiddleware` (outermost). CSRF is enforced on PUT (state-changing); CSRF is exempt on GET (safe method). NO new exemption added to `CsrfMiddleware`'s `_CSRF_EXEMPT_PATHS` set — `/v1/reading-speed` is NOT exempt (only `/v1/test/reset` is, Story 1.12).

[Source: epics.md#Story 3.5 lines 1333-1347; architecture.md#C2 lines 376-378; architecture.md#A6 line 352.]

**AC4 — Refresh-and-replay cycle (the NFR3 / A6 demonstration).** The architecture's marquee BFF→RS behavior is single 401-refresh-replay. `ResourceServerClient.get_reading_speed` and `put_reading_speed` BOTH implement this cycle internally:

1. Issue the RS call with `Authorization: Bearer <session_row.access_token>`.
2. If the RS returns 401 (any 401, regardless of body shape — the RS could emit `session_expired`, `forbidden_scope`, or even no body), the client invokes `_refresh_access_token(db, session_row)` (see below).
3. If refresh SUCCEEDS, retry the RS call ONCE with the new `access_token`. Forward the retry's response — whatever its status — to the caller. The proxy router then forwards it to the SPA. **No further retries** regardless of the retry's outcome (epic line 1356 — "single refresh-and-replay cycle only" / AR19).
4. If refresh FAILS (Keycloak `/token` returns 4xx, 5xx, or a transport error), the BFF deletes the `sessions` row via `SessionService.delete_session(db, session_id=session_row.id)`, clears BOTH the session cookie AND the `csrf_token` cookie via `Set-Cookie` headers with `Max-Age=0` AND `Path=/` (matching the `/auth/logout` cookie-clear pattern — verify at `services/bff/src/bff/api/auth.py` around the logout response). Then responds **401** with `errorCode: "session_expired"` to the SPA. The SPA's global 401 handler (Story 1.9 `withCredentialsInterceptor`) routes the user to `/login?return_to=<current_url>`.

   **Cookie-clear semantics:** the response must include TWO Set-Cookie headers. To return a JSONResponse with custom Set-Cookie headers, use the FastAPI pattern:
   ```python
   response = JSONResponse(status_code=401, content={"errorCode": "session_expired", "message": "Authentication required", "detail": None})
   response.delete_cookie(cfg.bff_session_cookie_name, path="/")
   response.delete_cookie(cfg.bff_csrf_cookie_name, path="/")
   return response
   ```
   `Response.delete_cookie` emits `Set-Cookie: <name>=; Max-Age=0; Path=/; SameSite=lax` per Starlette's implementation. Verify the `path="/"` is the same path on which the cookies were originally set (it is — Story 1.5 sets both at root). Domain attribute is left unset (host-only); Secure attribute is omitted (matches `bff_session_cookie_secure=false` baseline + Story 1.7's pattern).

5. If refresh succeeds but the retry STILL returns 401 (Keycloak issued a new access_token, but the RS still rejected it — could indicate a scope/audience drift OR a JWT-validation race), the BFF responds 401 `session_expired` to the SPA WITHOUT clearing cookies and WITHOUT deleting the `sessions` row. Rationale: a transient drift may resolve on next request (e.g., RS JWKS cache refresh); deleting the session would force a full re-login when the underlying refresh actually succeeded. The SPA's redirect to `/login` produces a new login attempt; if it succeeds, the new tokens overwrite the old. [Source: epics.md#Story 3.5 lines 1362-1364.]

[Source: epics.md#Story 3.5 lines 1349-1364; architecture.md#A6 line 352; architecture.md#NFR3 line 38.]

**AC5 — Pass-through status forwarding (non-401 from RS).** The proxy router and `ResourceServerClient` forward the RS's response verbatim for these RS statuses (no body rewrite, no errorCode translation, no header injection beyond what `JSONResponse` adds):
- **RS 200 → BFF 200** with the same body (`{"pages_per_hour": <n>}` for GET; same for PUT happy path).
- **RS 412 → BFF 412** with envelope `{"errorCode": "reading_speed_unset", "message": "Reading speed not set for this user", "detail": null}` (forwarded verbatim from the RS's `core/errors.py:29-33` declaration).
- **RS 403 → BFF 403** with envelope `{"errorCode": "forbidden_scope", "message": "Required scope is missing", "detail": null}`. NOTE: under normal Keycloak realm config the BFF's user-access-token DOES carry both `reading-speed:read` and `reading-speed:write` scopes (verified by Story 1.5's realm config), so 403 is a defensive path. The test suite asserts the forwarding works regardless.
- **RS 422 → BFF 422** with the RS's `invalid_input` envelope verbatim — body shape `{"errorCode": "invalid_input", "message": "Request validation failed", "detail": [<list of pydantic errors WITHOUT the user-supplied input field, per RS Story 3.3's sanitization>]}`. The BFF does NOT re-validate the body; the RS's `ReadingSpeedUpsert` with `extra="forbid"` + `Field(ge=1)` is the source of truth.
- **RS 204 (theoretical — RS doesn't emit 204 for these endpoints today, but defensive) → BFF 204** with empty body.

For each non-401 case, the BFF's `_refresh_access_token` is NOT called — the cycle is `RS 401 → refresh → retry` ONLY. A 412, 403, 422, 500, 502, 503, 504 from the RS short-circuits the refresh path. The 5xx case is AC6 (RS unavailable).

[Source: epics.md#Story 3.5 lines 1338-1347; architecture.md#"Format Patterns" lines 686-690.]

**AC6 — Honest 502/503 on RS unreachable (FR-ERROR-01 / AR17 / J6).** When `ResourceServerClient` cannot reach the RS or the RS returns a 5xx, the BFF MUST surface an **HTTP 503** response with envelope:
```json
{"errorCode": "resource_server_unavailable", "message": "The reading-speed service is temporarily unavailable", "detail": null}
```
**Specific trigger conditions** (the union is the full "RS unavailable" set):
- `httpx.ConnectError` (TCP connection refused / DNS failure) — RS container down or compose hostname unresolvable.
- `httpx.ConnectTimeout` (connect-timeout exceeded after 5s, per AR19).
- `httpx.ReadTimeout` (read-timeout exceeded after 10s, per AR19) — RS hung on a slow query.
- `httpx.WriteTimeout` / `httpx.PoolTimeout` — defensive parity with the other timeout shapes.
- `httpx.NetworkError` / `httpx.RemoteProtocolError` / `httpx.TransportError` (catch-all parent for transport failures) — fail-safe broad catch.
- RS responds with any 5xx (500, 501, 502, 503, 504, 599).

**Implementation:** wrap the httpx call in `try/except httpx.HTTPError as exc:` (the base class — covers all the transport errors above). Inside the try, check `response.status_code >= 500` AFTER the response lands and raise a custom internal exception (e.g., `_RsUnavailable("rs_5xx_response status=<n>")`) that's caught by the same except block. **Both paths funnel into the same 503 envelope.** Add the new ErrorCode member `RESOURCE_SERVER_UNAVAILABLE = ("resource_server_unavailable", "The reading-speed service is temporarily unavailable", 503)` to `services/bff/src/bff/core/errors.py` (next to the existing project-specific codes block, lines 20-28; preserve the leading comment that enumerates the codes per the existing pattern).

**No retries** on the 5xx path (epic line 1369 — "the BFF does NOT retry the request (no silent cross-service retries per AR19)"). The 401-refresh-replay cycle does NOT fire on 5xx — it's exclusively for 401. The 503 surface is final.

**Logging:** on every 5xx-classified failure, emit a WARN log `resource_server_unavailable cause=<classifier> http_status=<n_or_None>` where `<classifier>` is one of `connect_error`, `connect_timeout`, `read_timeout`, `write_timeout`, `pool_timeout`, `network_error`, `rs_5xx_response`, `unknown_transport`. The bearer token, refresh token, and session id are NEVER logged (architecture lines 781-788). Truncate `session_id` to first-8-chars if logged at all (mirrors `session_service.py:236-238`).

[Source: epics.md#Story 3.5 lines 1366-1369; epics.md#AR17 line 74; epics.md#AR19 line 76; architecture.md#"Format Patterns" line 688; PRD §FR-ERROR-01.]

**AC7 — Identity propagation (NFR6).** The BFF never adds `sub` (or any user identifier) to the request body, path, or query string when calling the RS. The RS reads `sub` from the JWT only (per architecture line 1141 — "`sub` is the only identifier that crosses service boundaries"). Concretely: `ResourceServerClient.get_reading_speed` calls `<rs_base_url>/v1/reading-speed` with NO query parameters; `put_reading_speed` forwards the request body unchanged (i.e., if the SPA posts `{"pages_per_hour": 30}`, the BFF posts the same JSON object to the RS — no `sub` injection). A regression test pins both shapes (`captured_request.url.query == ""` and the captured body matches the input verbatim). [Source: epics.md#Story 3.5 lines 1371-1373; architecture.md line 1141; architecture.md#NFR6 (identity-propagation invariant).]

**AC8 — `main.py` wiring is unchanged.** `v1_router` is already registered in `main.py:137` (Story 1.10's leftover wiring). This story does NOT modify `main.py`. The new proxy router is mounted by including it INTO `v1_router` in `bff/api/v1/__init__.py` (which currently declares `router = APIRouter(prefix="/v1")` and includes nothing). Story 3.5 adds:
```python
from bff.api.reading_speed import router as reading_speed_router

router.include_router(reading_speed_router)
```
Verify: `GET /v1/reading-speed` and `PUT /v1/reading-speed` appear in `app.openapi()` after the change; before the change, the OpenAPI schema lists ZERO paths under `/v1/*`. [Source: `services/bff/src/bff/main.py:137`; `services/bff/src/bff/api/v1/__init__.py`.]

**AC9 — Pre-existing session contract preserved.** The session cookie name (`cfg.bff_session_cookie_name`, default `bff_session`), the session lookup via `SessionService.get_session(...)`, and the expiry check (`row.expires_at < datetime.now(UTC)`) are LITERALLY copied from `api/me.py:50-69`. The proxy returns 401 `session_expired` for all three failure modes:
- Missing session cookie → 401 `session_expired`.
- Unknown session id (no row matching cookie value) → 401 `session_expired`.
- Expired session row (`expires_at < now`) → 401 `session_expired`; the expired row is lazily deleted via `SessionService.delete_expired_session(db, session_id=...)` (same as `api/me.py:67`).

These three 401 envelopes are emitted via `raise AppException(ErrorCode.SESSION_EXPIRED)` — the existing `app_exception_handler` maps the exception to the standard envelope. **NO cookies are cleared in these three pre-RS-call cases.** Cookie clearing is exclusive to the refresh-failure path (AC4 case 4). Rationale: a stale cookie from a long-closed browser is harmless; clearing it on every "no session" hit would interfere with concurrent tabs that just successfully logged in. [Source: `services/bff/src/bff/api/me.py:50-69`.]

**AC10 — CSRF enforcement on PUT, exemption on GET.** PUT requests against `/v1/reading-speed` MUST be rejected with **403** `csrf_invalid` if the `X-CSRF-Token` header is missing or does not match the `csrf_token` cookie, per the existing `CsrfMiddleware` (Story 1.6, `services/bff/src/bff/auth/csrf.py:53-138`). The CSRF check happens BEFORE the route handler runs (middleware-level), so no test setup is needed — just verify that PUT without the CSRF header returns 403 `csrf_invalid`. **No new path is added to `_CSRF_EXEMPT_PATHS`** (only `/v1/test/reset` is exempt; Story 1.12). GET requests are automatically exempt from CSRF (safe method per `_SAFE_METHODS` at `csrf.py:32`). The existing `client_with_csrf` fixture (conftest.py:97-126) provides the cookie + header + Origin combo for happy-path tests. [Source: `services/bff/src/bff/auth/csrf.py:53-138`; epics.md#Story 3.5 line 1334.]

### Tests — BFF

**AC11 — `tests/api/test_reading_speed_proxy.py` covers all proxy paths.** New file under `services/bff/tests/api/`. Uses the existing `client` / `client_with_csrf` fixtures + `respx` for mocking the RS endpoint (mirrors `tests/api/test_auth.py`'s respx pattern). Tests required:

| # | Scenario | Setup | Asserted |
|---|---|---|---|
| 1 | GET happy 200 forwards body | seeded session + respx mock returns 200 `{"pages_per_hour": 30}` | response 200 + body forwarded verbatim |
| 2 | GET RS 412 forwards | respx returns 412 `{"errorCode":"reading_speed_unset","message":"...","detail":null}` | response 412 + body forwarded |
| 3 | GET RS 403 forwards | respx returns 403 `forbidden_scope` envelope | response 403 + body forwarded |
| 4 | GET no session cookie | client without cookie | 401 + `errorCode:"session_expired"` |
| 5 | GET unknown session id | client with cookie pointing at non-existent row | 401 `session_expired` |
| 6 | GET expired session | seed row with `expires_at < now`; GET | 401 `session_expired`; row deleted post-call |
| 7 | PUT happy 200 forwards body | respx 200 + valid CSRF + valid session | 200 + body forwarded |
| 8 | PUT missing CSRF header | `client` fixture (no CSRF) | 403 `csrf_invalid` |
| 9 | PUT RS 422 forwards | respx 422 `invalid_input` envelope (with sanitized detail list) | 422 + body forwarded |
| 10 | PUT RS 403 forwards | respx 403 `forbidden_scope` | 403 + body forwarded |
| 11 | PUT body verbatim forward | respx captures body; SPA posts `{"pages_per_hour": 30}` | captured body equals `{"pages_per_hour":30}` byte-for-byte; NO `sub` field; NO query string on RS URL |
| 12 | GET RS ConnectError → 503 | respx side_effect raises `httpx.ConnectError` | 503 + `errorCode:"resource_server_unavailable"`; WARN log `cause=connect_error`; called exactly ONCE (no retry) |
| 13 | GET RS ReadTimeout → 503 | respx raises `httpx.ReadTimeout` | 503; WARN `cause=read_timeout`; called once |
| 14 | GET RS 500 → 503 | respx returns 500 | 503 + same envelope; WARN `cause=rs_5xx_response`; called once |
| 15 | GET RS 502 → 503 | respx returns 502 | 503 + same envelope; called once |
| 16 | GET RS 503 → 503 | respx returns 503 | 503 + same envelope; called once |
| 17 | PUT RS 504 → 503 | respx returns 504 | 503 + same envelope; called once |
| 18 | PUT RS WriteTimeout → 503 | respx raises `httpx.WriteTimeout` | 503; cause=`write_timeout` |
| 19 | No-retry on 5xx (mock counter) | respx 500; explicit `assert respx_mock.call_count == 1` | proves AC6 "no silent cross-service retries" |
| 20 | Authorization header carries Bearer + session.access_token | inspect captured request | `request.headers["authorization"] == f"Bearer {session.access_token}"` |

Coverage of `src/bff/api/reading_speed.py` and `src/bff/services/resource_server_client.py` is **≥90%** (per epic line 1459) — both files will land at >95% with the test matrix above.

[Source: epics.md#Story 3.5 lines 1455-1459; existing BFF respx pattern at `services/bff/tests/api/test_auth.py`.]

**AC12 — `tests/services/test_resource_server_client.py` covers refresh-and-replay.** New file under `services/bff/tests/services/`. Uses the BFF's synthetic-IdP harness (`services/bff/tests/auth/synthetic_idp.py`) to mock Keycloak's `/token` endpoint (refresh-grant branch already lives there per `synthetic_idp.py:214-238`). Tests required:

| # | Scenario | Setup | Asserted |
|---|---|---|---|
| 1 | refresh-and-replay happy path | RS returns 401 → respx `/token` returns 200 with new access_token + refresh_token → RS retry returns 200 | final response forwarded as 200; `session_row.access_token` updated in DB; `session_row.refresh_token` rotated if Keycloak returned a new one |
| 2 | refresh-and-replay: RS retry still 401 | RS 401 → token refresh 200 → RS retry 401 | 401 `session_expired` to SPA; sessions row NOT deleted; cookies NOT cleared |
| 3 | refresh fails (4xx from Keycloak) | RS 401 → token refresh 401 `invalid_grant` (synthetic IdP's revoked-token path) | 401 `session_expired`; session row deleted; both cookies cleared with `Max-Age=0` |
| 4 | refresh fails (5xx from Keycloak) | RS 401 → token refresh 503 | 401 `session_expired`; session row deleted; cookies cleared |
| 5 | refresh fails (network error) | RS 401 → token refresh raises `httpx.ConnectError` | 401 `session_expired`; session row deleted; cookies cleared |
| 6 | refresh updates session row's `expires_at` | RS 401 → refresh returns token with `expires_in: 3600` | `session_row.expires_at` advances to approximately `now + 3600s` (use `assert (row.expires_at - datetime.now(UTC)).total_seconds() > 3500`) |
| 7 | refresh: new refresh_token persisted (rotation) | Keycloak returns new `refresh_token: "rotated-rt"` | DB row's `refresh_token == "rotated-rt"` |
| 8 | refresh: missing refresh_token in response → session deleted | Keycloak returns 200 with `access_token` but no `refresh_token` | 401 `session_expired`; session row deleted (the cycle treats incomplete responses as failure) |
| 9 | NFR6 — no `sub` in RS URL or body | inspect captured request to RS | `request.url.query == ""`; body does NOT contain `sub` field |
| 10 | refresh-and-replay does NOT fire on 412 | RS returns 412 directly | NO `/token` call captured by synthetic IdP (assert `len(idp.captured_token_exchanges) == 0` after the call) |
| 11 | refresh-and-replay does NOT fire on 403 | RS returns 403 | same — no `/token` call |
| 12 | refresh-and-replay does NOT fire on 422 | RS returns 422 | same — no `/token` call |
| 13 | refresh-and-replay does NOT fire on 5xx | RS returns 500 | same — no `/token` call (5xx is the unavailable path, not the refresh path) |
| 14 | refresh-and-replay does NOT fire when session is already expired | call with `session.expires_at < now` | proxy returns 401 BEFORE the RS is called; respx asserts `call_count == 0` on the RS mock |
| 15 | single refresh attempt only (no double-refresh) | RS 401 → refresh 200 → retry 401 | exactly ONE `/token` call captured; exactly TWO RS calls captured |
| 16 | refresh uses correct grant_type | inspect captured `/token` request body | `body["grant_type"] == "refresh_token"`; `body["refresh_token"] == session.refresh_token` |
| 17 | refresh uses client credentials | inspect captured `/token` request | client_id + client_secret carried per BFF's existing pattern (verify shape matches `auth.py`'s token-exchange call form) |
| 18 | refresh failure: WARN log emitted | refresh fails | caplog at WARN: `refresh_failed cause=<classifier>` with classifier ∈ `{keycloak_4xx, keycloak_5xx, transport_error, malformed_response}` |
| 19 | refresh failure: cookies cleared with correct attributes | inspect `Set-Cookie` headers on the 401 response | two Set-Cookie lines: `bff_session=; Max-Age=0; Path=/`, `csrf_token=; Max-Age=0; Path=/` |
| 20 | refresh-and-replay happy path: WARN/INFO logs | caplog | INFO `access_token_refreshed sub=<sub> session=<id8>...`; no warns |

Coverage of `services/resource_server_client.py` ≥90%. The synthetic IdP fixture's `_token_handler` already supports the `refresh_token` grant (line 214 — synthetic_idp.py); for failure scenarios use the existing pattern of `idp.revoked_refresh_tokens.add(<token>)` (synthetic_idp.py:263), which causes the IdP to return 400 `invalid_grant`. For transport errors, monkeypatch the `httpx.AsyncClient.post` to raise.

[Source: epics.md#Story 3.5 line 1458; `services/bff/tests/auth/synthetic_idp.py:207-275`.]

**AC13 — Existing tests stay green.** All Epic 1 BFF tests (the 220-ish in the conftest-counted set) MUST remain green. No edits to the existing test files are expected — this story is purely additive on the BFF. **Specifically test the existing `tests/api/test_me.py`'s 401 path still works** (the new RESOURCE_SERVER_UNAVAILABLE ErrorCode addition does not perturb the existing envelope shapes).

### SPA side: `SettingsView` + `ReadingSpeedService`

**AC14 — `AppError` discriminated union module.** A new directory `spa/src/app/shared/errors/` is created (it does not exist yet — verified). Two files:

- `spa/src/app/shared/errors/app-error.types.ts` — exports the `AppError` discriminated union:
  ```ts
  export type AppError =
    | { kind: 'reading_speed_unset' }
    | { kind: 'resource_server_unavailable' }
    | { kind: 'invalid_input'; detail?: unknown }
    | { kind: 'forbidden_scope' }
    | { kind: 'unknown'; status?: number; errorCode?: string; message?: string };
  ```
  This is the minimal set this story needs. Per architecture lines 714-731, the union grows organically as stories surface new domain errors. **Do NOT pre-stage** Epic 4 / Epic 2 variants (e.g., `book_not_found`) — those land with their owning stories.

- `spa/src/app/shared/errors/error-service.ts` — exports `ErrorService` (`@Injectable({providedIn: 'root'})`) with one method `parse(err: unknown): AppError`. Logic:
  1. If `err instanceof HttpErrorResponse` and `err.status === 503`, check the body's `errorCode` field. If `errorCode === 'resource_server_unavailable'`, return `{ kind: 'resource_server_unavailable' }`.
  2. If `err.status === 412` and `errorCode === 'reading_speed_unset'`, return `{ kind: 'reading_speed_unset' }`.
  3. If `err.status === 422` and `errorCode === 'invalid_input'`, return `{ kind: 'invalid_input', detail: err.error?.detail }`.
  4. If `err.status === 403` and `errorCode === 'forbidden_scope'`, return `{ kind: 'forbidden_scope' }`.
  5. Else return `{ kind: 'unknown', status: err.status, errorCode: err.error?.errorCode, message: err.error?.message }`.
  6. If `err` is NOT an `HttpErrorResponse`, return `{ kind: 'unknown' }` (no status).

**Note:** `session_expired` (401) is intentionally NOT a variant. The global `withCredentialsInterceptor` (Story 1.9) handles 401s by navigating to `/login?return_to=…`; the SPA's feature services never observe a 401 as an AppError because the interceptor rethrows AFTER scheduling the navigation, and the service's catch block then converts it to `{ kind: 'unknown' }` — which the SettingsView's render code never inspects because the navigation has already occurred. The architecture (lines 728-731) explicitly states this.

[Source: architecture.md lines 714-731; epics.md#Story 3.5 line 1396.]

**AC15 — `ReadingSpeedService` (`spa/src/app/settings/reading-speed-service.ts`).** New service per epic line 1379, `@Injectable({providedIn: 'root'})`. Reactive state via Angular signals:

- `readonly pagesPerHour = signal<number | null>(null)` — `null` is the legitimate "unset" state from 412.
- `readonly loading = signal<boolean>(false)`.
- `readonly loadError = signal<AppError | null>(null)`.
- `readonly saving = signal<boolean>(false)`.
- `readonly saveError = signal<AppError | null>(null)`.
- `readonly justSaved = signal<boolean>(false)` — pulsed true for ~1s after a successful save.

(Implementation note: the service exposes the WRITABLE signals directly OR exposes read-only views via `.asReadonly()`. Mirror `AuthService`'s pattern: keep writable signals private; expose `Signal<T>` read-only types publicly. Internal writers are private methods like `_resetLoadState()` etc.)

Public methods:

- `async load(): Promise<void>` — sets `loading(true)`, `loadError(null)`, issues `GET /v1/reading-speed` via `HttpClient`.
  - On 200: parses `response.pages_per_hour`, sets `pagesPerHour.set(<value>)`, `loading.set(false)`.
  - On 412: sets `pagesPerHour.set(null)`, `loadError.set(null)`, `loading.set(false)`. **412 is NOT an error** from the SPA's perspective; it is the legitimate unset-state-on-first-use semantic. The helper text `"e.g., 30"` is the user-facing cue per UX-DR9.
  - On 503 (parsed via `ErrorService` to `{ kind: 'resource_server_unavailable' }`): sets `loadError` to that AppError, `pagesPerHour.set(null)`, `loading.set(false)`.
  - On 401: the global `withCredentialsInterceptor` handles the navigation. The service's catch block sets `loading.set(false)` and DOES NOT set `loadError` (the SettingsView is being torn down by the route navigation anyway).
  - On any other error: sets `loadError` to the parsed AppError (probably `{ kind: 'unknown' }`), `loading.set(false)`.

- `async save(value: number): Promise<void>` — sets `saving(true)`, `saveError(null)`, issues `PUT /v1/reading-speed` with body `{ pages_per_hour: value }`.
  - On 2xx: parses `response.pages_per_hour`, sets `pagesPerHour.set(<value>)`, toggles `justSaved.set(true)` then schedules `setTimeout(() => justSaved.set(false), 1000)` for the ~1s pulse per UX-DR9 / UX-DR11 + epic line 1440, sets `saving.set(false)`.
  - On 422: parses to `{ kind: 'invalid_input', ... }` AppError, sets `saveError`, `saving.set(false)`.
  - On 503: sets `saveError` to `{ kind: 'resource_server_unavailable' }`, `saving.set(false)`.
  - On 401: same as `load` — global handler navigates, service just resets `saving`.
  - On any other error: sets `saveError` to the parsed AppError, `saving.set(false)`.

**HTTP wiring:** `inject(HttpClient)` — the existing `withCredentialsInterceptor` adds `withCredentials: true` and `csrfInterceptor` attaches `X-CSRF-Token` automatically on PUT. The service does NOT touch headers or interceptors directly.

[Source: epics.md#Story 3.5 lines 1383-1404; UX-DR9 (epics line 111); UX-DR11 (line 113).]

**AC16 — `reading-speed.types.ts`.** New file `spa/src/app/settings/reading-speed.types.ts` exporting:
```ts
export interface ReadingSpeedOut {
  pages_per_hour: number;
}
```
Wire shape is `snake_case` (no case-conversion layer, per architecture AR16 / line 554-560). The interface is the contract the BFF/RS emit for both GET and PUT happy paths. **Do NOT** introduce a `ReadingSpeedUpsert` SPA interface — the request body is shaped inline by the service (`{ pages_per_hour: value }`); typing it adds zero safety in a one-call site. [Source: epics.md#Story 3.5 line 1380; architecture.md lines 554-560.]

**AC17 — `SettingsPage` component (replaces placeholder).** New files:
- `spa/src/app/settings/settings-page.ts`
- `spa/src/app/settings/settings-page.html`
- `spa/src/app/settings/settings-page.css`
- `spa/src/app/settings/settings-page.spec.ts`

The placeholder `spa/src/app/settings/settings-page-placeholder.ts` is **DELETED** (the route is repointed at the new component — AC19). `SettingsPage` is a standalone component with selector `app-settings-page`, `changeDetection: ChangeDetectionStrategy.OnPush`. Injects `ReadingSpeedService`. Imports `ErrorMessage` (the shared component from Story 1.10).

**On init**: calls `inject(ReadingSpeedService).load()` (use `inject` at field-level + a constructor body or `ngOnInit` — either is acceptable Angular v21 idiom; tests assert that `load` is called once on activation).

**Template (settings-page.html)** — centered 720px column (the parent `<main class="app-content">` from `app.html` already provides the column; the component renders inside it):
```html
<section class="settings-page">
  <h1 class="settings-heading">Reading speed</h1>
  <form (submit)="onSubmit($event)" novalidate>
    <label for="pages-per-hour" class="settings-label">Pages per hour</label>
    <input
      id="pages-per-hour"
      type="number"
      min="1"
      class="settings-input"
      [value]="inputValue()"
      (input)="onInput($event)"
      [disabled]="loading() || saving()"
    />
    <p class="settings-helper">e.g., 30</p>
    @if (validationError(); as msg) {
      <app-error-message [message]="msg" />
    }
    @if (loadError(); as err) {
      @if (err.kind === 'resource_server_unavailable') {
        <app-error-message message="Service unavailable — try again shortly" />
      }
    }
    @if (saveError(); as err) {
      @if (err.kind === 'resource_server_unavailable') {
        <app-error-message message="Service unavailable — try again shortly" />
      } @else if (err.kind === 'invalid_input') {
        <app-error-message message="Enter a positive number" />
      } @else {
        <app-error-message message="Couldn't save — try again" />
      }
    }
    <button
      type="submit"
      class="settings-save"
      [disabled]="loading() || saving()"
    >
      {{ saveButtonLabel() }}
    </button>
  </form>
</section>
```

**Component state and methods (settings-page.ts):**
- `readonly speed = inject(ReadingSpeedService);` — public so the template binds via `speed.loading()` etc., OR exposes thin pass-through computeds. Choose the form that yields the cleanest template; both pass the AC.
- `readonly loading = this.speed.loading;`
- `readonly saving = this.speed.saving;`
- `readonly loadError = this.speed.loadError;`
- `readonly saveError = this.speed.saveError;`
- `readonly justSaved = this.speed.justSaved;`
- A LOCAL writable signal `inputValueSignal = signal<string>('')` — bound to the input's value. **On first paint** (after `load()` resolves), an `effect()` synchronizes `inputValueSignal` from `speed.pagesPerHour()` IF the user has not edited yet. Mirrors UX-DR9: "Given `pagesPerHour()` resolves to a number `n` and `loadError()` is null, the input is populated with `n`."
- A LOCAL `validationError = signal<string | null>(null)` — set on submit when the value is not a positive integer.
- `readonly saveButtonLabel = computed(() => { if (this.justSaved()) return 'Saved'; if (this.saving()) return 'Saving…'; return 'Save'; });`
- `onInput(event: Event)` — reads `(event.target as HTMLInputElement).value` and writes to `inputValueSignal`. Also clears `validationError` if it was set (so the inline message disappears as soon as the user starts correcting).
- `onSubmit(event: Event)`:
  1. `event.preventDefault()`.
  2. Read `raw = inputValueSignal()`.
  3. Trim. If empty OR not matching `/^[1-9]\d*$/`, set `validationError.set('Enter a positive number')` and return (no network call, no button relabel — epic line 1436).
  4. Clear `validationError` (defensive).
  5. Parse to integer (`Number.parseInt(raw, 10)`) and call `speed.save(value)`.

**CSS (settings-page.css)** — uses the design tokens from `styles.css` per UX-DR1:
```css
.settings-page { display: flex; flex-direction: column; gap: var(--spacing-6); }
.settings-heading { font: var(--text-page-title); color: var(--color-text); margin: 0; }
.settings-label { font: var(--text-body); color: var(--color-text); display: block; margin-bottom: var(--spacing-1); }
.settings-input { font: var(--text-body); padding: var(--spacing-2) var(--spacing-3); border: 1px solid var(--color-border); border-radius: 4px; width: 200px; }
.settings-input:disabled { opacity: 0.5; }
.settings-helper { font: var(--text-small); color: var(--color-text-muted); margin: var(--spacing-1) 0 0; }
.settings-save { font: var(--text-body); padding: var(--spacing-2) var(--spacing-4); background: var(--color-accent); color: white; border: none; border-radius: 4px; cursor: pointer; margin-top: var(--spacing-4); }
.settings-save:hover:not(:disabled) { background: var(--color-accent-hover); }
.settings-save:disabled { opacity: 0.5; cursor: not-allowed; }
```

[Source: epics.md#Story 3.5 lines 1377-1451; UX-DR1 (line 103); UX-DR9 (line 111); UX-DR14 (line 121); UX-DR15 (line 122); UX-DR16 (line 123).]

**AC18 — Render states pinned by AC.** The component renders the following states distinctly, each pinned by tests in AC22:

| State | Trigger | Visual |
|---|---|---|
| Loading | `loading() === true` | input disabled, button disabled, button label `"Save"` (per UX-DR11: input+button disabled IS the cue; helper text remains visible; no spinner) |
| Loaded with value `n` | `pagesPerHour() === n && loadError() === null && !loading()` | input populated with `n`; helper `"e.g., 30"` visible; no error message |
| Unset (412) | `pagesPerHour() === null && loadError() === null && !loading()` | input empty; helper `"e.g., 30"` is the primary cue; NO `ErrorMessage` (per UX-DR9 line 111 — 412 is not an error from the user's POV) |
| Load-error 503 | `loadError() === { kind: 'resource_server_unavailable' }` | inline `ErrorMessage` reads `"Service unavailable — try again shortly"` (per UX-DR12 line 114 + epic line 1432) |
| Validation error | `validationError() !== null` on submit | inline `ErrorMessage` reads `"Enter a positive number"` (per UX-DR9 + epic line 1436); input preserves entered value; button NOT relabeled; NO network call |
| Saving | `saving() === true` | button label `"Saving…"`; button disabled (per UX-DR11) |
| Saved | `justSaved() === true` (~1s pulse) | button label `"Saved"`; input populated with the saved value (per epic line 1441) |
| Save-error 503 | `saveError() === { kind: 'resource_server_unavailable' }` | `ErrorMessage` `"Service unavailable — try again shortly"`; button restored to `"Save"`; input preserves entered value (per epic line 1444-1446) |
| Save-error 422 | `saveError() === { kind: 'invalid_input', ... }` | `ErrorMessage` `"Enter a positive number"`; button restored; input preserves entered value (per epic line 1448-1451; the message is the same as the validation-error string because the only ge=1 violation Pydantic catches on this endpoint is "non-positive integer") |

[Source: epics.md#Story 3.5 lines 1406-1451; UX-DR9 / UX-DR11 / UX-DR12.]

**AC19 — Route table update.** `spa/src/app/app.routes.ts` line for `'settings'` is updated:
```ts
{
  path: 'settings',
  loadComponent: () => import('./settings/settings-page').then((m) => m.SettingsPage),
  canActivate: [authGuard],
},
```
(Replaces the `settings-page-placeholder` lazy import.) The placeholder file `spa/src/app/settings/settings-page-placeholder.ts` is DELETED. The `/books` route is unchanged (Epic 2 will replace its placeholder separately). [Source: epics.md#Story 3.5 line 1381; `spa/src/app/app.routes.ts`.]

**AC20 — TopChrome contextual link unchanged but re-verified.** Story 1.10's `TopChrome` already computes the contextual route link as `"Books"` when on `/settings` (verified at `spa/src/app/shared/chrome/top-chrome.ts` lines 38-49). This story does NOT modify `TopChrome`. The existing `top-chrome.spec.ts` (Story 1.10) tests this; **augment the spec** with one additional assertion: navigate to `/settings`, assert the contextual link reads `"Books"` (epic line 1465 — "the `TopChrome` test from Story 1.10 is re-verified (or extended) to assert the contextual route link reads `"Books"` when the active route is `/settings`"). If the Story 1.10 spec already covers this exact case, capture that fact in the dev log and leave the spec unchanged; otherwise add the test. [Source: epics.md#Story 3.5 line 1465.]

### Tests — SPA

**AC21 — `reading-speed-service.spec.ts` covers each branch.** New file `spa/src/app/settings/reading-speed-service.spec.ts`. Uses Angular `TestBed` with `provideHttpClient(withFetch())` + `provideHttpClientTesting()` + `HttpTestingController` (mirrors Story 1.9's `auth-service.spec.ts` pattern). Tests required:

| # | Scenario | Setup | Asserted |
|---|---|---|---|
| 1 | `load()` happy 200 with value | controller responds 200 `{ pages_per_hour: 30 }` | `pagesPerHour() === 30`; `loadError() === null`; `loading() === false` after settle |
| 2 | `load()` 412 unset | controller responds 412 `{ errorCode: 'reading_speed_unset', ... }` | `pagesPerHour() === null`; `loadError() === null`; `loading() === false` |
| 3 | `load()` 503 RS unavailable | controller responds 503 `resource_server_unavailable` | `loadError() === { kind: 'resource_server_unavailable' }`; `pagesPerHour() === null`; `loading() === false` |
| 4 | `load()` initial state during pending | call `load()` but do not flush | `loading() === true`; `loadError() === null` |
| 5 | `save()` happy 200 | controller responds 200 `{ pages_per_hour: 45 }`; observe `justSaved` over time | `pagesPerHour() === 45`; `justSaved()` is `true` immediately after save and `false` after ~1s (use `tick(1000)` with `fakeAsync` OR `vi.advanceTimersByTime(1000)` with vitest's fake timers) |
| 6 | `save()` 422 | controller 422 `invalid_input` | `saveError() === { kind: 'invalid_input', detail: ... }`; `saving() === false`; `pagesPerHour()` unchanged from pre-call value |
| 7 | `save()` 503 | controller 503 | `saveError() === { kind: 'resource_server_unavailable' }`; `saving() === false` |
| 8 | `save()` 401 — silent (global handler owns nav) | controller 401 `session_expired` | the service's catch block sets `saving.set(false)` and does NOT set `saveError` to a meaningful AppError (it falls through to `{ kind: 'unknown' }` from `ErrorService` — but the SettingsView is being torn down anyway; assert `saving() === false`) |
| 9 | `justSaved` toggle window | save returns 200; observe signal across the ~1s window | true immediately, false after `setTimeout(_, 1000)` fires |
| 10 | `save()` body shape | inspect captured request | request body equals `{ "pages_per_hour": 30 }` (or whatever value was passed) — no other fields |
| 11 | `save()` PUT method | inspect captured request | `request.method === 'PUT'` |
| 12 | `load()` GET method | inspect captured request | `request.method === 'GET'` |
| 13 | Both call `/v1/reading-speed` | inspect captured request URLs | `request.url === '/v1/reading-speed'` (relative — the SPA's proxy / production same-origin handles routing) |

[Source: epics.md#Story 3.5 lines 1461-1463.]

**AC22 — `settings-page.spec.ts` covers all states.** New file `spa/src/app/settings/settings-page.spec.ts`. Mirrors Story 1.10's `top-chrome.spec.ts` and `login-view.spec.ts` patterns. Provide a mock `ReadingSpeedService` via `provideHttpClientTesting()` OR a custom `provide({ provide: ReadingSpeedService, useValue: mockService })` pattern (the latter is simpler — mock the service surface directly). Tests required:

| # | Scenario | Setup | Asserted |
|---|---|---|---|
| 1 | Loading state | mock service `loading() === true`, `pagesPerHour() === null` | input is disabled; button is disabled; button label is `"Save"` |
| 2 | Loaded with value | `pagesPerHour() === 30`, `loadError() === null` | input value `30`; helper text visible; NO ErrorMessage |
| 3 | Unset (412) state | `pagesPerHour() === null`, `loadError() === null`, `loading() === false` | input empty; helper text visible; NO ErrorMessage (the cue is the helper) |
| 4 | Load-error 503 | `loadError() === { kind: 'resource_server_unavailable' }` | inline ErrorMessage with text `"Service unavailable — try again shortly"` |
| 5 | Validation error on submit | enter `0` (or empty, or `-5`, or `abc`); click Save | inline ErrorMessage with `"Enter a positive number"`; service `save()` NOT called; input preserves entered value |
| 6 | Save success → `"Saved"` pulse | submit valid value; mock service flips `saving` then `justSaved` true/false | button label progresses `"Save"` → `"Saving…"` → `"Saved"` → `"Save"`; input populated with the saved value |
| 7 | Save error 503 | mock sets `saveError` to `{ kind: 'resource_server_unavailable' }` after save | ErrorMessage `"Service unavailable — try again shortly"`; button label restored to `"Save"`; input value preserved |
| 8 | Save error 422 | mock sets `saveError` to `{ kind: 'invalid_input', ... }` after save | ErrorMessage `"Enter a positive number"`; button restored; input preserved |
| 9 | Component invokes `load()` on init | spy `service.load`; mount component | `service.load` called exactly once |
| 10 | Save button click invokes `save(value)` | enter `30`; click | `service.save` called with `30` (Number, not string) |
| 11 | Submit form via Enter key | enter `30`; press Enter inside input | same as click — `service.save(30)` called |
| 12 | Validation: empty input | clear input; click Save | ErrorMessage `"Enter a positive number"`; service NOT called |
| 13 | Validation: non-numeric | type `abc`; click Save | ErrorMessage `"Enter a positive number"`; service NOT called |
| 14 | Validation: zero | type `0`; click Save | ErrorMessage; service NOT called |
| 15 | Validation: negative | type `-5`; click Save | ErrorMessage; service NOT called |
| 16 | Validation runs on submit only (not blur) | type `0`; tab out (blur) | NO ErrorMessage (per UX-DR15); only after click does it render |

[Source: epics.md#Story 3.5 lines 1464-1466; UX-DR15 line 122.]

**AC23 — Coverage target.** Vitest coverage of `spa/src/app/settings/` is **≥70%** per epic line 1466. The `@vitest/coverage-v8` tooling lands in Story 1.9; the existing `spa/vitest.config.ts` (or whatever Story 1.9 chose for its coverage harness — verify) covers `src/app/settings/**`. Add `src/app/shared/errors/**` to the same coverage scope if it's not already wildcarded. Aim for 100% on `ReadingSpeedService` and `ErrorService` (both pure logic); `SettingsPage` template branches naturally land in the 80-90% range with the test matrix above. [Source: epics.md#Story 3.5 line 1466; `spa/vitest.config.ts` (Story 1.9 artifact).]

**AC24 — Existing SPA gates still green.** From `spa/`:
- `npm run lint` → exits 0 (no new ESLint violations).
- `npm run build` → exits 0; `dist/spa/browser/index.html` produced; the new `SettingsPage` lazy chunk is emitted alongside `LoginView` / `BooksPagePlaceholder`.
- `npm test -- --no-watch` → exits 0; all Story 1.8 + 1.9 + 1.10 + new SettingsPage + ReadingSpeedService tests pass.
- `npm run test:coverage` → exits 0; per-folder coverage ≥70% for `src/app/settings/` and `src/app/shared/errors/`.

[Source: `spa/package.json` scripts; `spa/eslint.config.js`; Story 1.10 AC16.]

### Tests — BFF coverage gate

**AC25 — BFF gates remain green.** From `services/bff/`:
- `uv sync --frozen` → exit 0 (no dep changes; httpx is already pinned per `pyproject.toml:13`).
- `uv run ruff check` → 0 findings.
- `uv run ruff format --check` → 0 reformats needed.
- `uv run ty check` → 0 errors.
- `uv run pytest --cov` → all prior 281 + new ~40 tests pass; total coverage ≥ 90% (project gate at `[tool.coverage.report] fail_under = 90`).
- No Alembic changes (the `sessions` schema is unchanged; this story uses the existing `access_token` / `refresh_token` columns from Story 1.4 / 1.5).

[Source: `services/bff/pyproject.toml`; `services/bff/CLAUDE.md`.]

**AC26 — Compose default profile validates with new RS_BASE_URL.** From repo root:
- `docker compose --profile default config` → exit 0; the `bff` service environment includes `RS_BASE_URL=http://resource-server:8000` (or the env_file value). The `resource-server` service is reachable from the `bff` service over the compose network at the configured URL.
- A note in the dev log captures whether `compose/app.yml` needs a new `RS_BASE_URL` env entry on the `bff` service block (it does — `RS_BASE_URL` is a new env var the BFF now requires-fail-fast). Add it as a single line in the BFF's `environment:` block (or rely solely on `env_file:` if the BFF's per-service `.env` is the source — both work; choose the form the existing Epic 1 stories use).

**AC27 — Pre-existing repo state is preserved.** Files outside the new code paths are bit-for-bit identical. Specifically: `CLAUDE.md`, root `README.md`, root `.env.example`, `docker-compose.yml`, `compose/app.e2e.yml`, `compose/infra.yml`, `Justfile`, `keycloak/**`, `services/resource-server/**` (this is a BFF + SPA story; RS is consumed unchanged), `e2e/**`, and all SPA files outside `src/app/settings/`, `src/app/shared/errors/`, `src/app/app.routes.ts` (+ optionally `src/app/shared/chrome/top-chrome.spec.ts` per AC20). The **only modifications**:
- **NEW** `services/bff/src/bff/services/resource_server_client.py`
- **NEW** `services/bff/src/bff/api/reading_speed.py`
- **MODIFIED** `services/bff/src/bff/api/v1/__init__.py` (one-line include_router call)
- **MODIFIED** `services/bff/src/bff/core/config.py` (add `rs_base_url` field + `_validate_rs_base_url` model validator)
- **MODIFIED** `services/bff/src/bff/core/errors.py` (add `RESOURCE_SERVER_UNAVAILABLE` enum member)
- **MODIFIED** `services/bff/.env.example` (add `RS_BASE_URL` line)
- **MODIFIED** `compose/app.yml` (add `RS_BASE_URL` to BFF env block — single line, single service)
- **NEW** `services/bff/tests/api/test_reading_speed_proxy.py`
- **NEW** `services/bff/tests/services/test_resource_server_client.py`
- **NEW** `spa/src/app/shared/errors/app-error.types.ts`
- **NEW** `spa/src/app/shared/errors/error-service.ts`
- **NEW** `spa/src/app/shared/errors/error-service.spec.ts` (covers `parse` branches per AC14)
- **NEW** `spa/src/app/settings/settings-page.ts` + `.html` + `.css` + `.spec.ts`
- **NEW** `spa/src/app/settings/reading-speed-service.ts` + `.spec.ts`
- **NEW** `spa/src/app/settings/reading-speed.types.ts`
- **MODIFIED** `spa/src/app/app.routes.ts` (replace `settings-page-placeholder` import with `settings-page`)
- **DELETED** `spa/src/app/settings/settings-page-placeholder.ts`
- **MODIFIED (optional)** `spa/src/app/shared/chrome/top-chrome.spec.ts` (one extra test if missing — AC20)
- **MODIFIED** `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flip)
- **MODIFIED (potentially)** `_bmad-output/implementation-artifacts/deferred-work.md` (new defers D80+)

## Tasks / Subtasks

- [ ] **Task 1 — BFF: add `RESOURCE_SERVER_UNAVAILABLE` ErrorCode** (AC: #6)
  - [ ] Edit `services/bff/src/bff/core/errors.py`. Add to the `ErrorCode` enum after `CSRF_INVALID`:
    ```python
    RESOURCE_SERVER_UNAVAILABLE = (
        "resource_server_unavailable",
        "The reading-speed service is temporarily unavailable",
        503,
    )
    ```
  - [ ] Update the leading project-specific-codes comment to mention Story 3.5's addition (mirrors the discipline established by Stories 1.5-1.7 and 3.3 on the RS).
  - [ ] Run `uv run pytest tests/core/` → existing error-handler tests still pass (the addition is a new enum member, no behavior change to existing handlers).

- [ ] **Task 2 — BFF: add `rs_base_url` config field** (AC: #2)
  - [ ] Edit `services/bff/src/bff/core/config.py`:
    - Add field after `test_reset_token`: `rs_base_url: str = "http://resource-server:8000"`.
    - Add `@model_validator(mode="after")` named `_validate_rs_base_url` mirroring `_validate_oidc_authorize_url_browser`:
      ```python
      @model_validator(mode="after")
      def _validate_rs_base_url(self) -> AppSettings:
          val = self.rs_base_url.strip()
          if not val:
              msg = (
                  "RS_BASE_URL is required and must be non-empty "
                  "(the BFF→Resource Server base URL — typically "
                  "http://resource-server:8000 in compose, http://localhost:8001 in dev)"
              )
              raise ValueError(msg)
          if not val.startswith(("http://", "https://")):
              msg = (
                  "RS_BASE_URL must start with 'http://' or 'https://' "
                  f"(got: '{val[:40]}...')"
              )
              raise ValueError(msg)
          return self
      ```
  - [ ] Edit `services/bff/.env.example` — add a new section before the `AR29: Test-reset endpoint` block:
    ```
    # --- AR29: BFF → Resource Server ---------------------------------------------
    # Compose-internal hostname for the RS (matches the service name in compose/app.yml).
    # In dev (host runs), override to the local RS port (e.g., http://localhost:8001).
    RS_BASE_URL=http://resource-server:8000
    ```
  - [ ] Edit `compose/app.yml` — locate the `bff` service block, add `RS_BASE_URL=http://resource-server:8000` to its `environment:` list (verify whether the BFF uses `environment:` inline or only `env_file:` — match the existing pattern). If the BFF uses ONLY `env_file:`, the `.env.example` change is sufficient and the value carries via `services/bff/.env` at compose time.
  - [ ] Re-run `uv sync --frozen` (idempotent) and verify `AppSettings()` constructs cleanly with the default value.

- [ ] **Task 3 — BFF: author `ResourceServerClient` class** (AC: #1, #4, #6, #7)
  - [ ] Create `services/bff/src/bff/services/resource_server_client.py`. Module docstring describes: purpose (BFF → RS HTTP client), refresh-and-replay cycle (NFR3 / A6), timeouts (AR19 — 5s connect / 10s read; no retries on 5xx), identity propagation (NFR6 — no `sub` injection), and source references.
  - [ ] Imports:
    ```python
    from __future__ import annotations

    import logging
    from datetime import UTC, datetime, timedelta
    from typing import Any

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from bff.core.config import AppSettings, settings
    from bff.core.errors import AppException, ErrorCode
    from bff.models.entities.session import Session
    from bff.services.session_service import SessionService
    ```
  - [ ] Module-level constants:
    ```python
    logger = logging.getLogger(__name__)

    _RS_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)
    _READING_SPEED_PATH = "/v1/reading-speed"
    _TOKEN_PATH_SUFFIX = "/protocol/openid-connect/token"
    ```
  - [ ] Custom internal exception:
    ```python
    class _RsUnavailable(Exception):
        """Internal classifier for 5xx / transport failures from the RS."""

        def __init__(self, cause: str, http_status: int | None = None) -> None:
            self.cause = cause
            self.http_status = http_status
            super().__init__(cause)


    class _RefreshFailed(Exception):
        """Internal classifier for Keycloak `/token` refresh-grant failures."""

        def __init__(self, cause: str) -> None:
            self.cause = cause
            super().__init__(cause)
    ```
  - [ ] Class body skeleton:
    ```python
    class ResourceServerClient:
        def __init__(
            self,
            settings_obj: AppSettings,
            session_service: SessionService | None = None,
        ) -> None:
            self._settings = settings_obj
            self._session_service = session_service or SessionService()

        async def get_reading_speed(
            self, db: AsyncSession, session_row: Session
        ) -> tuple[int, dict[str, Any] | None]:
            return await self._call_with_refresh(db, session_row, method="GET", body=None)

        async def put_reading_speed(
            self, db: AsyncSession, session_row: Session, payload: dict[str, Any]
        ) -> tuple[int, dict[str, Any] | None]:
            return await self._call_with_refresh(db, session_row, method="PUT", body=payload)

        async def _call_with_refresh(
            self,
            db: AsyncSession,
            session_row: Session,
            *,
            method: str,
            body: dict[str, Any] | None,
        ) -> tuple[int, dict[str, Any] | None]:
            # First attempt with current access_token.
            access_token = session_row.access_token
            status, parsed = await self._do_rs_call(method, access_token, body)
            if status != 401:
                return status, parsed
            # RS-401 → attempt refresh-and-replay.
            try:
                new_tokens = await self._refresh_access_token(session_row)
            except _RefreshFailed as exc:
                # Refresh itself failed — clear session + cookies, return 401.
                await self._session_service.delete_session(db, session_id=session_row.id)
                logger.warning(
                    "refresh_failed cause=%s sub=%s session=%s...",
                    exc.cause,
                    session_row.sub,
                    session_row.id[:8],
                )
                # Mark for cookie-clearing in the caller via a sentinel exception.
                raise _SessionTerminated(clear_cookies=True) from exc
            # Persist the rotated tokens.
            await self._persist_refreshed_tokens(db, session_row, new_tokens)
            # Retry exactly once with the new access_token.
            new_access_token = new_tokens["access_token"]
            retry_status, retry_parsed = await self._do_rs_call(method, new_access_token, body)
            if retry_status == 401:
                # Retry still 401 — refresh worked but RS still rejected.
                # Leave session in place per AC4 case 5; return 401 to SPA.
                logger.warning(
                    "rs_401_after_refresh sub=%s session=%s...",
                    session_row.sub,
                    session_row.id[:8],
                )
                raise _SessionTerminated(clear_cookies=False)
            return retry_status, retry_parsed
    ```
  - [ ] `_do_rs_call`:
    ```python
    async def _do_rs_call(
        self, method: str, access_token: str, body: dict[str, Any] | None
    ) -> tuple[int, dict[str, Any] | None]:
        url = self._settings.rs_base_url.rstrip("/") + _READING_SPEED_PATH
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=_RS_TIMEOUT) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers)
                elif method == "PUT":
                    response = await client.put(url, headers=headers, json=body)
                else:  # pragma: no cover -- only GET/PUT shapes are wired
                    raise ValueError(f"unsupported method: {method}")
        except httpx.ConnectError as exc:
            raise _RsUnavailable("connect_error") from exc
        except httpx.ConnectTimeout as exc:
            raise _RsUnavailable("connect_timeout") from exc
        except httpx.ReadTimeout as exc:
            raise _RsUnavailable("read_timeout") from exc
        except httpx.WriteTimeout as exc:
            raise _RsUnavailable("write_timeout") from exc
        except httpx.PoolTimeout as exc:
            raise _RsUnavailable("pool_timeout") from exc
        except httpx.NetworkError as exc:
            raise _RsUnavailable("network_error") from exc
        except httpx.HTTPError as exc:
            raise _RsUnavailable("unknown_transport") from exc
        if response.status_code >= 500:
            raise _RsUnavailable("rs_5xx_response", http_status=response.status_code)
        # Parse body lazily; some statuses return empty bodies.
        try:
            parsed = response.json() if response.content else None
        except ValueError:
            parsed = None
        return response.status_code, parsed
    ```
  - [ ] `_refresh_access_token`:
    ```python
    async def _refresh_access_token(self, session_row: Session) -> dict[str, Any]:
        token_url = self._settings.oidc_issuer_url.rstrip("/") + _TOKEN_PATH_SUFFIX
        try:
            async with httpx.AsyncClient(timeout=_RS_TIMEOUT) as client:
                response = await client.post(
                    token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": session_row.refresh_token,
                        "client_id": self._settings.oidc_client_id,
                        "client_secret": self._settings.bff_client_secret,
                    },
                )
        except httpx.HTTPError as exc:
            raise _RefreshFailed(f"transport_error:{type(exc).__name__}") from exc
        if 400 <= response.status_code < 500:
            raise _RefreshFailed(f"keycloak_4xx:{response.status_code}")
        if response.status_code >= 500:
            raise _RefreshFailed(f"keycloak_5xx:{response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise _RefreshFailed("malformed_response") from exc
        if not isinstance(payload, dict):
            raise _RefreshFailed("malformed_response")
        if "access_token" not in payload or "refresh_token" not in payload:
            raise _RefreshFailed("malformed_response")
        return payload
    ```
  - [ ] `_persist_refreshed_tokens`:
    ```python
    async def _persist_refreshed_tokens(
        self, db: AsyncSession, session_row: Session, tokens: dict[str, Any]
    ) -> None:
        session_row.access_token = tokens["access_token"]
        session_row.refresh_token = tokens["refresh_token"]
        expires_in = tokens.get("expires_in")
        if isinstance(expires_in, (int, float)):
            session_row.expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
        db.add(session_row)
        await db.commit()
        await db.refresh(session_row)
        logger.info(
            "access_token_refreshed sub=%s session=%s...",
            session_row.sub,
            session_row.id[:8],
        )
    ```
  - [ ] `_SessionTerminated` sentinel exception (raised by `_call_with_refresh` to signal the caller to emit the cookie-clearing 401):
    ```python
    class _SessionTerminated(Exception):
        def __init__(self, *, clear_cookies: bool) -> None:
            self.clear_cookies = clear_cookies
            super().__init__("session_terminated")
    ```
    Place this AT MODULE SCOPE so the `bff/api/reading_speed.py` proxy router can `except resource_server_client._SessionTerminated as exc:` (export it through `__all__` to make the import shape explicit; or use a public-named class like `RsSessionTerminated` to avoid the underscore). **Recommended:** rename to `RsSessionTerminated` (public) so the proxy router's try/except is readable; the underscore convention is for module-internal classes only.
  - [ ] Module-level singleton: `resource_server_client = ResourceServerClient(settings)` at the bottom of the file. Also `__all__ = ["RsSessionTerminated", "ResourceServerClient", "resource_server_client"]`.

- [ ] **Task 4 — BFF: author `/v1/reading-speed` proxy router** (AC: #3, #5, #6, #7, #8, #9, #10)
  - [ ] Create `services/bff/src/bff/api/reading_speed.py`. Module docstring describes: purpose (thin proxy to RS), session check (mirrors `api/me.py`), forwarding rules (verbatim for 2xx/4xx; mapped 503 for 5xx), refresh-and-replay (delegated to `ResourceServerClient`), and source references.
  - [ ] Imports:
    ```python
    from __future__ import annotations

    import logging
    from datetime import UTC, datetime
    from typing import Annotated, Any

    from fastapi import APIRouter, Depends, Request
    from fastapi.responses import JSONResponse
    from sqlalchemy.ext.asyncio import AsyncSession

    from bff.core.config import AppSettings, settings
    from bff.core.database import get_session
    from bff.core.errors import AppException, ErrorCode
    from bff.services.resource_server_client import (
        RsSessionTerminated,
        resource_server_client,
    )
    from bff.services.session_service import SessionService
    ```
  - [ ] Module-level helpers (mirror `api/me.py:29-69`):
    ```python
    logger = logging.getLogger(__name__)
    router = APIRouter(tags=["reading-speed"])
    _session_service = SessionService()


    def _settings_dep() -> AppSettings:
        return settings


    def _as_utc_aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


    async def _require_session(
        request: Request, db: AsyncSession, cfg: AppSettings
    ):
        session_id = request.cookies.get(cfg.bff_session_cookie_name)
        if not session_id:
            raise AppException(ErrorCode.SESSION_EXPIRED)
        row = await _session_service.get_session(db, session_id=session_id)
        if row is None:
            raise AppException(ErrorCode.SESSION_EXPIRED)
        if _as_utc_aware(row.expires_at) < datetime.now(UTC):
            await _session_service.delete_expired_session(db, session_id=session_id)
            raise AppException(ErrorCode.SESSION_EXPIRED)
        return row


    def _session_terminated_response(cfg: AppSettings, *, clear_cookies: bool) -> JSONResponse:
        response = JSONResponse(
            status_code=401,
            content={
                "errorCode": "session_expired",
                "message": "Authentication required",
                "detail": None,
            },
        )
        if clear_cookies:
            response.delete_cookie(cfg.bff_session_cookie_name, path="/")
            response.delete_cookie(cfg.bff_csrf_cookie_name, path="/")
        return response


    def _resource_server_unavailable_response() -> JSONResponse:
        return JSONResponse(
            status_code=ErrorCode.RESOURCE_SERVER_UNAVAILABLE.http_status,
            content={
                "errorCode": ErrorCode.RESOURCE_SERVER_UNAVAILABLE.code,
                "message": ErrorCode.RESOURCE_SERVER_UNAVAILABLE.message,
                "detail": None,
            },
        )
    ```
  - [ ] GET handler:
    ```python
    @router.get("/reading-speed")
    async def get_reading_speed(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_session)],
        cfg: Annotated[AppSettings, Depends(_settings_dep)],
    ) -> JSONResponse:
        session_row = await _require_session(request, db, cfg)
        try:
            status, body = await resource_server_client.get_reading_speed(db, session_row)
        except RsSessionTerminated as exc:
            return _session_terminated_response(cfg, clear_cookies=exc.clear_cookies)
        except Exception as exc:
            # _RsUnavailable internal classifier; log + 503.
            cause = getattr(exc, "cause", "unknown")
            http_status = getattr(exc, "http_status", None)
            logger.warning(
                "resource_server_unavailable cause=%s http_status=%s",
                cause,
                http_status,
            )
            return _resource_server_unavailable_response()
        return JSONResponse(status_code=status, content=body)
    ```
    **Note (the `except Exception` catch):** It's broad but ONLY catches `_RsUnavailable` and `RsSessionTerminated` in practice (the only paths `ResourceServerClient` raises). Type-narrow with `isinstance(exc, _RsUnavailable)` to satisfy `ty`. Alternative: expose `_RsUnavailable` as `RsUnavailable` (public) and catch by name. **Recommended:** rename to `RsUnavailable` and catch by name — same cleanup as `_SessionTerminated → RsSessionTerminated`.
  - [ ] PUT handler — same shape with `payload: dict[str, Any]` body parameter and `put_reading_speed` call.
  - [ ] Edit `services/bff/src/bff/api/v1/__init__.py`. Add include_router:
    ```python
    from fastapi import APIRouter

    from bff.api.reading_speed import router as reading_speed_router

    router = APIRouter(prefix="/v1")
    router.include_router(reading_speed_router)
    ```
  - [ ] Verify NO edits to `main.py` are needed.

- [ ] **Task 5 — BFF: author proxy tests `tests/api/test_reading_speed_proxy.py`** (AC: #11)
  - [ ] Create `services/bff/tests/api/test_reading_speed_proxy.py`. Module docstring + ~20 tests per the AC11 matrix.
  - [ ] Imports: respx, httpx, pytest, the conftest fixtures (`client`, `client_with_csrf`, `session`). Use `respx.mock(assert_all_called=False, assert_all_mocked=False)` as a context manager OR `respx_mock` fixture.
  - [ ] Helper to seed a session row: `async def _seed_session(session, sub="user-a", access_token="initial-at", refresh_token="initial-rt", expires_at=None) -> Session` — uses `SessionService.create_session` OR direct `session.add(Session(...))`. Set the session cookie on the test client by adding it to `client.cookies` (the conftest `client_with_csrf` fixture handles the CSRF cookie + header; you can layer the session cookie on top).
  - [ ] For each scenario in AC11 #1-20, use respx to mock the RS endpoint at the URL the BFF will construct (`settings.rs_base_url + "/v1/reading-speed"` — monkeypatch `settings.rs_base_url` to the synthetic IdP's `http://rs.test` namespace OR use the default `http://resource-server:8000`).
  - [ ] **Important:** the `respx_mock` should be scoped per-test (use the `respx` pytest plugin's `respx_mock` fixture or wrap in `with respx.mock(...) as mock:`). Capture `mock["rs"].call_count` to verify "called exactly once" assertions (AC11 #19).
  - [ ] For 503 scenarios, also assert the WARN log via `caplog`: `caplog.set_level(logging.WARNING, logger="bff.services.resource_server_client")` then `assert "resource_server_unavailable" in caplog.text and "cause=connect_error" in caplog.text` etc.
  - [ ] Add a sanity test that the OpenAPI schema includes `/v1/reading-speed` (GET + PUT) — `response = await client.get("/openapi.json"); assert "/v1/reading-speed" in response.json()["paths"]`.

- [ ] **Task 6 — BFF: author refresh-and-replay tests `tests/services/test_resource_server_client.py`** (AC: #12)
  - [ ] Create `services/bff/tests/services/test_resource_server_client.py`. Module docstring describes the refresh-and-replay contract.
  - [ ] Use the BFF synthetic-IdP harness (`build_synthetic_idp(monkeypatch)` from `tests/auth/synthetic_idp.py`). The IdP's `_token_handler` already handles the `refresh_token` grant — no changes needed there.
  - [ ] For each scenario in AC12 #1-20:
    - Seed a `Session` row with `access_token="initial-at"`, `refresh_token="initial-rt"`.
    - Use respx to layer mocks on the RS endpoint: first call returns 401 (or whatever the scenario specifies), second call returns the retry outcome.
    - Use the synthetic IdP's `respx` mock for the `/token` endpoint to control refresh outcomes.
    - For failure scenarios, monkeypatch `httpx.AsyncClient.post` to raise specific exceptions.
    - Direct instantiation: `client = ResourceServerClient(settings_obj, session_service=SessionService())` — pass the test's `session_service` directly so `delete_session` calls land on the same DB session.
    - Assert: post-call DB state (`session.refresh_token`, `session.access_token`, `session.expires_at`), captured request shapes (Authorization headers, body verbatim, no `sub` in URL), respx call counts, caplog entries.
  - [ ] For the cookie-clearing assertion (AC12 #19), the test calls `ResourceServerClient.get_reading_speed` directly (which raises `RsSessionTerminated`), then drives the proxy router's `_session_terminated_response` helper directly OR uses the `client_with_csrf` fixture to exercise the full proxy path and inspect `response.headers.get_list("set-cookie")`. The full-proxy approach is preferred for catching response-shape regressions.
  - [ ] Aim for ≥90% coverage of `services/resource_server_client.py`.

- [ ] **Task 7 — SPA: author `AppError` discriminated union + `ErrorService`** (AC: #14)
  - [ ] Create `spa/src/app/shared/errors/` directory.
  - [ ] Create `spa/src/app/shared/errors/app-error.types.ts` with the discriminated union per AC14.
  - [ ] Create `spa/src/app/shared/errors/error-service.ts`:
    ```ts
    import { HttpErrorResponse } from '@angular/common/http';
    import { Injectable } from '@angular/core';

    import { AppError } from './app-error.types';

    interface ErrorEnvelope {
      errorCode?: string;
      message?: string;
      detail?: unknown;
    }

    @Injectable({ providedIn: 'root' })
    export class ErrorService {
      parse(err: unknown): AppError {
        if (!(err instanceof HttpErrorResponse)) {
          return { kind: 'unknown' };
        }
        const body = (err.error ?? {}) as ErrorEnvelope;
        const code = body.errorCode;
        if (err.status === 503 && code === 'resource_server_unavailable') {
          return { kind: 'resource_server_unavailable' };
        }
        if (err.status === 412 && code === 'reading_speed_unset') {
          return { kind: 'reading_speed_unset' };
        }
        if (err.status === 422 && code === 'invalid_input') {
          return { kind: 'invalid_input', detail: body.detail };
        }
        if (err.status === 403 && code === 'forbidden_scope') {
          return { kind: 'forbidden_scope' };
        }
        return {
          kind: 'unknown',
          status: err.status,
          errorCode: code,
          message: body.message,
        };
      }
    }
    ```
  - [ ] Create `spa/src/app/shared/errors/error-service.spec.ts` covering each branch of `parse`: 503/412/422/403 happy paths, 503/412 with wrong errorCode (falls through to unknown), non-HttpErrorResponse input, missing body fields.

- [ ] **Task 8 — SPA: author `ReadingSpeedService`** (AC: #15, #16)
  - [ ] Create `spa/src/app/settings/reading-speed.types.ts` with the `ReadingSpeedOut` interface.
  - [ ] Create `spa/src/app/settings/reading-speed-service.ts`:
    ```ts
    import { HttpClient, HttpErrorResponse } from '@angular/common/http';
    import { Injectable, Signal, inject, signal } from '@angular/core';
    import { firstValueFrom } from 'rxjs';

    import { AppError } from '../shared/errors/app-error.types';
    import { ErrorService } from '../shared/errors/error-service';
    import { ReadingSpeedOut } from './reading-speed.types';

    const READING_SPEED_URL = '/v1/reading-speed';
    const JUST_SAVED_PULSE_MS = 1000;

    @Injectable({ providedIn: 'root' })
    export class ReadingSpeedService {
      private readonly http = inject(HttpClient);
      private readonly errorService = inject(ErrorService);

      private readonly _pagesPerHour = signal<number | null>(null);
      private readonly _loading = signal<boolean>(false);
      private readonly _loadError = signal<AppError | null>(null);
      private readonly _saving = signal<boolean>(false);
      private readonly _saveError = signal<AppError | null>(null);
      private readonly _justSaved = signal<boolean>(false);

      readonly pagesPerHour: Signal<number | null> = this._pagesPerHour.asReadonly();
      readonly loading: Signal<boolean> = this._loading.asReadonly();
      readonly loadError: Signal<AppError | null> = this._loadError.asReadonly();
      readonly saving: Signal<boolean> = this._saving.asReadonly();
      readonly saveError: Signal<AppError | null> = this._saveError.asReadonly();
      readonly justSaved: Signal<boolean> = this._justSaved.asReadonly();

      async load(): Promise<void> {
        this._loading.set(true);
        this._loadError.set(null);
        try {
          const response = await firstValueFrom(
            this.http.get<ReadingSpeedOut>(READING_SPEED_URL),
          );
          this._pagesPerHour.set(response.pages_per_hour);
        } catch (err) {
          if (err instanceof HttpErrorResponse && err.status === 412) {
            // Unset state — not an error.
            this._pagesPerHour.set(null);
            this._loadError.set(null);
            return;
          }
          if (err instanceof HttpErrorResponse && err.status === 401) {
            // Global handler navigates to /login; no SPA state needed.
            return;
          }
          const appError = this.errorService.parse(err);
          this._loadError.set(appError);
          this._pagesPerHour.set(null);
        } finally {
          this._loading.set(false);
        }
      }

      async save(value: number): Promise<void> {
        this._saving.set(true);
        this._saveError.set(null);
        try {
          const response = await firstValueFrom(
            this.http.put<ReadingSpeedOut>(READING_SPEED_URL, { pages_per_hour: value }),
          );
          this._pagesPerHour.set(response.pages_per_hour);
          this._justSaved.set(true);
          setTimeout(() => this._justSaved.set(false), JUST_SAVED_PULSE_MS);
        } catch (err) {
          if (err instanceof HttpErrorResponse && err.status === 401) {
            return;
          }
          const appError = this.errorService.parse(err);
          this._saveError.set(appError);
        } finally {
          this._saving.set(false);
        }
      }
    }
    ```
  - [ ] Create `spa/src/app/settings/reading-speed-service.spec.ts` covering AC21 (13 scenarios).
    - Use `provideHttpClient(withFetch())` + `provideHttpClientTesting()` + `inject(HttpTestingController)`.
    - For the `justSaved` pulse, use vitest fake timers: `vi.useFakeTimers()` in `beforeEach`, `vi.advanceTimersByTime(1000)` after save resolves.

- [ ] **Task 9 — SPA: author `SettingsPage` component** (AC: #17, #18)
  - [ ] Create `spa/src/app/settings/settings-page.{ts,html,css,spec.ts}` per AC17.
  - [ ] In `settings-page.ts`:
    ```ts
    import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal } from '@angular/core';
    import { ErrorMessage } from '../shared/ui/error-message';
    import { ReadingSpeedService } from './reading-speed-service';

    @Component({
      selector: 'app-settings-page',
      standalone: true,
      imports: [ErrorMessage],
      templateUrl: './settings-page.html',
      styleUrl: './settings-page.css',
      changeDetection: ChangeDetectionStrategy.OnPush,
    })
    export class SettingsPage implements OnInit {
      private readonly speedService = inject(ReadingSpeedService);

      readonly loading = this.speedService.loading;
      readonly saving = this.speedService.saving;
      readonly loadError = this.speedService.loadError;
      readonly saveError = this.speedService.saveError;
      readonly justSaved = this.speedService.justSaved;

      private readonly inputValueSignal = signal<string>('');
      readonly inputValue = this.inputValueSignal.asReadonly();

      readonly validationErrorSignal = signal<string | null>(null);
      readonly validationError = this.validationErrorSignal.asReadonly();

      readonly saveButtonLabel = computed(() => {
        if (this.justSaved()) return 'Saved';
        if (this.saving()) return 'Saving…';
        return 'Save';
      });

      constructor() {
        // Sync input value from service when it changes — only if user has not edited yet.
        // Track edited-state to avoid clobbering user input mid-typing.
        effect(() => {
          const current = this.speedService.pagesPerHour();
          if (current !== null && !this._userEdited) {
            this.inputValueSignal.set(String(current));
          } else if (current === null && !this._userEdited) {
            this.inputValueSignal.set('');
          }
        });
      }

      private _userEdited = false;

      async ngOnInit(): Promise<void> {
        await this.speedService.load();
      }

      onInput(event: Event): void {
        const target = event.target as HTMLInputElement;
        this.inputValueSignal.set(target.value);
        this._userEdited = true;
        this.validationErrorSignal.set(null);
      }

      async onSubmit(event: Event): Promise<void> {
        event.preventDefault();
        const raw = this.inputValueSignal().trim();
        if (!/^[1-9]\d*$/.test(raw)) {
          this.validationErrorSignal.set('Enter a positive number');
          return;
        }
        this.validationErrorSignal.set(null);
        const value = Number.parseInt(raw, 10);
        await this.speedService.save(value);
      }
    }
    ```
    **Note re `_userEdited`:** the simple boolean flips true on the first input event and never resets. This is fine because after the initial paint, the user owns the input; if they navigate away and come back, the route reactivates the component fresh (lazy `loadComponent` re-instantiates on activation). If a future story keeps the component alive across navigations, revisit this.
  - [ ] In `settings-page.html`: the template body per AC17.
  - [ ] In `settings-page.css`: the styles per AC17.
  - [ ] In `settings-page.spec.ts`: 16 tests per AC22.

- [ ] **Task 10 — SPA: update route table + delete placeholder** (AC: #19, #20)
  - [ ] Edit `spa/src/app/app.routes.ts`. Replace the `settings` route's `loadComponent` to import `./settings/settings-page` → `m.SettingsPage`.
  - [ ] Delete `spa/src/app/settings/settings-page-placeholder.ts`.
  - [ ] Run `git status` after the deletion to verify it's tracked.
  - [ ] Verify `top-chrome.spec.ts` already covers the `/settings` → `"Books"` contextual link case. If not, add the test per AC20.

- [ ] **Task 11 — Run BFF gates** (AC: #25, #26)
  - [ ] From `services/bff/`:
    - `uv sync --frozen` → exit 0.
    - `uv run ruff check` → 0 findings.
    - `uv run ruff format --check` → 0 reformats.
    - `uv run ty check` → 0 errors. Add `# ty: ignore[...]` ONLY if the type-checker objects to specific lines; keep them rare and documented (e.g., respx mock setups).
    - `uv run pytest --cov` → all prior + ~40 new tests pass; total coverage ≥ 90%. Capture %.
  - [ ] From repo root: `docker compose --profile default config` → exit 0; capture the `bff` service block to confirm `RS_BASE_URL` is wired.

- [ ] **Task 12 — Run SPA gates** (AC: #24)
  - [ ] From `spa/`:
    - `npm run lint` → exit 0.
    - `npm test -- --no-watch` → exit 0. Capture test count.
    - `npm run build` → exit 0; `dist/spa/browser/index.html` produced; lazy chunk `settings-page` confirmed.
    - `npm run test:coverage` → exit 0; coverage of `src/app/settings/` ≥70%; coverage of `src/app/shared/errors/` ≥70%.
  - [ ] If `vitest.config.ts` exists (Story 1.9 may have created it), verify `src/app/shared/errors/**` is in its `coverage.include` glob. If not, add it.

- [ ] **Task 13 — Bookkeeping** (AC: #27)
  - [ ] Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: flip `3-5-bff-resourceserverclient-...` `ready-for-dev` → `in-progress` at story start, → `review` at end. Bump `last_updated`.
  - [ ] If new defers surface during implementation, append them under `## Deferred from: dev-story of 3-5-...` in `deferred-work.md`. Start at D80 (D71-D79 are owned by Story 3.4; verify the current ceiling).
  - [ ] Verify `git diff --stat` matches the file list in AC27 (no surprise touches).

## Dev Notes

### What this story is — and is not

**This story closes the J4 user surface end-to-end.** It introduces:

- The BFF's `ResourceServerClient` — a `httpx`-based HTTP client with the canonical AR19 timeouts (5s connect / 10s read), the architectural-marquee single 401-refresh-replay cycle, and the FR-ERROR-01 / J6 honest-503 surface for RS unavailability.
- The BFF's `/v1/reading-speed` thin proxy router (GET + PUT) — session-validated, CSRF-enforced on PUT, body-verbatim-forwarding for 2xx/4xx, mapped-503 for 5xx/transport failures.
- A new BFF `ErrorCode.RESOURCE_SERVER_UNAVAILABLE` member (the project-specific 503 wire code per architecture C5 line 401).
- A new BFF config field `RS_BASE_URL` (required-fail-fast) — closes the implicit-hostname coupling between the BFF and the RS service in compose.
- The SPA's `ReadingSpeedService` — signal-driven state + load/save methods + `justSaved` pulse for the "Saved" button relabel.
- The SPA's `SettingsPage` component (replaces `SettingsPagePlaceholder` from Story 1.10) — the J4 user-facing UI per UX-DR9 / UX-DR11 / UX-DR15.
- The SPA's `AppError` discriminated union + `ErrorService` parser — first instance of this pattern (architecture lines 714-731); future stories extend the union as new domain errors land.
- The SPA's `ReadingSpeedOut` type — wire-shape `snake_case` per AR16.

**Explicitly NOT in scope:**

- **No `POST /v1/estimate` on the RS.** Story 4.1.
- **No `compute_estimate` on `ResourceServerClient`.** Story 4.2 (epic line 1331 — "compute_estimate is NOT yet implemented (deferred to Epic 4 Story 4.2)").
- **No books CRUD.** Epic 2.
- **No `EstimateCell` SPA component.** Story 4.3.
- **No e2e Playwright spec for J4.** Story 3.6 (epic line 1469-1518 owns the J4 spec + compose `e2e` profile updates).
- **No `killRs` / `startRs` Playwright helpers.** Story 3.6.
- **No RS compose-profile changes.** Story 3.6.
- **No SPA changes to `TopChrome`** beyond optionally extending its spec for AC20.
- **No SPA changes to `AuthService`, the two interceptors, or the two guards** — Story 1.9's contracts are stable and consumed by this story.
- **No `from_attributes` Pydantic config on the BFF proxy** — there is no DTO on the BFF (the proxy uses `dict[str, Any]` per AC3 explanation).
- **No `book_not_found` / other variants in `AppError`** — only the four real consumers from this story's surface + `unknown` fallback. Architecture lines 714-731 enumerate the full eventual union; Story 2.2 / 4.3 / etc. add their own.
- **No metrics, no traces, no OTEL exporter wiring** — inert per the 2026-05-14 sprint-change cut.

### Dependencies (CRITICAL — read before starting)

**Story 3.3 (`done`)** — owns the RS's `/v1/reading-speed` GET/PUT handlers, the scope gates (`reading-speed:read` / `reading-speed:write`), the `reading_speeds` table + Alembic migration, and the wire envelopes for 412 `reading_speed_unset` / 403 `forbidden_scope` / 422 `invalid_input`. **The proxy in this story FORWARDS these envelopes verbatim** — no transformation, no rewrap. If a Story 3.3 envelope shape changes, the BFF proxy auto-tracks because it doesn't re-parse the body for 4xx paths.

**Story 3.4 (`done`)** — owns the RS's `POST /v1/test/reset` endpoint. **Not consumed by this story** (the BFF proxies user traffic via JWT bearer, not via the e2e test-reset bearer), but the conftest patterns for fresh-app + in-memory SQLite test contexts are worth mirroring for BFF tests if a per-test app build is needed.

**Story 1.5 (`done`)** — owns the BFF's `keycloak_cookie_session.py` (`exchange_code`, `revoke_refresh_token`, `end_session`, JWT verification, the `_TOKEN_EXCHANGE_TIMEOUT` httpx timeout idiom). **This story's `_refresh_access_token` method MIRRORS the pattern**: an async httpx POST to `oidc_issuer_url + "/protocol/openid-connect/token"` with form-encoded body, client_id + client_secret as form fields. **Do NOT use Authlib's `AsyncOAuth2Client`** for the refresh grant — its `fetch_token(grant_type='refresh_token', ...)` shape is awkward to test; a plain httpx POST is simpler. Story 1.5's `exchange_code` uses Authlib because the authorization-code flow benefits from Authlib's PKCE plumbing; the refresh grant is straightforward enough to issue directly.

**Story 1.6 (`done`)** — owns the `CsrfMiddleware`. **This story relies on the middleware as-is** — `/v1/reading-speed` PUT is subject to CSRF; the middleware enforces it before the route handler runs. No new exemption path. The `client_with_csrf` test fixture (conftest.py:97-126) provides the cookie + header + Origin combo.

**Story 1.7 (`done`)** — owns `/auth/logout`, which clears the session + CSRF cookies. **The cookie-clearing pattern in `_session_terminated_response` mirrors logout's pattern** — `response.delete_cookie(name, path="/")` for both cookies. Verify the exact path argument the logout endpoint uses; matching it preserves the contract that "logging out" and "session terminated by refresh failure" produce indistinguishable cookie clears.

**Story 1.9 (`done`)** — owns the SPA `AuthService`, the two interceptors (`withCredentialsInterceptor`, `csrfInterceptor`), and the two guards (`authGuard`, `redirectIfAuthedGuard`). **Critical contracts this story RELIES on:**
- `withCredentialsInterceptor` runs the global 401-handler for any path EXCEPT `/api/me` (line 26 of `with-credentials-interceptor.ts` — the `pathOf(authedReq.url) !== ME_PATH` check). A 401 from `/v1/reading-speed` triggers `authService.clear()` + `router.navigateByUrl('/login?return_to=...')`. **THIS STORY DOES NOT REPLICATE THE NAVIGATION** — it is the interceptor's job.
- `csrfInterceptor` attaches `X-CSRF-Token` to POST/PUT/PATCH/DELETE requests when the `csrf_token` cookie is present. **THIS STORY DOES NOT MANUALLY ATTACH THE HEADER** — the interceptor handles it.

**Story 1.10 (`done`)** — owns the route table, `TopChrome`, `ErrorMessage`, and the `SettingsPagePlaceholder`. **This story REPLACES the placeholder** (`spa/src/app/settings/settings-page-placeholder.ts` is deleted; `app.routes.ts` repoints to `./settings/settings-page`). The `ErrorMessage` shared component is imported and used by `SettingsPage` per UX-DR10. The `TopChrome` contextual link logic already produces `"Books"` on `/settings` — no change needed (the spec assertion is verified or extended per AC20).

**Story 3.6 (`backlog`)** — DOWNSTREAM. Owns the J4 Playwright spec, compose `e2e` profile updates (adding the RS), and the `killRs` / `startRs` / extended `resetState` helpers. **This story MUST land before 3.6 starts.** The 503 J6 surface this story implements is what Story 3.6's `killRs` spec asserts on.

**Story 4.2 (`backlog`)** — DOWNSTREAM. Will extend `ResourceServerClient` with a `compute_estimate(...)` method (epic line 1331). **This story explicitly does NOT pre-stage that method** — adding it now would force a partial test of an unfinished method, which dilutes the AC matrix.

### Architecture compliance

- **AR17 (epics line 74)** — `ErrorCode` enum extensions. Adds `RESOURCE_SERVER_UNAVAILABLE` (503) to the BFF; the RS half (`READING_SPEED_UNSET`, `FORBIDDEN_SCOPE`, `INVALID_INPUT`, `SESSION_EXPIRED`) already landed in Story 3.3.
- **AR19 (epics line 76)** — Timeouts. `httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)` matches the architecture's specification. **No retries on 5xx** (PRD §FR-ERROR-01 + AR19's explicit "zero retries on 5xx"). The 401-refresh-replay is the SOLE retry pattern, and it is bounded to ONE cycle.
- **AR21 (epics line 81)** — State management with Signals. `ReadingSpeedService` uses signals exclusively (no NgRx, no global store). `SettingsPage` reads signals via the service's exposed read-only signal types.
- **AR22 (epics line 82)** — HTTP interceptors. The SPA's existing two interceptors handle session cookie attachment + CSRF header + global 401 navigation. `ReadingSpeedService` does NOT touch headers or interceptors.
- **AR23 (epics line 83)** — Routing + guards. `/settings` is guarded by `authGuard` (already wired in Story 1.10).
- **AR16 (architecture §"Naming Patterns / HTTP API" lines 554-560)** — Wire shape is `snake_case` in both directions. `ReadingSpeedOut.pages_per_hour` is `snake_case` (NOT `pagesPerHour` on the wire; the SPA signal is `pagesPerHour` because that's the SPA's idiomatic naming, not the wire).
- **AR29 (epics line 90)** — Environment variables. `RS_BASE_URL` is a new project env var; both `services/bff/.env.example` and `compose/app.yml` declare it.
- **NFR3 (architecture line 38)** — Transparent token refresh. The 401-refresh-replay cycle in `ResourceServerClient` is the canonical implementation of this NFR.
- **NFR6 (architecture line 1141)** — Identity propagation. `sub` is never added to RS request bodies/paths/queries; the RS reads it from the JWT.
- **FR-ERROR-01 (PRD §FR-ERROR-01 / epics line 24 / architecture line 1178)** — Honest J6 error. The BFF surfaces 503 `resource_server_unavailable` when the RS is unreachable; never fabricates a result.
- **UX-DR9 (epics line 111)** — SettingsView. The component's render states (loading / value / unset / load-error / saving / saved / save-error / validation-error) match this requirement.
- **UX-DR10 (epics line 112)** — `ErrorMessage` component. Reused for the four error messages in SettingsPage.
- **UX-DR11 (epics line 113)** — Feedback. No spinners; loading is signaled via disabled controls; success is the `"Saved"` ~1s pulse (the only success acknowledgement permitted anywhere in the SPA).
- **UX-DR12 (epics line 114)** — Failure copy strings. `"Service unavailable — try again shortly"` for 503; `"Enter a positive number"` for validation + 422; `"Couldn't save — try again"` as the generic fallback (verify the exact string in epics line 114).
- **UX-DR14 (epics line 121)** — Button hierarchy. Single primary `"Save"` button styled with `--color-accent`; disabled state is 50% opacity.
- **UX-DR15 (epics line 122)** — Form patterns. Native HTML controls; validation on submit only (not blur); inputs preserve values on submit failure; every input has a `<label>`.
- **UX-DR16 (epics line 123)** — Layout. The 720px column is provided by `app.html`'s `<main class="app-content">`; the component renders inside it.

### Library / framework requirements

**BFF — no new dependencies.** All imports are already in `services/bff/pyproject.toml`:
- `fastapi` (≥0.135.1) — APIRouter, Request, Depends, JSONResponse, Response.
- `httpx` (≥0.28.1) — `AsyncClient`, `Timeout`, the `HTTPError` family.
- `sqlalchemy` / `sqlmodel` — `AsyncSession`, `Session` SQLModel entity.
- `pydantic-settings` — `AppSettings` baseclass for the new `rs_base_url` field.
- `respx` (≥0.21.0) — dev-only, used by the new tests for RS mock.

**SPA — no new dependencies.** All imports are already in `spa/package.json`:
- `@angular/common`, `@angular/core`, `@angular/forms` (signals, `inject`, `HttpClient`, `HttpErrorResponse`).
- `rxjs` (`firstValueFrom`).
- `vitest`, `@vitest/coverage-v8` — dev-only, already used by Stories 1.8-1.10.

Python 3.14 is the project floor. Match the existing codebase's style: type annotations everywhere, `from __future__ import annotations` at the top of every new module, `Annotated[...]` for `Depends`. ESLint rules `no-console` (allow warn/error), `no-empty` (no empty catch).

### File structure requirements

**New files (BFF):**
- `services/bff/src/bff/services/resource_server_client.py` — the client class + module-level singleton + `RsUnavailable` + `RsSessionTerminated` exceptions.
- `services/bff/src/bff/api/reading_speed.py` — the proxy router + session helper + response builders.
- `services/bff/tests/api/test_reading_speed_proxy.py` — the proxy tests.
- `services/bff/tests/services/test_resource_server_client.py` — the refresh-and-replay tests.

**New files (SPA):**
- `spa/src/app/shared/errors/app-error.types.ts`
- `spa/src/app/shared/errors/error-service.ts`
- `spa/src/app/shared/errors/error-service.spec.ts`
- `spa/src/app/settings/reading-speed.types.ts`
- `spa/src/app/settings/reading-speed-service.ts`
- `spa/src/app/settings/reading-speed-service.spec.ts`
- `spa/src/app/settings/settings-page.ts`
- `spa/src/app/settings/settings-page.html`
- `spa/src/app/settings/settings-page.css`
- `spa/src/app/settings/settings-page.spec.ts`

**Modified files (BFF):**
- `services/bff/src/bff/core/config.py` — add `rs_base_url` field + validator.
- `services/bff/src/bff/core/errors.py` — add `RESOURCE_SERVER_UNAVAILABLE` ErrorCode.
- `services/bff/src/bff/api/v1/__init__.py` — include the new reading_speed router.
- `services/bff/.env.example` — add `RS_BASE_URL` entry.
- `compose/app.yml` — add `RS_BASE_URL` to the BFF env block (if `environment:` style; skip if pure `env_file:` style).

**Modified files (SPA):**
- `spa/src/app/app.routes.ts` — repoint `'settings'` to `SettingsPage`.

**Deleted files:**
- `spa/src/app/settings/settings-page-placeholder.ts`.

**Modified (optional):**
- `spa/src/app/shared/chrome/top-chrome.spec.ts` — one extra test if AC20's contextual-link-on-`/settings` is missing.

**NOT modified:**
- `services/resource-server/**` — RS consumed unchanged. NO changes to RS modules.
- `services/bff/src/bff/main.py` — `v1_router` is already mounted.
- `services/bff/src/bff/api/me.py`, `auth.py`, `health.py`, `test_reset.py` — all unchanged.
- `services/bff/src/bff/services/session_service.py` — consumed as-is; the existing `get_session` / `delete_session` / `delete_expired_session` methods are sufficient.
- `services/bff/src/bff/auth/keycloak_cookie_session.py` — its `_TOKEN_EXCHANGE_TIMEOUT` constant is mirrored in `resource_server_client.py`'s `_RS_TIMEOUT`; no shared module (each service-level client gets its own timeout).
- `services/bff/src/bff/auth/csrf.py` — no new exemption added.
- `spa/src/app/auth/**` — consumed unchanged.
- `spa/src/app/shared/http/**` — consumed unchanged.
- `spa/src/app/shared/chrome/top-chrome.ts` — Story 1.10's contextual link is correct as-is.
- `spa/src/app/shared/ui/error-message.{ts,html,css}` — consumed unchanged.
- `spa/src/app/app.config.ts`, `app.html`, `app.ts`, `app.css`, `app.spec.ts` — unchanged.

### Testing standards

- **BFF Framework:** pytest 8+ / pytest-asyncio (`asyncio_mode = "auto"`), respx 0.21+ for httpx mocking.
- **BFF HTTP client:** `httpx.AsyncClient(transport=ASGITransport(app=app))` via the conftest fixtures.
- **BFF coverage:** project gate `fail_under = 90` (`services/bff/pyproject.toml`). Per-file ≥90% for the two new source files (epic line 1459).
- **BFF log assertion:** `caplog.set_level(logging.WARNING, logger="bff.services.resource_server_client")` + assert on `caplog.text` or `caplog.records`.
- **SPA Framework:** Vitest 4+ / `@angular/build:unit-test` builder.
- **SPA HTTP testing:** `provideHttpClient(withFetch())` + `provideHttpClientTesting()` + `HttpTestingController`. No Karma, no Jasmine.
- **SPA fake timers:** `vi.useFakeTimers()` + `vi.advanceTimersByTime(1000)` for the `justSaved` pulse test (AC21 #5, #9). Restore via `vi.useRealTimers()` in `afterEach`.
- **SPA coverage:** ≥70% for `src/app/settings/` and `src/app/shared/errors/` (epic line 1466).
- **SPA test naming:** `<feature>.spec.ts`, top-level `describe(...)` + `it(...)` blocks.
- **SPA standalone components only:** No `NgModule`. `TestBed.configureTestingModule({ imports: [Component] })`.
- **Python invocation:** all commands use `python` (not `python3`) per `CLAUDE.md`.
- **Lint/format:** `uv run ruff check` / `uv run ruff format --check` / `uv run ty check` all green before commit. `npm run lint` green for SPA.

### Previous story intelligence

**From Story 3.4 (RS test-reset — `done`, merged 053a8ff):**
- The doubled-prefix test file name pattern (`test_test_reset.py`) is for production modules whose name collides with pytest's test-discovery convention. **Not applicable here** — `test_reading_speed_proxy.py` and `test_resource_server_client.py` are unambiguously test files (the production modules are `reading_speed.py` and `resource_server_client.py`).
- `Response(status_code=204)` produces empty body + `content-length: 0` per RFC 7230 §3.3.2. **Not applicable** — this story emits 200/4xx/503 with bodies; no 204 path.
- Compose validation needed transient `.env` files (gitignored). For this story, only the BFF + RS profiles change minimally; `docker compose --profile default config` should work with the existing `.env` setup. The RS per-service `.env` is gitignored — if missing, copy from `services/resource-server/.env.example` for the validation run.
- The "register on gate" pattern (Story 3.4's `register_test_reset_router(app, cfg)`) is NOT mirrored here. The reading-speed proxy is unconditionally mounted (it's a production endpoint, not e2e-only). No gating.

**From Story 3.3 (RS `/v1/reading-speed` — `done`):**
- The RS uses `Field(ge=1)` Pydantic constraint + `extra="forbid"` ConfigDict on `ReadingSpeedUpsert`. **The BFF MUST forward 422 envelopes verbatim** because the validation is delegated to the RS.
- `ReadingSpeedOut` has only `pages_per_hour: int` — keeps `created_at` / `updated_at` / `sub` out of the wire. The BFF proxy preserves this — no body augmentation.
- The 412 `reading_speed_unset` envelope is `{"errorCode": "reading_speed_unset", "message": "Reading speed not set for this user", "detail": null}` — pin this exact body in proxy test #2.
- The 403 `forbidden_scope` envelope is `{"errorCode": "forbidden_scope", "message": "Required scope is missing", "detail": null}` — pin in proxy test #3.

**From Story 1.5 (BFF OIDC plugin — `done`):**
- The Keycloak `/token` endpoint URL is `oidc_issuer_url + "/protocol/openid-connect/token"`. Verify by reading `services/bff/src/bff/api/auth.py:227`.
- The httpx Timeout idiom: `httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)`. Mirror exactly.
- For confidential clients, Keycloak's `/token` accepts `client_id` + `client_secret` as form fields (NOT Basic auth — that's RFC standard but Keycloak's docs show form-field for the refresh grant in the confidential-client flow). Verify in dev by inspecting the Keycloak realm config.

**From Story 1.7 (BFF logout — `done`):**
- `response.delete_cookie(name, path="/")` is the Starlette pattern for emitting `Set-Cookie: name=; Max-Age=0; Path=/; SameSite=lax`. Verify the exact attributes by inspecting the logout response in `services/bff/tests/api/test_auth.py`.

**From Story 1.9 (SPA auth + interceptors — `done`):**
- The `withCredentialsInterceptor` runs the 401 global handler for any URL EXCEPT `/api/me`. This means a 401 from `/v1/reading-speed` triggers `authService.clear()` + navigation to `/login?return_to=...` AUTOMATICALLY. **The `ReadingSpeedService` MUST NOT replicate this** — its catch block for 401 just sets `saving/loading.set(false)` and returns silently (the navigation is already scheduled).
- `csrfInterceptor` attaches `X-CSRF-Token` on PUT — no manual header attachment needed.
- `AuthService.setMe` exists (Story 1.9 added it) — not used by this story; mentioned for completeness.

**From Story 1.10 (SPA route table + chrome — `done`):**
- The route loaders use `loadComponent: () => import('./settings/settings-page').then((m) => m.SettingsPage)`. Match this exact form.
- `provideAppInitializer(() => inject(AuthService).loadMe())` is in `app.config.ts` — `AuthService.me` is populated before route activation. `SettingsPage`'s `ngOnInit` calls `speedService.load()` knowing the user is authenticated.
- `ErrorMessage` accepts `message: input.required<string>()`. Import via `import { ErrorMessage } from '../shared/ui/error-message';` in the standalone `imports` array.
- `TopChrome` reads `Router.events` filtered to `NavigationEnd` + `startWith(this.router.url)`. The contextual link on `/settings` is `"Books"` (verified at `top-chrome.ts:38-49`). No change needed.

### Git intelligence summary

Last 5 commits on `epic-3` (the branch this story merges into):
- `053a8ff Merge story 3.4 — RS POST /v1/test/reset gated truncate of reading_speeds` — Story 3.4 merged 2026-05-17.
- `b92925c chore(3.4): code review — CR1–CR3 applied, mark done, log D74–D79`
- `5248e62 feat(3.4): RS POST /v1/test/reset — gated truncate of reading_speeds`
- `2338bba chore(3.4): create story — RS POST /v1/test/reset endpoint`
- `61b28c5 Merge story 3.3 — RS ReadingSpeed model + /v1/reading-speed GET+PUT scope-gated`

**Implication for this story:** Stories 3.3 + 3.4 sequentially landed the RS's reading-speed API + the test-reset endpoint. **This story is the FIRST to wire the BFF to the RS over HTTP** (Stories 3.1-3.4 were RS-only; Stories 1.x were BFF-only). The integration is the architectural marquee. Expect ~15-20 new BFF tests + ~25 new SPA tests; total new test count ≈ 40-50.

### Latest tech information

- **FastAPI 0.135+ / Starlette** — `Response.delete_cookie(key, path="/")` emits a single `Set-Cookie` header with `Max-Age=0; Path=/; SameSite=lax`. Multiple `delete_cookie` calls on the same response produce multiple `Set-Cookie` headers (the way to clear two cookies in one response). Verify by reading Starlette's `Response` source if unsure.
- **httpx 0.28+** — `httpx.HTTPError` is the base class for all transport + HTTP failures; specific subclasses include `httpx.ConnectError`, `httpx.ConnectTimeout`, `httpx.ReadTimeout`, `httpx.WriteTimeout`, `httpx.PoolTimeout`, `httpx.NetworkError`, `httpx.RemoteProtocolError`. The `Timeout` constructor accepts named `connect`/`read`/`write`/`pool` kwargs.
- **respx 0.21+** — `respx.mock` provides the context manager + the `respx_mock` fixture. `mock.get("http://...").mock(return_value=httpx.Response(200, json={...}))` is the basic pattern; `side_effect=...` accepts an exception or a callable returning a Response. `mock.calls.call_count` is the call counter (NOT `mock["name"].call_count`).
- **pydantic-settings 2.x** — string env vars are auto-loaded from `.env`; the `extra="ignore"` setting on `SettingsConfigDict` (BFF's pattern at `config.py:25`) means unknown env vars are silently dropped. The new `rs_base_url` field's required-fail-fast logic lives in a `model_validator(mode="after")`.
- **Angular 21 signals** — `signal<T>()` for writable, `.asReadonly()` for read-only views, `computed(() => ...)` for derived. `effect(() => ...)` for side-effects (e.g., syncing input value from service signal when the service value changes). `effect()` runs synchronously after each commit phase; the `_userEdited` boolean in `SettingsPage` guards against clobbering user typing.
- **Vitest 4 fake timers** — `vi.useFakeTimers()` + `vi.advanceTimersByTime(1000)`. The `setTimeout(_, 1000)` inside `ReadingSpeedService.save` is captured by the fake-timers harness; advancing time drains the queue.

### Project Structure Notes

- The new BFF source files slot cleanly into the existing `services/` and `api/` packages (per architecture line 902, 908).
- The new SPA `settings/` directory replaces the placeholder; the structure mirrors `login/` and `books/` (component + service + types + specs).
- The new `shared/errors/` directory is the first instance of this pattern (architecture line 627: `errors/             # error types, error-service.ts, AppError discriminated union`).
- `compose/app.yml` gains ONE env var on the BFF service block (`RS_BASE_URL`). The `resource-server` service profiles stay `[default, dev]` — Story 3.6 will add `e2e`.

### References

- [Source: epics.md#Story 3.5 lines 1316-1466] — the entire story spec.
- [Source: epics.md#AR17 line 74] — `RESOURCE_SERVER_UNAVAILABLE` ErrorCode requirement.
- [Source: epics.md#AR19 line 76] — BFF→RS timeouts + no retries on 5xx.
- [Source: epics.md#AR21 line 81] — Signals state management.
- [Source: epics.md#AR22 line 82] — HTTP interceptors pattern.
- [Source: epics.md#AR23 line 83] — Routing + guards.
- [Source: epics.md#AR16 architecture lines 554-560] — Wire-vs-model casing.
- [Source: epics.md#AR29 line 90] — Environment variables enumeration.
- [Source: epics.md#NFR3 architecture line 38] — Transparent token refresh.
- [Source: epics.md#NFR6 architecture line 1141] — Identity propagation.
- [Source: epics.md#FR-ERROR-01 line 24 / PRD §FR-ERROR-01] — Honest J6 failure.
- [Source: epics.md#UX-DR9 line 111] — SettingsView component states.
- [Source: epics.md#UX-DR10 line 112] — ErrorMessage reuse.
- [Source: epics.md#UX-DR11 line 113] — Loading + saved-pulse conventions.
- [Source: epics.md#UX-DR12 line 114] — Failure copy strings.
- [Source: epics.md#UX-DR14 line 121] — Button hierarchy.
- [Source: epics.md#UX-DR15 line 122] — Form patterns.
- [Source: epics.md#UX-DR16 line 123] — Layout structure.
- [Source: architecture.md#C2 lines 376-378] — BFF endpoints `/v1/reading-speed` proxy.
- [Source: architecture.md#C5 line 401] — `RESOURCE_SERVER_UNAVAILABLE` wire code.
- [Source: architecture.md#C6 line 413] — BFF→RS timeouts.
- [Source: architecture.md#A6 line 352] — Token refresh strategy (reactive, single replay).
- [Source: architecture.md lines 714-731] — SPA `AppError` discriminated union pattern.
- [Source: architecture.md lines 756-759] — `ResourceServerClient` class shape.
- [Source: architecture.md line 1141] — `sub` is the only identifier crossing service boundaries.
- [Source: architecture.md line 1178] — FR-ERROR-01 mapping (BFF 503).
- [Source: architecture.md lines 1206-1244] — J3 sequence diagram (estimate flow — not in scope but informs the refresh-and-replay pattern).
- [Source: architecture.md lines 1396-1409] — Requirements-to-structure mapping (FR-SPEED-01 / FR-ERROR-01).
- [Source: services/bff/src/bff/api/me.py:50-69] — `_require_session` pattern to mirror.
- [Source: services/bff/src/bff/api/auth.py:227] — Keycloak `/token` URL construction.
- [Source: services/bff/src/bff/auth/keycloak_cookie_session.py:34] — `_TOKEN_EXCHANGE_TIMEOUT` httpx timeout idiom.
- [Source: services/bff/src/bff/auth/csrf.py:32, 48-50] — CSRF safe-methods + exempt paths.
- [Source: services/bff/src/bff/core/config.py:113-132] — `_validate_oidc_authorize_url_browser` pattern to mirror for `_validate_rs_base_url`.
- [Source: services/bff/src/bff/core/errors.py:9-32] — `ErrorCode` enum and current members.
- [Source: services/bff/src/bff/services/session_service.py:212-238] — `delete_session` for the refresh-failure path.
- [Source: services/bff/tests/conftest.py:97-126] — `client_with_csrf` fixture.
- [Source: services/bff/tests/auth/synthetic_idp.py:207-238] — refresh-grant handler shape; `revoked_refresh_tokens` set.
- [Source: services/resource-server/src/resource_server/core/errors.py:9-46] — RS ErrorCode definitions (forwarded shapes).
- [Source: services/resource-server/src/resource_server/api/reading_speed.py] — RS endpoint shape (what the proxy calls).
- [Source: spa/src/app/auth/auth-service.ts] — `loadMe` / `clear` / `setMe` pattern to mirror in `ReadingSpeedService`.
- [Source: spa/src/app/shared/http/with-credentials-interceptor.ts] — global 401 handler skipping `/api/me`.
- [Source: spa/src/app/shared/http/csrf-interceptor.ts] — `X-CSRF-Token` header attachment.
- [Source: spa/src/app/shared/chrome/top-chrome.ts:38-49] — contextual link logic.
- [Source: spa/src/app/shared/ui/error-message.ts] — shared component used by SettingsPage.
- [Source: spa/src/app/login/login-view.{ts,html,css}] — analogous standalone-component shape.
- [Source: spa/src/app/app.routes.ts] — route table to update.
- [Source: services/bff/pyproject.toml] — `[tool.coverage.report].fail_under = 90` gate.
- [Source: services/bff/CLAUDE.md] — quality gate enumeration.
- [Source: CLAUDE.md (root)] — project convention: `python` (not `python3`).
- [Source: spa/eslint.config.js] — ESLint rules (no-console allow warn/error; no-empty no allowEmptyCatch).
- [Source: spa/package.json] — `test`, `lint`, `build`, `test:coverage` scripts.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — D71-D79 are owned by Story 3.4; Story 3.5 starts at D80.

### Project context reference

Project-context facts loaded at activation:
- BMAD_books accessibility / responsive design: OUT OF SCOPE (per `MEMORY.md`). The `SettingsPage` does NOT add ARIA roles, focus management, or breakpoint-specific styling beyond what the design tokens already provide.
- Backend archetype: `github.com/tommaso-meledina/fastapi-archetype` (Python 3.14 + FastAPI + SQLModel + uv + OTEL). This story stays inside the archetype's conventions (FastAPI APIRouter, SQLModel session pattern, uv-managed deps); httpx is already a dependency.
- Python invocation: `python` (never `python3`) — applies to any inline command examples in this story file. The existing Dockerfile, compose healthchecks, and pytest invocations already follow this convention.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.

### File List

(To be populated by dev-story.)
