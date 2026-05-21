"""Tests for `bff.services.session_service.SessionService`.

Exercises the lifecycle of `auth_states` / `sessions` rows the Story 1.5 OIDC
plugin owns: create, consume, expiry behavior, IntegrityError retry, and the
`safe_return_to` open-redirect validator (closes deferred-work.md#D33).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.models import entities
from bff.services import session_service as svc_mod
from bff.services.session_service import SessionService, safe_return_to

# ---------------------------------------------------------------------------
# safe_return_to — open-redirect validator (AC3 / D33)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/books", "/books"),
        ("/", "/"),
        ("/foo?bar=baz", "/foo?bar=baz"),
        ("/a/b/c", "/a/b/c"),
        # Open-redirect blockers — silent fallback to "/".
        ("//evil.example", "/"),
        ("https://evil.example", "/"),
        ("javascript:alert(1)", "/"),
        ("data:text/html,<script>", "/"),
        ("", "/"),
        (None, "/"),
        # Doesn't start with `/`
        ("books", "/"),
        # Length guardrail
        ("/" + "a" * 1025, "/"),
        # Length boundary — exactly 1024 chars survives.
        ("/" + "a" * 1022, "/" + "a" * 1022),
    ],
)
def test_safe_return_to(raw: str | None, expected: str) -> None:
    assert safe_return_to(raw) == expected


# ---------------------------------------------------------------------------
# create_auth_state
# ---------------------------------------------------------------------------


def _as_utc(dt: datetime) -> datetime:
    """SQLite roundtrips strip tzinfo (Story 1.4 D31)."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


async def test_create_auth_state_persists_row(
    session: AsyncSession,
) -> None:
    service = SessionService()
    row = await service.create_auth_state(session, return_to="/books")

    assert row.id
    assert row.state and row.state != row.id  # distinct opaque ids
    assert row.nonce and row.nonce != row.state
    # code_verifier is vestigial dead schema (default ""); see architecture.md.
    assert row.code_verifier == ""
    assert row.return_to == "/books"
    assert _as_utc(row.expires_at) > datetime.now(UTC)
    assert _as_utc(row.expires_at) < datetime.now(UTC) + timedelta(minutes=6)

    fetched = (
        (
            await session.execute(
                select(entities.AuthState).where(entities.AuthState.id == row.id)
            )
        )
        .scalars()
        .first()
    )
    assert fetched is not None
    assert fetched.state == row.state


async def test_create_auth_state_falls_back_unsafe_return_to(
    session: AsyncSession,
) -> None:
    service = SessionService()
    row = await service.create_auth_state(session, return_to="https://evil.example")
    assert row.return_to == "/"


