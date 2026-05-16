---
status: ready-for-dev
story_key: 2-3-bff-extend-v1-test-reset-to-truncate-books
created: 2026-05-16
---

# Story 2.3: BFF — extend `/v1/test/reset` to truncate `books`

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a maintainer running E2E tests,
I want the BFF's `POST /v1/test/reset` endpoint (introduced in Story 1.12) to also truncate the `books` table,
so that J2 Playwright specs can rely on a deterministic empty list at the start of each test.

## Scope (read this first)

This story is a **one-table extension** of an already-shipped endpoint. The endpoint, its bearer gate, its CSRF exemption, its 401 envelope, its compose-profile gating, and its 22-scenario regression suite are all from Story 1.12 (`done`). Story 1.13 (`done`) added a sibling `GET /v1/test/session-debug` route to the same module — leave it untouched.

What you change in `services/bff/src/bff/api/test_reset.py`:

1. Add a third `await db.execute(_delete(entities.Book), execution_options={"synchronize_session": False})` to the `POST /v1/test/reset` handler's truncate sequence.
2. Extend the existing `test_reset_truncated` INFO log line so it carries `books_deleted=<n>` and the `tables=` list includes `books`.
3. Update the module docstring's "Endpoints provided when the gate is ON" bullet to say `books`, `sessions`, `auth_states` (currently lists only the latter two).

What you change in `services/bff/tests/api/test_test_reset.py`:

