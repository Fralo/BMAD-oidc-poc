"""Tests for GET /api/me — Story 1.3 contract: always 401 with session_expired.

Authenticated /api/me is Story 1.5's deliverable (cookie-session OIDC plugin).
Until then, this endpoint exists so the SPA's authGuard (Story 1.9) has a
stable 401 contract to develop against. Cookie presence/value is irrelevant
in this story — every call returns 401 with the same envelope.
"""

from httpx import AsyncClient


async def test_api_me_returns_401_session_expired_when_no_cookie(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/me")
    assert response.status_code == 401
    body = response.json()
    assert body == {
        "errorCode": "session_expired",
        "message": "Session expired or not present",
        "detail": None,
    }


async def test_api_me_returns_401_when_unknown_cookie_present(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/me", cookies={"unrelated": "value"})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_api_me_returns_401_even_when_session_cookie_set(
    client: AsyncClient,
) -> None:
    # Story 1.3 does not consume the session cookie; Story 1.5 will. For now,
    # presenting a cookie named bff_session must NOT change the 401 contract.
    response = await client.get("/api/me", cookies={"bff_session": "anything"})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
