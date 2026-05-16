---
status: ready-for-dev
story_key: 2-2-bff-full-books-crud-v1-books-v1-books-id
created: 2026-05-16
---

# Story 2.2: BFF — full books CRUD (`/v1/books` + `/v1/books/{id}`)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a signed-in user (via the SPA),
I want full CRUD endpoints at `/v1/books` and `/v1/books/{id}` scoped strictly to my own books by `sub`,
so that I can manage my personal book list without ever seeing or being able to access another user's books.

## Scope (read this first)

This story turns the persistence + boundary-model layer Story 2.1 set up into a working HTTP surface. The end-state of this story is **five route handlers** (LIST / CREATE / READ / UPDATE / DELETE) under a single `APIRouter` at `/v1/books`, backed by a `BooksService` that owns DB access, with strict per-`sub` ownership isolation and the project's standard error envelope on every failure path.

What you build:

1. **`src/bff/api/books.py`** — new module exposing a single `APIRouter` mounted under `/v1` (so the full paths are `/v1/books` and `/v1/books/{id}`). Five handlers: `list_books`, `create_book`, `read_book`, `update_book`, `delete_book`. Each handler extracts the session's `sub` from the cookie, delegates to `BooksService`, and returns either a `BookOut` / `list[BookOut]` / empty 204 OR raises `AppException(ErrorCode.<...>)`.
2. **`src/bff/services/books_service.py`** — new module declaring `class BooksService:` with async methods `list_for_user`, `get_for_user`, `create`, `update`, `delete`. Mirrors the shape of `bff/services/session_service.py` (class with async methods, module-level singleton `_books_service` instantiated by the route module).
3. **`src/bff/core/errors.py`** — UPDATE: add `BOOK_NOT_FOUND` and `INVALID_INPUT` to the `ErrorCode` enum (per AR17 / C5). Update `validation_exception_handler` to emit the `INVALID_INPUT` wire code instead of the legacy `VALIDATION_ERROR`.
4. **`src/bff/api/v1/__init__.py`** — UPDATE: import the new books router and include it on `v1_router`. Currently the file just declares `router = APIRouter(prefix="/v1")` and nothing is attached.
5. **`tests/api/test_books.py`** — new file covering all five endpoints across happy / 401 / 403 / 404 / 422 paths AND cross-user isolation.
6. **`tests/services/test_books_service.py`** — new file covering each service method's happy and edge paths against the in-memory SQLite fixture.
7. **`tests/core/test_errors.py`** — UPDATE: one existing test (`test_validation_error_via_http` line 78–87) flips from asserting `"VALIDATION_ERROR"` to asserting `"invalid_input"`. Add two new enum-shape tests for `BOOK_NOT_FOUND` and `INVALID_INPUT`.

**Out of scope — DO NOT do these here:**

- **No SPA work.** Stories 2.4 / 2.5 / 2.6 own the SPA-side `BooksService`, components, and optimistic UI. This story is BFF-only.
- **No Playwright E2E spec.** Story 2.7 authors `j2-manage-books.spec.ts`.
- **No `/v1/test/reset` changes.** Story 2.3 (also `ready-for-dev`) extends the reset endpoint to truncate `books`; that diff is independent of this story's surface and 2.3 + 2.2 are mergeable in either order.
- **No `/v1/books/{id}/estimate` endpoint.** Story 4.2 adds the estimate forwarder. This story stops at the five CRUD verbs.
- **No book search, pagination, sorting beyond `created_at ASC`, or filtering.** Architecture §C8 line 420 explicitly defers these.
- **No new auth surface.** Reuse the existing cookie-session + CSRF middleware from Stories 1.5 + 1.6. Do NOT introduce a new `Depends(...)` shape if the existing `me.py`-style cookie-read works.
- **No schema changes.** Story 2.1's `0002_add_books` migration is sufficient. No new Alembic revision is created here.
- **No new dependencies** in `pyproject.toml`.

**Strict dependency:** Story 2.1 (`Book` SQLModel + Pydantic boundary models + Alembic `0002_add_books`) must be `done` before this story can pass tests. The first task is a precondition check; if 2.1 has not landed, **STOP**.

## Acceptance Criteria

**AC1 — Route surface mounted at `/v1/books`.**

A new file `services/bff/src/bff/api/books.py` exports:

```python
router = APIRouter(prefix="/v1/books", tags=["Books"])
```

The router is wired into the project by extending `services/bff/src/bff/api/v1/__init__.py` to include it:

```python
from fastapi import APIRouter
from bff.api.books import router as books_router

router = APIRouter(prefix="/v1")
router.include_router(books_router)
```

This is the ONLY edit to `v1/__init__.py`. `bff/main.py` already calls `app.include_router(v1_router)` at line 65 (Story 1.12 Dev Notes) — nothing in `main.py` changes for this story.

**Implementation alternative — acceptable but not required:** declare `router = APIRouter(prefix="/books", tags=["Books"])` in `books.py` (no `/v1/` prefix) and let `v1_router` add the `/v1` segment via its existing `APIRouter(prefix="/v1")`. Either approach yields the same final mount points. Pick one; document the choice in the File List.

**AC2 — Five handlers exist on the books router.**

Each handler declares its parameters via `Annotated[..., Depends(...)]` (consistent with `api/me.py:54` and `api/test_reset.py:198–200`). Order of params: `request: Request`, `db: Annotated[AsyncSession, Depends(get_session)]`, `cfg: Annotated[AppSettings, Depends(_settings_dep)]`, plus any path/body params.

| Handler | Method + Path | Body model | Response model | Success status |
|---|---|---|---|---|
| `list_books` | `GET /v1/books` | — | `list[BookOut]` | 200 |
| `create_book` | `POST /v1/books` | `BookCreate` | `BookOut` | 201 (+ `Location` header) |
| `read_book` | `GET /v1/books/{book_id}` | — | `BookOut` | 200 |
| `update_book` | `PATCH /v1/books/{book_id}` | `BookUpdate` | `BookOut` | 200 |
| `delete_book` | `DELETE /v1/books/{book_id}` | — | — | 204 (empty body) |

Path param: `book_id: int`. FastAPI's automatic int coercion handles non-int paths — they return Pydantic's default 422 envelope (which now reads `invalid_input` per AC8) without reaching the handler.

**AC3 — Every handler validates the session cookie BEFORE doing any work.**

The session-extraction pattern is duplicated from `api/me.py:51–80` because there is no shared "get current sub" dependency in the codebase. Extract a private helper `_resolve_session_sub` in `books.py` (or place it on the module) and call it at the top of every handler:

```python
async def _resolve_session_sub(
    request: Request,
    db: AsyncSession,
    cfg: AppSettings,
) -> str:
    """Return `sub` for a valid session cookie; raise AppException(SESSION_EXPIRED)
    if the cookie is missing, the session id is unknown, or the session is expired.

    Expired sessions are lazy-deleted as a side effect (mirrors api/me.py:67).
    """
    session_id = request.cookies.get(cfg.bff_session_cookie_name)
    if not session_id:
        raise AppException(ErrorCode.SESSION_EXPIRED)
    row = await _session_service.get_session(db, session_id=session_id)
    if row is None:
        raise AppException(ErrorCode.SESSION_EXPIRED)
    if _as_utc_aware(row.expires_at) < datetime.now(UTC):
        await _session_service.delete_expired_session(db, session_id=session_id)
        raise AppException(ErrorCode.SESSION_EXPIRED)
    return row.sub
```

