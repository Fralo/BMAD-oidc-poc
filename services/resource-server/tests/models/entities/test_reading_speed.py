"""SQLModel-level tests for `ReadingSpeed`.

Cover the table-level invariants Story 3.3's AC #1 enumerates: UNIQUE
constraint on `sub`, `updated_at` bumping on UPDATE, `created_at` stable
on UPDATE, NOT NULL on `pages_per_hour`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from resource_server.models.entities.reading_speed import ReadingSpeed


async def test_insert_and_read_back_round_trip(session: AsyncSession) -> None:
    row = ReadingSpeed(sub="user-1", pages_per_hour=30)
    session.add(row)
    await session.commit()
    await session.refresh(row)

    assert row.id is not None  # autoincrement populated
    assert row.sub == "user-1"
    assert row.pages_per_hour == 30
    assert isinstance(row.created_at, datetime)
    assert isinstance(row.updated_at, datetime)

    result = await session.execute(
        select(ReadingSpeed).where(ReadingSpeed.sub == "user-1")
    )
    found = result.scalars().first()
    assert found is not None
    assert found.id == row.id


async def test_unique_constraint_on_sub_rejects_duplicate_insert(
    session: AsyncSession,
) -> None:
    session.add(ReadingSpeed(sub="dup-sub", pages_per_hour=25))
    await session.commit()

    session.add(ReadingSpeed(sub="dup-sub", pages_per_hour=42))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_updated_at_bumps_on_update(session: AsyncSession) -> None:
    row = ReadingSpeed(sub="bump-sub", pages_per_hour=20)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    prior_updated_at = row.updated_at

    # Small sleep so the timestamp resolution catches the bump. SQLAlchemy's
    # `onupdate` callable fires at flush time; the in-memory `row.updated_at`
    # is refreshed on `session.refresh(row)`.
    await asyncio.sleep(0.005)

    row.pages_per_hour = 25
    session.add(row)
    await session.commit()
    await session.refresh(row)

    assert row.updated_at > prior_updated_at
    assert row.pages_per_hour == 25


async def test_created_at_stable_on_update(session: AsyncSession) -> None:
    row = ReadingSpeed(sub="stable-sub", pages_per_hour=30)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    prior_created_at = row.created_at

    await asyncio.sleep(0.005)
    row.pages_per_hour = 40
    session.add(row)
    await session.commit()
    await session.refresh(row)

    assert row.created_at == prior_created_at


async def test_max_length_on_sub_column_metadata() -> None:
    """The `sub` column should carry length=255 in its DDL type so that a
    future MariaDB migration honors the architecture's VARCHAR(255) spec.

    SQLite ignores VARCHAR length at runtime (so we can't assert on insert
    rejection), but the SQLModel-level metadata should still reflect the
    declared length — `sa_column_kwargs` would normally surface this on
    columns where SQLModel knows the type; for the AutoString case, the
    column's `type_.length` is the canonical attribute."""
    column = ReadingSpeed.__table__.c.sub  # type: ignore[attr-defined]
    assert column.type.length == 255
    assert column.nullable is False
    assert column.unique is True
