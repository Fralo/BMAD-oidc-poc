---
status: review
story_key: 4-2-bff-post-v1-books-id-estimate-resourceserverclient-compute-estimate
epic: 4
prerequisites: 2.2 (done — `/v1/books*` CRUD, `BooksService.get_for_user(db, *, sub, book_id)` returning `Book | None`, `ErrorCode.BOOK_NOT_FOUND`, `_resolve_session_sub` helper pattern in `api/books.py`); 3.5 (done — `ResourceServerClient` class with `_call_with_refresh` cycle, `RsUnavailable` / `RsSessionTerminated` exceptions, `ErrorCode.RESOURCE_SERVER_UNAVAILABLE`, `_require_session` row-returning helper pattern in `api/reading_speed.py`, `_session_terminated_response` / `_resource_server_unavailable_response` proxy helpers, respx-based BFF→RS test patterns); 4.1 (done — RS `POST /v1/estimate` body `{"pages": int}` returns `{"minutes": int, "formatted": str}`, 412 `reading_speed_unset`, 403 `forbidden_scope`, 422 `invalid_input`, 401 `session_expired` — this is the upstream contract Story 4.2 brokers)
created: 2026-05-17
baseline_commit: e167c3c
---

# Story 4.2: BFF — `POST /v1/books/{id}/estimate` + `ResourceServerClient.compute_estimate`

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a signed-in user (via the SPA),
I want the BFF to expose `POST /v1/books/{id}/estimate` that looks up my book by `(sub, id)`, brokers the RS estimate call with my bearer token, and returns the formatted duration — or an honest named failure if the RS is down,
so that the SPA can request estimates without ever talking to the RS directly and without needing to know my access token, scopes, or reading-speed value.

## Scope (read this first)

This story is **BFF-only** — the RS upstream (`POST /v1/estimate`) is done (Story 4.1), the SPA `EstimateCell` is Story 4.3, the J3/J6 E2E specs are Story 4.4.

Concretely, this story delivers:

1. `services/bff/src/bff/services/resource_server_client.py` (**MODIFY**) — generalize `_do_rs_call` to accept `path` + `method` (currently hardcoded `_READING_SPEED_PATH` + `GET`/`PUT`); add a public `async def compute_estimate(self, db, session_row, *, pages: int) -> tuple[int, dict[str, Any] | None]` that delegates through the existing `_call_with_refresh` so the 401-refresh-replay cycle / 5xx-or-transport → `RsUnavailable` / refresh-failure → `RsSessionTerminated` semantics carry over unchanged.
2. `services/bff/src/bff/api/books.py` (**MODIFY**) — add `async def estimate_for_book(...)` handler at `POST /{book_id}/estimate` on the existing books router (final mount: `/v1/books/{book_id}/estimate`). Resolves the session row, looks up the book by `(sub, book_id)` BEFORE any RS call, raises `BOOK_NOT_FOUND` if not found, then forwards `pages=book.pages` to `compute_estimate` and proxies the (status, body) verbatim. Add a parallel `_resolve_session_row(request, db, cfg) -> SessionRow` helper that returns the row (alongside the existing `_resolve_session_sub` which returns only `.sub` — the new handler needs the row for `session_row.access_token`).
3. `services/bff/tests/services/test_resource_server_client.py` (**MODIFY**) — extend with `test_compute_estimate_*` covering: happy path (RS 200 → forwarded); 412 / 403 / 422 forwarded verbatim; ConnectError / ReadTimeout / WriteTimeout → `RsUnavailable`; RS 5xx → `RsUnavailable` (no retry — `respx` call-count = 1); refresh-and-replay happy (RS 401 → Keycloak `/token` → RS retry → 2xx); refresh fails → `RsSessionTerminated(clear_cookies=True)` + session row deleted; refresh worked but retry still 401 → `RsSessionTerminated(clear_cookies=False)`, row not deleted; NFR6 (no `sub` in URL, query, body); `Authorization: Bearer <access_token>` actually present.
4. `services/bff/tests/api/test_books.py` (**MODIFY**) — extend with `test_estimate_*` covering: happy path (200 + body forwarded); cross-user 404 (book id exists but is owned by another sub — `respx` asserts the RS was **never called**); missing book id 404 (same short-circuit); 401 paths (no session cookie / unknown session id / expired session row); 403 `csrf_invalid` (no `X-CSRF-Token`); RS 412 → BFF 412 forwarded; RS 5xx / connect-error / read-timeout → BFF 503 `resource_server_unavailable`; refresh-failure → BFF 401 + both cookies cleared; the NFR6 pin (captured RS request has empty query string and a body matching `{"pages": <book.pages>}` byte-for-byte — never `{"pages": ..., "sub": ...}`).

**Out of scope for 4.2:** any RS code (Story 4.1 shipped the upstream); any SPA code (Story 4.3 owns `EstimateCell`); any new `ErrorCode` member (the codes this story emits — `BOOK_NOT_FOUND` from 2.2, `SESSION_EXPIRED` from 1.5, `CSRF_INVALID` from 1.6, `RESOURCE_SERVER_UNAVAILABLE` from 3.5 — already exist on `bff.core.errors.ErrorCode`); any new Pydantic schema (`compute_estimate` returns `tuple[int, dict[str, Any] | None]` like its `get_reading_speed`/`put_reading_speed` siblings — the BFF forwards the RS body verbatim via `JSONResponse(status_code=status, content=body)`; the typed `EstimateOut` lives on the RS only per Story 4.1 and reappears in the SPA only at Story 4.3); any compose / Dockerfile / Playwright change; any `_resolve_session_sub` refactor in `api/books.py` (keep it unchanged — add `_resolve_session_row` next to it; the architectural decision to extract a shared session helper was deferred at Story 3.5 to "after a fourth consumer arrives" — Story 4.2 is the third+ consumer in the same file, but the rule is preserved).

## Acceptance Criteria

The epic's BDD acceptance criteria are reproduced from `epics.md` lines 1585–1628 below; AC numbers are added for traceability into Tasks and Tests.

### AC1 — Endpoint mounted on the existing books router with the correct surface

