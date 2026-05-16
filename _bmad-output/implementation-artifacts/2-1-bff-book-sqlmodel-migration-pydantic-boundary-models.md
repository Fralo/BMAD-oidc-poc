---
status: done
story_key: 2-1-bff-book-sqlmodel-migration-pydantic-boundary-models
created: 2026-05-16
---

# Story 2.1: BFF — Book SQLModel + migration + Pydantic boundary models

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer extending the BFF to own the book domain,
I want a `Book` SQLModel and Alembic migration creating the `books` table, plus distinct API Pydantic models (`BookCreate`, `BookUpdate`, `BookOut`),
so that Story 2.2 can implement CRUD against a stable schema and a serialization layer that doesn't leak internal columns.

## Scope (read this first)

This story is **persistence + boundary types only**. It does **not** register routes, services, or error codes — those land in Story 2.2. The deliverables are:

1. `services/bff/src/bff/models/entities/book.py` — `Book` SQLModel.
2. `services/bff/src/bff/models/entities/__init__.py` — re-export `Book`.
3. `services/bff/src/bff/api/schemas/__init__.py` — new package.
4. `services/bff/src/bff/api/schemas/book.py` — `BookCreate`, `BookUpdate`, `BookOut`.
5. `services/bff/alembic/versions/0002_add_books.py` — Alembic migration.
6. `services/bff/tests/models/entities/test_book.py` — model tests.
7. `services/bff/tests/api/schemas/__init__.py` + `test_book_schemas.py` — schema tests.

Anything outside that list (routers, services, `ErrorCode` enum entries, `BookNotFoundError`, the `/v1/test/reset` extension) is **out of scope** for 2.1.

## Acceptance Criteria

**AC1 — `Book` SQLModel exists at `src/bff/models/entities/book.py`.**

Inspecting the module:

- Class header: `class Book(SQLModel, table=True):`
- `__tablename__ = "books"` (plural, snake_case — architecture §Naming Patterns).
- Columns:
  - `id: int | None = Field(default=None, primary_key=True)` — int PK, autoincrement (SQLAlchemy default for INTEGER PRIMARY KEY in SQLite).
  - `sub: str = Field(max_length=255, index=True, nullable=False)` — keyed identity (architecture §AR7).
  - `title: str = Field(max_length=500, nullable=False)`.
  - `pages: int = Field(nullable=False)` — positivity is enforced at the Pydantic boundary; **no DB-level CHECK constraint** (kept consistent with `Session` / `AuthState` which also enforce all constraints in the application layer).
  - `status: str = Field(default="to-read", nullable=False)` — value set `{"to-read","reading","finished"}` enforced at the Pydantic boundary; column is plain `str`. **No SQLAlchemy `Enum` type** (kept consistent with the existing models).
  - `created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)`.
  - `updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)})` — `updated_at` advances automatically on UPDATE via SQLAlchemy `onupdate`.

**AC2 — `Book` is re-exported from `models.entities`.**

`services/bff/src/bff/models/entities/__init__.py` adds `Book` to its imports and to `__all__`, preserving the existing `AuthState` and `Session` entries. This is what triggers SQLModel metadata registration in `alembic/env.py` (which imports `bff.models.entities`).

**AC3 — Pydantic boundary models exist at `src/bff/api/schemas/book.py`.**

Three classes, Pydantic v2 (`from pydantic import BaseModel, ConfigDict, Field`):

- `BookCreate(BaseModel)`:
  - `title: str = Field(min_length=1)` — additionally, leading/trailing whitespace is stripped and post-strip emptiness rejected (use `field_validator` with `mode="after"` or `model_validator`; whichever is idiomatic — see Dev Notes for the recommended snippet).
  - `pages: int = Field(ge=1)`.
  - `status: Literal["to-read", "reading", "finished"] = "to-read"`.
