"""SQLModel for the Resource Server's `reading_speeds` table.

One row per OIDC subject (`sub`). PUT is an upsert; GET returns 412 with
``errorCode: "reading_speed_unset"`` when no row exists for the caller's
``sub`` (architecture §"Format Patterns" line 690 — the SPA distinguishes
"unset" from transport 404 via the wire-code).

`sub` carries a UNIQUE index so the per-user-singleton invariant is enforced
at the DB layer as defense-in-depth on top of the service's
SELECT-then-INSERT pattern.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ReadingSpeed(SQLModel, table=True):
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
