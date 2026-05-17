---
status: done
story_key: 3-3-rs-reading-speed-model-migration-v1-reading-speed-get-put-scope-gated
epic: 3
prerequisites: 3.1 (done — RS scaffolded, `/health` + readiness probes, RS in compose default/dev, `ErrorCode.SERVICE_UNAVAILABLE`, required-fail-fast OIDC config, Alembic env.py reads `RS_DATABASE_URL`); 3.2 (done — `oidc_bearer` plugin, `get_authenticated_principal`, `require_scope(scope)`, `Principal.scopes: frozenset[str]`, `ErrorCode.{SESSION_EXPIRED, FORBIDDEN_SCOPE}`, synthetic-IdP harness)
specLoopIteration: 1
---

# Story 3.3: RS — `ReadingSpeed` model + migration + `/v1/reading-speed` GET/PUT (scope-gated)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a signed-in user (eventually, via the SPA),
I want the RS to expose GET and PUT on `/v1/reading-speed` strictly scoped to my `sub` (read from the JWT) and gated by the appropriate OAuth scopes,
so that my reading speed is stored on the RS and cannot be read or modified by anyone else's session, and the architectural scope-split is enforced where the PRD requires (at the RS, not the BFF).

## Acceptance Criteria

1. **`src/resource_server/models/entities/reading_speed.py` exists and declares the `ReadingSpeed` SQLModel.** The model:
   - `__tablename__ = "reading_speeds"` (plural, snake_case per architecture line 546).
   - `id: int = Field(default=None, primary_key=True)` — integer auto-increment (architecture line 548; "switch to UUID only if there is an external-stability reason"; this is internal, no stability concern).
   - `sub: str = Field(max_length=255, index=True, unique=True, nullable=False)` — opaque OIDC subject claim; UNIQUE + indexed (architecture line 549, 551; "`reading_speeds.sub`" is explicitly enumerated as one of the indexed columns).
   - `pages_per_hour: int = Field(nullable=False)` — application-enforced `ge=1` (Pydantic constraint on the API DTO, not the SQLModel — see AC #2; SQLModel-level constraints are awkward and Pydantic handles request validation cleanly).
   - `created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)` — UTC, naive `DATETIME` per architecture line 695.
   - `updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)})` — mirror the BFF's `Session.updated_at` pattern (verified at `services/bff/src/bff/models/entities/session.py:35-39`).
   - Class docstring documents the singleton-per-user invariant (one row per `sub`; PUT is upsert; GET returns 412 when absent — see AC #6).
   - Registered in `src/resource_server/models/entities/__init__.py`'s `__all__` so `SQLModel.metadata` picks it up at Alembic-autogenerate time (verified Story 3.1 left `__all__: list[str] = []` ready for this addition).

2. **`src/resource_server/api/schemas/reading_speed.py` exists and declares the API DTOs.** Architecture line 418 (C7) mandates "Distinct API Pydantic models, not SQLModel ORM classes serialized directly. Keeps internal columns (`created_at`, `sub`) out of responses by construction." Concrete shape:
   - `ReadingSpeedOut(BaseModel)`: `pages_per_hour: int`. Response model for GET + the success body of PUT.
   - `ReadingSpeedUpsert(BaseModel)`: `pages_per_hour: int = Field(ge=1)` — Pydantic enforces `ge=1` at the boundary; values 0 or negative are rejected as 422 `invalid_input` before reaching the handler. Request model for PUT body.
   - **Choice of location:** The architecture's directory listing at lines 968–1007 shows the RS has `models/dto/v1/` (per the archetype scaffold — Story 3.1 left this directory empty after `--no-demo` cleanup). Use `src/resource_server/api/schemas/reading_speed.py` per the **story spec's explicit AC text**, which trumps the archetype default. Rationale: this story is the first RS story to introduce request/response DTOs; placing them under `api/schemas/` keeps them closer to their consuming routers (one router file per resource, schemas adjacent). Document the placement choice in the dev log.
   - Add `from __future__ import annotations` at the top of the schemas file so forward references work cleanly with Pydantic v2.

3. **Alembic migration `alembic/versions/0001_init_<slug>.py` exists and creates `reading_speeds`.** Generation procedure:
   - From `services/resource-server/`, run: `uv run alembic revision --autogenerate -m "init reading_speeds"`. This generates a file named `0001_init_init_reading_speeds.py` or similar (Alembic uses the message slug; double "init" is fine and matches the BFF's `0001_init_init_sessions_and_auth_states.py` filename pattern from Story 1.4).
   - The generated migration MUST contain: `op.create_table("reading_speeds", ...)` with columns `id` (Integer PK, autoincrement), `sub` (`sqlmodel.sql.sqltypes.AutoString(length=255)`, nullable=False), `pages_per_hour` (Integer, nullable=False), `created_at` (DateTime, nullable=False), `updated_at` (DateTime, nullable=False); plus `op.create_index(op.f("ix_reading_speeds_sub"), "reading_speeds", ["sub"], unique=True)` (the UNIQUE constraint is conveyed via the unique index — SQLModel's `Field(index=True, unique=True)` autogenerates exactly this).
   - The migration file's revision: `0001_init`, down_revision: `None`, branch_labels: `None`, depends_on: `None` (matches the BFF's Story 1.4 pattern verbatim at `services/bff/alembic/versions/0001_init_init_sessions_and_auth_states.py:14-19`).
   - Inspect the autogenerated migration; if Alembic generates a redundant separate `op.create_unique_constraint` on top of the unique index, **remove the redundant constraint** (one or the other suffices; SQLModel's unique=True index is the simpler choice). Capture the verification in the dev log.
   - `uv run alembic upgrade head` (from within `services/resource-server/`, with `RS_DATABASE_URL=sqlite+aiosqlite:///./rs-dev.db` or similar local path) exits 0; `uv run alembic current` reports `0001_init (head)`. `uv run alembic downgrade base` reverses cleanly. Clean up the local `rs-dev.db` after verification.
   - The pre-existing `alembic/env.py` (Story 3.1 left it in place at `services/resource-server/alembic/env.py:23-26`) already does `from resource_server.models import entities` to populate `SQLModel.metadata` for autogenerate — the new `ReadingSpeed` entity is picked up via that import chain (per AC #1's registration in `__init__.py`).

4. **`src/resource_server/core/exceptions.py` exists and declares `ReadingSpeedUnsetError`.** Architecture lines 735–749 (Communication Patterns / Error handling — backend services) mandate "Business code raises **domain exceptions** from `core/exceptions.py`, never `HTTPException`." Concrete shape:
   - The file is new (Story 3.1 left `core/` without an `exceptions.py`; `core/errors.py` holds `AppException` + `ErrorCode` + the JSON handlers, but the architecture-prescribed pattern is to keep domain exceptions in a separate `exceptions.py`).
   - `ReadingSpeedUnsetError(AppException)` — `AppException` is the existing archetype-emitted base in `core/errors.py:33`. Initialize with `super().__init__(ErrorCode.READING_SPEED_UNSET)`.
   - This subclass-with-fixed-error-code pattern matches architecture's example at lines 742–748 (`BookNotFoundError(BFFError)`, `ReadingSpeedUnsetError(BFFError)` — substitute `AppException` for `BFFError` since the RS's archetype emits `AppException` rather than the architecture's hypothetical `BFFError`). Document the rename in the dev log.
   - Importing `core/exceptions` MUST be idempotent (no module-level side effects). The class is consumed by `services/reading_speed_service.py` (raises it on missing-row) and caught by the existing `app_exception_handler` in `core/errors.py:56-63` (since it subclasses `AppException`, no new handler registration is required).

5. **`core/errors.py` gains `ErrorCode.READING_SPEED_UNSET` and `ErrorCode.INVALID_INPUT`.** Wire values + HTTP statuses + leading-comment update:
   - `READING_SPEED_UNSET = ("reading_speed_unset", "Reading speed not set for this user", 412)` — per architecture line 402 (C5 table).
   - `INVALID_INPUT = ("invalid_input", "Request validation failed", 422)` — per architecture line 405.
   - Update the leading project-specific-codes comment to reflect Story 3.3's additions (mirrors the discipline established by Story 3.1 + 3.2; pre-existing block currently calls out 3.3 as the consumer for READING_SPEED_UNSET + INVALID_INPUT).
   - **`validation_exception_handler` in `core/errors.py:66-77` MUST be updated to emit `INVALID_INPUT` (not `VALIDATION_ERROR`).** The archetype's default emits `VALIDATION_ERROR` (UPPER_SNAKE wire value, not the architecture-mandated `invalid_input`); the RS's project-specific convention is lower_snake. Change the body to:
     ```python
     return JSONResponse(
         status_code=ErrorCode.INVALID_INPUT.http_status,
         content=_build_error_body(
             ErrorCode.INVALID_INPUT.code,
             ErrorCode.INVALID_INPUT.message,
             [{k: v for k, v in err.items() if k != "input"} for err in val_exc.errors()],
         ),
     )
     ```
     The detail-sanitization (`{k: v for k, v in err.items() if k != "input"}`) drops Pydantic's `input` field from each error before serializing. The BFF closed this in Story 1.3 review patch P3 (verified at `services/bff/src/bff/core/errors.py:62-68`) — Pydantic includes the user-supplied value verbatim; echoing it back leaks raw request data (passwords, tokens, PII) into 422 responses. Mirror the BFF's sanitization exactly. **Tests for the existing `VALIDATION_ERROR` envelope shape MUST be updated** to expect `invalid_input` — see AC #11.

6. **`src/resource_server/services/reading_speed_service.py` exists and exposes two async functions.** Architecture lines 612–613: "One service module per domain concept." Concrete surface:
   - `async def get_for_user(session: AsyncSession, sub: str) -> ReadingSpeed` — selects the single `reading_speeds` row WHERE `sub = :sub`. If no row exists, raises `ReadingSpeedUnsetError`. Return the SQLModel instance (not the DTO; the router does the boundary conversion via `ReadingSpeedOut(pages_per_hour=row.pages_per_hour)`).
   - `async def upsert(session: AsyncSession, sub: str, pages_per_hour: int) -> ReadingSpeed` — inserts a fresh row if no `sub`-match exists; updates `pages_per_hour` + `updated_at` if it does. Uses SQLAlchemy's `select(ReadingSpeed).where(ReadingSpeed.sub == sub)` pattern via `session.exec(...)` (async); commits at the end (the caller's session dependency handles rollback on exception). On insert path: set `created_at=datetime.now(UTC)` explicitly (SQLModel's default_factory handles this for default INSERTs but make the test deterministic). On update path: update `pages_per_hour`; the `onupdate` callable on `updated_at` fires automatically.
   - Returns the *committed-and-refreshed* SQLModel instance (`await session.commit(); await session.refresh(row); return row`) so the caller sees the latest `id` + timestamps.
   - **DB-level integrity:** the UNIQUE index on `sub` is a defense-in-depth backstop. If a race-condition INSERT collides (two requests for the same `sub` arriving in flight), the second INSERT will raise `IntegrityError`; the service does NOT need to catch this in v1 (FastAPI's transaction-per-request model + small load makes the race vanishingly unlikely, and a 500 is preferable to silent data loss). Document the assumption in the service module's docstring.
   - **No direct ORM queries in the router.** The router calls service functions only (architecture's separation: api → services → db).

7. **`src/resource_server/api/reading_speed.py` exists with the `/v1/reading-speed` router.** Concrete surface:
   - `router = APIRouter()` (no prefix here — the `/v1` prefix lives in `api/v1/__init__.py` per the existing pattern verified at `services/resource-server/src/resource_server/api/v1/__init__.py:3`).
   - GET handler:
     ```python
     @router.get(
         "/reading-speed",
         response_model=ReadingSpeedOut,
         tags=["reading-speed"],
     )
     async def get_reading_speed(
         session: Annotated[AsyncSession, Depends(get_session)],
         principal: Annotated[Principal, Depends(require_scope("reading-speed:read"))],
     ) -> ReadingSpeedOut:
         row = await reading_speed_service.get_for_user(session, principal.subject)
         return ReadingSpeedOut(pages_per_hour=row.pages_per_hour)
     ```
   - PUT handler:
     ```python
     @router.put(
         "/reading-speed",
         response_model=ReadingSpeedOut,
         tags=["reading-speed"],
     )
     async def put_reading_speed(
         payload: ReadingSpeedUpsert,
         session: Annotated[AsyncSession, Depends(get_session)],
         principal: Annotated[Principal, Depends(require_scope("reading-speed:write"))],
     ) -> ReadingSpeedOut:
         row = await reading_speed_service.upsert(session, principal.subject, payload.pages_per_hour)
         return ReadingSpeedOut(pages_per_hour=row.pages_per_hour)
     ```
   - Both handlers read `sub` from `principal.subject` (which `oidc_bearer.get_authenticated_principal` populates from the JWT `sub` claim — verified at `services/resource-server/src/resource_server/auth/oidc_bearer.py:89`). **No path or body parameter for the user identifier**, per architecture line 388: "All RS endpoints read user identity from the JWT `sub` claim — no path or body identifier accepted for user."
   - `tags=["reading-speed"]` keeps OpenAPI grouping clean.
   - HTTP status: GET returns 200 on success, 412 via `ReadingSpeedUnsetError` (the existing app_exception_handler emits the envelope). PUT returns 200 on success (NOT 201 — the singleton-per-user model means PUT is idempotent and "always already exists from the user's perspective"; matches architecture's C3 table entry "Upsert `{ pages_per_hour }`" at line 385).
   - Router is registered in `api/v1/__init__.py` via `from resource_server.api.reading_speed import router as reading_speed_router; router.include_router(reading_speed_router)` (the v1 wrapper router is `from resource_server.api.v1 import router as v1_router` and is already mounted on `app` in `main.py:10`).

8. **`get_session` is the session dependency.** Verified `services/resource-server/src/resource_server/core/database.py:88-91` already exposes `async def get_session() -> AsyncGenerator[AsyncSession]`. Story 3.3 does NOT need to author a new session dependency.

9. **AC #6's "GET returns 412 not 404" semantic is preserved across the stack.** Per architecture line 690 ("404 on GET /v1/reading-speed is not an error in the same sense as a missing book — it carries `errorCode: "reading_speed_unset"` so the SPA can distinguish from a transport-level 404") + line 686 (412 wire-row in the HTTP-status table). The route emits 412 because `ReadingSpeedUnsetError.error_code.http_status == 412`. **Do NOT use 404** — that would conflict with FastAPI's default 404 for nonexistent paths, and the SPA's `AppError.kind === "reading_speed_unset"` discriminated union (architecture line 718) is keyed on the wire value not the HTTP status.

10. **Cross-user isolation is enforced by reading `sub` from the JWT alone.** The router never accepts a `sub` from the request body, path, or query. The service's `get_for_user(session, sub)` accepts the `sub` parameter but the only caller is the router, which only ever passes `principal.subject`. Two users with subs `S1` and `S2` issuing concurrent PUT requests cannot affect each other's rows — the WHERE-clause + UNIQUE index guarantees row isolation.

11. **Tests cover every AC enumerated above.** Three test files (mirroring the source structure per architecture line 615):
    - `tests/models/entities/test_reading_speed.py` — SQLModel-level tests:
      - Insert a row, read it back, verify column types + index + unique constraint.
      - Insert two rows with the same `sub` → `IntegrityError` raised.
      - `updated_at` bumps on UPDATE (compare timestamps before / after; allow a 1ms tolerance for sub-second test runs — sleep 1ms or use `freezegun`-style time skip).
      - `created_at` is set on INSERT and DOES NOT change on UPDATE.
      - 5 tests minimum.
    - `tests/services/test_reading_speed_service.py` — service-level tests:
      - `get_for_user` happy path (row exists) → returns SQLModel.
      - `get_for_user` row absent → raises `ReadingSpeedUnsetError`.
      - `upsert` insert path → row created with the right `sub` + `pages_per_hour`; `id` is populated.
      - `upsert` update path (call twice with same `sub`, different `pages_per_hour`) → row count remains 1, `pages_per_hour` reflects the latest call, `updated_at > created_at`.
      - Cross-user isolation: `upsert(s1=A), upsert(s2=B), get_for_user(s1=A) == A's value, get_for_user(s2=B) == B's value`.
      - 5 tests minimum.
    - `tests/api/test_reading_speed.py` — request-layer tests (using the synthetic-IdP harness from `tests/auth/synthetic_idp.py` — verified at `services/resource-server/tests/auth/synthetic_idp.py:33-204`):
      - GET 200 happy path (token with `reading-speed:read` scope; row exists).
      - GET 412 `reading_speed_unset` (token valid + read-scope; row absent).
      - GET 403 `forbidden_scope` (token has only `reading-speed:write`, lacks `reading-speed:read`).
      - GET 401 `session_expired` (no Authorization header).
      - PUT 200 insert path (token has `reading-speed:write`; row absent → row created → response body `{"pages_per_hour": 30}`).
      - PUT 200 update path (token has `reading-speed:write`; row already exists → row updated → response body reflects new value; `updated_at` advances).
      - PUT 403 `forbidden_scope` (token has only `reading-speed:read`).
      - PUT 422 `invalid_input` with body `{"pages_per_hour": 0}`. Verify envelope `{"errorCode": "invalid_input", "message": "...", "detail": [...]}` — the detail is a list of Pydantic errors with the `input` field stripped per the BFF Story 1.3 P3 patch.
      - PUT 422 `invalid_input` with body `{"pages_per_hour": -5}`.
      - PUT 422 `invalid_input` with body `{}` (missing field).
      - PUT 422 `invalid_input` with body `{"pages_per_hour": "thirty"}` (wrong type).
      - PUT 401 `session_expired` (no Authorization header).
      - Cross-user isolation on PUT then GET: user A puts value 30, user B puts value 50, user A gets back 30, user B gets back 50. Use `synthetic_rs_idp.make_access_token(sub="user-a-...")` and `sub="user-b-..."` to vary the JWT.
      - 13 tests minimum.
    - Total minimum new test count: 23. Capture in the dev log.
    - **Coverage of `src/resource_server/api/reading_speed.py` AND `src/resource_server/services/reading_speed_service.py` is ≥90%** (per the AC verbatim). The whole-suite threshold (`[tool.coverage.report].fail_under = 90`) remains in place; the per-file ask of "≥90%" is met by the test plan above.

12. **No production-app changes outside the new code paths.** `main.py` is NOT modified — the `v1_router` is already registered (verified at `services/resource-server/src/resource_server/main.py:67-69`), and the new `reading_speed_router` is included into `v1_router` via `api/v1/__init__.py` (one-line edit). The existing `/health` handler, the `oidc_bearer` plumbing, and the entra/none auth modes are untouched.

13. **Existing tests continue to pass.** Run `uv run pytest` after every change; the Story 3.1 + 3.2 test suite (209 tests at story start) MUST remain green. Specifically:
    - The existing `tests/core/test_errors.py` tests asserting on `VALIDATION_ERROR` wire values WILL fail after AC #5 flips the validation handler to emit `invalid_input`. **Update those tests** to expect the new envelope shape (`errorCode: "invalid_input"`, status 422, sanitized detail list). This is an in-scope test update, not a regression. Capture the count of updated tests in the dev log.
    - Tests in `tests/auth/`, `tests/observability/`, `tests/api/test_health.py`, `tests/api/test_cors.py` are not affected.

14. **All `uv` / archetype gates remain green.** End-to-end command sequence:
    - `uv sync --frozen` → 0.
    - `uv run ruff check` → 0 findings.
    - `uv run ruff format --check` → 0 reformats needed (run `uv run ruff format` if anything is flagged).
    - `uv run ty check` → 0 errors.
    - `uv run pytest --cov` → all pass; whole-suite coverage ≥ 90%. Capture the post-change %.
    - `uv run alembic upgrade head` + `uv run alembic downgrade base` exit 0 (against a temporary SQLite file).

15. **Pre-existing repo state is preserved.** Files outside the new code paths are unchanged. Specifically: `CLAUDE.md`, root `README.md`, root `.env.example`, `docker-compose.yml`, `compose/*.yml`, `keycloak/**`, `services/bff/**`, `spa/**`, `e2e/**`, and `services/resource-server/{Dockerfile,entrypoint.sh,.gitattributes,.env.example,pyproject.toml,uv.lock,alembic.ini,alembic/env.py,alembic/script.py.mako,src/resource_server/main.py,src/resource_server/aop/**,src/resource_server/api/health.py,src/resource_server/api/v2/**,src/resource_server/auth/**,src/resource_server/observability/**,src/resource_server/core/config.py,src/resource_server/core/database.py,src/resource_server/factories/**,src/resource_server/models/dto/**}` are bit-for-bit identical to their pre-story state.

## Tasks / Subtasks

- [x] **Task 1 — Extend `ErrorCode` with READING_SPEED_UNSET + INVALID_INPUT** (AC: #5)
  - [x] Edit `services/resource-server/src/resource_server/core/errors.py`. Add to the `ErrorCode` enum, after `FORBIDDEN_SCOPE`:
    ```python
    READING_SPEED_UNSET = (
        "reading_speed_unset",
        "Reading speed not set for this user",
        412,
    )
    INVALID_INPUT = (
        "invalid_input",
        "Request validation failed",
        422,
    )
    ```
  - [x] Update the leading project-specific-codes comment to reflect Story 3.3's additions.
  - [x] **Update `validation_exception_handler`** to emit `INVALID_INPUT` instead of `VALIDATION_ERROR`. Mirror the BFF's `services/bff/src/bff/core/errors.py:58-76` (which strips Pydantic's `input` field from each error before serialization — Story 1.3 review P3 closed this PII-leak risk).
  - [x] Run `uv run pytest tests/core/test_errors.py -v` — existing tests expecting `VALIDATION_ERROR` envelopes WILL fail. Update them to expect `invalid_input` and the sanitized detail list. Capture the test-count delta in the dev log.

- [x] **Task 2 — Author `ReadingSpeed` SQLModel** (AC: #1)
  - [x] Author `services/resource-server/src/resource_server/models/entities/reading_speed.py`.
  - [x] Imports: `from datetime import UTC, datetime; from sqlmodel import Field, SQLModel`.
  - [x] Class body:
    ```python
    class ReadingSpeed(SQLModel, table=True):
        """User's reading speed (pages per hour). Singleton per `sub`.

        One row per OIDC subject. PUT is an upsert; GET returns 412 with
        ``errorCode: "reading_speed_unset"`` when no row exists for the
        caller's `sub` (per architecture's J3/J6 split — the SPA distinguishes
        "unset" from transport 404).
        """

        __tablename__ = "reading_speeds"

        id: int | None = Field(default=None, primary_key=True)
        sub: str = Field(
            max_length=255,
            index=True,
            unique=True,
            nullable=False,
        )
        pages_per_hour: int = Field(nullable=False)
        created_at: datetime = Field(
            default_factory=lambda: datetime.now(UTC),
            nullable=False,
        )
        updated_at: datetime = Field(
            default_factory=lambda: datetime.now(UTC),
            nullable=False,
            sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
        )
    ```
  - [x] Register in `services/resource-server/src/resource_server/models/entities/__init__.py`:
    ```python
    from resource_server.models.entities.reading_speed import ReadingSpeed

    __all__ = ["ReadingSpeed"]
    ```
    (Story 3.1's `__all__: list[str] = []` is replaced.)
  - [x] Smoke-import: `uv run python -c "from resource_server.models.entities import ReadingSpeed; print(ReadingSpeed.__tablename__)"` → `reading_speeds`.

- [x] **Task 3 — Generate the `0001_init` Alembic migration** (AC: #3)
  - [x] From `services/resource-server/`: `uv run alembic revision --autogenerate -m "init reading_speeds"`. Alembic emits `alembic/versions/0001_init_init_reading_speeds.py` (the slug double-"init" is fine; matches BFF convention).
  - [x] Inspect the generated file. Expected `upgrade()`:
    ```python
    op.create_table(
        "reading_speeds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sub", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("pages_per_hour", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reading_speeds_sub"), "reading_speeds", ["sub"], unique=True
    )
    ```
    Expected `downgrade()`: `op.drop_index(op.f("ix_reading_speeds_sub"), table_name="reading_speeds"); op.drop_table("reading_speeds")`.
  - [x] Verify the revision header: `revision: str = "0001_init"`, `down_revision: str | Sequence[str] | None = None`, `branch_labels: str | Sequence[str] | None = None`, `depends_on: str | Sequence[str] | None = None`. Matches BFF pattern at `services/bff/alembic/versions/0001_init_init_sessions_and_auth_states.py:14-19`.
  - [x] If Alembic emits a redundant separate `op.create_unique_constraint`, remove it. The unique index suffices.
  - [x] Smoke-test the migration:
    - `RS_DATABASE_URL=sqlite+aiosqlite:///./rs-dev.db uv run alembic upgrade head` → 0.
    - `RS_DATABASE_URL=sqlite+aiosqlite:///./rs-dev.db uv run alembic current` reports `0001_init (head)`.
    - `RS_DATABASE_URL=sqlite+aiosqlite:///./rs-dev.db uv run alembic downgrade base` → 0.
    - `rm -f rs-dev.db rs-dev.db-*` afterwards (the WAL / journal files too). Verify `git status` is clean of these artifacts (the repo's `.gitignore` should already cover `*.db`; if not, add it — see AC #15).
  - [x] Capture all command output in the dev log.

- [x] **Task 4 — Author `core/exceptions.py` with `ReadingSpeedUnsetError`** (AC: #4)
  - [x] Create `services/resource-server/src/resource_server/core/exceptions.py`. Body:
    ```python
    """Domain exceptions for the Resource Server.

    Business code raises subclasses of ``AppException`` (defined in
    ``core/errors.py``) rather than ``HTTPException`` so that the single
    archetype-emitted ``app_exception_handler`` can map every domain failure
    to the standard ``{errorCode, message, detail}`` envelope.

    See architecture §"Communication Patterns / Error handling (backend
    services)" line 735–749.
    """

    from __future__ import annotations

    from resource_server.core.errors import AppException, ErrorCode


    class ReadingSpeedUnsetError(AppException):
        """Raised by ``reading_speed_service.get_for_user`` when the caller's
        ``sub`` has no ``reading_speeds`` row. Maps to HTTP 412 with
        ``errorCode: "reading_speed_unset"`` via the existing
        ``app_exception_handler``.
        """

        def __init__(self, detail: str | None = None) -> None:
            super().__init__(ErrorCode.READING_SPEED_UNSET, detail)
    ```
  - [x] Verify it round-trips through the existing `app_exception_handler` (no new handler registration needed — `AppException` is already wired in `main.py:65` via Story 3.1).

- [x] **Task 5 — Author `api/schemas/reading_speed.py` with `ReadingSpeedOut` + `ReadingSpeedUpsert`** (AC: #2)
  - [x] Create the directory `services/resource-server/src/resource_server/api/schemas/` (and a minimal `__init__.py`).
  - [x] Author `services/resource-server/src/resource_server/api/schemas/reading_speed.py`:
    ```python
    """API DTOs for /v1/reading-speed.

    Distinct from the ``ReadingSpeed`` SQLModel per architecture §C7 line 418
    — keeps internal columns (``created_at``, ``updated_at``, ``sub``) out of
    responses by construction and lets Pydantic enforce the ``ge=1``
    invariant at the request boundary.
    """

    from __future__ import annotations

    from pydantic import BaseModel, Field


    class ReadingSpeedOut(BaseModel):
        """Response body for GET and PUT — exposes only ``pages_per_hour``."""

        pages_per_hour: int


    class ReadingSpeedUpsert(BaseModel):
        """Request body for PUT — Pydantic enforces ``ge=1`` at the boundary.

        Non-positive values yield 422 ``invalid_input`` before reaching the
        handler; the service / DB layer never sees them.
        """

        pages_per_hour: int = Field(ge=1)
    ```

- [x] **Task 6 — Author `services/reading_speed_service.py`** (AC: #6, #10)
  - [x] Create `services/resource-server/src/resource_server/services/reading_speed_service.py`. Body:
    ```python
    """Business logic for /v1/reading-speed.

    Singleton-per-user semantics: one ``reading_speeds`` row per OIDC
    ``sub``. GET → row or ``ReadingSpeedUnsetError``; PUT is an upsert.

    The UNIQUE index on ``sub`` is a defense-in-depth backstop against
    racing INSERTs; the service does not catch ``IntegrityError`` in v1
    because FastAPI's transaction-per-request model + small load makes the
    race effectively impossible. A 500 is preferable to silent data loss
    if the race ever materializes.
    """

    from __future__ import annotations

    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlmodel import select

    from resource_server.core.exceptions import ReadingSpeedUnsetError
    from resource_server.models.entities.reading_speed import ReadingSpeed


    async def get_for_user(session: AsyncSession, sub: str) -> ReadingSpeed:
        """Return the caller's ``reading_speeds`` row or raise ``ReadingSpeedUnsetError``."""
        result = await session.exec(select(ReadingSpeed).where(ReadingSpeed.sub == sub))
        row = result.first()
        if row is None:
            raise ReadingSpeedUnsetError()
        return row


    async def upsert(
        session: AsyncSession, sub: str, pages_per_hour: int
    ) -> ReadingSpeed:
        """Insert or update the caller's ``reading_speeds`` row.

        Returns the committed-and-refreshed row.
        """
        result = await session.exec(select(ReadingSpeed).where(ReadingSpeed.sub == sub))
        row = result.first()
        if row is None:
            row = ReadingSpeed(
                sub=sub,
                pages_per_hour=pages_per_hour,
                created_at=datetime.now(UTC),
            )
            session.add(row)
        else:
            row.pages_per_hour = pages_per_hour
            session.add(row)
        await session.commit()
        await session.refresh(row)
        return row
    ```

- [x] **Task 7 — Author `api/reading_speed.py` with the GET + PUT handlers** (AC: #7)
  - [x] Create `services/resource-server/src/resource_server/api/reading_speed.py`. Body:
    ```python
    """FastAPI router for /v1/reading-speed (GET + PUT, scope-gated)."""

    from __future__ import annotations

    from typing import Annotated

    from fastapi import APIRouter, Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from resource_server.api.schemas.reading_speed import (
        ReadingSpeedOut,
        ReadingSpeedUpsert,
    )
    from resource_server.auth.models import Principal
    from resource_server.auth.oidc_bearer import require_scope
    from resource_server.core.database import get_session
    from resource_server.services import reading_speed_service

    router = APIRouter(tags=["reading-speed"])


    @router.get("/reading-speed", response_model=ReadingSpeedOut)
    async def get_reading_speed(
        session: Annotated[AsyncSession, Depends(get_session)],
        principal: Annotated[Principal, Depends(require_scope("reading-speed:read"))],
    ) -> ReadingSpeedOut:
        row = await reading_speed_service.get_for_user(session, principal.subject)
        return ReadingSpeedOut(pages_per_hour=row.pages_per_hour)


    @router.put("/reading-speed", response_model=ReadingSpeedOut)
    async def put_reading_speed(
        payload: ReadingSpeedUpsert,
        session: Annotated[AsyncSession, Depends(get_session)],
        principal: Annotated[Principal, Depends(require_scope("reading-speed:write"))],
    ) -> ReadingSpeedOut:
        row = await reading_speed_service.upsert(
            session, principal.subject, payload.pages_per_hour
        )
        return ReadingSpeedOut(pages_per_hour=row.pages_per_hour)
    ```
  - [x] Wire the router into the v1 prefix wrapper. Edit `services/resource-server/src/resource_server/api/v1/__init__.py`:
    ```python
    from fastapi import APIRouter

    from resource_server.api.reading_speed import router as reading_speed_router

    router = APIRouter(prefix="/v1")
    router.include_router(reading_speed_router)
    ```
  - [x] Verify `main.py` requires NO edits — `v1_router` is already mounted on `app` at Story 3.1's line 67.

- [x] **Task 8 — Author SQLModel-level tests** (AC: #11)
  - [x] Create `services/resource-server/tests/models/` and `tests/models/entities/` directories with empty `__init__.py` files.
  - [x] Author `services/resource-server/tests/models/entities/test_reading_speed.py`. 5+ tests per AC #11 bullet list:
    1. `test_insert_and_read_back_round_trip`
    2. `test_unique_constraint_on_sub_rejects_duplicate_insert` → expect `sqlalchemy.exc.IntegrityError` (wrap in `pytest.raises`).
    3. `test_updated_at_bumps_on_update` — use `await asyncio.sleep(0.005)` between commits (or freezegun) so the timestamps differ; assert `row.updated_at > prior_updated_at`.
    4. `test_created_at_stable_on_update` — same row, two updates; assert `row.created_at` unchanged.
    5. `test_field_constraints` — `max_length=255` on `sub` (SQLite is permissive but the column metadata should expose `length=255`); `nullable=False` on `pages_per_hour` enforced by INSERT-with-NULL raising.
  - [x] Use the existing `engine` + `session` fixtures from `tests/conftest.py:75-99`. Verify by running the tests in isolation: `uv run pytest tests/models/ -v`.

- [x] **Task 9 — Author service-level tests** (AC: #11)
  - [x] Create `services/resource-server/tests/services/` directory if absent (it is — verified: only `tests/api/`, `tests/auth/`, `tests/core/`, `tests/observability/` exist).
  - [x] Author `services/resource-server/tests/services/test_reading_speed_service.py`. 5+ tests:
    1. `test_get_for_user_returns_existing_row`
    2. `test_get_for_user_raises_when_row_absent` → `pytest.raises(ReadingSpeedUnsetError)`.
    3. `test_upsert_insert_path_creates_new_row`
    4. `test_upsert_update_path_bumps_value_and_updated_at`
    5. `test_upsert_cross_user_isolation` — call `upsert(sub_a, 30)` then `upsert(sub_b, 50)`; assert two rows exist, each carrying its own value; calling `get_for_user(sub_a)` returns 30, `get_for_user(sub_b)` returns 50.
  - [x] Use the `session` fixture from `tests/conftest.py:90-98`.

- [x] **Task 10 — Author request-layer (API) tests** (AC: #11)
  - [x] Author `services/resource-server/tests/api/test_reading_speed.py`. Use the synthetic-IdP harness pattern established by Story 3.2:
    ```python
    from .auth.synthetic_idp import build_synthetic_rs_idp, SyntheticRsIdp
    ```
    Wait — the existing `synthetic_idp.py` lives at `tests/auth/synthetic_idp.py`. The API test under `tests/api/` imports it via relative-path `..auth.synthetic_idp` OR absolute `tests.auth.synthetic_idp` (the latter requires `tests/__init__.py` — verified present at `services/resource-server/tests/__init__.py`). Use the absolute import for clarity.
  - [x] Use the `client` fixture from `tests/conftest.py:101-111` which overrides `get_session` via `app.dependency_overrides`. The fixture is per-test, so each test starts with an empty DB.
  - [x] **Add a module-scoped `synthetic_rs_idp` fixture** that wraps `build_synthetic_rs_idp(monkeypatch)` (the existing one in `tests/auth/test_oidc_bearer.py:96-100` is module-private; we need a fresh fixture in this test file because pytest fixtures are not auto-shared across test files at module scope — copy the 3-line fixture).
  - [x] 13+ tests per AC #11 bullet list. Each test mints a token via `synthetic_rs_idp.make_access_token(sub=..., scope=...)` and calls the endpoint via the `client` fixture with `Authorization: Bearer <token>`.
  - [x] Helper for envelope assertion: `assert response.json() == {"errorCode": "<expected>", "message": "<msg>", "detail": <expected_detail>}` — match the body shape exactly, not just the errorCode (catches regressions in the handler).

- [x] **Task 11 — Update `tests/core/test_errors.py` for INVALID_INPUT** (AC: #5, #13)
  - [x] Read `services/resource-server/tests/core/test_errors.py` and identify every test asserting on `VALIDATION_ERROR` wire-value envelopes.
  - [x] Update those assertions to expect:
    - `errorCode == "invalid_input"`
    - `status_code == 422`
    - `detail` is a list of Pydantic error dicts, each WITHOUT the `input` key (the sanitization from BFF Story 1.3 P3).
  - [x] Capture the count of updated tests in the dev log.

- [x] **Task 12 — Run the full gate sequence** (AC: #14, #15)
  - [x] From `services/resource-server/`:
    - [x] `uv sync --frozen` → 0.
    - [x] `uv run ruff check` → 0 findings.
    - [x] `uv run ruff format --check` → 0 reformats needed.
    - [x] `uv run ty check` → 0 errors.
    - [x] `uv run pytest --cov` → all pass; whole-suite coverage ≥ 90%. Capture the post-change %.
    - [x] `uv run pytest --cov=resource_server.api.reading_speed --cov=resource_server.services.reading_speed_service --cov-report=term-missing tests/api/test_reading_speed.py tests/services/test_reading_speed_service.py` → confirm per-file coverage ≥ 90%.
    - [x] Alembic round-trip: `RS_DATABASE_URL=sqlite+aiosqlite:///./rs-dev.db uv run alembic upgrade head` → 0; `RS_DATABASE_URL=sqlite+aiosqlite:///./rs-dev.db uv run alembic downgrade base` → 0; `rm -f rs-dev.db*`.
  - [x] `git diff --stat` to verify the change set is scoped to: `core/errors.py`, `core/exceptions.py` (NEW), `models/entities/{__init__.py,reading_speed.py}`, `alembic/versions/0001_init_init_reading_speeds.py` (NEW), `api/schemas/__init__.py` (NEW), `api/schemas/reading_speed.py` (NEW), `api/reading_speed.py` (NEW), `api/v1/__init__.py`, `services/reading_speed_service.py` (NEW), `tests/models/__init__.py` (NEW if absent), `tests/models/entities/__init__.py` (NEW), `tests/models/entities/test_reading_speed.py` (NEW), `tests/services/__init__.py` (NEW), `tests/services/test_reading_speed_service.py` (NEW), `tests/api/test_reading_speed.py` (NEW), `tests/core/test_errors.py` (update), plus the BMAD bookkeeping files.

- [x] **Task 13 — Bookkeeping** (AC: #15)
  - [x] Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: flip `3-3-rs-reading-speed-model-migration-v1-reading-speed-get-put-scope-gated` `ready-for-dev` → `in-progress` at start, → `review` at end.
  - [x] If new defers surface during code review, append them under `## Deferred from: code review of 3-3-...` in `deferred-work.md`. Continue from D65 (the current ceiling from Story 3.2 review).
  - [x] Verify untouched-files list per AC #15.

### Review Findings

Code review run on 2026-05-17 against `baseline_commit: 119a25a` (the 2 dev-story commits on `worktree-story-3.3`: `f23cb3e` story creation + `7cf79ea` implementation). Three adversarial review layers ran in parallel via the Agent tool: Blind Hunter (diff-only), Edge Case Hunter (diff + project read), Acceptance Auditor (diff + spec + project read). Findings normalized, deduped (1 → race-condition was caught by both Blind + Edge), and triaged.

**Summary: 0 decision-needed, 3 patches applied, 5 deferred (D66–D70), 12 dismissed as noise.**

#### Patches — applied 2026-05-17

- [x] [Review][Patch] **CR1 — `ReadingSpeedUpsert` admits unknown fields silently** [`services/resource-server/src/resource_server/api/schemas/reading_speed.py`] — Blind Hunter MED. Pydantic v2 defaults to `extra="ignore"`, so a client posting `{"pages_per_hour": 30, "sub": "victim-sub", "id": 999}` is silently accepted (extras dropped). Not a privilege escalation vector today (the router pulls `sub` from `principal.subject`, never from the body), but it masks client bugs and weakens the API contract. Added `model_config = ConfigDict(extra="forbid")`. **APPLIED.** Added one test pinning that `{"pages_per_hour": 30, "sub": "victim"}` is rejected as 422 `invalid_input`.

- [x] [Review][Patch] **CR2 — Float-shape `pages_per_hour` not pinned by tests** [`services/resource-server/tests/api/test_reading_speed.py`] — Edge Case Hunter MED. Tests cover `0`, `-1`, `-100`, `"thirty"`, missing-field — but not floats. Pydantic v2's strict-int default rejects `1.5` (`int_from_float` error) and the JSON deserializer handles `30.0` as float→int coercion (which Pydantic strict-int also rejects in `strict` mode but accepts in lax). Added two tests pinning the current behavior: `1.5` is rejected as 422, `30.0` is rejected as 422 (Pydantic v2's `int` is strict by default for JSON-source). **APPLIED.**

- [x] [Review][Patch] **CR3 — `created_at == updated_at` after INSERT not pinned** [`services/resource-server/tests/services/test_reading_speed_service.py`] — Edge Case Hunter LOW. The existing tests verify `updated_at` bumps on UPDATE and `created_at` is stable on UPDATE, but no test verifies that immediately after INSERT, `row.created_at == row.updated_at` (within a tiny tolerance). A future change to `default_factory` (e.g., decoupling the two timestamps) could silently introduce a skew. Added one test asserting `(updated_at - created_at).total_seconds() < 0.01` after a fresh `upsert(...)` insert. **APPLIED.**

#### Deferred

See `_bmad-output/implementation-artifacts/deferred-work.md` "Deferred from: code review of 3-3-..." (D66–D70) for full text.

- [x] [Review][Defer] **D66 — No upper bound on `pages_per_hour`** [`services/resource-server/src/resource_server/api/schemas/reading_speed.py`] — Blind Hunter MED. `Field(ge=1)` allows arbitrary positives up to int64. A malicious client posting `pages_per_hour=999999999999` is persisted and later read back; downstream Story 4.1 estimate math (`pages / pages_per_hour * 60`) would yield a tiny "minutes" value (~0). Belongs to Story 4.1 (where estimate's behavior under degenerate inputs is the load-bearing concern), or a security-review pass. Real fix: `Field(ge=1, le=10000)` — 10000 pages/hour is well above any plausible human reading speed (~600 pages/hour is the elite-skim ceiling). **Severity:** medium (no current consumer; first real-world exposure is Story 4.1).
- [x] [Review][Defer] **D67 — Empty `sub` (RFC-permitted) yields 412 not 401** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:89-90` + `services/resource-server/src/resource_server/api/reading_speed.py:27`] — Edge Case Hunter LOW. Story 3.2's defensive `claims.get("sub", "")` means a JWT with `sub: ""` (RFC 7519 permits but Keycloak doesn't emit) passes `_validate_access_token`'s `require=["sub"]` check (which validates presence not non-emptiness), then `get_for_user(session, "")` returns 412 `reading_speed_unset`. Architecturally an empty `sub` should fail authentication (401). Real fix: reject empty `sub` in `_principal_from_claims` and emit `SESSION_EXPIRED`. Not user-facing because Keycloak doesn't issue empty subs; belongs to a security-review pass (Story 5.2). **Severity:** low (theoretical attack surface; no real-world hit).
- [x] [Review][Defer] **D68 — `validation_exception_handler` defensiveness gaps** [`services/resource-server/src/resource_server/core/errors.py:77-97`] — Edge Case Hunter LOW (two related items). (a) Only one direct-handler test (`tests/core/test_errors.py::test_validation_error_via_http`) covers the registration; a future story that registers a different `RequestValidationError` handler later in app setup would silently replace this one without test failure. (b) Sanitization uses a denylist (`if k != "input"`) — a future Pydantic version adding a sensitive field (e.g., `ctx` already exists and can echo input fragments) would leak through. Real fix: assert handler registration in `tests/core/test_errors.py`, and switch to an allowlist of safe keys (`{"loc", "msg", "type", "url"}`). Belongs to a test-quality + security-review pass. **Severity:** low (defensive coding; current Pydantic version is sanitized correctly).
- [x] [Review][Defer] **D69 — `sa.DateTime()` not `timezone=True` + ORM-only `onupdate` callable** [`services/resource-server/alembic/versions/0001_init_init_reading_speeds.py:14-15` + `services/resource-server/src/resource_server/models/entities/reading_speed.py:30-33`] — Blind Hunter LOW (two related items). (a) Migration uses `sa.DateTime()` without `timezone=True` — model stores `datetime.now(UTC)` (tz-aware), SQLite stores ISO string and naïvely round-trips, but a future PostgreSQL/MariaDB deployment would mis-convert (TIMESTAMPTZ vs TIMESTAMP). (b) `sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)}` only fires when SQLAlchemy issues an UPDATE through the ORM — raw `session.execute(update(...))` or future Alembic data migrations would NOT bump `updated_at`. Real fix: `sa.DateTime(timezone=True)` + `server_default=func.now(), onupdate=func.now()`. Belongs to a cross-database-portability pass. **Severity:** low (SQLite is fine today; this story's surface is ORM-only via SQLModel).
- [x] [Review][Defer] **D70 — Upsert race condition is documented but not behaviorally tested** [`services/resource-server/src/resource_server/services/reading_speed_service.py:23-46`] — Blind Hunter HIGH + Edge Case Hunter MED (deduped). The SELECT-then-INSERT pattern is not atomic; two concurrent PUTs for the same `sub` can both pass the SELECT, both attempt INSERT, the second raises `IntegrityError` → 500. The service docstring explicitly endorses this ("500 is preferable to silent data loss") per the spec's design choice. No test exercises the path. A future refactor (e.g., upgrading to PostgreSQL and adopting `ON CONFLICT(sub) DO UPDATE`) would need to verify behavior at the boundary. Real fix: add a test that triggers `IntegrityError` (`session.add` two rows with same `sub` directly) and asserts the surfaced 500 envelope, OR switch to `INSERT … ON CONFLICT(sub) DO UPDATE` (dialect-aware via SQLAlchemy's `dialect.insert()`). Belongs to a test-quality / hardening pass. **Severity:** medium (real race exists; current SPA single-click pattern makes it rare).

#### Dismissed (12)

- **`_build_error_body` accepts `list[dict]` as detail** — Blind Hunter [QUESTION]. Verified: the signature is `detail: Any = None` (line 49 of `core/errors.py`); JSON serialization handles list[dict] natively. The BFF's equivalent handler does the same; pattern is well-established.
- **`unique=True` flag test brittleness** — Blind Hunter [QUESTION]. The metadata test passes; SQLModel's `Field(index=True, unique=True)` does set `column.unique` on the underlying `Column` object in current SQLModel (verified by test passing).
- **Tests rely on `session` fixture not in diff** — Blind Hunter MED. The `session` fixture exists in `tests/conftest.py` from Story 3.1 (drops + recreates `SQLModel.metadata` after each test, line 96–98 — verified by reading conftest). Per-test isolation is correct.
- **Data leakage across tests via shared `sub` values** — Blind Hunter MED. Same as above: the `session` fixture drops + recreates the schema per test, so cross-test contamination via reused `sub` values cannot happen.
- **`detail`-list type change is a wire contract change** — Acceptance Auditor CONCERN. Intentional per the spec; only consumer is the test suite + future BFF Story 3.5's `ResourceServerClient` which is built against the new shape.
- **`VALIDATION_ERROR` dead enum member** — Blind Hunter LOW. Removing it would break the `tests/core/test_errors.py::test_error_code_validation_error` test which still references the archetype-emitted code; keeping it preserves backward-compatible enum surface for any archetype-internal consumer.
- **`ReadingSpeedUnsetError.__init__` accepts unused `detail` parameter** — Blind Hunter NIT. Consistent with `AppException`'s signature; allows future callers to pass a sanitized detail string if needed.
- **Re-construct `ReadingSpeedOut` despite `response_model` auto-coercion** — Blind Hunter NIT. Intentional explicit construction guards against future SQLModel field additions leaking via duck-typing.
- **`from_attributes=True` not set on `ReadingSpeedOut`** — Blind Hunter NIT. Router constructs explicitly via kwarg, never coerces from an attribute-bearing object.
- **`session.add(row)` on UPDATE path is redundant** — Edge Case Hunter NIT. SQLAlchemy auto-tracks loaded objects' attribute changes; the explicit `add` is harmless and signals intent.
- **`scalar_one_or_none()` vs `scalars().first()`** — Edge Case Hunter NIT. Stylistic; UNIQUE index guarantees at-most-one-row, so `.first()` is correct. The BFF uses the same pattern.
- **Filename `0001_init_init_reading_speeds.py` carries redundant `init_init`** — Edge Case Hunter NIT. Alembic autogen-message + revision-id collision artifact; matches BFF Story 1.4's `0001_init_init_sessions_and_auth_states.py` convention.

#### Acceptance Auditor verdict table

| AC | Status | Note |
|----|--------|------|
| 1  | MET | `ReadingSpeed` SQLModel exists with all required columns + UNIQUE index on `sub`; registered in `models/entities/__init__.py::__all__`. |
| 2  | MET | `ReadingSpeedOut(pages_per_hour: int)` + `ReadingSpeedUpsert(pages_per_hour: int = Field(ge=1))` at `api/schemas/reading_speed.py`; CR1 adds `extra="forbid"`. |
| 3  | MET | Migration at `alembic/versions/0001_init_init_reading_speeds.py` with `revision = "0001_init"`, `down_revision = None`, `create_table` + `create_index unique=True`, `import sqlmodel` restored (the autogen gotcha). Smoke-tested upgrade/downgrade. |
| 4  | MET | `core/exceptions.py` is NEW; `ReadingSpeedUnsetError(AppException)`. |
| 5  | MET | `ErrorCode.READING_SPEED_UNSET` (412) + `ErrorCode.INVALID_INPUT` (422); `validation_exception_handler` flipped to emit `invalid_input` with per-error `input`-field sanitization. |
| 6  | MET | `services/reading_speed_service.py` with `get_for_user` raising `ReadingSpeedUnsetError` and `upsert` doing SELECT-then-INSERT-or-UPDATE. Async pattern is `await session.execute(select(...)).scalars().first()` (BFF parity; spec's `session.exec(...)` was sync-only). |
| 7  | MET | `api/reading_speed.py` with scope-gated GET + PUT handlers; identity from `principal.subject`. |
| 8  | MET | `get_session` reused from Story 3.1. |
| 9  | MET | 412 returned for row-absent; test pins envelope `{"errorCode": "reading_speed_unset", "message": "...", "detail": None}`. |
| 10 | MET | `sub` is read from JWT only; verified by cross-user-isolation test + handler signatures. |
| 11 | MET | 5+5+15 tests = 25 (above spec's 23 minimum); per-file coverage 100% for both `api.reading_speed` and `services.reading_speed_service` (>> 90% gate). CR1/CR2/CR3 add 4 more tests; total 29. |
| 12 | MET | `main.py` not modified; v1 wrapper at `api/v1/__init__.py` is the single integration point. |
| 13 | MET | All 209 Story-3.1+3.2 tests continue green; only `tests/core/test_errors.py::test_validation_error_via_http` was updated for the wire-value flip. |
| 14 | MET | After CR1–CR3 applied: ruff/format/ty clean; pytest 238 passed; coverage 98.07% (oidc_bearer.py + api.reading_speed.py + services.reading_speed_service.py: 100% each). Alembic round-trip verified. |
| 15 | MET | No prohibited paths touched (CLAUDE.md, root files, compose, keycloak, services/bff, spa, e2e, RS Dockerfile/entrypoint/main.py/auth/observability/etc. all bit-for-bit identical). |

**Verdict:** All 15 ACs **MET** after CR1–CR3 applied. Story moves `review` → `done`.

## Dev Notes

### What this story is — and is not

**This story lands the first real domain surface on the Resource Server.** It introduces:
- The `reading_speeds` table + SQLModel + Alembic migration (the RS's first real schema).
- The `/v1/reading-speed` GET + PUT handlers, scope-gated via Story 3.2's `require_scope` factory.
- Domain exception `ReadingSpeedUnsetError` (the architecture-prescribed `core/exceptions.py` pattern at lines 735–749 — first instance on the RS).
- The lower_snake `invalid_input` wire value (replacing the archetype's emitted `VALIDATION_ERROR` for the RS's project-specific posture).
- New `ErrorCode` members: `READING_SPEED_UNSET` (412), `INVALID_INPUT` (422).

**Explicitly NOT in scope:**

- **No `/v1/test/reset` endpoint.** Story 3.4.
- **No `POST /v1/estimate` endpoint** or `EstimateService`. Story 4.1.
- **No BFF `/v1/reading-speed` proxy** or `ResourceServerClient`. Story 3.5.
- **No SPA `SettingsView` / `ReadingSpeedService`.** Story 3.5.
- **No `e2e` compose-profile additions.** Story 3.6.
- **No deletion of `auth/entra.py`.** It remains vestigial until a coordinated post-Story-4.1 cleanup.
- **No changes to OTEL/Prometheus stack.** Inert per the 2026-05-14 sprint-change cut.
- **No new ErrorCode members beyond `READING_SPEED_UNSET` + `INVALID_INPUT`.** `RESOURCE_SERVER_UNAVAILABLE` lands on the BFF in Story 3.5; `BOOK_NOT_FOUND` / `AUTH_STATE_INVALID` / `CSRF_INVALID` are BFF-only (and `AUTH_STATE_INVALID` / `CSRF_INVALID` were already added to the BFF in Epic 1).

### Architectural foundation (line references — single source of truth)

- **§C3 lines 382–388** — RS endpoint table. `GET /v1/reading-speed` requires `reading-speed:read`; `PUT /v1/reading-speed` requires `reading-speed:write`. "All RS endpoints read user identity from the JWT `sub` claim — no path or body identifier accepted for user."
- **§C5 lines 396–409** — `ErrorCode` enum. `READING_SPEED_UNSET = "reading_speed_unset"` (412); `INVALID_INPUT = "invalid_input"` (422). Wire values are lower_snake.
- **§C7 line 418** — "Distinct API Pydantic models, not SQLModel ORM classes serialized directly." → Hence `ReadingSpeedOut` + `ReadingSpeedUpsert` are separate from the `ReadingSpeed` SQLModel.
- **§Format Patterns line 686** — 412 wire-row. **§Format Patterns line 690** — "404 on `GET /v1/reading-speed` is not an error in the same sense as a missing book — it carries `errorCode: "reading_speed_unset"` so the SPA can distinguish from a transport-level 404." → Hence 412 not 404.
- **§Communication Patterns lines 735–749** — "Business code raises **domain exceptions** from `core/exceptions.py`, never `HTTPException`. A single exception handler in `core/error_handlers.py` catches `BFFError` and emits the archetype envelope." → The RS uses `AppException` (not `BFFError` — the archetype's emission name); subclassing `AppException` with a fixed `ErrorCode` matches the prescribed pattern.
- **§Naming Patterns lines 546–552** — Database conventions. Tables plural snake_case (`reading_speeds`); columns `snake_case`; PK `id` integer auto-increment; `sub` VARCHAR(255) indexed; `ix_<table>_<columns>` (Alembic autogenerate default); `reading_speeds.sub` explicitly enumerated as one of the indexed columns. UTC naive `DATETIME`; `created_at` + `updated_at` on every persisted entity.
- **§Implementation Patterns lines 556** — "/v1/reading-speed (singular because it's a singleton per user, not a collection)" — path is kebab-case singular, distinct from `/v1/books` which is plural collection.
- **§Implementation Patterns lines 612–615** — "One service module per domain concept. `services/reading_speed_service.py`. Exceptions live in `core/exceptions.py`. Tests mirror source paths."
- **§Architectural Boundaries lines 1127** — "Resource Server ↔ Keycloak: JWKS endpoint only, periodically cached. No session, no token exchange, no admin API." — relevant because the RS reads identity from the JWT directly (via Story 3.2's `Principal`).
- **§Architectural Boundaries line 1141** — "`sub` is the only identifier that crosses service boundaries."
- **§Requirements to Structure Mapping lines 1158–1163 (FR-SPEED-01)** — "Resource Server: `src/resource_server/api/reading_speed.py` (GET/PUT, scope-enforced), `src/resource_server/services/reading_speed_service.py`, `src/resource_server/db/models/reading_speed.py`, Alembic migration."
   - **Path discrepancy:** architecture line 1160 says `db/models/reading_speed.py`; Story 3.1's actual scaffold landed `models/entities/` (the archetype's emission name — verified at `services/resource-server/src/resource_server/models/entities/`). **Use the actual scaffolded path** (`models/entities/reading_speed.py`) — cross-service consistency with the BFF, which also uses `models/entities/` (verified at `services/bff/src/bff/models/entities/`). Document the deviation in the dev log; the architecture line is a stale wishful-thinking spec that the archetype's actual emission overrode.

### Reading prior-story state (Story 3.1 + 3.2 carry-overs)

- **`ErrorCode` enum** (post-3.2): `INTERNAL_ERROR`, `VALIDATION_ERROR`, `BAD_REQUEST`, `NOT_FOUND`, `UNAUTHORIZED`, `FORBIDDEN` (archetype-emitted UPPER_SNAKE wire values) + `SERVICE_UNAVAILABLE`, `SESSION_EXPIRED`, `FORBIDDEN_SCOPE` (project-specific lower_snake). Story 3.3 adds `READING_SPEED_UNSET` + `INVALID_INPUT` in the project-specific block.
- **`validation_exception_handler`** currently emits `VALIDATION_ERROR` (UPPER_SNAKE). Story 3.3 flips it to `INVALID_INPUT` (lower_snake) — a contract change visible to consumers. **Update `tests/core/test_errors.py` accordingly** (AC #11, Task 11).
- **`AppException` in `core/errors.py:33`** — accepts `(error_code: ErrorCode, detail: str | None = None)`. `app_exception_handler` (lines 56–63) emits the envelope. Story 3.3 inherits this verbatim; `ReadingSpeedUnsetError(AppException)` plugs in with no new handler registration.
- **`oidc_bearer.require_scope(scope: str)`** (Story 3.2) — returns an async dependency producing `Principal` after JWT validation. `principal.subject` is the JWT `sub` claim. Story 3.3 uses `require_scope("reading-speed:read")` on GET and `require_scope("reading-speed:write")` on PUT.
- **`get_session`** (Story 3.1, `core/database.py:88-91`) — async dependency yielding `AsyncSession`. Story 3.3's handlers use it as a `Depends(...)` parameter.
- **`alembic/env.py`** (Story 3.1) — already imports `from resource_server.models import entities` so the new `ReadingSpeed` is auto-discovered for `--autogenerate`. No env.py changes needed.
- **Test infrastructure** (`tests/conftest.py`) — provides `engine`, `session`, `client` fixtures. The `client` fixture overrides `get_session` via `app.dependency_overrides[get_session]` so each test uses the per-test in-memory SQLite. Story 3.3's API tests reuse `client` verbatim.
- **Synthetic-IdP harness** (`tests/auth/synthetic_idp.py`, Story 3.2) — exports `build_synthetic_rs_idp(monkeypatch, ...)` that monkeypatches `jwt.PyJWKClient.fetch_data` + `settings.oidc_*`. Reusable from `tests/api/test_reading_speed.py` via `from tests.auth.synthetic_idp import build_synthetic_rs_idp, SyntheticRsIdp` (the project's `pyproject.toml`'s pytest config sets `testpaths = ["tests"]` and the absolute import works because `tests/__init__.py` exists).

### Required-fail-fast OIDC config (carries over from Story 3.1)

`AppSettings._validate_oidc_required_fail_fast` (verified at `services/resource-server/src/resource_server/core/config.py:114-139`) raises if `OIDC_ISSUER_URL` / `OIDC_JWKS_URL` / `OIDC_AUDIENCE` are empty / whitespace-only. The `tests/conftest.py:20-25` pre-set non-secret placeholder env vars so `AppSettings()` constructs successfully at module import time. Story 3.3's tests do NOT need to interact with these settings directly — the synthetic-IdP fixture monkeypatches `oidc_bearer.settings.oidc_*` per-test (verified at `services/resource-server/tests/auth/synthetic_idp.py:202-204`).

### The "404 vs 412" decision rationale

The architecture explicitly chose 412 over 404 for "row absent" (line 686 + line 690). Rationale recap:
- 412 ("Precondition Failed") communicates "the underlying resource is missing a *precondition*" — semantically, the user must set their reading speed before they can use estimate-related features.
- 404 would conflate "no row" with "wrong URL" and would force the SPA to inspect the body to distinguish.
- The error envelope's `errorCode: "reading_speed_unset"` makes the distinction explicit in the wire format, which the SPA's `AppError` discriminated union (architecture line 718) keys on.

**Do NOT return 404 for the missing-row case.** Do not be tempted to use FastAPI's `status_code=status.HTTP_404_NOT_FOUND` — the `ReadingSpeedUnsetError` → `app_exception_handler` chain emits 412 because that is the `ErrorCode.READING_SPEED_UNSET.http_status` value.

### Pydantic v2 boundary specifics

- `Field(ge=1)` on `ReadingSpeedUpsert.pages_per_hour` is the modern Pydantic v2 syntax. The archetype pins Pydantic v2 (verified via the existing `core/config.py` using `field_validator`/`model_validator` decorators from `pydantic`).
- A request body of `{"pages_per_hour": 0}` causes Pydantic to raise `ValidationError` BEFORE the handler runs; FastAPI converts that to `RequestValidationError`, which the updated `validation_exception_handler` (post-Task 1) maps to 422 `invalid_input`.
- A request body of `{"pages_per_hour": "thirty"}` (string instead of int) → same path; Pydantic's int-coercion rejects.
- A request body of `{}` → field-missing → same path.
- A request body of `{"pages_per_hour": 1}` → boundary-accept (≥1 means 1 is allowed). Worth a single test to pin the boundary.
- A request body of `{"pages_per_hour": 999999999}` → no upper bound enforced; the column is `int` (SQLite stores it). This is OK for v1 (no realistic user reads 1B pages/hour); a future `le=...` could be added later without a migration.

### Architecture's `models/dto/v1/` vs `api/schemas/` — which to use?

The architecture's directory listing (lines 968–1007) shows the RS has `db/models/` for SQLModels and (implicitly) no `api/schemas/` — the architecture's prose at line 418 just says "Distinct API Pydantic models" without prescribing a folder. The archetype's actual emission lays out `models/dto/v1/` (verified Story 3.1 retained this directory, empty).

**Decision: use `api/schemas/reading_speed.py`** (per the AC #2 verbatim). Rationale:
- The architecture's high-level wishful-thinking layout used `db/models/` for SQLModels but Story 3.1 landed `models/entities/` (the archetype's emission name); the architecture is a target spec, not the actual landed shape.
- `api/schemas/` is conventional in FastAPI shops and keeps DTOs adjacent to their consuming routers.
- The archetype-emitted `models/dto/v1/` is empty and unused by Story 3.1/3.2 — keeping it empty (or removing it in a future cleanup) is consistent with the post-`--no-demo` cleanup discipline that Story 3.1 established.

Document the choice in the dev log; either future cleanup (move to `models/dto/v1/`) or a one-line architectural amendment will reconcile.

### Anti-patterns to avoid

- **Do not raise `HTTPException`** in the router or service. Use `ReadingSpeedUnsetError` (which extends `AppException`); the existing handler emits the envelope.
- **Do not accept `sub` from the request body, path, or query.** Read it from `principal.subject` only. Cross-user isolation depends on this. If a future endpoint admits an admin-style "look up another user's row," it needs a separate scope (`reading-speed:admin`) — out of scope here.
- **Do not return the `ReadingSpeed` SQLModel directly as the FastAPI response.** Construct `ReadingSpeedOut(pages_per_hour=row.pages_per_hour)` explicitly. The `response_model=ReadingSpeedOut` argument on `@router.get`/`@router.put` is the safety net but the explicit construction makes the intent obvious.
- **Do not skip the `await session.refresh(row)` after commit.** Without it, the SQLModel instance's `id` / `updated_at` / `created_at` may not reflect the DB's final state (especially `updated_at` after an UPDATE, since the `onupdate` callable fires at flush time but the in-memory object may not be re-read).
- **Do not catch `IntegrityError` in `upsert`.** The UNIQUE constraint is a backstop; the surrounding `SELECT ... WHERE sub = :sub` already guarantees the insert path is taken only when no row exists. A 500 on a race is better than silent data loss.
- **Do not register `/reading-speed` on the production `app` directly in `main.py`.** Use the `v1_router` wrapper (architecture's API path convention is `/v1/<resource>`; the router prefix is `/v1` at the wrapper level, the `/reading-speed` handler is at the leaf level).
- **Do not introduce `NULL`-able `pages_per_hour`.** The column is NOT NULL; the singleton-per-user model means "no row" semantically equals "not set" (and the 412 path handles that). A nullable column would create three states (absent / NULL / set) for a two-state concept.
- **Do not log `pages_per_hour` values.** They're not PII per se but logging them adds noise without diagnostic value. Log `sub` (an opaque UUID-like identifier — architecture line 787) when correlation is needed, not the user's reading-speed number.
- **Do not commit the dev `rs-dev.db` SQLite file.** It's a smoke-test artifact; clean it up after AC #14's verification. Verify the repo's `.gitignore` excludes `*.db` (it does — Story 1.1's `.gitignore` is broad enough; verify by `git check-ignore -v rs-dev.db`).

### Naming and pattern compliance

- Python file names: `reading_speed.py` (snake_case, single underscore between words).
- Test file names: `test_reading_speed.py` mirroring source paths.
- Class names: `ReadingSpeed`, `ReadingSpeedOut`, `ReadingSpeedUpsert`, `ReadingSpeedUnsetError` (PascalCase).
- HTTP API path: `/v1/reading-speed` (kebab-case, singular per architecture line 556).
- JSON field names: `pages_per_hour` (snake_case; architecture line 560 — no case conversion at any boundary).
- Wire values: `reading_speed_unset`, `invalid_input` (lower_snake per architecture §C5).
- Migration filename: `0001_init_init_reading_speeds.py` (Alembic-default slug; matches BFF Story 1.4 convention).
- Index name: `ix_reading_speeds_sub` (Alembic autogenerate default; architecture line 551 explicit).

### Practical notes & gotchas

- **SQLite vs. MariaDB on `UNIQUE` violation**: both raise `sqlalchemy.exc.IntegrityError`. The unit test for AC #11 / Task 8 case 2 should use `pytest.raises(IntegrityError)` (not the SQLite-specific `IntegrityError` from `sqlite3` — SQLAlchemy wraps it).
- **`session.exec(...)` vs `session.execute(...)`**: SQLModel adds `exec(...)` which auto-unwraps the result for `select(Model)` queries. Use `.exec(...).first()` for "row or None" and `.exec(...).one()` only when "exactly one row is expected" (which we don't here — we use `.first()` and check for None). The BFF's pattern at `services/bff/src/bff/services/session_service.py` (verified by Story 1.5) uses `.exec(...)` consistently.
- **Async session lifecycle**: the `client` fixture in `tests/conftest.py:101-111` overrides `get_session` with a session that yields the test-DB session; commits inside the test write to the same in-memory SQLite. After each test, the engine fixture drops + re-creates `SQLModel.metadata` (`tests/conftest.py:96-98`) so the next test starts with an empty DB.
- **`datetime.now(UTC)` vs `datetime.utcnow()`**: use `datetime.now(UTC)` — `utcnow()` is deprecated in Python 3.12+ and removed in 3.14+ (the archetype pins 3.14). The BFF uses the same pattern (`services/bff/src/bff/models/entities/session.py:33` verified).
- **`from __future__ import annotations`**: not strictly required in Python 3.14 (PEP 649 deferred eval is the default), but the rest of the RS codebase uses it consistently for forward-ref safety. Add it to every new module for cross-service consistency.
- **Coverage interplay with `app/v1` empty router stays at 100%**: the `from resource_server.api.v1 import router` line in `main.py` was emitted by Story 3.1; this story adds a `router.include_router(reading_speed_router)` line in `api/v1/__init__.py`. The empty `api/v2/__init__.py` remains untouched; coverage for that file remains 100% (it's two lines: `from fastapi import APIRouter; router = APIRouter(prefix="/v2")`).

### Git intelligence (recent commits, last 5)

```
119a25a Merge story 3.2 — RS oidc_bearer plugin + scope enforcement + synthetic-IdP harness
ad578bf chore: 3.2 code review — CR1–CR7 applied, mark done, log D59–D65
5966b2a feat: 3.2 RS oidc_bearer plugin + require_scope + synthetic-IdP harness
f5b0bc0 chore(3.2): create story — RS oidc_bearer + scope enforcement + synthetic-IdP
2a35822 Merge story 3.1 — RS scaffold + baseline /health + compose default/dev
```

- Story 3.2 is merged; epic-3 is at `119a25a`. `worktree-story-3.2` was cleaned up.
- The current working branch is `worktree-story-3.3` (fresh worktree off epic-3 head).
- Story 3.3 builds directly on 3.2's surface; no other in-flight changes to merge.

### Latest tech information

- **SQLModel 0.0.37+** — confirmed pinned by archetype `pyproject.toml`. `Field(index=True, unique=True)` is the canonical way to declare a uniquely-indexed column.
- **Alembic 1.18.4+** — pinned by Story 3.1's `uv add alembic`. `revision --autogenerate` works against SQLModel-tagged metadata; the `alembic/env.py` already imports `entities` to populate it.
- **SQLAlchemy 2.x with async engine** — both `session.exec(select(...))` and `session.execute(select(...))` work; SQLModel's `exec` is preferred for type-narrowing of the result.
- **Pydantic 2.x** — `Field(ge=1)` enforces at validation time; rejection causes `RequestValidationError` which the (updated) `validation_exception_handler` maps to `invalid_input` 422.
- **FastAPI** — `Depends(require_scope("..."))` per Story 3.2; `response_model=...` enforces the response schema.

### Project Structure Notes

Expected post-story tree additions:

```
services/resource-server/
├── alembic/versions/
│   └── 0001_init_init_reading_speeds.py        # NEW (Task 3)
├── src/resource_server/
│   ├── api/
│   │   ├── reading_speed.py                    # NEW (Task 7)
│   │   ├── schemas/
│   │   │   ├── __init__.py                     # NEW (Task 5)
│   │   │   └── reading_speed.py                # NEW (Task 5)
│   │   └── v1/__init__.py                      # MODIFIED (include reading_speed_router)
│   ├── core/
│   │   ├── errors.py                           # MODIFIED (READING_SPEED_UNSET + INVALID_INPUT; handler flip)
│   │   └── exceptions.py                       # NEW (Task 4)
│   ├── models/entities/
│   │   ├── __init__.py                         # MODIFIED (ReadingSpeed export)
│   │   └── reading_speed.py                    # NEW (Task 2)
│   └── services/
│       └── reading_speed_service.py            # NEW (Task 6)
└── tests/
    ├── api/test_reading_speed.py               # NEW (Task 10)
    ├── core/test_errors.py                     # MODIFIED (Task 11)
    ├── models/                                 # NEW (Task 8)
    │   ├── __init__.py
    │   └── entities/
    │       ├── __init__.py
    │       └── test_reading_speed.py
    └── services/                               # NEW (Task 9)
        ├── __init__.py
        └── test_reading_speed_service.py
```

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.3` lines 1213–1280] — canonical story spec and Given/When/Then ACs.
- [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` AR1, AR8, AR15, AR19, AR20, AR25, AR29, AR33] — archetype mandate, RS data, repo structure, timeouts, schemas-distinct-from-SQLModels, ErrorCode envelope, env vars, backend test patterns.
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns` C3 lines 382–388, C5 lines 396–409, C6 lines 411–416, C7 line 418] — RS endpoint + scope table, ErrorCode enum, RS→Keycloak timeouts, distinct Pydantic models from SQLModels.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Communication Patterns` lines 735–749] — domain exceptions from `core/exceptions.py` (architecture's prescribed pattern; the architecture's `BFFError` example renames to `AppException` on the RS).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Format Patterns` lines 685–701] — HTTP status table (412 + `reading_speed_unset`); ISO-8601 timestamps; UTC naive DATETIME in DB.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Naming Patterns` lines 546–569] — database conventions (plural snake_case tables, `id` integer PK, `sub` VARCHAR(255) indexed, `ix_<table>_<col>` index names, `created_at` / `updated_at` on every entity), HTTP path conventions (kebab-case, singular for singletons).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Structural Patterns` lines 596–615] — service-tree layout, per-resource router, per-domain service module, exceptions in `core/exceptions.py`, tests mirror source.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Requirements to Structure Mapping` lines 1158–1163 (FR-SPEED-01)] — file-path map for the reading-speed feature (note path discrepancy: arch says `db/models/`; actual scaffold uses `models/entities/`).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Architectural Boundaries` lines 1092–1141] — RS reads identity from JWT `sub` only; never from body/path/query.
- [Source: `_bmad-output/implementation-artifacts/3-1-rs-scaffold-from-archetype-baseline-health-rs-in-compose-default-dev.md`] — Story 3.1 (RS scaffold + `/health` + AppSettings extensions). Read for the AppSettings fail-fast + database session helpers.
- [Source: `_bmad-output/implementation-artifacts/3-2-rs-oidc-bearer-auth-plugin-jwks-scope-enforcement-synthetic-idp-test-harness.md`] — Story 3.2 (oidc_bearer + require_scope + synthetic-IdP harness). Read for `require_scope` usage + synthetic_idp fixture pattern.
- [Source: `_bmad-output/implementation-artifacts/1-4-bff-session-and-auth-state-schema-alembic-migration.md`] — BFF's `0001_init` migration (Story 1.4) — the direct analog for Story 3.3's migration. Read for the autogenerate + revision-header conventions.
- [Source: `services/resource-server/src/resource_server/auth/oidc_bearer.py:103-128`] — `get_authenticated_principal`, `require_scope` (consumed by this story's handlers).
- [Source: `services/resource-server/src/resource_server/core/errors.py:9-32`] — `ErrorCode` enum (extended by this story); `AppException` class (subclassed by `ReadingSpeedUnsetError`).
- [Source: `services/resource-server/src/resource_server/core/database.py:74-91`] — `get_engine`, `get_session` (consumed by this story's handlers).
- [Source: `services/resource-server/alembic/env.py:23-26`] — already imports `entities` for autogenerate (no changes needed).
- [Source: `services/resource-server/tests/conftest.py:75-111`] — `engine`, `session`, `client` fixtures (consumed by this story's tests).
- [Source: `services/resource-server/tests/auth/synthetic_idp.py:1-220`] — synthetic-IdP test harness (consumed by this story's API tests).
- [Source: `services/bff/src/bff/models/entities/session.py:32-39`] — `created_at` + `updated_at` SQLModel pattern (mirrored by `ReadingSpeed`).
- [Source: `services/bff/alembic/versions/0001_init_init_sessions_and_auth_states.py:14-19`] — revision-header convention for `0001_init` (mirrored by Story 3.3's migration).
- [Source: `services/bff/src/bff/core/errors.py:58-76`] — `validation_exception_handler` with `input`-stripping sanitization (Story 1.3 P3 patch) — mirror this on the RS for INVALID_INPUT envelopes.
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md` D59–D65] — Story 3.2 review defers; none re-surface here (D60 JWKS cache, D61–D62 timeouts, D63 WWW-Authenticate, D64–D65 leeway/aud-list — all auth-layer concerns, untouched by Story 3.3).
- [Source: `CLAUDE.md` at repo root] — invoke Python as `python` (never `python3`).
- [Source: `services/resource-server/CLAUDE.md`] — strict-spec-adherence + Conventional-Commits (no scope syntax) + run all gates before each commit.
- [Source: `[[project-bmad-books-backend-archetype]]` — user memory] — backend archetype mandate.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code, bmad-dev-story workflow)

### Debug Log References

**Task 1 — `ErrorCode` extension + handler flip:** Added `READING_SPEED_UNSET` (412) + `INVALID_INPUT` (422). Flipped `validation_exception_handler` to emit lower_snake `invalid_input` with per-error `input`-field sanitization (mirrors BFF Story 1.3 review P3). Updated one test in `tests/core/test_errors.py::test_validation_error_via_http`.

**Task 2 — `ReadingSpeed` SQLModel:** Authored `models/entities/reading_speed.py` with the table conventions (`__tablename__ = "reading_speeds"`, `id` autoincrement PK, `sub` VARCHAR(255) `index=True, unique=True`, `pages_per_hour` NOT NULL, `created_at`/`updated_at` defaulting to `datetime.now(UTC)` with `onupdate` on the latter). Registered in `models/entities/__init__.py`.

**Task 3 — Alembic migration:** Generated via `uv run alembic revision --autogenerate -m "init reading_speeds"` (with placeholder OIDC env vars for AppSettings fail-fast). Renamed the file from `ee4111fcacd1_init_reading_speeds.py` → `0001_init_init_reading_speeds.py` and edited the revision identifier to `"0001_init"`; added the missing `import sqlmodel` line that autogenerate misses (line 26 references `sqlmodel.sql.sqltypes.AutoString` but no import was emitted); reformatted to match BFF Story 1.4 conventions. Smoke-tested: `alembic upgrade head` → `0001_init (head)`; `alembic downgrade base` → empty. Cleaned up `rs-dev.db`.

**Task 4 — `core/exceptions.py`:** New file with `ReadingSpeedUnsetError(AppException)`. No new handler registration; the archetype's `app_exception_handler` already catches `AppException` subclasses.

**Task 5 — `api/schemas/reading_speed.py`:** New `api/schemas/` package. `ReadingSpeedOut(BaseModel)` for responses; `ReadingSpeedUpsert(BaseModel)` with `pages_per_hour: int = Field(ge=1)` for the PUT body — Pydantic rejects non-positive values at the boundary.

**Task 6 — `services/reading_speed_service.py`:** Two async functions: `get_for_user(session, sub)` raising `ReadingSpeedUnsetError` on absent row; `upsert(session, sub, pages_per_hour)` with SELECT-then-INSERT-or-UPDATE. **Spec adjustment**: the spec's sample used SQLModel's `session.exec(...)` which is sync-Session-only; for `AsyncSession` the correct call is `await session.execute(select(...))` followed by `.scalars().first()` (verified pattern at `services/bff/src/bff/services/session_service.py:117`).

**Task 7 — `api/reading_speed.py` + v1 wiring:** Authored the router with GET + PUT handlers, both gated via `Depends(require_scope(...))`. Wired into `api/v1/__init__.py` via `router.include_router(reading_speed_router)`. `main.py` unmodified.

**Task 8 — SQLModel tests:** 5 tests in `tests/models/entities/test_reading_speed.py`: round-trip insert/read; UNIQUE rejection; `updated_at` bumps on UPDATE; `created_at` stable on UPDATE; column metadata (length=255, nullable=False, unique=True).

**Task 9 — Service tests:** 5 tests in `tests/services/test_reading_speed_service.py`: `get_for_user` happy/raise; `upsert` insert/update; cross-user isolation.

**Task 10 — API tests:** 15 tests in `tests/api/test_reading_speed.py` (13 unique + 3 parametrized = 15 collected): GET happy/412/403/401; PUT insert/update/403/422×3/401/boundary; cross-user isolation. Uses synthetic-IdP harness via absolute import `from tests.auth.synthetic_idp import ...`.

**Task 11 — `tests/core/test_errors.py` update:** Flipped one test (`test_validation_error_via_http`) from UPPER_SNAKE `VALIDATION_ERROR` to lower_snake `invalid_input` with sanitized detail list assertion.

**Task 12 — Final gate run:**
- `uv sync --frozen` → 0 (84 packages)
- `uv run ruff check` → All checks passed!
- `uv run ruff format --check` → 85 files already formatted
- `uv run ty check` → All checks passed!
- `uv run pytest --cov` → **234 passed**, coverage **98.05%** (209 baseline → 234 = +25 new tests)
- Per-file coverage on the new code paths → **100% / 100%** (api.reading_speed: 18/18; services.reading_speed_service: 23/23) — well above AC #11 ≥90% gate
- Alembic round-trip verified: `upgrade head` → `0001_init (head)`; `downgrade base` → empty. `rs-dev.db` cleaned up.

### Completion Notes List

- All 15 ACs satisfied. RS now serves `/v1/reading-speed` GET + PUT, scope-gated via Story 3.2's `require_scope` factory, with cross-user isolation enforced via `principal.subject` (JWT `sub` claim — never body/path/query, per arch line 388).
- `ReadingSpeed` SQLModel + Alembic migration `0001_init` lands the RS's first real schema. UNIQUE index on `sub` enforces singleton-per-user at the DB layer (defense-in-depth on top of the SELECT-then-INSERT pattern).
- `core/exceptions.py` is the new home for domain exceptions (arch §"Communication Patterns / Error handling" line 735–749). First instance: `ReadingSpeedUnsetError`. Subclassing `AppException` means the existing handler picks it up without new registration.
- **Wire-value flip from `VALIDATION_ERROR` to `invalid_input`** (Task 1): the archetype default contradicted arch §C5's lower_snake mandate. One existing test updated; no other consumers found.
- **Async query pattern adjustment**: spec used `session.exec(...)` (sync-Session-only); switched to `await session.execute(select(...)).scalars().first()` per BFF parity. Documented in the service module's docstring.
- Coverage of new code: **100%** (api.reading_speed.py 18/18; services.reading_speed_service.py 23/23). Whole-suite coverage 97.85% → **98.05%**.
- **No production-app router changes** outside `api/v1/__init__.py`'s one-line inclusion. `main.py` untouched.
- **No archetype regressions.** All 209 Story-3.1+3.2 tests continue green (one expected update for the wire-value flip).
- **No defers introduced.** D59–D65 from Story 3.2 review remain open as-is.
- **Adherence to `services/resource-server/CLAUDE.md`** verified: every gate green before commit; conventional-commit format without scope syntax.

### File List

**New files:**
- `services/resource-server/src/resource_server/core/exceptions.py` — `ReadingSpeedUnsetError(AppException)` (Task 4).
- `services/resource-server/src/resource_server/models/entities/reading_speed.py` — `ReadingSpeed` SQLModel (Task 2).
- `services/resource-server/src/resource_server/api/schemas/__init__.py` — package marker for `api/schemas/` (Task 5).
- `services/resource-server/src/resource_server/api/schemas/reading_speed.py` — `ReadingSpeedOut` + `ReadingSpeedUpsert(ge=1)` Pydantic DTOs (Task 5).
- `services/resource-server/src/resource_server/api/reading_speed.py` — FastAPI router, scope-gated GET + PUT (Task 7).
- `services/resource-server/src/resource_server/services/reading_speed_service.py` — `get_for_user` + `upsert` async services (Task 6).
- `services/resource-server/alembic/versions/0001_init_init_reading_speeds.py` — Alembic migration creating `reading_speeds` + `ix_reading_speeds_sub` UNIQUE index (Task 3).
- `services/resource-server/tests/models/__init__.py` (Task 8).
- `services/resource-server/tests/models/entities/__init__.py` (Task 8).
- `services/resource-server/tests/models/entities/test_reading_speed.py` — 5 tests (Task 8).
- `services/resource-server/tests/services/__init__.py` (Task 9).
- `services/resource-server/tests/services/test_reading_speed_service.py` — 5 tests (Task 9).
- `services/resource-server/tests/api/test_reading_speed.py` — 15 tests (Task 10).

**Modified files:**
- `services/resource-server/src/resource_server/core/errors.py` — added `READING_SPEED_UNSET` (412) + `INVALID_INPUT` (422); flipped `validation_exception_handler` to emit `invalid_input` with input-field sanitization (Task 1).
- `services/resource-server/src/resource_server/models/entities/__init__.py` — registered `ReadingSpeed` (Task 2).
- `services/resource-server/src/resource_server/api/v1/__init__.py` — `router.include_router(reading_speed_router)` (Task 7).
- `services/resource-server/tests/core/test_errors.py` — `test_validation_error_via_http` updated to expect `invalid_input` envelope with sanitized detail list (Task 11).

**BMAD bookkeeping:**
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status `ready-for-dev` → `in-progress` → `review`.
- `_bmad-output/implementation-artifacts/3-3-rs-reading-speed-model-migration-v1-reading-speed-get-put-scope-gated.md` — frontmatter + status header → `review`; all 62 task/subtask checkboxes ticked.

**Untouched (verified):** `CLAUDE.md`, root files, `docker-compose.yml`, `compose/*.yml`, `keycloak/**`, `services/bff/**`, `spa/**`, `e2e/**`, `services/resource-server/{Dockerfile,entrypoint.sh,.gitattributes,.env.example,pyproject.toml,uv.lock,alembic.ini,alembic/env.py,alembic/script.py.mako,src/resource_server/main.py,src/resource_server/aop/**,src/resource_server/api/health.py,src/resource_server/api/v2/**,src/resource_server/auth/**,src/resource_server/observability/**,src/resource_server/core/config.py,src/resource_server/core/database.py,src/resource_server/factories/**,src/resource_server/models/dto/**,tests/auth/**,tests/api/test_health.py,tests/api/test_cors.py,tests/aop/**,tests/observability/**,tests/conftest.py}` — bit-for-bit identical.