- Use the same `_as_utc_aware` helper shape (3 lines) from `me.py:47`. Copy verbatim — DO NOT import from `me.py` (that creates a circular dep risk and the helper is intentionally cheap).
- `_session_service` is a module-level singleton: `_session_service = SessionService()` (mirrors `me.py:29`).
- Raising `AppException(ErrorCode.SESSION_EXPIRED)` flows through `app_exception_handler` (errors.py:48–55) to produce the 401 envelope `{"errorCode": "session_expired", "message": "Session expired or not present", "detail": null}` — matching what `me.py` returns via `_session_expired_response()`. DO NOT inline a `JSONResponse(...)` — go through `AppException` so the handler can return its declared `BookOut` / `list[BookOut]` response model.

**AC4 — `list_books` (GET /v1/books).**

- Returns 200 with a **plain JSON array** of `BookOut` objects (no envelope, no `{items: [...]}` wrapper) — per architecture §AR16 line 73 and architecture line 668 ("collections return a plain JSON array").
- Body order: `created_at` ascending (insertion order per UX-DR5 default). Service-layer query: `select(entities.Book).where(entities.Book.sub == sub).order_by(entities.Book.created_at.asc())`.
- Only books where `books.sub == <session.sub>` are returned. Books owned by other users are NEVER included.
- Empty list returns `200 []` (NOT 204; NOT 404).

**AC5 — `create_book` (POST /v1/books).**

- Body is parsed as `BookCreate`. Invalid input → 422 with envelope `{"errorCode": "invalid_input", "message": "Invalid input", "detail": <list of pydantic errors with `input` field stripped>}` (the `validation_exception_handler` already strips `input` per the Story 1.3 Patch P3).
- On valid input, the service inserts `entities.Book(sub=<session sub>, title=payload.title, pages=payload.pages, status=payload.status)`. `id`, `created_at`, `updated_at` auto-populate from the SQLModel defaults (per Story 2.1 AC1).
- Response: 201 with the created `BookOut` as the body.
- Response header: `Location: /v1/books/{id}` (per architecture line 679; format described at AR16). Set via `response.headers["Location"] = f"/v1/books/{book.id}"` — inject the FastAPI `Response` object as a handler parameter (`response: Response`) and mutate `headers` directly. Do NOT use `JSONResponse` — let FastAPI handle serialization via the declared `response_model=BookOut, status_code=201`, and add the header through the injected response.

**AC6 — `read_book` (GET /v1/books/{book_id}).**

- Service-layer lookup: `select(entities.Book).where(entities.Book.id == book_id).where(entities.Book.sub == sub)`. The two predicates compose so that:
  - **Non-existent id** → 404 `book_not_found`.
  - **Existing id owned by another `sub`** → 404 `book_not_found` (NOT 403, NOT 401). This is the cross-user-isolation contract from the epic spec lines 819–821 — existence is not leaked across users.
- The handler raises `AppException(ErrorCode.BOOK_NOT_FOUND)` for both cases.
- Owned-by-current-`sub` happy path → 200 with the `BookOut`.

**AC7 — `update_book` (PATCH /v1/books/{book_id}).**

- Body parsed as `BookUpdate`. **Partial semantics:** any subset of `{title, pages, status}` is acceptable. An empty body (`{}`) MUST 200 with the book unchanged — `BookUpdate()` is valid per Story 2.1 AC3 ("all three fields optional; the model itself does NOT require 'at least one field present'").
- Invalid input (e.g. `pages=0`, unknown status, empty/whitespace title) → 422 `invalid_input`. The Pydantic validators on `BookUpdate` (Story 2.1 AC3) handle this automatically.
- Non-existent OR other-`sub` book → 404 `book_not_found` (same as AC6).
- Happy path: the service performs `model_dump(exclude_unset=True)` on the payload, updates only the fields actually present in the request, commits, and refreshes. SQLModel's `onupdate` factory on `updated_at` (Story 2.1 AC1) advances the timestamp automatically.
- Response: 200 with the updated `BookOut`. Owned columns NOT in the payload remain unchanged.

**AC8 — `delete_book` (DELETE /v1/books/{book_id}).**

- Non-existent OR other-`sub` book → 404 `book_not_found`.
- Happy path: row is deleted; response is **204 No Content with NO body**. Use the `fastapi.Response(status_code=204)` idiom from Story 1.7 / 1.12 — do NOT return `None` (FastAPI emits `null` body) and do NOT return a `JSONResponse({})` (emits `{}`). The literal `Response(status_code=204)` is the project convention.

**AC9 — CSRF + session cookie are enforced on state-changing methods.**

The existing `CsrfMiddleware` (Story 1.6) already enforces double-submit cookie + `X-CSRF-Token` header + same-origin `Origin`/`Referer` on every non-safe method (POST/PUT/PATCH/DELETE) for every path NOT in `_CSRF_EXEMPT_PATHS`. The books endpoints are NOT in the exempt set; CSRF flows in automatically. No middleware change is needed.

- Missing CSRF header on POST/PATCH/DELETE → 403 `csrf_invalid` (the middleware emits the envelope BEFORE the handler runs).
- Missing session cookie OR expired session → 401 `session_expired` (the handler emits this via `_resolve_session_sub`).
- The order of checks (CSRF middleware before handler) means: a state-changing request without CSRF gets 403, never 401, even if the session is also missing. This is the existing project contract; tests must match.

**AC10 — `ErrorCode` enum gains `BOOK_NOT_FOUND` and `INVALID_INPUT`.**

`services/bff/src/bff/core/errors.py` is updated:

```python
class ErrorCode(enum.Enum):
    INTERNAL_ERROR = ("INTERNAL_ERROR", "An unexpected error occurred", 500)
    VALIDATION_ERROR = ("VALIDATION_ERROR", "Request validation failed", 422)  # legacy — kept for API symmetry; no longer emitted on wire
    BAD_REQUEST = ("BAD_REQUEST", "Bad request", 400)
    NOT_FOUND = ("NOT_FOUND", "Resource not found", 404)
    UNAUTHORIZED = ("UNAUTHORIZED", "Authentication required", 401)
    FORBIDDEN = ("FORBIDDEN", "Access forbidden", 403)
    # Project-specific lower_snake_case wire codes (architecture §C5 + AR17).
    SESSION_EXPIRED = ("session_expired", "Session expired or not present", 401)
    SERVICE_UNAVAILABLE = ("service_unavailable", "A required dependency is unavailable", 503)
    AUTH_STATE_INVALID = ("auth_state_invalid", "Authorization state invalid", 400)
    CSRF_INVALID = ("csrf_invalid", "CSRF token missing or invalid", 403)
    BOOK_NOT_FOUND = ("book_not_found", "Book not found", 404)
    INVALID_INPUT = ("invalid_input", "Invalid input", 422)
```

The new members go alphabetically-ish after the existing project-specific block — keep `BOOK_NOT_FOUND` near `AUTH_STATE_INVALID` / `CSRF_INVALID` to reinforce the "project-specific lower_snake" group; place `INVALID_INPUT` immediately after, ahead of any future additions.

**AC11 — `validation_exception_handler` emits `invalid_input` on the wire.**

`errors.py` lines 58–76 currently emit `ErrorCode.VALIDATION_ERROR` (upper_snake `"VALIDATION_ERROR"`). Update the handler to use `ErrorCode.INVALID_INPUT` instead:

```python
async def validation_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    val_exc = cast(RequestValidationError, exc)
    sanitized = [
        {k: v for k, v in err.items() if k != "input"} for err in val_exc.errors()
    ]
    return JSONResponse(
        status_code=ErrorCode.INVALID_INPUT.http_status,
        content=build_error_body(
            ErrorCode.INVALID_INPUT.code,
            ErrorCode.INVALID_INPUT.message,
            sanitized,
        ),
    )
```

The `VALIDATION_ERROR` enum member STAYS — it's still part of the archetype-default surface and is read by `test_error_code_validation_error` (test_errors.py:16–18). No code is emitting it on the wire after this change; it lives in the enum as legacy. (A future cleanup story may remove it; that is NOT this story's call.)

