"""Tests for the `Session` SQLModel — round-trip, indexed lookups, expiry
filtering, default timestamps, the ``onupdate`` hook, and NOT NULL
constraints.

Per Story 1.4: the model is the persistence surface for Story 1.5's
cookie-session OIDC plugin. Stories 1.5+ own the value generation
(`secrets.token_urlsafe`); this story just verifies the column contract.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.models.entities.session import Session


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _build_session(**overrides: object) -> Session:
    base: dict[str, object] = {
        "id": "session-id-1",
        "sub": "user-sub-1",
        "access_token": "at-1",
        "refresh_token": "rt-1",
        "id_token": "it-1",
        "expires_at": datetime.now(UTC) + timedelta(minutes=15),
        "csrf_secret": "csrf-1",
    }
    base.update(overrides)
    return Session(**base)  # type: ignore[arg-type]


async def test_create_and_read_by_id(session: AsyncSession) -> None:
    row = _build_session()
    session.add(row)
    await session.commit()
    await session.refresh(row)

    fetched = await session.get(Session, "session-id-1")
    assert fetched is not None
    assert fetched.id == "session-id-1"
    assert fetched.sub == "user-sub-1"
    assert fetched.access_token == "at-1"
    assert fetched.refresh_token == "rt-1"
    assert fetched.id_token == "it-1"
    assert fetched.csrf_secret == "csrf-1"


async def test_query_by_sub_uses_indexed_lookup(session: AsyncSession) -> None:
    session.add(_build_session(id="s-a", sub="alice"))
    session.add(_build_session(id="s-b", sub="bob"))
    await session.commit()

    result = await session.execute(select(Session).where(Session.sub == "alice"))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].id == "s-a"


async def test_filter_expired_sessions(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    session.add(_build_session(id="s-fresh", expires_at=now + timedelta(minutes=10)))
    session.add(_build_session(id="s-stale", expires_at=now - timedelta(minutes=10)))
    await session.commit()

    result = await session.execute(select(Session).where(Session.expires_at < now))
    rows = result.scalars().all()
    assert [r.id for r in rows] == ["s-stale"]


async def test_created_at_and_updated_at_autopopulate(
    session: AsyncSession,
) -> None:
    before = datetime.now(UTC) - timedelta(seconds=1)
    row = _build_session()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    after = datetime.now(UTC) + timedelta(seconds=1)

    # Timestamps round-trip as naive datetimes through SQLite's DATETIME
    # storage; compare in UTC by treating the read-back value as UTC.
    assert before <= _as_utc(row.created_at) <= after
    assert before <= _as_utc(row.updated_at) <= after


async def test_updated_at_advances_on_mutation(session: AsyncSession) -> None:
    row = _build_session()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    initial_updated_at = _as_utc(row.updated_at)

    # Force a measurable wall-clock delta so the comparison is not microsecond-fragile.
    await asyncio.sleep(0.01)
    before_mutation = datetime.now(UTC)
    row.access_token = "rotated"
    session.add(row)
    await session.commit()
    await session.refresh(row)
    new_updated_at = _as_utc(row.updated_at)

    # Strict `>` against the initial value proves `onupdate` advanced the
    # column; `>= before_mutation` proves it was re-evaluated AFTER the
    # mutation point (not stale-cached from the insert).
    assert new_updated_at > initial_updated_at
    assert new_updated_at >= before_mutation
    assert row.access_token == "rotated"


@pytest.mark.parametrize(
    "missing_field",
    [
        "sub",
        "access_token",
        "refresh_token",
        "id_token",
        "expires_at",
        "csrf_secret",
    ],
)
async def test_not_null_columns_reject_none(
    session: AsyncSession, missing_field: str
) -> None:
    # SQLModel/Pydantic would reject None at construction for non-Optional types;
    # bypass validation to drive the IntegrityError at the database boundary.
    row = _build_session()
    object.__setattr__(row, missing_field, None)
    session.add(row)
    # `match=` pins the failure to the right column so an unrelated
    # IntegrityError (e.g., a PK collision from a fixture leak) cannot
    # satisfy this test silently.
    with pytest.raises(IntegrityError, match=rf"sessions\.{missing_field}"):
        await session.commit()
    await session.rollback()
