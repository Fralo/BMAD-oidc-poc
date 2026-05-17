"""Service-level tests for ``estimate_service.compute_for_user``.

Cover the business-logic invariants Story 4.1 enumerates: happy path,
missing-row 412 propagation, cross-user isolation, ceiling-rounding for
sub-minute reads, and the deliberate return-DTO-not-entity choice (vs.
``reading_speed_service``).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from resource_server.api.schemas.estimate import EstimateOut
from resource_server.core.exceptions import ReadingSpeedUnsetError
from resource_server.services import estimate_service, reading_speed_service


async def test_compute_for_user_happy_path(session: AsyncSession) -> None:
    """``pages_per_hour=30`` + ``pages=600`` → 1200 minutes / ``"≈ 20 h"``.

    Pins the rounding rule (``math.ceil(600 * 60 / 30) == 1200``) and the
    formatted-string contract (no minutes component when ``minutes % 60 == 0``).
    Mirrors Story 4.4's J3 happy-path input.
    """
    await reading_speed_service.upsert(session, sub="user-a", pages_per_hour=30)

    result = await estimate_service.compute_for_user(session, sub="user-a", pages=600)

    assert result.minutes == 1200
    assert result.formatted == "≈ 20 h"


async def test_compute_for_user_raises_reading_speed_unset_when_row_absent(
    session: AsyncSession,
) -> None:
    """Missing ``reading_speeds`` row propagates ``ReadingSpeedUnsetError`` from
    ``reading_speed_service.get_for_user`` — Story 4.1 reuses the existing
    service rather than duplicating the SELECT, so the 412 wire envelope is
    inherited via ``app_exception_handler``."""
    with pytest.raises(ReadingSpeedUnsetError):
        await estimate_service.compute_for_user(session, sub="orphan-sub", pages=600)


async def test_cross_user_isolation(session: AsyncSession) -> None:
    """Each user's estimate uses their own ``pages_per_hour`` row — no
    cross-contamination, no shared session state. AC10."""
    await reading_speed_service.upsert(session, sub="user-1", pages_per_hour=30)
    await reading_speed_service.upsert(session, sub="user-2", pages_per_hour=60)

    r1 = await estimate_service.compute_for_user(session, sub="user-1", pages=600)
    r2 = await estimate_service.compute_for_user(session, sub="user-2", pages=600)

    assert r1.minutes == 1200
    assert r2.minutes == 600
    # Each user's formatted string reflects their own row.
    assert r1.formatted == "≈ 20 h"
    assert r2.formatted == "≈ 10 h"


async def test_ceiling_round_up_partial_minute(session: AsyncSession) -> None:
    """Sub-minute raw values ceiling-round to 1, not 0. Pins the ``math.ceil``
    rule against a future floor-division regression that would silently
    underestimate quick reads.

    ``pages_per_hour=600`` + ``pages=1`` → raw 0.1 minute → ceiling 1.
    """
    await reading_speed_service.upsert(session, sub="speed-reader", pages_per_hour=600)

    result = await estimate_service.compute_for_user(
        session, sub="speed-reader", pages=1
    )

    assert result.minutes == 1
    assert result.formatted == "≈ 1 m"


async def test_returns_dto_not_entity(session: AsyncSession) -> None:
    """The service returns ``EstimateOut`` (DTO), NOT the ``ReadingSpeed``
    SQLModel entity. Pins the deliberate return-shape choice — see story
    Dev Notes "Why the service returns the DTO instead of the entity".
    A future refactor that returns the entity (or a tuple) will fail this
    assertion."""
    await reading_speed_service.upsert(session, sub="user-x", pages_per_hour=30)

    result = await estimate_service.compute_for_user(session, sub="user-x", pages=60)

    assert isinstance(result, EstimateOut)
    # Only the two contract fields; no entity-level fields leak through.
    assert set(result.model_dump().keys()) == {"minutes", "formatted"}


async def test_speed_change_yields_different_estimate(session: AsyncSession) -> None:
    """AC11 service-level: PUT-then-PUT-then-recompute returns strictly
    smaller minutes when ``pages_per_hour`` doubles. Pins the
    J4↔J3 coupling at the service layer (Story 4.4's J3 spec asserts it
    end-to-end)."""
    await reading_speed_service.upsert(session, sub="user-y", pages_per_hour=30)
    r1 = await estimate_service.compute_for_user(session, sub="user-y", pages=600)

    await reading_speed_service.upsert(session, sub="user-y", pages_per_hour=60)
    r2 = await estimate_service.compute_for_user(session, sub="user-y", pages=600)

    assert r1.minutes == 1200
    assert r2.minutes == 600
    assert r2.minutes < r1.minutes