async def test_create_auth_state_retries_on_integrity_error(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First two commits raise IntegrityError; third succeeds.

    Patching `AsyncSession.commit` is cleaner than colliding PKs on the real
    DB — SQLAlchemy's identity-map state after a rolled-back collision is
    fiddly to reason about. This exercises the retry code path directly.
    """
    real_commit = session.commit
    attempts = {"n": 0}

    async def _flaky_commit() -> None:
        attempts["n"] += 1
        if attempts["n"] < 3:
            await session.rollback()  # mimic IntegrityError-then-rollback
            raise IntegrityError("forced", {}, BaseException("forced"))
        await real_commit()

    monkeypatch.setattr(session, "commit", _flaky_commit)

    service = SessionService()
    row = await service.create_auth_state(session, return_to="/x")
    assert attempts["n"] == 3
    assert row.id  # successfully persisted


# ---------------------------------------------------------------------------
# consume_auth_state
# ---------------------------------------------------------------------------


async def test_consume_auth_state_returns_and_deletes_row(
    session: AsyncSession,
) -> None:
    service = SessionService()
    row = await service.create_auth_state(session, return_to="/books")
    consumed = await service.consume_auth_state(session, state=row.state)
    assert consumed is not None
    assert consumed.id == row.id

    # Replay: the row is gone.
    second = await service.consume_auth_state(session, state=row.state)
    assert second is None


async def test_consume_auth_state_missing_returns_none(
    session: AsyncSession,
) -> None:
    service = SessionService()
    result = await service.consume_auth_state(session, state="never-existed")
    assert result is None


async def test_consume_auth_state_expired_returns_none_and_deletes(
    session: AsyncSession,
) -> None:
    service = SessionService()
    expired = entities.AuthState(
        id="expired-id",
        state="expired-state",
        nonce="n",
        return_to="/",
        expires_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    session.add(expired)
    await session.commit()

    result = await service.consume_auth_state(session, state="expired-state")
    assert result is None

    refetch = (
        (
            await session.execute(
                select(entities.AuthState).where(entities.AuthState.id == "expired-id")
            )
        )
        .scalars()
        .first()
    )
    assert refetch is None


# ---------------------------------------------------------------------------
# create_session / get_session / delete_expired_session
# ---------------------------------------------------------------------------


async def test_create_session_persists_row(session: AsyncSession) -> None:
    service = SessionService()
    expires = datetime.now(UTC) + timedelta(hours=1)
    row = await service.create_session(
        session,
        sub="user-sub-1",
        access_token="at",
        refresh_token="rt",
        id_token="it",
        expires_at=expires,
    )
    assert row.id
    assert row.csrf_secret
    assert row.sub == "user-sub-1"
    assert row.access_token == "at"
    # Story 7.1: roles default to "" when no roles= kwarg is passed.
    assert row.roles == ""


async def test_create_session_persists_roles_sorted(session: AsyncSession) -> None:
    """Story 7.1 AC3: create_session persists the mapped role set as a
    comma-separated, alphabetically sorted string."""
    from bff.auth.role_mapping import Role

    service = SessionService()
    expires = datetime.now(UTC) + timedelta(hours=1)
    row = await service.create_session(
        session,
        sub="user-sub-roles",
        access_token="at",
        refresh_token="rt",
        id_token="it",
        expires_at=expires,
        roles=frozenset({Role.READER, Role.ADMIN}),
    )
    # Sorted alphabetically — admin precedes reader.
    assert row.roles == "admin,reader"


async def test_create_session_persists_empty_roles(session: AsyncSession) -> None:
    """Story 7.1 AC3: passing frozenset() persists the canonical empty string."""
    from bff.auth.role_mapping import Role

    service = SessionService()
    expires = datetime.now(UTC) + timedelta(hours=1)
    row = await service.create_session(
        session,
        sub="user-sub-no-roles",
        access_token="at",
        refresh_token="rt",
        id_token="it",
        expires_at=expires,
        roles=frozenset(),
    )
    assert row.roles == ""
    # Sanity: single-role serialization is also tested via the mapper unit
    # tests, but pin the through-the-service path too.
    row2 = await service.create_session(
        session,
        sub="user-sub-single-role",
        access_token="at",
        refresh_token="rt",
        id_token="it",
        expires_at=expires,
        roles=frozenset({Role.READER}),
    )
    assert row2.roles == "reader"


async def test_get_session_returns_row_or_none(session: AsyncSession) -> None:
    service = SessionService()
    expires = datetime.now(UTC) + timedelta(hours=1)
    created = await service.create_session(
        session,
        sub="sub-x",
        access_token="a",
        refresh_token="r",
        id_token="i",
        expires_at=expires,
    )
    fetched = await service.get_session(session, session_id=created.id)
    assert fetched is not None
    assert fetched.sub == "sub-x"

    missing = await service.get_session(session, session_id="not-a-real-id")
    assert missing is None


async def test_delete_session_removes_row(session: AsyncSession) -> None:
    """`delete_session` removes the row regardless of `expires_at` (the
    explicit logout case)."""
    service = SessionService()
    row = entities.Session(
        id="logout-sess",
        sub="sub-l",
        access_token="a",
        refresh_token="r",
        id_token="i",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        csrf_secret="c",
    )
    session.add(row)
    await session.commit()

    await service.delete_session(session, session_id="logout-sess")
    assert await service.get_session(session, session_id="logout-sess") is None


async def test_delete_session_is_idempotent_when_missing(
    session: AsyncSession,
) -> None:
    """Calling delete_session against an unknown id is a no-op (no exception)."""
    service = SessionService()
    # Seed an unrelated row to confirm we don't nuke neighbors by mistake.
    row = entities.Session(
        id="neighbor",
        sub="sub-n",
        access_token="a",
        refresh_token="r",
        id_token="i",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        csrf_secret="c",
    )
    session.add(row)
    await session.commit()

    await service.delete_session(session, session_id="does-not-exist")
    assert await service.get_session(session, session_id="neighbor") is not None


async def test_delete_expired_session_removes_only_expired(
    session: AsyncSession,
) -> None:
    service = SessionService()
    expired_session = entities.Session(
        id="expired-sess",
        sub="sub-e",
        access_token="a",
        refresh_token="r",
        id_token="i",
        expires_at=datetime.now(UTC) - timedelta(minutes=10),
        csrf_secret="c",
    )
    live_session = entities.Session(
        id="live-sess",
        sub="sub-l",
        access_token="a",
        refresh_token="r",
        id_token="i",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        csrf_secret="c",
    )
    session.add_all([expired_session, live_session])
    await session.commit()

    await service.delete_expired_session(session, session_id="expired-sess")
    assert await service.get_session(session, session_id="expired-sess") is None

    # No-op for live sessions.
    await service.delete_expired_session(session, session_id="live-sess")
    assert await service.get_session(session, session_id="live-sess") is not None

    # No-op for missing ids.
    await service.delete_expired_session(session, session_id="does-not-exist")


# ---------------------------------------------------------------------------
# IntegrityError retry exhaustion — defense in depth (D40)
# ---------------------------------------------------------------------------


async def test_create_session_retry_exhausts_then_raises(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pre-insert a row that will collide on every attempted id.
    locked = entities.Session(
        id="locked-id",
        sub="x",
        access_token="a",
        refresh_token="r",
        id_token="i",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        csrf_secret="c",
    )
    session.add(locked)
    await session.commit()

    monkeypatch.setattr(svc_mod, "_new_opaque_id", lambda: "locked-id")

    service = SessionService()
    with pytest.raises(RuntimeError, match="session insert collided"):
        await service.create_session(
            session,
            sub="x2",
            access_token="a",
            refresh_token="r",
            id_token="i",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )


async def test_create_auth_state_retry_exhausts_then_raises(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locked = entities.AuthState(
        id="locked-state-id",
        state="s",
        nonce="n",
        return_to="/",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    session.add(locked)
    await session.commit()

    monkeypatch.setattr(svc_mod, "_new_opaque_id", lambda: "locked-state-id")

    service = SessionService()
    with pytest.raises(RuntimeError, match="auth_state insert collided"):
        await service.create_auth_state(session, return_to="/books")


# `IntegrityError` is imported but referenced only via SQLAlchemy internals;
# `noqa` suppression is unnecessary because we DO use it (parametrize doesn't
# show it). Keep the import to mark intent: this file exercises IntegrityError
# behavior via real DB collisions.
_ = IntegrityError
