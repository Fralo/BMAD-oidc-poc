"""Owns the lifecycle of `books` rows for the BFF's per-user book list
(Story 2.2).

All queries embed the `sub` predicate directly in SQL so cross-user
isolation is enforced at the database boundary rather than by an
in-Python post-check. See architecture line 685 + epic spec lines
819–821 for the "404 not 403" reasoning.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.api.schemas.book import BookCreate, BookUpdate
from bff.models import entities

logger = logging.getLogger(__name__)


def _safe_sub_log(sub: str) -> str:
    """Truncate `sub` to 8 chars + literal "..." only when actually truncated.

    Mirrors the `_safe_session_id_log` idiom from `session_service.py:235–238`
    (Story 1.7 Review Findings). For short subs (e.g. test fixtures) the
    literal "..." would lie about truncation, so it is only appended when
    `len(sub) > 8`.
    """
    if not sub:
        return "(none)"
    suffix = "..." if len(sub) > 8 else ""
    return f"{sub[:8]}{suffix}"


class BooksService:
    """Lifecycle owner for `books` rows. Per-user isolation via WHERE sub=:sub."""

    async def list_for_user(
        self,
        db: AsyncSession,
        *,
        sub: str,
    ) -> list[entities.Book]:
        """Return every book owned by `sub` ordered by `created_at` ASC."""
        result = await db.execute(
            select(entities.Book)
            .where(entities.Book.sub == sub)
            .order_by(entities.Book.created_at.asc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def get_for_user(
        self,
        db: AsyncSession,
        *,
        sub: str,
        book_id: int,
    ) -> entities.Book | None:
        """Return the single book matching `(book_id, sub)` or None.

        Both predicates compose in SQL — never fetch by id alone and check
        `row.sub` in Python (existence-leak risk + readability + races).
        """
        result = await db.execute(
            select(entities.Book)
            .where(entities.Book.id == book_id)
            .where(entities.Book.sub == sub)
        )
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        *,
        sub: str,
        payload: BookCreate,
    ) -> entities.Book:
        """Persist a new book for `sub` from a validated `BookCreate` payload.

        `id`, `created_at`, `updated_at` auto-populate from the SQLModel
        defaults (Story 2.1 AC1). No PK-collision retry loop is needed —
        `Book.id` is an autoincrementing int, not a generated opaque id.
        """
        book = entities.Book(
            sub=sub,
            title=payload.title,
            pages=payload.pages,
            status=payload.status,
        )
        db.add(book)
        await db.commit()
        await db.refresh(book)
        logger.info("book_created sub=%s id=%s", _safe_sub_log(sub), book.id)
        return book

    async def update(
        self,
        db: AsyncSession,
        *,
        sub: str,
        book_id: int,
        payload: BookUpdate,
    ) -> entities.Book | None:
        """Apply `payload`'s set fields to the row matching `(book_id, sub)`.

        Returns the refreshed row, or `None` if no matching row exists
        (handler translates None → 404 book_not_found). Uses
        `model_dump(exclude_unset=True)` so omitted fields keep their
        prior values rather than being clobbered to `None`/defaults.
        SQLModel's `onupdate` factory advances `updated_at` automatically.
        """
        book = await self.get_for_user(db, sub=sub, book_id=book_id)
        if book is None:
            return None
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(book, field, value)
        await db.commit()
        await db.refresh(book)
        return book

    async def delete(
        self,
        db: AsyncSession,
        *,
        sub: str,
        book_id: int,
    ) -> bool:
        """Delete the row matching `(book_id, sub)`. True if deleted, False
        if no matching row existed (handler translates False → 404).
        """
        book = await self.get_for_user(db, sub=sub, book_id=book_id)
        if book is None:
            return False
        await db.delete(book)
        await db.commit()
        logger.info("book_deleted sub=%s id=%s", _safe_sub_log(sub), book_id)
        return True
