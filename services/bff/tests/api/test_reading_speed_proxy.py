"""Tests for the BFF's ``/v1/reading-speed`` proxy router (Story 3.5).

Covers the AC11 matrix:

* Happy GET/PUT body-verbatim forwarding (200, 412, 403, 422 cases).
* Session-check failures (missing cookie, unknown id, expired row).
* CSRF enforcement on PUT.
* RS 5xx + transport failures → 503 ``resource_server_unavailable`` with no
  retry (called exactly once).
* NFR6 identity propagation — request URL has no query, body has no ``sub``.
* OpenAPI surface lists ``/v1/reading-speed`` GET + PUT.

Uses ``respx`` to mock the RS endpoint (the BFF's ``ResourceServerClient``
issues outbound httpx calls; respx intercepts them at the transport layer).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bff.core.config import settings
from bff.models.entities.session import Session as SessionRow

_RS_BASE_URL = "http://rs.test"
_RS_READING_SPEED_URL = f"{_RS_BASE_URL}/v1/reading-speed"
_SESSION_COOKIE_NAME = "bff_session"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def rs_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the BFF's settings at the respx mock host."""
    monkeypatch.setattr(settings, "rs_base_url", _RS_BASE_URL)


async def _seed_session(
    session: AsyncSession,
    *,
    session_id: str = "sess-1234567890",
    sub: str = "user-a",
    access_token: str = "initial-at",
    refresh_token: str = "initial-rt",
    expires_at: datetime | None = None,
) -> SessionRow:
    """Insert a `sessions` row and commit so the proxy's session lookup hits."""
    if expires_at is None:
        expires_at = datetime.now(UTC) + timedelta(hours=1)
    # SQLite stores naive datetimes; mirror the existing me.py / session_service
    # pattern that compares via _as_utc_aware. Store naive UTC.
    row = SessionRow(
        id=session_id,
        sub=sub,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token="dummy-id-token",
        expires_at=expires_at.replace(tzinfo=None),
        csrf_secret="dummy-csrf-secret",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def _set_session_cookie(client: AsyncClient, session_id: str) -> None:
    client.cookies.set(_SESSION_COOKIE_NAME, session_id)


# ---------------------------------------------------------------------------
# Happy-path forwarding tests
# ---------------------------------------------------------------------------


async def test_get_happy_200_forwards_body(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(200, json={"pages_per_hour": 30})
        )
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 200
    assert response.json() == {"pages_per_hour": 30}
    assert rs_route.call_count == 1


async def test_get_rs_412_forwards_envelope(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    envelope = {
        "errorCode": "reading_speed_unset",
        "message": "Reading speed not set for this user",
        "detail": None,
    }
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(412, json=envelope)
        )
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 412
    assert response.json() == envelope


async def test_get_rs_403_forwards_envelope(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    envelope = {
        "errorCode": "forbidden_scope",
        "message": "Required scope is missing",
        "detail": None,
    }
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(403, json=envelope)
        )
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 403
    assert response.json() == envelope


async def test_get_no_session_cookie_returns_401(
    client: AsyncClient, rs_settings: None
) -> None:
    response = await client.get("/v1/reading-speed")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_get_unknown_session_id_returns_401(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    _set_session_cookie(client, "nonexistent-session-id")
    response = await client.get("/v1/reading-speed")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"


async def test_get_expired_session_returns_401_and_deletes_row(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    expired_at = datetime.now(UTC) - timedelta(hours=1)
    row = await _seed_session(session, expires_at=expired_at)
    _set_session_cookie(client, row.id)
    response = await client.get("/v1/reading-speed")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    # The expired row was lazily deleted (mirrors api/me.py:67).
    from sqlmodel import select

    found = (
        await session.execute(select(SessionRow).where(SessionRow.id == row.id))
    ).first()
    assert found is None


async def test_put_happy_200_forwards_body(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    _set_session_cookie(client_with_csrf, row.id)
    with respx.mock(assert_all_called=False) as mock:
        mock.put(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(200, json={"pages_per_hour": 45})
        )
        response = await client_with_csrf.put(
            "/v1/reading-speed", json={"pages_per_hour": 45}
        )
    assert response.status_code == 200
    assert response.json() == {"pages_per_hour": 45}


async def test_put_missing_csrf_returns_403(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    """Without the `client_with_csrf` fixture, the CSRF middleware rejects PUT."""
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    response = await client.put("/v1/reading-speed", json={"pages_per_hour": 30})
    assert response.status_code == 403
    assert response.json()["errorCode"] == "csrf_invalid"


async def test_put_rs_422_forwards_envelope(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    _set_session_cookie(client_with_csrf, row.id)
    envelope = {
        "errorCode": "invalid_input",
        "message": "Request validation failed",
        "detail": [
            {
                "loc": ["body", "pages_per_hour"],
                "msg": "ge",
                "type": "value_error",
            }
        ],
    }
    with respx.mock(assert_all_called=False) as mock:
        mock.put(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(422, json=envelope)
        )
        response = await client_with_csrf.put(
            "/v1/reading-speed", json={"pages_per_hour": 0}
        )
    assert response.status_code == 422
    assert response.json() == envelope


async def test_put_rs_403_forwards_envelope(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    _set_session_cookie(client_with_csrf, row.id)
    envelope = {
        "errorCode": "forbidden_scope",
        "message": "Required scope is missing",
        "detail": None,
    }
    with respx.mock(assert_all_called=False) as mock:
        mock.put(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(403, json=envelope)
        )
        response = await client_with_csrf.put(
            "/v1/reading-speed", json={"pages_per_hour": 30}
        )
    assert response.status_code == 403
    assert response.json() == envelope


async def test_put_body_forwarded_verbatim_no_sub_no_query(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    """NFR6: no `sub` injection, no query string."""
    row = await _seed_session(session)
    _set_session_cookie(client_with_csrf, row.id)
    captured_body: list[bytes] = []
    captured_url: list[str] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured_body.append(request.content)
        captured_url.append(str(request.url))
        return httpx.Response(200, json={"pages_per_hour": 30})

    with respx.mock(assert_all_called=False) as mock:
        mock.put(_RS_READING_SPEED_URL).mock(side_effect=_capture)
        response = await client_with_csrf.put(
            "/v1/reading-speed", json={"pages_per_hour": 30}
        )
    assert response.status_code == 200
    assert len(captured_body) == 1
    import json as _json

    body_dict = _json.loads(captured_body[0])
    assert body_dict == {"pages_per_hour": 30}
    assert "sub" not in body_dict
    # URL has no query string.
    assert "?" not in captured_url[0]


# ---------------------------------------------------------------------------
# 503 / transport-error tests
# ---------------------------------------------------------------------------


async def test_get_rs_connect_error_returns_503(
    client: AsyncClient,
    session: AsyncSession,
    rs_settings: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.services.resource_server_client")
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            side_effect=httpx.ConnectError("refused")
        )
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "resource_server_unavailable"
    assert rs_route.call_count == 1  # No retry on transport failure.
    assert "cause=connect_error" in caplog.text


async def test_get_rs_read_timeout_returns_503(
    client: AsyncClient,
    session: AsyncSession,
    rs_settings: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.services.resource_server_client")
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            side_effect=httpx.ReadTimeout("slow")
        )
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "resource_server_unavailable"
    assert rs_route.call_count == 1
    assert "cause=read_timeout" in caplog.text


async def test_get_rs_500_returns_503(
    client: AsyncClient,
    session: AsyncSession,
    rs_settings: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.services.resource_server_client")
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "resource_server_unavailable"
    assert rs_route.call_count == 1
    assert "cause=rs_5xx_response" in caplog.text


async def test_get_rs_502_returns_503(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(502)
        )
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "resource_server_unavailable"
    assert rs_route.call_count == 1


async def test_get_rs_503_returns_503(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(503)
        )
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "resource_server_unavailable"
    assert rs_route.call_count == 1


async def test_put_rs_504_returns_503(
    client_with_csrf: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    _set_session_cookie(client_with_csrf, row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.put(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(504)
        )
        response = await client_with_csrf.put(
            "/v1/reading-speed", json={"pages_per_hour": 30}
        )
    assert response.status_code == 503
    assert response.json()["errorCode"] == "resource_server_unavailable"
    assert rs_route.call_count == 1


async def test_put_rs_write_timeout_returns_503(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
    rs_settings: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.services.resource_server_client")
    row = await _seed_session(session)
    _set_session_cookie(client_with_csrf, row.id)
    with respx.mock(assert_all_called=False) as mock:
        mock.put(_RS_READING_SPEED_URL).mock(
            side_effect=httpx.WriteTimeout("slow write")
        )
        response = await client_with_csrf.put(
            "/v1/reading-speed", json={"pages_per_hour": 30}
        )
    assert response.status_code == 503
    assert "cause=write_timeout" in caplog.text


async def test_no_retry_on_5xx(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    """Proves AC6 'no silent cross-service retries' — exactly ONE call."""
    row = await _seed_session(session)
    _set_session_cookie(client, row.id)
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(500)
        )
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 503
    assert rs_route.call_count == 1


async def test_authorization_header_carries_bearer_access_token(
    client: AsyncClient, session: AsyncSession, rs_settings: None
) -> None:
    """The RS request carries `Authorization: Bearer <session.access_token>`."""
    row = await _seed_session(session, access_token="my-token-xyz")
    _set_session_cookie(client, row.id)
    captured_headers: list[dict[str, str]] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured_headers.append(dict(request.headers))
        return httpx.Response(200, json={"pages_per_hour": 30})

    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(side_effect=_capture)
        response = await client.get("/v1/reading-speed")
    assert response.status_code == 200
    assert len(captured_headers) == 1
    assert captured_headers[0]["authorization"] == "Bearer my-token-xyz"


async def test_refresh_failure_clears_cookies_and_returns_401(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
    rs_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When refresh fails, the proxy emits 401 with both cookies cleared."""
    monkeypatch.setattr(settings, "oidc_issuer_url", "http://idp.test/realms/test")
    monkeypatch.setattr(settings, "oidc_client_id", "bmad-books-bff")
    monkeypatch.setattr(settings, "bff_client_secret", "test-secret")
    row = await _seed_session(session)
    _set_session_cookie(client_with_csrf, row.id)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post("http://idp.test/realms/test/protocol/openid-connect/token").mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )
        response = await client_with_csrf.get("/v1/reading-speed")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    set_cookie_headers = response.headers.get_list("set-cookie")
    # Two Set-Cookie headers — session + csrf — both Max-Age=0.
    assert len(set_cookie_headers) == 2
    joined = "\n".join(set_cookie_headers).lower()
    assert "bff_session=" in joined
    assert "csrf_token=" in joined
    assert "max-age=0" in joined


async def test_refresh_succeeds_but_retry_still_401_no_cookie_clear(
    client_with_csrf: AsyncClient,
    session: AsyncSession,
    rs_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh worked, retry 401: proxy emits 401 WITHOUT clearing cookies."""
    monkeypatch.setattr(settings, "oidc_issuer_url", "http://idp.test/realms/test")
    monkeypatch.setattr(settings, "oidc_client_id", "bmad-books-bff")
    monkeypatch.setattr(settings, "bff_client_secret", "test-secret")
    row = await _seed_session(session)
    _set_session_cookie(client_with_csrf, row.id)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post("http://idp.test/realms/test/protocol/openid-connect/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-at",
                    "refresh_token": "new-rt",
                    "expires_in": 3600,
                },
            )
        )
        response = await client_with_csrf.get("/v1/reading-speed")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    # No Set-Cookie clearing (the session row stays in place).
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert set_cookie_headers == []


async def test_openapi_lists_reading_speed_paths(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/v1/reading-speed" in paths
    assert "get" in paths["/v1/reading-speed"]
    assert "put" in paths["/v1/reading-speed"]
