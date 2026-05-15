"""Tests for GET /api/me — Story 1.5: session-cookie-driven identity endpoint.

Returns 200 `{sub, preferred_username}` for a valid session cookie; 401 with
`session_expired` envelope for missing/unknown/expired cookies. Expired
sessions are deleted lazily on access.
"""

from datetime import UTC, datetime, timedelta

import jwt
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bff.models import entities
from bff.services.session_service import SessionService


async def _seed_session(
    session: AsyncSession,
    *,
    sub: str = "test-sub-1",
    preferred_username: str = "testuser",
    expires_offset_seconds: int = 3600,
) -> entities.Session:
    """Insert a `sessions` row with a self-signed id_token (no verification)."""
    service = SessionService()
    now_ts = int(datetime.now(UTC).timestamp())
    id_token = jwt.encode(
        {
            "sub": sub,
            "preferred_username": preferred_username,
            "iss": "http://idp.test/realms/test",
            "aud": "test-client",
            "exp": now_ts + expires_offset_seconds,
            "iat": now_ts,
            "nonce": "n",
        },
        "test-secret-only-used-for-encoding",  # noqa: S106 -- not a real secret
        algorithm="HS256",
    )
    return await service.create_session(
        session,
        sub=sub,
        access_token="at",
        refresh_token="rt",
        id_token=id_token,
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_offset_seconds),
    )


async def test_api_me_returns_401_when_no_cookie(client: AsyncClient) -> None:
    response = await client.get("/api/me")
    assert response.status_code == 401
    assert response.json() == {
        "errorCode": "session_expired",
        "message": "Session expired or not present",
        "detail": None,
    }


async def test_api_me_returns_401_when_unknown_session_id(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/me", cookies={"bff_session": "never-existed"})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_api_me_returns_200_for_valid_session(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row = await _seed_session(session, sub="user-sub-9", preferred_username="alice")
    response = await client.get("/api/me", cookies={"bff_session": row.id})
    assert response.status_code == 200
    assert response.json() == {"sub": "user-sub-9", "preferred_username": "alice"}


async def test_api_me_returns_401_and_deletes_expired_session(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row = await _seed_session(session, sub="expired-sub", expires_offset_seconds=-60)
    response = await client.get("/api/me", cookies={"bff_session": row.id})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"

    # Expired session was deleted as a side effect.
    service = SessionService()
    assert await service.get_session(session, session_id=row.id) is None


async def test_api_me_uses_empty_preferred_username_when_claim_missing(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """If the stored id_token has no `preferred_username` claim, the response
    still returns 200 with an empty string (defensive — claim is optional)."""
    service = SessionService()
    now_ts = int(datetime.now(UTC).timestamp())
    bare_token = jwt.encode(
        {"sub": "u", "iss": "x", "aud": "x", "exp": now_ts + 600, "iat": now_ts},
        "secret",  # noqa: S106 -- test-only HS256 secret
        algorithm="HS256",
    )
    row = await service.create_session(
        session,
        sub="bare-sub",
        access_token="at",
        refresh_token="rt",
        id_token=bare_token,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    response = await client.get("/api/me", cookies={"bff_session": row.id})
    assert response.status_code == 200
    assert response.json() == {"sub": "bare-sub", "preferred_username": ""}


async def test_api_me_returns_401_when_id_token_is_malformed(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """A corrupted id_token in the DB triggers the defensive parse-fail branch."""
    service = SessionService()
    row = await service.create_session(
        session,
        sub="corrupt-sub",
        access_token="at",
        refresh_token="rt",
        id_token="this is not a JWT",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    response = await client.get("/api/me", cookies={"bff_session": row.id})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
