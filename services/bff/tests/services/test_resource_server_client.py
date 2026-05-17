"""Tests for ``ResourceServerClient`` refresh-and-replay cycle (Story 3.5).

Covers the AC12 matrix:

* Refresh-and-replay happy path.
* Refresh succeeds but RS retry still 401 (cycle bounded).
* Refresh itself fails (4xx, 5xx, transport error, malformed response).
* `expires_at` advance on refresh.
* Refresh-token rotation persistence.
* NFR6 identity propagation (no `sub` in URL or body).
* Refresh-and-replay does NOT fire on 412 / 403 / 422 / 5xx.
* Single refresh attempt only (no double-refresh).
* Refresh request shape (grant_type, credentials).
* WARN/INFO logs.

These tests exercise ``ResourceServerClient`` directly (no proxy router).
Cookie-clearing behavior is verified at the proxy-router level in
``test_reading_speed_proxy.py``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.core.config import settings
from bff.models.entities.session import Session as SessionRow
from bff.services.resource_server_client import (
    ResourceServerClient,
    RsSessionTerminated,
    RsUnavailable,
    _RefreshFailed,
)
from bff.services.session_service import SessionService

_RS_BASE_URL = "http://rs.test"
_RS_READING_SPEED_URL = f"{_RS_BASE_URL}/v1/reading-speed"
_KEYCLOAK_ISSUER = "http://idp.test/realms/test"
_KEYCLOAK_TOKEN_URL = f"{_KEYCLOAK_ISSUER}/protocol/openid-connect/token"


@pytest.fixture
def rs_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point BFF settings at the respx mock hosts (RS + Keycloak)."""
    monkeypatch.setattr(settings, "rs_base_url", _RS_BASE_URL)
    monkeypatch.setattr(settings, "oidc_issuer_url", _KEYCLOAK_ISSUER)
    monkeypatch.setattr(settings, "oidc_client_id", "bmad-books-bff")
    monkeypatch.setattr(settings, "bff_client_secret", "test-secret")


async def _seed_session(
    session: AsyncSession,
    *,
    session_id: str = "sess-1234567890",
    sub: str = "user-a",
    access_token: str = "initial-at",
    refresh_token: str = "initial-rt",
    expires_at: datetime | None = None,
) -> SessionRow:
    if expires_at is None:
        expires_at = datetime.now(UTC) + timedelta(hours=1)
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


def _build_client() -> ResourceServerClient:
    return ResourceServerClient(settings, session_service=SessionService())


# ---------------------------------------------------------------------------
# Happy-path refresh-and-replay
# ---------------------------------------------------------------------------


async def test_refresh_and_replay_happy_path(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    client = _build_client()
    rs_call_seq: list[int] = []

    def _rs(request: httpx.Request) -> httpx.Response:
        rs_call_seq.append(1)
        token = request.headers.get("authorization", "")
        if token == "Bearer initial-at":
            return httpx.Response(401, json={"errorCode": "session_expired"})
        return httpx.Response(200, json={"pages_per_hour": 30})

    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(side_effect=_rs)
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-at",
                    "refresh_token": "new-rt",
                    "expires_in": 3600,
                },
            )
        )
        status, body = await client.get_reading_speed(session, row)
    assert status == 200
    assert body == {"pages_per_hour": 30}
    assert len(rs_call_seq) == 2  # one initial, one retry
    await session.refresh(row)
    assert row.access_token == "new-at"
    assert row.refresh_token == "new-rt"


async def test_refresh_and_replay_retry_still_401(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(401, json={"errorCode": "session_expired"})
        )
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-at",
                    "refresh_token": "new-rt",
                    "expires_in": 3600,
                },
            )
        )
        with pytest.raises(RsSessionTerminated) as exc_info:
            await client.get_reading_speed(session, row)
    assert exc_info.value.clear_cookies is False
    # Session row still exists (AC4 case 5).
    found = (
        await session.execute(select(SessionRow).where(SessionRow.id == row.id))
    ).first()
    assert found is not None


# ---------------------------------------------------------------------------
# Refresh failures
# ---------------------------------------------------------------------------


