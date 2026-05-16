"""SQLModel for the BFF's `books` table.

A `books` row holds a single user-owned book entry: the human-presented
title and page count plus the reading status, scoped to a Keycloak
subject via `sub`. The plural snake_case table name and `ix_books_sub`
index follow the project's naming pattern (architecture §Naming
Patterns); the `sub` index supports the per-user list queries Story
2.2 will issue (`SELECT ... WHERE sub = :current_user_sub`).

All shape constraints (`pages >= 1`, `status ∈ {to-read, reading,
finished}`, non-empty title) are enforced at the Pydantic boundary in
``bff.api.schemas.book`` — the DB column types stay engine-agnostic
and CHECK-free, matching the convention established by `Session` and
`AuthState`.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Book(SQLModel, table=True):
    __tablename__ = "books"

    id: int | None = Field(default=None, primary_key=True)
    sub: str = Field(max_length=255, index=True, nullable=False)
    title: str = Field(max_length=500, nullable=False)
    pages: int = Field(nullable=False)
    status: str = Field(default="to-read", nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