**The `input`-stripping behavior (Story 1.3 Patch P3) is preserved verbatim** — only the wire code and message change. Do NOT remove the `sanitized` list comprehension.

**AC12 — `tests/core/test_errors.py` is updated for the new enum members and wire code.**

The existing test file at `services/bff/tests/core/test_errors.py` is updated:

- Line 85: change `assert data["errorCode"] == "VALIDATION_ERROR"` → `assert data["errorCode"] == "invalid_input"`.
- Line 86: change `assert data["message"] == "Request validation failed"` → `assert data["message"] == "Invalid input"`.
- Add two new tests `test_error_code_book_not_found` and `test_error_code_invalid_input` mirroring the shape of `test_csrf_invalid_enum_shape` at lines 43–48:
  ```python
  def test_error_code_book_not_found() -> None:
      assert ErrorCode.BOOK_NOT_FOUND.code == "book_not_found"
      assert ErrorCode.BOOK_NOT_FOUND.message == "Book not found"
      assert ErrorCode.BOOK_NOT_FOUND.http_status == 404


  def test_error_code_invalid_input() -> None:
      assert ErrorCode.INVALID_INPUT.code == "invalid_input"
      assert ErrorCode.INVALID_INPUT.message == "Invalid input"
      assert ErrorCode.INVALID_INPUT.http_status == 422
  ```
- The existing `test_error_code_validation_error` (lines 16–18) STAYS unchanged — `VALIDATION_ERROR` remains in the enum.

**AC13 — `BooksService` exposes five async methods.**

`services/bff/src/bff/services/books_service.py` declares a single class:

```python
class BooksService:
    async def list_for_user(
        self, db: AsyncSession, *, sub: str
    ) -> list[entities.Book]: ...

    async def get_for_user(
        self, db: AsyncSession, *, sub: str, book_id: int
    ) -> entities.Book | None: ...

    async def create(
        self, db: AsyncSession, *, sub: str, payload: BookCreate
    ) -> entities.Book: ...

    async def update(
        self, db: AsyncSession, *, sub: str, book_id: int, payload: BookUpdate
    ) -> entities.Book | None: ...

    async def delete(
        self, db: AsyncSession, *, sub: str, book_id: int
    ) -> bool: ...
```

Method-by-method behavior:

- **`list_for_user`** — `select(entities.Book).where(entities.Book.sub == sub).order_by(entities.Book.created_at.asc())`. Returns the (possibly empty) list of rows.
- **`get_for_user`** — `select(entities.Book).where(entities.Book.id == book_id).where(entities.Book.sub == sub)`. Returns the row or `None`. **The `sub` predicate MUST be part of the SQL query** — never fetch by `id` only and then check `row.sub` in Python (subtle race + readability + log-of-existence-leak risk).
- **`create`** — instantiates `entities.Book(sub=sub, title=payload.title, pages=payload.pages, status=payload.status)`, `db.add(...)`, `await db.commit()`, `await db.refresh(book)`, returns the persisted row.
- **`update`** — first call `get_for_user(...)` to fetch the row. If `None`, return `None` (handler translates to 404). Otherwise apply `payload.model_dump(exclude_unset=True)` to mutate fields, `await db.commit()`, `await db.refresh(book)`, return the row. The `model_dump(exclude_unset=True)` is the load-bearing detail — without it, an explicit `null` in the body (e.g., `{"title": null}`) would clobber the title. With `exclude_unset=True`, only fields actually present in the JSON are mutated.
- **`delete`** — first call `get_for_user(...)`. If `None`, return `False`. Otherwise `await db.delete(row)`, `await db.commit()`, return `True`. Handler translates the bool to 204 vs 404.

All methods declare `*` to make `sub`, `book_id`, `payload` keyword-only (mirrors `SessionService.get_session` shape).

No `_INSERT_RETRY_LIMIT` retry loop is needed — `entities.Book.id` is `int | None` with autoincrement, so PK collisions are impossible (unlike `Session.id` which is a token-urlsafe string).

The handler logs `book_created sub=<truncated 8> id=<book_id>` at INFO on create (mirroring `session_service.py:169`). On delete: `book_deleted sub=<truncated 8> id=<book_id>`. On update: nothing (the field-level changes are not security-sensitive and adding a log line per PATCH would noise up the journey). Cross-user 404s do NOT log — silent rejection per the existence-non-leak contract.

**AC14 — Tests at `tests/api/test_books.py` cover the full route surface.**

Test file location: `services/bff/tests/api/test_books.py` (matches the `tests/<mirror>/test_<module>.py` convention from architecture line 615 + 938).

Required scenarios (use `client_with_csrf` + the existing seed helpers from `tests/api/test_me.py::_seed_session` adapted as needed):

**Authentication (applies to every endpoint):**

1. `GET/POST/PATCH/DELETE /v1/books[/:id]` with NO session cookie → 401 `session_expired`. (For POST/PATCH/DELETE, the test must include valid CSRF material — `client_with_csrf` — so the request reaches the session check; otherwise CSRF middleware short-circuits with 403 first per AC9 + scenario 8.)
2. With a session cookie pointing at a non-existent `sessions.id` → 401 `session_expired`.
3. With a session cookie pointing at an expired `sessions` row → 401 `session_expired`; the expired row is deleted as a side effect (assert via `session_service.get_session(...)` post-call).

**CSRF (applies to POST / PATCH / DELETE):**

4. POST `/v1/books` without `X-CSRF-Token` header → 403 `csrf_invalid`. No DB writes.
5. PATCH `/v1/books/1` without CSRF cookie/header → 403 `csrf_invalid`.
6. DELETE `/v1/books/1` without CSRF cookie/header → 403 `csrf_invalid`.

**LIST happy + isolation:**

7. Authenticated user with 3 own books + 2 books owned by a different `sub` → GET `/v1/books` returns 200, body is an array of exactly 3 items, sorted `created_at ASC`, none of the 3 has `sub` field in the response (per Story 2.1 AC3 `BookOut` excludes `sub`).
8. Authenticated user with 0 books → GET returns 200 with `[]` (NOT 204; NOT 404).

**CREATE happy + error paths:**

