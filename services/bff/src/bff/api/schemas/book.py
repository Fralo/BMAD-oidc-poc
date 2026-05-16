"""Pydantic v2 boundary models for the books domain.

These models guard the wire-format contract for `/v1/books*` (Story 2.2):

* `BookCreate` — request body for POST. All fields required.
* `BookUpdate` — request body for PATCH. All fields optional;
  empty-patch semantics are deliberately punted to the handler.
* `BookOut` — response body. Built from a `Book` ORM instance via
  `model_validate(...)`; intentionally omits `sub` so the per-user
  ownership column never leaks into responses (architecture §C7).

Constraint enforcement lives here (not at the DB layer) — see
`bff.models.entities.book` for the rationale.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BookStatus = Literal["to-read", "reading", "finished"]


def _strip_and_reject_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("title must not be empty or whitespace-only")
    return stripped


class BookCreate(BaseModel):
    # `max_length=500` mirrors the `Book.title` column cap so the API
    # 422s on overlong input instead of letting it through to a 500
    # on engines that enforce VARCHAR (Postgres/MySQL).
    # `le=1_000_000` keeps `pages` within `Number.MAX_SAFE_INTEGER` and
    # comfortably below 32-bit `INTEGER` overflow on non-SQLite engines.
    title: str = Field(min_length=1, max_length=500)
    pages: int = Field(ge=1, le=1_000_000)
    status: BookStatus = "to-read"

    @field_validator("title", mode="after")
    @classmethod
    def _title_not_blank_after_strip(cls, v: str) -> str:
        return _strip_and_reject_blank(v)


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    pages: int | None = Field(default=None, ge=1, le=1_000_000)
    status: BookStatus | None = None

    @field_validator("title", mode="after")
    @classmethod
    def _title_not_blank_after_strip(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _strip_and_reject_blank(v)


class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    pages: int
    status: BookStatus
    created_at: datetime
    updated_at: datetime