**Given** the existing `services/bff/src/bff/api/books.py` registers `router = APIRouter(prefix="/books", tags=["Books"])` (line 42),
**When** Story 4.2 adds a new handler decorated as `@router.post("/{book_id}/estimate")`,
**Then** the endpoint appears in OpenAPI at path `/v1/books/{book_id}/estimate` (the `/v1` segment comes from `api/v1/__init__.py`'s `router = APIRouter(prefix="/v1")` and the existing `router.include_router(books_router)` — verified in `bff/api/v1/__init__.py`),
**And** the handler signature is:
```python
@router.post("/{book_id}/estimate")
async def estimate_for_book(
    request: Request,
    book_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> JSONResponse:
    ...
```
**And** the handler returns a `fastapi.responses.JSONResponse` always (happy + every error path) — no `response_model=` decoration is used (mirrors `api/reading_speed.py`'s proxy pattern at lines 153–187; the 200/412/422/403/503 paths all flow through the same return shape without forcing the error envelopes through `EstimateOut` validation),
**And** no `api/v1/__init__.py` edit is required (the books router is already wired; the new handler auto-mounts because it lives on the same `router` instance).

[Source: epics.md#Story 4.2 line 1587; architecture.md#C2 line 376; `services/bff/src/bff/api/books.py:42`; `services/bff/src/bff/api/v1/__init__.py`.]

### AC2 — Session resolution returns the **row** (not just the sub) for the new handler

**Given** the new handler needs `session_row.access_token` to forward to `ResourceServerClient.compute_estimate`,
**And** the existing `_resolve_session_sub(request, db, cfg) -> str` (books.py:63–86) returns only the `sub` string and is consumed by the five CRUD handlers,
**When** Story 4.2 adds a parallel helper `_resolve_session_row(request, db, cfg) -> SessionRow` in `services/bff/src/bff/api/books.py` directly below `_resolve_session_sub`,
**Then** `_resolve_session_row` is a verbatim copy of `_resolve_session_sub`'s body except the final return is `return row` (not `return row.sub`),
**And** the three 401 failure modes are preserved exactly — missing cookie → `AppException(ErrorCode.SESSION_EXPIRED)`; unknown session id → `AppException(ErrorCode.SESSION_EXPIRED)`; expired row → `_session_service.delete_expired_session(...)` + `AppException(ErrorCode.SESSION_EXPIRED)` (lazy-delete preserved),
**And** the existing `_resolve_session_sub` is **NOT modified** (the five CRUD handlers continue calling it; behavior preservation is asserted by AC11's "existing tests stay green" gate),
**And** the new helper imports the existing `SessionRow` type via `from bff.models.entities.session import Session as SessionRow` at the top of the file (mirrors `api/reading_speed.py:42`).

**Design note — why a parallel helper, not a refactor.** The architecturally-correct refactor would have `_resolve_session_sub` call `_resolve_session_row(...).sub`. Story 3.5's Dev Notes explicitly deferred that consolidation to "after a fourth consumer arrives" to avoid pre-mature abstraction (Story 1.9's lesson) and to keep regression risk contained. Story 4.2 is the third+ consumer of the pattern in the same `books.py` file, but the rule is preserved — the two helpers coexist with a 12-line duplication that a follow-up story can collapse safely when a true fourth callsite materializes.

[Source: `services/bff/src/bff/api/books.py:63-86`; `services/bff/src/bff/api/reading_speed.py:81-100` (the row-returning pattern mirrored here); epics.md#Story 4.2 lines 1586-1589.]

### AC3 — Book lookup short-circuits BEFORE the RS call (existence-leak guard + no-fanout)

**Given** an authenticated session with `sub = S`,
**When** `POST /v1/books/{book_id}/estimate` is called for a `book_id = B`,
**Then** the handler resolves the session row first (AC2), then calls `_books_service.get_for_user(db, sub=S, book_id=B)` (the existing Story 2.2 method at `services/bff/src/bff/services/books_service.py:38-55`),
**And** if `get_for_user` returns `None` (book does not exist OR is owned by a different `sub` — the SQL embeds `WHERE id = :id AND sub = :sub` so both cases collapse to `None`), the handler raises `AppException(ErrorCode.BOOK_NOT_FOUND)` which maps to **404 `book_not_found`** via the existing `app_exception_handler`,
**And** the RS is **never called** in the 404 path — the `respx` mock for `/v1/estimate` MUST record call_count == 0 (this is asserted explicitly in AC10's cross-user-404 and missing-book-404 tests).

**Why this ordering matters:**
- **Existence-leak guard.** Per architecture line 685 + Story 2.2's lines 819–821 ("404 not 403"), the BFF must NOT distinguish "book does not exist" from "book belongs to someone else" — both yield the same 404 + `book_not_found` envelope. The `(sub, id)` predicate composed in SQL already enforces this for CRUD; AC3 extends it to the estimate path.
- **No useless RS fanout.** Every estimate call costs a BFF→RS round-trip + JWT validation + a `reading_speeds` DB lookup. Calling the RS for a book the user doesn't own would be a latency penalty + log-noise + potential `reading-speed:read` scope check exhaustion for no user-visible benefit. The book lookup is one local SQL `SELECT` against an indexed table; cheap by comparison.

[Source: epics.md#Story 4.2 lines 1591-1598; architecture.md line 685; `services/bff/src/bff/services/books_service.py:38-55`; `services/bff/src/bff/api/books.py:119-130` (the existing GET handler's identical (sub, id) check is the precedent).]

### AC4 — Happy path: 200 + body forwarded verbatim from the RS

**Given** an authenticated session for `sub = S` and a book row `(id=B, sub=S, pages=688)`,
**When** `POST /v1/books/{B}/estimate` is called with a valid session cookie + valid `X-CSRF-Token`,
**Then** the handler calls `resource_server_client.compute_estimate(db, session_row, pages=688)`,
**And** the RS responds 200 with body `{"minutes": 1376, "formatted": "≈ 22 h 56 m"}` (the example from epics.md#Story 4.2 line 1595 — `math.ceil(688 * 60 / 30) = 1376` minutes when `pages_per_hour = 30`; `format_duration(1376)` = `"≈ 22 h 56 m"` per Story 4.1's pinned boundary rule),
**And** the BFF responds 200 with the same body — byte-identical, including the `≈` (U+2248) character and the field order if `dict[str, Any]` round-trips it (the JSON spec does not preserve order, but Python's `dict` preserves insertion-order so the round-trip through `JSONResponse(content=body)` emits the same shape — pin via test that asserts `body == {"minutes": 1376, "formatted": "≈ 22 h 56 m"}` by equality, not by string).

The pass-through is implemented via `return JSONResponse(status_code=status, content=body)` — identical to `api/reading_speed.py:168` / `:187`.

[Source: epics.md#Story 4.2 lines 1591-1595; Story 4.1 AC4 (the upstream contract); architecture.md#C7 line 418 (`EstimateOut` is the wire shape).]

### AC5 — RS 412 `reading_speed_unset` forwarded verbatim (J3 freshuser precondition)

**When** the RS responds 412 with `{"errorCode": "reading_speed_unset", "message": "Reading speed not set for this user", "detail": null}` (Story 4.1 AC6 — the `freshuser` precondition path),
**Then** the BFF responds **412** with the same body, byte-identical.

The BFF does NOT re-wrap, re-codify, or translate the envelope. Specifically: the BFF MUST NOT raise `AppException(ErrorCode.READING_SPEED_UNSET)` (no such member exists on `bff.core.errors.ErrorCode` — checking the enum at `services/bff/src/bff/core/errors.py:24-42` shows only the BFF-emitted codes; `reading_speed_unset` is RS-owned, the BFF only forwards). Adding a new `READING_SPEED_UNSET` member to the BFF's enum is **out of scope for this story** — the verbatim-forward pattern is intentionally what `api/reading_speed.py` does today and what Story 4.2 preserves.

The 412 path goes through the same `return JSONResponse(status_code=status, content=body)` as AC4; the only difference is `status == 412` and the body shape.

[Source: epics.md#Story 4.2 lines 1600-1601; Story 4.1 AC6; `services/bff/src/bff/core/errors.py:24-42`; `services/bff/src/bff/api/reading_speed.py:153-187`.]

### AC6 — RS 403 `forbidden_scope` forwarded verbatim (defensive)

**When** the RS responds 403 with `{"errorCode": "forbidden_scope", "message": "Required scope is missing", "detail": null}` (Story 4.1 AC5),
**Then** the BFF responds **403** with the same body, byte-identical.

Under normal Keycloak realm config the BFF's user-access-token carries both `reading-speed:read` and `reading-speed:write` scopes (Story 1.2 + 1.5), so a 403 from the RS is a defensive path. The test suite asserts the forwarding works regardless. This is the same pattern Story 3.5 AC5 pinned for `/v1/reading-speed`.

[Source: epics.md#Story 4.2 lines 1603-1604; Story 4.1 AC5; `services/bff/src/bff/api/reading_speed.py:165-168`.]

### AC7 — RS 422 `invalid_input` forwarded verbatim (defensive)

**When** the RS responds 422 `invalid_input` (Story 4.1 AC7 — e.g., if a future refactor makes the BFF send a body other than `{"pages": <int>=1}`),
**Then** the BFF responds **422** with the same body, byte-identical (including the `detail` array with each entry's `input` field already dropped by the RS's `validation_exception_handler`).

This is a defensive path — Story 4.2's handler will always send a well-formed body (`{"pages": book.pages}` where `book.pages` is `ge=1` per `BookCreate.pages = Field(ge=1, le=1_000_000)` at `services/bff/src/bff/api/schemas/book.py:31`). Pin the forwarding behavior anyway — a future RS contract tightening (e.g., adding a `le=N` cap on `pages`) would surface here and the assertion catches the regression early.

[Source: epics.md#Story 4.2 line 1627 ("422 forwarded"); `services/bff/src/bff/api/schemas/book.py:31`.]

### AC8 — RS 5xx / transport error → BFF 503 `resource_server_unavailable` (no retry)

**Given** `ResourceServerClient.compute_estimate` calls the RS,
**When** any of the following occurs:
- `httpx.ConnectError` (TCP connection refused, DNS failure),
- `httpx.ConnectTimeout` (>5s connect — per AR19),
- `httpx.ReadTimeout` (>10s read — per AR19),
- `httpx.WriteTimeout` / `httpx.PoolTimeout`,
- `httpx.NetworkError` / `httpx.RemoteProtocolError` / catch-all `httpx.HTTPError`,
- RS responds with any 5xx (500, 501, 502, 503, 504, 599),

**Then** `ResourceServerClient._do_rs_call` raises `RsUnavailable(cause=...)` (the existing classifier, no new behavior — this is already implemented at `services/bff/src/bff/services/resource_server_client.py:251-283`),
**And** the books-router handler catches `RsUnavailable` and returns the project-standard 503 envelope:
```json
{"errorCode": "resource_server_unavailable", "message": "The resource server is temporarily unavailable", "detail": null}
```
via a helper identical to `api/reading_speed.py:141-150`'s `_resource_server_unavailable_response()`. **Reuse that helper if practical** — either by extracting it to a small shared module (e.g., `bff.api._proxy_responses`) OR by inlining a copy in `books.py` (favoring inline copy to avoid the import-coupling Story 3.5's Dev Notes flagged at AC4 about `auth._clear_session_cookies`).

**Concretely:** for Story 4.2, inline a private helper `_resource_server_unavailable_response()` in `services/bff/src/bff/api/books.py` (10 lines, no imports beyond what's already there). The duplication is the conservative play: extracting a shared module is a single-arrow-of-coupling change that should be staged behind a fourth consumer (consistent with AC2's reasoning above). Document the deliberate-duplication choice in the dev log so a follow-up story can collapse `reading_speed.py`'s + `books.py`'s + any future copies into a shared helper.

**The 401-refresh-replay cycle does NOT fire on 5xx or transport errors** — that branch is reserved exclusively for RS 401 responses (AC9 below). The 5xx surface is final; no further BFF activity (no retry, no log-and-suppress).

**No retries on any failure:** `respx`-based tests in AC10 assert the RS mock's `call_count == 1` for every 5xx and transport-error case. This pins AR19 — "BFF → RS: 5s connect, 10s read; **zero retries on 5xx**".

[Source: epics.md#Story 4.2 lines 1606-1608; architecture.md#C6 line 413 (AR19); `services/bff/src/bff/services/resource_server_client.py:151-283` (existing RsUnavailable / `_do_rs_call`); `services/bff/src/bff/api/reading_speed.py:141-150` (the proxy helper to mirror).]

### AC9 — RS 401 → refresh-and-replay (single cycle, reuses Story 3.5's logic)

**Given** the existing `ResourceServerClient._call_with_refresh` (resource_server_client.py:204-250) owns the marquee 401-refresh-replay cycle architecturally,
**When** `compute_estimate` delegates through `_call_with_refresh`,
**Then** the RS-401 path triggers exactly as it does for `/v1/reading-speed`:

1. **First attempt** with `session_row.access_token` → RS responds 401.
2. **Refresh** via Keycloak `/token` with `grant_type=refresh_token` + the session's `refresh_token` + `client_id` + `client_secret`.
3a. **Refresh SUCCEEDS** → persist the rotated `access_token` + `refresh_token` + new `expires_at` via `_persist_refreshed_tokens` (Story 3.5 / Story 4.1's code-review applied CR3-CR4 here — verify the `_is_valid_expires_in` gate is still in place before the retry).
3b. **Retry** the RS call ONCE with the new access_token. Forward the retry's outcome (any status — 200, 412, 422, 503, etc.) to the caller. **No further retries** regardless of the retry's outcome (AR19 / epic line 1611).
4a. **Refresh FAILS** (Keycloak 4xx/5xx, transport error, malformed response, missing/invalid `expires_in`) → delete the session row via `SessionService.delete_session(db, session_id=session_row.id)`, raise `RsSessionTerminated(clear_cookies=True)`. The handler catches it and emits 401 `session_expired` with both `bff_session` and `csrf_token` cookies cleared (`Max-Age=0`).
4b. **Refresh succeeds but the retry still 401s** → raise `RsSessionTerminated(clear_cookies=False)`. The handler emits 401 `session_expired` WITHOUT clearing cookies — the SPA's `/login` redirect will produce a new login that overwrites the session on success.

**Zero new behavior in `_call_with_refresh`** — Story 4.2 extends the public surface (`compute_estimate`), but does NOT modify the refresh logic. The only change to `resource_server_client.py` is:

1. Add a constant `_ESTIMATE_PATH = "/v1/estimate"` near the existing `_READING_SPEED_PATH` constant (line 68).
2. Generalize `_do_rs_call(method, access_token, body)` to `_do_rs_call(method, path, access_token, body)` — accept the URL path as a parameter rather than the current hardcoded `_READING_SPEED_PATH`.
3. Generalize `_call_with_refresh(db, session_row, *, method, body)` to `_call_with_refresh(db, session_row, *, method, path, body)` — thread `path` through both attempts (initial + retry).
4. Update the two existing callers `get_reading_speed` and `put_reading_speed` to pass `path=_READING_SPEED_PATH` (preserves their wire behavior identically).
5. Add the new public method:
```python
async def compute_estimate(
    self,
    db: AsyncSession,
    session_row: Session,
    *,
    pages: int,
) -> tuple[int, dict[str, Any] | None]:
    """Issue ``POST /v1/estimate`` with body ``{"pages": pages}`` and refresh-and-replay.

    Same return / raise contract as :meth:`get_reading_speed`:
    returns ``(http_status, parsed_body_or_None)`` on every reachable
    RS response. Raises :class:`RsUnavailable` on transport failure or
    RS 5xx; :class:`RsSessionTerminated` when the refresh cycle cannot
    recover (``clear_cookies=True`` if refresh failed,
    ``clear_cookies=False`` if refresh worked but the retry still 401'd).

    NFR6: ``sub`` is NEVER added to the URL, query, or body. The RS
    reads ``sub`` from the JWT only.
    """
    return await self._call_with_refresh(
        db,
        session_row,
        method="POST",
        path=_ESTIMATE_PATH,
        body={"pages": pages},
    )
```

**`_do_rs_call` must learn the POST verb.** The current `_do_rs_call` (line 252-313) has a `method == "GET" / "PUT"` branch and a `# pragma: no cover` else that raises `ValueError`. Extend it with `elif method == "POST": response = await client.post(url, headers=headers, json=body)` — this is a single new branch.

[Source: epics.md#Story 4.2 lines 1610-1613; `services/bff/src/bff/services/resource_server_client.py:204-313`; Story 3.5 AC4 / AC12 (refresh-and-replay tests already pin the behavior — extend them with a `POST /v1/estimate` parametrization rather than re-pinning the cycle).]

### AC10 — NFR6 identity propagation (no `sub` in URL/query/body)

**Given** identity propagation (architecture line 1141: `"sub` is the only identifier that crosses service boundaries; the RS reads it from the JWT`"),
**When** the BFF calls the RS for the estimate path,
**Then** the captured RS request inspectable by `respx` MUST satisfy ALL of:
- `request.url.path == "/v1/estimate"` (no `sub` segment appended).
- `request.url.query == b""` (or empty string, depending on httpx version — pin via `assert request.url.params == httpx.QueryParams()` for portability).
- `json.loads(request.content) == {"pages": <book.pages>}` — exactly two-key absent (NO `"sub"` field, NO other keys), values byte-identical.
- `request.headers["Authorization"] == f"Bearer {session_row.access_token}"`.

**Tests:** in `tests/services/test_resource_server_client.py`, add `test_compute_estimate_does_not_inject_sub_in_url_or_body` that inspects the captured request via `respx_mock.calls.last.request` (or `respx_mock.routes[...].calls[-1]`). Pin the four invariants above.

[Source: epics.md#Story 4.2 lines 1615-1617; architecture.md line 1141; Story 3.5 AC12 case #9 (the mirror invariant for `/v1/reading-speed`).]

### AC11 — Session + CSRF gates (1.5 / 1.6 plumbing preserved)

**When** `POST /v1/books/{B}/estimate` is called without a session cookie,
**Then** the BFF responds 401 with `{"errorCode": "session_expired", ...}` BEFORE any DB lookup or RS call. **NO cookies are cleared** in this path (the AC4 case-4 cookie-clear is exclusive to the refresh-failure trajectory).

**When** the cookie value is present but no row matches (unknown session id),
**Then** the BFF responds 401 `session_expired`, no cookie clear, no RS call.

**When** the cookie's row exists but `expires_at < datetime.now(UTC)`,
**Then** the BFF lazy-deletes the row via `_session_service.delete_expired_session(...)` and responds 401 `session_expired`, no cookie clear, no RS call.

**When** `POST /v1/books/{B}/estimate` is called with a valid session cookie but without `X-CSRF-Token` (or with a header that does not equal the `csrf_token` cookie value, or with a cross-origin `Origin`/`Referer`),
**Then** the existing `CsrfMiddleware` (Story 1.6, `services/bff/src/bff/auth/csrf.py`) rejects the request at the middleware layer with 403 `csrf_invalid` BEFORE the route handler runs. **No new `_CSRF_EXEMPT_PATHS` entry is added** (only `/v1/test/reset` is exempt; Story 1.12). POST is a state-changing method per `_SAFE_METHODS` exclusion — the check runs automatically.

[Source: epics.md#Story 4.2 lines 1619-1623; `services/bff/src/bff/api/books.py:63-86` (session pattern); `services/bff/src/bff/auth/csrf.py` (Story 1.6).]

### AC12 — `tests/services/test_resource_server_client.py` covers `compute_estimate`

**Given** the existing `tests/services/test_resource_server_client.py` already pins the refresh-and-replay cycle for `get_reading_speed`/`put_reading_speed` (Story 3.5 AC12, 20 cases),
**When** Story 4.2 extends the file with `compute_estimate` cases,
**Then** the following tests are added (parametrize across `get_reading_speed` / `compute_estimate` where the cycle behavior is identical — preferred — OR duplicate the assertions on a `_estimate` suffix; both are acceptable; choose the form that yields the most readable test count):

| # | Scenario | Setup | Asserted |
|---|---|---|---|
| 1 | happy 200 forwards body + status | seeded session_row + `respx` mock RS POST `/v1/estimate` → 200 `{"minutes": 1376, "formatted": "≈ 22 h 56 m"}` | returned tuple equals `(200, {"minutes": 1376, "formatted": "≈ 22 h 56 m"})`; `respx` called exactly once |
| 2 | RS 412 forwarded | mock → 412 `reading_speed_unset` envelope | tuple equals `(412, {"errorCode": "reading_speed_unset", "message": "...", "detail": None})` |
| 3 | RS 403 forwarded | mock → 403 `forbidden_scope` | `(403, {"errorCode": "forbidden_scope", ...})` |
| 4 | RS 422 forwarded | mock → 422 `invalid_input` with sanitized detail | `(422, ...)` |
| 5 | RS 500 → RsUnavailable | mock → 500 | `pytest.raises(RsUnavailable) as exc; assert exc.value.cause == "rs_5xx_response"; assert exc.value.http_status == 500`; `respx` called exactly once |
| 6 | RS 502 → RsUnavailable | mock → 502 | same shape, `http_status == 502` |
| 7 | RS 503 → RsUnavailable | mock → 503 | same shape, `http_status == 503` |
| 8 | RS 504 → RsUnavailable | mock → 504 | same shape, `http_status == 504` |
| 9 | ConnectError → RsUnavailable | mock `side_effect = httpx.ConnectError("boom")` | `cause == "connect_error"`, `http_status is None`, called once |
| 10 | ConnectTimeout → RsUnavailable | `httpx.ConnectTimeout` | `cause == "connect_timeout"` |
| 11 | ReadTimeout → RsUnavailable | `httpx.ReadTimeout` | `cause == "read_timeout"` |
| 12 | WriteTimeout → RsUnavailable | `httpx.WriteTimeout` | `cause == "write_timeout"` |
| 13 | refresh-and-replay happy | synthetic IdP `/token` returns 200 with new tokens; respx RS 401 → 200 | tuple equals retry's `(200, body)`; session row's `access_token` updated in DB; `_token` called exactly once; RS called exactly twice |
| 14 | refresh fails → RsSessionTerminated(clear_cookies=True) | RS 401 → IdP 4xx via `idp.revoked_refresh_tokens.add(...)` | `pytest.raises(RsSessionTerminated) as exc; assert exc.value.clear_cookies is True`; session row deleted from DB |
| 15 | refresh succeeds + retry still 401 → RsSessionTerminated(clear_cookies=False) | RS 401, IdP 200 with new tokens, RS retry 401 | `clear_cookies is False`; session row NOT deleted |
| 16 | NFR6 — no `sub` in URL / query / body | inspect `respx_mock.calls[-1].request` | `.url.path == "/v1/estimate"`; query empty; `json.loads(.content) == {"pages": 688}`; no `"sub"` key |
| 17 | `Authorization: Bearer <access_token>` header present | inspect captured request | `headers["authorization"] == f"Bearer {session_row.access_token}"` |
| 18 | refresh-and-replay does NOT fire on 412 | RS 412 directly | `idp.captured_token_exchanges` is empty (synthetic IdP pattern from `tests/auth/synthetic_idp.py:214`) |
| 19 | refresh-and-replay does NOT fire on 403 | RS 403 | same — no `/token` call |
| 20 | refresh-and-replay does NOT fire on 5xx | RS 500 | no `/token` call; 5xx is the unavailable path, not the refresh path |
| 21 | post body verbatim — `pages=int` | call `compute_estimate(db, row, pages=600)` | captured body equals `{"pages": 600}` byte-for-byte; `pages` is JSON int (`600`), not string (`"600"`) or float (`600.0`) |
| 22 | rejects `pages` as kwarg only | inspect signature — `compute_estimate(db, row, pages=...)` is keyword-only via the `*` separator | a positional `compute_estimate(db, row, 600)` raises `TypeError` (Python's enforcement) — pinned by a small `pytest.raises(TypeError)` |

**Path-extension regression coverage.** The existing 20 cases for `get_reading_speed`/`put_reading_speed` (Story 3.5 AC12) MUST remain green after `_call_with_refresh` learns the `path` parameter. Verify by running the full `tests/services/test_resource_server_client.py` suite — every case that previously passed `method="GET"`/`"PUT"` should now pass `method=...`, `path=_READING_SPEED_PATH` and have identical observable behavior. If any case fails after the threading-through change, the refactor introduced a behavior change rather than a pure generalization — diagnose before continuing.

**Coverage of `services/bff/src/bff/services/resource_server_client.py` remains ≥90%** (per epic line 1628; was already at ~95% post-Story 3.5). The path-threading change is a no-op on covered lines; the new `compute_estimate` method + `_ESTIMATE_PATH` constant + the `method == "POST"` branch land at >90% with cases 1–22 above.

[Source: epics.md#Story 4.2 lines 1625-1628; `services/bff/tests/services/test_resource_server_client.py` (Story 3.5's existing suite); `services/bff/tests/auth/synthetic_idp.py:214-275`.]

### AC13 — `tests/api/test_books.py` covers the route end-to-end

**Given** the existing `tests/api/test_books.py` covers the five CRUD routes (Story 2.2, 30+ tests),
**When** Story 4.2 extends the file with a new section `# Story 4.2 — POST /v1/books/{id}/estimate` (or moves the estimate tests to a new file `tests/api/test_books_estimate.py` if the dev judges the existing file is getting unwieldy — both are acceptable; prefer extension for traceability),
**Then** the following tests are added using the existing `client` / `client_with_csrf` fixtures + `respx` for the RS mock (mirrors `tests/api/test_reading_speed_proxy.py`):

| # | Scenario | Setup | Asserted |
|---|---|---|---|
| 1 | happy 200 forwards body | seed session + book (`pages=688`) for `sub=S`; respx RS returns 200 `{"minutes":1376,"formatted":"≈ 22 h 56 m"}` | response.status_code == 200; response.json() == `{"minutes":1376,"formatted":"≈ 22 h 56 m"}`; respx called once |
| 2 | missing book id 404 | seed session for S; no book seeded; POST `/v1/books/999/estimate` | 404 + `errorCode: "book_not_found"`; respx call_count == 0 (RS never called — AC3 short-circuit) |
| 3 | cross-user 404 | seed session for S; seed book owned by S2; POST `/v1/books/<S2-book-id>/estimate` with S's session | 404 + `book_not_found`; respx call_count == 0 |
| 4 | no session cookie 401 | client without cookie | 401 + `session_expired`; respx call_count == 0; cookies NOT cleared in response Set-Cookie headers (AC11 — no clear on missing-cookie path) |
| 5 | unknown session id 401 | client with cookie pointing at a non-existent row | 401 + `session_expired`; respx call_count == 0 |
| 6 | expired session 401 + row deleted | seed row with `expires_at < now`; POST | 401 + `session_expired`; expired row deleted post-call (assert via `await session_service.get_session(db, session_id=...) is None`) |
| 7 | missing CSRF 403 | `client` fixture (session cookie but no CSRF header) | 403 + `csrf_invalid`; respx call_count == 0 |
| 8 | RS 412 → BFF 412 forwarded | seed session + book; respx 412 `reading_speed_unset` | 412 + body forwarded verbatim (`errorCode: "reading_speed_unset"`) |
| 9 | RS 403 → BFF 403 forwarded | respx 403 `forbidden_scope` | 403 + body forwarded |
| 10 | RS 422 → BFF 422 forwarded | respx 422 `invalid_input` (sanitized detail) | 422 + body forwarded |
| 11 | RS 500 → BFF 503 | respx 500 | 503 + `errorCode: "resource_server_unavailable"`; respx call_count == 1 (no retry) |
| 12 | RS 503 → BFF 503 | respx 503 | 503 + same envelope |
| 13 | RS ConnectError → BFF 503 | respx side_effect ConnectError | 503 + same envelope; call_count == 1 |
| 14 | RS ReadTimeout → BFF 503 | respx ReadTimeout | 503 + same envelope |
| 15 | refresh-failure → BFF 401 + both cookies cleared | respx RS 401 → IdP 4xx; full integration via `synthetic_idp` | 401 + `session_expired`; response Set-Cookie headers include `bff_session=...; Max-Age=0; Path=/` AND `csrf_token=...; Max-Age=0; Path=/`; sessions row deleted |
| 16 | refresh-replay happy → 200 forwarded | respx RS 401 → IdP 200 (new tokens) → RS retry 200 | 200 + body forwarded; session row's `access_token` rotated in DB |
| 17 | refresh worked + retry 401 → 401 without cookie clear | respx 401 → IdP 200 → RS retry 401 | 401 + `session_expired`; NO Set-Cookie deletion headers in response; sessions row NOT deleted |
| 18 | NFR6 — captured RS request shape | respx 200 mock, then inspect `respx_mock.calls.last.request` | `.url.path == "/v1/estimate"`; query empty; `json.loads(.content) == {"pages": <book.pages>}`; `headers["authorization"] == f"Bearer {session_row.access_token}"` |
| 19 | book lookup uses `(sub, id)` predicate | seed two users each with their own book having `id=1`; POST `/v1/books/1/estimate` for user A | RS receives `pages` matching A's book (not B's); respx body inspected for the right `pages` value |
| 20 | path parameter validation — non-integer book_id | POST `/v1/books/not-an-int/estimate` | 422 `invalid_input` (FastAPI's path-conversion error); respx call_count == 0; assertion does NOT require the body since the upstream `validation_exception_handler` shape is already pinned by `tests/api/test_books.py`'s CRUD tests |
| 21 | empty body acceptable | POST with no body (the handler does not consume a body — `pages` is taken from `book.pages`, not the request) | the handler ignores any body — pin via test that posts `{}` and asserts 200 (the body is dead-weight; if a future refactor adds a body schema, this catches it) |

**Use the existing harness:** `services/bff/tests/api/test_reading_speed_proxy.py` is the template — its respx setup, fixture composition, and assertion style are the precedent. Mirror them; do not invent new patterns.

**Coverage of `services/bff/src/bff/api/books.py` remains ≥90%** (Story 2.2's gate). The new handler + `_resolve_session_row` helper + the inline 503 helper land at >90% with cases 1–21 above.

[Source: epics.md#Story 4.2 lines 1625-1628; `services/bff/tests/api/test_reading_speed_proxy.py` (the template); `services/bff/tests/api/test_books.py` (the file being extended).]

### AC14 — Static / lint / format / type / coverage gates remain green

**Given** the BFF's existing gate set,
**When** the following commands run from `services/bff/`:

```sh
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest --cov
```

**Then** all four exit 0,
**And** coverage gate at `[tool.coverage.report] fail_under = 90` is satisfied (project total ≥ 90%; the two modified modules — `services/resource_server_client.py` and `api/books.py` — each remain ≥ 90% per Story 2.2's and Story 3.5's existing thresholds),
**And** no Story 1.x / 2.x / 3.x test regression — all existing tests stay green (AC11 of Story 3.5's precedent is re-asserted here: this story extends behavior; it does not change any existing wire contract).

Capture transcripts in the Dev Agent Record's Debug Log References.

[Source: `services/bff/pyproject.toml` (gate config); `services/bff/CLAUDE.md` (the four-gates rule).]

### AC15 — Pre-existing repo state is preserved

Files outside the four modified files are bit-for-bit identical. Specifically: `CLAUDE.md`, root `README.md`, root `.env.example`, `docker-compose.yml`, `compose/`, `keycloak/`, `services/resource-server/**`, `spa/**`, `e2e/**`, `_bmad-output/planning-artifacts/**`, every other BFF source / test file.

**The only modifications:**
- **MODIFIED** `services/bff/src/bff/services/resource_server_client.py` — thread `path` through `_do_rs_call` / `_call_with_refresh`; add `_ESTIMATE_PATH` constant; add `method == "POST"` branch in `_do_rs_call`; add public `compute_estimate` method; update `get_reading_speed` / `put_reading_speed` to pass `path=_READING_SPEED_PATH`. **No changes to the refresh logic, the `RsUnavailable` / `RsSessionTerminated` exceptions, or the module-level singleton.**
- **MODIFIED** `services/bff/src/bff/api/books.py` — add `from typing import Any` (or extend the existing import); add `from fastapi.responses import JSONResponse`; add `from bff.models.entities.session import Session as SessionRow`; add `from bff.services.resource_server_client import RsSessionTerminated, RsUnavailable, resource_server_client`; add `_resolve_session_row` helper; add `_session_terminated_response(cfg, *, clear_cookies)` helper (inline copy mirroring `api/reading_speed.py:103-138`); add `_resource_server_unavailable_response()` helper (inline copy of `api/reading_speed.py:141-150`); add `@router.post("/{book_id}/estimate") async def estimate_for_book(...)`. **No changes to `_resolve_session_sub` or the five existing CRUD handlers.**
- **MODIFIED** `services/bff/tests/services/test_resource_server_client.py` — add ~20 new tests for `compute_estimate` (or parametrize the existing cycle tests over `method/path`). No edits to the existing 20 tests beyond mechanical parametrization.
- **MODIFIED** `services/bff/tests/api/test_books.py` — add ~20 new tests for the estimate route. No edits to the existing 30+ CRUD tests.
- **MODIFIED** `_bmad-output/implementation-artifacts/sprint-status.yaml` — status flip for `4-2-...` from `backlog` → `ready-for-dev`.
- **POTENTIALLY MODIFIED** `_bmad-output/implementation-artifacts/deferred-work.md` — new defers, if code review surfaces any.

[Source: this file's Dev Notes on the deliberate decision to inline-copy proxy helpers from `api/reading_speed.py` rather than extract a shared module.]

## Tasks / Subtasks

- [x] **Task 1 — Generalize `ResourceServerClient` to accept a path parameter** (AC: #9, #12)
  - [x] 1.1 Open `services/bff/src/bff/services/resource_server_client.py`. Below the existing `_READING_SPEED_PATH = "/v1/reading-speed"` (line 68), add `_ESTIMATE_PATH = "/v1/estimate"`.
  - [x] 1.2 Update `_do_rs_call` (line 252-313) signature: change `async def _do_rs_call(self, method: str, access_token: str, body: dict[str, Any] | None)` to `async def _do_rs_call(self, method: str, path: str, access_token: str, body: dict[str, Any] | None)`. Update the URL construction to use the passed `path` instead of the hardcoded `_READING_SPEED_PATH`. Add a `method == "POST"` branch:
    ```python
    elif method == "POST":
        response = await client.post(url, headers=headers, json=body)
    ```
    Place it between the existing `PUT` branch and the `else: raise ValueError` to keep alphabetic-by-verb-letter ordering loose but consistent.
  - [x] 1.3 Update `_call_with_refresh` (line 204-250) signature: change `*, method: str, body: dict[str, Any] | None` to `*, method: str, path: str, body: dict[str, Any] | None`. Thread `path` through BOTH `self._do_rs_call` calls (initial + retry).
  - [x] 1.4 Update `get_reading_speed` (line 179-189) and `put_reading_speed` (line 191-202) to pass `path=_READING_SPEED_PATH` when calling `_call_with_refresh`. Verify their existing tests still pass after this no-op generalization.
  - [x] 1.5 Run `uv run pytest tests/services/test_resource_server_client.py -q` to confirm the existing 20 cases still pass (parameter-threading should be observably identical).

- [x] **Task 2 — Add `ResourceServerClient.compute_estimate`** (AC: #1, #9, #10)
  - [x] 2.1 In the same file, add the public method (place it AFTER `put_reading_speed` to keep the methods in declaration order: read → write → estimate):
    ```python
    async def compute_estimate(
        self,
        db: AsyncSession,
        session_row: Session,
        *,
        pages: int,
    ) -> tuple[int, dict[str, Any] | None]:
        """Issue ``POST /v1/estimate`` with body ``{"pages": pages}`` and refresh-and-replay.

        Same return / raise contract as :meth:`get_reading_speed`. NFR6:
        ``sub`` is NEVER added to the URL, query, or body. The RS reads
        ``sub`` from the JWT only.
        """
        return await self._call_with_refresh(
            db,
            session_row,
            method="POST",
            path=_ESTIMATE_PATH,
            body={"pages": pages},
        )
    ```
  - [x] 2.2 Update the module docstring (lines 1-47): replace `"Compute-estimate (Epic 4 Story 4.2) will land as a third public method on this class. Story 3.5 explicitly does NOT pre-stage that method."` (lines 34-35) with one short paragraph stating compute_estimate is now present (Story 4.2). Append a `- epics.md §Story 4.2 lines 1585-1628` row to the References section.
  - [x] 2.3 Update `__all__` (line 399-404) — `compute_estimate` is a method, not a module export, so `__all__` does not change; verify the diff is clean.

- [x] **Task 3 — Extend `tests/services/test_resource_server_client.py` for `compute_estimate`** (AC: #12)
  - [x] 3.1 Open `services/bff/tests/services/test_resource_server_client.py`. The existing test fixtures (`session_row` factory, `synthetic_rs_idp`, `respx_mock`) carry over unchanged.
  - [x] 3.2 Add the 22 tests enumerated in AC12 above. Mirror the structure / style of the existing `test_get_reading_speed_*` / `test_put_reading_speed_*` cases. The minimum-viable approach: parametrize one large test over `(method, path, body, mock_response)` tuples covering happy + 412 + 403 + 422 + every RsUnavailable trigger + refresh-replay variants. Acceptable alternative: copy the existing `_get_*` test bodies and search-replace to `_estimate_*` with the new body — explicit and readable, slightly more lines.
  - [x] 3.3 The book-lookup happens in the router (AC3 → handler-level, tested in test_books.py), so this file does NOT seed a `books` row — the `compute_estimate` unit tests operate on `pages: int` directly.
  - [x] 3.4 Run `uv run pytest tests/services/test_resource_server_client.py -v` → exit 0; total per-method coverage ≥ 90% per file.

- [x] **Task 4 — Add `_resolve_session_row` helper to `api/books.py`** (AC: #2)
  - [x] 4.1 Open `services/bff/src/bff/api/books.py`. Add the imports needed by Tasks 5 + 6 at the top:
    ```python
    from typing import Any  # add to existing imports if not already covered
    from fastapi.responses import JSONResponse
    from bff.models.entities.session import Session as SessionRow
    from bff.services.resource_server_client import (
        RsSessionTerminated,
        RsUnavailable,
        resource_server_client,
    )
    ```
  - [x] 4.2 Immediately below the existing `_resolve_session_sub` (line 63-86), add `_resolve_session_row(request, db, cfg) -> SessionRow`. The body is a verbatim copy of `_resolve_session_sub` with the final `return row.sub` replaced by `return row`. **Do NOT modify `_resolve_session_sub`** — the existing five CRUD handlers continue calling it unchanged.
  - [x] 4.3 The expiry-check (`_as_utc_aware(row.expires_at) < datetime.now(UTC)` → lazy-delete + 401) is preserved exactly — copy the three lines verbatim.

- [x] **Task 5 — Add proxy-response helpers in `api/books.py`** (AC: #8, #9, #11)
  - [x] 5.1 Below `_resolve_session_row`, add `_session_terminated_response(cfg: AppSettings, *, clear_cookies: bool) -> JSONResponse`. Body: verbatim copy of `api/reading_speed.py:103-138` — the JSONResponse constructor with `errorCode: "session_expired"`, the lazy `_clear_session_cookies` import on the `clear_cookies` branch, the docstring CR1 note about `secure`/`samesite` attributes. The import-import-import dance for `_clear_session_cookies` (`from bff.api.auth import _clear_session_cookies` lazily inside the function) is mandatory — top-level import would create a circular dependency between `api.auth` and `api.books`.
  - [x] 5.2 Add `_resource_server_unavailable_response() -> JSONResponse`. Verbatim copy of `api/reading_speed.py:141-150` — the 503 envelope, no arguments.
  - [x] 5.3 Document the deliberate inline-copy choice with a single-line comment near each helper: `# Inlined from api/reading_speed.py per Story 4.2 — extract to a shared module after a fourth consumer arrives (3.5/4.2 = consumers two/three).`

- [x] **Task 6 — Add `POST /{book_id}/estimate` handler in `api/books.py`** (AC: #1, #3, #4, #5, #6, #7, #8, #9, #11)
  - [x] 6.1 Append the new handler at the bottom of `api/books.py` (after `delete_book`):
    ```python
    @router.post("/{book_id}/estimate")
    async def estimate_for_book(
        request: Request,
        book_id: int,
        db: Annotated[AsyncSession, Depends(get_session)],
        cfg: Annotated[AppSettings, Depends(_settings_dep)],
    ) -> JSONResponse:
        # Session row first (AC2). The 401 path NEVER clears cookies
        # (only the refresh-failure path does — AC11).
        session_row = await _resolve_session_row(request, db, cfg)

        # Book lookup BEFORE any RS call (AC3). Cross-user / missing
        # both collapse to None; both map to 404 book_not_found.
        book = await _books_service.get_for_user(
            db, sub=session_row.sub, book_id=book_id
        )
        if book is None:
            raise AppException(ErrorCode.BOOK_NOT_FOUND)

        # Broker the RS call. NFR6: pages from our local row; sub stays
        # in the JWT. compute_estimate handles the 401-refresh-replay
        # cycle internally.
        try:
            status, body = await resource_server_client.compute_estimate(
                db, session_row, pages=book.pages
            )
        except RsSessionTerminated as exc:
            return _session_terminated_response(cfg, clear_cookies=exc.clear_cookies)
        except RsUnavailable:
            # WARN log emitted inside ResourceServerClient; build the
            # standard 503 envelope here.
            return _resource_server_unavailable_response()

        # Forward verbatim — 200 / 412 / 403 / 422 all flow through here.
        return JSONResponse(status_code=status, content=body)
    ```
  - [x] 6.2 Verify the route appears in OpenAPI: from `services/bff/`, `uv run python -c "from bff.main import app; import json; print(json.dumps([p for p in app.openapi()['paths'] if 'estimate' in p], indent=2))"` should print `["/v1/books/{book_id}/estimate"]`.

- [x] **Task 7 — Extend `tests/api/test_books.py` for the estimate route** (AC: #13)
  - [x] 7.1 Open `services/bff/tests/api/test_books.py`. At the bottom, add a comment marker `# === Story 4.2 — POST /v1/books/{id}/estimate ===` and the 21 tests from AC13 below it. Reuse the existing `client` / `client_with_csrf` / `session_row_factory` / `book_factory` (if present) fixtures.
  - [x] 7.2 The `respx` mock target is `f"{settings.rs_base_url}/v1/estimate"`. Use `respx_mock.post(...)` to intercept POSTs specifically (not `route(...)`) so a GET that escapes by mistake fails the test instead of silently passing.
  - [x] 7.3 For the refresh-replay tests (cases #15-17 of AC13), reuse the synthetic IdP fixture pattern from `tests/api/test_reading_speed_proxy.py`'s refresh-replay tests (Story 3.5 — find the equivalent setups there and mirror them).
  - [x] 7.4 Run `uv run pytest tests/api/test_books.py -v` → exit 0; the new estimate section's tests pass alongside the existing CRUD tests.

- [x] **Task 8 — Coverage verification + per-file gate** (AC: #12, #13, #14)
  - [x] 8.1 From `services/bff/`, run `uv run pytest --cov=src/bff/api/books --cov=src/bff/services/resource_server_client --cov-report=term-missing`. Confirm both files report ≥ 90% line coverage.
  - [x] 8.2 Capture the per-file coverage table in the Dev Agent Record's Debug Log References. If `_resource_server_unavailable_response` or `_session_terminated_response` falls below 90% on books.py, add a targeted unit test rather than excluding lines (the surface is tiny; full coverage is achievable).
  - [x] 8.3 Run the full BFF suite: `uv run pytest --cov`. Confirm the project gate (`fail_under = 90`) is satisfied.

- [x] **Task 9 — Static + lint + format + type gates** (AC: #14)
  - [x] 9.1 From `services/bff/`: `uv run ruff check` → exit 0; transcript captured.
  - [x] 9.2 `uv run ruff format --check` → exit 0; transcript captured.
  - [x] 9.3 `uv run ty check` → exit 0 with zero errors. If `ty` flags the threading-through of `path` as causing a type narrowing on `_call_with_refresh`'s callers (it should not — `path: str` is a plain annotation), diagnose before suppressing.
  - [x] 9.4 `uv run pytest -q` → exit 0; full BFF suite green including Story 1.x / 2.x / 3.x; no new warnings escalated.

- [x] **Task 10 — Commit pacing per BFF CLAUDE.md** (AC: #14, #15)
  - [x] 10.1 Per `services/bff/CLAUDE.md`: commit at every point of stability with Conventional Commits messages (no scope). Suggested cadence:
    - C1: `refactor(4.2): thread path through ResourceServerClient._call_with_refresh / _do_rs_call` (Task 1 green — existing 20 tests still pass)
    - C2: `feat(4.2): add ResourceServerClient.compute_estimate + tests` (Tasks 2, 3 green)
    - C3: `feat(4.2): add _resolve_session_row + proxy helpers in api/books.py` (Tasks 4, 5 green; lint/type/test green)
    - C4: `feat(4.2): add POST /v1/books/{id}/estimate handler + route tests` (Tasks 6, 7 green)
    - C5: `chore(4.2): capture coverage + static-gate transcripts` (Tasks 8, 9 green, transcripts in Dev Agent Record)
  - [x] 10.2 Before each commit: re-run all four gates (`ruff check`, `ruff format --check`, `ty check`, `pytest`). Do NOT commit on a red gate.

## Dev Notes

### What this story is — and is not

**Is:** A pure-BFF story landing the `/v1/books/{id}/estimate` proxy endpoint + `ResourceServerClient.compute_estimate` method + their tests. Two source files modified (`services/resource_server_client.py`, `api/books.py`), two test files extended (`tests/services/test_resource_server_client.py`, `tests/api/test_books.py`). Zero new files. Zero changes outside `services/bff/`.

**Is NOT:** Any RS code (Story 4.1 shipped the upstream `/v1/estimate`); any SPA code (Story 4.3 owns `EstimateCell` + the `reading_speed_unset` AppError variant); any new `ErrorCode` enum member (every code emitted here — `BOOK_NOT_FOUND`, `SESSION_EXPIRED`, `CSRF_INVALID`, `RESOURCE_SERVER_UNAVAILABLE` — already exists on `bff.core.errors.ErrorCode`); any new Pydantic schema (the proxy forwards the RS body verbatim — `EstimateOut` lives only on the RS and reappears at Story 4.3 as a SPA TypeScript interface); any Alembic migration (no DB schema change); any compose / Dockerfile / Playwright change (Story 4.4 owns J3 / J6 E2E specs); any `_resolve_session_sub` refactor (Story 3.5 deferred the shared-helper extraction to "after a fourth consumer arrives" — preserved here).

### Files being read (not modified) for context

| File | Why | Lines of interest |
|---|---|---|
| `services/bff/src/bff/api/books.py` | Layout for the new handler + session-resolution pattern | 1-163 (whole file) |
| `services/bff/src/bff/api/reading_speed.py` | Proxy-helper template (`_session_terminated_response` + `_resource_server_unavailable_response`) | 103-150 |
| `services/bff/src/bff/services/resource_server_client.py` | The cycle to extend; existing `_call_with_refresh` / `_do_rs_call` | 1-405 (whole file) |
| `services/bff/src/bff/services/books_service.py` | `get_for_user(db, *, sub, book_id)` — the lookup we'll call | 38-55 |
| `services/bff/src/bff/core/errors.py` | `ErrorCode` enum (verify `BOOK_NOT_FOUND` / `RESOURCE_SERVER_UNAVAILABLE` / `SESSION_EXPIRED` present; no additions) | 9-47 |
| `services/bff/src/bff/api/schemas/book.py` | `BookCreate.pages = Field(ge=1, le=1_000_000)` — the upstream invariant that lets us trust `book.pages` is a positive int | 28-44 |
| `services/bff/src/bff/models/entities/book.py` | `Book.pages` SQLModel field | 23-30 |
| `services/bff/src/bff/auth/csrf.py` | CSRF middleware enforcement on POST | the `_CSRF_EXEMPT_PATHS` set + `_SAFE_METHODS` (verify no exemption needed) |
| `services/bff/tests/api/test_reading_speed_proxy.py` | respx + CSRF + session fixtures pattern | whole file (the template) |
| `services/bff/tests/services/test_resource_server_client.py` | The cycle tests being extended | whole file (the template + the suite to keep green) |
| `_bmad-output/implementation-artifacts/4-1-rs-post-v1-estimate-endpoint-estimate-service-format-duration-helper.md` | Upstream contract (the RS we're brokering) | AC1-AC11 (the wire shapes) |
| `_bmad-output/implementation-artifacts/3-5-bff-resourceserverclient-refresh-replay-reading-speed-proxy-spa-settingsview-route.md` | The precedent for this story's pattern | AC1-AC13 (the precedent BFF half of cross-service calls) |

### Why no new ErrorCode member

The codes this story emits are all already present:

| BFF response | ErrorCode | First added by |
|---|---|---|
| 200 / 412 / 403 / 422 (forwarded verbatim from RS) | (the RS's codes, passed through as JSON; not raised as AppException) | n/a — they bypass the BFF's enum entirely |
| 404 `book_not_found` | `BOOK_NOT_FOUND` (line 32 of errors.py) | Story 2.2 |
| 401 `session_expired` | `SESSION_EXPIRED` (line 24) | Story 1.5 |
| 403 `csrf_invalid` | `CSRF_INVALID` (line 31) | Story 1.6 |
| 503 `resource_server_unavailable` | `RESOURCE_SERVER_UNAVAILABLE` (line 38-42; CR8's generic-message form deliberately chosen for Story 4.2 reuse) | Story 3.5 |

In particular: **do NOT add `READING_SPEED_UNSET` to the BFF enum.** The 412 path is verbatim-forwarding — the body comes from the RS's `core/errors.py` (Story 3.3) and is passed through `JSONResponse(status_code=412, content=body)` without ever flowing through the BFF's `AppException` machinery. Adding a BFF-side `READING_SPEED_UNSET` member would imply the BFF could raise the error itself, which it cannot — the BFF has no access to the user's `reading_speeds` row, only the RS does.

### Why the proxy forwards verbatim instead of using `response_model=EstimateOut`

Architecture line 418 (`Distinct API Pydantic models (..., EstimateOut, ...)`) suggests an `EstimateOut` schema for type safety + OpenAPI documentation. The simpler alternative — already used by `api/reading_speed.py` — is verbatim-forwarding without `response_model`. Story 4.2 chooses the latter for three reasons:

1. **Error-path compatibility.** A `response_model=EstimateOut` decoration would force `JSONResponse` (used in error paths) to bypass it explicitly, OR force every error envelope through model validation (which would fail — `EstimateOut` doesn't have `errorCode` / `message` / `detail` fields). The proxy pattern with `JSONResponse` everywhere is simpler and uniform.
2. **Single source of truth.** The wire shape is owned by the RS (Story 4.1's `EstimateOut`). A BFF-side mirror schema would have to track every RS contract change in lock-step. The architecture line 418 reading "distinct Pydantic models" is satisfied by the RS — the BFF is a thin proxy here.
3. **Precedent consistency.** Story 3.5 chose verbatim-forwarding for `/v1/reading-speed`. Story 4.2 preserves the pattern.

The SPA (Story 4.3) will declare its OWN `interface EstimateOut { minutes: number; formatted: string }` in `spa/src/app/books/estimate.types.ts` — that's where the typed contract lives on the client side.

### The `_do_rs_call` path-parameter extension

The refactor is **purely additive**: `_do_rs_call` learns a new positional-keyword parameter `path: str`. The two existing callers (`get_reading_speed`, `put_reading_speed`) pass `path=_READING_SPEED_PATH` explicitly. The new caller (`compute_estimate`) passes `path=_ESTIMATE_PATH`. The existing 20 tests in `tests/services/test_resource_server_client.py` exercise the cycle with `method=GET`/`PUT` only; after the threading-through change they will pass `method=...`, `path=_READING_SPEED_PATH` and continue to assert the same observable behavior.

**Watch for:** if the existing test code uses `respx.get(f"{settings.rs_base_url}/v1/reading-speed")` or similar URL-prefix matching, the change is transparent. If any test reaches INTO `ResourceServerClient`'s private surface and calls `_do_rs_call` directly with positional args (which would be unusual), update the call sites to pass `path` explicitly.

### NFR6 — three places to pin "no `sub` injection"

The architecture invariant ("`sub` is the only identifier that crosses service boundaries; the RS reads it from the JWT") is asserted at three levels in Story 4.2:

1. **`compute_estimate` body shape.** The method's signature accepts `pages: int` as keyword-only; it constructs `body = {"pages": pages}` literally. There is no path-or-conditional through which `sub` could leak into the body. The test (AC12 case #16, AC13 case #18) inspects the captured request and pins `{"pages": <n>}` as the only body shape.
2. **`compute_estimate` URL.** The method's URL is `<rs_base_url> + _ESTIMATE_PATH` — no `sub` segment, no query string. Pin via test assertion `request.url.path == "/v1/estimate"` and `request.url.params == httpx.QueryParams()`.
3. **The book-lookup `(sub, id)` SQL predicate.** The handler reads `book = await _books_service.get_for_user(db, sub=session_row.sub, book_id=book_id)`. The `sub` used in the lookup comes from the session row, not from any user input. A future regression that took `sub` from a path/query/body parameter would surface as a behavior change in the handler — the test pattern (case #19 of AC13: "book lookup uses `(sub, id)` predicate") asserts that user A's request to user B's book id returns 404, which only holds if the `sub` predicate is composed in SQL.

### Cross-service-call sequence diagram (mental model for the dev)

```
SPA           BFF (api/books.py)            BFF (rsc.py)            RS (api/estimate.py)            Keycloak (/token)
 │ POST /v1/books/B/estimate                                                                              
 │ (cookie + X-CSRF-Token)                                                                                
 │────────────►│                                                                                          
 │             │ CsrfMiddleware ✓                                                                          
 │             │ _resolve_session_row(...)                                                                
 │             │ → SessionRow (sub=S)                                                                     
 │             │ _books_service.get_for_user(sub=S, book_id=B)                                            
 │             │ → Book(id=B, pages=688, sub=S)  [404 if None]                                            
 │             │                                                                                          
 │             │ resource_server_client.compute_estimate(db, row, pages=688)                              
 │             │────────────────────────────►│                                                            
 │             │                              │ POST /v1/estimate {"pages":688}                           
 │             │                              │ Authorization: Bearer <access_token>                      
 │             │                              │──────────────────────────────►│                           
 │             │                              │                              │ require_scope read ✓        
 │             │                              │                              │ estimate_service.compute    
 │             │                              │                              │ → EstimateOut(1376, "≈ 22 h 56 m")
 │             │                              │ ←─────── 200 + body ─────────│                           
 │             │ ◄─────── (200, body) ────────│                                                            
 │             │ JSONResponse(200, body)                                                                  
 │ ◄───────── 200 + body ─────│                                                                            
 │                                                                                                         

 RS 401 alternative:
 │             │                              │ POST /v1/estimate → RS 401                                
 │             │                              │ _refresh_access_token(row) ─────────────────────────►│    
 │             │                              │                                  POST /token         │    
 │             │                              │                                  grant_type=refresh ◄│    
 │             │                              │ ◄────────── 200 + new tokens ───────────────────────│    
 │             │                              │ _persist_refreshed_tokens (DB)                            
 │             │                              │ POST /v1/estimate → 200                                   
 │             │                              │ ◄── retry result ────────────                              
 │             │ ◄── (200, body) ─────────────│                                                            
 │ ◄────── 200 ─────│                                                                                      

 RS 5xx / transport-error alternative:
 │             │                              │ POST /v1/estimate → 500 / ConnectError                    
 │             │                              │ ──raises── RsUnavailable("rs_5xx_response")               
 │             │ ◄──────── RsUnavailable ─────│                                                            
 │             │ JSONResponse(503, {...resource_server_unavailable...})                                   
 │ ◄────── 503 ─────│                                                                                      

 Refresh-failure alternative:
 │             │                              │ POST /v1/estimate → RS 401                                
 │             │                              │ _refresh_access_token → Keycloak 4xx                      
 │             │                              │ session row deleted; ──raises── RsSessionTerminated(clear=True)
 │             │ ◄──────── RsSessionTerminated │                                                            
 │             │ JSONResponse(401, session_expired)                                                       
 │             │ + Set-Cookie: bff_session=; Max-Age=0                                                    
 │             │ + Set-Cookie: csrf_token=; Max-Age=0                                                     
 │ ◄────── 401 + cookies cleared ─│                                                                        
```

### Source tree components to touch

```
services/bff/
├── src/bff/
│   ├── api/
│   │   └── books.py                                       # MODIFY — add /{id}/estimate handler + helpers
│   └── services/
│       └── resource_server_client.py                      # MODIFY — generalize _do_rs_call + add compute_estimate
└── tests/
    ├── api/
    │   └── test_books.py                                  # MODIFY — add estimate tests
    └── services/
        └── test_resource_server_client.py                 # MODIFY — add compute_estimate tests
```

Four files modified, zero new files.

### Edge cases pinned by tests (do not relax without surfacing)

1. **Cross-user 404 short-circuit.** User A POSTs `/v1/books/<B-id>/estimate` where the book is owned by user B. AC3 + AC13 case #3 require the RS NEVER be called. Pin via `respx.calls.call_count == 0` after the assertion. A regression that swapped the order ("call RS, then check book") would still produce a 404 but would leak existence + waste a round-trip.
2. **No retry on 5xx.** AC8 + AC12 cases #5-#8 + AC13 cases #11-#12 require `respx.calls.call_count == 1` for every 5xx response. A regression that added an httpx retry transport would silently pass case #1 (happy path) but fail every 5xx test.
3. **Cookie clearing on refresh-failure only.** AC4 case 4 vs case 5 / AC13 case #15 vs #17 — refresh fails clears both cookies; refresh-then-retry-401 clears neither. Pin via assertion on the response's `Set-Cookie` headers (count + Max-Age=0 form).
4. **The `≈` character round-trips byte-identically.** The RS emits U+2248. The BFF's `JSONResponse(content=body)` serializes via Python's default JSON encoder, which preserves Unicode strings. Test the byte-identity with `response.json() == {"minutes": 1376, "formatted": "≈ 22 h 56 m"}` (object equality), not string-content matching — JSON serializers do not preserve key order across all versions, but key-value semantic equality holds. **If a future test runs in an environment with `JSONResponse(content=body, media_type="application/json; charset=...")` and `ensure_ascii=True` somehow becomes the default, the bytes would change (`≈` instead of the raw character)** — equality on the parsed dict is robust to that, content-string matching is not.
5. **Path parameter is `int`, not `str`.** FastAPI converts `{book_id}` to `int` via the type annotation. A request to `/v1/books/abc/estimate` becomes a 422 BEFORE the handler runs (FastAPI's path validation). AC13 case #20 pins this — do not relax `book_id: int` to `book_id: str` for any reason.

### What success looks like

After Story 4.2 lands, a developer can:

1. `docker compose --profile default up` brings up Keycloak + BFF + RS + SPA.
2. Log in as `testuser`. Set reading speed to `30` at `/settings` (Story 3.5).
3. Add a book (`Dune`, 688 pages, to-read) via the SPA (Story 2.7 path).
4. (At this point Story 4.3's SPA `EstimateCell` is NOT YET shipped, so the SPA's stub still renders. But the BFF endpoint exists and is testable via `curl`.)
5. From a separate shell:
   ```sh
   curl -X POST http://localhost:8000/v1/books/1/estimate \
     -H "X-CSRF-Token: $(cookies show csrf_token)" \
     -b "$(cookies all)" \
     -d ''
   ```
   returns `{"minutes": 1376, "formatted": "≈ 22 h 56 m"}`.
6. `docker compose stop resource-server` and re-run → 503 + `resource_server_unavailable`.
7. `docker compose start resource-server` and re-run after healthcheck → 200 again.
8. POST to a book id owned by `freshuser` → 404 `book_not_found` (no RS call in the BFF logs).
9. POST as `freshuser` (who has no reading_speeds row) → 412 `reading_speed_unset`.

When the J3 / J6 E2E specs (Story 4.4) come online, all five steps above become Playwright-asserted on every CI-style run.

### References

- epics.md §Story 4.2 lines 1585-1628 (BDD acceptance criteria — verbatim source)
- architecture.md §C2 line 376 (BFF endpoint contract: `POST /v1/books/{id}/estimate`)
- architecture.md §C5 lines 397-409 (`ErrorCode` enum — confirms `RESOURCE_SERVER_UNAVAILABLE` / `READING_SPEED_UNSET` are RS-owned wire codes; `BOOK_NOT_FOUND` is BFF-owned)
- architecture.md §C6 line 413 (AR19: 5s/10s; zero retries on 5xx)
- architecture.md §A6 line 352 (refresh-and-replay strategy)
- architecture.md §NFR3 line 38 (transparent token refresh)
- architecture.md §NFR6 line 1141 (identity propagation — `sub` is JWT-only)
- architecture.md line 685 (404 not 403 for resource ownership)
- architecture.md §C7 line 418 (`EstimateOut` is the wire shape; RS-side schema, SPA-side TypeScript mirror)
- PRD §FR-ESTIMATE-01 (the defining cross-service interaction)
- PRD §FR-ERROR-01 (honest J6 failure surface)
- `_bmad-output/implementation-artifacts/3-5-bff-resourceserverclient-refresh-replay-reading-speed-proxy-spa-settingsview-route.md` (the precedent BFF half of cross-service calls — Story 4.2 follows this story's pattern verbatim, extended for POST + book-lookup short-circuit)
- `_bmad-output/implementation-artifacts/4-1-rs-post-v1-estimate-endpoint-estimate-service-format-duration-helper.md` (the upstream RS contract Story 4.2 brokers)
- `services/bff/src/bff/services/resource_server_client.py` (the class being extended)
- `services/bff/src/bff/api/books.py` (the file being extended)
- `services/bff/src/bff/api/reading_speed.py` (the proxy-pattern template)

### Project Structure Notes

The four-file edit follows the existing BFF layout (architecture.md §I1 / §"Structural Patterns"):
- Source files mirror tests by path: `src/bff/api/books.py` ↔ `tests/api/test_books.py`; `src/bff/services/resource_server_client.py` ↔ `tests/services/test_resource_server_client.py`.
- One router file per resource family — the estimate endpoint lives on the existing `books` router (it is a books-domain endpoint operating on a book id), not on a new `estimate.py` router; this matches architecture.md's "POST `/v1/books/:id/estimate`" path placement.
- One service module per domain concept — `ResourceServerClient` is the single BFF→RS client; `compute_estimate` belongs on it, not on a new `EstimateClient` (no second-cross-service-client justification).

No deviation from the unified structure. Zero new directories. Zero new top-level packages.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) via `bmad-dev-story`.

### Debug Log References

Date: 2026-05-17.

- After Task 1 source change (`_call_with_refresh` / `_do_rs_call` learn `path`; `get_reading_speed` / `put_reading_speed` updated to pass `path=_READING_SPEED_PATH`):
  - `uv run pytest tests/services/test_resource_server_client.py -q` → **50 passed in 0.37s** (all existing cases green after the no-op generalization).
  - `uv run pytest tests/api/test_reading_speed_proxy.py -q` → **25 passed in 0.27s** (proxy router still green).
- After Task 3 (extend RSC tests with `compute_estimate` cases):
  - `uv run pytest tests/services/test_resource_server_client.py -q` → **71 passed in 0.54s** (50 prior + 21 new compute_estimate cases including 4-status 5xx parametrize + 4-cause transport parametrize + 2-status no-refresh-on-4xx parametrize, plus NFR6 + post-body-shape + kwarg-only signature).
- After Tasks 4–6 (api/books.py: `_resolve_session_row` + proxy helpers + estimate handler):
  - `uv run pytest tests/api/test_books.py -q` → **33 passed** (existing CRUD tests untouched).
  - `uv run python -c "from bff.main import app; …openapi()…"` → `["/v1/books/{book_id}/estimate"]` (route mounted correctly via the existing `/v1` prefix on the books router).
- After Task 7 (extend api tests with 22 estimate cases):
  - `uv run pytest tests/api/test_books.py -v` → **55 passed** (33 prior + 22 new estimate cases including parametrized 5xx + happy / missing / cross-user / no-session / unknown-session / expired / no-csrf / RS 4xx / 5xx / transport / refresh-failure / refresh-replay / refresh-then-401 / NFR6 / owner-pages / non-int-path / empty-body / openapi).
- After Task 8 (coverage):
  - `uv run pytest --cov=bff.api.books --cov=bff.services.resource_server_client --cov-report=term-missing tests/api/test_books.py tests/api/test_reading_speed_proxy.py tests/services/test_resource_server_client.py` →
    - `src/bff/api/books.py`: **96 / 96 = 100%**.
    - `src/bff/services/resource_server_client.py`: **141 / 141 = 100%**.
  - `uv run pytest --cov` → project **97.26%** (1418 / 1458), gate `fail_under=90` satisfied. The remaining ~40 misses live in unrelated long-tail observability / session-service edge cases that pre-date this story.
- After Task 9 (static gates):
  - `uv run ty check` → **All checks passed!**
  - `uv run ruff check` → initial run flagged 5 × E501 (line-length) in `tests/services/test_resource_server_client.py`; `uv run ruff format` autocollapsed and the next `ruff check` returned **All checks passed!** (no hand-fixes were necessary — `ruff format` owns the line wrapping).
  - `uv run ruff format --check` → **81 files already formatted**.
  - `uv run pytest -q` → **541 passed in 9.14s**.

### Completion Notes List

- **Surgical four-file edit, zero new files.** Modified: `services/bff/src/bff/services/resource_server_client.py` (path-thread + `_ESTIMATE_PATH` + POST branch + `compute_estimate`), `services/bff/src/bff/api/books.py` (added `_resolve_session_row`, `_session_terminated_response`, `_resource_server_unavailable_response`, `estimate_for_book` handler + corresponding imports), `services/bff/tests/services/test_resource_server_client.py` (21 new tests for `compute_estimate`), `services/bff/tests/api/test_books.py` (22 new tests for the estimate route). The deliberate inline-copy of the two proxy-response helpers (mirroring `api/reading_speed.py:103-150`) is documented with a single-line comment per the story's Task 5.3 instruction — extraction is deferred until a fourth consumer.
- **`_resolve_session_sub` left untouched** per AC2 / Story 3.5 Dev Notes precedent. `_resolve_session_row` is a parallel helper (12 lines), not a refactor.
- **`_call_with_refresh` extension is purely additive.** The existing 20 RSC tests for `get_reading_speed` / `put_reading_speed` continue to pass after `path` is threaded through both `_call_with_refresh` and `_do_rs_call`. The `method == "POST"` branch was added between the existing `PUT` branch and the `ValueError` else.
- **NFR6 (no `sub` injection) pinned at three layers.** `compute_estimate(pages=…)` builds `body={"pages": pages}` literally; `request.url.path == "/v1/estimate"` + `request.url.params == httpx.QueryParams()` + parsed body equals `{"pages": <book.pages>}` are all asserted at both the service level (`test_compute_estimate_no_sub_in_url_query_or_body`) and the route level (`test_estimate_nfr6_captured_rs_request_shape`).
- **`pages` is keyword-only.** `compute_estimate(db, row, *, pages)` enforces it via the `*` separator; `test_compute_estimate_pages_is_keyword_only` asserts the signature via `inspect.signature`.
- **JSON int (not float / string) pinned.** `test_compute_estimate_post_body_pages_is_int` asserts the wire body parses to `{"pages": 600}`, that `isinstance(parsed["pages"], int)` (with explicit `not isinstance(..., bool)` guard), and that the raw bytes contain neither `"600"` (string) nor `600.0` (float). Note: httpx emits without a space after the JSON colon (`{"pages":600}` vs the spec's `{"pages": 600}`), so the test asserts on parsed shape + byte exclusions rather than byte-exact match.
- **Existence-leak guard pinned.** Two AC10/AC13 tests assert `respx.calls.call_count == 0` for both cross-user-404 and missing-book-404 — the RS is never called when the book lookup short-circuits.
- **No retries on 5xx pinned.** AC8 / AC13 parametrized over 500 / 502 / 503 / 504 + every transport error class — `respx` call count is exactly 1 in every case.
- **Cookie-clearing semantics distinguished.** Refresh-failure path clears both cookies via the existing `_clear_session_cookies` helper (`Max-Age=0`); refresh-worked-but-retry-401 path emits no `Set-Cookie` deletion headers. Both pinned in `tests/api/test_books.py` (cases #15-#17 of AC13).
- **The `≈` (U+2248) character round-trips.** Tests assert via parsed-dict equality (not raw byte matching), which is robust to JSON-encoder differences in how Unicode characters are emitted.
- **Module docstring updated.** Removed the obsolete "Story 3.5 explicitly does NOT pre-stage that method" sentence; added the Story 4.2 references line.
- **No new `ErrorCode` enum members.** Every code emitted by this story (`BOOK_NOT_FOUND`, `SESSION_EXPIRED`, `CSRF_INVALID`, `RESOURCE_SERVER_UNAVAILABLE`) already exists. RS-emitted codes (`reading_speed_unset`, `forbidden_scope`, `invalid_input`) flow through as `JSONResponse(content=body)` and never enter the BFF's `AppException` machinery.
- **No deferred items.** All ACs satisfied; no D-numbered defers created. The architectural consolidation of `_resolve_session_sub` / `_resolve_session_row` was already a pre-existing deferred item (Story 3.5 Dev Notes "after a fourth consumer arrives") and remains deferred.

### File List

- **MODIFIED** `services/bff/src/bff/services/resource_server_client.py`
  - Added `_ESTIMATE_PATH = "/v1/estimate"` constant.
  - Generalized `_do_rs_call(method, access_token, body)` → `_do_rs_call(method, path, access_token, body)`; URL now `<rs_base_url> + path`. Added `method == "POST"` branch.
  - Generalized `_call_with_refresh(*, method, body)` → `_call_with_refresh(*, method, path, body)`; threaded `path` through both attempts.
  - Updated `get_reading_speed` / `put_reading_speed` to pass `path=_READING_SPEED_PATH` (no observable change).
  - Added public `compute_estimate(db, session_row, *, pages: int) -> tuple[int, dict[str, Any] | None]`.
  - Module docstring: removed Story 3.5 "explicitly does NOT pre-stage" sentence; added Story 4.2 reference.
- **MODIFIED** `services/bff/src/bff/api/books.py`
  - Added imports: `JSONResponse`, `SessionRow`, `RsSessionTerminated`, `RsUnavailable`, `resource_server_client`.
  - Added `_resolve_session_row(request, db, cfg) -> SessionRow` (parallel to `_resolve_session_sub`; `_resolve_session_sub` unchanged).
  - Added `_session_terminated_response(cfg, *, clear_cookies)` and `_resource_server_unavailable_response()` (inline copies of `api/reading_speed.py:103-150`, documented as deliberate duplication).
  - Added `@router.post("/{book_id}/estimate")` handler `estimate_for_book` (session row → book lookup → `compute_estimate` → forward verbatim / 401-cookie-clear / 503).
- **MODIFIED** `services/bff/tests/services/test_resource_server_client.py`
  - Added `_RS_ESTIMATE_URL` constant.
  - Added 21 tests for `compute_estimate`: happy 200; 4xx forwarding (412 / 403 / 422); parametrized 5xx (500 / 502 / 503 / 504); parametrized transport errors (4); refresh-replay happy; refresh-failure → `RsSessionTerminated(clear_cookies=True)` + row deleted; refresh-succeeded-retry-401 → `RsSessionTerminated(clear_cookies=False)` + row preserved; NFR6 URL / query / body / Authorization invariants; POST body is JSON int (not float / string); `pages` kwarg-only signature; parametrized no-refresh-on-4xx; no-refresh-on-5xx.
- **MODIFIED** `services/bff/tests/api/test_books.py`
  - Added imports: `httpx`, `pytest`, `respx`, `bff.core.config.settings`, `SessionRow`.
  - Added `_RS_BASE_URL` / `_RS_ESTIMATE_URL` constants, `rs_settings` monkeypatch fixture, `_seed_session_row` helper (deterministic session id for cookie-driven tests).
  - Added 22 route-level tests for `POST /v1/books/{id}/estimate`: happy 200; missing-book-404 + cross-user-404 (both `respx.call_count == 0`); 401 paths (missing cookie, unknown id, expired row); CSRF 403; RS 4xx forwarding (412 / 403 / 422); parametrized RS 5xx (500 / 503); ConnectError + ReadTimeout; refresh-failure with both cookies cleared and session deleted; refresh-replay happy; refresh-worked-but-retry-401 (no cookie clear, row preserved); NFR6 captured-request shape; owner-pages-not-other-users; non-int book_id → 422; empty-body POST succeeds with book.pages forwarded; OpenAPI lists the new path.
- **MODIFIED** `_bmad-output/implementation-artifacts/sprint-status.yaml`
  - `development_status.4-2-...` flipped `ready-for-dev` → `in-progress` (start of session) → `review` (end of session).
  - `last_updated` line refreshed with the in-progress + review-handoff notes.

## Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-17 | Initial implementation per story spec. RSC: `_call_with_refresh` / `_do_rs_call` generalized over `path`; added `_ESTIMATE_PATH` + `method == "POST"` branch + public `compute_estimate`. `api/books.py`: added `_resolve_session_row` + inline proxy-response helpers + `POST /{book_id}/estimate` handler. Tests: 21 new RSC cases + 22 new route cases. All four gates (ruff check / ruff format --check / ty check / pytest) green; coverage at 100% per-file + 97.26% project. Status → review. | Claude Opus 4.7 (bmad-dev-story) |