9. POST with `{"title": "Dune", "pages": 688, "status": "reading"}` → 201; body is the new `BookOut`; `Location` header is `/v1/books/{new_id}`; DB row exists with `sub == session.sub`.
10. POST with `{"title": "Dune", "pages": 688}` (status omitted) → 201; persisted row has `status="to-read"` (default per Story 2.1 AC1 + AC3).
11. POST with empty body → 422 `invalid_input` (Pydantic flags missing `title` + `pages`).
12. POST with `{"title": "", "pages": 100}` → 422 `invalid_input`.
13. POST with `{"title": "   ", "pages": 100}` → 422 `invalid_input` (Story 2.1's strip-and-reject validator).
14. POST with `{"title": "Dune", "pages": 0}` → 422 `invalid_input`.
15. POST with `{"title": "Dune", "pages": 100, "status": "archived"}` → 422 `invalid_input`.

**READ happy + isolation:**

16. GET `/v1/books/{owned_id}` → 200 with the `BookOut`.
17. GET `/v1/books/99999` (non-existent) → 404 `book_not_found`.
18. GET `/v1/books/{other_users_id}` (exists, owned by different `sub`) → 404 `book_not_found` (NOT 403). Use two distinct seeded sessions to construct this case.
19. GET `/v1/books/not-an-int` → 422 `invalid_input` (FastAPI's path-coercion failure flows through `validation_exception_handler`).

**UPDATE happy + edge:**

20. PATCH with `{"status": "finished"}` → 200; only `status` changed; title and pages unchanged; `updated_at` strictly later than `created_at` (or strictly later than the pre-patch `updated_at`).
21. PATCH with `{}` (empty body) → 200; row unchanged. (Confirms Story 2.1's "empty patch is OK at the model level" semantics.)
22. PATCH with `{"pages": 0}` → 422 `invalid_input`; row unchanged in DB (re-fetch and assert).
23. PATCH with `{"status": "archived"}` → 422 `invalid_input`; row unchanged.
24. PATCH `/v1/books/99999` (non-existent) → 404 `book_not_found`.
25. PATCH `/v1/books/{other_users_id}` → 404 `book_not_found`. Re-fetch and assert the other user's row is unchanged.

**DELETE happy + edge:**

26. DELETE `/v1/books/{owned_id}` → 204; response.content == b"" (NO body); DB row gone (`get_for_user` returns None post-call).
27. DELETE `/v1/books/99999` → 404 `book_not_found`.
28. DELETE `/v1/books/{other_users_id}` → 404 `book_not_found`; the other user's row is still present in DB.

**Two-distinct-sessions cross-user matrix (per epic spec line 850):**

29. Seed two sessions (sub `A` with 2 books, sub `B` with 3 books). With session `A`'s cookie: GET `/v1/books` returns 2 items, GET `/v1/books/{B's book id}` returns 404, PATCH/DELETE on `B`'s ids → 404. With session `B`'s cookie: GET returns 3 items, GET on `A`'s id returns 404. Re-list after both clients run — both lists unchanged in size and content.

**AC15 — Tests at `tests/services/test_books_service.py` cover the service contract.**

Test file location: `services/bff/tests/services/test_books_service.py`. Uses the `session` fixture directly (no HTTP client) — service-layer tests bypass the route entirely. Mirrors the pattern of `services/bff/tests/services/test_session_service.py`. Required scenarios:

- `test_list_for_user_returns_empty_for_unknown_sub` — service returns `[]` for a sub with no books.
- `test_list_for_user_returns_only_own_books_ordered_by_created_at` — seed books with explicit `created_at` set via construction (set `created_at` to known increasing datetimes; SQLModel allows this since `default_factory` only fires when unset); assert returned list is ordered.
- `test_list_for_user_excludes_other_users_books` — seed 2 books for sub `A`, 3 for sub `B`; `list_for_user(sub="A")` returns 2; `list_for_user(sub="B")` returns 3.
- `test_get_for_user_returns_row_for_owner` / `test_get_for_user_returns_none_for_unknown_id` / `test_get_for_user_returns_none_for_other_user_id`.
- `test_create_persists_row_with_session_sub` — pass `sub="alice"` to `create(...)`, assert `book.sub == "alice"` in the returned row AND after re-fetch.
- `test_create_uses_default_status_when_payload_omits_it` — verify default.
- `test_update_applies_partial_payload` — confirm `model_dump(exclude_unset=True)` semantics.
- `test_update_returns_none_for_unknown_id` / `test_update_returns_none_for_other_user_id`.
- `test_update_advances_updated_at` — assert post-update `updated_at` is strictly later than pre-update (use `asyncio.sleep(0.01)` between).
- `test_delete_returns_true_when_deleted` / `test_delete_returns_false_for_unknown_id` / `test_delete_returns_false_for_other_user_id`.
- `test_delete_actually_removes_row` — post-delete, `get_for_user` returns `None`.

**AC16 — Coverage and lint gates remain green.**

From `services/bff/`:

- `uv sync --frozen` → exit 0 (no dep changes).
- `uv run ruff check` → clean.
- `uv run ruff format --check` → clean.
- `uv run ty check` → clean.
- `uv run pytest --cov` → all prior tests + new tests pass; total project coverage ≥ 90% (gate per `pyproject.toml:86`).
- Per-module coverage ≥90% on `src/bff/api/books.py` and `src/bff/services/books_service.py` (epic line 851).
- Suite size grows by approximately 40+ tests (29 route scenarios + 13+ service-layer scenarios + 2 new enum-shape tests + 1 updated test). The post-2.1 baseline is ~360 tests; this story lands ~400.

## Tasks / Subtasks

- [ ] **Task 1 — Verify Story 2.1 has landed (precondition check, AC16)**
  - [ ] From `services/bff/`: run `uv run python -c "from bff.models import entities; from bff.api.schemas.book import BookCreate, BookUpdate, BookOut; print('ok')"`. If this `ImportError`s, **STOP** — Story 2.1 has not been merged.
  - [ ] Confirm Alembic head: `uv run alembic heads` MUST report `0002_add_books`.
  - [ ] Confirm SQLModel registration: `uv run python -c "from bff.models.entities import Book; print(Book.__tablename__)"` → prints `books`.

- [ ] **Task 2 — Extend `ErrorCode` enum + update validation handler (AC10, AC11)**
  - [ ] Edit `services/bff/src/bff/core/errors.py`: add `BOOK_NOT_FOUND = ("book_not_found", "Book not found", 404)` and `INVALID_INPUT = ("invalid_input", "Invalid input", 422)` to the project-specific block (lines 20–27 in the current file).
  - [ ] Update `validation_exception_handler` (lines 58–76) to reference `ErrorCode.INVALID_INPUT` in three spots: `status_code`, the first arg to `build_error_body`, and the second arg (message). The `sanitized` list comprehension and the `input`-stripping behavior STAY exactly as-is.
  - [ ] Add an inline comment on `VALIDATION_ERROR` (line 11) noting it is now legacy / not emitted on the wire but kept for enum-surface stability:
    ```python
    VALIDATION_ERROR = ("VALIDATION_ERROR", "Request validation failed", 422)  # legacy: validation_exception_handler now emits INVALID_INPUT (Story 2.2)
    ```

- [ ] **Task 3 — Update `tests/core/test_errors.py` for the new wire contract (AC12)**
  - [ ] Edit `services/bff/tests/core/test_errors.py` line 85: change to `assert data["errorCode"] == "invalid_input"`.
  - [ ] Edit line 86: change to `assert data["message"] == "Invalid input"`.
  - [ ] Append the two new enum-shape tests `test_error_code_book_not_found` + `test_error_code_invalid_input` after `test_csrf_invalid_enum_shape` (line 48).
  - [ ] Run `uv run pytest tests/core/test_errors.py -v` → all tests pass.

- [ ] **Task 4 — Author `BooksService` at `src/bff/services/books_service.py` (AC13)**
  - [ ] Create `services/bff/src/bff/services/books_service.py`. Mirror the imports + module structure of `session_service.py`:
    ```python
    import logging
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlmodel import select

    from bff.api.schemas.book import BookCreate, BookUpdate
    from bff.models import entities

    logger = logging.getLogger(__name__)
    ```
  - [ ] Declare `class BooksService:` with the five async methods per AC13. Use `select(entities.Book)...` queries from `sqlmodel.select` (matches the existing `session_service.py:188`).
  - [ ] On `create`: log `book_created sub=<8-char prefix>... id=<book.id>` at INFO. On `delete` (when actually deleting): log `book_deleted sub=<8-char prefix>... id=<book.id>` at INFO. Mirror the truncation idiom from `session_service.py:235–238` — use `... if len(sub) > 8 else ""` to avoid emitting a misleading `...` for short ids (Story 1.7 Review Findings caught this for session ids; the same lesson applies here).
  - [ ] **Do NOT add a `_safe_sub_log` helper to this file** — keep the truncation inline. The cross-module helper extraction (auth.py / test_reset.py both have local copies of `_safe_session_id_log`) is a known D-item; do not add a third copy or hoist now.

- [ ] **Task 5 — Author route handlers at `src/bff/api/books.py` (AC1–AC9)**
  - [ ] Create `services/bff/src/bff/api/books.py`. Imports follow `api/me.py` and `api/test_reset.py` conventions:
    ```python
    from datetime import UTC, datetime
    from typing import Annotated

    from fastapi import APIRouter, Depends, Request, Response, status
    from sqlalchemy.ext.asyncio import AsyncSession

    from bff.api.schemas.book import BookCreate, BookOut, BookUpdate
    from bff.core.config import AppSettings, settings
    from bff.core.database import get_session
    from bff.core.errors import AppException, ErrorCode
    from bff.services.books_service import BooksService
    from bff.services.session_service import SessionService
    ```
  - [ ] Module-level singletons mirroring `me.py:29`:
    ```python
    router = APIRouter(prefix="/v1/books", tags=["Books"])
    _session_service = SessionService()
    _books_service = BooksService()


    def _settings_dep() -> AppSettings:
        return settings


    def _as_utc_aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    ```
  - [ ] Implement `_resolve_session_sub` per AC3 — exact shape provided in the AC. Raise `AppException(ErrorCode.SESSION_EXPIRED)` rather than returning a `JSONResponse`.
  - [ ] Implement the five handlers. Signatures and decorators:
    ```python
    @router.get("", response_model=list[BookOut])
    async def list_books(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_session)],
        cfg: Annotated[AppSettings, Depends(_settings_dep)],
    ) -> list[BookOut]:
        sub = await _resolve_session_sub(request, db, cfg)
        rows = await _books_service.list_for_user(db, sub=sub)
        return [BookOut.model_validate(r) for r in rows]


    @router.post("", response_model=BookOut, status_code=status.HTTP_201_CREATED)
    async def create_book(
        request: Request,
        response: Response,
        payload: BookCreate,
        db: Annotated[AsyncSession, Depends(get_session)],
        cfg: Annotated[AppSettings, Depends(_settings_dep)],
    ) -> BookOut:
        sub = await _resolve_session_sub(request, db, cfg)
        book = await _books_service.create(db, sub=sub, payload=payload)
        response.headers["Location"] = f"/v1/books/{book.id}"
        return BookOut.model_validate(book)


    @router.get("/{book_id}", response_model=BookOut)
    async def read_book(
        request: Request,
        book_id: int,
        db: Annotated[AsyncSession, Depends(get_session)],
        cfg: Annotated[AppSettings, Depends(_settings_dep)],
    ) -> BookOut:
        sub = await _resolve_session_sub(request, db, cfg)
        book = await _books_service.get_for_user(db, sub=sub, book_id=book_id)
        if book is None:
            raise AppException(ErrorCode.BOOK_NOT_FOUND)
        return BookOut.model_validate(book)


    @router.patch("/{book_id}", response_model=BookOut)
    async def update_book(
        request: Request,
        book_id: int,
        payload: BookUpdate,
        db: Annotated[AsyncSession, Depends(get_session)],
        cfg: Annotated[AppSettings, Depends(_settings_dep)],
    ) -> BookOut:
        sub = await _resolve_session_sub(request, db, cfg)
        book = await _books_service.update(db, sub=sub, book_id=book_id, payload=payload)
        if book is None:
            raise AppException(ErrorCode.BOOK_NOT_FOUND)
        return BookOut.model_validate(book)


    @router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_book(
        request: Request,
        book_id: int,
        db: Annotated[AsyncSession, Depends(get_session)],
        cfg: Annotated[AppSettings, Depends(_settings_dep)],
    ) -> Response:
        sub = await _resolve_session_sub(request, db, cfg)
        deleted = await _books_service.delete(db, sub=sub, book_id=book_id)
        if not deleted:
            raise AppException(ErrorCode.BOOK_NOT_FOUND)
        return Response(status_code=204)
    ```
  - [ ] Module-level `__all__ = ["router"]` so the import in `v1/__init__.py` is explicit.

- [ ] **Task 6 — Wire the router into `v1/__init__.py` (AC1)**
  - [ ] Edit `services/bff/src/bff/api/v1/__init__.py` (currently 3 lines):
    ```python
    from fastapi import APIRouter

    from bff.api.books import router as books_router

    router = APIRouter(prefix="/v1")
    router.include_router(books_router)
    ```
  - [ ] **Note on the prefix:** because `books_router` already declares `prefix="/v1/books"`, the `v1_router`'s `prefix="/v1"` will prepend, producing the final mount `/v1/v1/books`. That's wrong. Two ways to fix; pick ONE:
    - **Option A (recommended):** change `books.py`'s router declaration to `APIRouter(prefix="/books", tags=["Books"])` (no `/v1`), and rely on `v1_router`'s prefix to supply it. Final mount: `/v1/books`.
    - **Option B:** keep `books.py`'s router as `APIRouter(prefix="/v1/books", ...)` and include it on `app` directly from `main.py` instead of routing through `v1_router`. NOT recommended — adds a special case to the wiring.
  - [ ] Use Option A. Update `books.py`'s `router = APIRouter(prefix="/v1/books", tags=["Books"])` → `router = APIRouter(prefix="/books", tags=["Books"])` accordingly. The `Location` header value in `create_book` stays `/v1/books/{book.id}` (it's the public URL, not the local mount-path).

- [ ] **Task 7 — Author `tests/api/test_books.py` (AC14)**
  - [ ] Create `services/bff/tests/api/test_books.py`. Module docstring: "Route-level tests for /v1/books CRUD (Story 2.2). Covers session auth, CSRF, cross-user isolation, validation, and the five verbs."
  - [ ] Import the existing `_seed_session` helper pattern from `tests/api/test_me.py:18–48`. Either import it directly (`from tests.api.test_me import _seed_session`) or copy the function into the new test file. Copying is preferred to keep test files self-contained — duplication of a 30-line helper across 2 files is acceptable per the project's "small redundancy over abstraction" stance (Story 1.12 Dev Notes).
  - [ ] Add a `_seed_book(session, *, sub, **overrides)` helper that builds an `entities.Book` and commits it.
  - [ ] Use the `client_with_csrf` fixture for state-changing tests (POST/PATCH/DELETE) — it pre-seeds the CSRF cookie/header/origin.
  - [ ] Use the plain `client` fixture for GET tests and for the "no CSRF" rejection tests (scenarios 4–6 above).
  - [ ] For each scenario in AC14, write one async test function. Use descriptive names: `test_list_books_returns_only_own_books`, `test_create_book_returns_201_with_location_header`, `test_read_book_returns_404_for_other_users_book`, etc.
  - [ ] For cross-user scenarios (18, 25, 28, 29): seed TWO sessions in the same test, capture both cookie values, then drive requests with each one via the `cookies={...}` kwarg on `client.get/post/etc.`.
  - [ ] For the "expired session" test (scenario 3): seed a session with `expires_offset_seconds=-60`. After the 401 response, fetch via `session_service.get_session(...)` and assert `is None`.

- [ ] **Task 8 — Author `tests/services/test_books_service.py` (AC15)**
  - [ ] Create `services/bff/tests/services/test_books_service.py`. Mirror the structure of `tests/services/test_session_service.py`.
  - [ ] Helper `def _build_book(**overrides) -> entities.Book` (mirrors Story 2.1's `_build_book`).
  - [ ] All tests use the `session` fixture directly. No `client` involvement.
  - [ ] Implement each scenario listed in AC15.

- [ ] **Task 9 — Run the full BFF gate matrix (AC16)**
  - [ ] From `services/bff/`:
    - `uv sync --frozen` → exit 0.
    - `uv run ruff check` → clean.
    - `uv run ruff format --check` → clean.
    - `uv run ty check` → clean.
    - `uv run pytest --cov` → all tests pass; total coverage ≥ 90%; per-module coverage ≥90% on `src/bff/api/books.py` and `src/bff/services/books_service.py`.
  - [ ] Audit any unexpected test fallout: the wire-code change in `validation_exception_handler` flips `VALIDATION_ERROR` → `invalid_input` globally; ANY test elsewhere that asserts `errorCode == "VALIDATION_ERROR"` for a 422 response needs updating. Sanity grep before running: `grep -rn "VALIDATION_ERROR" tests/` should return ONLY the legacy enum-shape test at `test_errors.py:17` (which keeps its assertion). Fix any others.
  - [ ] Capture suite-size delta (before / after) and per-module coverage in **Completion Notes**.

- [ ] **Task 10 — Update sprint-status**
  - [ ] On story start: flip `2-2-bff-full-books-crud-v1-books-v1-books-id: ready-for-dev` → `in-progress`. Bump `last_updated`.
  - [ ] On story complete (before `code-review`): flip to `review`. Bump `last_updated`.
  - [ ] If any defect surfaces (test_errors fallout, ty-check issues, etc.), append to `deferred-work.md` with the next sequential D-number.

## Dev Notes

### Critical path translation: epic doc vs. actual codebase

The epic doc (`epics.md` §Story 2.2 lines 791–793) describes a target where books-related errors live in `src/bff/core/exceptions.py` with `BFFError`/`BookNotFoundError`/`InvalidInputError` subclasses. **The actual codebase has no `exceptions.py`** — error semantics live in `bff/core/errors.py` with `AppException(ErrorCode, detail)` as the single canonical exception class. The translation:

- Epic says: `raise BookNotFoundError(...)` → **Code: `raise AppException(ErrorCode.BOOK_NOT_FOUND)`**.
- Epic says: `raise InvalidInputError(...)` → **Not used directly** — Pydantic's `RequestValidationError` short-circuits to `validation_exception_handler` which emits `invalid_input`. The handler code does NOT need an explicit `raise InvalidInputError(...)` for body validation — Pydantic does it for free.
- Epic says: `error_code = ErrorCode.BOOK_NOT_FOUND` → **Add `BOOK_NOT_FOUND` to the existing `ErrorCode` enum at `bff/core/errors.py`** (AC10).

**Do NOT create `src/bff/core/exceptions.py`.** This is the same pattern Story 2.1 documented for `db/models` → `models/entities`: the epic file's path was aspirational; the codebase is the source of truth.

### Wire-code convention (read this before touching errors.py)

Architecture §C5 (line 396) + AR17 (epics line 74) + the Format Patterns table (architecture lines 674–688) all align on **lower_snake_case wire codes** for project-specific errors:

- `session_expired`, `csrf_invalid`, `auth_state_invalid` — already lower_snake.
- `book_not_found`, `invalid_input` — added in this story per the same convention.
- `VALIDATION_ERROR`, `NOT_FOUND`, `INTERNAL_ERROR`, etc. — archetype-default UPPER_SNAKE codes that pre-date the project's lower_snake convention. **These stay as enum members for shape-stability** but are NOT emitted on the wire by handlers this story owns.

The cross-cutting wire-code change in this story:

- **`validation_exception_handler` flips `"VALIDATION_ERROR"` → `"invalid_input"`** (AC11). Any test asserting the OLD code on the wire breaks. Audit via `grep -rn "VALIDATION_ERROR" services/bff/tests/`. The known fix points are `tests/core/test_errors.py:85–86` (covered by AC12). If the grep turns up others — fix them or surface them in Completion Notes.

### Cross-user isolation: WHY 404 not 403

Epic spec line 821 explicitly: "the BFF responds 404 with `errorCode: "book_not_found"` (NOT 403 — existence is not leaked across users)". Architecture line 685 reaffirms: `404 → book_not_found`.

The reasoning: a 403 on `GET /v1/books/42` would tell a malicious client "book 42 exists, but you can't see it." A 404 says "book 42 doesn't exist for you" — indistinguishable from "book 42 doesn't exist at all." The SQL query `WHERE id = :id AND sub = :sub` produces this naturally — composing the two predicates yields a single "row not found for this user" result without exposing the cross-user case.

**Implementation rule:** the service-layer `get_for_user` method MUST embed the `sub` predicate in SQL. Never fetch by `id` alone and check `row.sub` in Python — that would split the two failure modes apart and invite a future caller to short-circuit the second check.

### Session extraction: shared helper vs. inline

Three modules now need to resolve a session cookie → `sub`: `api/me.py` (already inline), `api/test_reset.py::test_session_debug` (already inline — story 1.13), and this story's `api/books.py` (new inline). A shared helper would DRY the pattern.

**Decision for THIS story: keep the helper INSIDE `books.py` (`_resolve_session_sub` per AC3).** Reasons:

1. The existing two implementations in `me.py` and `test_reset.py` differ slightly (the test_session_debug variant returns a `JSONResponse` directly; `me.py`'s returns `_session_expired_response()` then falls through). Unifying them is a refactor that touches three story surfaces — out of scope here.
2. Adding a fourth call-site copy is the same redundancy the project already tolerates (per Story 1.12's "explicit one-line-per-table" stance).
3. **Defer extraction.** If a future story (e.g., Story 3.5 BFF reading-speed proxy) is the fourth consumer, file a D-item to hoist the helper into a `bff/auth/session_guard.py` module at that point.

**Do NOT import `_as_utc_aware` from `me.py`** — circular-import risk and the 3-line helper is cheaper to redeclare.

### Why `model_dump(exclude_unset=True)` is load-bearing for PATCH

If `BooksService.update` applied `payload.model_dump()` (without `exclude_unset=True`), every field NOT in the request would be set to its model default (`None` for `BookUpdate`'s optional fields). That would silently clobber the row's existing values whenever the client patches a subset of fields.

`payload.model_dump(exclude_unset=True)` returns ONLY fields explicitly provided in the request — including explicit `null` if the client sent it. For this story's `BookUpdate` (all fields optional, no nullable wire fields), explicit `null` should ALSO be rejected by Pydantic at validation time because the field types are `str | None` / `int | None` and `None` IS a valid value for those types. **In practice this means: explicit `null` in the request body for `title`/`pages`/`status` would pass Pydantic validation, reach the service, and clobber the field to `None`. Since the SQLModel columns are `nullable=False` (Story 2.1 AC1), the DB-level constraint would catch this with an `IntegrityError`.**

Edge case to consider: `PATCH {"title": null}`. Currently Pydantic accepts it (validator returns `None` because the first guard in `_title_not_blank_after_strip` is `if v is None: return v`). Service applies `{title: None}` → DB raises IntegrityError. Per AR17 + project conventions, the response would be a 500 (`INTERNAL_ERROR`) — ugly but correct. **For this story's scope, accept the IntegrityError fall-through.** A future hardening story can add a validator that rejects explicit `null` at the boundary. Document this in Completion Notes if you observe it during testing.

### Existing patterns to mirror exactly

**1. Route module shape — `api/me.py`.** The pattern for module-level singletons + `_settings_dep` helper + `Annotated[..., Depends(...)]` parameter ordering.

**2. Service module shape — `services/session_service.py`.** Class with async methods; module-level `logger`; uses `from sqlmodel import select`; uses `from sqlalchemy.ext.asyncio import AsyncSession`. The `*` keyword-only marker on method params is the project's convention for service methods.

**3. Test-side route patterns — `tests/api/test_me.py`.** The `_seed_session(session, **kwargs)` helper. The `client_with_csrf` fixture for state-changing requests. The bare `client` fixture for GET tests and CSRF-rejection tests.

**4. Test-side service patterns — `tests/services/test_session_service.py`.** Direct use of the `session` AsyncSession fixture; no HTTP involvement.

**5. Empty 204 response — `api/test_reset.py::test_reset` line 288.** `return Response(status_code=204)` from `fastapi.Response` (NOT `fastapi.responses.Response` — the convenience export is what the project uses).

### Architecture compliance

- **AR15 line 72** — "Versioned (domain APIs): `/v1/books`, `/v1/books/{id}`". Confirmed; the mount path is `/v1/books`.
- **AR16 line 73** — JSON contract: snake_case both directions; success returns the resource directly; failures use the `{errorCode, message, detail}` envelope; collections return a plain JSON array; empty 204 has no body; ISO 8601 UTC with `Z` for datetimes. All covered by the AC.
- **AR17 line 74** — `ErrorCode` enum extensions: `BOOK_NOT_FOUND` (404), `INVALID_INPUT` (422), `SESSION_EXPIRED` (401), `CSRF_INVALID` (403). All wired by this story's AC10 + AC11.
- **AR20 line 77** — Pydantic boundary models: `BookCreate`, `BookUpdate`, `BookOut`. Authored by Story 2.1; this story consumes them.
- **AR23 (SPA-side) line 83** — out of scope here; mentioned to confirm no SPA-side wiring obligation this story.
- **Architecture §C5 lines 396–409** — exact enum definitions with wire codes; this story adds `BOOK_NOT_FOUND` + `INVALID_INPUT` matching the spec.
- **Architecture §C6 line 411** — timeouts/retries: not relevant (no external HTTP calls in this story).
- **Architecture §C7 line 418** — distinct API Pydantic models. `BookOut` excludes `sub` — verified test-side via "`sub` field is NOT in the response" assertion.
- **Architecture §C8 line 420** — Pagination/Sorting/Search deferred. This story implements `created_at ASC` only; no further sort axes.
- **Architecture §"HTTP status codes" lines 676–688** — every status/wire-code pair this story emits is in this table. 200 LIST/READ/UPDATE; 201 CREATE + Location; 204 DELETE; 401 `session_expired`; 403 `csrf_invalid`; 404 `book_not_found`; 422 `invalid_input`.
- **Architecture §"Logging conventions" lines 781–788** — never log token material; truncate session ids; log `<event_name> sub=<8-char> id=<id>` style. The service-layer logs `book_created sub=<8-char> id=<book.id>` per AC13.
- **Architecture line 685** — "404 → `book_not_found`. Resource not found (book)". This story's exact wire code.

### Library / framework requirements

No new dependencies. All imports are already in `pyproject.toml`:

- `fastapi` — `APIRouter`, `Depends`, `Request`, `Response`, `status`.
- `sqlalchemy` / `sqlmodel` — `select`, `AsyncSession`. `entities.Book` newly available via Story 2.1.
- `pydantic` — `BookCreate`/`BookUpdate`/`BookOut` from Story 2.1.
- `httpx` (tests only) — already pinned.

No new dev dependencies. Python 3.14 floor unchanged.

### File structure requirements

**New files (this story):**

- `services/bff/src/bff/api/books.py` — five route handlers + `_resolve_session_sub` helper + module-level singletons.
- `services/bff/src/bff/services/books_service.py` — `BooksService` class with five async methods.
- `services/bff/tests/api/test_books.py` — 29-scenario route test matrix.
- `services/bff/tests/services/test_books_service.py` — service-layer test scenarios.

**Modified files:**

- `services/bff/src/bff/api/v1/__init__.py` — import `books_router` and include it on `v1_router`.
- `services/bff/src/bff/core/errors.py` — add `BOOK_NOT_FOUND` + `INVALID_INPUT` to the enum; update `validation_exception_handler` wire code.
- `services/bff/tests/core/test_errors.py` — flip the wire-code assertion in `test_validation_error_via_http`; add two new enum-shape tests.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — flip the story's status across the workflow.

**NOT modified (intentional — per scope):**

- `services/bff/src/bff/main.py` — `v1_router` is already wired (Story 1.3); no change here.
- `services/bff/src/bff/auth/csrf.py` — CSRF middleware works as-is for non-exempt paths.
- `services/bff/src/bff/api/test_reset.py` — Story 2.3 owns the books-truncate extension.
- `services/bff/src/bff/models/entities/book.py` — Story 2.1 owns this file.
- `services/bff/src/bff/api/schemas/book.py` — Story 2.1 owns this file.
- `services/bff/alembic/...` — no schema changes.
- `services/bff/pyproject.toml` — no new dependencies.
- `compose/...`, `.env.example` — no infra changes.

### Testing standards

- **Framework:** pytest 8+, pytest-asyncio (`asyncio_mode = "auto"`).
- **HTTP client:** `client_with_csrf` (pre-seeded CSRF cookie/header/origin) for POST/PATCH/DELETE. `client` for GET and for the CSRF-rejection tests.
- **DB:** in-memory SQLite via the existing `engine` + `session` fixtures from `conftest.py`. The `books` table is auto-created by `SQLModel.metadata.create_all` because Story 2.1 registers `Book` in `bff.models.entities.__init__.py`.
- **Seed helpers:** copy `_seed_session` from `tests/api/test_me.py` (or import it). Author a new `_seed_book` helper in `test_books.py`.
- **Coverage gate:** total project `fail_under = 90` (`pyproject.toml:86`). Per-module ≥90% on the two new source files per epic line 851.
- **Lint / format / type-check:** `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` — all clean.
- **Python invocation:** `python` (never `python3`) per `CLAUDE.md`.

### Previous story intelligence

**From Story 2.1 (precondition):**

- `Book.id` is `int | None` with autoincrement at the SQLAlchemy layer. Do NOT pass `id=` when constructing `Book(...)` in service methods or tests — SQLAlchemy assigns it on commit.
- `Book.sub` is `str(255)` indexed via `ix_books_sub`. The query `WHERE sub = :sub AND id = :id` uses the index (the `id` predicate alone uses the PK).
- `Book.status` column-level default is `"to-read"`. `BookCreate.status` has the same default at the Pydantic layer. Both should agree.
- `BookOut` has `model_config = ConfigDict(from_attributes=True)`. Use `BookOut.model_validate(book)` to convert an ORM row to the response model.
- The conftest's `engine` + `session` fixtures create / drop SQLModel.metadata between tests. Per-test seed rows do NOT leak.

**From Story 1.12 (test-reset):**

- The 204 idiom is `return Response(status_code=204)` — never `None`, never `JSONResponse({})`.
- `hmac.compare_digest` for secret comparison — NOT relevant for this story (no secrets compared in books CRUD; CSRF middleware handles that for state-changing paths).

**From Story 1.7 (logout endpoint):**

- The `_safe_session_id_log` truncate-to-8-chars + `...` (only when actually truncated) idiom. Apply this to the books service's `sub` logging (`sub=<8-char>... if len(sub) > 8 else ""`).

**From Story 1.6 (CSRF middleware):**

- The middleware enforces double-submit cookie + `X-CSRF-Token` header + same-origin `Origin`/`Referer`. State-changing requests without ALL of these get 403 `csrf_invalid` BEFORE the route handler runs.
- The `client_with_csrf` fixture provides all three. Use it for happy-path POST/PATCH/DELETE tests.

**From Story 1.5 (cookie-session OIDC plugin):**

- Session cookies are HttpOnly opaque 256-bit values, NOT JWTs. Server-side state in the `sessions` table is the source of truth for `sub`. The plain `bff_session` cookie name is configured by `cfg.bff_session_cookie_name`.
- Expired sessions get lazy-deleted on first access. The pattern is in `me.py:65–68` — mirror it.

**From Story 1.3 review (validation handler P3):**

- `validation_exception_handler` strips the `input` key from each Pydantic error before serializing (because echoing it back leaks raw request data including potential PII / secrets). This story keeps that behavior verbatim — only the wire code/message change.

### Git intelligence summary

Recent commits on `epic-2` (per `git log -5`):

```
81ae50f story 2.1
060df66 feat: minor fixes to the CSFR token naming
ca02146 fix: BFF drops offline_access scope + realm declares profile scope
180b1e2 chore(1.14): code review — F1 path-traversal guard, F2 docstring fix, 5 defers; close epic-1
501a85a Merge story 1.14 — dev-story phase
```

**Implication for this story:**

- `81ae50f` ("story 2.1") created the `Book` SQLModel + Alembic migration. Sprint-status reports 2.1 as `ready-for-dev` (NOT `done`) — this might be in-progress work, not the merged final. Task 1's precondition check is the load-bearing assertion. **If the precondition fails, STOP.**
- The CSRF fix (`060df66`) is unrelated to this story's diff.
- Branch `epic-2` is the working branch.

### Latest tech information

- **FastAPI 0.115+** — `APIRouter.include_router(other_router)` composes prefixes; the resulting mount path is `outer.prefix + inner.prefix + route.path`. Use Option A in Task 6 to avoid a double `/v1/` prefix.
- **Pydantic v2 `model_dump(exclude_unset=True)`** — returns ONLY fields explicitly present in the input. Required for PATCH partial-update semantics.
- **SQLAlchemy 2.x async** — `select(entities.Book).where(...).order_by(...)` then `await db.execute(...)` then `.scalars().all()`. The full pattern is in `session_service.py:117–120`.
- **httpx 0.27+ AsyncClient with cookies kwarg** — `await client.get("/v1/books", cookies={"bff_session": session_id})` — overrides any cookies the fixture pre-set for THIS request only. Useful for the cross-user-isolation scenarios.
- **pytest-asyncio `asyncio_mode = "auto"`** — `async def test_...` is enough. No `@pytest.mark.asyncio` decorator.

### Project Structure Notes

The diff follows the architecture's source-tree (architecture lines 901, 938, 941):

```
services/bff/
├── src/bff/
│   ├── api/
│   │   ├── books.py                     (NEW)
│   │   ├── v1/__init__.py               (UPDATE: include books_router)
│   │   └── ...                          (existing)
│   ├── services/
│   │   ├── books_service.py             (NEW)
│   │   └── ...                          (existing)
│   └── core/errors.py                   (UPDATE: +BOOK_NOT_FOUND, +INVALID_INPUT, validator wire code)
└── tests/
    ├── api/test_books.py                (NEW)
    ├── services/test_books_service.py   (NEW)
    └── core/test_errors.py              (UPDATE: validator assertion + new enum-shape tests)
