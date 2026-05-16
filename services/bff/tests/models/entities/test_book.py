"""Tests for the `Book` SQLModel — round-trip, indexed `sub` lookups,
default timestamps and `onupdate` advancement, default `status`,
DB-layer permissiveness for `pages`, and NOT NULL on `sub`.

Per Story 2.1: the model is the persistence surface for the books
CRUD landing in Story 2.2. Shape constraints (`pages >= 1`,
`status ∈ {to-read, reading, finished}`, non-empty title) are
enforced at the Pydantic boundary in `bff.api.schemas.book` —
this file only verifies the DB column contract.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.models.entities.book import Book


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _build_book(**overrides: object) -> Book:
    base: dict[str, object] = {
        "sub": "user-sub-1",
        "title": "Dune",
        "pages": 688,
        # `status` defaults to "to-read" via the SQLModel field default.
    }
    base.update(overrides)
    return Book(**base)  # type: ignore[arg-type]


async def test_create_and_read_by_id(session: AsyncSession) -> None:
    row = _build_book()
    session.add(row)
    await session.commit()
    await session.refresh(row)

    assert row.id is not None
    fetched = await session.get(Book, row.id)
    assert fetched is not None
    assert fetched.id == row.id
    assert fetched.sub == "user-sub-1"
    assert fetched.title == "Dune"
    assert fetched.pages == 688
    assert fetched.status == "to-read"


async def test_query_by_sub_uses_indexed_lookup(session: AsyncSession) -> None:
    session.add(_build_book(sub="alice", title="A"))
    session.add(_build_book(sub="bob", title="B"))
    await session.commit()

    result = await session.execute(select(Book).where(Book.sub == "alice"))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "A"


async def test_created_at_and_updated_at_autopopulate(
    session: AsyncSession,
) -> None:
    before = datetime.now(UTC) - timedelta(seconds=1)
    row = _build_book()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    after = datetime.now(UTC) + timedelta(seconds=1)

    # SQLite's DATETIME storage strips tzinfo on write; coerce read-back
    # values to UTC for an apples-to-apples comparison.
    assert before <= _as_utc(row.created_at) <= after
    assert before <= _as_utc(row.updated_at) <= after


async def test_updated_at_advances_on_update(session: AsyncSession) -> None:
    row = _build_book()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    initial_updated_at = _as_utc(row.updated_at)

    # `asyncio.sleep(0.01)` guarantees a measurable tick — smaller waits
    # can be eaten by clock resolution on fast CI.
    await asyncio.sleep(0.01)
    before_mutation = datetime.now(UTC)
    row.status = "reading"
    session.add(row)
    await session.commit()
    await session.refresh(row)
    new_updated_at = _as_utc(row.updated_at)

    assert new_updated_at > initial_updated_at
    assert new_updated_at >= before_mutation
    assert row.status == "reading"


async def test_default_status_is_to_read(session: AsyncSession) -> None:
    row = _build_book()
    session.add(row)
    await session.commit()
    await session.refresh(row)

    assert row.status == "to-read"


async def test_pages_accepts_positive_int_at_db_layer(
    session: AsyncSession,
) -> None:
    # Sanity: positivity is a Pydantic-layer concern, but the column
    # itself happily takes any integer. `pages=100` round-trips.
    row = _build_book(pages=100)
    session.add(row)
    await session.commit()
    await session.refresh(row)

    assert row.pages == 100


async def test_sub_not_null_at_db(session: AsyncSession) -> None:
    # SQLModel/Pydantic would reject `sub=None` at construction;
    # bypass validation so the IntegrityError is driven at the DB
    # boundary. `match=` pins the failure to the right column so an
    # unrelated IntegrityError (e.g., PK collision from a fixture leak)
    # cannot satisfy this test silently.
    row = _build_book()
    object.__setattr__(row, "sub", None)
    session.add(row)
    with pytest.raises(IntegrityError, match=r"books\.sub"):
        await session.commit()
    await session.rollback()
