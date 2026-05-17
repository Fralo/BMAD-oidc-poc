"""Service-level tests for `reading_speed_service`.

Cover the business-logic invariants Story 3.3's AC #6 enumerates: get/upsert
behavior, cross-user isolation, ReadingSpeedUnsetError surfacing.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from resource_server.core.exceptions import ReadingSpeedUnsetError
from resource_server.services import reading_speed_service


async def test_get_for_user_returns_existing_row(session: AsyncSession) -> None:
    await reading_speed_service.upsert(session, sub="user-a", pages_per_hour=30)
    row = await reading_speed_service.get_for_user(session, sub="user-a")
    assert row.sub == "user-a"
    assert row.pages_per_hour == 30


async def test_get_for_user_raises_when_row_absent(session: AsyncSession) -> None:
    with pytest.raises(ReadingSpeedUnsetError):
        await reading_speed_service.get_for_user(session, sub="missing-sub")


async def test_upsert_insert_path_creates_new_row(session: AsyncSession) -> None:
    row = await reading_speed_service.upsert(session, sub="fresh", pages_per_hour=42)
    assert row.id is not None
    assert row.sub == "fresh"
    assert row.pages_per_hour == 42


async def test_upsert_update_path_bumps_value_and_updated_at(
    session: AsyncSession,
) -> None:
    first = await reading_speed_service.upsert(session, sub="user-b", pages_per_hour=20)
    first_id = first.id
    first_updated_at = first.updated_at

    await asyncio.sleep(0.005)
    second = await reading_speed_service.upsert(
        session, sub="user-b", pages_per_hour=50
    )

    assert second.id == first_id  # same row, no new insert
    assert second.pages_per_hour == 50
    assert second.updated_at > first_updated_at


async def test_upsert_cross_user_isolation(session: AsyncSession) -> None:
    """Two users with distinct subs each get their own row; one user's PUT
    does not affect the other's value (cross-user isolation enforced by the
    WHERE-clause on sub)."""
    await reading_speed_service.upsert(session, sub="user-a", pages_per_hour=30)
    await reading_speed_service.upsert(session, sub="user-b", pages_per_hour=50)

    a = await reading_speed_service.get_for_user(session, sub="user-a")
    b = await reading_speed_service.get_for_user(session, sub="user-b")

    assert a.pages_per_hour == 30
    assert b.pages_per_hour == 50
    assert a.id != b.id  # truly two rows


async def test_upsert_insert_path_sets_created_at_equal_to_updated_at(
    session: AsyncSession,
) -> None:
    """CR3 — Immediately after INSERT, ``created_at`` and ``updated_at``
    should be effectively equal (within μs tolerance). The bump-on-UPDATE
    test verifies the UPDATE path; this test pins the INSERT-path invariant
    so a future change to ``default_factory`` (e.g., decoupling the two
    timestamps) cannot silently introduce a skew."""
    row = await reading_speed_service.upsert(
        session, sub="fresh-insert-user", pages_per_hour=30
    )
    skew_seconds = (row.updated_at - row.created_at).total_seconds()
    # ``default_factory`` for the two fields fires at slightly different
    # times during ``ReadingSpeed.__init__``, but the gap should be
    # sub-millisecond on any reasonable host.
    assert abs(skew_seconds) < 0.01, (
        f"INSERT path produced created_at/updated_at skew of "
        f"{skew_seconds}s (expected ~0)"
    )
