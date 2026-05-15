"""Tests for the `AuthState` SQLModel — round-trip, expiry filter,
nullable ``return_to``, and NOT NULL constraints.

Per Story 1.4: this model holds in-flight PKCE state between
``/auth/login`` and ``/auth/callback`` (Story 1.5).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.models.entities.auth_state import AuthState


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _build_auth_state(**overrides: object) -> AuthState:
    base: dict[str, object] = {
        "id": "auth-state-1",
        "code_verifier": "verifier-1",
        "state": "state-1",
        "nonce": "nonce-1",
        "return_to": "/books",
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
    }
    base.update(overrides)
    return AuthState(**base)  # type: ignore[arg-type]


async def test_create_and_read_by_id(session: AsyncSession) -> None:
    row = _build_auth_state()
    session.add(row)
    await session.commit()

    fetched = await session.get(AuthState, "auth-state-1")
    assert fetched is not None
    assert fetched.code_verifier == "verifier-1"
    assert fetched.state == "state-1"
    assert fetched.nonce == "nonce-1"
    assert fetched.return_to == "/books"


async def test_filter_expired_rows(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    session.add(_build_auth_state(id="as-fresh", expires_at=now + timedelta(minutes=2)))
    session.add(_build_auth_state(id="as-stale", expires_at=now - timedelta(minutes=2)))
    await session.commit()

    result = await session.execute(select(AuthState).where(AuthState.expires_at < now))
    rows = result.scalars().all()
    assert [r.id for r in rows] == ["as-stale"]


async def test_return_to_is_nullable(session: AsyncSession) -> None:
    row = _build_auth_state(id="as-noreturn", return_to=None)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.return_to is None


async def test_created_at_autopopulates(session: AsyncSession) -> None:
    before = datetime.now(UTC) - timedelta(seconds=1)
    row = _build_auth_state()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    after = datetime.now(UTC) + timedelta(seconds=1)

    assert before <= _as_utc(row.created_at) <= after


@pytest.mark.parametrize(
    "missing_field",
    ["code_verifier", "state", "nonce", "expires_at"],
)
async def test_not_null_columns_reject_none(
    session: AsyncSession, missing_field: str
) -> None:
    row = _build_auth_state()
    object.__setattr__(row, missing_field, None)
    session.add(row)
    # `match=` pins the failure to the right column.
    with pytest.raises(IntegrityError, match=rf"auth_states\.{missing_field}"):
        await session.commit()
    await session.rollback()