1. Add a `_seed_book_row(ctx, *, suffix)` helper plus `_count_books(ctx)` mirroring the existing session/auth-state helpers.
2. Update scenarios 11–14 + 17 + 18 + the trailing-slash regression (scenario 23) to seed and assert on the `books` table alongside the existing two.
3. Add ONE new scenario covering "books-only populated → 204; books=0; log reflects 0/0/N" (mirrors scenarios 12 and 13's pattern for the new table).

**Out of scope — DO NOT do these here:**

- No new bearer/auth/CSRF/compose work. Story 1.12 owns all of that.
- No changes to `bff/api/v1/__init__.py`, `bff/main.py`, or `bff/auth/csrf.py`.
- No CRUD endpoints — Story 2.2 owns `/v1/books` routes. This story does NOT depend on 2.2 (we only need the `Book` SQLModel + table from 2.1, which is already `ready-for-dev`).
- No Alembic migration — Story 2.1's `0002_add_books` already creates the table.
- No `BookOut`/`BookCreate`/`BookUpdate` schema work — Story 2.1 already authored those.
- No `/v1/test/session-debug` changes (Story 1.13's sibling route). Leave its body, log lines, and tests as-is.
- No `.env.example` / `compose/app.yml` / `compose/app.e2e.yml` changes — gating is unchanged.
- No new dependencies in `pyproject.toml`.

**Strict dependency:** Story 2.1 must be done before this story can pass tests (the `Book` entity must be importable from `bff.models.entities` and the `books` table must exist in SQLModel.metadata for the conftest's `create_all` to provision it). Story 2.2 is **not** required.

## Acceptance Criteria

**AC1 — `Book` is truncated alongside `sessions` and `auth_states`.**

Inspecting `services/bff/src/bff/api/test_reset.py::test_reset`, the happy-path block now executes THREE `db.execute(_delete(...))` calls before its single `commit`. Order: `Session`, `AuthState`, `Book`. (The order is arbitrary because no FK constraints exist between the three tables, but `Book` is appended last so the existing 1.12 diff is preserved and the new line is the only structural change — a clear `git blame` for Story 2.3.) Each `execute` uses the same `execution_options={"synchronize_session": False}` kwarg as the existing two.

**AC2 — The `test_reset_truncated` INFO log carries the new counter.**

The single `logger.info(...)` line in the happy path is updated to format:

```
test_reset_truncated tables=sessions,auth_states,books sessions_deleted=<N1> auth_states_deleted=<N2> books_deleted=<N3>
```

- `tables=` list literally contains the three table names comma-separated in the same order as the `execute` calls (Session, AuthState, Book → `sessions,auth_states,books`).
- The `books_deleted=<N3>` token comes from `getattr(books_result, "rowcount", -1)` — identical accessor pattern to the existing two counters (Story 1.12 Dev Notes documents why `getattr` over direct attribute access).

**AC3 — Successful invocation truncates all three tables in a single commit.**

Given:
- The gate is ON (`ENABLE_TEST_RESET=true`, `TEST_RESET_TOKEN` set to a known value).
- The `sessions` table holds `>0` rows AND `auth_states` holds `>0` rows AND `books` holds `>0` rows.

When `POST /v1/test/reset` is invoked with `Authorization: Bearer <token>` matching `TEST_RESET_TOKEN`:

- The response is `204 No Content` with an empty body and no `content-length` (RFC 7230 §3.3.2 — 204 omits content-length entirely; the existing scenario 11 already asserts this).
- The three `DELETE FROM <table>` statements run in one transaction (a single `await db.commit()`), so partial state is impossible at the DB level.
- Subsequent reads against any of the three tables return zero rows.
- The INFO log line described in AC2 fires once with the row counts that match the pre-state.

**AC4 — Books-only seed truncates only `books`.**

Given the gate is ON and `books` has `N>0` rows while `sessions` and `auth_states` are empty:

When `POST /v1/test/reset` runs with a valid bearer:

- Response is 204.
- `books` count after = 0.
- The INFO log carries `sessions_deleted=0 auth_states_deleted=0 books_deleted=N`.

This is the new test scenario (call it scenario 14b in the test file, or rename if a more natural placement exists in the AC10 matrix; the existing scenarios 12 / 13 / 14 already cover sessions-only / auth-states-only / both-non-books — this is the symmetric missing case).

**AC5 — Gating, bearer auth, CSRF exemption, and OpenAPI behavior are UNCHANGED.**

All 24 existing test scenarios from Story 1.12 + 1.13 in `services/bff/tests/api/test_test_reset.py` continue to pass without functional modification beyond the row-count assertion updates documented in AC6 below:

- Scenarios 1–3 (gate not registered when off / token empty / token whitespace): unchanged — still 404 on all methods.
- Scenarios 4–10 (auth-failure classifiers): unchanged — still 401 `session_expired` envelope.
- Scenario 11 (empty tables): updated to also assert `books_deleted=0` in the INFO log and `_count_books(ctx) == 0` pre/post.
- Scenario 15 (CSRF exemption — POST without CSRF material → 204): unchanged.
- Scenario 16 (CSRF non-regression — POST `/test/open` without CSRF → 403): unchanged.
- Scenario 19 (env token with whitespace): unchanged.
- Scenarios 20a/20b (OpenAPI schema lists / hides `/v1/test/reset`): unchanged.
- Scenarios 21/22 (startup INFO log present/absent): unchanged — the `test_reset_route_registered` line is emitted by `register_test_reset_router` and is not affected by handler-body changes.
- Scenario 23 (trailing-slash CSRF exemption regression): unchanged in shape, but the underlying 204 must still hold after `books` truncation runs against an empty-but-mounted table.
- All Story 1.13 `session-debug` scenarios (`test_session_debug_*`): unchanged — this story does not touch the GET route.

**AC6 — Existing scenarios 11, 12, 13, 14, 17 are extended with `books` assertions.**

For every scenario whose body currently asserts on `sessions_deleted=` / `auth_states_deleted=` substrings:

- Add a corresponding assertion that `books_deleted=<expected>` is present in the same INFO log record.
- Add a pre-and-post `_count_books(ctx)` assertion mirroring `_count_sessions(ctx)` / `_count_auth_states(ctx)`.
- For scenarios 12 / 13 / 14 / 17 (which currently seed only sessions, only auth_states, or both): the expected `books_deleted` value is `0` since those tests don't seed `Book` rows. The string `books_deleted=0` MUST appear in the log line — confirming the new counter formats correctly even when no books exist.
- For scenario 14 (both tables seeded): the test must NOT regress — adding `books_deleted=0` to the assertion suffices.
- For scenario 17 (idempotency): both successive POSTs must log `books_deleted=0` (no books seeded; symmetric with the existing assertions).

**AC7 — Test helper additions `_seed_book_row` and `_count_books`.**

Add to the helper block at the top of `services/bff/tests/api/test_test_reset.py` (alongside `_seed_session_row` / `_seed_auth_state_row` / `_count_sessions` / `_count_auth_states`):

```python
async def _seed_book_row(ctx: _AppContext, *, suffix: str) -> None:
    async with ctx.factory() as db:
        row = entities.Book(
            sub=f"sub-{suffix}",
            title=f"Book {suffix}",
            pages=100,
            # status defaults to "to-read"
        )
        db.add(row)
        await db.commit()


async def _count_books(ctx: _AppContext) -> int:
    async with ctx.factory() as db:
        result = await db.execute(select(entities.Book))
        return len(result.scalars().all())
```

- Mirrors `_seed_session_row` / `_seed_auth_state_row` exactly — same `async with ctx.factory() as db:` body, same commit pattern, same `entities.<Model>(...)` construction.
- Uses `sub=f"sub-{suffix}"` so seeded rows are easy to spot in caplog if debugging.
- Uses positional defaults from the SQLModel — `id` autoincrements (do NOT pass `id=`), `created_at`/`updated_at` populate from the `default_factory`, `status` defaults to `"to-read"` (Story 2.1 AC1).
- The `pages=100` value is arbitrary — the boundary models (`BookCreate`) reject `pages<=0`, but the SQLModel itself accepts any int (Story 2.1 Dev Notes — "positivity is a Pydantic-layer concern, not enforced here"). Any positive int matches the spec.

**AC8 — New scenario: books-only populated.**

Add a new test function `test_scenario_14b_correct_bearer_books_populated` (or similarly named — place it adjacent to scenario 14 in the file) that:

- Seeds 4 `Book` rows via `_seed_book_row` (suffix `s14b-0..3`).
- Does NOT seed sessions or auth_states.
- POSTs `/v1/test/reset` with the valid bearer.
- Asserts: response 204; `_count_books(ctx) == 0` post; INFO log contains `sessions_deleted=0 auth_states_deleted=0 books_deleted=4`.

The seed count `4` is deliberately distinct from the counts used in scenarios 12 (`3`), 13 (`2`), and 14 (`5/3`) to keep test failures easy to attribute via log-line inspection.

**AC9 — Module docstring reflects the new table.**

The `services/bff/src/bff/api/test_reset.py` module docstring's "Endpoints provided when the gate is ON" bullet currently reads:

```
- `POST /v1/test/reset` (Story 1.12) — truncates `sessions` and
  `auth_states`; returns 204. ...
```

Update to:

```
- `POST /v1/test/reset` (Story 1.12 + Story 2.3) — truncates `sessions`,
  `auth_states`, and `books`; returns 204. ...
```

The Story 2.3 cross-reference makes the diff explicit for future readers grepping the module for table-list ownership. Also append one line to the `References` block at the bottom of the docstring:

```
- epics.md §Story 2.3 (lines 854–878) — adds `books` to the truncate sequence.
```

The remainder of the docstring (gating, auth, safety notes, Story 1.13 `session-debug` section) stays exactly as-is.

**AC10 — Coverage and lint gates remain green.**

From `services/bff/`:

- `uv sync --frozen` → exit 0 (no dep changes; `pyproject.toml` untouched).
- `uv run ruff check` → clean.
- `uv run ruff format --check` → clean.
- `uv run ty check` → clean. The new `entities.Book` reference does NOT require a `# ty: ignore[...]` — the import works identically to the existing `entities.Session` / `entities.AuthState` references; if `ty` complains on `_delete(entities.Book)` it accepts the same comment shape used at session_service.py:206 (Story 1.4) but the existing two calls don't carry it, so the new line shouldn't need it either.
- `uv run pytest --cov` → all prior tests + updated test_reset tests pass; total coverage ≥ 90% (project gate per `pyproject.toml:86`).
- Coverage of `services/bff/src/bff/api/test_reset.py` remains ≥ 90% (Story 1.12 hit 100% on this module — the one-line addition + the docstring edit must not drop it below the gate).

The new test scenario plus the extended assertions add `~30 LOC` of test code; the suite count grows by exactly one. The current suite size (per Story 2.1's git intelligence) is ~360 tests, so this story lands the suite at ~361.

## Tasks / Subtasks

- [ ] **Task 1 — Verify Story 2.1 has landed (precondition check, AC10)**
  - [ ] Run `uv run python -c "from bff.models import entities; entities.Book"` from `services/bff/`. If this `ImportError`s, **STOP**: Story 2.1 has not landed yet and this story cannot pass tests. Coordinate with the maintainer.
  - [ ] Run `uv run alembic heads`. The head MUST be `0002_add_books` (Story 2.1's migration). If the head is `0001_init`, run `uv run alembic upgrade head` first.
  - [ ] Skim `services/bff/src/bff/models/entities/__init__.py` to confirm `Book` is in the imports and in `__all__`. (If 2.1 was implemented per its spec, both will be present.)

- [ ] **Task 2 — Add `Book` truncation to the handler (AC1, AC2)**
  - [ ] Open `services/bff/src/bff/api/test_reset.py`. Locate the `try:` block inside `test_reset` (around line 249 — the three-statement sequence: `sessions_result = await db.execute(...)`, `auth_states_result = await db.execute(...)`, `await db.commit()`).
  - [ ] Insert a third execute between the auth_states execute and the commit:
    ```python
    books_result = await db.execute(
        _delete(entities.Book),
        execution_options={"synchronize_session": False},
    )
    ```
    Keep the bare `_delete` import alias — it's already imported at module top as `from sqlalchemy import delete as _delete` (test_reset.py:75). No new imports needed; `entities.Book` resolves through the existing `from bff.models import entities` (test_reset.py:82).
  - [ ] After the three executes, the single `await db.commit()` line stays exactly where it is. The DB sees one transaction with three DELETEs (atomic from the DB's POV per Story 1.12 AC6).
  - [ ] In the success-path `logger.info(...)` call (~line 282), update the format string AND its arguments:
    - String: `"test_reset_truncated tables=sessions,auth_states,books sessions_deleted=%s auth_states_deleted=%s books_deleted=%s"`.
    - Compute `books_deleted = getattr(books_result, "rowcount", -1)` next to the existing two `sessions_deleted` / `auth_states_deleted` assignments.
    - Append `books_deleted` as the third positional arg to `logger.info`.
  - [ ] Re-read the function once to confirm no other code paths reference `sessions_result` or `auth_states_result`; the new `books_result` follows the same one-line-then-rowcount-pluck shape.

- [ ] **Task 3 — Update module docstring (AC9)**
  - [ ] In the docstring at the top of `services/bff/src/bff/api/test_reset.py`, find the line under "Endpoints provided when the gate is ON" describing `POST /v1/test/reset`. Change `"truncates `sessions` and `auth_states`"` to `"truncates `sessions`, `auth_states`, and `books`"` and update the attribution from `(Story 1.12)` to `(Story 1.12 + Story 2.3)`.
  - [ ] In the same docstring, near the handler implementation note that currently says `"Story 2.3 will extend this handler with a third DELETE for the `books` table; keep the structure ordered and explicit..."` — UPDATE this comment to past tense / present tense: `"Story 2.3 added the books DELETE; the structure remains ordered and explicit (one db.execute per table) so future tables follow the same pattern."` (The forward-pointer comment becomes a backwards-pointer comment — same code-archaeology value, accurate after this story lands.)
  - [ ] In the `References` block at the bottom of the docstring, append one line:
    ```
    - epics.md §Story 2.3 (lines 854–878) — adds `books` to the truncate sequence.
    ```

- [ ] **Task 4 — Add test helpers `_seed_book_row` and `_count_books` (AC7)**
  - [ ] Open `services/bff/tests/api/test_test_reset.py`. Find the helper block (lines 132–170) containing `_seed_session_row`, `_seed_auth_state_row`, `_count_sessions`, `_count_auth_states`.
  - [ ] Add `_seed_book_row` immediately after `_seed_auth_state_row` (keep table-alphabetical groupings within the seed and count helpers).
  - [ ] Add `_count_books` immediately after `_count_auth_states`.
  - [ ] Use the snippet provided in AC7 verbatim. The existing helpers use `select(entities.<Model>)` followed by `.scalars().all()` — match that idiom exactly.
  - [ ] Confirm `select` is already imported at the top of the test file (test_test_reset.py:25 imports `from sqlalchemy import select`).

- [ ] **Task 5 — Extend existing scenarios 11, 12, 13, 14, 17 (AC6)**
  - [ ] **Scenario 11** (`test_scenario_11_correct_bearer_empty_tables`):
    - Add `assert await _count_books(ctx) == 0` pre and post the POST call (mirroring the existing two pre/post asserts).
    - Update the `any(...)` log-assertion: append `and "books_deleted=0" in r.message` to the boolean.
  - [ ] **Scenario 12** (`test_scenario_12_correct_bearer_sessions_populated`):
    - Update the log assertion: change the boolean from `"sessions_deleted=3" in r.message and "auth_states_deleted=0" in r.message` to also include `"books_deleted=0" in r.message`.
    - Optional: add `assert await _count_books(ctx) == 0` post the POST — but since no books are seeded, this asserts the trivial case. Add it for symmetry with the new helper.
  - [ ] **Scenario 13** (`test_scenario_13_correct_bearer_auth_states_populated`): same treatment as scenario 12 — log assertion adds `"books_deleted=0"`.
  - [ ] **Scenario 14** (`test_scenario_14_correct_bearer_both_tables_populated`): same treatment — log assertion adds `"books_deleted=0"`. Optionally add `assert await _count_books(ctx) == 0` post.
  - [ ] **Scenario 17** (`test_scenario_17_idempotent_successive_calls`): no behavioral change needed since the test asserts on count of `truncated_logs` (== 2), not on the per-log message contents. **However**, the asserted log message format now includes `books_deleted=` — any other test that pattern-matches `test_reset_truncated` with the substring `tables=sessions,auth_states` will break because the new format reads `tables=sessions,auth_states,books`. Audit `caplog` substring matches: scenarios 11–14 use `sessions_deleted=` / `auth_states_deleted=` substrings (not the `tables=` substring), so they are immune. Scenario 17 only counts records — also immune. **No change to scenario 17 except verifying it still passes.**
  - [ ] **Scenario 23** (`test_scenario_23_trailing_slash_path_is_csrf_exempt_and_succeeds`): asserts on `response.status_code == 204` only — no log-substring assertion on `test_reset_truncated`. Verify it still passes; no code change needed.

- [ ] **Task 6 — Add new scenario for books-only seed (AC4, AC8)**
  - [ ] Add a new test function `test_scenario_14b_correct_bearer_books_populated` immediately after `test_scenario_14_correct_bearer_both_tables_populated` in the test file.
  - [ ] Body shape (mirror scenario 12 / 13 exactly):
    ```python
    async def test_scenario_14b_correct_bearer_books_populated(
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """#14b: 4 books seeded → 204; books=0; log reflects 0 / 0 / 4."""
        monkeypatch.setattr(settings, "enable_test_reset", True)
        monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
        caplog.set_level(logging.INFO, logger="bff.api.test_reset")
        ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
        try:
            for i in range(4):
                await _seed_book_row(ctx, suffix=f"s14b-{i}")
            assert await _count_books(ctx) == 4
            async with ctx.make_client() as client:
                response = await client.post(
                    "/v1/test/reset",
                    headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
                )
            assert response.status_code == 204
            assert await _count_books(ctx) == 0
            assert any(
                "sessions_deleted=0" in r.message
                and "auth_states_deleted=0" in r.message
                and "books_deleted=4" in r.message
                for r in caplog.records
            )
        finally:
            await ctx.engine.dispose()
    ```
  - [ ] (Optional, but recommended for completeness) Add a second new test `test_scenario_14c_correct_bearer_all_three_tables_populated` that seeds e.g. 2 sessions + 3 auth_states + 5 books and asserts the log line carries `sessions_deleted=2 auth_states_deleted=3 books_deleted=5` — this is the symmetric "all three" case that AC3 describes. If you skip this, scenario 14 + 14b together give equivalent coverage; if you add it, the coverage matrix is fully symmetric. Pick one approach and document the choice in **Completion Notes**.

- [ ] **Task 7 — Run the full BFF gate matrix (AC10)**
  - [ ] From `services/bff/`:
    - `uv sync --frozen` → exit 0.
    - `uv run ruff check` → clean.
    - `uv run ruff format --check` → clean.
    - `uv run ty check` → clean.
    - `uv run pytest --cov` → all tests pass; total coverage ≥ 90%; coverage of `src/bff/api/test_reset.py` ≥ 90%.
  - [ ] Capture before/after suite-size counts and the coverage delta on `src/bff/api/test_reset.py` in **Completion Notes**.
  - [ ] No compose verification needed — no compose files change in this story.

- [ ] **Task 8 — Update sprint-status**
  - [ ] On story start: flip `_bmad-output/implementation-artifacts/sprint-status.yaml` development_status `2-3-bff-extend-v1-test-reset-to-truncate-books: ready-for-dev` → `in-progress`. Bump `last_updated`.
  - [ ] On story complete (before `code-review`): flip to `review`. Bump `last_updated`.
  - [ ] If any defect surfaces, append to `deferred-work.md` with the next sequential D-number.

## Dev Notes

### What this story is — and is not

**This story is a surgical one-line extension** of the `POST /v1/test/reset` handler from Story 1.12, plus the symmetric test-side bookkeeping. The endpoint structurally already accommodates this addition — Story 1.12's handler used three separate `await db.execute(...)` calls (not a generic `for table in [...]` loop) precisely so that 2.3's diff would be the addition of a single execute line, not a refactor. The Dev Notes in Story 1.12 (lines 332–334) explicitly call this out:

> Story 2.3 will extend the SAME `test_reset.py` to truncate the `books` table; that extension is also handler-local. Do NOT factor the truncate into a list-of-tables abstraction now — keep it explicit (one `await db.execute(...)` per table) for readability; 2.3 will add its line in the same style.

**Follow that guidance.** Resist the urge to:

- Replace the three executes with a `for entity in [entities.Session, entities.AuthState, entities.Book]:` loop. (It would shrink the diff to ~5 lines but break the explicit ordering the log format depends on.)
- Introduce a `_TRUNCATE_TABLES: Final[list[type[SQLModel]]] = [...]` module constant. (Same anti-pattern — Story 1.12 explicitly rejected it.)
- Refactor the log line into a structured-log shape (key/value pairs in a dict, JSON formatter, etc.). (Out of scope; the project uses plain logging-string format throughout per architecture §Logging conventions, lines 781–788.)

**Explicitly NOT in scope (each is a downstream story OR not part of this story's contract):**

- **No CRUD route work.** Story 2.2 implements `/v1/books` and `/v1/books/{id}`. This story does not touch `bff/api/v1/__init__.py`, `bff/api/books.py` (if/when it exists), or any service layer.
- **No `Book` model changes.** Story 2.1 owns the SQLModel; this story imports it via the already-existing `from bff.models import entities`.
- **No `BookOut` / `BookCreate` / `BookUpdate` references.** This story operates at the ORM layer (bare `delete(entities.Book)`); no Pydantic boundary models are involved.
- **No `ErrorCode` additions.** The 1.12 endpoint reuses `ErrorCode.SESSION_EXPIRED` for 401s and `ErrorCode.INTERNAL_ERROR` for the DB-failure honest-degradation envelope (test_reset.py:267). Both are sufficient; no `BOOK_RESET_FAILURE` enum member is appropriate (and would create an information-disclosure side-channel per Story 1.12 Dev Notes — see `_unauthorized_response`'s docstring at test_reset.py:135).
- **No `/v1/test/session-debug` changes.** Story 1.13's sibling endpoint in the same module is for J5 logout verification — unrelated to `books`. Leave its body, log lines, and tests alone.
- **No new ENV vars.** `ENABLE_TEST_RESET` and `TEST_RESET_TOKEN` are sufficient; the truncate target list is hardcoded in the handler (consistent with the project's "no operator-broadenable surfaces" stance — Story 1.12 Dev Notes).
- **No `compose/app.yml` / `compose/app.e2e.yml` changes.** Compose-profile gating is unchanged.
- **No `.env.example` changes.** The truncate target list is internal to the handler.

### Dependencies (CRITICAL — read before starting)

**Story 2.1 (`ready-for-dev`)** — owns the `Book` SQLModel at `services/bff/src/bff/models/entities/book.py`, the re-export from `entities/__init__.py`, and the Alembic migration `0002_add_books.py`. **This story REQUIRES 2.1 to be `done` before its tests can pass.** Task 1's precondition check (`from bff.models import entities; entities.Book`) is the load-bearing assertion that 2.1 has landed.

- If 2.1 has not landed: **STOP**. Notify the maintainer. Implementing 2.3 against a missing `Book` entity will produce an `AttributeError: module 'bff.models.entities' has no attribute 'Book'` at import time in `test_reset.py` AND a `NameError: name 'Book' is not defined` when SQLModel.metadata.create_all runs in the test conftest — neither is a problem this story should "fix" by stubbing.
- If 2.1 has landed but its tests are red: **STOP**. The conftest's `SQLModel.metadata.create_all` provisions every entity registered via `bff.models.entities.__init__.py`; a broken `Book` model will surface as a misleading `no such table: books` error in 2.3's test runs.

**Story 2.2 (`backlog`)** — owns `/v1/books` CRUD endpoints. **NOT a dependency** of this story. 2.3 can be implemented and tested in isolation; 2.2 and 2.3 are independent leaves of the dependency tree rooted at 2.1.

**Story 1.12 (`done`)** — owns the endpoint surface this story extends. Read `_bmad-output/implementation-artifacts/1-12-bff-post-v1-test-reset-endpoint.md` for the full context if any of the 22 baseline scenarios feel ambiguous. Pay attention to:
- AC6 ("Happy path: 204 + truncation") — describes the two-execute + single-commit pattern this story extends to three executes.
- Dev Notes "Implementation note (AC6)" — explicitly forecasts this story's one-line addition.
- The handler's `try/except (SQLAlchemyError, OSError)` block (test_reset.py:249–273) — the new `books_result` execute MUST go inside the try block, not after the commit. A DB error during the books DELETE must trigger the same rollback + 500 envelope as a sessions/auth_states failure.

**Story 1.13 (`done`)** — added `GET /v1/test/session-debug` to the same module. **Leave it alone.** Its tests (`test_session_debug_*`) and its body do not interact with `books`.

**Story 2.7 (`backlog`)** — the J2 Playwright spec is the first consumer of this story's behavior. The fixture pattern is established in Story 1.11; Story 2.7's `beforeEach(resetState)` will hit `POST /v1/test/reset` and rely on the `books` table being empty. This story makes that guarantee real. Out of scope here.

### Architecture compliance

- **AR32 (epics line 97)** — "Test reset endpoint: `POST /v1/test/reset` on BFF (truncates `books`, `sessions`, `auth_states`) and RS (truncates `reading_speeds`). Available only when `ENABLE_TEST_RESET=true`; requires shared bearer from `TEST_RESET_TOKEN`. Returns 204. Production builds do not register the route." — **this story completes the BFF half of AR32 by adding `books` to the truncate list.** The RS half is owned by Story 3.4.
- **Architecture §"POST /v1/test/reset (e2e profile only)" lines 1354–1360** — wire contract reaffirmed: 204 success, 404 when off, bearer required, gating via `ENABLE_TEST_RESET`. This story does not change the contract; it brings the implementation into full conformance with line 1357 ("On the BFF: truncates `books`, `sessions`, `auth_states`").
- **Architecture §Logging conventions lines 781–788** — never log token material; never include row-level ids unless truncated. The truncate is table-wide; no per-row context appears in the log. The updated INFO line continues to carry only row counts (safe to log).
- **Architecture §D1 line 333** — "BFF database engine: SQLite". The `DELETE FROM books` against SQLite is supported and returns `result.rowcount` correctly (Story 1.12 Dev Notes "Latest tech information" — the same applies to any additional table).
- **Architecture §Naming Patterns line 546** — `books` is plural snake_case; the `entities.Book` SQLModel registers `__tablename__ = "books"` (Story 2.1 AC1).

### Library / framework requirements

No new dependencies. All imports needed for the diff are already in `bff/api/test_reset.py`:

- `entities.Book` — newly available via Story 2.1's update to `bff/models/entities/__init__.py`. Pre-existing import line `from bff.models import entities` (test_reset.py:82) is unchanged.
- `_delete` (alias for `sqlalchemy.delete`) — already imported (test_reset.py:75).
- `getattr` (stdlib) — already used for the existing two `rowcount` extractions.

No new dev dependencies. Pytest, `httpx.AsyncClient`, SQLModel, async sessionmaker — all already used by the test file.

Python 3.14 floor stays unchanged (`services/bff/pyproject.toml:9`).

### File structure requirements

**Modified files (this story):**

- `services/bff/src/bff/api/test_reset.py` — add one execute line, add one variable assignment for `books_deleted`, extend one log format string by one `%s` and one positional arg, update module docstring (2 lines) + comment about Story 2.3 forward-pointer + References block (1 line). ~10 LOC diff total.
- `services/bff/tests/api/test_test_reset.py` — add two helpers (`_seed_book_row`, `_count_books`) (~15 LOC), extend log-assertion strings in scenarios 11–14 (1 word per scenario, 4 lines touched), add new test function for scenario 14b (~25 LOC). ~45 LOC diff total.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — flip `2-3-bff-extend-v1-test-reset-to-truncate-books` status across the workflow (`ready-for-dev` → `in-progress` → `review`). Bump `last_updated`.

**NOT modified (intentional — per scope):**

- `services/bff/src/bff/api/v1/__init__.py` — no router changes.
- `services/bff/src/bff/main.py` — no startup-wiring changes.
- `services/bff/src/bff/auth/csrf.py` — CSRF exemption already covers `/v1/test/reset`.
- `services/bff/src/bff/core/config.py` — no new settings.
- `services/bff/src/bff/core/errors.py` — no new `ErrorCode` members.
- `services/bff/src/bff/models/entities/__init__.py` — Story 2.1 owns this update.
- `services/bff/src/bff/models/entities/book.py` — Story 2.1 owns this file.
- `services/bff/.env.example` — `ENABLE_TEST_RESET=false` + `TEST_RESET_TOKEN=change-me` already present.
- `compose/app.yml`, `compose/app.e2e.yml`, `docker-compose.yml` — no infra changes.
- `services/bff/alembic/...` — no schema changes.
- `services/bff/pyproject.toml` — no new dependencies.

### Testing standards

- **Framework:** pytest 8+, pytest-asyncio (already configured in `services/bff/pyproject.toml`; `asyncio_mode = "auto"` so `async def test_...` is enough — no `@pytest.mark.asyncio` decorator needed).
- **HTTP client:** `httpx.AsyncClient(transport=ASGITransport(app=ctx.app))` — same as the rest of the test file.
- **DB fixture:** Each test calls `_build_context(enable=True, token=_DEFAULT_TOKEN)` to build a fresh `FastAPI` app + in-memory SQLite engine via `create_async_engine("sqlite+aiosqlite://", ..., poolclass=StaticPool)`. The fixture provisions ALL SQLModel-registered tables via `SQLModel.metadata.create_all`, so the `books` table is created automatically once Story 2.1's `Book` model is registered (Story 2.1 AC2). **Do not add `Book` to `_build_context` manually — the metadata-level registration is enough.**
- **Log assertion:** Use `caplog.set_level(logging.INFO, logger="bff.api.test_reset")` (matches existing scenarios 11–14, 17). Assert on `any(... in r.message for r in caplog.records)` boolean substring matches — same idiom the existing tests use.
- **Test naming:** the new test goes in the SAME file `services/bff/tests/api/test_test_reset.py`. Use `async def test_scenario_14b_correct_bearer_books_populated(...)` (or the agent's preferred name; document in **Completion Notes**). Place it adjacent to scenario 14.
- **Coverage gate:** total project `fail_under = 90` (`services/bff/pyproject.toml:86`). Per-module: keep `src/bff/api/test_reset.py` at ≥90% (Story 1.12 hit 100%; the one-line diff is trivially covered by the new scenario 14b plus the extended scenarios).
- **Lint / format / type-check:** `uv run ruff check`, `uv run ruff format --check`, and `uv run ty check` must all be clean.
- **Python invocation:** all commands and inline scripts use `python` (never `python3`) per `CLAUDE.md`. The existing test file, Dockerfile, compose healthchecks, and pytest commands already follow this convention.

### Previous story intelligence

**From Story 2.1 (`ready-for-dev` — the precondition):**

- `Book.id` is `int | None` with `autoincrement=True` at the SQLAlchemy level. Do NOT pass `id=` when constructing seed rows in `_seed_book_row` — SQLAlchemy assigns it on commit.
- `Book.sub` is `str(255)` indexed. The `ix_books_sub` index does NOT affect truncation behavior (DROP INDEX is implicit on TRUNCATE / DELETE-all in SQLite).
- `Book.status` defaults to `"to-read"` at the column level. Seed rows can omit the field and rely on the default.
- `Book.created_at` and `Book.updated_at` populate from `default_factory=lambda: datetime.now(UTC)`. Seed rows can omit them.
- The conftest's `engine` fixture creates all SQLModel-registered tables. As long as Story 2.1 has wired `Book` into `entities/__init__.py`, the conftest will produce a fresh `books` table for every test.
- Story 2.1's Dev Notes explicitly state "the conftest's engine fixture creates ALL SQLModel metadata" — no test-level setup is needed beyond seeding.

**From Story 1.12 review (test-reset endpoint baseline):**

- The handler's truncate-and-commit block is wrapped in `try/except (SQLAlchemyError, OSError)` (test_reset.py:249–273). This story's new execute MUST sit inside the same try block — a DB failure on the books DELETE must trigger the same rollback + `INTERNAL_ERROR` 500 envelope as the existing two.
- `getattr(result, "rowcount", -1)` is the canonical pattern for extracting deleted-row counts. `ty` complains on direct `.rowcount` access because `AsyncSession.execute` returns the broader `Result[Any]` static type. Use the same `getattr` form for the new `books_deleted` value.
- The `_TRUNCATE_TABLES` constant approach was DELIBERATELY REJECTED in 1.12 (Dev Notes line 333). Do not re-litigate that decision.
- The `synchronize_session=False` kwarg is a Story 1.4 D31 mitigation for SQLite naive-datetime ORM-evaluator issues. It is harmless for the books DELETE (no WHERE clause, no datetime comparison) but is included for consistency with the existing two executes.
- Story 1.12's tests build a fresh app per test via `_build_context` — this avoids the global `app` singleton's gate-state bleeding across tests. The new scenario 14b uses the same pattern.
- The trailing-slash CSRF exemption regression (scenario 23) was added during Story 1.12's code review (Patch P2). It still applies; this story's diff does not affect it.
- The DB-failure honest-degradation envelope (scenario 24, Patch P6 from Story 1.12's review) wraps the truncate in `try/except`. This story's new execute joins that wrapper; no new error-path scenario is needed since the existing P6 test exercises the rollback for sessions and auth_states — books is structurally identical.

**From Story 1.13 review (session-debug sibling):**

- `GET /v1/test/session-debug` lives in the SAME module (`bff/api/test_reset.py`). Do not edit its handler, its docstring section, or its log lines — they relate to refresh-token exposure, not the books truncate.
- The `_safe_session_id_log` helper at test_reset.py:97 is used only by the session-debug endpoint. Do not introduce calls to it from the new `books_result` block (there's nothing to truncate-and-log per row).

**From Story 2.1 Dev Notes "Test-side gotchas observed in Epic 1":**

- Async tests use bare `async def test_...` — no `@pytest.mark.asyncio` decorator (matches `asyncio_mode = "auto"`).
- SQLite stores `DateTime` as naive (TZ stripped on write). The new seed helper doesn't compare timestamps, so this doesn't bite here.
- The fixture re-creates tables between tests by dropping + recreating SQLModel.metadata. Per-test seed rows do NOT leak into subsequent tests.

### Latest tech information

- **SQLAlchemy 2.x** — `delete(Table)` without a `WHERE` clause issues a bare `DELETE FROM <table>` SQL statement against the connected dialect. SQLite supports this and reports `result.rowcount` accurately for the executed statement. With `execution_options={"synchronize_session": False}`, the ORM's in-memory session-sync step is skipped (irrelevant here — no rows are pinned in the session at handler time).
- **SQLite truncation semantics** — `DELETE FROM books` (no WHERE) removes all rows. SQLite optimizes this to a "truncate-optimization" internally if the table has no foreign key constraints pointing to it (`PRAGMA foreign_keys=ON`); in either case the rowcount reflects the number of rows previously present.
- **Pytest caplog** — `caplog.records` is a list of `logging.LogRecord` objects; `r.message` is the formatted message after `%`-substitution. Substring matches on `r.message` are stable across the project. Use `caplog.set_level(logging.INFO, logger="bff.api.test_reset")` to scope capture to the handler's logger (the existing scenarios do exactly this).
- **httpx + ASGITransport** — `AsyncClient(transport=ASGITransport(app=ctx.app))` directly invokes the in-process FastAPI app without a TCP socket. The truncate test runs in microseconds; no special configuration needed.

### Project Structure Notes

The diff is intentionally minimal. No new files are created; no files are deleted; no files are renamed. The two modified source files are:

```
services/bff/
├── src/bff/api/test_reset.py        (MODIFY: +1 execute, +1 var, log format, docstring touch)
└── tests/api/test_test_reset.py     (MODIFY: +2 helpers, +1 test, scenario log-assertion edits)
```

Plus the sprint-status YAML flip.

**No variance from architecture spec.** Architecture's source-tree (line 903) lists `src/bff/api/test_reset.py` as the canonical path; the file already exists at that path (Story 1.12). The architecture's AR32 (epics line 97) explicitly enumerates `books, sessions, auth_states` as the BFF truncate list — this story makes the implementation match.

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

- Commit `81ae50f` ("story 2.1") created the `Book` SQLModel + migration + boundary schemas. **Verify** this commit has actually landed the `Book` entity by running Task 1's precondition check. The commit title says "story 2.1" but the sprint-status YAML still reports `2-1-bff-book-sqlmodel-migration-pydantic-boundary-models: ready-for-dev` (NOT `done`). The commit may represent the in-progress dev work, not the final merge. **If the precondition check fails, do not proceed.**
- The two CSRF-related fixes (`060df66`, `ca02146`) and the Epic 1 cleanup (`180b1e2`) are unrelated to this story's diff. No rebase risk.
- Branch `epic-2` is the working branch.

### Latest tech information (continued — Pydantic / SQLModel reminders)

This story does NOT use Pydantic boundary models directly (no `BookCreate` / `BookOut` involvement). It operates exclusively at the SQLModel layer (`entities.Book`) and the bare SQLAlchemy `delete(...)` construct. If the dev agent finds itself reaching for `BookOut.model_validate(...)` or similar, it has wandered out of scope — back up.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3: BFF — extend `/v1/test/reset` to truncate `books` (lines 854–878)]
- [Source: _bmad-output/planning-artifacts/epics.md#AR32 — Test reset endpoint (line 97)]
- [Source: _bmad-output/planning-artifacts/architecture.md#"POST /v1/test/reset (e2e profile only)" lines 1354–1360]
- [Source: _bmad-output/planning-artifacts/architecture.md#Naming Patterns line 546] (plural snake_case `books`)
- [Source: _bmad-output/planning-artifacts/architecture.md#D1 line 333] (SQLite + WAL — `DELETE FROM books` semantics)
- [Source: _bmad-output/planning-artifacts/architecture.md#Logging conventions lines 781–788] (no token material; row counts safe)
- [Pattern: _bmad-output/implementation-artifacts/1-12-bff-post-v1-test-reset-endpoint.md#AC6] (two-execute + single-commit baseline this story extends)
- [Pattern: _bmad-output/implementation-artifacts/1-12-bff-post-v1-test-reset-endpoint.md#Dev Notes "Implementation note (AC6)"] (forecast of this story's one-line addition)
- [Pattern: services/bff/src/bff/api/test_reset.py:196–288] (existing `test_reset` handler — the function this story modifies)
- [Pattern: services/bff/tests/api/test_test_reset.py:132–170] (existing seed + count helper block; the new helpers slot in here)
- [Pattern: services/bff/tests/api/test_test_reset.py:431–556] (scenarios 11–14 — the bodies whose log-assertion strings need the `books_deleted=` suffix)
- [Pattern: _bmad-output/implementation-artifacts/2-1-bff-book-sqlmodel-migration-pydantic-boundary-models.md#AC1] (Book SQLModel contract; explains what the seed helper can omit)
- [Gate: services/bff/pyproject.toml lines 9, 76–86] (Python 3.14; pytest config; coverage `fail_under=90`)
- [Convention: CLAUDE.md] (project convention: invoke Python as `python`, never `python3`)

### Project context reference

Project-context facts loaded at activation:

- BMAD_books accessibility / responsive design: OUT OF SCOPE — not relevant; this is a backend-only test-surface change with no UI.
- Backend archetype: `github.com/tommaso-meledina/fastapi-archetype` (Python 3.14 + FastAPI + SQLModel + uv + OTEL). This story stays inside the archetype's conventions — same APIRouter, same SQLModel entities, same uv-managed deps.
- Python invocation: `python` (never `python3`) per `CLAUDE.md`. The existing test_reset module and its tests already follow this — nothing for this story to change.

## Definition of Done

1. `services/bff/src/bff/api/test_reset.py::test_reset` truncates `books` in addition to `sessions` and `auth_states`; the new execute sits inside the existing try/except wrapper; the `await db.commit()` remains a single commit (AC1, AC3).
2. The success-path `test_reset_truncated` INFO log carries `tables=sessions,auth_states,books` and three `<table>_deleted=<n>` counters (AC2).
3. `services/bff/src/bff/api/test_reset.py` module docstring lists `books` in the endpoint description and references Story 2.3; the forward-pointer comment about Story 2.3 has been rewritten in present/past tense (AC9).
4. `services/bff/tests/api/test_test_reset.py` exposes `_seed_book_row` and `_count_books` helpers (AC7).
5. Existing scenarios 11, 12, 13, 14, 17 in the test file include `books_deleted=` substring assertions and (where naturally applicable) `_count_books(ctx)` pre/post assertions (AC6).
6. A new test scenario covers books-only seed (AC4, AC8).
7. All other Story 1.12 + 1.13 scenarios still pass without functional change (AC5).
8. `uv run pytest --cov`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` all clean; coverage of `src/bff/api/test_reset.py` ≥ 90%; total project coverage ≥ 90% (AC10).
9. Sprint-status YAML reflects the story's final state (`review` before code-review, then `done` after).
10. No files outside the two source modifications + the sprint-status YAML are touched.

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