async def test_refresh_keycloak_4xx_terminates_session(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )
        with pytest.raises(RsSessionTerminated) as exc_info:
            await client.get_reading_speed(session, row)
    assert exc_info.value.clear_cookies is True
    # Session row deleted by client.
    found = (
        await session.execute(select(SessionRow).where(SessionRow.id == row.id))
    ).first()
    assert found is None


async def test_refresh_keycloak_5xx_terminates_session(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post(_KEYCLOAK_TOKEN_URL).mock(return_value=httpx.Response(503))
        with pytest.raises(RsSessionTerminated) as exc_info:
            await client.get_reading_speed(session, row)
    assert exc_info.value.clear_cookies is True
    found = (
        await session.execute(select(SessionRow).where(SessionRow.id == row.id))
    ).first()
    assert found is None


async def test_refresh_transport_error_terminates_session(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post(_KEYCLOAK_TOKEN_URL).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(RsSessionTerminated) as exc_info:
            await client.get_reading_speed(session, row)
    assert exc_info.value.clear_cookies is True


async def test_refresh_malformed_response_terminates_session(
    session: AsyncSession, rs_settings: None
) -> None:
    """Refresh response missing `access_token` is treated as a failure."""
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"foo": "bar"})  # no access_token
        )
        with pytest.raises(RsSessionTerminated) as exc_info:
            await client.get_reading_speed(session, row)
    assert exc_info.value.clear_cookies is True


async def test_refresh_response_missing_refresh_token_terminates_session(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "new-at"})
        )
        with pytest.raises(RsSessionTerminated) as exc_info:
            await client.get_reading_speed(session, row)
    assert exc_info.value.clear_cookies is True


# ---------------------------------------------------------------------------
# Refresh side effects (expires_at, rotation, logging)
# ---------------------------------------------------------------------------


async def test_refresh_advances_expires_at(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(
            side_effect=[
                httpx.Response(401),
                httpx.Response(200, json={"pages_per_hour": 30}),
            ]
        )
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-at",
                    "refresh_token": "new-rt",
                    "expires_in": 3600,
                },
            )
        )
        await client.get_reading_speed(session, row)
    await session.refresh(row)
    delta_seconds = (
        row.expires_at.replace(tzinfo=UTC) - datetime.now(UTC)
    ).total_seconds()
    assert 3500 < delta_seconds <= 3601


async def test_refresh_rotates_refresh_token(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(
            side_effect=[
                httpx.Response(401),
                httpx.Response(200, json={"pages_per_hour": 30}),
            ]
        )
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-at",
                    "refresh_token": "rotated-rt",
                    "expires_in": 3600,
                },
            )
        )
        await client.get_reading_speed(session, row)
    await session.refresh(row)
    assert row.refresh_token == "rotated-rt"


async def test_refresh_failure_emits_warn_log(
    session: AsyncSession,
    rs_settings: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.services.resource_server_client")
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(401, json={"error": "invalid_grant"})
        )
        with pytest.raises(RsSessionTerminated):
            await client.get_reading_speed(session, row)
    assert "refresh_failed" in caplog.text
    assert "keycloak_4xx" in caplog.text


async def test_refresh_happy_path_emits_info_log(
    session: AsyncSession,
    rs_settings: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="bff.services.resource_server_client")
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(
            side_effect=[
                httpx.Response(401),
                httpx.Response(200, json={"pages_per_hour": 30}),
            ]
        )
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-at",
                    "refresh_token": "new-rt",
                    "expires_in": 3600,
                },
            )
        )
        await client.get_reading_speed(session, row)
    assert "access_token_refreshed" in caplog.text


# ---------------------------------------------------------------------------
# Refresh-and-replay does NOT fire on non-401 responses
# ---------------------------------------------------------------------------


async def test_no_refresh_on_412(session: AsyncSession, rs_settings: None) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(412, json={"errorCode": "reading_speed_unset"})
        )
        token_route = mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(200, json={})
        )
        status, body = await client.get_reading_speed(session, row)
    assert status == 412
    assert rs_route.call_count == 1
    assert token_route.call_count == 0


async def test_no_refresh_on_403(session: AsyncSession, rs_settings: None) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(403, json={"errorCode": "forbidden_scope"})
        )
        token_route = mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(200, json={})
        )
        status, _ = await client.get_reading_speed(session, row)
    assert status == 403
    assert rs_route.call_count == 1
    assert token_route.call_count == 0


