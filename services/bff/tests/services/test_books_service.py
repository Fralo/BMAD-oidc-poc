"""Tests for `bff.services.books_service.BooksService` (Story 2.2).

Service-layer tests bypass the HTTP surface entirely and drive the
`session` AsyncSession fixture directly. The route layer's session/CSRF
concerns live in tests/api/test_books.py.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bff.api.schemas.book import BookCreate, BookUpdate
from bff.models import entities
from bff.services.books_service import BooksService


def _build_book(**overrides: object) -> entities.Book:
    """Mirrors Story 2.1's `_build_book`: a minimal valid `Book` row builder
    with `sub` defaulting to a deterministic test value and required fields
    filled in. Caller can override any column."""
    defaults: dict[str, object] = {
        "sub": "test-sub",
        "title": "Sample",
        "pages": 100,
        "status": "to-read",
    }
    defaults.update(overrides)
    return entities.Book(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# list_for_user
# ---------------------------------------------------------------------------


async def test_list_for_user_returns_empty_for_unknown_sub(
    session: AsyncSession,
) -> None:
    svc = BooksService()
    result = await svc.list_for_user(session, sub="nobody")
    assert result == []


async def test_list_for_user_returns_only_own_books_ordered_by_created_at(
    session: AsyncSession,
) -> None:
    base = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
    # Add out of order so we know ORDER BY is what produces the sequence.
    second = _build_book(
        sub="alice",
        title="Second",
        created_at=base + timedelta(seconds=10),
        updated_at=base + timedelta(seconds=10),
    )
    first = _build_book(sub="alice", title="First", created_at=base, updated_at=base)
    third = _build_book(
        sub="alice",
        title="Third",
        created_at=base + timedelta(seconds=20),
        updated_at=base + timedelta(seconds=20),
    )
    session.add_all([second, first, third])
    await session.commit()

    svc = BooksService()
    result = await svc.list_for_user(session, sub="alice")
    assert [b.title for b in result] == ["First", "Second", "Third"]


async def test_list_for_user_excludes_other_users_books(
    session: AsyncSession,
) -> None:
    session.add_all(
        [
            _build_book(sub="alice", title="A-1"),
            _build_book(sub="alice", title="A-2"),
            _build_book(sub="bob", title="B-1"),
            _build_book(sub="bob", title="B-2"),
            _build_book(sub="bob", title="B-3"),
        ]
    )
    await session.commit()

    svc = BooksService()
    alice_books = await svc.list_for_user(session, sub="alice")
    bob_books = await svc.list_for_user(session, sub="bob")
    assert len(alice_books) == 2
    assert len(bob_books) == 3
    assert all(b.sub == "alice" for b in alice_books)
    assert all(b.sub == "bob" for b in bob_books)


# ---------------------------------------------------------------------------
# get_for_user
# ---------------------------------------------------------------------------


async def test_get_for_user_returns_row_for_owner(session: AsyncSession) -> None:
    row = _build_book(sub="alice", title="Mine")
    session.add(row)
    await session.commit()
    await session.refresh(row)

    svc = BooksService()
    fetched = await svc.get_for_user(session, sub="alice", book_id=row.id)  # type: ignore[arg-type]
    assert fetched is not None
    assert fetched.id == row.id
    assert fetched.title == "Mine"


async def test_get_for_user_returns_none_for_unknown_id(
    session: AsyncSession,
) -> None:
    svc = BooksService()
    assert await svc.get_for_user(session, sub="alice", book_id=99999) is None


async def test_get_for_user_returns_none_for_other_user_id(
    session: AsyncSession,
) -> None:
    row = _build_book(sub="bob", title="Bob's")
    session.add(row)
    await session.commit()
    await session.refresh(row)

    svc = BooksService()
    assert await svc.get_for_user(session, sub="alice", book_id=row.id) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_create_persists_row_with_session_sub(
    session: AsyncSession,
) -> None:
    svc = BooksService()
    payload = BookCreate(title="Dune", pages=688, status="reading")
    book = await svc.create(session, sub="alice", payload=payload)

    assert book.id is not None
    assert book.sub == "alice"
    assert book.title == "Dune"
    assert book.pages == 688
    assert book.status == "reading"

    # Re-fetch via get_for_user — DB-side state confirms.
    fetched = await svc.get_for_user(session, sub="alice", book_id=book.id)
    assert fetched is not None
    assert fetched.sub == "alice"


async def test_create_uses_default_status_when_payload_omits_it(
    session: AsyncSession,
) -> None:
    svc = BooksService()
    # status omitted → BookCreate default "to-read".
    payload = BookCreate(title="The Hobbit", pages=310)
    book = await svc.create(session, sub="alice", payload=payload)
    assert book.status == "to-read"


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


async def test_update_applies_partial_payload(session: AsyncSession) -> None:
    row = _build_book(sub="alice", title="Original", pages=200, status="to-read")
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.id is not None

    svc = BooksService()
    # Only status — title and pages should keep their original values.
    payload = BookUpdate(status="reading")
    updated = await svc.update(
        session,
        sub="alice",
        book_id=row.id,
        payload=payload,
    )
    assert updated is not None
    assert updated.status == "reading"
    assert updated.title == "Original"
    assert updated.pages == 200


async def test_update_returns_none_for_unknown_id(session: AsyncSession) -> None:
    svc = BooksService()
    result = await svc.update(
        session, sub="alice", book_id=99999, payload=BookUpdate(status="reading")
    )
    assert result is None


async def test_update_returns_none_for_other_user_id(
    session: AsyncSession,
) -> None:
    row = _build_book(sub="bob", title="Bob's", pages=100)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.id is not None

    svc = BooksService()
    result = await svc.update(
        session,
        sub="alice",
        book_id=row.id,
        payload=BookUpdate(title="Hijacked"),
    )
    assert result is None
    # Bob's row unchanged.
    await session.refresh(row)
    assert row.title == "Bob's"


async def test_update_advances_updated_at(session: AsyncSession) -> None:
    row = _build_book(sub="alice", title="Time")
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.id is not None
    pre = row.updated_at

    # Brief sleep so the onupdate factory's `datetime.now(UTC)` returns a
    # strictly later value (resolution is sub-millisecond on POSIX, but
    # SQLite roundtrip strips subsecond on some drivers — be generous).
    await asyncio.sleep(0.02)

    svc = BooksService()
    updated = await svc.update(
        session,
        sub="alice",
        book_id=row.id,
        payload=BookUpdate(status="reading"),
    )
    assert updated is not None
    pre_aware = pre if pre.tzinfo is not None else pre.replace(tzinfo=UTC)
    post_aware = (
        updated.updated_at
        if updated.updated_at.tzinfo is not None
        else updated.updated_at.replace(tzinfo=UTC)
    )
    assert post_aware > pre_aware


async def test_update_with_empty_payload_returns_row_unchanged(
    session: AsyncSession,
) -> None:
    """`BookUpdate()` with no fields set → model_dump(exclude_unset=True)
    yields {}, so nothing changes. Service still returns the row."""
    row = _build_book(sub="alice", title="Untouched", pages=42, status="to-read")
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.id is not None

    svc = BooksService()
    result = await svc.update(
        session,
        sub="alice",
        book_id=row.id,
        payload=BookUpdate(),
    )
    assert result is not None
    assert result.title == "Untouched"
    assert result.pages == 42
    assert result.status == "to-read"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


async def test_delete_returns_true_when_deleted(session: AsyncSession) -> None:
    row = _build_book(sub="alice", title="Doomed")
    session.add(row)
    await session.commit()
    await session.refresh(row)

    svc = BooksService()
    result = await svc.delete(session, sub="alice", book_id=row.id)  # type: ignore[arg-type]
    assert result is True


async def test_delete_returns_false_for_unknown_id(session: AsyncSession) -> None:
    svc = BooksService()
    result = await svc.delete(session, sub="alice", book_id=99999)
    assert result is False


async def test_delete_returns_false_for_other_user_id(
    session: AsyncSession,
) -> None:
    row = _build_book(sub="bob", title="Bob's")
    session.add(row)
    await session.commit()
    await session.refresh(row)

    svc = BooksService()
    result = await svc.delete(session, sub="alice", book_id=row.id)  # type: ignore[arg-type]
    assert result is False
    # Row still exists.
    await session.refresh(row)
    assert row.id is not None


async def test_delete_actually_removes_row(session: AsyncSession) -> None:
    row = _build_book(sub="alice", title="Bye")
    session.add(row)
    await session.commit()
    await session.refresh(row)
    book_id = row.id
    assert book_id is not None

    svc = BooksService()
    await svc.delete(session, sub="alice", book_id=book_id)
    assert await svc.get_for_user(session, sub="alice", book_id=book_id) is None