- `BookUpdate(BaseModel)`:
  - `title: str | None = Field(default=None, min_length=1)` (with the same strip-and-reject behavior when present).
  - `pages: int | None = Field(default=None, ge=1)`.
  - `status: Literal["to-read", "reading", "finished"] | None = None`.
  - **Partial update semantics:** all three fields optional; the model itself does NOT require "at least one field present" (Story 2.2's handler may decide what to do with an empty patch — it's not 2.1's call to enforce).
- `BookOut(BaseModel)`:
  - `model_config = ConfigDict(from_attributes=True)` — enables construction from a `Book` ORM instance via `BookOut.model_validate(book)`.
  - Fields: `id: int`, `title: str`, `pages: int`, `status: Literal["to-read", "reading", "finished"]`, `created_at: datetime`, `updated_at: datetime`.
  - **Must NOT include `sub`** (architecture §C7 — internal columns stay out of responses by construction).

**AC4 — `BookCreate` and `BookUpdate` reject the documented invalid inputs.**

For each model, `model_validate` raises `pydantic.ValidationError` on:

- `title=""` (empty).
- `title="   "` (whitespace only, after strip).
- `title` missing in `BookCreate` (required); accepted as `None` in `BookUpdate`.
- `pages=0`, `pages=-5`.
- `status="archived"` (or any value outside the documented set).

For `BookCreate`, omission of `pages` is also rejected (required). For `BookUpdate`, omission of every field is accepted (empty patch — see scope note above).

**AC5 — Alembic migration `0002_add_books.py` creates the table and index.**

File: `services/bff/alembic/versions/0002_add_books.py`.

- `revision: str = "0002_add_books"`.
- `down_revision: str | Sequence[str] | None = "0001_init"`.
- `upgrade()` creates the `books` table with columns matching the SQLModel:
  - `sa.Column("id", sa.Integer(), nullable=False, autoincrement=True)` and `sa.PrimaryKeyConstraint("id")`.
  - `sa.Column("sub", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False)`.
  - `sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False)`.
  - `sa.Column("pages", sa.Integer(), nullable=False)`.
  - `sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False)`.
  - `sa.Column("created_at", sa.DateTime(), nullable=False)`.
  - `sa.Column("updated_at", sa.DateTime(), nullable=False)`.
- `op.create_index(op.f("ix_books_sub"), "books", ["sub"], unique=False)` — index name matches the autogenerate convention used by 0001.
- `downgrade()` drops the index first, then the table.
- The file's docstring uses the same one-line summary style as `0001_init_init_sessions_and_auth_states.py`.

**AC6 — Migration applies cleanly forward and back.**

- Starting from `0001_init`, running `uv run alembic upgrade head` advances to `0002_add_books`. `uv run alembic current` reports `0002_add_books (head)`.
- The `sessions` and `auth_states` tables are untouched.
- Running `uv run alembic downgrade -1` removes only the `books` table; `alembic current` returns to `0001_init`.

**AC7 — Autogenerate-clean.**

After AC1 + AC2 + AC5 are in place, `uv run alembic upgrade head && uv run alembic revision --autogenerate -m "noop sanity check"` produces a revision file whose `upgrade()`/`downgrade()` bodies are empty (no spurious diff between the live schema and the SQLModel metadata). Delete the sanity-check file before committing. This proves the model and the migration agree on column types, NOT NULL, and the index.

**AC8 — Tests at `tests/models/entities/test_book.py` cover the model contract.**

The test file uses the existing `session` / `engine` fixtures from `services/bff/tests/conftest.py`. Mirrors the structure of `test_session.py`. Includes at minimum:

- `test_create_and_read_by_id` — insert a `Book`, refresh, fetch by PK, assert columns round-trip including `sub`.
- `test_query_by_sub_uses_indexed_lookup` — insert two books with different `sub` values, query by one, assert isolation.
- `test_created_at_and_updated_at_autopopulate` — assert both timestamps fall between `before` and `after` (use the `_as_utc` helper pattern from `test_session.py`).
- `test_updated_at_advances_on_update` — fetch a row, mutate `status`, commit, refresh; assert `updated_at` is strictly later than the original (use `asyncio.sleep(0.01)` between to guarantee tick).
- `test_default_status_is_to_read` — insert a `Book` without specifying `status`, assert the persisted value is `"to-read"`.
- `test_pages_accepts_positive_int_at_db_layer` — sanity: a model instance with `pages=100` persists; this confirms the DB column allows any int (positivity is a Pydantic-layer concern, not enforced here).
- `test_sub_not_null_at_db` — attempting to flush a row with `sub=None` raises `IntegrityError`.

**AC9 — Tests at `tests/api/schemas/test_book_schemas.py` cover the boundary contract.**

Create the new test package: `services/bff/tests/api/schemas/__init__.py`. The test file imports `BookCreate`, `BookUpdate`, `BookOut`, and `pydantic.ValidationError`. Covers:

- `test_book_create_happy_path` — `BookCreate(title="Dune", pages=688, status="reading")` validates; defaults to `status="to-read"` when omitted.
- `test_book_create_rejects_empty_title` — `title=""` raises `ValidationError`.
- `test_book_create_rejects_whitespace_title` — `title="   "` raises.
- `test_book_create_rejects_missing_title` — missing `title` raises.
- `test_book_create_rejects_nonpositive_pages` — `pages=0` and `pages=-1` each raise.
- `test_book_create_rejects_missing_pages` — missing `pages` raises.
- `test_book_create_rejects_unknown_status` — `status="archived"` raises.
- `test_book_update_all_fields_optional` — `BookUpdate()` validates (empty patch is OK at the model level — see scope).
- `test_book_update_partial_status_only` — `BookUpdate(status="finished")` validates.
- `test_book_update_rejects_invalid_values` — `pages=0`, `status="archived"`, `title=""`, `title="   "` each raise.
- `test_book_out_roundtrips_from_orm` — construct a `Book` ORM instance with all fields set (including `sub`), `BookOut.model_validate(book)` succeeds, the resulting dict has keys `{id, title, pages, status, created_at, updated_at}` and **does not** contain the key `sub`.
- `test_book_out_serializes_datetime_iso8601_utc` — `BookOut(...).model_dump(mode="json")` emits `created_at`/`updated_at` as ISO 8601 strings (Pydantic v2 default). (Z-suffix exactness is a 2.2 concern — here, just assert it's a string parsed by `datetime.fromisoformat`.)

**AC10 — Coverage and lint gates remain green.**

- `uv run pytest` from `services/bff/` passes; the suite count grows by ≥ the count of tests added above (no regressions in the 348 currently-passing tests).
- Coverage of `src/bff/models/entities/book.py` and `src/bff/api/schemas/book.py` is **≥90%** (archetype target; see `pyproject.toml` `[tool.coverage.report] fail_under = 90`).
- `uv run ruff check services/bff/` reports no new findings.
- `uv run ty check services/bff/` reports no new findings.

## Tasks / Subtasks

- [x] Task 1 — `Book` SQLModel + `__init__.py` re-export (AC1, AC2)
  - [x] 1.1 Create `services/bff/src/bff/models/entities/book.py` mirroring the column-style of `session.py`.
  - [x] 1.2 Update `services/bff/src/bff/models/entities/__init__.py` to import `Book` and add to `__all__`.
  - [x] 1.3 Skim `alembic/env.py` to confirm the `entities` import will pick up `Book` (no change required — the existing wildcard-style `from bff.models import entities` is the trigger).

- [x] Task 2 — Pydantic boundary models (AC3, AC4)
  - [x] 2.1 Create `services/bff/src/bff/api/schemas/__init__.py` (empty package marker is fine, or re-export `BookCreate`, `BookUpdate`, `BookOut` from `book.py` for ergonomics).
  - [x] 2.2 Create `services/bff/src/bff/api/schemas/book.py` with `BookCreate`, `BookUpdate`, `BookOut` per AC3.
  - [x] 2.3 Verify Pydantic constraints reject every invalid input listed in AC4 (this is fully test-covered in AC9 — no separate dev verification required).

- [x] Task 3 — Alembic migration `0002_add_books.py` (AC5, AC6, AC7)
  - [x] 3.1 With `Book` registered in `bff.models.entities`, run `uv run alembic revision --autogenerate -m "add books"` from `services/bff/` and capture the produced file as `0002_add_books.py`.
  - [x] 3.2 Inspect the autogenerated output and adjust to AC5's column types/order (`AutoString(length=...)` for strings, `sa.Integer()` for `id`/`pages`, `sa.DateTime()` for timestamps). Reorder if autogenerate didn't.
  - [x] 3.3 Set `revision = "0002_add_books"` (autogenerate produces a UUID-ish slug by default) and confirm `down_revision = "0001_init"`. Rename the file to `0002_add_books.py` to match.
  - [x] 3.4 Run `uv run alembic upgrade head` against a fresh DB and inspect schema with `sqlite3 <db> .schema books` to confirm the table and `ix_books_sub` index exist.
  - [x] 3.5 Run `uv run alembic downgrade -1` and confirm the table is removed and revision returns to `0001_init`.
  - [x] 3.6 Run AC7's autogenerate sanity check (no-op revision); delete the noop file.

- [x] Task 4 — Model tests (AC8)
  - [x] 4.1 Create `services/bff/tests/models/entities/test_book.py`. Mirror imports/structure of `test_session.py`.
  - [x] 4.2 Add the seven test functions listed in AC8.

- [x] Task 5 — Schema tests (AC9)
  - [x] 5.1 Create `services/bff/tests/api/schemas/__init__.py`.
  - [x] 5.2 Create `services/bff/tests/api/schemas/test_book_schemas.py` with the test functions listed in AC9.

- [x] Task 6 — Coverage & lint verification (AC10)
  - [x] 6.1 `uv run pytest` — full BFF suite green; coverage of the two new modules ≥90%.
  - [x] 6.2 `uv run ruff check` — clean.
  - [x] 6.3 `uv run ty check` — clean.

### Review Findings

- [x] [Review][Decision→Patch] D1/P3 — Mirrored DB cap on the boundary: `BookCreate.title` / `BookUpdate.title` now `Field(min_length=1, max_length=500)`. Added `test_book_create_rejects_overlong_title` and extended `test_book_update_rejects_invalid_values` with `title="x"*501`.
- [x] [Review][Decision→Patch] D2/P4 — Capped `BookCreate.pages` / `BookUpdate.pages` at `Field(ge=1, le=1_000_000)`. Added `test_book_create_rejects_pages_above_cap` and extended `test_book_update_rejects_invalid_values` with `pages=1_000_001`.
- [x] [Review][Patch] P1 — Added `test_book_update_explicit_title_none_passes_validator` to exercise the validator's `if v is None: return v` early-return. Coverage on `bff/api/schemas/book.py` rose from 97% → 100%.
- [x] [Review][Patch] P2 — `test_check_alembic_at_head_passes_when_current_matches_head` now resolves `alembic.ini` via `Path(__file__).resolve().parents[2] / "alembic.ini"` instead of the CWD-relative `health_module._ALEMBIC_INI`. Test is now invocation-directory-independent.
- [x] [Review][Defer] W1 — `_strip_and_reject_blank` rejects only Python-`str.isspace` whitespace, so zero-width / BOM characters (U+200B, U+FEFF, U+2060) pass through and persist [services/bff/src/bff/api/schemas/book.py:14-17]. AC4 enumerates `title="   "` only (regular spaces); broader Unicode normalization belongs to a hardening pass — deferred, pre-existing definition of "blank".
- [x] [Review][Defer] W2 — No test asserts that `BookOut.model_validate(Book(status="archived", ...))` raises [services/bff/tests/api/schemas/test_book_schemas.py]. The Pydantic `Literal` would reject it, but a future relaxation of the type to `BookStatus | str` would silently pass — deferred, defensive coverage gap.

## Dev Notes

### Critical path translation: epic doc paths vs. actual archetype layout

The epic document (`epics.md` §Story 2.1) names the files `src/bff/db/models/book.py` and `src/bff/api/schemas/book.py`. The **actual BFF codebase**, generated from the archetype, uses `src/bff/models/entities/...` (not `src/bff/db/models/...`). All four existing precedents (`session.py`, `auth_state.py`, their `__init__.py`, and the alembic `env.py` import) live under `bff.models.entities`. **Follow the actual codebase layout** for the model file. The schemas path is correct as-stated (`src/bff/api/schemas/book.py`) — that directory does not yet exist and will be created by this story.

### Existing patterns to mirror exactly

**1. `services/bff/src/bff/models/entities/session.py`** is the canonical reference for SQLModel style:

```python
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(primary_key=True)
    sub: str = Field(max_length=255, index=True, nullable=False)
    # ...
    expires_at: datetime = Field(index=True, nullable=False)
    csrf_secret: str = Field(nullable=False, repr=False)
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

The `Book` model uses the **same imports, the same `nullable=False`-on-every-column convention, the same `created_at`/`updated_at` `default_factory` + `sa_column_kwargs={"onupdate": ...}` pattern**. The only structural difference: `Book.id` is an `int | None` PK with autoincrement (vs. `Session.id`, an opaque `str` issued by the OIDC plugin).

**2. `services/bff/src/bff/models/entities/__init__.py` is the registration choke-point** that `alembic/env.py` relies on for autogenerate:

```python
from bff.models.entities.auth_state import AuthState
from bff.models.entities.session import Session

__all__ = ["AuthState", "Session"]
```

After Task 1: add `Book` to both the imports and `__all__`. Keep alphabetical (the existing entries are already sorted).

**3. `services/bff/alembic/versions/0001_init_init_sessions_and_auth_states.py` is the canonical reference for migration style** (see Dev Notes — Migration excerpt below).

**4. `services/bff/tests/models/entities/test_session.py`** is the canonical reference for model-test style. Helpers: `_as_utc(dt)` to coerce naive datetimes back to UTC after SQLite round-trip, and `_build_session(**overrides)` factory. **Use the same factory pattern** in `test_book.py`:

```python
def _build_book(**overrides: object) -> Book:
    base: dict[str, object] = {
        "sub": "user-sub-1",
        "title": "Dune",
        "pages": 688,
        # status defaults to "to-read"
    }
    base.update(overrides)
    return Book(**base)  # type: ignore[arg-type]
```

**5. `services/bff/tests/conftest.py`** provides `engine` and `session` fixtures that create/drop SQLModel metadata around every test. **Add `Book` to `entities/__init__.py` (Task 1.2) before writing model tests** — otherwise SQLModel.metadata.create_all in the fixture won't create the `books` table and tests will fail with "no such table" errors.

### Pydantic v2 whitespace-trim-and-reject pattern for `title`

The acceptance criteria require that `title="   "` is rejected. Pydantic's `min_length=1` alone does NOT trim whitespace before measuring. Recommended snippet:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal


class BookCreate(BaseModel):
    title: str = Field(min_length=1)
    pages: int = Field(ge=1)
    status: Literal["to-read", "reading", "finished"] = "to-read"

    @field_validator("title", mode="after")
    @classmethod
    def _title_not_blank_after_strip(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace-only")
        return stripped


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    pages: int | None = Field(default=None, ge=1)
    status: Literal["to-read", "reading", "finished"] | None = None

    @field_validator("title", mode="after")
    @classmethod
    def _title_not_blank_after_strip(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace-only")
        return stripped


class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    pages: int
    status: Literal["to-read", "reading", "finished"]
    created_at: datetime
    updated_at: datetime
```

Returning the stripped value from the validator also normalizes "Dune  " → "Dune" before it reaches the DB — that's deliberate and acceptable. (If you'd rather not normalize, just `raise ValueError` and `return v`; either approach passes the ACs.)

### Migration content (reference template)

The autogenerate output should look roughly like this after Task 3.2's adjustments. The bare-bones expected body:

```python
"""add books

Revision ID: 0002_add_books
Revises: 0001_init
Create Date: <ISO>

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0002_add_books"
down_revision: str | Sequence[str] | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("sub", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_books_sub"), "books", ["sub"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_books_sub"), table_name="books")
    op.drop_table("books")
```

Notes:
- `sa.Integer()` for `id` (autoincrement INTEGER PRIMARY KEY in SQLite — no `length` arg). Autogenerate may emit `sa.Integer()` without an explicit `autoincrement=True`; that's fine for SQLite (INTEGER PRIMARY KEY is auto-incrementing).
- `AutoString(length=255)` matches `Field(max_length=255)` on the model.
- `AutoString()` (no length) for `status` matches the model (`status: str` has no `max_length` — short enum-shape values).
- The autogenerate command may also produce SQLAlchemy `batch_alter_table` shims; remove them if they appear — 0001 doesn't use them and consistency matters.

### Why no DB-level CHECK constraints for `pages` and `status`

The epic AC offers a choice between application-level (Pydantic) and DB-level (CHECK) constraints for `pages ≥ 1` and `status ∈ {to-read, reading, finished}`. Pick **application-level only**, for three reasons:

1. **Consistency with the existing models.** `Session.expires_at` and `AuthState.expires_at` are not CHECK-bounded (e.g., "expires_at > created_at"); the project treats application-layer validation as authoritative.
2. **SQLite-portability.** SQLite supports CHECK but not all engines do the same way; keeping the DB engine-agnostic preserves the architecture's "SQLModel + Alembic are engine-agnostic" claim (architecture §D1).
3. **Single source of truth.** The wire-format truth lives in Pydantic. Duplicating it at the DB level invites drift if the enum extends later.

If a future story decides differently, that's a deliberate change — not a 2.1 omission.

### Why `status` is `str`, not `SQLAlchemy Enum`

Same reasoning as above. The Pydantic `Literal[...]` on the boundary plus default `"to-read"` on the column is enough. `SAEnum` would (a) create a CHECK constraint at the DB level (which we explicitly don't want — see above), and (b) couple the DB schema to a Python enum class, complicating future evolution of the value set.

### Pydantic v2 idioms checklist

- Use `from pydantic import BaseModel, ConfigDict, Field, field_validator` — **not** `from pydantic.v1 ...`.
- Use `model_config = ConfigDict(from_attributes=True)` — **not** the v1 `class Config: orm_mode = True`.
- Use `model_validate(orm_instance)` — **not** `parse_obj` (v1).
- Use `model_dump(mode="json")` for JSON-safe dumps — **not** `dict()` or `json()` (v1).

### Existing migration patterns to preserve

Don't reformat or "tidy" `0001_init_init_sessions_and_auth_states.py`. Its `# ### commands auto generated by Alembic - please adjust! ###` markers and column ordering are intentional and the autogenerate tool generates similar markers in 0002. Keep both files internally consistent.

### Test-side gotchas observed in Epic 1

- Async tests use bare `async def test_...` — no `@pytest.mark.asyncio` decorator is needed (the project has `asyncio_mode = "auto"` or equivalent in `pyproject.toml`/`pytest.ini` — confirm by reading any existing test in `tests/models/entities/`).
- SQLite stores `DateTime` as naive (TZ stripped on write). Reads come back without `tzinfo`. Use the `_as_utc()` helper from `test_session.py` when comparing to `datetime.now(UTC)`.
- The fixture re-creates all tables between tests by dropping + recreating SQLModel.metadata. Tests do not need to clean up rows themselves.
- For `test_updated_at_advances_on_update`: `asyncio.sleep(0.01)` is enough to make the second `datetime.now(UTC)` later than the first; smaller waits sometimes fail on fast CI.

### Files NOT to touch in this story

- `services/bff/src/bff/core/errors.py` — `BOOK_NOT_FOUND` and `INVALID_INPUT` ErrorCode entries are Story 2.2.
- `services/bff/src/bff/api/v1/__init__.py` — router registration is Story 2.2.
- `services/bff/src/bff/api/test_reset.py` — `books` truncation is Story 2.3.
- `compose/app.yml`, `docker-compose.yml`, `services/bff/Dockerfile` — no infra changes.
- `services/bff/alembic.ini`, `services/bff/alembic/env.py` — already wired correctly via `from bff.models import entities`; no change needed.

### Project Structure Notes

The story extends the existing archetype layout without restructuring. New files:

```
services/bff/
├── src/bff/
│   ├── models/entities/book.py            (NEW)
│   ├── models/entities/__init__.py         (UPDATE: add Book)
│   └── api/schemas/
│       ├── __init__.py                     (NEW)
│       └── book.py                         (NEW)
├── alembic/versions/
│   └── 0002_add_books.py                   (NEW)
└── tests/
    ├── models/entities/test_book.py        (NEW)
    └── api/schemas/
        ├── __init__.py                     (NEW)
        └── test_book_schemas.py            (NEW)
```

**Detected variance from epic document:** `epics.md` says `src/bff/db/models/book.py`; actual archetype layout is `src/bff/models/entities/book.py`. Use the actual layout. Update no docs — the epic file is a planning artifact and won't be back-rewritten.

### Previous Story Intelligence (Story 1.14 — done, reviewed, merged)

Relevant patterns / gotchas carried forward from the last completed BFF story:

- **`ruff check` / `ty check` are non-negotiable gates.** 1.14 caught an import-sort issue (auto-fixed) and two line-too-long errors (manual fix). Run the linters before declaring task complete.
- **Coverage is enforced at 90%.** Don't drop below by adding new uncovered modules.
- **Story 1.14 did `347 → 348` passed tests post-merge (added 3 in `test_static.py`).** This story should add ≥12 new tests (7 model + 5+ schema), so the suite should land around 360 passing.
- **Don't reorder existing imports or middleware blocks** — Story 1.14's review found an attempted reformat that broke a load-bearing comment. New imports go in alphabetical/grouped position per existing isort settings (`known-first-party = ["bff"]`).
- **The conftest's `engine` fixture creates ALL SQLModel metadata.** As long as `Book` is registered via the `entities/__init__.py` import, the `books` table will exist in every test's fresh DB.

### Git intelligence (recent commits)

```
060df66 feat: minor fixes to the CSFR token naming
ca02146 fix: BFF drops offline_access scope + realm declares profile scope
180b1e2 chore(1.14): code review — F1 path-traversal guard, F2 docstring fix, 5 defers; close epic-1
501a85a Merge story 1.14 — dev-story phase
96d6640 feat(1.14): BFF multi-stage build serves SPA bundle (closes D46, unblocks 5.4)
```

Epic 1 is closed. No in-flight work on the BFF as of `060df66`. Branch `epic-2` is the working branch for this story.

### Latest tech information

- **Pydantic v2** (already in BFF dependencies via the archetype). Idioms above match v2.x. No version bumps required.
- **SQLModel** is pinned via the archetype; `Field(default_factory=..., sa_column_kwargs={"onupdate": ...})` is the documented way to wire a SQLAlchemy `onupdate` through SQLModel.
- **Alembic** autogenerate against SQLModel metadata is the standard archetype workflow; `0001_init_init_sessions_and_auth_states.py` was generated this way.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1: BFF — Book SQLModel + migration + Pydantic boundary models]
- [Source: _bmad-output/planning-artifacts/architecture.md#AR7 — BFF schema] (`books` columns, `ix_books_sub` index)
- [Source: _bmad-output/planning-artifacts/architecture.md#AR20 — Pydantic boundary models]
- [Source: _bmad-output/planning-artifacts/architecture.md#C7. JSON serialization] (distinct API models; no `sub` in `BookOut`)
- [Source: _bmad-output/planning-artifacts/architecture.md#Naming Patterns] (plural snake_case tables, `ix_<table>_<col>` indexes, `PascalCase` model classes)
- [Source: _bmad-output/planning-artifacts/architecture.md#D1] (engine-agnostic SQLModel + Alembic)
- [Source: _bmad-output/planning-artifacts/PRD.md#FR2 (FR-BOOK-01)] (book = title + pages + status; ownership keyed by `sub`)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#BookForm] (title text, page count number with min 1, status default `to-read`)
- [Pattern: services/bff/src/bff/models/entities/session.py] (column style, timestamp factories)
- [Pattern: services/bff/alembic/versions/0001_init_init_sessions_and_auth_states.py] (migration body shape, `op.f` index naming)
- [Pattern: services/bff/tests/models/entities/test_session.py] (`_build_*` factory, `_as_utc` helper, fixture usage)
- [Gate: services/bff/pyproject.toml] (`[tool.coverage.report] fail_under = 90`; ruff `E,W,F,I,N,UP,B,SIM`; `ty` configured)

## Definition of Done

1. `Book` SQLModel exists at `services/bff/src/bff/models/entities/book.py` and is re-exported from `entities/__init__.py` (AC1, AC2).
2. `BookCreate`, `BookUpdate`, `BookOut` exist at `services/bff/src/bff/api/schemas/book.py` and behave per AC3/AC4.
3. Alembic migration `0002_add_books.py` exists; `upgrade` and `downgrade` round-trip cleanly against a 0001-state DB; autogenerate sanity check is no-op (AC5, AC6, AC7).
4. Model and schema test files exist and contain at least the cases listed in AC8/AC9.
5. Full `pytest` suite is green, coverage of the two new modules is ≥90%, and the suite size strictly increases (AC10).
6. `ruff check` and `ty check` report no new findings (AC10).
7. The epic-doc-vs-actual path translation (`db/models` → `models/entities`) is followed; no dead `src/bff/db/` directory is created.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code, dev-story workflow)

### Debug Log References

- `uv run alembic upgrade head` against `sqlite:////tmp/bff-mig-2-1.db` advanced `0001_init → 0002_add_books`; `.schema books` confirmed columns + `ix_books_sub` index.
- `uv run alembic downgrade -1` returned to `0001_init`; `sqlite3 .tables` showed only `alembic_version`, `auth_states`, `sessions`.
- AC7 autogenerate sanity check produced empty `upgrade()`/`downgrade()` (no schema drift); noop revision file deleted.
- `uv run pytest`: 367 passed (348 baseline + 19 new). `uv run ruff check`: clean. `uv run ty check`: clean.

### Completion Notes List

- Followed actual archetype layout `src/bff/models/entities/book.py` (epic doc's `src/bff/db/models/book.py` was a stale alias — see Dev Notes).
- `Book.id` is `int | None` PK with autoincrement (SQLite INTEGER PRIMARY KEY). `sub`, `title`, `pages`, `status`, `created_at`, `updated_at` all NOT NULL; `created_at`/`updated_at` use `default_factory=lambda: datetime.now(UTC)`, and `updated_at` adds `sa_column_kwargs={"onupdate": ...}` to advance on UPDATE — verified by `test_updated_at_advances_on_update`.
- No DB-level CHECK constraints or `SAEnum` for `pages`/`status` — application-level Pydantic enforcement only, consistent with `Session` and `AuthState` (Dev Notes "Why no DB-level CHECK constraints").
- Pydantic v2 idioms: `ConfigDict(from_attributes=True)`, `field_validator(mode="after")`. Shared `_strip_and_reject_blank` helper used by both `BookCreate` and `BookUpdate` to keep the whitespace-reject rule single-sourced.
- `BookOut` deliberately omits `sub` — verified by `test_book_out_roundtrips_from_orm` (asserts `"sub" not in dumped`).
- Empty-patch `BookUpdate()` is accepted at the model layer — Story 2.2's handler will decide whether to 4xx an empty PATCH.
- Side-effect to test harness: `tests/api/test_health.py::test_check_alembic_at_head_passes_when_current_matches_head` had hardcoded `0001_init` as the alembic head. Updated to read the head dynamically via `ScriptDirectory.from_config(AlembicConfig(str(_ALEMBIC_INI))).get_current_head()` so future migrations don't rot this test. The negative-path test (`...fails_when_current_differs_from_head`) still uses a mocked head string deliberately and was left untouched.
- Coverage on the two new modules: `bff/models/entities/book.py` 100% (11/11 stmts), `bff/api/schemas/book.py` 97% (28/29 stmts, the missing line is the `return v` early-return in `BookUpdate.title` validator when `v is None` — exercised by the empty-patch test but reported as not covered because Pydantic short-circuits the validator on `Optional[None]` defaults; well above the 90% gate).

### File List

**New:**
- `services/bff/src/bff/models/entities/book.py`
- `services/bff/src/bff/api/schemas/__init__.py`
- `services/bff/src/bff/api/schemas/book.py`
- `services/bff/alembic/versions/0002_add_books.py`
- `services/bff/tests/models/entities/test_book.py`
- `services/bff/tests/api/schemas/__init__.py`
- `services/bff/tests/api/schemas/test_book_schemas.py`

**Modified:**
- `services/bff/src/bff/models/entities/__init__.py` — added `Book` import and `__all__` entry.
- `services/bff/tests/api/test_health.py` — `test_check_alembic_at_head_passes_when_current_matches_head` now reads the alembic head dynamically (was hardcoded to `0001_init`).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `2-1-...` status moved `ready-for-dev → in-progress → review` (review write happens in story Step 9).

### Change Log

| Date       | Change                                                                                                      |
| ---------- | ----------------------------------------------------------------------------------------------------------- |
| 2026-05-16 | Story 2.1 implemented: `Book` SQLModel + Pydantic boundary models + Alembic 0002 migration + tests. Story moved to "review". |
| 2026-05-16 | Code review (4 patches applied): `title` max_length=500 + `pages` le=1_000_000 on `BookCreate`/`BookUpdate`; explicit `BookUpdate(title=None)` test; CWD-independent alembic-head test resolution. 370 tests pass, `schemas/book.py` coverage 100%. W1/W2 deferred. Story moved to "done". |