```

**Detected variance from epic document:** `epics.md` §Story 2.2 line 792 mentions `src/bff/core/exceptions.py` with `BFFError`/`BookNotFoundError`/`InvalidInputError` classes. The actual codebase uses `bff/core/errors.py` with `AppException(ErrorCode, detail)` exclusively. Follow the codebase pattern (per Task 2). Do NOT create `exceptions.py`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2: BFF — full books CRUD (`/v1/books` + `/v1/books/{id}`)] (lines 782–852)
- [Source: _bmad-output/planning-artifacts/epics.md#AR16 — JSON contract (line 73)]
- [Source: _bmad-output/planning-artifacts/epics.md#AR17 — ErrorCode enum extensions (line 74)]
- [Source: _bmad-output/planning-artifacts/epics.md#AR20 — Pydantic boundary models (line 77)]
- [Source: _bmad-output/planning-artifacts/architecture.md#C5 ErrorCode enum (lines 396–409)]
- [Source: _bmad-output/planning-artifacts/architecture.md#C7 JSON serialization (line 418)] (BookOut excludes sub)
- [Source: _bmad-output/planning-artifacts/architecture.md#"HTTP status codes (binding rules)" (lines 674–688)]
- [Source: _bmad-output/planning-artifacts/architecture.md#"Logging conventions" (lines 781–788)]
- [Source: _bmad-output/planning-artifacts/architecture.md#Naming Patterns (line 546)] (plural snake_case `books`)
- [Pattern: services/bff/src/bff/api/me.py lines 1–87] (cookie-session handler shape this story mirrors)
- [Pattern: services/bff/src/bff/api/test_reset.py lines 196–288] (Response(status_code=204) idiom)
- [Pattern: services/bff/src/bff/services/session_service.py lines 105–240] (service-class shape, keyword-only params, logging)
- [Pattern: services/bff/src/bff/core/errors.py lines 1–77] (ErrorCode enum + AppException + handlers)
- [Pattern: services/bff/tests/api/test_me.py lines 1–110] (test-route shape + _seed_session helper)
- [Pattern: services/bff/tests/services/test_session_service.py] (service-layer test shape)
- [Pattern: services/bff/tests/conftest.py lines 84–144] (client / client_with_csrf / client_no_redirects fixtures)
- [Pattern: _bmad-output/implementation-artifacts/2-1-bff-book-sqlmodel-migration-pydantic-boundary-models.md] (Book entity + boundary models — precondition for this story)
- [Gate: services/bff/pyproject.toml lines 9, 76–86] (Python 3.14; pytest config; coverage `fail_under=90`)
- [Convention: CLAUDE.md] (project convention: invoke Python as `python`, never `python3`)

### Project context reference

Project-context facts loaded at activation:

- BMAD_books accessibility / responsive design: OUT OF SCOPE — not relevant; this is a backend-only HTTP-surface story.
- Backend archetype: `github.com/tommaso-meledina/fastapi-archetype` (Python 3.14 + FastAPI + SQLModel + uv + OTEL). This story stays inside the archetype's conventions — same APIRouter pattern, same SQLModel entities, same uv-managed deps, same `AppException`/`ErrorCode` error envelope.
- Python invocation: `python` (never `python3`) per `CLAUDE.md`. All command examples in this story use `python`.

## Definition of Done

1. `services/bff/src/bff/api/books.py` exists with five route handlers (`list_books`, `create_book`, `read_book`, `update_book`, `delete_book`) and the `_resolve_session_sub` helper (AC1–AC9).
2. `services/bff/src/bff/services/books_service.py` exists with `class BooksService` and five async methods (AC13).
3. `services/bff/src/bff/api/v1/__init__.py` includes the books router (AC1).
4. `services/bff/src/bff/core/errors.py` declares `BOOK_NOT_FOUND` and `INVALID_INPUT` in the `ErrorCode` enum; `validation_exception_handler` emits `invalid_input` on the wire (AC10, AC11).
5. `services/bff/tests/api/test_books.py` covers the 29-scenario matrix in AC14 and all tests pass.
6. `services/bff/tests/services/test_books_service.py` covers the service-layer scenarios in AC15 and all tests pass.
7. `services/bff/tests/core/test_errors.py` is updated: `test_validation_error_via_http` asserts the new wire code/message; two new enum-shape tests exist for `BOOK_NOT_FOUND` and `INVALID_INPUT` (AC12).
8. Cross-user isolation holds: a session for sub `A` can never see / read / update / delete a book owned by sub `B`. The 404 vs 403 contract per architecture line 685 is enforced via the SQL `WHERE id = :id AND sub = :sub` query.
9. `uv run pytest --cov`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` all clean. Coverage of the two new source files ≥90%; total project coverage ≥90%.
10. Sprint-status YAML reflects the story's final state (`review` before code-review, then `done` after).
11. The `src/bff/db/` directory does NOT exist (epic-doc variance noted; codebase uses `models/entities/` per Story 2.1's translation).
12. No `src/bff/core/exceptions.py` exists (epic-doc variance noted; codebase uses `bff/core/errors.py::AppException` exclusively).
13. No new dependencies in `pyproject.toml`; no new Alembic migration; no infra changes.

## Dev Agent Record

### Agent Model Used

<!-- filled by dev-story -->

### Debug Log References

<!-- filled by dev-story -->

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.

### File List

<!-- filled by dev-story -->

### Change Log

<!-- filled by dev-story -->