async def test_no_refresh_on_422(session: AsyncSession, rs_settings: None) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.put(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(422, json={"errorCode": "invalid_input"})
        )
        token_route = mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(200, json={})
        )
        status, _ = await client.put_reading_speed(session, row, {"pages_per_hour": 0})
    assert status == 422
    assert rs_route.call_count == 1
    assert token_route.call_count == 0


async def test_no_refresh_on_5xx(session: AsyncSession, rs_settings: None) -> None:
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(500)
        )
        token_route = mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(200, json={})
        )
        with pytest.raises(RsUnavailable):
            await client.get_reading_speed(session, row)
    assert rs_route.call_count == 1
    assert token_route.call_count == 0  # 5xx is the unavailable path, not refresh.


async def test_single_refresh_attempt_only(
    session: AsyncSession, rs_settings: None
) -> None:
    """RS 401 → refresh 200 → retry 401: exactly one /token call, two RS calls."""
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        rs_route = mock.get(_RS_READING_SPEED_URL).mock(
            return_value=httpx.Response(401)
        )
        token_route = mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-at",
                    "refresh_token": "new-rt",
                    "expires_in": 3600,
                },
            )
        )
        with pytest.raises(RsSessionTerminated):
            await client.get_reading_speed(session, row)
    assert rs_route.call_count == 2
    assert token_route.call_count == 1


# ---------------------------------------------------------------------------
# Refresh-request shape
# ---------------------------------------------------------------------------


async def test_refresh_uses_refresh_token_grant(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session, refresh_token="my-rt-xyz")
    client = _build_client()
    captured_requests: list[httpx.Request] = []

    def _capture_token(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "access_token": "new-at",
                "refresh_token": "new-rt",
                "expires_in": 3600,
            },
        )

    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(
            side_effect=[
                httpx.Response(401),
                httpx.Response(200, json={"pages_per_hour": 30}),
            ]
        )
        mock.post(_KEYCLOAK_TOKEN_URL).mock(side_effect=_capture_token)
        await client.get_reading_speed(session, row)
    assert len(captured_requests) == 1
    # Parse the form-encoded body.
    from urllib.parse import parse_qs

    body = parse_qs(captured_requests[0].content.decode())
    assert body["grant_type"] == ["refresh_token"]
    assert body["refresh_token"] == ["my-rt-xyz"]
    assert body["client_id"] == ["bmad-books-bff"]
    assert body["client_secret"] == ["test-secret"]


# ---------------------------------------------------------------------------
# NFR6 — identity propagation
# ---------------------------------------------------------------------------


async def test_no_sub_in_rs_url_or_body(
    session: AsyncSession, rs_settings: None
) -> None:
    row = await _seed_session(session)
    client = _build_client()
    captured_url: list[str] = []
    captured_body: list[bytes] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured_url.append(str(request.url))
        captured_body.append(request.content)
        return httpx.Response(200, json={"pages_per_hour": 30})

    with respx.mock(assert_all_called=False) as mock:
        mock.put(_RS_READING_SPEED_URL).mock(side_effect=_capture)
        await client.put_reading_speed(session, row, {"pages_per_hour": 30})
    assert "?" not in captured_url[0]
    assert "sub" not in captured_body[0].decode()


# ---------------------------------------------------------------------------
# Direct unit coverage for _RefreshFailed branches
# ---------------------------------------------------------------------------


async def test_refresh_failed_exception_carries_cause() -> None:
    exc = _RefreshFailed("test_cause")
    assert exc.cause == "test_cause"
    assert str(exc) == "test_cause"


async def test_rs_unavailable_exception_carries_cause_and_status() -> None:
    exc = RsUnavailable("connect_error")
    assert exc.cause == "connect_error"
    assert exc.http_status is None
    exc2 = RsUnavailable("rs_5xx_response", http_status=502)
    assert exc2.http_status == 502


async def test_rs_session_terminated_exception_carries_flag() -> None:
    exc = RsSessionTerminated(clear_cookies=True)
    assert exc.clear_cookies is True
    exc2 = RsSessionTerminated(clear_cookies=False)
    assert exc2.clear_cookies is False
