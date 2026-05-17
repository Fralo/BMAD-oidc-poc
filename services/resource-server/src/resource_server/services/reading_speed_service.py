"""Business logic for /v1/reading-speed.

Singleton-per-user semantics: one ``reading_speeds`` row per OIDC ``sub``.
GET → row or ``ReadingSpeedUnsetError``; PUT is an upsert.

The UNIQUE index on ``sub`` is defense-in-depth against racing INSERTs;
the service does not catch ``IntegrityError`` in v1 because FastAPI's
transaction-per-request model + small load makes the race effectively
impossible. A 500 is preferable to silent data loss if the race ever
materializes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from resource_server.core.exceptions import ReadingSpeedUnsetError
from resource_server.models.entities.reading_speed import ReadingSpeed


async def get_for_user(session: AsyncSession, sub: str) -> ReadingSpeed:
    """Return the caller's row or raise ``ReadingSpeedUnsetError`` if absent."""
    result = await session.execute(select(ReadingSpeed).where(ReadingSpeed.sub == sub))
    row = result.scalars().first()
    if row is None:
        raise ReadingSpeedUnsetError()
    return row


async def upsert(session: AsyncSession, sub: str, pages_per_hour: int) -> ReadingSpeed:
    """Insert or update the caller's ``reading_speeds`` row.

    Returns the committed-and-refreshed row.
    """
    result = await session.execute(select(ReadingSpeed).where(ReadingSpeed.sub == sub))
    row = result.scalars().first()
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
